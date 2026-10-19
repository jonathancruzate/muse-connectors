#!/usr/bin/env python3
"""Winix air purifier CLI (Winix cloud API).

  winix.py auth              status check: known devices + state endpoint answers
  winix.py discover          one-time: login (env WINIX_EMAIL / WINIX_PASSWORD),
                             save deviceIds (password never stored)
  winix.py devices           list known purifiers
  winix.py state [name]      credential-free state read (power/mode/fan/AQI/filter)
  winix.py watch             state for all purifiers, one line each (for watchers)
  winix.py control <name> <attr> <value> --confirm "<exact effect>"
                             control a purifier (power/mode/fan/plasmawave/
                             childlock). Needs the Cognito identity_id passed
                             transiently via env WINIX_IDENTITY_ID (printed by
                             discover); it is never persisted by this tool.

State reads need no credentials: the state endpoint is device-scoped. The
one-time login (AWS Cognito SRP against the Winix app's public client) is
used only to discover deviceIds and obtain the identity_id capability token
for control URLs.

API constants (Cognito pool/client ids, AES key/IV for the mobile transport)
are the Winix app's own public constants, as documented by the open-source
iprak/winix project (MIT). They are not user credentials.

Needs: pycryptodome (AES transport); warrant_lite + python-jose (one-time
SRP login only).
"""
import base64
import binascii
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.request

try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad, unpad
except ImportError:
    sys.exit("need pycryptodome: pip install pycryptodome")

COGNITO_IDP = "https://cognito-idp.us-east-1.amazonaws.com/"
COGNITO_IDENTITY = "https://cognito-identity.us-east-1.amazonaws.com/"
MOBILE = "https://us.mobile.winix-iot.com"
API = "https://us.api.winix-iot.com"

CLIENT_ID = "5rjk59c5tt7k9g8gpj0vd2qfg9"  # Winix app public Cognito client
USER_POOL = "us-east-1_Ofd50EosD"
IDENTITY_POOL = "us-east-1:84008e15-d6af-4698-8646-66d05c1abe8b"

AES_KEY = bytes.fromhex("84be38f854e320dd4a0a8c7fe0f3a9b84c288445916933fc222465bbd5a518d0")
AES_IV = bytes.fromhex("dfd55f316e72e97b905f8739005c99a7")

APP_META = {"osType": "android", "osVersion": "29", "mobileLang": "en",
            "appVersion": "1.5.7", "mobileModel": "SM-G988B"}

ATTR = {
    "power": ("A02", {"on": "1", "off": "0"}),
    "mode": ("A03", {"auto": "01", "manual": "02"}),
    "fan": ("A04", {"low": "01", "medium": "02", "high": "03",
                     "turbo": "05", "sleep": "06", "super": "08"}),
    "plasmawave": ("A07", {"on": "1", "off": "0"}),
    "childlock": ("A08", {"on": "1", "off": "0"}),
}

CONFIG_DIR = os.path.expanduser("~/.config/muse-connectors/winix")
DEVICES_FILE = os.path.join(CONFIG_DIR, "devices.json")


def _req(url, data=None, headers=None, timeout=15):
    """One retry on transient connection failures."""
    last = None
    for _ in range(2):
        req = urllib.request.Request(
            url, method="POST" if data is not None else "GET")
        req.add_header("Connection", "close")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        if data is not None:
            req.data = data if isinstance(data, bytes) else json.dumps(data).encode()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        except Exception as e:  # transient network failure: retry once
            last = e
            time.sleep(1)
    raise last


def _cognito(action, payload):
    status, body = _req(
        COGNITO_IDP, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/x-amz-json-1.1",
                 "X-Amz-Target": f"AWSCognitoIdentityProviderService.{action}"},
        timeout=20)
    if status != 200:
        raise RuntimeError(f"cognito {action} failed: {status} {body[:300]!r}")
    return json.loads(body)


def _enc(payload):
    raw = pad(json.dumps(payload).encode(), AES.block_size)
    return AES.new(AES_KEY, AES.MODE_CBC, AES_IV).encrypt(raw)


