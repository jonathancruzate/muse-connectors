# TMDB

- `custom.tmdb` connects Muse to The Movie Database (TMDB) REST API v3 at `api.themoviedb.org`. It covers movie and TV metadata, search, trending lists, US watch providers, and similar titles.

- It authenticates with the registered `api_key` credential, which is the account's API Read Access Token (v4) sent as an `Authorization: Bearer` header. The account is jonathancruzateassistant on themoviedb.org, registered 2026-11-11 under the per-service alias tmdb@jonathancruzate.com with an approved Developer application named Muse Personal Assistant (Free Developer plan).

- The helper is `~/workspace/custom-connectors/custom.tmdb/bin/tmdb.py`. It prints compact JSON and was live-verified on 2026-11-11 for search, providers, and trending.

## Connect

- The connection was registered with `credentials.request_api_access` and these details. Reuse them to reconnect:

```json
{
  "provider": "tmdb",
  "auth_scheme": "api_key",
  "placement": "bearer_header",
  "api_hosts": ["api.themoviedb.org"]
}
```

- Before the first change in a conversation, prove access with a harmless read:

```text
python3 ~/workspace/custom-connectors/custom.tmdb/bin/tmdb.py search "Dune" --limit 3
```

## Credentials

- The registered connection holds the credential. Helpers import `/opt/muse/skills/custom-connector-setup/bin/dynamic_credentials.py`, which returns an `hsurr:` surrogate and places it where the provider reads the key. Muse swaps in the real credential only on an approved request to a registered host.

- Never put a key, token, password or cookie in this doc, a helper, a command argument, an environment variable or a log. Never ask the user to paste one in chat.

- Keep redirects disabled on authenticated requests.

- On a 401 or 403, check the request first. Confirm that the helper attached the credential, that the host is registered and that the placement and scopes match.

- Only when a request that carried the credential is still rejected, call `credentials.request_api_access` with the details above and `"reconnect": true`.

## Search movies and TV

- Search across movies and TV in one call. Quote multi-word queries. Results carry id, media_type, title, date, vote_average, and a short overview.

```text
python3 ~/workspace/custom-connectors/custom.tmdb/bin/tmdb.py search "Dune Part Two" --limit 3
```

- `--limit` defaults to 10. Person results are filtered out of the output.

## Read one movie or show

- Fetch full details for one TMDB id, including genres, status, runtime or season counts, and the top billed cast.

```text
python3 ~/workspace/custom-connectors/custom.tmdb/bin/tmdb.py movie 693134
python3 ~/workspace/custom-connectors/custom.tmdb/bin/tmdb.py tv 1396
```

## Trending this week

- List the weekly trending titles for all media, movies only, or TV only.

```text
python3 ~/workspace/custom-connectors/custom.tmdb/bin/tmdb.py trending movie --limit 5
```

## US watch providers

- Show where a title streams, rents, or buys in the US, with the TMDB watch page link. Provider data comes from JustWatch through TMDB, so pair it with the JustWatch skill when the user needs direct watch links or prices.

```text
python3 ~/workspace/custom-connectors/custom.tmdb/bin/tmdb.py providers movie 693134
```

## Similar titles

- List titles similar to a given movie or show.

```text
python3 ~/workspace/custom-connectors/custom.tmdb/bin/tmdb.py similar movie 693134 --limit 5
```

## Recover from errors

- A 401 means the request carried no valid token. Confirm the surrogate was attached and the host matches the registered host before suspecting the credential itself.

- A 404 on a detail call means the id does not exist for that media type. Search first and use the id and media_type the search returned.

- All commands are reads. A failed or timed-out call is safe to retry once.

## Limits

- The connector is read-only. It does not rate titles, edit lists, or change the account.

- Watch provider coverage is US only in the helper. Other regions are untested.

## Related skills

- [JustWatch](~/workspace/custom-skills/local-justwatch/SKILL.md) for direct streaming, rent, and buy links with prices.

- Use `muse.skill_search` to find other skills and `muse.connector_search` to find other connectors.
