"""
Watches HTTP Toolkit's HAR export folder for new captures,
extracts YI id_token and client_id, and posts them to the gateway.

Usage:
  python extract_yi_token.py [--har <path>] [--gateway http://localhost:8080]

If no --har path given, scans common HTTP Toolkit export locations.
Also accepts a raw token via --token flag for manual paste.
"""
from __future__ import annotations
import argparse, json, os, re, sys, time
from pathlib import Path

GW_DEFAULT = "http://localhost:8080"
_SEARCH_DIRS = [
    Path.home() / "Downloads",
    Path.home() / "Documents",
    Path(os.environ.get("USERPROFILE", "")) / "Downloads",
]


def find_latest_har() -> Path | None:
    candidates = []
    for d in _SEARCH_DIRS:
        if d.exists():
            candidates.extend(d.glob("*.har"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def extract_from_har(har_path: Path) -> dict:
    """Return {id_token, client_id, yi_token} from a HAR file."""
    data = json.loads(har_path.read_text(encoding="utf-8"))
    entries = data.get("log", {}).get("entries", [])
    found: dict = {}

    for entry in entries:
        url = entry.get("request", {}).get("url", "")
        req = entry.get("request", {})
        resp = entry.get("response", {})

        # Google token endpoint → grab id_token
        if "oauth2/token" in url or "accounts.google.com" in url:
            body_text = req.get("postData", {}).get("text", "")
            for part in body_text.split("&"):
                if "=" in part:
                    k, v = part.split("=", 1)
                    if k == "id_token":
                        found["id_token"] = v
                    if k == "client_id":
                        found["google_client_id"] = v

        # YI API call to xiaoyi.com or laikuai.com → grab their session token
        if "xiaoyi.com" in url or "laikuai.com" in url:
            print(f"  → YI API call: {url}")
            # Check request body
            body_text = req.get("postData", {}).get("text", "")
            if body_text:
                try:
                    body = json.loads(body_text)
                    if "id_token" in body:
                        found["id_token"] = body["id_token"]
                    if "client_id" in body:
                        found["google_client_id"] = body["client_id"]
                except Exception:
                    # Try to extract with regex
                    m = re.search(r'"id_token"\s*:\s*"([^"]+)"', body_text)
                    if m:
                        found["id_token"] = m.group(1)
            # Check response for YI session token
            resp_text = resp.get("content", {}).get("text", "")
            if resp_text:
                try:
                    resp_body = json.loads(resp_text)
                    data_obj = resp_body.get("data", resp_body)
                    yi_token = (data_obj.get("token") or data_obj.get("access_token")
                                or data_obj.get("sessionId"))
                    if yi_token:
                        found["yi_token"] = yi_token
                        found["yi_user_id"] = data_obj.get("user_id") or data_obj.get("uid")
                except Exception:
                    pass

    return found


def post_to_gateway(id_token: str, gateway: str) -> bool:
    try:
        import urllib.request
        body = json.dumps({"google_token": id_token}).encode()
        req = urllib.request.Request(
            f"{gateway}/api/cloud/google-login",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            resp = json.loads(r.read())
            if resp.get("ok"):
                print(f"\n✅ YI Cloud login OK! user_id={resp.get('user_id')}")
                print(f"   Now call POST {gateway}/api/cameras/import to import all cameras.")
                return True
            print(f"\n❌ Token exchange failed: {resp}")
            return False
    except Exception as exc:
        print(f"\n❌ Gateway error: {exc}")
        return False


def main():
    ap = argparse.ArgumentParser(description="Extract YI id_token from HTTP Toolkit capture")
    ap.add_argument("--har", help="Path to .har file exported from HTTP Toolkit")
    ap.add_argument("--token", help="Paste the id_token directly (skip HAR)")
    ap.add_argument("--gateway", default=GW_DEFAULT, help="Gateway URL")
    ap.add_argument("--watch", action="store_true",
                    help="Watch Downloads folder for new .har files")
    args = ap.parse_args()

    if args.token:
        print(f"Using manually provided token ({args.token[:40]}...)")
        post_to_gateway(args.token, args.gateway)
        return

    har_path = Path(args.har) if args.har else None

    if args.watch:
        print("Watching for new .har files in Downloads... (Ctrl+C to stop)")
        print("Tip: In HTTP Toolkit → File → Export → Save as HAR")
        seen = set(p.name for d in _SEARCH_DIRS if d.exists() for p in d.glob("*.har"))
        while True:
            time.sleep(2)
            for d in _SEARCH_DIRS:
                if not d.exists():
                    continue
                for p in d.glob("*.har"):
                    if p.name not in seen:
                        print(f"\nNew HAR: {p}")
                        seen.add(p.name)
                        har_path = p
                        break
            if har_path:
                break

    if not har_path:
        har_path = find_latest_har()

    if not har_path or not har_path.exists():
        print("No .har file found.")
        print("\nIn HTTP Toolkit: File → Export HAR → Save to Downloads")
        print("Or run: python extract_yi_token.py --token eyJ...")
        sys.exit(1)

    print(f"Parsing: {har_path}")
    found = extract_from_har(har_path)

    if not found:
        print("Nothing found in HAR. Make sure you signed into YI app while intercepting.")
        sys.exit(1)

    print("\n── Captured ──────────────────────────────────")
    for k, v in found.items():
        display = v[:60] + "..." if len(str(v)) > 63 else v
        print(f"  {k}: {display}")

    if "google_client_id" in found:
        print(f"\n💡 Google client_id found: {found['google_client_id']}")
        print("   Set env var YI_GOOGLE_CLIENT_ID to enable future auto-login.")

    if "yi_token" in found:
        print(f"\n✅ YI session token captured directly from traffic!")
        print("   No exchange needed — importing cameras now...")
        # Post the YI token directly
        try:
            import urllib.request
            body = json.dumps({
                "token": found["yi_token"],
                "user_id": found.get("yi_user_id", "")
            }).encode()
            req = urllib.request.Request(
                f"{args.gateway}/api/cloud/inject-session",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                print(json.loads(r.read()))
        except Exception:
            pass
    elif "id_token" in found:
        post_to_gateway(found["id_token"], args.gateway)
    else:
        print("\nNo id_token found. Try exporting HAR after signing into YI app.")


if __name__ == "__main__":
    main()
