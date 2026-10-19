#!/usr/bin/env python3
"""smartthings_find.py — SmartThings Find API client for Galaxy SmartTags.

Flow (documented by the open-source rreverser/ha-smartthings-find project, MIT):
  OAuth2 PKCE against Samsung account servers -> Find + SmartThings IoT tokens
  -> SmartThings installed-app execute proxy -> /devices, /trackers/geolocation

Passive mode only: reads the last reported location, never requests a fresh
fix (saves tag battery, matches what smartthingsfind.samsung.com shows).

Commands:
  auth-url                  Print the Samsung login URL (one-time setup)
  auth-complete <redir_url> Exchange the ms-app:// redirect URL for tokens
  auth                      Status check: tokens present, list trackers
  trackers                  List SmartTags on the account (name + device id)
  locate [--name <substr>]  Print a tracker's last reported location JSON
  battery [--name <substr>] Print a tracker's battery label only

Auth state: ~/.config/muse-connectors/smartthings-find/auth.json
(tokens, auto-refreshed). Needs the Python packages: requests, cryptography.
"""
import base64
import hashlib
import html
import json
import os
import random
import secrets
import string
import sys
import time
import urllib.parse
from datetime import datetime, timezone

import requests
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.backends import default_backend

CONFIG_DIR = os.path.expanduser("~/.config/muse-connectors/smartthings-find")
AUTH_FILE = os.path.join(CONFIG_DIR, "auth.json")

CLIENT_ID_AUTH = "yfrtglt53o"
CLIENT_ID_FIND = "27zmg0v1oo"
CLIENT_ID_ONECONNECT = "6iado3s6jc"
REDIRECT_URI = "ms-app://s-1-15-2-4027708247-2189610-1983755848-2937435718-1578786913-2158692839-1974417358"
URL_ENTRY_POINT = "https://account.samsung.com/accounts/ANDROIDSDK/getEntryPoint"
APP_VERSION = "1.8.21.28"
UA = f"Android/OneApp/{APP_VERSION}/Main (Google Pixel 8 Pro; Android 14/14) SmartKit/4.423.1"
FME_PLUGIN = "com.samsung.android.plugin.fme"

BATTERY_LABELS = {"FULL": "Full", "MEDIUM": "Medium", "LOW": "Low", "VERY_LOW": "Very low"}

S = requests.Session()
S.headers.update({"User-Agent": UA})


def _rand(n):
    return "".join(random.choices(string.ascii_letters + string.digits, k=n))


def _verifier():
    return base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()


def _challenge(v):
    return base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b"=").decode()


def _load_auth():
    if os.path.exists(AUTH_FILE):
        return json.load(open(AUTH_FILE))
    return {}


def _save_auth(a):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    json.dump(a, open(AUTH_FILE, "w"), indent=2)
    os.chmod(AUTH_FILE, 0o600)


def _encrypt_svc_param(svc_json, chk_do_num, public_key):
    chk_str = str(chk_do_num)
    chk_hash = hashlib.sha256(chk_str.encode()).digest()
    key = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", base64.b64encode(chk_hash), key, chk_do_num, dklen=16)
    enc_ky = public_key.encrypt(base64.b64encode(dk), asym_padding.PKCS1v15())
    iv = os.urandom(16)
    cipher = Cipher(algorithms.AES(dk), modes.CBC(iv), backend=default_backend())
    enc = cipher.encryptor()
    padder = padding.PKCS7(128).padder()
    padded = padder.update(svc_json.encode()) + padder.finalize()
    enc_param = enc.update(padded) + enc.finalize()
    payload = json.dumps({
        "chkDoNum": chk_str,
        "svcEncParam": base64.b64encode(enc_param).decode(),
        "svcEncKY": base64.b64encode(enc_ky).decode(),
        "svcEncIV": iv.hex(),
    })
    return urllib.parse.quote(base64.b64encode(payload.encode()).decode())


def _decrypt(value, key):
    try:
        kb = key.encode()
        kb = kb.ljust(16, b"\0")[:16]
        d = Cipher(algorithms.AES(kb), modes.ECB(), backend=default_backend()).decryptor()
        padded = d.update(bytes.fromhex(value)) + d.finalize()
        u = padding.PKCS7(128).unpadder()
        return (u.update(padded) + u.finalize()).decode()
    except Exception:
        return None


