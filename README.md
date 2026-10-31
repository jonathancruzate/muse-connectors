# Muse Connectors

Connectors I've built for [Muse](https://ai.meta.com/muse/), Meta's personal AI agent — the shelf for the ones that don't fit the community catalog.

Most of my connectors use official public APIs, and those live upstream in the community catalog, [Anil-matcha/awesome-muse-connectors](https://github.com/Anil-matcha/awesome-muse-connectors), where I contribute them. The three connectors here are different: the provider offers no public developer API, so each one works through the provider's own app or web endpoints, signed in as my own account — the same requests the provider's own app makes. That provenance is exactly why they live here instead of the catalog. Each one is extracted from a setup that runs them in production every day, scrubbed of all personal data and credentials.

## Index

| Connector | What it does | Maturity |
|---|---|---|
| [resy](./connectors/resy/SKILL.md) | Search venues, check slots, book and cancel Resy reservations — bookings and cancellations always confirmed first. | ✅ Live |
| [winix](./connectors/winix/SKILL.md) | Winix air purifiers: credential-free state reads (power, mode, fan, AQI, PM2.5, filter life) and confirmation-gated control via the Winix cloud API. | ✅ Live (state); control gated |
| [smartthings-find](./connectors/smartthings-find/SKILL.md) | Locate Samsung Galaxy SmartTags (last reported location and battery) through SmartThings Find with a Samsung account OAuth PKCE flow. Passive, read-only — never requests a fresh fix or rings a tag. | ✅ Live |

## Format

Each connector is one self-contained folder under `connectors/`:

- `SKILL.md` — the connector document in Muse's custom-connector format: Purpose, Tooling, Auth (provider id, allowed hosts, status-check command), Operating Rules, Files, and an honest Maturity label.
- `bin/` — a small CLI the skill drives. No dependencies beyond what the skill itself notes.

Credentials are collected through Muse's secure credential flow (`custom.<provider>`) or, where a provider has no API-key program, through the account flow the skill documents. Nothing secret is stored in this repo, ever. Where a connector can write — book a table, change a device — the write is confirmation-gated in the code, not just in the prose.

## Provenance

Each of these three uses the provider's own app/web endpoints on the user's own account, because no public developer API exists for the job. The SKILL.md files state the terms considerations plainly rather than dressing the endpoints up as an official API. If you use one: use it on your own account, at a human cadence, and judge the provider's terms for your situation.

## Maintainer

Maintained by Jonathan Cruzate. All packages are scrubbed of personal data and credentials before they land here.

## Install it with Muse

Just give this prompt to your Muse:

> "Install Muse Connectors from https://github.com/jonathancruzate/muse-connectors — read the README, install it, set it up for me, and show me how to use it."

