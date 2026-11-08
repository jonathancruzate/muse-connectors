#!/usr/bin/env python3
"""Public-data pack: no-auth official/public APIs mined from MuseAi-Bypass (2026-11-08).

Every route here was live-tested 2026-11-08 (see CONNECTOR.md for the
per-route verdicts). Stdlib only. Usage:

  public_data.py fda-label <drug name> [--limit N]
  public_data.py fda-event <drug name> [--limit N]
  public_data.py trials <query> [--limit N]
  public_data.py gdelt <query> [--limit N]
  public_data.py news-rss <query> [--limit N]
  public_data.py hn <query> [--limit N]
  public_data.py mastodon <query> [--limit N]
  public_data.py bluesky-actors <query> [--limit N]
  public_data.py polymarket [<query>] [--limit N]
  public_data.py lemmy <query> [--limit N]
  public_data.py peertube <query> [--limit N]
  public_data.py imdb-status
  public_data.py muse-jobs [<keyword>] [--limit N]
  public_data.py remotive [<keyword>] [--limit N]

Output is a compact JSON summary, never a raw dump.
"""
import argparse, json, sys, urllib.parse, urllib.request
import xml.etree.ElementTree as ET

UA = {"User-Agent": "Mozilla/5.0 (Muse public-data pack)"}