def cmd_auth_url():
    r = S.get(URL_ENTRY_POINT, timeout=30)
    r.raise_for_status()
    data = r.json()
    sign_in_uri, pki_key, chk_do_num = data["signInURI"], data["pkiPublicKey"], int(data["chkDoNum"])

    state = _rand(20)
    verifier = _verifier()
    device_id = secrets.token_hex(16)
    auth = _load_auth()
    auth.update({"pending": {"state": state, "code_verifier": verifier, "device_id": device_id}})
    _save_auth(auth)

    svc = {
        "clientId": CLIENT_ID_AUTH,
        "code_challenge": _challenge(verifier),
        "code_challenge_method": "S256",
        "competitorDeviceYNFlag": "Y",
        "countryCode": "us",
        "deviceInfo": "Google|com.android.chrome",
        "deviceModelID": "Pixel 8 Pro",
        "deviceName": "Google Pixel 8 Pro",
        "deviceOSVersion": "35",
        "devicePhysicalAddressText": f"ANID:{device_id}",
        "deviceType": "APP",
        "deviceUniqueID": device_id,
        "redirect_uri": REDIRECT_URI,
        "replaceableClientConnectYN": "N",
        "replaceableClientId": "",
        "replaceableDevicePhysicalAddressText": "",
        "responseEncryptionType": "1",
        "responseEncryptionYNFlag": "Y",
        "scope": "",
        "state": state,
        "svcIptLgnID": "",
        "iosYNFlag": "Y",
    }
    from cryptography.hazmat.primitives.serialization import load_der_public_key
    pub = load_der_public_key(base64.b64decode(pki_key), backend=default_backend())
    svc_value = _encrypt_svc_param(json.dumps(svc), chk_do_num, pub)
    print(f"{sign_in_uri}?locale=en&svcParam={svc_value}&mode=C")


