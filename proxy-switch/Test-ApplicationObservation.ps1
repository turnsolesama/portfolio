$ErrorActionPreference='Stop'
$qa=Join-Path $env:TEMP ('FlowSwitch-observation-'+[Guid]::NewGuid().ToString('N'))
$env:PROXY_SWITCH_DATA_DIR=Join-Path $qa 'data'
. (Join-Path $PSScriptRoot 'ProxyBackend.ps1')
$script:Pass=0
function Check($Value,[string]$Message){if(-not $Value){throw $Message};$script:Pass++}
$script:Profiles=[pscustomobject]@{Version=3;Profiles=@(
    [pscustomobject]@{Id='gateway';Name='Gateway';Protocol='http';Host='127.0.0.1';Port=7897;CorePath=''},
    [pscustomobject]@{Id='upstream';Name='Fixture';Protocol='http';Host='127.0.0.1';Port=18082;CorePath=''}
);Routing=[pscustomobject]@{Adapter='clash-verge';ProfileId='gateway'}}
[void][IO.Directory]::CreateDirectory($qa)
$exe=Join-Path $qa 'Example.exe';$helper=Join-Path $qa 'worker.exe'
[IO.File]::WriteAllText($exe,'observation fixture - never executed');[IO.File]::WriteAllText($helper,'observation fixture - never executed')
$script:FixtureApp=[pscustomobject]@{Name='Example';Path=$exe;SavedPath=$exe;RowKey=$exe;Conflict=$false}
$script:FixtureCore=[pscustomobject]@{available=$true;rulesAvailable=$true;connectionsAvailable=$true;proxiesAvailable=$true}
$main=[pscustomobject]@{Id=10;ParentId=1;Path=$exe;ProcessName='Example'}
$worker=[pscustomobject]@{Id=11;ParentId=10;Path=$helper;ProcessName='worker'}
$sameExeWorker=[pscustomobject]@{Id=12;ParentId=10;Path=$exe;ProcessName='Example'}
$rule=[pscustomobject]@{route='upstream';loaded=$true}
$launch=[pscustomobject]@{route='upstream'}
function Test-ManagedProgramSession {return $true}
function Socket([int]$Owner,[int]$Source,[string]$Remote,[int]$Port,[string]$State='Established'){
    [pscustomobject]@{OwningProcess=$Owner;LocalAddress='127.0.0.1';LocalPort=$Source;RemoteAddress=$Remote;RemotePort=$Port;State=$State}
}
function Observe($Processes,$Connections=@(),$Rule=$null,$Launch=$null,$Core=$script:FixtureCore,$EngineConnections=@(),[bool]$TcpAvailable=$true,[bool]$ProcessesAvailable=$true,$App=$script:FixtureApp){
    $byId=@{};foreach($p in $Processes){$byId[[int]$p.Id]=$p}
    $evidence=Get-ApplicationConnectionEvidence $Processes $Connections $EngineConnections 'gateway' $byId $App.Path $TcpAvailable
    $row=Get-ApplicationObservationRow $App $Processes $evidence $Core $Rule $Launch $null $ProcessesAvailable
    [pscustomobject]@{Evidence=$evidence;Row=$row}
}

# Process presence and observation failure have separate meanings.
$seen=Observe @($main)
Check ($seen.Row.ObservationState -eq 'Idle' -and $seen.Row.Actual -match '运行中.*未观察到 TCP' -and -not $seen.Row.Loaded) 'A running idle process is not reported absent or disconnected'
$seen=Observe @()
Check ($seen.Row.ObservationState -eq 'NotRunning' -and $seen.Row.Actual -eq '程序未运行') 'A successful empty process snapshot identifies a stopped application'
$missing=[pscustomobject]@{Name='Old';Path=(Join-Path $qa 'missing.exe');SavedPath='';RowKey='missing';Conflict=$false}
$seen=Observe -Processes @() -App $missing
Check ($seen.Row.ObservationState -eq 'Missing' -and $seen.Row.Actual -match '路径已失效') 'An absent saved executable is distinguished from an installed stopped app'
$seen=Observe -Processes @() -ProcessesAvailable $false
Check ($seen.Row.ObservationState -eq 'Unknown' -and $seen.Row.Actual -match '进程读取失败' -and $seen.Row.Status -notmatch '未运行') 'Process collection failure does not become an empty successful inventory'
$seen=Observe -Processes @($main) -TcpAvailable $false
Check ($seen.Row.ObservationState -eq 'Unknown' -and $seen.Row.Status -match '采集失败，不代表断网' -and -not $seen.Row.Loaded) 'TCP collection failure remains unknown without alleging a network outage'
function Get-NetTCPConnection {throw 'simulated access denied'}
$snapshot=Get-TcpObservationSnapshot
Check (-not $snapshot.Available -and $snapshot.ErrorCode -eq 'tcp-query-failed') 'The actual collection wrapper preserves query failure evidence'
function Get-NetTCPConnection {return @()}
$snapshot=Get-TcpObservationSnapshot
Check ($snapshot.Available -and @($snapshot.Rows).Count -eq 0) 'A successful query with no sockets remains an available empty snapshot'

