#Requires -Version 5.1
<#
.SYNOPSIS
  Stage the correct Hi3518e yi-hack-v3 firmware (rootfs_h30 / home_h30) onto a
  FAT32 microSD card for this specific camera (YI Outdoor 1080p, YHS.3017).

.DESCRIPTION
  This script only prepares the microSD card. Removing the card from the
  camera, inserting it into this PC, and re-inserting it into the camera to
  power-cycle are manual physical steps that must be done by hand.

  Safety checks performed before any copy:
    - Destination drive must exist and be removable (SD card / USB reader).
    - Destination filesystem must be FAT32 (exFAT is rejected by the loader).
    - Destination must NOT already contain an Allwinner-v2 layout
      (Factory/ or yi-hack/ folders) -- mixing firmware families for two
      different chipsets on one card is a bricking risk.
    - Source firmware files must match the pinned SHA-256 in yi.cfg exactly.

.PARAMETER DriveLetter
  The drive letter of the mounted microSD card, e.g. "E".

.EXAMPLE
  .\Stage-YiH30Firmware.ps1 -DriveLetter E
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[D-Zd-z]$')]
    [string]$DriveLetter
)

$ErrorActionPreference = 'Stop'

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$sdcardSrc  = Join-Path $scriptRoot 'sdcard'
$cfgPath    = Join-Path (Split-Path -Parent $scriptRoot) 'flash-config\yi.cfg'

$expected = @{
    rootfs_h30 = '07BD22B4DCAB90C40AEEA0DEFD5DFEADAFE206317A77CB2A799F026122B68E12'
    home_h30   = '3E76577F528BBA0A8FB32A4DCF86A614EF9E732FCE21D9418A31EEC228202181'
}

if (-not (Test-Path $cfgPath)) {
    throw "Missing $cfgPath -- refusing to stage firmware without its pinned config."
}

foreach ($name in $expected.Keys) {
    $srcFile = Join-Path $sdcardSrc $name
    if (-not (Test-Path $srcFile)) {
        throw "Missing source firmware file: $srcFile"
    }
    $actual = (Get-FileHash -Path $srcFile -Algorithm SHA256).Hash
    if ($actual -ne $expected[$name]) {
        throw "Checksum mismatch for $name. Expected $($expected[$name]) but got $actual. Refusing to stage a firmware file that does not match the pinned, verified release asset."
    }
    Write-Host "Verified $name (sha256 OK)" -ForegroundColor Green
}

$drive = "$($DriveLetter):"
$volume = Get-Volume -DriveLetter $DriveLetter -ErrorAction SilentlyContinue
if (-not $volume) {
    throw "Drive $drive not found. Insert the microSD card into this PC and confirm the drive letter."
}
if ($volume.FileSystem -ne 'FAT32') {
    throw "Drive $drive is formatted as '$($volume.FileSystem)', not FAT32. Reformat the card as FAT32 before continuing (exFAT will not be recognized by the camera's firmware loader)."
}

$diskDrive = Get-Partition -DriveLetter $DriveLetter -ErrorAction SilentlyContinue |
    Get-Disk -ErrorAction SilentlyContinue
if ($diskDrive -and $diskDrive.BusType -eq 'NVMe') {
    throw "Drive $drive resolves to an NVMe-attached disk, not a removable SD card. Refusing to continue as a safety guard against writing to the wrong disk."
}

$staleAllwinnerMarkers = @('Factory', 'yi-hack') | ForEach-Object { Join-Path $drive $_ }
$found = $staleAllwinnerMarkers | Where-Object { Test-Path $_ }
if ($found) {
    throw "Drive $drive already contains an Allwinner-v2 layout ($($found -join ', ')). This card was previously prepared for a different chipset family. Erase the card fully before staging the Hi3518e (rootfs_h30/home_h30) firmware to avoid a mixed/bricking flash."
}

foreach ($name in $expected.Keys) {
    $srcFile = Join-Path $sdcardSrc $name
    $dstFile = Join-Path $drive $name
    Copy-Item -Path $srcFile -Destination $dstFile -Force
    Write-Host "Copied $name -> $dstFile" -ForegroundColor Green
}

Write-Host "`nSD card staged. Remaining manual steps:" -ForegroundColor Cyan
Write-Host "  1. Safely eject drive $drive from this PC."
Write-Host "  2. Power off the camera, insert the microSD card, power the camera back on."
Write-Host "  3. Watch for the yellow LED to flash for ~30 seconds (firmware writing)."
Write-Host "  4. Find the camera's IP (e.g. via router DHCP list) and open it in a browser to confirm the yi-hack-v3 web UI loads."
