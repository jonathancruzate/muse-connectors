#!/usr/bin/env python3
"""Guardian CLI — custom.guardian connector helper.

Auth: the vault-held Developer API key reaches requests only via the
dynamic-credentials surrogate as the `api-key` query parameter (as
registered). The real key never appears in this file, argv, env, or logs.

Usage:
  guardian.py search "query" [--limit N] [--section ID]
  guardian.py sections
  guardian.py item <content-id>     e.g. world/2026/nov/11/some-slug
"""
import json, sys, urllib.parse, urllib.request
sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
from dynamic_credentials import url_with_surrogate_query_param, read_json_response

BASE = "https://content.guardianapis.com"
HOSTS = ["content.guardianapis.com"]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise RuntimeError("redirect refused, verify the endpoint")


def get(path, params=None):
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    url = url_with_surrogate_query_param(url, "custom.guardian", allowed_hosts=HOSTS)
    req = urllib.request.Request(url)
    opener = urllib.request.build_opener(NoRedirect())
    with opener.open(req, timeout=30) as resp:
        return read_json_response(resp)


def article(item):
    f = item.get("fields") or {}
    return {
        "id": item.get("id"),
        "title": item.get("webTitle"),
        "section": item.get("sectionName"),
        "published": item.get("webPublicationDate"),
        "url": item.get("webUrl"),
        "byline": f.get("byline"),
        "trail": f.get("trailText"),
    }


def cmd_search(args):
    limit = 10
    section = None
    rest = []
    i = 0
    while i < len(args):
        if args[i] == "--limit":
            limit = int(args[i + 1]); i += 2
        elif args[i] == "--section":
            section = args[i + 1]; i += 2
        else:
            rest.append(args[i]); i += 1
    params = {"q": " ".join(rest), "page-size": min(limit, 50), "order-by": "newest",
              "show-fields": "trailText,byline"}
    if section:
        params["section"] = section
    data = get("/search", params)
    out = [article(x) for x in (data.get("response") or {}).get("results", [])][:limit]
    print(json.dumps(out, ensure_ascii=False))


def cmd_sections(args):
    data = get("/sections")
    out = [{"id": s.get("id"), "title": s.get("webTitle")} for s in (data.get("response") or {}).get("results", [])]
    print(json.dumps(out, ensure_ascii=False))


def cmd_item(args):
    cid = args[0].lstrip("/")
    data = get("/" + cid, {"show-fields": "trailText,byline,bodyText"})
    c = (data.get("response") or {}).get("content") or {}
    out = article(c)
    body = (c.get("fields") or {}).get("bodyText") or ""
    out["body_excerpt"] = body[:1500]
    print(json.dumps(out, ensure_ascii=False))


def main():
    if len(sys.argv) < 2:
        print(__doc__); return 1
    cmd, args = sys.argv[1], sys.argv[2:]
    try:
        if cmd == "search":
            cmd_search(args)
        elif cmd == "sections":
            cmd_sections(args)
        elif cmd == "item":
            cmd_item(args)
        else:
            print(f"unknown command: {cmd}\n{__doc__}"); return 1
    except urllib.error.HTTPError as e:
        print(json.dumps({"error": "http", "status": e.code, "body": e.read().decode("utf-8", "replace")[:300]}))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