# SYN means a connection attempt, and its destination must remain reviewable.
$seen=Observe @($main) @((Socket 10 50000 '127.0.0.1' 7897 'SynSent'))
Check ($seen.Row.Actual -match 'SynSent.*7897' -and $seen.Row.Status -match '尚未建立' -and $seen.Row.Status -notmatch '失败|断网') 'SynSent exposes its target without promoting an attempt to success or definite failure'
Check ($seen.Evidence.State -eq 'Connecting' -and $seen.Evidence.Counts.Count -eq 0 -and $seen.Row.OutsidePending -eq 0) 'A pending registered proxy socket is not a completed or outside connection'
$seen=Observe @($main) @((Socket 10 50000 '203.0.113.2' 443 'SynSent'))
Check ($seen.Row.OutsidePending -eq 1 -and $seen.Row.ChildPending -eq 0) 'OutsidePending counts unregistered destinations even in the main process'
$seen=Observe -Processes @($main,$sameExeWorker) -Connections @((Socket 10 50000 '127.0.0.1' 18082),(Socket 12 50001 '127.0.0.1' 7897 'SynSent')) -Launch $launch
Check ($seen.Row.ChildPending -eq 1 -and $seen.Row.OutsidePending -eq 0 -and $seen.Row.Status -match '联网子进程.*尚未建立' -and -not $seen.Row.Loaded) 'Same-executable child attempts are explicit and are not incorrectly counted outside the proxy'
$seen=Observe -Processes @($main,$worker) -Connections @((Socket 10 50000 '127.0.0.1' 18082),(Socket 11 50001 '203.0.113.2' 443 'SynSent')) -Launch $launch
Check ($seen.Row.OutsidePending -eq 1 -and $seen.Row.Status -match '联网子进程' -and -not $seen.Row.Loaded) 'A working main-process proxy connection does not conceal a child awaiting an outside connection'
$seen=Observe -Processes @($main,$worker) -Connections @((Socket 10 50000 '127.0.0.1' 18082)) -Launch $launch
Check (-not $seen.Row.Loaded -and $seen.Row.Status -match '子进程连接待验证') 'Main-process evidence alone cannot certify an idle helper'
$seen=Observe -Processes @($main,$worker) -Connections @((Socket 10 50000 '127.0.0.1' 18082),(Socket 11 50001 '127.0.0.1' 18082)) -Launch $launch
Check ($seen.Row.Loaded -and $seen.Row.Actual -match 'Fixture ×2') 'Observed main and child proxy sockets can confirm the recorded launch route'
Check (-not $seen.Row.AuthenticationVerified -and -not $seen.Evidence.AuthenticationVerified -and $seen.Row.Coverage -match '不代表.*账号登录成功') 'Even matching proxy connections provide no authentication-success evidence'

