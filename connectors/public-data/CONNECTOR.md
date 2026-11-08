# Public Data (no-auth APIs)

## Purpose
One CLI for the no-auth official/public API routes Muse did **not** already
have, mined 2026-11-08 from Git-FED/MuseAi-Bypass at Jonathan's order
("do it all") — mining record: `~/workspace/museai-bypass-mining-2026-11-08.md`.
The source repo is tracked in the GitHub updater registry (id `museai-bypass`,
watch policy, pushed commit f346ab1).

No credential exists for this connector: every route below is public and
keyless. Do not invent a key flow for it. Tier-2 keyed routes (TMDB, Adzuna,
USAJOBS, Guardian, CourtListener, Census) are NOT in this pack — they are
documented as key-pending in the mining file.

## Tool
`~/workspace/custom-connectors/custom.public-data/bin/public_data.py` (stdlib
only, JSON summary output, multi-word queries must be quoted):

| Command | Route | Verified 2026-11-08 |
|---|---|---|
| `fda-label "Vyvanse"` | openFDA drug/label | 200, real label returned |
| `fda-event "Vyvanse"` | openFDA drug/event (FAERS) | 200 — raw unverified reports, never present as established effects |
| `trials "ulcerative colitis"` | ClinicalTrials.gov API v2 | 200 |
| `gdelt "query"` | GDELT doc API, 7d window | 200 twice; intermittent 429 rate limit — back off and retry, do not hammer |
| `news-rss "query"` | Google News RSS search (empty query = top news) | 200 |
| `hn "query"` | Hacker News via Algolia | 200 |
| `mastodon "query"` | Mastodon public search (accounts, mastodon.social) | 200 |
| `bluesky-actors "query"` | Bluesky public actor search | 200 — post search (`searchPosts`) is 403-restricted, do not promise it |
| `polymarket ["query"]` | Polymarket Gamma events | 200 |
| `lemmy "query"` | Lemmy search (lemmy.world) | 200, sparse fields |
| `peertube "query"` | PeerTube SepiaSearch | 200 |
| `imdb-status` | IMDb datasets reachability | 200 — title.basics.tsv.gz alone is ~230MB; download on demand only |
| `muse-jobs ["category"]` | The Muse public jobs API | 200 (page_count ~20,507 at build) |
| `remotive ["keyword"]` | Remotive remote-jobs API | 200 |

## Operating rules
1. Prefer an existing dedicated connector when one exists (Plaid, Spotify,
   Ticketmaster, Duffel, GitHub, JustWatch, etc.) — this pack is the fallback
   shelf for routes nothing else covers, per the mining cross-check.
2. GDELT 429s and Stack-Exchange-style shared-IP quota are rate limits: stop,
   back off, report — never loop retries.
3. openFDA event data is spontaneous-report noise until corroborated; label it
   as such in anything user-facing.
4. Job feeds here are a read CLI only. Feeding Stephany's hunt is the
   crawler's job (see the job-hunt goal), governed by its REA/proving-out
   growth rule — this connector does not file or apply to anything.
