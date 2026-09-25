[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this installer from an elevated PowerShell session.'
}

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $PSScriptRoot 'run-lan-relay.ps1'
$python = Join-Path $repositoryRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    throw "Relay runtime not found: $python"
}

$firewallName = 'CamControl LAN Relay :21417'
if (-not (Get-NetFirewallRule -DisplayName $firewallName -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule `
        -DisplayName $firewallName `
        -Description 'Allow local cameras to upload snapshots to the CamControl LAN relay.' `
        -Direction Inbound `
        -Action Allow `
        -Protocol TCP `
        -LocalPort 21417 `
        -RemoteAddress LocalSubnet `
        -Profile Any | Out-Null
}

$taskName = 'CamControl LAN Relay'
$arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$runner`""
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments
$startupTrigger = New-ScheduledTaskTrigger -AtStartup
$recoveryTrigger = New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 5) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
$taskPrincipal = New-ScheduledTaskPrincipal `
    -UserId 'SYSTEM' `
    -LogonType ServiceAccount `
    -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask `
    -TaskName $taskName `
    -Description 'Continuously forwards local camera snapshots to the CamControl Azure gateway.' `
    -Action $action `
    -Trigger @($startupTrigger, $recoveryTrigger) `
    -Principal $taskPrincipal `
    -Settings $settings `
    -Force | Out-Null

Start-ScheduledTask -TaskName $taskName

$deadline = (Get-Date).AddSeconds(30)
do {
    Start-Sleep -Seconds 1
    try {
        $health = Invoke-RestMethod 'http://127.0.0.1:21417/api/health' -TimeoutSec 2
        if ($health.status -eq 'ok') {
            Write-Output 'CamControl LAN Relay is installed and healthy.'
            exit 0
        }
    } catch {
        if ((Get-Date) -ge $deadline) {
            throw "Relay task started but did not become healthy: $($_.Exception.Message)"
        }
    }
} while ((Get-Date) -lt $deadline)

throw 'Relay task started but did not become healthy within 30 seconds.'
