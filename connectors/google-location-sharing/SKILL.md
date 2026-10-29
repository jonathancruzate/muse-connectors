---
name: "google-location-sharing"
description: "Google Maps Location Sharing via the gls CLI: read the locations people share with your Google account (address, freshness, phone battery), plus your own shared location. No official API exists; uses the reverse-engineered Maps RPC with cookie-session auth. Trigger phrases: location sharing, where is, track phone location, google maps sharing, gls."
metadata: { "includeInPrompt": true }
tagline: "Read Google Maps Location Sharing data from the command line — reverse-engineered RPC connector with cookie-session auth."
catalog_auth: "Google session cookies (Netscape cookies.txt) exported from a browser signed in to the account that receives the shares; stored beside the CLI at mode 600. No API key or OAuth program exists for this data. Signing out of Google anywhere invalidates the export."
catalog_hosts: ["www.google.com"]
---

# Google Location Sharing

## Purpose
Read the location data that other Google accounts share with your account
through Google Maps Location Sharing, plus your own shared location, from the
command line. Google offers no API, API key, or OAuth scope for this data, so
the connector calls the same internal RPC the Google Maps web app calls
(`GET https://www.google.com/maps/rpc/locationsharing/read`). The contract —
endpoint, `pb` parameter, payload index map — was reverse engineered from the
open-source locationsharinglib client (MIT) with REA plus live probes; the
full dossier ships in the public repo as `docs/contract.md`
(github.com/jonathancruzate/google-location-sharing-connector).

## Tooling
All commands go through `gls`, a dependency-light Python 3 CLI (stdlib +
`requests`). Read-only; prints to stdout only; persists nothing about the
people it reads; never prints a cookie value.

Key commands:
- `gls people` — everyone sharing with this account: full name, nickname,
  latitude/longitude, address, accuracy, `age_seconds` freshness, battery
  level and charging state.
- `gls person "<full name>"` / `gls locate "<full name>"` — one person
  (case-insensitive exact match on full name or nickname; exit 5 lists the
  names it did see when nobody matches).
- `gls auth status` — cookie file presence, cookie names, earliest expiry,
  and whether the session is live.
- `gls auth import <cookies.txt> --account <email>` — import an export and
  record which account it belongs to (`authuser` slot supported for
  multi-login profiles; default 0).

## Setup
1. Sign in to Google in a browser as the account that receives the shares
   and export the google.com cookies in Netscape `cookies.txt` format.
   (The author's setup mints the session in a dedicated local Chromium and
   exports its own profile cookies; tooling ships in the public repo under
   `tools/`.)
2. `gls auth import <file> --account <email>`, then prove access with
   `gls auth status` and `gls people` before first use.

## Session validation — the hard-won part
Do not validate with the source client's rule (myaccount.google.com with no
redirect history = live). Verified live 2026-10-29: a valid session still
302s through ServiceLogin and SetOSID before landing back on myaccount, so
redirect history cannot distinguish live from dead. This connector probes
the read RPC itself: live iff the payload returns in authenticated shape
(element [0] is a list; unauthenticated responses have [0] = null). A bare
HTTP 200 proves nothing — unauthenticated probes also return 200.

## Exit codes
2 = no cookies imported · 3 = session no longer live (re-export and import;
do not retry reads against a dead session) · 4 = unparsable endpoint response
(contract may have changed; re-check docs/contract.md) · 5 = person not
found.

## Limits
- Read-only: cannot start, stop, or change a share, and cannot read anyone
  who has not shared with the account.
- Locations are only as fresh as each phone last reported; always read
  `age_seconds` before calling a location current.
- The endpoint is unofficial and can change or stop working without notice.
