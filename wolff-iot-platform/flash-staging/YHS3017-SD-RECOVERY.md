# YHS.3017 SD Recovery

Use this procedure only for the YI Outdoor 1080p **YHS.3017** cameras. It
installs the verified `yi-hack-v3` Hi3518e firmware pair (`rootfs_h30` and
`home_h30`) so that a new SSH password can be set and the CamControl uploader
can be installed.

Do not use this card with a YHS-113 or any other YI model.

## Prepare the card

1. Use a microSD card of 16 GB or less when possible. Back up anything on it.
2. Format it as FAT32 with one MBR partition. Do not use exFAT.
3. Insert the card into this PC and note its drive letter.
4. From the repository root, run:

   ```powershell
   .\wolff-iot-platform\flash-staging\Stage-YiH30Firmware.ps1 -DriveLetter E
   ```

   Replace `E` with the card's actual drive letter. The command validates both
   pinned firmware checksums, rejects a non-FAT32 card, and copies exactly two
   files to the card root: `rootfs_h30` and `home_h30`.

## Load the camera

Only load the card after the staging command reports both files copied without
an error.

1. Safely eject the card from Windows.
2. Disconnect power from one YHS.3017 camera.
3. Insert the prepared card, then restore power.
4. Watch for the yellow LED to flash for about 30 seconds. This indicates the
   internal firmware write. Do not remove power or the card during this time.
5. Allow the camera to finish booting, then find its DHCP address in the
   router's client list and open its local web UI.
6. Confirm SSH access and establish a unique root password before removing the
   card. Repeat with a freshly staged card for the second camera.

After SSH is restored, install the CamControl uploader through the normal
provisioning command. The recovery card contains no gateway or Wi-Fi secrets.