# A source port can be reused against another destination; correlate the socket itself.
$engine=[pscustomobject]@{path=$exe;sourcePort=51000;sourceAddress='127.0.0.1';destinationAddress='198.51.100.1';destinationPort=443;network='tcp';inbound='HTTP';route='upstream'}
$seen=Observe -Processes @($main) -Connections @((Socket 10 51000 '127.0.0.1' 7897),(Socket 10 51000 '203.0.113.5' 443)) -Rule $rule -EngineConnections @($engine)
Check ($seen.Evidence.Counts.upstream -eq 1 -and $seen.Evidence.Outside -eq 1 -and -not $seen.Row.Loaded) 'A shared LocalPort does not turn an outside TCP socket into a gateway connection'
$wrongSource=$engine.PSObject.Copy();$wrongSource.sourceAddress='127.0.0.2'
$seen=Observe -Processes @($main) -Connections @((Socket 10 51000 '127.0.0.1' 7897)) -Rule $rule -EngineConnections @($wrongSource)
Check ($seen.Evidence.GatewayUnknown -eq 1 -and $seen.Evidence.Counts.Count -eq 0) 'A controller source address mismatch cannot certify the socket exit'
$tunA=$engine.PSObject.Copy();$tunA.inbound='Tun';$tunA.destinationAddress='203.0.113.8'
$tunB=$tunA.PSObject.Copy();$tunB.destinationAddress='203.0.113.9';$tunB.route='Direct'
$seen=Observe -Processes @($main) -Connections @((Socket 10 51000 '203.0.113.8' 443),(Socket 10 51000 '203.0.113.9' 443)) -EngineConnections @($tunA,$tunB)
Check ($seen.Evidence.Counts.upstream -eq 1 -and $seen.Evidence.Counts.Direct -eq 1 -and $seen.Evidence.Outside -eq 0) 'Distinct TUN destinations sharing a source port retain distinct observed routes'
$unidentified=$engine.PSObject.Copy();$unidentified.route=''
$seen=Observe -Processes @($main) -Connections @((Socket 10 51000 '127.0.0.1' 7897)) -EngineConnections @($unidentified)
Check ($seen.Evidence.State -eq 'Connected' -and $seen.Row.Actual -match '出口待确认' -and $seen.Row.ObservationState -ne 'Idle') 'An unidentified engine exit cannot erase an established gateway socket'
$unidentified.route='removed-profile'
$seen=Observe -Processes @($main) -Connections @((Socket 10 51000 '127.0.0.1' 7897)) -EngineConnections @($unidentified)
Check ($seen.Row.Actual -match '未识别线路' -and $seen.Row.ObservationState -eq 'Connected') 'A route missing from the current profile list is visible instead of becoming idle'

# A partially available control API preserves positive evidence without inventing missing evidence.
$partial=$script:FixtureCore.PSObject.Copy();$partial.connectionsAvailable=$false
$seen=Observe -Processes @($main) -Connections @((Socket 10 51000 '127.0.0.1' 7897)) -Rule $rule -Core $partial
Check (-not $seen.Row.Loaded -and $seen.Row.Status -match '连接读取失败.*未知' -and $seen.Row.RuleLoaded) 'Unavailable connection evidence does not erase the independently loaded rule'
$partial=$script:FixtureCore.PSObject.Copy();$partial.rulesAvailable=$false
$unknownRule=[pscustomobject]@{route='upstream';loaded=$null}
$seen=Observe -Processes @($main) -Connections @((Socket 10 51000 '127.0.0.1' 7897)) -Rule $unknownRule -Core $partial -EngineConnections @($engine)
Check (-not $seen.Row.Loaded -and $seen.Row.Status -match '规则读取失败.*未知' -and $seen.Row.Actual -match 'Fixture ×1') 'Unavailable rule evidence does not erase an actually observed proxy socket'
$partial=$script:FixtureCore.PSObject.Copy();$partial.proxiesAvailable=$false
$seen=Observe -Processes @($main) -Connections @((Socket 10 51000 '127.0.0.1' 7897)) -Rule $rule -Core $partial -EngineConnections @($engine)
Check (-not $seen.Row.Loaded -and $seen.Row.Status -match '当前出口读取失败.*未知' -and $seen.Row.Actual -match 'Fixture ×1') 'Unavailable current selector remains unknown despite an older observed proxy connection'