def _dec(blob):
    return json.loads(unpad(AES.new(AES_KEY, AES.MODE_CBC, AES_IV).decrypt(blob),
                            AES.block_size).decode())


def _mobile(path, payload):
    status, body = _req(MOBILE + path, data=_enc(payload),
                        headers={"Content-Type": "application/octet-stream",
                                 "Accept": "application/octet-stream"},
                        timeout=20)
    if status != 200:
        raise RuntimeError(f"mobile {path}: {status} {body[:200]!r}")
    return _dec(body)


def _uuid_for(sub):
    b = sub.encode()
    return (f"{binascii.crc32(b'github.com/hfern/winixctl' + b):08x}"
            f"{binascii.crc32(b'HGF' + b):08x}")


class WinixSession:
    """One-time authenticated session (Cognito USER_SRP_AUTH). Use once for
    discovery, then discard. The password is never stored."""

    def __init__(self, email, password):
        try:
            from warrant_lite import WarrantLite
            from jose import jwt as jose_jwt
        except ImportError:
            sys.exit("discover needs warrant_lite + python-jose: "
                     "pip install warrant_lite python-jose")
        wl = WarrantLite(username=email, password=password,
                         pool_id=USER_POOL, client_id=CLIENT_ID,
                         client_secret=None, client=object())
        res = _cognito("InitiateAuth", {
            "ClientId": CLIENT_ID, "AuthFlow": "USER_SRP_AUTH",
            "AuthParameters": wl.get_auth_params()})
        if res.get("ChallengeName") != "PASSWORD_VERIFIER":
            raise RuntimeError(f"unexpected challenge: {res.get('ChallengeName')}")
        cp = res["ChallengeParameters"]
        user_id_for_srp = cp["USER_ID_FOR_SRP"]
        hkdf = wl.get_password_authentication_key(
            user_id_for_srp, password, int(cp["SRP_B"], 16), cp["SALT"])
        secret_block_bytes = base64.standard_b64decode(cp["SECRET_BLOCK"])
        import datetime as _dt
        import re as _re
        _days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        _months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        now = _dt.datetime.now(_dt.timezone.utc)
        timestamp = (f"{_days[now.weekday()]} {_months[now.month - 1]} "
                     f"{now.day} {now:%H:%M:%S} UTC {now.year}")
        timestamp = _re.sub(r" 0(\d) ", r" \1 ", timestamp)
        msg = (USER_POOL.split("_")[1].encode() + user_id_for_srp.encode()
               + secret_block_bytes + timestamp.encode())
        sig = base64.standard_b64encode(
            hmac.new(hkdf, msg, digestmod=hashlib.sha256).digest()).decode()
        res2 = _cognito("RespondToAuthChallenge", {
            "ClientId": CLIENT_ID,
            "ChallengeName": "PASSWORD_VERIFIER",
            "ChallengeResponses": {
                "TIMESTAMP": timestamp,
                "USERNAME": user_id_for_srp,
                "PASSWORD_CLAIM_SECRET_BLOCK": cp["SECRET_BLOCK"],
                "PASSWORD_CLAIM_SIGNATURE": sig}})
        auth = res2["AuthenticationResult"]
        self.access_token = auth["AccessToken"]
        self.id_token = auth["IdToken"]
        self.sub = jose_jwt.get_unverified_claims(self.access_token)["sub"]
        self.uuid = _uuid_for(self.sub)

        status, body = _req(
            COGNITO_IDENTITY,
            data=json.dumps({"IdentityPoolId": IDENTITY_POOL,
                             "Logins": {f"cognito-idp.us-east-1.amazonaws.com/{USER_POOL}":
                                        self.id_token}}).encode(),
            headers={"Content-Type": "application/x-amz-json-1.1",
                     "X-Amz-Target": "AWSCognitoIdentityService.GetId"},
            timeout=20)
        if status != 200:
            raise RuntimeError(f"getId failed: {status} {body[:200]!r}")
        self.identity_id = json.loads(body)["IdentityId"]

        _mobile("/registerUser",
                {"accessToken": self.access_token, "uuid": self.uuid,
                 **APP_META, "email": email, "identityId": self.identity_id})
        _mobile("/init", {"accessToken": self.access_token,
                          "uuid": self.uuid, "region": "US"})
        _mobile("/checkAccessToken",
                {"accessToken": self.access_token, "uuid": self.uuid,
                 **APP_META, "identityId": self.identity_id})

    def devices(self):
        res = _mobile("/getDeviceInfoList",
                      {"accessToken": self.access_token, "uuid": self.uuid})
        return res.get("deviceInfoList", [])