def get_json(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

def get_text(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")

def out(obj):
    print(json.dumps(obj, indent=1, ensure_ascii=False)[:6000])

def q(s):
    return urllib.parse.quote_plus(s)

def cmd_fda_label(a):
    d = get_json(f"https://api.fda.gov/drug/label.json?search=openfda.brand_name:%22{q(a.query)}%22&limit={a.limit}")
    res = []
    for r in d.get("results", []):
        of = r.get("openfda", {})
        res.append({"brand": of.get("brand_name"), "generic": of.get("generic_name"),
                    "manufacturer": of.get("manufacturer_name"),
                    "purpose": (r.get("purpose") or [""])[0][:200]})
    out({"source": "openFDA drug/label", "count": len(res), "results": res})

def cmd_fda_event(a):
    d = get_json(f"https://api.fda.gov/drug/event.json?search=patient.drug.medicinalproduct:%22{q(a.query)}%22&limit={a.limit}")
    res = []
    for r in d.get("results", []):
        res.append({"date": r.get("receivedate"),
                    "reactions": [x.get("reactionmeddrapt") for x in r.get("patient", {}).get("reaction", [])][:5],
                    "serious": r.get("serious")})
    out({"source": "openFDA drug/event (raw FAERS reports, unverified)", "count": len(res), "results": res})

def cmd_trials(a):
    d = get_json(f"https://clinicaltrials.gov/api/v2/studies?query.term={q(a.query)}&pageSize={a.limit}&format=json")
    res = []
    for s in d.get("studies", []):
        p = s.get("protocolSection", {})
        res.append({"nct": p.get("identificationModule", {}).get("nctId"),
                    "title": p.get("identificationModule", {}).get("briefTitle"),
                    "status": p.get("statusModule", {}).get("overallStatus"),
                    "phases": p.get("designModule", {}).get("phases")})
    out({"source": "ClinicalTrials.gov API v2", "count": len(res), "results": res})

def cmd_gdelt(a):
    d = get_json(f"https://api.gdeltproject.org/api/v2/doc/doc?query={q(a.query)}&mode=ArtList&maxrecords={a.limit}&format=json&timespan=7d", timeout=40)
    res = [{"title": x.get("title"), "url": x.get("url"), "domain": x.get("domain"),
            "date": x.get("seendate"), "language": x.get("language")} for x in d.get("articles", [])]
    out({"source": "GDELT doc API (7d)", "count": len(res), "results": res})

def cmd_news_rss(a):
    url = f"https://news.google.com/rss/search?q={q(a.query)}&hl=en-US&gl=US&ceid=US:en" if a.query else "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en"
    root = ET.fromstring(get_text(url))
    res = []
    for item in root.iter("item"):
        res.append({"title": item.findtext("title"), "link": item.findtext("link"),
                    "date": item.findtext("pubDate"), "source": (item.find("source").text if item.find("source") is not None else None)})
        if len(res) >= a.limit: break
    out({"source": "Google News RSS", "count": len(res), "results": res})

def cmd_hn(a):
    d = get_json(f"https://hn.algolia.com/api/v1/search?query={q(a.query)}&hitsPerPage={a.limit}")
    res = [{"title": h.get("title") or h.get("story_title"), "url": h.get("url"),
            "points": h.get("points"), "comments": h.get("num_comments"),
            "date": h.get("created_at")} for h in d.get("hits", [])]
    out({"source": "Hacker News (Algolia)", "count": len(res), "results": res})

def cmd_mastodon(a):
    d = get_json(f"https://mastodon.social/api/v2/search?q={q(a.query)}&type=accounts&limit={a.limit}")
    res = [{"acct": x.get("acct"), "name": x.get("display_name"), "followers": x.get("followers_count"),
            "url": x.get("url")} for x in d.get("accounts", [])]
    out({"source": "Mastodon public API (mastodon.social accounts)", "count": len(res), "results": res})

def cmd_bluesky(a):
    d = get_json(f"https://public.api.bsky.app/xrpc/app.bsky.actor.searchActors?q={q(a.query)}&limit={a.limit}")
    res = [{"handle": x.get("handle"), "name": x.get("display_name"),
            "description": (x.get("description") or "")[:160]} for x in d.get("actors", [])]
    out({"source": "Bluesky public API (actor search; post search is restricted)", "count": len(res), "results": res})

def cmd_polymarket(a):
    url = f"https://gamma-api.polymarket.com/events?limit={a.limit}&active=true&closed=false"
    if a.query: url += f"&search={q(a.query)}"
    d = get_json(url)
    res = [{"title": x.get("title"), "slug": x.get("slug"), "volume": x.get("volume"),
            "end": x.get("endDate")} for x in d]
    out({"source": "Polymarket Gamma API", "count": len(res), "results": res})

def cmd_lemmy(a):
    d = get_json(f"https://lemmy.world/api/v3/search?q={q(a.query)}&limit={a.limit}")
    res = [{"type": x.get("type"), "name": (x.get("community", {}) or x.get("post", {}) or {}).get("name") or (x.get("post", {}) or {}).get("name"),
            } for x in (d.get("communities", []) + d.get("posts", []))][:a.limit]
    out({"source": "Lemmy API (lemmy.world)", "count": len(res), "results": res})

def cmd_peertube(a):
    d = get_json(f"https://sepiasearch.org/api/v1/search/videos?search={q(a.query)}&count={a.limit}")
    res = [{"name": x.get("name"), "channel": (x.get("channel") or {}).get("displayName"),
            "views": x.get("views"), "url": x.get("url")} for x in d.get("data", [])]
    out({"source": "PeerTube SepiaSearch", "total": d.get("total"), "count": len(res), "results": res})

def cmd_imdb_status(a):
    req = urllib.request.Request("https://datasets.imdbws.com/title.basics.tsv.gz", headers=UA, method="HEAD")
    with urllib.request.urlopen(req, timeout=25) as r:
        out({"source": "IMDb datasets", "status": r.status,
             "title.basics.tsv.gz bytes": r.headers.get("Content-Length"),
             "note": "Bulk TSV datasets (basics/ratings/akas/episode/crew/principals/names); download on demand only, they are large."})

def muse_remotive_common(kind, a):
    if kind == "muse":
        d = get_json(f"https://www.themuse.com/api/public/jobs?page=0&page_limit={a.limit}" + (f"&category={q(a.query)}" if a.query else ""))
        res = [{"title": x.get("name"), "company": (x.get("company") or {}).get("name"),
                "locations": [l.get("name") for l in x.get("locations", [])],
                "url": (x.get("refs") or {}).get("landing_page"), "date": x.get("publication_date")} for x in d.get("results", [])[:a.limit]]
        out({"source": "The Muse jobs API", "page_count": d.get("page_count"), "count": len(res), "results": res})
    else:
        d = get_json(f"https://remotive.com/api/remote-jobs?limit={a.limit}" + (f"&search={q(a.query)}" if a.query else ""))
        res = [{"title": x.get("title"), "company": x.get("company_name"), "salary": x.get("salary"),
                "url": x.get("url"), "date": x.get("publication_date")} for x in d.get("jobs", [])[:a.limit]]
        out({"source": "Remotive jobs API", "count": len(res), "results": res})

def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    def add(name, fn, query=True):
        s = sub.add_parser(name); s.set_defaults(fn=fn)
        if query: s.add_argument("query")
        s.add_argument("--limit", type=int, default=5)
    add("fda-label", cmd_fda_label); add("fda-event", cmd_fda_event)
    add("trials", cmd_trials); add("gdelt", cmd_gdelt); add("hn", cmd_hn)
    add("mastodon", cmd_mastodon); add("bluesky-actors", cmd_bluesky)
    add("lemmy", cmd_lemmy); add("peertube", cmd_peertube)
    s = sub.add_parser("news-rss"); s.set_defaults(fn=cmd_news_rss); s.add_argument("query", nargs="?", default=""); s.add_argument("--limit", type=int, default=5)
    s = sub.add_parser("polymarket"); s.set_defaults(fn=cmd_polymarket); s.add_argument("query", nargs="?", default=""); s.add_argument("--limit", type=int, default=5)
    s = sub.add_parser("imdb-status"); s.set_defaults(fn=cmd_imdb_status)
    s = sub.add_parser("muse-jobs"); s.set_defaults(fn=lambda a: muse_remotive_common("muse", a)); s.add_argument("query", nargs="?", default=""); s.add_argument("--limit", type=int, default=5)
    s = sub.add_parser("remotive"); s.set_defaults(fn=lambda a: muse_remotive_common("remotive", a)); s.add_argument("query", nargs="?", default=""); s.add_argument("--limit", type=int, default=5)
    a = p.parse_args()
    try:
        a.fn(a)
    except Exception as e:
        print(json.dumps({"error": str(e)[:300], "cmd": a.cmd})); sys.exit(1)

if __name__ == "__main__":
    main()
