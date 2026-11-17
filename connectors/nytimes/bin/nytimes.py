#!/usr/bin/env python3
"""NYT CLI — custom.nytimes connector helper.

Auth: the vault-held app API key reaches requests only via the
dynamic-credentials surrogate as the `api-key` query parameter (as
registered). The real key never appears in this file, argv, env, or logs.

Rate limits (free key): 500 requests/day, 5/minute. Keep calls sparse.

Usage:
  nytimes.py topstories [section] [--limit N]     section default: home
  nytimes.py search "query" [--limit N] [--begin YYYYMMDD] [--end YYYYMMDD]
  nytimes.py popular [emailed|shared|viewed] [1|7|30] [--limit N]
  nytimes.py books [list-name]                    default: hardcover-fiction
"""
import json, sys, urllib.parse, urllib.request
sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
from dynamic_credentials import url_with_surrogate_query_param, read_json_response

BASE = "https://api.nytimes.com/svc"
HOSTS = ["api.nytimes.com"]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise RuntimeError("redirect refused, verify the endpoint")


def get(path, params=None):
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    url = url_with_surrogate_query_param(url, "custom.nytimes", allowed_hosts=HOSTS)
    req = urllib.request.Request(url)
    opener = urllib.request.build_opener(NoRedirect())
    with opener.open(req, timeout=30) as resp:
        return read_json_response(resp)


def take_limit(args, default=10):
    limit = default
    rest = []
    i = 0
    while i < len(args):
        if args[i] == "--limit":
            limit = int(args[i + 1]); i += 2
        else:
            rest.append(args[i]); i += 1
    return limit, rest


def story(r):
    return {
        "title": r.get("title"),
        "abstract": (r.get("abstract") or "")[:280],
        "url": r.get("url"),
        "section": r.get("section"),
        "published": r.get("published_date"),
        "byline": r.get("byline"),
    }


def cmd_topstories(args):
    limit, rest = take_limit(args)
    section = rest[0] if rest else "home"
    data = get(f"/topstories/v2/{section}.json")
    print(json.dumps([story(r) for r in data.get("results", [])][:limit], ensure_ascii=False))


def cmd_search(args):
    limit = 10
    begin = end = None
    rest = []
    i = 0
    while i < len(args):
        if args[i] == "--limit":
            limit = int(args[i + 1]); i += 2
        elif args[i] == "--begin":
            begin = args[i + 1]; i += 2
        elif args[i] == "--end":
            end = args[i + 1]; i += 2
        else:
            rest.append(args[i]); i += 1
    params = {"q": " ".join(rest), "sort": "newest"}
    if begin: params["begin_date"] = begin
    if end: params["end_date"] = end
    data = get("/search/v2/articlesearch.json", params)
    docs = (data.get("response") or {}).get("docs", [])
    out = [{
        "headline": (d.get("headline") or {}).get("main"),
        "abstract": (d.get("abstract") or "")[:280],
        "url": d.get("web_url"),
        "published": d.get("pub_date"),
        "section": d.get("section_name"),
        "byline": ((d.get("byline") or {}).get("original")),
    } for d in docs][:limit]
    print(json.dumps(out, ensure_ascii=False))


def cmd_popular(args):
    limit, rest = take_limit(args)
    kind = rest[0] if len(rest) > 0 else "viewed"
    days = rest[1] if len(rest) > 1 else "7"
    data = get(f"/mostpopular/v2/{kind}/{days}.json")
    print(json.dumps([story(r) for r in data.get("results", [])][:limit], ensure_ascii=False))


def cmd_books(args):
    list_name = args[0] if args else "hardcover-fiction"
    data = get(f"/books/v3/lists/current/{list_name}.json")
    books = ((data.get("results") or {}).get("books")) or []
    out = [{"rank": b.get("rank"), "title": b.get("title"), "author": b.get("author"),
            "weeks_on_list": b.get("weeks_on_list")} for b in books]
    print(json.dumps(out, ensure_ascii=False))


def main():
    if len(sys.argv) < 2:
        print(__doc__); return 1
    cmd, args = sys.argv[1], sys.argv[2:]
    try:
        if cmd == "topstories":
            cmd_topstories(args)
        elif cmd == "search":
            cmd_search(args)
        elif cmd == "popular":
            cmd_popular(args)
        elif cmd == "books":
            cmd_books(args)
        else:
            print(f"unknown command: {cmd}\n{__doc__}"); return 1
    except urllib.error.HTTPError as e:
        print(json.dumps({"error": "http", "status": e.code, "body": e.read().decode("utf-8", "replace")[:300]}))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
