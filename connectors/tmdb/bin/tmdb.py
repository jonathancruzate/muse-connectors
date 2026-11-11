#!/usr/bin/env python3
"""TMDB CLI — custom.tmdb connector helper.

Auth: the vault-held API Read Access Token (v4) reaches requests only via
the dynamic-credentials surrogate (Authorization: Bearer placement, as
registered). The real token never appears in this file, argv, env, or logs.

Usage:
  tmdb.py search "query" [--limit N]
  tmdb.py movie <id>
  tmdb.py tv <id>
  tmdb.py trending [all|movie|tv] [--limit N]
  tmdb.py providers <movie|tv> <id>     (US watch providers)
  tmdb.py similar <movie|tv> <id> [--limit N]
"""
import json, sys, urllib.parse, urllib.request
sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
from dynamic_credentials import add_surrogate_to_request, read_json_response

BASE = "https://api.themoviedb.org/3"
HOSTS = ["api.themoviedb.org"]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise RuntimeError("redirect refused, verify the endpoint")


def get(path, params=None):
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)
    add_surrogate_to_request(req, "custom.tmdb", allowed_hosts=HOSTS)
    opener = urllib.request.build_opener(NoRedirect())
    with opener.open(req, timeout=30) as resp:
        return read_json_response(resp)


def brief(item):
    media = item.get("media_type") or ("movie" if "title" in item or "release_date" in item else "tv")
    return {
        "id": item.get("id"),
        "media_type": media,
        "title": item.get("title") or item.get("name"),
        "date": item.get("release_date") or item.get("first_air_date"),
        "vote_average": item.get("vote_average"),
        "overview": (item.get("overview") or "")[:240],
    }


def cmd_search(args):
    limit = 10
    if "--limit" in args:
        i = args.index("--limit"); limit = int(args[i + 1]); args = args[:i] + args[i + 2:]
    data = get("/search/multi", {"query": " ".join(args), "include_adult": "false"})
    out = [brief(x) for x in data.get("results", []) if x.get("media_type") in ("movie", "tv")][:limit]
    print(json.dumps(out, ensure_ascii=False))


def cmd_detail(kind, args):
    data = get(f"/{kind}/{args[0]}", {"append_to_response": "credits,external_ids"})
    keep = ["id", "title", "name", "tagline", "overview", "release_date", "first_air_date",
            "runtime", "episode_run_time", "number_of_seasons", "number_of_episodes",
            "vote_average", "vote_count", "status", "genres", "original_language"]
    out = {k: data.get(k) for k in keep if k in data}
    cast = (data.get("credits") or {}).get("cast") or []
    out["cast"] = [{"name": c.get("name"), "character": c.get("character")} for c in cast[:8]]
    print(json.dumps(out, ensure_ascii=False))


def cmd_trending(args):
    limit = 10
    if "--limit" in args:
        i = args.index("--limit"); limit = int(args[i + 1]); args = args[:i] + args[i + 2:]
    kind = args[0] if args else "all"
    data = get(f"/trending/{kind}/week")
    print(json.dumps([brief(x) for x in data.get("results", [])][:limit], ensure_ascii=False))


def cmd_providers(args):
    kind, tid = args[0], args[1]
    data = get(f"/{kind}/{tid}/watch/providers")
    us = (data.get("results") or {}).get("US") or {}
    out = {k: [p.get("provider_name") for p in us.get(k, [])] for k in ("flatrate", "rent", "buy") if us.get(k)}
    out["link"] = us.get("link")
    print(json.dumps(out, ensure_ascii=False))


def cmd_similar(args):
    limit = 10
    rest = args
    if "--limit" in rest:
        i = rest.index("--limit"); limit = int(rest[i + 1]); rest = rest[:i] + rest[i + 2:]
    kind, tid = rest[0], rest[1]
    data = get(f"/{kind}/{tid}/similar")
    print(json.dumps([brief(x) for x in data.get("results", [])][:limit], ensure_ascii=False))


def main():
    if len(sys.argv) < 2:
        print(__doc__); return 1
    cmd, args = sys.argv[1], sys.argv[2:]
    try:
        if cmd == "search":
            cmd_search(args)
        elif cmd == "movie":
            cmd_detail("movie", args)
        elif cmd == "tv":
            cmd_detail("tv", args)
        elif cmd == "trending":
            cmd_trending(args)
        elif cmd == "providers":
            cmd_providers(args)
        elif cmd == "similar":
            cmd_similar(args)
        else:
            print(f"unknown command: {cmd}\n{__doc__}"); return 1
    except urllib.error.HTTPError as e:
        print(json.dumps({"error": "http", "status": e.code, "body": e.read().decode("utf-8", "replace")[:300]}))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
