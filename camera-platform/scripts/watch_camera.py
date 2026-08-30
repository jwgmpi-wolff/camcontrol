"""
Camera online watcher — polls 10.0.0.161:8000 and auto-connects the gateway
the moment the camera appears. Run this while setting up via YI app.
"""
import socket
import time
import urllib.request
import json

CAMERA_IP = "10.0.0.248"
CAMERA_PORT = 8000
GATEWAY = "http://localhost:8080"
POLL_INTERVAL = 3  # seconds


def camera_up() -> bool:
    s = socket.socket()
    s.settimeout(1)
    try:
        r = s.connect_ex((CAMERA_IP, CAMERA_PORT))
        return r == 0
    finally:
        s.close()


def set_gateway_camera(ip: str) -> bool:
    try:
        body = json.dumps({"ip": ip, "qr": ""}).encode()
        req = urllib.request.Request(
            f"{GATEWAY}/api/camera/register-qr",
            data=body, headers={"Content-Type": "application/json"}, method="POST"
        )
        r = urllib.request.urlopen(req, timeout=8)
        data = json.loads(r.read())
        print(f"  Gateway registered: {data.get('note', 'ok')}")
        return True
    except Exception as e:
        print(f"  Gateway error: {e}")
        return False


def main() -> None:
    print("=" * 55)
    print("  YI Camera Online Watcher")
    print(f"  Watching {CAMERA_IP}:{CAMERA_PORT}")
    print("=" * 55)
    print()
    print("  1. Open the YI Home (or YI IoT) app on your phone")
    print("  2. Tap + → Add Device → follow setup for YHS.3017")
    print("  3. App will show the QR code; point camera at it")
    print("  4. Camera connects → this script detects it automatically")
    print()
    print("Watching for camera... (Ctrl+C to stop)")

    was_up = False
    while True:
        up = camera_up()
        if up and not was_up:
            print(f"\n✅ CAMERA ONLINE at {CAMERA_IP}:{CAMERA_PORT}!")
            print("  Registering with gateway...")
            set_gateway_camera(CAMERA_IP)
            print("  Dashboard: http://localhost:8080/api/camera/yi-probe?ip=" + CAMERA_IP)
            print("  Snapshot:  http://localhost:8080/api/camera/yi-snapshot?ip=" + CAMERA_IP)
        elif not up and was_up:
            print(f"\n⚠  Camera went offline — may be rebooting or resetting")
        elif not up:
            print(".", end="", flush=True)

        was_up = up
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nWatcher stopped.")
