#Requires -Version 7
<#
.SYNOPSIS
    Start a local FFmpeg recording from a confirmed RTSP URL.
    The RTSP URL must already be verified reachable. This script never guesses credentials.
.PARAMETER RtspUrl
    Full RTSP URL including your credentials: rtsp://<user>:<pass>@<ip>:554/...
.PARAMETER OutputDir
    Local directory for segments. Defaults to .\recordings.
.PARAMETER SegmentMinutes
    Segment length in minutes. Defaults to 5.
#>
param(
    [Parameter(Mandatory)][string]$RtspUrl,
    [string]$OutputDir = ".\recordings",
    [int]$SegmentMinutes = 5
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Error "ffmpeg not found. Install FFmpeg and add it to PATH."
    exit 1
}

$redacted = $RtspUrl -replace "://(.*?):(.*)@", "://\$1:***@"
Write-Host "Starting recording from: $redacted"
Write-Host "Output directory: $OutputDir"
Write-Host "Segment length: $SegmentMinutes min"
Write-Host "Press Ctrl+C to stop."

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$segSecs  = $SegmentMinutes * 60
$pattern  = Join-Path $OutputDir "rec-%Y%m%dT%H%M%SZ.mp4"

& ffmpeg `
    -loglevel warning `
    -rtsp_transport tcp `
    -i $RtspUrl `
    -c copy `
    -f segment `
    -segment_time $segSecs `
    -segment_format mp4 `
    -reset_timestamps 1 `
    -strftime 1 `
    $pattern
