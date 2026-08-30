#!/usr/bin/env pwsh
#Requires -Version 5.1
<#
.SYNOPSIS
    Detects UVC-compatible USB cameras attached to this Windows host.
.DESCRIPTION
    Lists PnP camera devices and their USB VID/PID. Does not modify any
    device, firmware, or driver. Run as your own user account; elevation
    is not required for enumeration.
.EXAMPLE
    .\detect-usb-camera.ps1
    .\detect-usb-camera.ps1 -Verbose
#>

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Write-Verbose 'Querying PnP camera devices...'

$cameras = Get-PnpDevice -Class 'Camera' -Status OK -ErrorAction SilentlyContinue

if (-not $cameras) {
    Write-Warning 'No PnP Camera-class devices found in status OK.'
    exit 2
}

$results = foreach ($cam in $cameras) {
    $instanceId = $cam.InstanceId

    # Extract VID/PID from the instance ID (USB\VID_XXXX&PID_XXXX pattern)
    $vid = if ($instanceId -match 'VID_([0-9A-Fa-f]{4})') { $Matches[1] } else { 'N/A' }
    $pid_ = if ($instanceId -match 'PID_([0-9A-Fa-f]{4})') { $Matches[1] } else { 'N/A' }

    [PSCustomObject]@{
        FriendlyName = $cam.FriendlyName
        Status       = $cam.Status
        InstanceId   = $instanceId
        VID          = $vid
        PID          = $pid_
    }
}

$results | Format-Table -AutoSize

Write-Host "`nTo use a device with the camera-bridge, set CAMERA_DEVICE_PATH to its" -ForegroundColor Cyan
Write-Host "0-based OpenCV index (0, 1, 2 ...) matching the order in this list." -ForegroundColor Cyan
Write-Host "Run: python -m camera_bridge.main --detect-only" -ForegroundColor Cyan
