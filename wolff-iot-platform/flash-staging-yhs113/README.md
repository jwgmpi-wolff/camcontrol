# Flash staging -- YI Home Camera (YHS-113-IR)

This is a **different camera** from the YI Outdoor (YHS.3017) already flashed
in [../flash-staging](../flash-staging). It uses a **different third-party
firmware project** and a fundamentally different (safer) install mechanism.

## Identification

- Model: **YHS-113-IR**, FCC ID `2AFIB-H1500A`, CMIIT ID `2014DP4828`
  (Shanghai Xiaoyi Technology Co., Ltd.) -- the original ~2014 "Yi Home /
  Yi Ants" camera.
- The shadow-1 Hi3518e custom firmware project (used for the other camera)
  has **never** supported this model -- confirmed by checking every release
  (0.1.0 through 0.1.6): no unsuffixed `rootfs`/`home` assets exist in any
  release, and plain "Yi Home" is never listed as supported.
- The correct project for this hardware is the original fritz-smh custom
  firmware project (`github.com/fritz-smh/yi-hack`), built specifically for
  this camera. Confirms the same Hi3518 SoC family
  (`cd /home/3518; ./load3518_left`).

## How this mechanism differs from the other camera

- **No internal flash write.** The modified `home` firmware image loads
  from the SD card into RAM at each boot; nothing is permanently written
  to the camera's internal storage.
- **The SD card must stay in the camera.** Remove it and the camera boots
  back to 100% original/stock behavior immediately -- this is fully and
  instantly reversible, unlike a real flash.
- `equip_test.sh` self-detects which RTSP/HTTP server binary variant to run
  by reading the *bundled* `home` image's own version string at runtime, so
  bundling only the matching variant (here: `M`) is self-consistent and
  correct -- it does not depend on knowing the camera's original factory
  firmware version in advance.

## Contents

- `sdcard/home` -- the "M" release firmware image from the fritz-smh project.
- `sdcard/test/rtspsvrM`, `sdcard/test/http/serverM` -- matching binaries.
- `sdcard/test/yi-hack.cfg` -- network config (filename fixed by
  `equip_test.sh`, do not rename). Already filled in:
  `IP=10.0.0.150`, `NETMASK=255.255.255.0`, `GATEWAY=10.0.0.1`,
  `NAMESERVER=10.0.0.1`.
- `sdcard/test/wpa_supplicant.conf` -- WiFi config. Already filled in:
  `ssid="wolffwifi"`.

## Required manual steps before use (secrets -- do not paste these into chat)

Open these two files yourself and replace the placeholders:

1. `sdcard/test/yi-hack.cfg` -- replace `ROOT_PASSWORD=REPLACE_WITH_YOUR_OWN_ROOT_PASSWORD`
   with a real password. Do not leave the stock default (`1234qwer`) or the
   placeholder in place.
2. `sdcard/test/wpa_supplicant.conf` -- replace
   `psk="REPLACE_WITH_YOUR_WIFI_PASSWORD"` with the actual WiFi password for
   `wolffwifi`.

## Procedure

1. Format a microSD card as **FAT32**.
2. Copy the contents of `sdcard/` to the root of the card.
3. Insert the card into the camera, then power it on.
4. Watch the LED: orange (startup) -> blue blinking (network config) ->
   blue solid (ready).
5. Browse to `http://10.0.0.150/` to confirm the custom firmware's status
   page loads.
6. **Leave the SD card in the camera permanently** -- removing it reverts
   to stock.

## After it's confirmed working

- RTSP: `rtsp://10.0.0.150:554/ch0_0.h264` (HD) or `ch0_1.h264` (low-res).
- Telnet on port 23 (`root` / the password you set above).