def get_state(device_id):
    """Credential-free state read."""
    status, body = _req(f"{API}/common/event/sttus/devices/{device_id}",
                        headers={}, timeout=15)
    if status != 200:
        return {"ok": False, "http": status,
                "raw": body[:200].decode("utf8", "replace")}
    try:
        data = json.loads(body)
        item = data["body"]["data"][0]
        return {"ok": True, "deviceId": device_id,
                "attributes": item.get("attributes", {}),
                "rssi": item.get("rssi"),
                "utcDatetime": item.get("utcDatetime"),
                "utcTimestamp": item.get("utcTimestamp"),
                "modelId": item.get("modelId")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def control(device_id, identity_id, attr, value):
    """Direct control. identity_id is a capability-style token in the control
    URL; supply it transiently per invocation, never persist it."""
    code, mapping = ATTR[attr]
    val = mapping[value]
    url = f"{API}/common/control/devices/{device_id}/{identity_id}/{code}:{val}"
    status, body = _req(url, headers={}, timeout=15)
    if status in (500, 503):  # retry once after 1s
        time.sleep(1)
        status, body = _req(url, headers={}, timeout=15)
    return {"ok": status == 200, "http": status,
            "raw": body[:200].decode("utf8", "replace")}


def interpret(attrs):
    """Human-friendly summary of raw attributes."""
    aqi_map = {"01": "good", "02": "fair", "03": "poor", "04": "very_poor"}
    fan_map = {"01": "low", "02": "medium", "03": "high", "05": "turbo",
               "06": "sleep", "08": "super"}
    used = int(attrs.get("A21", 0) or 0)
    return {
        "power": "on" if attrs.get("A02") == "1" else "off",
        "mode": "auto" if attrs.get("A03") == "01" else "manual",
        "fan": fan_map.get(attrs.get("A04"), attrs.get("A04")),
        "aqi_led": attrs.get("A05"),
        "air_quality": aqi_map.get(attrs.get("S07"), attrs.get("S07")),
        "pm25": attrs.get("S04"),
        "plasmawave": "on" if attrs.get("A07") == "1" else "off",
        "filter_used_hours": used,
        "filter_remaining_pct": round(max(0, (6480 - used)) / 6480 * 100, 1),
    }


def load_devices():
    if os.path.exists(DEVICES_FILE):
        with open(DEVICES_FILE) as f:
            return json.load(f)
    return {}


def save_devices(devs):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(DEVICES_FILE, "w") as f:
        json.dump(devs, f, indent=2)
    os.chmod(DEVICES_FILE, 0o600)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

USAGE = (__doc__)


def _resolve(name):
    devs = load_devices()
    if not devs:
        sys.exit("no devices known; run `winix.py discover` first")
    if name:
        for alias, d in devs.items():
            if name.lower() in alias.lower():
                return alias, d["deviceId"]
        sys.exit(f"no purifier matching {name!r}")
    if len(devs) == 1:
        alias = next(iter(devs))
        return alias, devs[alias]["deviceId"]
    sys.exit("multiple purifiers; name one")


def cmd_auth():
    devs = load_devices()
    if not devs:
        print(json.dumps({"ok": False,
                          "reason": "no devices discovered yet; run discover"}))
        return 1
    alias, device_id = _resolve(None) if len(devs) == 1 else (None, None)
    if device_id is None:
        alias = next(iter(devs))
        device_id = devs[alias]["deviceId"]
    res = get_state(device_id)
    print(json.dumps({"ok": bool(res.get("ok")), "devices": list(devs),
                      "sample_state_ok": bool(res.get("ok"))}))
    return 0 if res.get("ok") else 1


def cmd_discover():
    email = os.environ.get("WINIX_EMAIL")
    password = os.environ.get("WINIX_PASSWORD")
    if not email or not password:
        sys.exit("set WINIX_EMAIL and WINIX_PASSWORD env vars "
                 "(one-time use; never stored)")
    sess = WinixSession(email, password)
    devs = {}
    for d in sess.devices():
        if d.get("productGroup") == "Air01":
            alias = d.get("deviceAlias") or d.get("modelName")
            devs[alias] = {"deviceId": d["deviceId"], "mac": d.get("mac"),
                           "model": d.get("modelName")}
    save_devices(devs)
    print(f"discovered {len(devs)} purifier(s): {', '.join(devs)}")
    print("password was used once and discarded; deviceIds saved.")
    print(f"control identity_id for this session: {sess.identity_id}")
    print("pass it transiently as WINIX_IDENTITY_ID for `control`; "
          "it is intentionally not stored.")


def cmd_devices():
    devs = load_devices()
    if not devs:
        sys.exit("no devices known; run `winix.py discover` first")
    for alias, d in devs.items():
        print(f"{alias}: {d['deviceId']} ({d.get('model', '?')})")


def cmd_state(name):
    alias, device_id = _resolve(name)
    res = get_state(device_id)
    if not res.get("ok"):
        print(json.dumps({"purifier": alias, **res}, indent=2))
        return
    print(json.dumps({"purifier": alias, **interpret(res["attributes"]),
                      "rssi": res.get("rssi"),
                      "winix_timestamp": res.get("utcDatetime")}, indent=2))


def cmd_watch():
    devs = load_devices()
    if not devs:
        sys.exit("no devices known; run `winix.py discover` first")
    for alias, d in devs.items():
        res = get_state(d["deviceId"])
        if not res.get("ok"):
            print(f"{alias}: UNREACHABLE ({res.get('http') or res.get('error')})")
            continue
        s = interpret(res["attributes"])
        print(f"{alias}: power={s['power']} mode={s['mode']} fan={s['fan']} "
              f"aq={s['air_quality']} filter={s['filter_remaining_pct']}% "
              f"winix_ts={res.get('utcDatetime')}")


def cmd_control(rest):
    confirm = None
    args = []
    i = 0
    while i < len(rest):
        if rest[i] == "--confirm" and i + 1 < len(rest):
            confirm = rest[i + 1]
            i += 2
        else:
            args.append(rest[i])
            i += 1
    if len(args) != 3:
        sys.exit("usage: winix.py control <name> <attr> <value> "
                 "--confirm \"<exact effect>\"")
    name, attr, value = args
    if attr not in ATTR:
        sys.exit(f"attr must be one of {sorted(ATTR)}")
    if value not in ATTR[attr][1]:
        sys.exit(f"value for {attr} must be one of {sorted(ATTR[attr][1])}")
    if not confirm or len(confirm.strip()) < 3:
        sys.exit(f"refused: control is a write. This would set {attr}={value} "
                 f"on purifier '{name}'. Re-run with --confirm \"<exact "
                 f"effect>\" after the user confirms in conversation.")
    identity_id = os.environ.get("WINIX_IDENTITY_ID")
    if not identity_id:
        sys.exit("WINIX_IDENTITY_ID is not set: run `discover` (one-time "
                 "login) and pass the printed identity_id transiently.")
    alias, device_id = _resolve(name)
    res = control(device_id, identity_id, attr, value)
    print(json.dumps({"purifier": alias, "attr": attr, "value": value, **res}))


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(USAGE)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "auth":
        return cmd_auth()
    if cmd == "discover":
        cmd_discover()
    elif cmd == "devices":
        cmd_devices()
    elif cmd == "state":
        cmd_state(rest[0] if rest else None)
    elif cmd == "watch":
        cmd_watch()
    elif cmd == "control":
        cmd_control(rest)
    else:
        print(USAGE)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
