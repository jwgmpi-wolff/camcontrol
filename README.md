# CamControl — YI Camera Platform

Owner-authorized camera management platform for YI Outdoor cameras. Streams all cameras to your own infrastructure — no YI app dependency at runtime.

## Downloads

| Platform | File | Size |
|----------|------|------|
| **Windows** (no install needed) | [⬇ CamControl-Windows.zip](https://github.com/jwgmpi-wolff/AppsandScripts/releases/download/v1.0/CamControl-Windows.zip) | 21 MB |
| **Windows** (source + bat files, safer) | [⬇ CamControl-Windows-Full.zip](https://github.com/jwgmpi-wolff/AppsandScripts/releases/download/v1.0/CamControl-Windows-Full.zip) | 16 MB |
| **Android APK** | [⬇ CamControl-Android.apk](https://github.com/jwgmpi-wolff/AppsandScripts/releases/download/v1.0/CamControl-Android.apk) | 14 KB |
| **All releases** | [GitHub Releases →](https://github.com/jwgmpi-wolff/AppsandScripts/releases) | |

> **Android (no APK):** Open Chrome → `http://[your-pc-ip]:8080/` → ⋮ → **Add to Home Screen** — installs as full-screen PWA instantly.

---

## What it does

- **Live multi-camera dashboard** at `http://localhost:8080/` — HLS video grid for all YI cameras
- **No YI app required** — authenticates directly via Google Sign-In → YI cloud API
- **Your own CDN** — streams via ffmpeg → HLS → any browser or device on your network
- **Camera WiFi QR** — add new cameras to WiFi without the YI app
- **Android APK** — native WebView app that connects to the dashboard on your local network

**Cameras pre-registered:** Camera (`10.0.0.248`), back door (`10.0.0.252`), Kitchen (`10.0.0.141`)

---

## Quick Start — Windows

### Option A: Standalone EXE (no Python needed)
1. [⬇ Download CamControl-Windows.zip](https://github.com/jwgmpi-wolff/AppsandScripts/releases/download/v1.0/CamControl-Windows.zip)
2. Extract ZIP → double-click `CamControl.exe` → gateway starts → browser opens at `http://localhost:8080/`

### Option B: From source
```powershell
# One-time setup (run as Administrator):
.\Install-CamControl.ps1

# Launch every time:
.\Start-CamControl.bat
```

---

## Quick Start — Android

### Option A: Install APK
1. [⬇ Download CamControl-Android.apk](https://github.com/jwgmpi-wolff/AppsandScripts/releases/download/v1.0/CamControl-Android.apk)
2. Enable *Install unknown apps* in Android settings → install and open
3. Enter your PC's IP when prompted (e.g. `http://10.0.0.112:8080/`)

### Option B: PWA — no APK required
1. Start CamControl on your PC
2. On any Android phone on the same WiFi → Chrome → `http://[pc-ip]:8080/`
3. Tap **⋮ → Add to Home Screen** → full-screen app installed

---

## Architecture

```
YI Camera (WiFi) ──ThroughTek P2P──▶ go2rtc ──RTSP──▶ ffmpeg ──HLS──▶ Dashboard
                                                                         │
                                                              Android / PC browser
```

**API host:** `gw-us.xiaoyi.com`  
**Auth:** Google OAuth (`/v4/auth/login`) → session token + HMAC signing  
**Streaming:** go2rtc Kalay P2P → RTSP → ffmpeg → HLS at `/streams/hls/`

---

## Files

```
camcontrol/
├── Start-CamControl.bat        ← Windows launcher (double-click)
├── Install-CamControl.ps1      ← First-time setup (run as Admin)
├── CamControl.spec             ← PyInstaller spec for building EXE
├── cameras.json                ← 3 cameras pre-registered
├── tools/
│   ├── go2rtc.exe              ← Stream proxy (Kalay P2P → RTSP)
│   └── go2rtc.yaml             ← Camera stream config
├── camera-platform/
│   ├── dashboard.html          ← Web UI (served at localhost:8080/)
│   └── static/                 ← hls.js, qrcode.js, PWA icons/manifest
├── src/camera_bridge/          ← Python FastAPI gateway
│   ├── api.py                  ← REST API + bindkey/stream endpoints
│   ├── yi_cloud.py             ← YI cloud auth (Google OAuth, real client ID)
│   ├── stream_manager.py       ← ffmpeg HLS engine (N cameras)
│   └── registry.py             ← Camera database
└── android/                    ← Android APK source (WebView wrapper)
    └── app/src/main/java/.../MainActivity.java
```

---

## Build from source

**Windows EXE:**
```powershell
pip install pyinstaller
pyinstaller CamControl.spec --distpath dist
# → dist\CamControl.exe
```

**Android APK:**
```bash
cd android && ./gradlew assembleDebug
# → app/build/outputs/apk/debug/app-debug.apk
```

GitHub Actions builds both automatically on every push to `main` and attaches them to the [latest release](https://github.com/jwgmpi-wolff/AppsandScripts/releases/latest).
