# Contributing

Suggestions and pull requests are welcome. One connector per change, in its own folder under `connectors/<provider-id>/`, following the format of the existing entries.

Rules every contribution has to meet:

- **Grounding.** Every capability is documented from the provider's public documentation or observed app behavior, with the source and the date it was checked named in the skill.
- **No secrets, no personal data.** No credentials, tokens, account identifiers, device IDs, or personal locations — in code, docs, examples, or commit history. Credentials belong in Muse's secure credential flow or the documented account flow, never in files.
- **Writes are gated in code.** Anything that changes state outside the repo (a booking, a device command, an upload) must require an explicit confirmation in the CLI itself, not just a note in the prose.
- **Honest Maturity.** Label it "Draft" until it has run against the real provider. Say what was actually tested and when.
- **Files manifest matches.** The skill's Files list must name exactly the files the connector needs — no more, no fewer.
