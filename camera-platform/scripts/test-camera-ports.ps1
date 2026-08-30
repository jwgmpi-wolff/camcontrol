#Requires -Version 7
<#
.SYNOPSIS
    Test specific ports on a known camera IP.
.PARAMETER CameraIp
    IP address of the camera to test.
.PARAMETER Ports
    Ports to test. Defaults to the safe probe set.
#>
param(
    [Parameter(Mandatory)][string]$CameraIp,
    [int[]]$Ports = @(80, 443, 554, 8080, 8000, 8899, 1900),
    [int]$TimeoutMs = 1000
)

Set-StrictMode -Version Latest

function Test-TcpPort {
    param([string]$Ip, [int]$Port)
    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $ar = $client.BeginConnect($Ip, $Port, $null, $null)
        $ok = $ar.AsyncWaitHandle.WaitOne($TimeoutMs, $false)
        if ($ok -and $client.Connected) { $client.EndConnect($ar); $client.Close(); return $true }
        $client.Close(); return $false
    } catch { return $false }
}

Write-Host "Port scan for $CameraIp"
foreach ($port in $Ports) {
    $result = Test-TcpPort -Ip $CameraIp -Port $port
    $status = if ($result) { "OPEN  ✓" } else { "closed" }
    $hint = switch ($port) {
        80   { "HTTP" }
        443  { "HTTPS" }
        554  { "RTSP (check for stream)" }
        8080 { "HTTP alternate" }
        8000 { "ONVIF candidate" }
        8899 { "ONVIF/Hikvision candidate" }
        1900 { "UPnP/SSDP" }
        default { "" }
    }
    Write-Host "  $port  $status  $hint"
}
