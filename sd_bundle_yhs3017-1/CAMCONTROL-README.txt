CamControl SD card bundle
=========================

Reconfigure an already-provisioned camera:
  1. Copy camcontrol.conf to the root of a FAT32 card.
  2. Power the camera off, insert the card, power it on.
  3. The settings are imported and applied during boot, then the
     file is renamed to camcontrol.conf.applied so a card left in
     the slot stops overriding later changes.

First-time install with no boot hook yet (needs shell access):
  STAGE_DIR=/tmp/sd/camcontrol-install sh /tmp/sd/camcontrol-install/install.sh

This file contains no credentials. camcontrol.conf does -- erase
the card once the camera has booted.
