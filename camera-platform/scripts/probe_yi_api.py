"""Probe YI/Kami Home API endpoints with captured session HMAC."""
import subprocess

Q = "hmac=0zLfYnrDo4yqvvw4571Ia1zCUJo=&userid=201393&seq=1"
UA = "yihome/6.9.2_20260522071155"
BASE = "https://gw-us.xiaoyi.com"
CURLH = ["-A", UA,
         "-H", "x-kamihome-appType: ANDROID",
         "-H", "x-xiaoyi-appCountryCode: US",
         "-H", "x-kamihome-packageType: RELEASE"]

# HMAC confirmed session-level: same token works for any path
# Now searching for home/device list endpoints
PATHS = [
    # User-scoped device paths
    "/v4/users/home", "/v4/users/homeList", "/v4/users/homes",
    "/v4/users/device", "/v4/users/devices", "/v4/users/camera",
    "/v4/users/device/list", "/v4/users/homeInfo",
    "/v8/users/home", "/v8/users/homes",
    # Home-first patterns  
    "/v4/home", "/v8/home",
    "/v4/home/0/device/list", "/v4/home/1/device/list",
    "/v4/home/device", "/v4/home/deviceList",
    "/cms/v8/home/list", "/cms/v8/device/list",
    # User ID as path param
    "/v4/users/201393/home", "/v4/users/201393/device",
    # Kami/cove specific (app was rebranded)
    "/v4/kami/device/list", "/v8/kami/device",
    "/cove/v8/device/list",
    # Push-related (we see push/v8/bind in traffic)
    "/push/v8/device/list", "/push/v8/bind/list",
    # Alternative versioning
    "/v7/home/device/list", "/v9/home/device/list",
    "/v7/users/home", "/v9/users/home",
    # Lowercase device
    "/v4/device", "/v8/device",
    "/v4/device/query", "/v8/device/query",
]

print(f"Probing {len(PATHS)} paths with session HMAC...")
hits = []
for p in PATHS:
    r = subprocess.run(["curl", "-sk"] + CURLH + [f"{BASE}{p}?{Q}"],
                       capture_output=True, text=True, timeout=10)
    out = r.stdout.strip()
    is_hit = "404" not in out and "Not Found" not in out and len(out) > 10
    if is_hit:
        print(f"✓ HIT {p}: {out[:150]}")
        hits.append(p)
    else:
        print(f"✗ {p}")

print(f"\n{len(hits)} hits found")

