"""
YI Cloud API client — authenticates with us.laikuai.com and pulls camera streams
without requiring the YI app at runtime.

Architecture:
  1. Login once with YI account credentials → get access token
  2. Get camera device ID from device list
  3. Use device ID to get streaming URL / P2P token
  4. Feed stream into the camera gateway

Security: credentials are NEVER stored to disk or git.
           Pass via env vars: YI_EMAIL, YI_PASSWORD (or provide at runtime).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import time
from typing import Any

LOGGER = logging.getLogger(__name__)

# YI Cloud API endpoints — real host discovered via HTTP Toolkit traffic capture
_ENDPOINTS = [
    "https://gw-us.xiaoyi.com",   # US gateway (confirmed from live traffic)
    "https://gw-eu.xiaoyi.com",   # EU fallback
]
APP_ID = "com.yi.android"

# Google OAuth client IDs extracted from live JWT capture 2026-08-08
# aud = YI server-side client, azp = Android app client
_GOOGLE_CLIENT_ID = "903608373634-1mdc1ep1pn25ks95plf7idsosa5v2ejh.apps.googleusercontent.com"
_GOOGLE_AZP_CLIENT_ID = "903608373634-hu8acfi640dstvrroa25k280eseiejbb.apps.googleusercontent.com"

_session: dict[str, Any] = {}


# ── Low-level HTTP helper ─────────────────────────────────────────────────────
# Python's ssl stack sends SNI which YI's AWS Global Accelerator rejects.
# curl uses a different TLS stack and handles it correctly.

_CURL = shutil.which("curl")

# Exact headers observed from live YI app traffic (HTTP Toolkit capture 2026-08-08)
_APP_VERSION = "android;448;6.9.2_20260522071155"
_USER_AGENT = "yihome/6.9.2_20260522071155 (Android 15; en-US)"

_BASE_HEADERS = [
    "Content-Type: application/json",
    "Accept: application/json",
    "Accept-Encoding: gzip",
    "Connection: Keep-Alive",
    f"User-Agent: {_USER_AGENT}",
    "x-kamihome-appType: ANDROID",
    "x-kamihome-packageType: RELEASE",
    "x-xiaoyi-appCountryCode: US",
    f"x-xiaoyi-appVersion: {_APP_VERSION}",
]


def _hmac_params(user_id: str, secret: str, path: str) -> dict:
    """Build HMAC query params matching YI app signing (HMAC-SHA1 over userid+path+timestamp)."""
    import hmac as _hmac, base64, time as _t
    ts = str(int(_t.time()))
    msg = f"{user_id}{path}{ts}".encode()
    key = secret.encode()
    sig = base64.b64encode(_hmac.new(key, msg, "sha1").digest()).decode()
    return {"hmac": sig, "userid": user_id, "seq": ts}


def _curl_request(method: str, url: str, body: dict | None = None,
                  token: str | None = None) -> dict:
    """HTTP via curl subprocess — bypasses Python TLS SNI issue entirely."""
    if not _CURL:
        return {"error": "curl not found on PATH"}
    cmd = [_CURL, "-sk", "-X", method, "--max-time", "20"]
    for h in _BASE_HEADERS:
        cmd += ["-H", h]
    if token:
        cmd += ["-H", f"Authorization: Bearer {token}"]
    if body:
        cmd += ["-d", json.dumps(body, separators=(",", ":"))]
    cmd.append(url)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
        raw = result.stdout.strip()
        if not raw:
            err = result.stderr.strip()[:300]
            LOGGER.error("curl empty response: %s", err)
            return {"error": f"curl: {err}"}
        parsed = json.loads(raw)
        # Normalise: treat non-zero YI error codes as errors
        code = parsed.get("code", parsed.get("status", 0))
        if code not in (0, 200, None, ""):
            return {"error": code, "message": parsed.get("msg", parsed.get("message", raw[:200]))}
        return parsed
    except json.JSONDecodeError:
        LOGGER.error("curl non-JSON: %s", result.stdout[:300])
        return {"error": "non-json", "raw": result.stdout[:300]}
    except Exception as exc:
        LOGGER.error("curl request failed: %s", exc)
        return {"error": str(exc)}


def _request(method: str, path: str, body: dict | None = None,
             token: str | None = None, base_url: str = _ENDPOINTS[0]) -> dict:
    # Build URL with HMAC auth params if session has them
    uid = _session.get("user_id", "")
    hmac_val = _session.get("hmac", "")
    qs = f"?userid={uid}&seq=1" if uid else ""
    if hmac_val:
        import urllib.parse
        qs += f"&hmac={urllib.parse.quote(hmac_val, safe='')}"
    return _curl_request(method, f"{base_url}{path}{qs}", body=body, token=token)


# ── Auth ─────────────────────────────────────────────────────────────────────

# YI uses Google Sign-In. The app exchanges a Google id_token for a YI session token.
_GOOGLE_LOGIN_PATHS = [
    "/v5/user/google_signin",
    "/v4/user/google_signin",
    "/v1/user/google_signin",
    "/v5/oauth/google",
    "/v1/oauth/google",
    "/v5/user/social_login",
    "/v1/user/social_login",
]


def login_google(google_id_token: str) -> dict[str, Any]:
    """Exchange a Google id_token for a YI session via /v4/auth/login (real endpoint)."""
    import urllib.parse, json as _json
    last_err = "unknown"
    # Decode JWT email/name from the token payload for the API call
    try:
        import base64 as _b64
        payload_b64 = google_id_token.split('.')[1]
        payload_b64 += '=' * (-len(payload_b64) % 4)
        jwt_data = _json.loads(_b64.b64decode(payload_b64))
        email = jwt_data.get('email', '')
        name = jwt_data.get('name', '')
    except Exception:
        email, name = '', ''

    for base in _ENDPOINTS:
        # Real login endpoint discovered from HTTP Toolkit capture (opt_type=1 = login)
        qs = urllib.parse.urlencode({
            'code': google_id_token, 'dev_name': 'PC', 'name': name,
            'dev_os_version': 'Windows 11', 'opt_type': '1', 'type': '14',
            'dev_type': 'camcontrol', 'seq': '1', 'email': email,
        })
        url = f"{base}/v4/auth/login?{qs}"
        resp = _curl_request('GET', url)
        if resp.get('code') == '20000':
            data = resp.get('data', {})
            token = data.get('token', '')
            token_secret = data.get('token_secret', '')
            user_id = str(data.get('userid', ''))
            open_id = data.get('openId', '')
            if token:
                _session.update({
                    'token': token, 'token_secret': token_secret,
                    'user_id': user_id, 'open_id': open_id,
                    'login_at': time.time(), 'base': base,
                    # Use the session HMAC pattern from live capture
                    'hmac': '0zLfYnrDo4yqvvw4571Ia1zCUJo=',
                })
                LOGGER.info("YI login OK via /v4/auth/login user=%s", user_id)
                return {'ok': True, 'token': token, 'user_id': user_id}
            last_err = f"No token in response: {str(resp)[:200]}"
        else:
            last_err = f"{base}: code={resp.get('code')} {resp.get('message','')[:100]}"
    return {'ok': False, 'error': last_err}


def login(email: str, password: str) -> dict[str, Any]:
    """Try password login (legacy) — most YI accounts now require Google auth."""
    pw_variants = [
        hashlib.md5(password.encode()).hexdigest(),
        password,
        hashlib.sha256(password.encode()).hexdigest(),
    ]
    last_err = "unknown"
    paths = ["/v5/user/signin", "/v4/user/signin", "/v1/user/signin",
             "/v5/user/login", "/v4/user/login", "/v1/account/login"]

    for base in _ENDPOINTS:
        for pw in pw_variants:
            for path in paths:
                for body in [
                    {"username": email, "password": pw, "app_id": APP_ID},
                    {"email": email, "password": pw, "app_id": APP_ID},
                    {"account": email, "password": pw},
                ]:
                    resp = _request("POST", path, body, base_url=base)
                    if "error" not in resp:
                        data = resp.get("data", resp)
                        token = (data.get("token") or data.get("access_token")
                                 or data.get("sessionId"))
                        user_id = data.get("user_id") or data.get("uid") or data.get("userId")
                        if token:
                            _session.update({"token": token, "user_id": user_id,
                                             "login_at": time.time(), "base": base})
                            LOGGER.info("YI Cloud login OK via %s%s user=%s", base, path, user_id)
                            return {"ok": True, "token": token, "user_id": user_id}
                        last_err = f"No token in response from {base}{path}: {str(resp)[:200]}"
                    else:
                        last_err = f"{base}{path}: {resp.get('message', resp.get('error', ''))}"

    LOGGER.error("All login attempts failed. Last: %s", last_err)
    return {"ok": False, "error": last_err}


def _token() -> str | None:
    return _session.get("token")


def _base() -> str:
    return _session.get("base", _ENDPOINTS[0])


# ── Devices ──────────────────────────────────────────────────────────────────

def get_device_password(uid: str) -> str | None:
    """Get the TUTK P2P password for a device from /v5/devices/password."""
    t = _token()
    uid_val = _session.get("user_id", "")
    hmac_val = _session.get("hmac", "")
    url = f"{_base()}/v5/devices/password?uid={uid}&pincode=&userid={uid_val}&seq=1"
    if hmac_val:
        import urllib.parse
        url += f"&hmac={urllib.parse.quote(hmac_val, safe='')}"
    resp = _curl_request("GET", url)
    data = resp.get("data", {}) if resp.get("code") == "20000" else {}
    return data.get("password")


def get_devices() -> list[dict]:
    """Return list of cameras registered to the account."""
    t = _token()
    uid = _session.get("user_id", "")
    if not t or not uid:
        return []
    resp = _request("GET", f"/v5/devices/list", token=t, base_url=_base())
    if "error" in resp:
        return []
    devices = resp.get("data", [])
    if isinstance(devices, list):
        return devices
    return []


def find_camera(mac: str | None = None, ip: str | None = None) -> dict | None:
    """Find camera by MAC address or IP. Returns device dict or None."""
    for dev in get_devices():
        dev_mac = (dev.get("mac") or "").replace(":", "").lower()
        if mac and dev_mac == mac.replace(":", "").lower():
            return dev
        if ip and dev.get("ip") == ip:
            return dev
    return None


# ── Streaming ────────────────────────────────────────────────────────────────

def get_stream_url(device_id: str, channel: int = 0) -> dict:
    """Get live stream URL for a camera. Returns RTSP or HLS URL if available."""
    t = _token()
    if not t:
        return {"error": "Not authenticated"}

    # Try direct stream URL first
    resp = _request("GET", f"/v1/device/stream?device_id={device_id}&channel={channel}", token=t)
    if "error" not in resp:
        data = resp.get("data", resp)
        url = data.get("url") or data.get("rtsp_url") or data.get("hls_url") or data.get("stream_url")
        if url:
            return {"ok": True, "url": url, "device_id": device_id}

    # Try P2P token endpoint
    resp2 = _request("POST", "/v1/device/p2p_token", {"device_id": device_id, "channel": channel}, token=t)
    if "error" not in resp2:
        data2 = resp2.get("data", resp2)
        return {"ok": True, "p2p_token": data2.get("token"), "did": data2.get("did"), "raw": data2}

    return {"ok": False, "raw_stream": resp, "raw_p2p": resp2}


def get_snapshot(device_id: str) -> bytes | None:
    """Get a JPEG snapshot from the camera via YI cloud."""
    t = _token()
    if not t:
        return None
    resp = _request("GET", f"/v1/device/snapshot?device_id={device_id}", token=t)
    if "error" in resp:
        return None
    url = (resp.get("data") or resp).get("url")
    if not url:
        return None
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.read()
    except Exception as exc:
        LOGGER.error("Snapshot download failed: %s", exc)
        return None


# ── Convenience ───────────────────────────────────────────────────────────────

def status() -> dict:
    if not _session.get("token"):
        return {"authenticated": False}
    age = int(time.time() - _session.get("login_at", 0))
    return {"authenticated": True, "user_id": _session.get("user_id"), "token_age_s": age}


def login_from_env() -> dict:
    """Login using YI_EMAIL and YI_PASSWORD environment variables."""
    email = os.environ.get("YI_EMAIL", "")
    password = os.environ.get("YI_PASSWORD", "")
    if not email or not password:
        return {"ok": False, "error": "YI_EMAIL and YI_PASSWORD not set"}
    return login(email, password)


def get_google_token_url() -> str:
    """Google OAuth URL using the real YI app client ID (captured from live JWT)."""
    redirect = "http://localhost:8765/oauth/callback"
    return (
        f"https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={_GOOGLE_CLIENT_ID}"
        f"&redirect_uri={redirect}"
        f"&response_type=id_token"
        f"&scope=openid+email+profile"
        f"&nonce=camcontrol"
    )


def capture_google_token_via_browser(timeout: int = 120) -> dict:
    """Open browser for Google OAuth and capture the id_token via local callback."""
    import urllib.parse
    import webbrowser
    from http.server import BaseHTTPRequestHandler, HTTPServer

    captured: dict = {}

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass  # suppress access logs

        def do_GET(self):
            # Google returns token in fragment (#id_token=...) which never reaches server.
            # Serve a tiny page that reads the fragment and POSTs it back.
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"""<html><body>
<script>
var p=new URLSearchParams(location.hash.slice(1));
var t=p.get('id_token');
if(t){fetch('/token',{method:'POST',body:t}).then(()=>{document.body.innerHTML='<h2>Token captured! You can close this tab.</h2>'});}
else{document.body.innerHTML='<h2>No token found. Try again.</h2>';}
</script><p>Capturing token...</p></body></html>""")

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            token = self.rfile.read(length).decode()
            captured["id_token"] = token
            self.send_response(200)
            self.end_headers()

    server = HTTPServer(("localhost", 8765), _Handler)
    server.timeout = 2
    url = get_google_token_url()
    webbrowser.open(url)
    LOGGER.info("Opened browser for Google OAuth. Waiting for callback...")
    deadline = time.time() + timeout
    while time.time() < deadline and "id_token" not in captured:
        server.handle_request()
    server.server_close()
    if "id_token" not in captured:
        return {"ok": False, "error": "Timed out waiting for Google OAuth callback"}
    return login_google(captured["id_token"])
