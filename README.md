# CamControl

CamControl is a self-hosted camera gateway and Flutter app for
owner-authorized camera management. It supports gateway and direct-camera
profiles, snapshots, recordings, motion status, and configurable live-view
refresh intervals.

## Download

- [Download the latest Android APK](https://github.com/jwgmpi-wolff/camcontrol/releases/download/latest/app-release.apk)
- [View the latest release](https://github.com/jwgmpi-wolff/camcontrol/releases/tag/latest)

The APK is built from `main` by GitHub Actions and published to the stable
`latest` release.

## Architecture

```text
Flutter app ---- HTTP ----> FastAPI gateway ---- SSH/RTSP ----> Cameras
     |
     +---- direct HTTP ---------------------------------------> Cameras
```

- **Gateway mode** connects the app to the Python API on port `21416`.
- **Direct mode** loads camera-hosted live views without the gateway UI.
- Camera tiles continuously monitor feed health and report **Live**,
  **Stalled** (the image has stopped changing), or **Offline** (updates have
  timed out or repeatedly failed). Stalled and offline feeds hide the last
  image so old footage cannot be mistaken for a current view.
- The app refresh button sends a refresh request to the gateway, invalidates
  cached relay snapshots, and waits for new camera uploads before showing
  footage again.
- The gateway can capture images, publish camera live-view pages, record video,
  report motion status, and route captures to configured storage.

## Connection URLs

Gateway and direct-camera profiles use different URLs:

- **Gateway mode:** enter the FastAPI gateway URL, for example
  `http://192.168.1.20:21416`. Port `21416` is the gateway API port; it is not the
  camera live-view address.
- **Direct-camera mode:** enter the camera address or its complete live-view
  URL, for example `192.168.1.50` or `http://192.168.1.50/live.html`.

To view a camera directly in a browser, open:

```text
http://<camera-address>/live.html
```

The app retrieves refreshed images from:

```text
http://<camera-address>/live.jpg?t=<timestamp>
```

The query parameter prevents a browser or proxy from returning a cached image.
If the camera web server is exposed on a non-default port, include that port
before the path, for example `http://camera.example.net:8081/live.html`.

## Run The Gateway On Windows

Prerequisites: Python 3.10 or newer and Git.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m camera_bridge.main
```

The API listens on `http://0.0.0.0:21416` by default. Verify it locally:

```powershell
Invoke-RestMethod http://127.0.0.1:21416/api/health
```

Optional environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | Gateway bind address |
| `PORT` | `21416` | Gateway port |
| `API_KEY` | unset | Protect administrative API operations when set |

Camera settings are stored in the gitignored `config/cameras.json`. Configure
cameras in the app instead of committing camera addresses or credentials.

## Keep The LAN Relay Running On Windows

Constrained cameras send snapshots to the LAN relay on TCP port `21417`, and
the relay forwards them to the Azure gateway. Install it as a boot-time SYSTEM
task from an elevated PowerShell window:

```powershell
.\scripts\install-lan-relay.ps1
```

The installer creates a local-subnet-only firewall rule, starts the relay at
Windows boot, retries it after failures, and checks every five minutes that
the task is still running. Relay logs are written to `logs\lan-relay.log`.

Verify each hop:

```powershell
Invoke-RestMethod http://127.0.0.1:21417/api/health
Invoke-RestMethod https://camcontrol-wolff.azurewebsites.net/api/health
```

The local response reports whether each camera is reaching and forwarding
through the relay. The Azure response reports `feeds_live`, `feeds_expected`,
and `all_feeds_live`. A powered camera light does not imply a live feed; only
recent successful snapshot delivery does. GitHub Actions also checks this
Azure health signal every five minutes in the **Monitor production camera
feeds** workflow.

## Install The Android App

1. Open the [latest APK download](https://github.com/jwgmpi-wolff/camcontrol/releases/download/latest/app-release.apk).
2. Allow your browser to install unknown apps when Android prompts you.
3. Install CamControl.
4. Open **Settings** and configure a gateway or direct-camera profile.

Android permits an in-place update only when both APKs use the same signing
certificate. If Android reports an incompatible signature, uninstall the old
development build before installing this release. Uninstalling clears saved
app profiles.

## Build The Android App

Prerequisites: Flutter stable, Android SDK, and Java 17.

```powershell
Push-Location ui
flutter pub get
flutter test
flutter build apk --release
Pop-Location
```

The APK is written to:

```text
ui/build/app/outputs/flutter-apk/app-release.apk
```

## Test The Gateway

```powershell
.\.venv\Scripts\python.exe -m compileall -q src tests
.\.venv\Scripts\python.exe -m pytest -q
```

## Project Layout

```text
camcontrol/
|-- .github/workflows/build-apk.yml  Android release workflow
|-- config/                          Local camera and user configuration
|-- src/camera_bridge/               FastAPI gateway and camera backends
|-- tests/                           Python tests
`-- ui/                              Flutter application
```

Report problems through [GitHub Issues](https://github.com/jwgmpi-wolff/camcontrol/issues).