# Security Notes

## What this project does not do

- Does not modify, flash, or replace camera firmware or bootloaders.
- Does not bypass YI cloud controls, app authentication, or vendor software.
- Does not extract or transmit camera vendor credentials.
- Does not upload raw continuous video to Azure IoT Hub.

## Secrets and credentials

- Store `IOTHUB_DEVICE_CONNECTION_STRING`, `STREAM_USERNAME`, and
  `STREAM_PASSWORD` in environment variables or an untracked `.env` file.
- When running as an IoT Edge module, inject secrets via Edge module environment
  variables in the Azure portal — never in `deployment.template.json`.
- Rotate IoT Hub SAS keys and RTSP passwords on a regular schedule.
- Consider replacing SAS-key connection strings with X.509 certificate
  authentication for production Edge devices.

## Network exposure

- `STREAM_ENABLED` defaults to `false`. Enable RTSP only when required and only
  on a trusted private network, VPN, or behind a reverse proxy with TLS.
- Never expose RTSP port 8554 directly to the public internet.
- Restrict the container's host network binding to a loopback or VLAN interface
  if the edge host is multi-homed.
- Use an nginx or Caddy TLS reverse proxy if the stream must traverse an
  untrusted segment.

## Direct method access control

- All incoming direct method calls are logged as `directMethodAudit` telemetry
  events, including method name and HTTP-equivalent status.
- Restrict which principals can invoke direct methods using IoT Hub shared
  access policies (service role, least privilege).

## Container security

- The Dockerfile runs as the default non-root `python:3.12-slim` process;
  do not add `--privileged` unless required by the USB host driver.
- Use `--device /dev/video0` to scope device access to the camera only.
- Mount the snapshot directory as a named volume, not a bind mount to a
  sensitive host path.

## Dependency updates

- Pin all dependencies in `requirements.txt` and audit them with
  `pip audit` before each release.
