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

- **Gateway mode** connects the app to the Python API on port `8080`.
- **Direct mode** loads camera-hosted live views without the gateway UI.
- The gateway can capture images, publish camera live-view pages, record video,
  report motion status, and route captures to configured storage.

## Run The Gateway On Windows

Prerequisites: Python 3.10 or newer and Git.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m camera_bridge.main
```

The API listens on `http://0.0.0.0:8080` by default. Verify it locally:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/api/health
```

Optional environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | Gateway bind address |
| `PORT` | `8080` | Gateway port |
| `API_KEY` | unset | Protect administrative API operations when set |

Camera settings are stored in the gitignored `config/cameras.json`. Configure
cameras in the app instead of committing camera addresses or credentials.

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