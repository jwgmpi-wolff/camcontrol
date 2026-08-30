"""Download yi-hack-allwinner-v2 firmware and stage it for SD card flashing."""
import json, os, shutil, socket, tarfile, urllib.request

# yi-hack-Allwinner-v2 by roleoroleo — supports Yi Outdoor 1080p (YHS.3017)
# Model codes: h30ga (IFUS/RFUS serial prefix) or r40ga (QFUS serial prefix)
REPO_API  = "https://api.github.com/repos/roleoroleo/yi-hack-Allwinner-v2/releases/latest"
STAGE_DIR = os.path.join(os.path.dirname(__file__), "..", "flash-staging")
CFG_DIR   = os.path.join(os.path.dirname(__file__), "..", "flash-config")
DL_DIR    = os.path.join(os.environ.get("TEMP", "/tmp"), "yi-hack-download")

# Serial number prefix -> model code mapping for YI Outdoor 1080p
OUTDOOR_MODELS = ["h30ga", "r40ga", "r35gb"]

def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.0.0.1", 1))
        return s.getsockname()[0]
    finally:
        s.close()

GATEWAY_IP = local_ip()

print("=== YI Hack Firmware Downloader ===")
print(f"  Gateway IP : {GATEWAY_IP}")
print(f"  Stage dir  : {os.path.abspath(STAGE_DIR)}")

# ── 1. Fetch release metadata ────────────────────────────────────────────────
print("\n[1/4] Fetching latest release info...")
req = urllib.request.Request(REPO_API, headers={"User-Agent": "camcontrol-flasher"})
with urllib.request.urlopen(req, timeout=15) as r:
    release = json.loads(r.read())

tag = release["tag_name"]
print(f"      Tag: {tag}")

# Find outdoor model assets — prefer h30ga (most common outdoor 1080p)
assets = release.get("assets", [])
print(f"      All assets: {[a['name'] for a in assets]}")
asset = next((a for a in assets if any(m in a["name"] for m in OUTDOOR_MODELS)), None)
if not asset:
    # Fall back to any zip
    asset = next((a for a in assets if a["name"].endswith(".zip")), None)
if not asset:
    raise RuntimeError("No zip asset found. Check https://github.com/roleoroleo/yi-hack-Allwinner-v2/releases")

print(f"      Asset: {asset['name']}  ({asset['size']//1024//1024} MB)")

# ── 2. Download ───────────────────────────────────────────────────────────────
os.makedirs(DL_DIR, exist_ok=True)
zip_path = os.path.join(DL_DIR, asset["name"])

if os.path.exists(zip_path) and os.path.getsize(zip_path) == asset["size"]:
    print("\n[2/4] Already downloaded — skipping.")
else:
    print(f"\n[2/4] Downloading {asset['name']}...")
    def reporthook(count, block, total):
        pct = min(100, int(count * block * 100 / total))
        if count % 50 == 0:
            print(f"      {pct}%", end="\r", flush=True)
    urllib.request.urlretrieve(asset["browser_download_url"], zip_path, reporthook)
    print(f"\n      Download complete: {zip_path}")

# ── 3. Extract ────────────────────────────────────────────────────────────────
print(f"\n[3/4] Extracting to staging area...")
if os.path.exists(STAGE_DIR):
    shutil.rmtree(STAGE_DIR)
os.makedirs(STAGE_DIR, exist_ok=True)

with tarfile.open(zip_path, "r:gz") as t:
    t.extractall(STAGE_DIR)

# yi-hack-Allwinner-v2 archives extract as: Factory/, yi-hack/, lower_half_init.sh
# The whole archive root IS the SD card content — no extra flattening needed
entries = os.listdir(STAGE_DIR)
print(f"      Top-level  : {entries}")
flash_root = STAGE_DIR  # copy everything to SD root

print(f"      Flash root : {flash_root}")

# List what's in there
files = []
for root, dirs, fnames in os.walk(flash_root):
    for fn in fnames:
        files.append(os.path.relpath(os.path.join(root, fn), flash_root))
print(f"      Files      : {len(files)} total")
for f in sorted(files)[:20]:
    print(f"        {f}")
if len(files) > 20:
    print(f"        ... and {len(files)-20} more")

# ── 4. Write yi.cfg ───────────────────────────────────────────────────────────
print(f"\n[4/4] Writing yi.cfg (gateway={GATEWAY_IP})...")

# yi-hack-Allwinner-v2: config is set via web UI after flashing.
# We write a reference file and the WiFi credentials file.
yi_cfg = f"""# yi-hack-Allwinner-v2 post-flash settings reference
# After flashing, open http://10.0.0.161 and apply these settings:
#
# System > Hostname       : yicam-wolff
# Streaming > RTSP        : enabled, port 554
# Streaming > RTSP auth   : disabled (or set user/pass)
# System > SSH            : enabled
# System > HTTP           : enabled, port 80
# MQTT > Host             : {GATEWAY_IP}
# MQTT > Port             : 1883
# MQTT > Topic prefix     : yicam/yhs3017
# Cloud > Disable cloud   : YES
#
# RTSP URLs after flashing:
#   rtsp://10.0.0.161/ch0_0.h264   (high res 1080p)
#   rtsp://10.0.0.161/ch0_1.h264   (low res)
"""

for dest_dir in [flash_root, CFG_DIR]:
    os.makedirs(dest_dir, exist_ok=True)
    with open(os.path.join(dest_dir, "yi.cfg"), "w") as f:
        f.write(yi_cfg)

print(f"      yi.cfg written to flash root and flash-config/")
print()
print("=== READY ===")
print(f"  Firmware staged at: {os.path.abspath(flash_root)}")
print()
print("  *** IMPORTANT: Check your camera serial number first 4 letters:")
print("    IFUS or RFUS -> use h30ga firmware (most common outdoor 1080p)")
print("    QFUS         -> use r40ga firmware")
print()
print("  To write to SD card, run:")
print("    .\\prep-flash-sd.ps1 -SdDrive E   (replace E with your SD card letter)")
print()
print("  After flashing (SD card STAYS IN the camera):")
print("    RTSP (high): rtsp://10.0.0.161/ch0_0.h264")
print("    RTSP (low) : rtsp://10.0.0.161/ch0_1.h264")
print("    HTTP admin : http://10.0.0.161")
print("    SSH        : ssh root@10.0.0.161  (pass: root)")
print()
print("  Then in the dashboard: paste rtsp://10.0.0.161/ch0_0.h264 -> Use This URL")
