#!/usr/bin/env python3
"""Resy API client (unofficial api.resy.com endpoints used by the resy.com web app).

Commands:
  auth otp             Email one-time-code login. With only RESY_EMAIL set,
                       requests a code (POST /3/auth/email/request,
                       {em_address}); with RESY_OTP_CODE also set, verifies it
                       (POST /4/auth/email/verify, {code, em_address}) and
                       caches the returned token like login does.
  auth import-token    Cache a token from RESY_AUTH_TOKEN (minted in a signed-in
                       resy.com browser session) and validate it.
  auth login           Log in with RESY_EMAIL / RESY_PASSWORD env vars, cache the token.
                       Secondary path. Many Resy accounts sign in by email
                       one-time code and have no password, so prefer import-token.
  auth status          Show whether a token is cached, without printing it.
  search               POST /3/venuesearch/search  (resolve a venue name to a venue_id)
  find                 GET  /4/find                (slots for a venue, day, party size)
  details              GET  /3/details             (book_token + terms for one slot)
  book                 POST /3/book                (details -> book; requires --confirm)
  list                 GET  /3/user/reservations   (upcoming reservations by default)
  cancel               POST /3/cancel              (requires --confirm)

Safety rules baked in:
  - The auth token is read from token.json (mode 600) beside this file and is
    never printed, logged, or accepted on the command line.
  - The password is read only from the RESY_PASSWORD environment variable and
    is never stored.
  - Reads re-authenticate once on 401/419 and replay once. Writes (book,
    cancel) are NEVER replayed automatically: a failed write is reported as
    outcome-unknown and the caller is told to check `list` before retrying.
  - Redirects are disabled on every request.
"""

import argparse
import base64
import json
import os
import sys
import time
from datetime import date

import requests

BASE_URL = "https://api.resy.com"
CONNECTOR_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_KEY_FILE = os.path.join(CONNECTOR_DIR, "api_key.txt")
TOKEN_FILE = os.path.join(CONNECTOR_DIR, "token.json")

DEFAULT_LAT = "40.7128"
DEFAULT_LONG = "-73.9876"
TIMEOUT_SECS = 30

BROWSER_HEADERS = {
    "Origin": "https://resy.com",
    "Referer": "https://resy.com/",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}

AUTH_FAILURE_STATUSES = (401, 419)


class ResyError(Exception):
    """User-facing error. str() is safe to print: it never contains the token."""


class OutcomeUnknown(ResyError):
    """A write may or may not have landed. Caller must check state first."""


# --------------------------------------------------------------------------
# Credential handling
# --------------------------------------------------------------------------

def load_api_key():
    """Resolve Resy's public web-app API key.

    Precedence: RESY_API_KEY env var, then api_key.txt beside this connector.
    The key is baked into resy.com's own JavaScript and is not a secret, but it
    is kept out of source control churn by living in the cache file so a Resy
    key rotation only needs that one file replaced.
    """
    env_key = os.environ.get("RESY_API_KEY", "").strip()
    if env_key:
        return env_key
    try:
        with open(API_KEY_FILE, "r", encoding="utf-8") as fh:
            key = fh.read().strip()
    except OSError:
        key = ""
    if key:
        return key
    raise ResyError(
        "No Resy API key found. Set RESY_API_KEY or place Resy's public "
        "web-app key (extractable from resy.com's own JS) in " + API_KEY_FILE
    )


def _write_token_cache(data):
    fd = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    os.chmod(TOKEN_FILE, 0o600)


def _read_token_cache():
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    if isinstance(data, dict) and data.get("token"):
        return data
    return None


def _cache_token(token, payload=None):
    """Write the token cache (mode 600) and return it. Never prints the token."""
    cache = {"token": token, "obtained_at": int(time.time())}
    payload = payload or {}
    if payload.get("payment_method_id"):
        cache["payment_method_id"] = payload["payment_method_id"]
    user = payload.get("user") or {}
    if user.get("first_name"):
        cache["account_first_name"] = user["first_name"]
    _write_token_cache(cache)
    return cache


