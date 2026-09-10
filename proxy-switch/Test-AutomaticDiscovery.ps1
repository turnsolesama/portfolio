$ErrorActionPreference='Stop'
$env:PROXY_SWITCH_DATA_DIR=Join-Path $env:TEMP ('ProxySwitch-unit-'+[Guid]::NewGuid().ToString('N'))
. (Join-Path $PSScriptRoot 'ProxyBackend.ps1')
$script:Pass=0
$productionOwnerCheck=${function:Test-DiscoveryOwnerStillListening}
function Check($Value,[string]$Name){if(-not $Value){throw $Name};$script:Pass++}
$data=Join-Path $env:TEMP ('ProxySwitch-auto-'+[Guid]::NewGuid().ToString('N'))
$script:DataRoot=$data;$script:ConfigPath=Join-Path $data 'config.json';$script:StatePath=Join-Path $data 'selection.json';$script:BackupDir=Join-Path $data 'backups'
$script:Profiles=ConvertTo-ValidProfileSettings ([pscustomobject]@{Version=3;Profiles=@();Routing=@{Adapter='none';ProfileId=''}})
Write-LocalJson $script:ConfigPath $script:Profiles
$script:ProbeCalls=@();$script:CorePid=20;$script:CorePort=19081;$script:Started='1000';$script:CoreAlive=$true
$script:Configured=$false
function Set-SystemSnapshot {throw 'Automatic discovery changed system proxy'}
function Set-UserProxyEnv {throw 'Automatic discovery changed environment'}
function Set-RoutingSnapshot {throw 'Automatic discovery changed rules'}
function Get-SystemSnapshot {[pscustomobject]@{Flags=$(if($script:Configured){3}else{1});Server=$(if($script:Configured){'localhost:19083'}else{'127.0.0.1:7897'});Bypass=''}}
function Get-UserProxyEnv {[pscustomobject]@{HTTP_PROXY=$null;HTTPS_PROXY=$null;ALL_PROXY=$null}}
function Get-Selection {$null}
function Get-LocalListenerInventory {@(
    [pscustomobject]@{Host='127.0.0.1';Port=$script:CorePort;PID=$script:CorePid;Started=$script:Started;Name='mihomo';Path='C:\Apps\mihomo.exe'},
    [pscustomobject]@{Host='127.0.0.1';Port=44531;PID=30;Started='2000';Name='CalabiYau';Path='C:\Games\CalabiYau.exe'},
    [pscustomobject]@{Host='127.0.0.1';Port=19083;PID=40;Started='2001';Name='CustomProxy';Path='C:\Apps\customproxy.exe'}
)}
function Test-DiscoveryOwnerStillListening($Endpoint){$script:CoreAlive -and $Endpoint.PID -eq $script:CorePid}
function Test-LocalProxyProtocol($Address,$Port,$Protocol){$script:ProbeCalls+=@($Port);if($Port -eq 44531){throw 'Game port was probed'};return $Protocol -eq 'http'}
$first=Sync-AutomaticProxyDiscovery
Check ($first.Added -eq 1 -and (Read-ProfileSettings).Profiles.Count -eq 1) 'Startup automatically discovers and adds a real proxy candidate'
Check ($first.Probed -eq 1 -and $script:ProbeCalls.Count -eq 1 -and $script:ProbeCalls[0] -eq 19081) 'Automatic handshake targets identified proxy owner only'
$second=Sync-AutomaticProxyDiscovery $first.Cache
Check ($second.Added -eq 0 -and $second.Probed -eq 0 -and $script:ProbeCalls.Count -eq 1) 'Repeated refresh uses cache without repeated handshakes'
$script:CorePid=21;$script:Started='3000'
$third=Sync-AutomaticProxyDiscovery $second.Cache
Check ($third.Probed -eq 1 -and $script:ProbeCalls.Count -eq 2) 'Proxy restart invalidates cached owner identity'
$script:CorePort=19082
$fourth=Sync-AutomaticProxyDiscovery $third.Cache
Check ($fourth.Added -eq 1 -and $fourth.Probed -eq 1) 'New proxy port is discovered while manager stays open'
$script:Configured=$true
$fifth=Sync-AutomaticProxyDiscovery $fourth.Cache
Check ($fifth.Configured -eq 1 -and $fifth.Added -eq 1 -and $fifth.Probed -eq 0) 'Unknown proxy is automatically read from active Windows configuration without a handshake'
Check (19083 -notin $script:ProbeCalls -and 44531 -notin $script:ProbeCalls) 'Neither unfamiliar application nor game receives automatic protocol traffic'
Check (-not (Test-RecognizedProxyOwner ([pscustomobject]@{Name='GameWithUpnetOverlay';Path='C:\Games\GameWithUpnetOverlay.exe'}))) 'A substring in a process name cannot authorize probing'
$fresh=Read-ProfileSettings;$fresh.Profiles=@($fresh.Profiles|Where-Object Port -ne 19082);$fresh.DiscoveryIgnored=@('loopback:19082');Save-ProfileSettings $fresh
$sixth=Sync-AutomaticProxyDiscovery $fifth.Cache
Check ($sixth.Added -eq 0 -and 19082 -notin @((Read-ProfileSettings).Profiles.Port)) 'Deleted proxy is not restored by automatic discovery'
$script:CoreAlive=$false;$script:CorePid=22
$n=$script:ProbeCalls.Count;$last=Sync-AutomaticProxyDiscovery $sixth.Cache
Check ($script:ProbeCalls.Count -eq $n) 'Owner is rechecked before sending any handshake'

# The production inventory uses documented process snapshots and limited queries.
Check ([LocalProxySwitch.ProcessCatalog]::QueryAccess -eq 0x1000) 'Process access is limited query only, without VM_READ'
$self=Get-ProcessInventory -Id $PID
Check ($self.Id -eq $PID -and (Test-Path -LiteralPath $self.Path)) 'Native inventory returns a usable executable path without module enumeration'
Check ($self.StartTime -ne [DateTime]::MinValue) 'Process birth time is available for discovery cache invalidation'
$implementation=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'ProcessInventory.ps1') -Raw
Check ($implementation -notmatch 'extern\s+.*(?:ReadProcessMemory|EnumProcessModules|GetModuleFileNameEx|VirtualQueryEx)\s*\(') 'Process inventory does not import memory or module inspection APIs'

function Get-NetTCPConnection {throw 'TCP provider unavailable'}
$script:FallbackRows=@([pscustomobject]@{Port=19085;PID=$PID;Path=$self.Path})
function Get-LocalListenerInventory {$script:FallbackRows}
$endpoint=[pscustomobject]@{PID=$PID;Name=$self.ProcessName;Path=$self.Path;Started=$self.StartTime.ToUniversalTime().Ticks.ToString();Port=19085}
Check (& $productionOwnerCheck $endpoint) 'Listener ownership can still be rechecked through the fallback inventory'
$script:FallbackRows=@([pscustomobject]@{Port=19085;PID=1;Path=$self.Path})
Check (-not (& $productionOwnerCheck $endpoint)) 'Fallback ownership check refuses a reused port owned by another process'

Write-Output ('PASS: '+$script:Pass+' automatic discovery and process-query assertions; isolated settings only.')
