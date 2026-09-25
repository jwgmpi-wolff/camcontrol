[CmdletBinding()]
param()

$ErrorActionPreference = 'Continue'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repositoryRoot '.venv\Scripts\python.exe'
$logDirectory = Join-Path $repositoryRoot 'logs'
$logPath = Join-Path $logDirectory 'lan-relay.log'
$previousLogPath = "$logPath.1"

New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null

while ($true) {
    if ((Test-Path $logPath) -and (Get-Item $logPath).Length -gt 10MB) {
        Remove-Item $previousLogPath -Force -ErrorAction SilentlyContinue
        Move-Item $logPath $previousLogPath -Force
    }

    if (-not (Test-Path $python)) {
        Add-Content $logPath "$(Get-Date -Format o) relay runtime missing: $python"
        Start-Sleep -Seconds 60
        continue
    }

    Add-Content $logPath "$(Get-Date -Format o) starting LAN relay"
    & $python -m camera_bridge.lan_relay *>> $logPath
    Add-Content $logPath "$(Get-Date -Format o) LAN relay exited with code $LASTEXITCODE; restarting"
    Start-Sleep -Seconds 5
}
