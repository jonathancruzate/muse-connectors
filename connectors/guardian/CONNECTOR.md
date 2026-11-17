# The Guardian

- `custom.guardian` connects Muse to the Guardian Open Platform Content API at `content.guardianapis.com`. It covers full Guardian article search, section browsing, and single-article reads with byline and trail text.

- It authenticates with the registered `api_key` credential, the free Developer key sent as the `api-key` query parameter. The key was issued 2026-11-11 to the registration under the per-service alias guardian@jonathancruzate.com (free Developer tier, non-commercial use). The key email ("New Key Created") was forwarded unread to the user's Gmail for the vault paste; Muse never read the key value.

- The helper is `~/workspace/custom-connectors/custom.guardian/bin/guardian.py`. It prints compact JSON and was live-verified on 2026-11-17 for search and sections (real current Guardian results through the vault-held key).

## Connect

- The connection was registered with `credentials.request_api_access` and these details. Reuse them to reconnect:

```json
{
  "provider": "guardian",
  "auth_scheme": "api_key",
  "placement": "query_param:api-key",
  "api_hosts": ["content.guardianapis.com"]
}
```

- Before the first change in a conversation, prove access with a harmless read:

```text
python3 ~/workspace/custom-connectors/custom.guardian/bin/guardian.py search "New York" --limit 3
```

## Credentials

- The registered connection holds the credential. Helpers import `/opt/muse/skills/custom-connector-setup/bin/dynamic_credentials.py`, which returns an `hsurr:` surrogate and places it where the provider reads the key. Muse swaps in the real credential only on an approved request to a registered host.

- Never put a key, token, password or cookie in this doc, a helper, a command argument, an environment variable or a log. Never ask the user to paste one in chat.

- Keep redirects disabled on authenticated requests.

- On a 401 or 403, check the request first. Confirm that the helper attached the credential, that the host is registered and that the placement and scopes match. The Developer key can return 403 with a key that is only provisioned for the test tier — if a verified call 403s, suspect tier provisioning before the key value.

- Only when a request that carried the credential is still rejected, call `credentials.request_api_access` with the details above and `"reconnect": true`.

## Search articles

- Search the full Guardian archive and live content. Quote multi-word queries. Results carry id, headline, section, publication time, URL, byline, and trail text.

```text
python3 ~/workspace/custom-connectors/custom.guardian/bin/guardian.py search "climate summit" --limit 5
python3 ~/workspace/custom-connectors/custom.guardian/bin/guardian.py search "transit" --section us-news --limit 5
```

- `--limit` defaults to 10, capped at 50 per call.

## List sections

```text
python3 ~/workspace/custom-connectors/custom.guardian/bin/guardian.py sections
```

## Read one article

- Fetch one item by its content id (the path form, e.g. `world/2026/nov/11/some-slug`). Returns metadata plus a body excerpt (first ~1500 chars of the body text field). Summarize and link rather than reproducing the article.

```text
python3 ~/workspace/custom-connectors/custom.guardian/bin/guardian.py item world/2026/nov/11/example-slug
```

## Recover from errors

- A 401/403 means the request carried no accepted key. Confirm the surrogate was attached and the host matches the registered host before suspecting the credential itself.

- A 404 on an item call means the content id does not exist. Search first and use the id the search returned.

- All commands are reads. A failed or timed-out call is safe to retry once.

## Limits

- The connector is read-only.

- The free Developer tier is rate-limited and licensed for non-commercial use only. Keep calls sparse and cache results in the caller's notes rather than re-querying.

- Summarize Guardian content and link to it; do not reproduce articles at length.
