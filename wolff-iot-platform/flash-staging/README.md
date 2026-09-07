# Flash staging -- Hi3518e YI Outdoor 1080p (YHS.3017)

This camera was confirmed to be the **HiSilicon Hi3518e V200** chipset family
(see [../flash-config/yi.cfg](../flash-config/yi.cfg) for the identification
evidence), so it uses the **shadow-1 Hi3518e custom firmware** (`yi-hack-v3`
upstream), not the Allwinner-targeted alternative firmware project. Do not
mix the two -- flashing the wrong family's image onto this camera risks
bricking it.

## Contents

- `sdcard/rootfs_h30`, `sdcard/home_h30` -- the two firmware files, downloaded
  verbatim from the shadow-1 project's release `0.1.6`. Checksums are pinned in
  `../flash-config/yi.cfg` and re-verified by the staging script below.
- `Stage-YiH30Firmware.ps1` -- copies the two files onto a FAT32 microSD card
  after verifying checksums, filesystem, and that the card isn't already
  carrying a stale Allwinner-targeted layout.

## Procedure

1. Format a microSD card (16GB or less recommended) as **FAT32** (not exFAT).
2. Insert it into this PC and note its drive letter.
3. Run:
   ```powershell
   .\Stage-YiH30Firmware.ps1 -DriveLetter E
   ```
4. Eject the card, power off the camera, insert the card, power the camera
   back on.
5. Watch for the yellow LED to flash for ~30 seconds -- that's the firmware
   writing. The camera will then boot normally.
6. Find the camera's new IP (router DHCP list) and open it in a browser to
   confirm the custom firmware's web UI loads.

## Known limitation

This firmware's documented feature set (SSH, Telnet, FTP, local web UI,
proxychains-ng) does not include a confirmed built-in RTSP/ONVIF restreamer
the way the Allwinner-targeted alternative firmware does. After flashing,
verify what local streaming/access is actually available before wiring it into
CamControl's capture pipeline -- don't assume `rtsp://<ip>/ch0_0.264` works here.
