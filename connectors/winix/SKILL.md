---
name: "winix"
description: "Winix air purifiers: state reads (power, mode, fan, AQI, PM2.5, PlasmaWave, filter life) and confirmation-gated control via the Winix cloud API. Trigger phrases: winix, air purifier, purifier mode, plasmawave."
metadata: { "includeInPrompt": true }
tagline: "Winix air purifiers: credential-free state reads (power, mode, fan, AQI, PM2.5, filter life) and confirmation-gated control via the Winix cloud API."
catalog_auth: "No stored credential: state reads are credential-free; one-time account login via env vars (never persisted) for discovery and the control capability token"
catalog_hosts: ["cognito-idp.us-east-1.amazonaws.com", "cognito-identity.us-east-1.amazonaws.com", "us.mobile.winix-iot.com", "us.api.winix-iot.com"]
---

# Winix

## Purpose
Read and control Winix air purifiers through the Winix cloud API: state (power, operating mode, fan speed, air quality / AQI, PM2.5, PlasmaWave, filter hours used and percent remaining), and control (power, mode, fan, PlasmaWave, child lock). Use when the user asks about their Winix purifier or wants to change how it runs. This is the direct cloud path — the authoritative state source when an indirect link (e.g. a smart-home platform integration) is stale or dropped.

Source: the Winix cloud API as documented by the open-source project [iprak/winix](https://github.com/iprak/winix) (MIT), checked 2026-10-19. Winix offers no public developer API; this is the same cloud API the official Winix app uses, exercised with the user's own account.

## Tooling
All commands go through `bin/winix.py` (needs `pycryptodome`; the one-time login also needs `warrant_lite` and `python-jose`):

```bash
bin/winix.py auth                          # status check: known devices + state endpoint answers
bin/winix.py discover                      # one-time: WINIX_EMAIL/WINIX_PASSWORD env, saves deviceIds
bin/winix.py devices                       # list known purifiers
bin/winix.py state [name]                  # full interpreted state for one purifier
bin/winix.py watch                         # one-line state per purifier (for watchers)

# Writes — require --confirm and the transient control token:
WINIX_IDENTITY_ID=<from discover> bin/winix.py control "Kitchen" fan turbo --confirm "set the kitchen purifier fan to turbo"
bin/winix.py control <name> <power|mode|fan|plasmawave|childlock> <value> --confirm "<exact effect>"
```

Fan values: low, medium, high, turbo, sleep, super. Modes: auto, manual. State interpretation includes filter life (a filter is rated 6,480 hours) and air quality (good/fair/poor/very poor) from the raw attribute codes.

## Auth
- Provider id: `winix` — this provider has no API-key program, so there is no `custom.winix` credential in the secure store; the auth model is the user's own Winix account, used as follows.
- **State reads are credential-free.** The state endpoint is device-scoped: knowing a purifier's deviceId is the capability. DeviceIds are discovered once (below) and stored in `~/.config/muse-connectors/winix/devices.json` (mode 600).
- **Discovery / control token:** a one-time Cognito SRP login (`USER_SRP_AUTH`) against the Winix app's public client, with the account email/password supplied via the `WINIX_EMAIL` / `WINIX_PASSWORD` environment variables for that single run. The password is used once and never stored. Discovery prints the session's Cognito `identity_id` — the capability token control URLs require. It is deliberately **not persisted**: pass it transiently as `WINIX_IDENTITY_ID` for `control` calls.
- The Cognito pool/client ids and the mobile transport's AES key/IV in `bin/winix.py` are the Winix app's own public constants, as documented by the MIT-licensed source project — they are not user credentials.
- Allowed hosts: `cognito-idp.us-east-1.amazonaws.com`, `cognito-identity.us-east-1.amazonaws.com`, `us.mobile.winix-iot.com`, `us.api.winix-iot.com`
- Status check: `bin/winix.py auth`
- Practical note: Winix kills other sessions on login (multi-login limit). For persistent use, create a second Winix account, share the purifiers to it from the app (Device Settings > Device Sharing), and use that account for automation so the user's phone session is never kicked.

## Operating Rules
1. **Control is a write and is confirmation-gated in code**: `control` refuses to run without `--confirm "<exact effect>"`. Get the user's confirmation in conversation first; never pre-fill it.
2. Never store the Winix password anywhere, and never persist the `identity_id` — it is a session capability token, passed transiently per control call.
3. State reads are cheap but poll considerately: no tighter than every 5 minutes for watcher-style consumers.
4. State comes with the Winix cloud timestamp (`winix_timestamp`); if it is stale or the read fails, the purifier itself is unreachable (Wi-Fi/power) — say so rather than presenting old state as current. If direct state is fresh but another platform shows the purifier offline, that platform's link dropped, not the purifier.
5. Never print deviceIds or tokens beyond what the immediate task needs.

## Files
- SKILL.md
- bin/winix.py

## Maturity
✅ Live (state) — this is the production version from a running Muse setup: state reads and watch output run daily against real purifiers and drive link-drop detection and air-quality decisions; live-tested 2026-10-19. The control path is implemented with the confirmation gate above and the transient-token rule; treat first control use on a new account as supervised.
