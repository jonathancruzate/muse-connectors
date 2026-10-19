---
name: "resy"
description: "Find, book, list, and cancel Resy restaurant reservations on your own account. Trigger phrases: resy, reservation, book a table, restaurant booking, cancel my reservation."
metadata: { "includeInPrompt": true }
tagline: "Search venues, check slots, book and cancel Resy reservations — bookings and cancellations always confirmed first."
catalog_auth: "Your own Resy account session token (minted via your resy.com sign-in) plus Resy's public web-app API key"
catalog_hosts: ["api.resy.com"]
---

# Resy

## Purpose
Search Resy venues, check bookable slots, read booking terms, and book, list, or cancel reservations on the signed-in user's own Resy account.

**Transparency about the endpoints — read this first.** Resy does not offer a public developer API for diners. This connector calls the `api.resy.com` endpoints that Resy's own web app (resy.com) calls — the same requests your browser makes when you book signed in. Nothing here is an official or documented Resy API, and Resy's terms of service restrict automation. Decide for yourself whether this fits your situation; if you use it, use it only for your own account, at a human cadence, for ordinary reservation management. The endpoint shapes were confirmed against resy.com's own app behavior and web bundle, cross-checked with the open-source resy-mcp and resy-booking-bot projects (checked 2026-10-19).

Source: resy.com web app behavior and app bundle (endpoints under `https://api.resy.com`), checked 2026-10-19.

## Tooling
All commands go through `bin/resy.py` (Python 3, requires `requests`):

```bash
bin/resy.py auth status                                       # token cached? age/expiry, value never shown
bin/resy.py search --query "Venue Name"                       # resolve a venue name to a venue_id (token optional)
bin/resy.py find --venue-id 12345 --day 2026-11-14 --party-size 2
bin/resy.py details --config-id <config token from find> --day 2026-11-14 --party-size 2
bin/resy.py book --config-id <config token> --day 2026-11-14 --party-size 2            # preview only
bin/resy.py book --config-id <config token> --day 2026-11-14 --party-size 2 --confirm  # books, after explicit confirmation
bin/resy.py list                                              # upcoming reservations (prints the resy_token cancel needs)
bin/resy.py cancel --id <resy_token or reservation_id>        # preview only
bin/resy.py cancel --id <resy_token or reservation_id> --confirm
```

Add `--json` to `search`, `find`, `details`, or `list` for machine-readable output. `list --scope` accepts `upcoming` (default), `past`, or `all`.

Auth commands: `auth import-token` (cache a token minted in a signed-in resy.com session; the token is supplied only via the `RESY_AUTH_TOKEN` environment variable), `auth otp` (email one-time-code login via `RESY_EMAIL`, then `RESY_OTP_CODE`, both environment-only), `auth login` (password login via `RESY_EMAIL` / `RESY_PASSWORD`, environment-only; many accounts are one-time-code-only and have no password), `auth status`.

Exit codes: 0 success, 1 error, 2 preview waiting on `--confirm`, 3 a write whose outcome is unknown.

## Auth
- Provider id: `resy` (credential is collected as `custom.resy`)
- This connector is not registered through the hosted credential flow, because Resy has no API key or OAuth program for diners. The CLI keeps its own local state files beside itself instead:
  - **Web-app API key** — sent on every request as `Authorization: ResyAPI api_key="<key>"`. This is the same key baked into resy.com's own JavaScript and sent on unauthenticated requests from the site; it is a public client key, not a personal secret. Supply it via the `RESY_API_KEY` environment variable or an `api_key.txt` file (mode 600) beside the CLI. If calls start failing with HTTP 419, Resy has rotated it: extract the current key from resy.com's JavaScript and replace it.
  - **Account session token** — an ES256 JWT with a lifetime of roughly 45 days, carried in the `x-resy-auth-token` and `x-resy-universal-auth` headers. Mint it by signing in to resy.com as yourself, then import it with `RESY_AUTH_TOKEN=<token> bin/resy.py auth import-token`. The import validates the token against `GET /2/user` and caches it in `token.json` at mode 600. The token is never printed, logged, or accepted as a command-line argument.
- Required scopes: none (no OAuth)
- Allowed hosts: `api.resy.com` only. Redirects are disabled on every request, so a token is never leaked to a different host.
- Status check: `bin/resy.py auth status`

## Operating Rules
1. **Booking and cancelling are consequential writes.** Never run `book --confirm` or `cancel --confirm` without the user's explicit confirmation, obtained immediately before the call, covering the venue, date, time, and party size. Without `--confirm` both commands only print a preview and change nothing.
2. Always run `details` first and read the cancellation fee to the user before confirming a booking — cancellation fees are real and venue-specific.
3. Writes are sent exactly once and are never replayed automatically, because Resy may have completed a write before a failure surfaced. A failed write exits 3 with the outcome unknown: run `list` and check the real state before any retry. Never re-send a book or cancel blindly.
4. `book` refuses when an upcoming reservation already exists at the same venue on the same day; pass `--allow-duplicate` only when a second table is genuinely wanted.
5. Never print, log, or pass the account token as a command argument. Passwords and one-time codes are read only from environment variables and are never stored.
6. Human cadence only: no polling, no slot sniping. Reads back off once on HTTP 429 and then stop. Aggressive use risks the account being flagged or suspended.
7. Use only on the account holder's own account and their own reservations.
8. Slot times come back as restaurant-local strings (`2026-11-14 18:30:00`) with no timezone offset. Read the HH:MM straight off the string; never run them through a timezone-aware parser.

## Files
- SKILL.md
- bin/resy.py

## Maturity
✅ Live — tested against the real api.resy.com on 2026-10-19; in production use for real bookings on the contributor's own account.
