#Requires -Version 7
<#
.SYNOPSIS
    Safe local discovery for YI Outdoor Camera 1080p (YHS.3017) and compatible devices.
    Probes only safe ports. No login attempt, no firmware access, no exploit.
.PARAMETER SubnetPrefix
    Override auto-detected subnet prefix (e.g. "192.168.1").
.PARAMETER Ports
    Ports to probe. Defaults to safe set: 80 443 554 8080 8000 8899 1900.
.PARAMETER TimeoutMs
    TCP connection timeout in milliseconds.
.PARAMETER OutputPath
    Write JSON capability report to this file.
#>
param(
    [string]$SubnetPrefix = "",
    [int[]]$Ports = @(80, 443, 554, 8080, 8000, 8899, 1900),
    [int]$TimeoutMs = 700,
    [string]$OutputPath = ".\yhs3017-discovery-report.json"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-LocalSubnetPrefix {
    $ip = Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object {
            $_.IPAddress -notlike "169.254.*" -and
            $_.IPAddress -ne "127.0.0.1" -and
            $_.PrefixOrigin -ne "WellKnown"
        } | Select-Object -First 1
    if (-not $ip) { throw "No active IPv4 interface found." }
    ($ip.IPAddress -split "\.")[0..2] -join "."
}

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

function Get-ArpTable {
    $out = & arp -a
    $map = @{}
    foreach ($line in $out) {
        if ($line -match "^\s*(\d+\.\d+\.\d+\.\d+)\s+([a-fA-F0-9\-]{17})") {
            $map[$matches[1]] = $matches[2]
        }
    }
    $map
}

if ([string]::IsNullOrWhiteSpace($SubnetPrefix)) {
    $SubnetPrefix = Get-LocalSubnetPrefix
}

Write-Host "Safe discovery  subnet=$SubnetPrefix.0/24  ports=$($Ports -join ',')"
Write-Host "No credentials, no firmware access, no exploit."

# Warm ARP cache
1..254 | ForEach-Object {
    $ip = "$SubnetPrefix.$_"
    $null = Test-Connection -ComputerName $ip -Count 1 -Quiet -TimeoutSeconds 1 -ErrorAction SilentlyContinue
}

$arp = Get-ArpTable
$candidates = $arp.Keys | Where-Object { $_ -like "$SubnetPrefix.*" }
$results = [System.Collections.Generic.List[object]]::new()

foreach ($ip in $candidates) {
    $open = @($Ports | Where-Object { Test-TcpPort -Ip $ip -Port $_ })
    if ($open.Count -eq 0) { continue }

    $hostname = $null
    try { $hostname = [System.Net.Dns]::GetHostEntry($ip).HostName } catch {}

    $rtsp    = $open -contains 554
    $http    = ($open -contains 80) -or ($open -contains 8080)
    $https   = $open -contains 443
    $onvif   = ($open -contains 8000) -or ($open -contains 8899) -or ($open -contains 80)

    $nextSteps = @(
        "Confirm this device belongs to your YI YHS.3017 via router DHCP table or YI app."
    )
    if ($rtsp)  { $nextSteps += "Port 554 open. Test RTSP with YOUR credentials: rtsp://<user>:<pass>@$ip`:554/ch0_0.264" }
    if ($http)  { $nextSteps += "HTTP port open. Check for local admin page with your browser." }
    if ($onvif) { $nextSteps += "ONVIF port may be open. Test with an ONVIF client and your credentials." }
    $nextSteps += "Do NOT attempt brute-force or default credentials."

    $results.Add([PSCustomObject]@{
        IPAddress      = $ip
        Hostname       = $hostname
        MacAddress     = $arp[$ip]
        OpenPorts      = $open
        RtspLikely     = $rtsp
        HttpLikely     = $http
        HttpsLikely    = $https
        OnvifCandidate = $onvif
        RtspCandidates = if ($rtsp) { @(
            "rtsp://<user>:<pass>@${ip}:554/ch0_0.264",
            "rtsp://<user>:<pass>@${ip}:554/ch0_0.h264",
            "rtsp://<user>:<pass>@${ip}:554/live"
        ) } else { @() }
        SafeNextSteps  = $nextSteps
    })
}

$report = [PSCustomObject]@{
    TimestampUtc      = (Get-Date).ToUniversalTime().ToString("o")
    TargetModel       = "YI Outdoor Camera 1080p YHS.3017"
    SubnetScanned     = "$SubnetPrefix.0/24"
    PortsChecked      = $Ports
    DevicesFound      = $results.Count
    Devices           = $results
}

$report | ConvertTo-Json -Depth 8 | Out-File -FilePath $OutputPath -Encoding UTF8

Write-Host ""
Write-Host "Discovery complete. Report: $OutputPath"
$results | Format-Table IPAddress, MacAddress, OpenPorts, RtspLikely, HttpLikely, OnvifCandidate -AutoSize
