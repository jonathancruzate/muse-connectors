---
name: "google-health"
description: "Google Health API via the ghealth CLI: read and write sleep, weight, and body fat in a Google Health account (the app formerly known as Fitbit), with onward export to Health Connect. The write path that survives the legacy Fitbit Web API shutdown (Nov 2, 2026). Trigger phrases: google health, health connect write, fitbit api, log sleep, log weight, ghealth."
metadata: { "includeInPrompt": true }
tagline: "Write sleep, weight, and body fat to Google Health / Health Connect via the Google Health API and the open-source ghealth CLI."
catalog_auth: "OAuth 2.0 Desktop client in your own Google Cloud project (Google Health API enabled); client secret and tokens stored at ~/.config/ghealth (mode 0600); consent screen published to production so refresh tokens do not expire after 7 days"
catalog_hosts: ["health.googleapis.com", "accounts.google.com", "oauth2.googleapis.com"]
---

# Google Health

## Purpose
Read and write health data in a Google Health account through the Google Health API v4:
sleep sessions (read + write), weight and body fat (read + write), plus identity and
profile reads. The phone app (Fitbit, rebranded in place to Google Health in May 2026)
exports API-created entries onward to Health Connect tagged as manually entered — static
analysis of the app shows no source filter in its fetch→convert path — so this is a
working third-party **write** path into Health Connect, which has no general write API
of its own.

The legacy alternative is dead: Fitbit Web API support ended Sep 30, 2026, new developer
app registration is disabled, and the legacy API + OAuth endpoints shut off Nov 2, 2026.

## Tooling
All commands go through `ghealth`, the open-source agent-oriented CLI for the Google
Health API (github.com/Google-Health-API/google-health-cli, Apache 2.0), built from
source and driven non-interactively. Simplified JSON output; `--dry-run` previews any
request; `--raw` returns the untouched API response.

Key commands:
- `ghealth user identity` — verify the account is linked; returns the health user ID.
- `ghealth data sleep list [--detail] [--from DATE] [--limit N]` — sleep sessions.
- `ghealth data sleep create --json '<body>'` — write a session (async Operation;
  `"done": true` + the new data point name confirms).
- `ghealth data sleep delete --ids <id[,id...]>` — remove sessions.
- `ghealth data weight ...` / `ghealth data body-fat ...` — same pattern.

## Setup
1. Google Cloud project with the **Google Health API** (`health.googleapis.com`) enabled.
2. OAuth consent screen (External): select the least-privilege scopes —
   `googlehealth.sleep.readonly`, `googlehealth.sleep.writeonly`,
   `googlehealth.health_metrics_and_measurements.readonly`,
   `googlehealth.health_metrics_and_measurements.writeonly`,
   `googlehealth.profile.readonly`.
3. OAuth client of type **Desktop app**; save the client-secret JSON to
   `~/.config/ghealth/client_secret.json` (`0600`).
4. Sign in to the Google Health phone app and link the Google Account **before**
   consenting, or calls fail with `400 ACCOUNT_NOT_LINKED`.
5. Authorize headlessly (PKCE): `ghealth setup --project-id <id> --client-secret
   ~/.config/ghealth/client_secret.json --scopes <list> --skip-enable-api --no-prompt
   --non-interactive-auth`, then `ghealth auth login --non-interactive --scopes <list>`,
   open the printed `auth_url` anywhere, copy the `code` parameter from the localhost
   redirect (it fails to load — expected), and finish with
   `ghealth auth login --complete <code>`.

## The Testing-mode trap
A consent screen left in **Testing** publishing status gets refresh tokens that expire
after **7 days**. Publish to production: Branding requires app name, support email, a
home page URL, and a privacy policy URL on an authorized domain before Publish enables.
The app stays unverified (the health scopes are Restricted) — the console banner is
advisory for single-user personal use. Re-run consent once after publishing so the
stored refresh token is production-issued.

## Payload notes
- Sleep create bodies wrap fields in a top-level `sleep` object; a bare
  `{"interval": ...}` is rejected (`Unknown name "interval" at 'data_point'`).
- `startUtcOffset` / `endUtcOffset` are protobuf Durations: `"-14400s"`, never `"-04:00"`.
- Civil times are structured `CivilDateTime` objects — omit them; UTC instants + offsets
  suffice.

```json
{"sleep":{"interval":{"startTime":"2026-01-01T05:45:00Z","endTime":"2026-01-01T15:00:00Z","startUtcOffset":"-14400s","endUtcOffset":"-14400s"},"metadata":{"mainSleep":true,"manuallyEdited":true,"externalId":"example-1"}}}
```

## Provenance for estimated data
Estimated entries are written only when no observed session exists for the night,
always tagged (`metadata.externalId = "muse-estimate-<date>"`, `manuallyEdited: true`),
and deleted + reconciled the moment observed data lands. An estimate and an observed
session never coexist for the same night.

## Boundaries
- Credentials and tokens never leave `~/.config/ghealth/`; never commit project IDs,
  client IDs, or user IDs.
- First API calls can be slow (tens of seconds); a cold-start timeout earns one retry
  before anything is declared down.
- This lane complements, and does not replace, any existing Health Connect read/sync
  pipeline.
