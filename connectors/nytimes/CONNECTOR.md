# New York Times

- `custom.nytimes` connects Muse to the New York Times Developer APIs at `api.nytimes.com`. It covers Article Search (the NYT archive back to 1851), Top Stories by section, Most Popular lists, and Books bestseller lists. Responses are article metadata and links — never subscriber full text.

- It authenticates with the registered `api_key` credential, the app key sent as the `api-key` query parameter. The key belongs to the app "Muse Personal Assistant" (App ID bbb63fa6-11c8-4faa-91db-e973454687d8, created 2026-11-11, key Active, no expiry) on the developer account at developer.nytimes.com registered under jonathan.r.cruzate@gmail.com. That developer login is separate from the nytimes.com subscription login (verified 2026-11-11: the developer sign-in is not recognized at myaccount.nytimes.com), and Jonathan directed keeping the Gmail developer account after NYT's change-email flow failed (405) and the portal offered no account deletion. APIs enabled on the app: Article Search, Top Stories, Most Popular, Books, Archive.

- The helper is `~/workspace/custom-connectors/custom.nytimes/bin/nytimes.py`. It prints compact JSON and was live-verified on 2026-11-17 for top stories and books (real current results through the vault-held key).

## Connect

- The connection was registered with `credentials.request_api_access` and these details. Reuse them to reconnect:

```json
{
  "provider": "nytimes",
  "auth_scheme": "api_key",
  "placement": "query_param:api-key",
  "api_hosts": ["api.nytimes.com"]
}
```

- Before the first change in a conversation, prove access with a harmless read:

```text
python3 ~/workspace/custom-connectors/custom.nytimes/bin/nytimes.py topstories home --limit 3
```

## Credentials

- The registered connection holds the credential. Helpers import `/opt/muse/skills/custom-connector-setup/bin/dynamic_credentials.py`, which returns an `hsurr:` surrogate and places it where the provider reads the key. Muse swaps in the real credential only on an approved request to a registered host.

- Never put a key, token, password or cookie in this doc, a helper, a command argument, an environment variable or a log. Never ask the user to paste one in chat.

- Keep redirects disabled on authenticated requests.

- On a 401 or 403, check the request first. Confirm that the helper attached the credential, that the host is registered and that the placement and scopes match. A 401 on one endpoint only usually means that API is not enabled on the app — check the app's APIs tab before suspecting the key.

- Only when a request that carried the credential is still rejected, call `credentials.request_api_access` with the details above and `"reconnect": true`.

## Top stories

- Current top stories for a section (home, world, us, politics, technology, science, health, arts, books, and the other standard NYT section slugs).

```text
python3 ~/workspace/custom-connectors/custom.nytimes/bin/nytimes.py topstories home --limit 5
python3 ~/workspace/custom-connectors/custom.nytimes/bin/nytimes.py topstories technology --limit 5
```

## Search the archive

- Keyword search across the NYT archive with optional date bounds (YYYYMMDD). Quote multi-word queries.

```text
python3 ~/workspace/custom-connectors/custom.nytimes/bin/nytimes.py search "congestion pricing" --limit 5
python3 ~/workspace/custom-connectors/custom.nytimes/bin/nytimes.py search "World Series" --begin 20261001 --end 20261101
```

## Most popular

- Most emailed, shared, or viewed stories over 1, 7, or 30 days.

```text
python3 ~/workspace/custom-connectors/custom.nytimes/bin/nytimes.py popular viewed 7 --limit 5
```

## Books bestsellers

- One bestseller list by list name (default hardcover-fiction). Other common lists: combined-print-and-e-book-fiction, paperback-nonfiction, young-adult-hardcover.

```text
python3 ~/workspace/custom-connectors/custom.nytimes/bin/nytimes.py books
python3 ~/workspace/custom-connectors/custom.nytimes/bin/nytimes.py books paperback-nonfiction
```

## Recover from errors

- A 429 means the free quota is being hit (500/day, 5/minute). Stop, do not retry in a loop, and tell the user which limit was hit.

- A 404 on books usually means the list name is wrong; the names are slug-form as shown above.

- All commands are reads. A failed or timed-out call (other than 429) is safe to retry once.

## Limits

- The connector is read-only. It does not access the user's subscription, account, or full article text.

- Free tier: 500 requests/day, 5 requests/minute. Keep calls sparse; never poll.

- Summarize NYT content and link to it; do not reproduce articles at length.
