$ErrorActionPreference='Stop'
$qa=Join-Path $env:TEMP ('FlowSwitch-StatusSnapshot-'+[Guid]::NewGuid().ToString('N'))
. (Join-Path $PSScriptRoot 'ProxyBackend.ps1') -DataDirectory $qa
$checks=0;$queries=0
function Check($Value,$Message){if(-not $Value){throw $Message};$script:checks++}
$script:Profiles=ConvertTo-ValidProfileSettings ([pscustomobject]@{Version=3;Profiles=@([pscustomobject]@{Id='proxy';Name='Fixture';Protocol='http';Host='127.0.0.1';Port=30000;CorePath='C:\Fixture\proxy.exe';AppPath=''});Routing=[pscustomobject]@{Adapter='none';ProfileId=''}})
function Get-NetTCPConnection {param($State,$LocalPort,$ErrorAction);$script:queries++;return @()}
function Get-ProcessInventory {param($Id);$all=@([pscustomobject]@{Id=10;ProcessName='app';Path='C:\Fixture\app.exe';MainWindowHandle=[IntPtr]1},[pscustomobject]@{Id=11;ProcessName='proxy';Path='C:\Fixture\proxy.exe';MainWindowHandle=[IntPtr]0});if($Id){$all|Where-Object Id -eq $Id}else{$all}}
function Get-ProgramFamily($Executable,$Processes){@($Processes|Where-Object Path -eq $Executable)}
function Get-ProgramLaunchEntries {@()}
function Invoke-AppRouter($Request){[pscustomobject]@{available=$false;entries=@();connections=@();defaultRoute=$null;defaultLoaded=$false}}
function Get-SystemSnapshot {[pscustomobject]@{Flags=1;Server='';Bypass=''}}
function Get-UserProxyEnv {[pscustomobject]@{HTTP_PROXY=$null;HTTPS_PROXY=$null;ALL_PROXY=$null;NO_PROXY='localhost'}}
function Get-ClientWarnings {}
function Get-OverrideWarnings {}
$rows=@([pscustomobject]@{State='Listen';LocalAddress='127.0.0.1';LocalPort=30000;OwningProcess=11})
foreach($state in @('Established','SynSent','TimeWait')){$rows+=@([pscustomobject]@{State=$state;LocalAddress='127.0.0.1';LocalPort=(50000+$rows.Count);RemoteAddress='127.0.0.1';RemotePort=30000;OwningProcess=10})}
$apps=Get-ApplicationRoutes -TcpRows $rows
$status=Get-ProxyStatus $apps -TcpRows $rows
Check ($queries -eq 0) 'Display functions repeated the Windows connection query'
Check ($status.Listeners[0].Ready) 'Shared snapshot lost the listener'
Check ($status.Connections.Count -eq 1 -and $status.Connections[0].Count -eq 1) 'Non-established sockets counted as live connections'
Check ($apps.Rows.Count -eq 1 -and $apps.Rows[0].Actual -match '×1' -and $apps.Rows[0].Actual -match 'SynSent') 'Application connections or pending state changed'
$empty=Get-ProxyStatus $apps -TcpRows @()
Check (-not $empty.Listeners[0].Ready -and $queries -eq 0) 'An empty display snapshot was confused with no snapshot'
Check (-not (Get-Listener (Get-Profile 'proxy'))) 'A fresh readiness check reused a stale display listener'
Check ($queries -eq 1) 'Readiness did not query Windows again'
Get-ApplicationRoutes | Out-Null
Check ($queries -eq 2) 'Default application query unexpectedly reused a previous snapshot'
$script:Profiles.Routing.UnifiedMode='gateway';$script:Profiles.Routing.ProfileId='proxy'
$script:Profiles.Routing.Adapter='clash-verge'
$offline=Get-ProxyStatus $apps -TcpRows @()
Check (($offline.Warnings -join ' ') -match '固定分流入口未就绪') 'Offline configured gateway explicitly explains why switching depends on it'
$unknown=Get-ProxyStatus $apps -TcpRows @() -TcpAvailable $false
Check (($unknown.Warnings -join ' ') -notmatch '固定分流入口未就绪') 'Unknown TCP data cannot falsely diagnose an offline gateway'
function Get-NetTCPConnection {param($State,$LocalPort,$ErrorAction)
    if($State){throw 'A missing requested state aborts assignment in the Windows CIM wrapper'}
    @([pscustomobject]@{State='Listen';LocalPort=30000},[pscustomobject]@{State='Established';LocalPort=50000},[pscustomobject]@{State='TimeWait';LocalPort=50001})
}
$observed=Get-TcpObservationSnapshot
Check ($observed.Available -and $observed.Rows.Count -eq 2 -and @($observed.Rows|Where-Object State -eq 'Listen').Count -eq 1) 'Absent SynSent cannot discard listeners and established connections'
function Get-NetTCPConnection {param($State,$LocalPort,$ErrorAction);throw 'Access denied fixture'}
$observed=Get-TcpObservationSnapshot
Check (-not $observed.Available -and $observed.ErrorCode -eq 'tcp-query-failed') 'Actual collection failure still reports unknown instead of an empty healthy snapshot'
Write-Output ('PASS: '+$checks+' display snapshot checks; no Windows writes or real network queries.')
