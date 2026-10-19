---
name: "smartthings-find"
description: "Locate Samsung Galaxy SmartTags — last reported location and battery — through SmartThings Find. Read-only. Trigger phrases: smarttag, find my tag, tracker location, where is the tag."
metadata: { "includeInPrompt": true }
tagline: "Locate Samsung Galaxy SmartTags (last reported location and battery) through SmartThings Find with a Samsung account OAuth PKCE flow. Passive, read-only — never requests a fresh fix or rings a tag."
catalog_auth: "Samsung account OAuth 2.0 PKCE (user's own sign-in, one-time setup; tokens stored locally, auto-refreshed)"
catalog_hosts: ["account.samsung.com", "auth.api.smartthings.com", "api.smartthings.com"]
---

# SmartThings Find

## Purpose
Read Galaxy SmartTag locations and battery levels through SmartThings Find: list the trackers on a Samsung account, and get a tag's last reported latitude/longitude, accuracy, timestamp, and battery label. Use when the user asks where a SmartTag is, or whether something carrying one is home or left behind. The regular SmartThings API returns nulls for SmartTags (their GPS is end-to-end encrypted), so this Find flow is the only API route to tag locations.

Source: the flow is documented by the open-source project [rreverser/ha-smartthings-find](https://github.com/rreverser/ha-smartthings-find) (MIT), checked 2026-10-19; it is the same OAuth + installed-app flow the SmartThings Find service itself uses. In production use since 2026-10-06.

## Tooling
All commands go through `bin/smartthings_find.py` (needs the Python packages `requests` and `cryptography`):

```bash
bin/smartthings_find.py auth-url                     # one-time setup: print the Samsung login URL
bin/smartthings_find.py auth-complete <redir_url>    # exchange the ms-app:// redirect URL for tokens
bin/smartthings_find.py auth                         # status check: tokens work, list tracker names
bin/smartthings_find.py trackers                     # list SmartTags (name + device id)
bin/smartthings_find.py locate [--name <substr>]     # last reported location JSON for a tag
bin/smartthings_find.py battery [--name <substr>]    # battery label only (Full/Medium/Low/Very low)
```

With one tag on the account, `--name` is optional; with several, it selects by name substring. `locate` prints `{name, location_found, lat, lng, accuracy_m, updated_utc, battery}`.

## Auth
- Provider id: `smartthings-find` (this connector does **not** use the Muse credential store: Samsung account sign-in can't ride the API-key surrogate pattern, so tokens live in a local store at `~/.config/muse-connectors/smartthings-find/auth.json`, mode 600, auto-refreshed).
- Flow: OAuth2 PKCE against Samsung account servers → separate Find and SmartThings IoT tokens → calls go through the SmartThings installed-app execute proxy (`/installedapps/{id}/execute`) for the Find plugin, which is how the Find backend serves the app.
- Setup (one time, needs the user's own Samsung sign-in): run `auth-url`, have the user open the URL and sign in with **their own** Samsung account, then pass the resulting `ms-app://` redirect URL to `auth-complete` promptly (the code expires in about 300 seconds). Desktop-browser tip: if the `ms-app://` redirect won't resolve, the full redirect URL sits in the sign-in-complete page's HTML `onload` handler — copy it and unescape `&amp;` to `&`.
- Required scopes: `offline.access` (Find token), `iot.client` (IoT token) — requested during the flow.
- Allowed hosts: `account.samsung.com` (sign-in entry point; the flow then redirects to the account's regional Samsung auth server, whose host is returned by Samsung itself), `auth.api.smartthings.com`, `api.smartthings.com`.
- Status check: `bin/smartthings_find.py auth`
- If auth breaks (Samsung revokes the tokens), re-run the one-time setup. Do not burn repeated sign-in attempts against the user's account — a failed automated fill should hand the sign-in to the user rather than risk a lockout.

## Operating Rules
1. **Passive reads only.** The CLI returns the tag's last reported location; it never requests a fresh fix and never rings, shares, or changes Find settings. Fresh fixes cost tag battery, and what the user sees in SmartThings Find is exactly this last-reported value.
2. Read-only: there are no writes of any kind, so no confirmation flow applies.
3. Location output includes an `updated_utc` timestamp — always report it with the location. A tag that hasn't reported recently (dead battery, out of range of the Galaxy Find network) shows a stale timestamp or `location_found: false`; say so plainly instead of presenting an old fix as current.
4. Treat coordinates as the user's private data: never log, transmit, or include them anywhere except the answer to the user's own question.
5. Poll considerately: tag locations change slowly; watcher-style consumers should poll no tighter than every 15–30 minutes, and only when the answer can change an outcome.
6. Never print or persist the token values; the auth store stays local and mode-600.

## Files
- SKILL.md
- bin/smartthings_find.py

## Maturity
✅ Live — this is the production version from a running Muse setup: it locates a collar-worn SmartTag and a fleet of item trackers daily (departure-essentials checks, pet-location reads), against real Samsung accounts, since 2026-10-06. Live-tested 2026-10-19.
