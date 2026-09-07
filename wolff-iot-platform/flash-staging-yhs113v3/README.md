# Flash staging -- YI Home Camera (YHS-113-IR), attempt 2: yi-hack-v3 (y18)

## Why this exists

The originally-planned mechanism for this camera, the **fritz-smh/yi-hack**
project (see [../flash-staging-yhs113](../flash-staging-yhs113)), does not
work on this specific unit -- confirmed by matching, unresolved upstream
reports for this exact model:

- [fritz-smh/yi-hack#217 "YI YHS-113-IR unable to flash"](https://github.com/fritz-smh/yi-hack/issues/217)
  -- identical symptom to ours ("waiting to connect" voice/LED, SD card
  never touched by the camera).
- [fritz-smh/yi-hack#228 "Not working on 2018 model - YHS-113-IR"](https://github.com/fritz-smh/yi-hack/issues/228)
  -- confirms Xiaoyi patched out the internal factory-test hook this hack
  depends on in later production firmware. This is a firmware-version
  incompatibility, not a config or SD card problem.
- The same #217 thread also reports success switching to **shadow-1's
  yi-hack-v3** on this exact camera: a working web UI, but no built-in RTSP
  (same known limitation already accepted for camera #1/#2).

## Identification

- Model: **YHS-113-IR** -- per our own project notes, "the original ~2014
  Yi Home / Yi Ants camera". shadow-1/yi-hack-v3's release 0.1.6 lists
  "Yi Home 17CN / 27US / 47US" as supported, using the `rootfs_y18` /
  `home_y18` firmware pair -- this is the correct match for this camera
  generation (as distinct from `_h30`, the Yi Outdoor pair already used for
  camera #1/#2).

## This is a real flash, like camera #1/#2

Unlike the fritz-smh mechanism, this **writes to the camera's internal
flash** the same way camera #1/#2 were flashed. The SD card does not need
to stay in the camera afterward.

## Contents

- `sdcard/rootfs_y18`, `sdcard/home_y18` -- downloaded verbatim from
  `shadow-1/yi-hack-v3` release `0.1.6`.
  - `rootfs_y18`: 962,400 bytes,
    sha256 `66ACA8F218AAC1532D9EF8F8725DCF1F9223DA40A900DA933CDA4D2516C36FD7`
  - `home_y18`: 6,984,664 bytes,
    sha256 `126CB1A99342A122C0D0FE0207FC0003746DDA89718A4EC73EA8B229CD2FC2CB`

## Procedure

1. Format a microSD card (16GB or less recommended) as **FAT32** (not
   exFAT), with a real MBR partition table and a single active partition
   -- some cards/readers leave a stray second partition from prior use,
   which can prevent the camera's simple loader from recognizing the card.
2. Copy `sdcard/rootfs_y18` and `sdcard/home_y18` to the **root** of the
   card (no subfolders).
3. Eject the card, power off the camera, insert the card, power the camera
   back on.
4. Watch for the yellow LED to flash for ~30 seconds -- that's the
   firmware writing. The camera will then boot normally.
5. Find the camera's new IP (router DHCP list) and open it in a browser to
   confirm the custom firmware's web UI loads.

## Known limitation

Per the upstream report, this firmware variant is not confirmed to expose a
built-in RTSP/ONVIF restreamer on this camera either. Verify what local
streaming/access is actually available (web UI "About" page, SSH) before
wiring it into CamControl's capture pipeline the same way camera #1/#2 use
the `/tmp/view` SSH capture fallback.