def _token_post(auth_server, payload):
    r = S.post(f"{auth_server}/auth/oauth2/token", data=payload,
               headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
    r.raise_for_status()
    return r.json()


def cmd_auth_complete(redir):
    auth = _load_auth()
    pend = auth.get("pending")
    if not pend:
        sys.exit("No pending auth. Run 'auth-url' first.")
    parsed = urllib.parse.urlparse(redir)
    params = urllib.parse.parse_qs(parsed.query)
    if parsed.fragment:
        params.update(urllib.parse.parse_qs(parsed.fragment))
    g = lambda k: params.get(k, [""])[0]
    auth_server, code, state_p, ret = g("auth_server_url"), g("code"), g("state"), g("retValue")
    dec_state = _decrypt(state_p, pend["state"])
    if dec_state:
        auth_server = _decrypt(auth_server, dec_state) or auth_server
        code = _decrypt(code, dec_state) or code
        ret = _decrypt(ret, dec_state) or ret
    if auth_server and not auth_server.startswith("http"):
        auth_server = "https://" + auth_server
    if not auth_server or not code or not ret:
        sys.exit("Could not parse redirect URL (missing auth_server_url/code/retValue).")

    r = S.post(f"{auth_server}/auth/oauth2/authenticate", data={
        "grant_type": "authorization_code", "serviceType": "M",
        "client_id": CLIENT_ID_AUTH, "code": code,
        "code_verifier": pend["code_verifier"], "username": ret,
        "physical_address_text": pend["device_id"],
    }, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
    if r.status_code != 200:
        sys.exit(f"authenticate failed: {r.status_code} {r.text[:200]}")
    data = r.json()
    user_token = data.get("userauth_token") or data.get("userAuthToken")
    user_id = data.get("userId") or data.get("user_id")
    login_id = data.get("loginId") or data.get("login_id") or ret
    if not user_token or not user_id:
        sys.exit("authenticate response missing token/user id")

    def authorize(client_id, scope):
        v = _verifier()
        p = {"response_type": "code", "client_id": client_id, "scope": scope,
             "code_challenge": _challenge(v), "code_challenge_method": "S256",
             "userauth_token": user_token, "serviceType": "M",
             "childAccountSupported": "Y", "physical_address_text": pend["device_id"],
             "login_id": login_id}
        r = S.get(f"{auth_server}/auth/oauth2/v2/authorize", params=p, timeout=30)
        r.raise_for_status()
        ac = r.json().get("code")
        if not ac:
            sys.exit(f"authorize ({client_id}) returned no code: {r.text[:200]}")
        return _token_post(auth_server, {
            "grant_type": "authorization_code", "client_id": client_id,
            "code": ac, "code_verifier": v,
            "physical_address_text": pend["device_id"]})

    find_tok = authorize(CLIENT_ID_FIND, "offline.access")
    iot_tok = authorize(CLIENT_ID_ONECONNECT, "iot.client")
    auth.update({
        "auth_server_url": auth_server, "user_id": user_id,
        "device_id": pend["device_id"],
        "find_access": find_tok["access_token"], "find_refresh": find_tok["refresh_token"],
        "iot_access": iot_tok["access_token"], "iot_refresh": iot_tok["refresh_token"],
    })
    auth.pop("pending", None)
    _save_auth(auth)
    print("auth complete: tokens saved")


def _refresh(auth, which):
    acc_k, ref_k = (("find_access", "find_refresh") if which == "find"
                    else ("iot_access", "iot_refresh"))
    cid = CLIENT_ID_FIND if which == "find" else CLIENT_ID_ONECONNECT
    data = _token_post(auth["auth_server_url"], {
        "grant_type": "refresh_token", "refresh_token": auth[ref_k], "client_id": cid})
    auth[acc_k] = data["access_token"]
    auth[ref_k] = data["refresh_token"]
    _save_auth(auth)


def _iot_headers(auth):
    return {
        "Authorization": f"Bearer {auth['iot_access']}",
        "Accept": "application/vnd.smartthings+json;v=1",
        "User-Agent": UA,
        "X-St-Client-Appversion": APP_VERSION,
        "X-St-Client-Devicemodel": "Google Pixel 8 Pro",
        "X-St-Client-Os": "Android 14",
        "X-St-Correlation": secrets.token_hex(16),
    }


def _st_get(auth, url):
    r = S.get(url, headers=_iot_headers(auth), timeout=30)
    if r.status_code in (401, 403):
        _refresh(auth, "iot")
        r = S.get(url, headers=_iot_headers(auth), timeout=30)
    r.raise_for_status()
    return r.json()


def _installed_app_id(auth):
    if auth.get("installed_app_id"):
        return auth["installed_app_id"]
    me = _st_get(auth, "https://auth.api.smartthings.com/users/me")
    uuid_ = me.get("uuid")
    url = "https://api.smartthings.com/installedapps?allowed=true"
    app_id = None
    while url:
        data = _st_get(auth, url)
        for item in data.get("items", []):
            if item.get("ui", {}).get("pluginId") == FME_PLUGIN:
                if item.get("owner", {}).get("ownerId") == uuid_:
                    app_id = item["installedAppId"]
                    break
                app_id = app_id or item["installedAppId"]
        if app_id and item.get("owner", {}).get("ownerId") == uuid_:
            break
        url = ((data.get("_links") or {}).get("next") or {}).get("href")
    if not app_id:
        sys.exit("Find My Mobile installed app not found")
    auth["installed_app_id"] = app_id
    _save_auth(auth)
    return app_id


def _tz_offset():
    off = datetime.now(timezone.utc).astimezone().utcoffset()
    total = int(off.total_seconds()) if off else 0
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    return f"UTC{sign}{total // 3600:02d}:{(total % 3600) // 60:02d}"


def _execute(auth, method, uri, extra_uri=None, extra_params=None, body=None):
    app_id = _installed_app_id(auth)

    def b64j(p):
        if p is None:
            return ""
        raw = p.encode() if isinstance(p, str) else json.dumps(p, separators=(",", ":")).encode()
        return base64.b64encode(raw).decode()

    payload = {
        "client": {"displayMode": "LIGHT", "language": "en-US",
                   "mobileDeviceId": auth["device_id"], "os": "Android",
                   "samsungAccountId": auth["user_id"],
                   "supportedTemplates": ["BASIC_V1"],
                   "timeZoneOffset": _tz_offset(), "version": APP_VERSION},
        "parameters": {"requester": auth["user_id"], "requesterToken": auth["iot_access"],
                       "clientType": "aPlugin", "clientVersion": "1",
                       "method": method, "uri": uri, "extraUri": extra_uri,
                       "encodedHeaders": "", "encodedBody": b64j(body)},
    }
    if extra_params:
        payload["parameters"].update(extra_params)
    url = f"https://api.smartthings.com/installedapps/{app_id}/execute"
    h = _iot_headers(auth)
    h["Content-Type"] = "application/json"
    r = S.post(url, json=payload, headers=h, timeout=60)
    if r.status_code in (401, 403):
        _refresh(auth, "iot")
        payload["parameters"]["requesterToken"] = auth["iot_access"]
        h = _iot_headers(auth)
        h["Content-Type"] = "application/json"
        r = S.post(url, json=payload, headers=h, timeout=60)
    r.raise_for_status()
    return r.json()


def _trackers(auth):
    resp = _execute(auth, "GET", "/devices")
    if resp.get("statusCode") != 200 or not resp.get("message"):
        sys.exit(f"device list failed: {resp}")
    out = []
    for d in resp["message"].get("devices", []):
        if str(d.get("locationType", "")).upper() != "TRACKER":
            continue
        out.append(d)
    return out


def _tracker_name(d):
    return html.unescape(d.get("stDevName") or d.get("deviceName") or "")


def _tracker_id(d):
    return d.get("stDid") or d.get("deviceId") or d.get("fmmDevId")


def _find_device(auth, name_substr=None):
    trackers = _trackers(auth)
    if not trackers:
        sys.exit("no SmartTags found on this account")
    if name_substr:
        for d in trackers:
            if name_substr.lower() in _tracker_name(d).lower():
                return d
        sys.exit(f"no tracker matching {name_substr!r}; "
                 f"have: {[_tracker_name(d) for d in trackers]}")
    if len(trackers) == 1:
        return trackers[0]
    sys.exit("multiple trackers; name one with --name: "
             f"{[_tracker_name(d) for d in trackers]}")


def _require_auth():
    auth = _load_auth()
    if not auth.get("iot_access"):
        sys.exit("Not authenticated. Run 'auth-url' then 'auth-complete'.")
    return auth


def _locate(auth, name_substr=None):
    dev = _find_device(auth, name_substr)
    st_did = _tracker_id(dev)
    resp = _execute(auth, "GET", "/trackers/geolocation", extra_params={"stDids": st_did})
    if resp.get("statusCode") != 200 or not resp.get("message"):
        sys.exit(f"geolocation failed: {resp}")
    items = resp["message"].get("items", [])
    item = next((i for i in items
                 if i.get("deviceId") == st_did or i.get("stDid") == st_did
                 or i.get("fmmDevId") == st_did), items[0] if items else None)
    if not item:
        return {"name": _tracker_name(dev), "location_found": False}
    geos = item.get("geolocations") or item.get("geoLocations") or []
    geo = geos[0] if geos else {}
    batt_raw = geo.get("battery", geo.get("batteryLevel"))
    out = {
        "name": _tracker_name(dev),
        "location_found": bool(geo.get("latitude") and geo.get("longitude")),
        "lat": float(geo["latitude"]) if geo.get("latitude") else None,
        "lng": float(geo["longitude"]) if geo.get("longitude") else None,
        "accuracy_m": float(geo["accuracy"]) if geo.get("accuracy") else None,
        "updated_utc": None,
        "battery": BATTERY_LABELS.get(str(batt_raw), str(batt_raw) if batt_raw else None),
    }
    lu = geo.get("lastUpdateTime") or geo.get("lastUpdateAt")
    if lu:
        out["updated_utc"] = datetime.fromtimestamp(int(lu) / 1000, tz=timezone.utc).isoformat()
    return out


def cmd_auth():
    auth = _require_auth()
    trackers = _trackers(auth)
    print(json.dumps({"ok": True,
                      "trackers": [_tracker_name(d) for d in trackers]}))


def cmd_trackers():
    auth = _require_auth()
    for d in _trackers(auth):
        print(json.dumps({"name": _tracker_name(d), "deviceId": _tracker_id(d)}))


def cmd_locate(name_substr=None):
    auth = _require_auth()
    print(json.dumps(_locate(auth, name_substr)))


def cmd_battery(name_substr=None):
    auth = _require_auth()
    print(_locate(auth, name_substr).get("battery") or "unknown")


def _name_arg(argv):
    if "--name" in argv:
        i = argv.index("--name")
        if i + 1 < len(argv):
            return argv[i + 1]
        sys.exit("--name needs a value")
    return None


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: smartthings_find.py auth-url | auth-complete <url> | "
                 "auth | trackers | locate [--name X] | battery [--name X]")
    cmd = sys.argv[1]
    if cmd == "auth-url":
        cmd_auth_url()
    elif cmd == "auth-complete":
        cmd_auth_complete(sys.argv[2] if len(sys.argv) > 2 else sys.exit("missing redirect url"))
    elif cmd == "auth":
        cmd_auth()
    elif cmd == "trackers":
        cmd_trackers()
    elif cmd == "locate":
        cmd_locate(_name_arg(sys.argv[2:]))
    elif cmd == "battery":
        cmd_battery(_name_arg(sys.argv[2:]))
    else:
        sys.exit(f"unknown command: {cmd}")