def login(email, password):
    """POST /3/auth/password and cache the returned token. Returns cache dict."""
    api_key = load_api_key()
    try:
        resp = requests.post(
            BASE_URL + "/3/auth/password",
            headers=_headers(api_key, token=None),
            data={"email": email, "password": password},
            timeout=TIMEOUT_SECS,
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise ResyError("Login request failed before a response: %s" % exc.__class__.__name__)
    if resp.status_code in (301, 302, 303, 307, 308):
        raise ResyError("Login was redirected (HTTP %d). Refusing to follow." % resp.status_code)
    if resp.status_code == 429:
        raise ResyError("Resy rate limited the login (HTTP 429). Wait and try again later.")
    if not resp.ok:
        raise ResyError(
            "Login failed (HTTP %d). Check the email and password." % resp.status_code
        )
    payload = _json_or_error(resp, "login")
    token = (
        payload.get("token")
        or (payload.get("id") or {}).get("token")
        or payload.get("auth_token")
    )
    if not token:
        raise ResyError("Login response carried no token. Response shape not recognized.")
    return _cache_token(token, payload)


def _auth_post(path, form):
    """POST a form to an auth endpoint (no token yet). Shared by otp."""
    api_key = load_api_key()
    try:
        resp = requests.post(
            BASE_URL + path,
            headers=_headers(api_key, token=None),
            data=form,
            timeout=TIMEOUT_SECS,
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise ResyError("Auth request failed before a response: %s" % exc.__class__.__name__)
    if resp.status_code in (301, 302, 303, 307, 308):
        raise ResyError("Auth request was redirected (HTTP %d). Refusing to follow." % resp.status_code)
    if resp.status_code == 429:
        raise ResyError("Resy rate limited the auth request (HTTP 429). Stop and wait; do not retry this run.")
    if not resp.ok:
        raise ResyError("Auth request failed (HTTP %d): %s" % (resp.status_code, _short_body(resp)))
    return _json_or_error(resp, path)


def otp_request(email):
    """POST /3/auth/email/request {em_address} — mined 2026-10-19 from
    resy.com's app bundle (modules/app.81996c7cef7626d15568.js):
    ge=e=>post("3/auth/email/request", parameterize(e)), called from
    handleEmailCapture as requestEmailCodeThunk({em_address: email}).
    Response carries email_mask."""
    return _auth_post("/3/auth/email/request", {"em_address": email})


def otp_verify(email, code):
    """POST /4/auth/email/verify {code, em_address} — same bundle:
    ye=e=>post("4/auth/email/verify", parameterize(e)), called from
    handleEmailCodeSubmit as {code, em_address} for the email flow.
    Response carries the account token like the password login does."""
    payload = _auth_post("/4/auth/email/verify", {"code": code, "em_address": email})
    token = (
        payload.get("token")
        or (payload.get("id") or {}).get("token")
        or payload.get("auth_token")
    )
    if not token:
        raise ResyError(
            "OTP verify response carried no token. Response keys: %s. "
            "A challenge or email_claim step may be required; nothing was cached."
            % ", ".join(sorted(payload.keys()))
        )
    return _cache_token(token, payload)


def import_token(token):
    """Cache a token minted elsewhere (the account signs in by email one-time
    code in the browser, so tokens are minted in that signed-in session and
    imported here). Validates the token with GET /2/user, which also yields
    the default payment method id. Returns the cache dict."""
    api_key = load_api_key()
    profile = None
    try:
        resp = requests.get(
            BASE_URL + "/2/user",
            headers=_headers(api_key, token),
            timeout=TIMEOUT_SECS,
            allow_redirects=False,
        )
    except requests.RequestException:
        resp = None
    if resp is not None and resp.status_code in AUTH_FAILURE_STATUSES:
        raise ResyError(
            "Resy rejected the supplied token (HTTP %d). It is expired or "
            "invalid, so nothing was cached. Mint a fresh one from a "
            "signed-in resy.com session." % resp.status_code
        )
    if resp is not None and resp.ok:
        try:
            profile = resp.json()
        except ValueError:
            profile = None
    payload = {}
    if profile:
        methods = profile.get("payment_methods") or []
        for method in methods:
            if method.get("is_default"):
                payload["payment_method_id"] = method.get("id")
                break
        if "payment_method_id" not in payload and methods:
            payload["payment_method_id"] = methods[0].get("id")
        if profile.get("first_name"):
            payload["user"] = {"first_name": profile["first_name"]}
    cache = _cache_token(token, payload)
    cache["_validated"] = profile is not None
    return cache


def ensure_token(allow_login=True):
    """Return (token, cache).

    Precedence: the token cache, then a token supplied in RESY_AUTH_TOKEN
    (imported without a validation call to keep the hot path light), then a
    password login from RESY_EMAIL and RESY_PASSWORD when both are set.
    """
    cache = _read_token_cache()
    if cache:
        return cache["token"], cache
    env_token = os.environ.get("RESY_AUTH_TOKEN", "").strip()
    if env_token:
        cache = _cache_token(env_token)
        return cache["token"], cache
    email = os.environ.get("RESY_EMAIL", "").strip()
    password = os.environ.get("RESY_PASSWORD", "")
    if allow_login and email and password:
        cache = login(email, password)
        return cache["token"], cache
    raise ResyError(
        "No cached Resy token. Mint one from a signed-in resy.com session "
        "and run `resy auth import-token` with RESY_AUTH_TOKEN set, or run "
        "`resy auth login` if the account has a password."
    )


def reauth():
    """Re-mint from whatever the environment offers and return the fresh
    cache, or None after dropping the dead token."""
    env_token = os.environ.get("RESY_AUTH_TOKEN", "").strip()
    cached = _read_token_cache()
    if env_token and (cached is None or cached.get("token") != env_token):
        return _cache_token(env_token)
    email = os.environ.get("RESY_EMAIL", "").strip()
    password = os.environ.get("RESY_PASSWORD", "")
    if email and password:
        return login(email, password)
    # Nothing to re-mint with: drop the dead token so the next run fails at
    # ensure_token with clear instructions instead of looping.
    try:
        os.remove(TOKEN_FILE)
    except OSError:
        pass
    return None


# --------------------------------------------------------------------------
# HTTP plumbing
# --------------------------------------------------------------------------

def _headers(api_key, token):
    headers = dict(BROWSER_HEADERS)
    headers["Authorization"] = 'ResyAPI api_key="%s"' % api_key
    if token:
        headers["x-resy-auth-token"] = token
        headers["x-resy-universal-auth"] = token
    return headers


def _json_or_error(resp, what):
    try:
        return resp.json()
    except ValueError:
        raise ResyError("Resy returned a non-JSON response for %s (HTTP %d)." % (what, resp.status_code))


def _looks_like_auth_failure(status, body_text):
    if status in AUTH_FAILURE_STATUSES:
        return True
    if status == 500 and body_text:
        lowered = body_text.lower()
        return "unauthorized" in lowered or "auth" in lowered and "token" in lowered
    return False


def request_read(method, path, params=None, data=None, json_body=None, auth=True):
    """Read-style request with one re-auth replay on 401/419 and one 429 retry.

    Only used for operations that do not change state (find, details, list,
    search, profile). Writes go through request_write.
    """
    api_key = load_api_key()
    token = None
    cache = None
    if auth:
        token, cache = ensure_token()
    retried_429 = False
    reauthed = False
    while True:
        try:
            resp = requests.request(
                method,
                BASE_URL + path,
                headers=_headers(api_key, token),
                params=params,
                data=data,
                json=json_body,
                timeout=TIMEOUT_SECS,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            raise ResyError(
                "%s %s failed before a response: %s" % (method, path, exc.__class__.__name__)
            )
        if resp.status_code in (301, 302, 303, 307, 308):
            raise ResyError(
                "%s %s was redirected (HTTP %d). Refusing to follow."
                % (method, path, resp.status_code)
            )
        if resp.status_code == 429 and not retried_429:
            retried_429 = True
            delay = _retry_after_seconds(resp)
            time.sleep(delay)
            continue
        if auth and _looks_like_auth_failure(resp.status_code, resp.text) and not reauthed:
            reauthed = True
            fresh = reauth()
            if fresh is None:
                raise ResyError(
                    "Resy rejected the cached token (HTTP %d) and nothing in "
                    "the environment can re-mint it. Mint a fresh token from "
                    "a signed-in resy.com session and run "
                    "`resy auth import-token`." % resp.status_code
                )
            token = fresh["token"]
            continue
        if resp.status_code == 429:
            raise ResyError("Resy rate limited the request (HTTP 429) even after a backoff.")
        if not resp.ok:
            raise ResyError(
                "%s %s failed (HTTP %d): %s"
                % (method, path, resp.status_code, _short_body(resp))
            )
        return _json_or_error(resp, path)


def request_write(method, path, data):
    """Write request (book, cancel). Sent exactly once, never replayed.

    Any failure, including a network error or an auth-shaped response, is
    reported as OutcomeUnknown because Resy may have processed the write
    before the failure surfaced.
    """
    api_key = load_api_key()
    token, _cache = ensure_token()
    try:
        resp = requests.request(
            method,
            BASE_URL + path,
            headers=_headers(api_key, token),
            data=data,
            timeout=TIMEOUT_SECS,
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise OutcomeUnknown(
            "%s %s failed mid-request (%s). The outcome is UNKNOWN: Resy may "
            "already have completed it. Run `resy list` and check before any "
            "retry. Never re-send the write blindly." % (method, path, exc.__class__.__name__)
        )
    if not resp.ok:
        raise OutcomeUnknown(
            "%s %s returned HTTP %d. The outcome is UNKNOWN: Resy may already "
            "have completed it. Run `resy list` and check before any retry. "
            "Never re-send the write blindly. Response: %s"
            % (method, path, resp.status_code, _short_body(resp))
        )
    try:
        return resp.json()
    except ValueError:
        return {"raw": resp.text[:200]}


def _retry_after_seconds(resp):
    raw = resp.headers.get("Retry-After", "")
    try:
        return max(1, min(60, int(raw)))
    except (TypeError, ValueError):
        return 15


def _short_body(resp):
    text = (resp.text or "").strip().replace("\n", " ")
    return text[:200] if text else "(empty body)"


# --------------------------------------------------------------------------
# Response parsing helpers
# --------------------------------------------------------------------------

def slot_time(start_value):
    """Resy slot times are restaurant-local strings like '2026-11-14 18:30:00'.

    Read HH:MM straight off the string. Never parse them as datetimes, which
    would shift them across timezones.
    """
    if not start_value:
        return ""
    text = str(start_value).replace("T", " ")
    parts = text.split(" ")
    if len(parts) >= 2 and ":" in parts[1]:
        return parts[1][:5]
    return text[:5]


def venue_id_from_config_token(config_token):
    """Config tokens look like rgs://resy/<venue_id>/<config_id>/... ."""
    if not config_token:
        return None
    text = str(config_token)
    if text.startswith("rgs://resy/"):
        segment = text[len("rgs://resy/"):].split("/", 1)[0]
        if segment.isdigit():
            return int(segment)
    return None


def parse_find_slots(payload):
    venues = ((payload.get("results") or {}).get("venues")) or []
    slots = []
    for venue in venues:
        for slot in venue.get("slots") or []:
            config = slot.get("config") or {}
            date_info = slot.get("date") or {}
            slots.append(
                {
                    "time": slot_time(date_info.get("start")),
                    "type": config.get("type") or "Dining Room",
                    "config_token": config.get("token"),
                }
            )
    return slots


def parse_reservations(payload):
    if isinstance(payload, list):
        items = payload
    else:
        items = payload.get("reservations") or []
    parsed = []
    for item in items:
        venue = item.get("venue") or {}
        cancellation = item.get("cancellation") or {}
        parsed.append(
            {
                "reservation_id": item.get("reservation_id") or item.get("id"),
                "resy_token": item.get("resy_token"),
                "venue_id": venue.get("id"),
                "venue_name": venue.get("name"),
                "day": item.get("day"),
                "time": slot_time(item.get("time_slot")) or item.get("time_slot"),
                "party_size": item.get("num_seats"),
                "cancellable": cancellation.get("allowed"),
            }
        )
    return parsed


def fetch_reservations():
    payload = request_read("GET", "/3/user/reservations")
    return parse_reservations(payload)


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------

def cmd_auth_login(_args):
    email = os.environ.get("RESY_EMAIL", "").strip()
    password = os.environ.get("RESY_PASSWORD", "")
    if not email or not password:
        raise ResyError(
            "auth login reads RESY_EMAIL and RESY_PASSWORD from the "
            "environment only. Set both and retry. Passwords are never taken "
            "as command arguments and never stored."
        )
    cache = login(email, password)
    name = cache.get("account_first_name")
    print("Logged in%s. Token cached (mode 600), value not shown."
          % ((" as " + name) if name else ""))
    return 0


def cmd_auth_otp(_args):
    email = os.environ.get("RESY_EMAIL", "").strip()
    if not email:
        raise ResyError(
            "auth otp reads the account email from the RESY_EMAIL "
            "environment variable only. Set it and retry."
        )
    code = os.environ.get("RESY_OTP_CODE", "").strip()
    if not code:
        payload = otp_request(email)
        mask = payload.get("email_mask") or payload.get("email") or "the account email"
        print("One-time code requested for %s. Check that inbox, then re-run "
              "with RESY_OTP_CODE set to verify." % mask)
        return 0
    cache = otp_verify(email, code)
    name = cache.get("account_first_name")
    print("OTP verified. Logged in%s. Token cached (mode 600), value not shown."
          % ((" as " + name) if name else ""))
    return 0


def cmd_auth_import_token(_args):
    token = os.environ.get("RESY_AUTH_TOKEN", "").strip()
    if not token:
        raise ResyError(
            "auth import-token reads the token from the RESY_AUTH_TOKEN "
            "environment variable only. Tokens are never taken as command "
            "arguments and never printed."
        )
    cache = import_token(token)
    name = cache.get("account_first_name")
    state = "validated against the account" if cache.get("_validated") else \
        "stored without validation (profile check did not complete)"
    print("Token imported%s and %s. Cached at mode 600, value not shown."
          % ((" for " + name) if name else "", state))
    return 0


def cmd_auth_status(_args):
    cache = _read_token_cache()
    if not cache:
        print("No cached token. Mint one from a signed-in resy.com session "
              "and run `resy auth import-token` with RESY_AUTH_TOKEN set.")
        return 0
    age_hours = (int(time.time()) - int(cache.get("obtained_at", 0))) / 3600.0
    expiry = _jwt_expiry(cache["token"])
    print("Cached token present, obtained %.1f hours ago.%s"
          % (age_hours, (" Expires " + expiry + ".") if expiry else ""))
    if cache.get("payment_method_id"):
        print("Default payment method id cached from login.")
    return 0


def _jwt_expiry(token):
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        exp = payload.get("exp")
        if exp:
            return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(int(exp)))
    except Exception:
        pass
    return None


def cmd_search(args):
    struct = {
        "page": 1,
        "per_page": 20,
        "types": ["venue"],
        "order_by": "availability",
        "geo": {"latitude": float(args.lat), "longitude": float(args.long),
                "radius": 16100},
        "query": args.query,
    }
    if args.day:
        struct["availability"] = True
        struct["slot_filter"] = {"day": args.day, "party_size": args.party_size}
    payload = request_read(
        "POST", "/3/venuesearch/search",
        data={"struct_data": json.dumps(struct)},
        auth=_token_available(),
    )
    hits = payload.get("hits")
    if hits is None:
        hits = (payload.get("search") or {}).get("hits") or []
    results = []
    for hit in hits:
        venue_id = None
        id_field = hit.get("id")
        if isinstance(id_field, dict):
            venue_id = id_field.get("resy")
        elif isinstance(id_field, int):
            venue_id = id_field
        results.append(
            {
                "venue_id": venue_id or hit.get("venue_id"),
                "name": hit.get("name"),
                "url_slug": hit.get("url_slug"),
                "neighborhood": (hit.get("location") or {}).get("neighborhood"),
            }
        )
    if args.json:
        print(json.dumps(results, indent=2))
        return 0
    if not results:
        print("No venues matched.")
        return 0
    for row in results:
        print("%s  %s  slug=%s  neighborhood=%s"
              % (row["venue_id"], row["name"], row["url_slug"], row["neighborhood"]))
    return 0


def _token_available():
    return _read_token_cache() is not None or bool(
        os.environ.get("RESY_AUTH_TOKEN")
        or (os.environ.get("RESY_EMAIL") and os.environ.get("RESY_PASSWORD"))
    )


def cmd_find(args):
    params = {
        "lat": args.lat,
        "long": args.long,
        "day": args.day,
        "party_size": str(args.party_size),
        "venue_id": str(args.venue_id),
    }
    if args.offset is not None:
        params["offset"] = str(args.offset)
    if args.limit is not None:
        params["limit"] = str(args.limit)
    payload = request_read("GET", "/4/find", params=params)
    slots = parse_find_slots(payload)
    if args.json:
        print(json.dumps(slots, indent=2))
        return 0
    if not slots:
        print("No slots for venue %s on %s for %d." % (args.venue_id, args.day, args.party_size))
        return 0
    for slot in slots:
        print("%s  %-20s  %s" % (slot["time"], slot["type"], slot["config_token"]))
    return 0


def fetch_details(config_id, day, party_size):
    return request_read(
        "GET", "/3/details",
        params={"config_id": config_id, "day": day, "party_size": str(party_size)},
    )


def _details_summary(details):
    policy = details.get("cancellation_policy") or {}
    pricing = details.get("pricing") or {}
    return {
        "cancellation_fee": policy.get("fee_description"),
        "is_cancellable": policy.get("is_cancellable"),
        "pricing_fees": pricing.get("fees"),
        "pricing_tax": pricing.get("tax"),
        "book_token_expires": (details.get("book_token") or {}).get("date_expires"),
    }


def cmd_details(args):
    details = fetch_details(args.config_id, args.day, args.party_size)
    summary = _details_summary(details)
    book_token = (details.get("book_token") or {}).get("value")
    if args.json:
        out = dict(summary)
        out["book_token"] = book_token
        print(json.dumps(out, indent=2))
        return 0
    print("Cancellation fee: %s" % (summary["cancellation_fee"] or "none stated"))
    print("Cancellable: %s" % summary["is_cancellable"])
    print("Pricing fees: %s  tax: %s" % (summary["pricing_fees"], summary["pricing_tax"]))
    print("Book token expires: %s" % summary["book_token_expires"])
    print("Book token (short-lived, needed by book): %s" % book_token)
    return 0


def resolve_payment_method_id(explicit, cache):
    if explicit:
        return explicit
    if cache and cache.get("payment_method_id"):
        return cache["payment_method_id"]
    try:
        profile = request_read("GET", "/2/user")
    except ResyError:
        return None
    methods = profile.get("payment_methods") or []
    for method in methods:
        if method.get("is_default"):
            return method.get("id")
    if methods:
        return methods[0].get("id")
    return None


def cmd_book(args):
    details = fetch_details(args.config_id, args.day, args.party_size)
    book_token = (details.get("book_token") or {}).get("value")
    if not book_token:
        raise ResyError("Details response carried no book_token. The slot may be gone.")
    summary = _details_summary(details)
    venue_id = venue_id_from_config_token(args.config_id)

    print("Booking preview")
    print("  venue_id: %s" % venue_id)
    print("  day: %s  party_size: %d" % (args.day, args.party_size))
    print("  cancellation fee: %s" % (summary["cancellation_fee"] or "none stated"))
    print("  pricing fees: %s  tax: %s" % (summary["pricing_fees"], summary["pricing_tax"]))
    if not args.confirm:
        print("Preview only. No booking was made. Re-run with --confirm to book.")
        return 2

    if not args.allow_duplicate and venue_id is not None:
        existing = [
            r for r in fetch_reservations()
            if r.get("venue_id") == venue_id and r.get("day") == args.day
            and r.get("day", "") >= date.today().isoformat()
        ]
        if existing:
            raise ResyError(
                "Refusing to book: an upcoming reservation already exists at "
                "venue %s on %s (reservation_id %s). Cancel it first or pass "
                "--allow-duplicate." % (venue_id, args.day, existing[0]["reservation_id"])
            )

    _token, cache = ensure_token()
    payment_id = resolve_payment_method_id(args.payment_method_id, cache)
    form = {"book_token": book_token, "source_id": "resy.com-venue-details"}
    if payment_id:
        form["struct_payment_method"] = json.dumps({"id": payment_id})
    else:
        print("Warning: no payment method id found. Booking without one. "
              "Venues that require a card hold will reject this.", file=sys.stderr)
    result = request_write("POST", "/3/book", data=form)
    print("Booked. reservation_id=%s resy_token=%s"
          % (result.get("reservation_id"), result.get("resy_token")))
    return 0


def cmd_list(args):
    reservations = fetch_reservations()
    today = date.today().isoformat()
    if args.scope == "upcoming":
        reservations = [r for r in reservations if (r.get("day") or "") >= today]
    elif args.scope == "past":
        reservations = [r for r in reservations if (r.get("day") or "") < today]
    reservations.sort(key=lambda r: (r.get("day") or "", str(r.get("time") or "")))
    if args.json:
        print(json.dumps(reservations, indent=2))
        return 0
    if not reservations:
        print("No %s reservations." % args.scope)
        return 0
    for row in reservations:
        print("%s %s  %s (venue %s)  party of %s  reservation_id=%s  resy_token=%s  cancellable=%s"
              % (row["day"], row["time"], row["venue_name"], row["venue_id"],
                 row["party_size"], row["reservation_id"], row["resy_token"],
                 row["cancellable"]))
    return 0


def cmd_cancel(args):
    resy_token = args.id
    match = None
    if not str(args.id).startswith("rr://"):
        for row in fetch_reservations():
            if str(row.get("reservation_id")) == str(args.id):
                match = row
                resy_token = row.get("resy_token")
                break
        if not resy_token:
            raise ResyError(
                "No upcoming reservation with id %s was found, so there is no "
                "resy_token to cancel with." % args.id
            )
    else:
        for row in fetch_reservations():
            if row.get("resy_token") == args.id:
                match = row
                break
    if match:
        print("Cancelling: %s %s at %s (venue %s), party of %s, reservation_id=%s"
              % (match["day"], match["time"], match["venue_name"],
                 match["venue_id"], match["party_size"], match["reservation_id"]))
    else:
        print("Cancelling resy_token %s (not found in the current list)." % resy_token)
    if not args.confirm:
        print("Preview only. Nothing was cancelled. Re-run with --confirm to cancel.")
        return 2
    request_write("POST", "/3/cancel", data={"resy_token": resy_token})
    print("Cancelled.")
    return 0


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        prog="resy",
        description="Unofficial Resy API client (api.resy.com). See SKILL.md.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    auth = sub.add_parser("auth", help="Login and token cache management.")
    auth_sub = auth.add_subparsers(dest="auth_command", required=True)
    auth_sub.add_parser("import-token", help="Cache a token from RESY_AUTH_TOKEN and validate it.")
    auth_sub.add_parser("otp", help="Email one-time-code login: RESY_EMAIL requests a code; RESY_EMAIL + RESY_OTP_CODE verifies it and caches the token.")
    auth_sub.add_parser("login", help="Log in via RESY_EMAIL / RESY_PASSWORD env vars.")
    auth_sub.add_parser("status", help="Show cached token state without printing it.")

    search = sub.add_parser("search", help="Resolve a venue name to a venue_id.")
    search.add_argument("--query", required=True)
    search.add_argument("--json", action="store_true")
    search.add_argument("--day", help="YYYY-MM-DD. Adds an availability slot filter.")
    search.add_argument("--party-size", type=int, default=2)
    search.add_argument("--lat", default=DEFAULT_LAT)
    search.add_argument("--long", default=DEFAULT_LONG)

    find = sub.add_parser("find", help="List bookable slots for a venue.")
    find.add_argument("--json", action="store_true")
    find.add_argument("--venue-id", required=True, type=int)
    find.add_argument("--day", required=True, help="YYYY-MM-DD")
    find.add_argument("--party-size", type=int, default=2)
    find.add_argument("--offset", type=int, default=None)
    find.add_argument("--limit", type=int, default=None)
    find.add_argument("--lat", default=DEFAULT_LAT)
    find.add_argument("--long", default=DEFAULT_LONG)

    details = sub.add_parser("details", help="Get book token and terms for one slot.")
    details.add_argument("--json", action="store_true")
    details.add_argument("--config-id", required=True,
                         help="The slot config token from find output.")
    details.add_argument("--day", required=True, help="YYYY-MM-DD")
    details.add_argument("--party-size", type=int, default=2)

    book = sub.add_parser("book", help="Book one slot. Requires --confirm.")
    book.add_argument("--config-id", required=True,
                      help="The slot config token from find output.")
    book.add_argument("--day", required=True, help="YYYY-MM-DD")
    book.add_argument("--party-size", type=int, default=2)
    book.add_argument("--payment-method-id", type=int, default=None)
    book.add_argument("--allow-duplicate", action="store_true")
    book.add_argument("--confirm", action="store_true",
                      help="Actually place the booking. Without it, prints a preview.")

    listing = sub.add_parser("list", help="List reservations.")
    listing.add_argument("--json", action="store_true")
    listing.add_argument("--scope", choices=["upcoming", "past", "all"], default="upcoming")

    cancel = sub.add_parser("cancel", help="Cancel a reservation. Requires --confirm.")
    cancel.add_argument("--id", required=True,
                        help="The reservation resy_token (rr://...) or numeric reservation_id.")
    cancel.add_argument("--confirm", action="store_true",
                        help="Actually cancel. Without it, prints a preview.")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    handlers = {
        "search": cmd_search,
        "find": cmd_find,
        "details": cmd_details,
        "book": cmd_book,
        "list": cmd_list,
        "cancel": cmd_cancel,
    }
    try:
        if args.command == "auth":
            if args.auth_command == "login":
                return cmd_auth_login(args)
            if args.auth_command == "otp":
                return cmd_auth_otp(args)
            if args.auth_command == "import-token":
                return cmd_auth_import_token(args)
            return cmd_auth_status(args)
        handler = handlers[args.command]
        return handler(args)
    except OutcomeUnknown as exc:
        print("OUTCOME UNKNOWN: %s" % exc, file=sys.stderr)
        return 3
    except ResyError as exc:
        print("Error: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
