#Requires -Version 5.1
<#
.SYNOPSIS
    One-time setup for CamControl on a fresh Windows PC.
    Run this once, then use Start-CamControl.bat to launch.
#>
$ErrorActionPreference = 'Stop'
$root = Split-Path $MyInvocation.MyCommand.Path

Write-Host "=== CamControl Installer ===" -ForegroundColor Cyan

# Python check / install
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "Installing Python via winget..." -ForegroundColor Yellow
    winget install Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH","Machine") + ";" + $env:PATH
}
Write-Host "Python: $(python --version)" -ForegroundColor Green

# ffmpeg
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host "Installing ffmpeg..." -ForegroundColor Yellow
    winget install Gyan.FFmpeg -e --accept-package-agreements --accept-source-agreements
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH","Machine") + ";" + $env:PATH
}
Write-Host "ffmpeg: OK" -ForegroundColor Green

# Virtual env + deps
Set-Location $root
if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    python -m venv .venv
}
Write-Host "Installing Python packages..." -ForegroundColor Yellow
& ".venv\Scripts\pip.exe" install -r requirements.txt --quiet
Write-Host "Packages: OK" -ForegroundColor Green

# Firewall rules for gateway and RTSP
foreach ($port in @(8080, 8554)) {
    $name = "CamControl :$port"
    if (-not (Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue)) {
        Write-Host "Adding firewall rule for port $port..." -ForegroundColor Yellow
        New-NetFirewallRule -DisplayName $name -Direction Inbound -Protocol TCP -LocalPort $port -Action Allow -Profile Any | Out-Null
    }
}

Write-Host ""
Write-Host "=== Installation complete! ===" -ForegroundColor Green
Write-Host "Run Start-CamControl.bat to launch." -ForegroundColor Cyan
Write-Host "Access from any device on your network: http://$($(Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.InterfaceAlias -notmatch 'Loopback'} | Select-Object -First 1).IPAddress):8080/"
pause
