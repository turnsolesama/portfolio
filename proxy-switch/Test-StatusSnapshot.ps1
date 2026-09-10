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
Write-Output ('PASS: '+$checks+' display snapshot checks; no Windows writes or real network queries.')
