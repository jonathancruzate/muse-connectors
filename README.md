# Muse Connectors

Connectors I've built for [Muse](https://ai.meta.com/muse/), Meta's personal AI agent, my own shelf: the full set I run, including the ones that don't fit the community catalog.

Some of my connectors use official public APIs; those that fit the community catalog, [Anil-matcha/awesome-muse-connectors](https://github.com/Anil-matcha/awesome-muse-connectors), are contributed there too. This repo holds the rest of the set, including the connectors whose provider offers no public developer API: those work through the provider's own app or web endpoints, signed in as my own account, the same requests the provider's own app makes. Every connector here is extracted from a setup that runs it in production every day, scrubbed of all personal data and credentials.

## Index

| Connector | What it does | Maturity |
|---|---|---|
| [google-health](./connectors/google-health/SKILL.md) | Read and write sleep, weight, and body fat in Google Health (formerly Fitbit) via the Google Health API and the ghealth CLI, with onward export to Health Connect. | ✅ Live |
| [google-location-sharing](./connectors/google-location-sharing/SKILL.md) | Read Google Maps Location Sharing: the locations people share with your Google account (address, freshness, phone battery), plus your own shared location, via the gls CLI. | ✅ Live |
| [guardian](./connectors/guardian/CONNECTOR.md) | Full-text Guardian article search, section browsing, and article content via the Guardian Open Platform API. | ✅ Live |
| [kasm-form-frontdoor](./connectors/kasm-form-frontdoor/SKILL.md) | A form-login front door for KasmVNC: signed session-cookie gate and HTTP/WebSocket proxy in front of a KasmVNC server, so password managers and browser saved-login flows can sign in. KasmVNC's own authentication stays fully enabled behind the door. | Published |
| [nytimes](./connectors/nytimes/CONNECTOR.md) | New York Times article search (archive back to 1851), top stories by section, most popular lists, and Books bestseller lists via the NYT Developer APIs. | ✅ Live |
| [public-data](./connectors/public-data/CONNECTOR.md) | One CLI for no-auth official/public APIs Muse did not already have: openFDA, ClinicalTrials.gov, GDELT, Google News RSS, Hacker News, Polymarket, and more. No key needed. | ✅ Live |
| [resy](./connectors/resy/SKILL.md) | Search venues, check slots, book and cancel Resy reservations; bookings and cancellations always confirmed first. | ✅ Live |
| [smartthings-find](./connectors/smartthings-find/SKILL.md) | Locate Samsung Galaxy SmartTags (last reported location and battery) through SmartThings Find with a Samsung account OAuth PKCE flow. Passive, read-only; never requests a fresh fix or rings a tag. | ✅ Live |
| [tmdb](./connectors/tmdb/CONNECTOR.md) | Movie and TV search, details, weekly trending, US watch providers, and similar titles via the TMDB API. | ✅ Live |
| [winix](./connectors/winix/SKILL.md) | Winix air purifiers: credential-free state reads (power, mode, fan, AQI, PM2.5, filter life) and confirmation-gated control via the Winix cloud API. | ✅ Live (state); control gated |

## Format

Each connector is one self-contained folder under `connectors/`:

- `SKILL.md` or `CONNECTOR.md`, the connector document in Muse's custom-connector format: Purpose, Tooling, Auth (provider id, allowed hosts, status-check command), Operating Rules, Files, and an honest Maturity label.
- `bin/` — a small CLI the skill drives. No dependencies beyond what the skill itself notes.

Credentials are collected through Muse's secure credential flow (`custom.<provider>`) or, where a provider has no API-key program, through the account flow the skill documents. Nothing secret is stored in this repo, ever. Where a connector can write (book a table, change a device), the write is confirmation-gated in the code, not just in the prose.

## Provenance

Some connectors here use the provider's own app/web endpoints on the user's own account, because no public developer API exists for the job; the rest use official public APIs. The connector docs state the terms considerations plainly rather than dressing the endpoints up as an official API. If you use one: use it on your own account, at a human cadence, and judge the provider's terms for your situation.

## Maintainer

Maintained by Jonathan Cruzate. All packages are scrubbed of personal data and credentials before they land here.

## Install it with Muse

Just give this prompt to your Muse:

> "Install Muse Connectors from https://github.com/jonathancruzate/muse-connectors — read the README, install it, set it up for me, and show me how to use it."