# The actual inventory integration separates a child with its own saved policy.
$script:IntegratedRules=@([pscustomobject]@{path=$exe;route='upstream'},[pscustomobject]@{path=$helper;route='Direct'})
$script:IntegratedProcesses=@($main.PSObject.Copy(),$worker.PSObject.Copy())
foreach($p in $script:IntegratedProcesses){$p|Add-Member MainWindowHandle $(if($p.Id -eq 10){[IntPtr]1}else{[IntPtr]::Zero});$p|Add-Member StartTime ([DateTime]'2026-09-11')}
$script:IntegratedConnections=@(
    [pscustomobject]@{path=$exe;sourcePort=52000;sourceAddress='127.0.0.1';network='tcp';inbound='HTTP';route='upstream'},
    [pscustomobject]@{path=$helper;sourcePort=52001;sourceAddress='127.0.0.1';network='tcp';inbound='HTTP';route='Direct'}
)
function Get-RoutingSnapshot {[pscustomobject]@{entries=$script:IntegratedRules;launchEntries=@();defaultRoute='upstream'}}
function Invoke-AppRouter {[pscustomobject]@{available=$true;rulesAvailable=$true;connectionsAvailable=$true;entries=@($script:IntegratedRules|ForEach-Object {[pscustomobject]@{path=$_.path;route=$_.route;loaded=$true}});connections=$script:IntegratedConnections;defaultRoute='upstream';defaultLoaded=$true}}
function Get-ProcessInventory {$script:IntegratedProcesses}
$integratedTcp=@((Socket 10 52000 '127.0.0.1' 7897),(Socket 11 52001 '127.0.0.1' 7897))
$integrated=Get-ApplicationRoutes -TcpRows $integratedTcp
$parentRow=$integrated.Rows|Where-Object Path -eq $exe;$childRow=$integrated.Rows|Where-Object Path -eq $helper
Check ($parentRow.Loaded -and $parentRow.PIDs -eq '10' -and $parentRow.Actual -eq 'Fixture ×1') 'A correctly routed explicit child no longer makes its parent appear to retain an old route'
Check ($childRow.Loaded -and $childRow.PIDs -eq '11' -and @($integrated.Rows).Count -eq 2) 'The separately configured child retains its own connection evidence and row'
$grandchild=Join-Path $qa 'grandchild.exe';[IO.File]::WriteAllText($grandchild,'grandchild fixture')
$script:IntegratedProcesses+=@([pscustomobject]@{Id=13;ParentId=11;Path=$grandchild;ProcessName='grandchild';MainWindowHandle=[IntPtr]::Zero;StartTime=[DateTime]'2026-09-11'})
$script:IntegratedConnections+=@([pscustomobject]@{path=$grandchild;sourcePort=52002;sourceAddress='127.0.0.1';network='tcp';inbound='HTTP';route='Direct'})
$integratedTcp+=@(Socket 13 52002 '127.0.0.1' 7897)
$integrated=Get-ApplicationRoutes -TcpRows $integratedTcp
$parentRow=$integrated.Rows|Where-Object Path -eq $exe;$childRow=$integrated.Rows|Where-Object Path -eq $helper
Check ($parentRow.PIDs -eq '10' -and $childRow.PIDs -match '13' -and $parentRow.Loaded) 'The independent child subtree is excluded from its parent and remains assigned to the child observation'
$oldDirectory=Join-Path $qa 'old';[void][IO.Directory]::CreateDirectory($oldDirectory);$oldHelper=Join-Path $oldDirectory 'worker.exe';[IO.File]::WriteAllText($oldHelper,'different older installation')
$script:IntegratedRules=@([pscustomobject]@{path=$exe;route='upstream'},[pscustomobject]@{path=$oldHelper;route='Direct'})
$integrated=Get-ApplicationRoutes -TcpRows $integratedTcp
$parentRow=$integrated.Rows|Where-Object Path -eq $exe
Check ($parentRow.PIDs -match '11' -and $parentRow.PIDs -match '13' -and -not $parentRow.Loaded) 'An unrelated saved installation with the same executable name cannot suppress the actual child traffic'
# A verified alias resolves to the current child executable and must still separate that subtree.
$alias=Join-Path $qa 'worker-alias.exe';[void](New-Item -ItemType HardLink -Path $alias -Target $helper)
$script:IntegratedRules=@([pscustomobject]@{path=$exe;route='upstream'},[pscustomobject]@{path=$alias;route='Direct'})
$integrated=Get-ApplicationRoutes -TcpRows $integratedTcp
$parentRow=$integrated.Rows|Where-Object Path -eq $exe;$childRow=$integrated.Rows|Where-Object SavedPath -eq $alias
Check ($parentRow.PIDs -eq '10' -and $parentRow.Loaded -and $childRow.Path -eq $helper -and $childRow.RequiresRepair) 'Resolved current child identity separates evidence while its literal saved path awaits repair'
Write-Output ('PASS: '+$script:Pass+' application observation assertions; isolated files and synthetic snapshots only.')
