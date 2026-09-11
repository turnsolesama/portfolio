$ErrorActionPreference='Stop'
$qa=Join-Path $env:TEMP ('FlowSwitch-managed-observation-'+[Guid]::NewGuid().ToString('N'))
$env:PROXY_SWITCH_DATA_DIR=Join-Path $qa 'data'
. (Join-Path $PSScriptRoot 'ProxyBackend.ps1')
. (Join-Path $PSScriptRoot 'ProgramFamilyTracking.ps1')
[void][IO.Directory]::CreateDirectory($qa)
$script:Pass=0
function Check($Value,[string]$Message){if(-not $Value){throw $Message};$script:Pass++}
$app=Join-Path $qa 'IDE.exe';$child=Join-Path $qa 'worker.exe'
foreach($file in @($app,$child)){[IO.File]::WriteAllText($file,'read-only observation fixture')}
$script:Profiles=[pscustomobject]@{Version=3;Profiles=@(
    [pscustomobject]@{Id='gateway';Name='Gateway';Protocol='http';Host='127.0.0.1';Port=18790;CorePath='';AppPath=''},
    [pscustomobject]@{Id='a';Name='Proxy A';Protocol='http';Host='127.0.0.1';Port=21001;CorePath='';AppPath=''},
    [pscustomobject]@{Id='b';Name='Proxy B';Protocol='http';Host='127.0.0.1';Port=21002;CorePath='';AppPath=''}
);Routing=[pscustomobject]@{Adapter='standalone';ProfileId='gateway'}}
$birth=[DateTime]::UtcNow.AddMinutes(-1)
$main=[pscustomobject]@{Id=10;ParentId=1;Path=$app;PathStatus='Available';ProcessName='IDE';StartTime=$birth;MainWindowHandle=[IntPtr]1}
$worker=[pscustomobject]@{Id=11;ParentId=10;Path=$child;PathStatus='Available';ProcessName='worker';StartTime=$birth.AddSeconds(1);MainWindowHandle=[IntPtr]::Zero}
$script:Ingress=[pscustomobject]@{id='0123456789abcdef';path=$app;port=22111;route='b';loaded=$true;ready=$true;effectiveRoute='b';inboundName='FS-Program-0123456789abcdef';managed=$true}
$script:ManagedCore=[pscustomobject]@{available=$true;rulesAvailable=$true;connectionsAvailable=$true;proxiesAvailable=$true;programIngresses=@($script:Ingress);entries=@();connections=@();defaultRoute='b';defaultLoaded=$true;siteRulesLoaded=$true}
$candidate=New-ApplicationCandidate $app 'IDE';$candidate.SavedPath=$app
$script:Session=$false
function Test-ManagedProgramSession {return $script:Session}
function Socket([int]$Owner,[int]$Source,[int]$Destination=22111,[string]$State='Established'){
    [pscustomobject]@{OwningProcess=$Owner;LocalAddress='127.0.0.1';LocalPort=$Source;RemoteAddress='127.0.0.1';RemotePort=$Destination;State=$State}
}
function Engine([string]$Path,[int]$Source,[string]$Route='b',[string]$Expected='b'){
    [pscustomobject]@{path=$Path;sourcePort=$Source;sourceAddress='127.0.0.1';network='tcp';inbound='HTTP';ingressId=$script:Ingress.id;inboundName=$script:Ingress.inboundName;route=$Route;expectedRoute=$Expected;policyMatches=($Route -eq $Expected)}
}
function Observe($Family,$Tcp=@(),$Connections=@(),$Rule=$script:Ingress,$FamilySnapshot=$null,$Core=$script:ManagedCore){
    $byId=@{};foreach($p in $Family){$byId[[int]$p.Id]=$p}
    $evidence=Get-ApplicationConnectionEvidence $Family $Tcp $Connections 'gateway' $byId $app $true @($script:Ingress)
    $row=Get-ApplicationObservationRow $candidate $Family $evidence $Core $Rule $null $null $true $FamilySnapshot
    [pscustomobject]@{Evidence=$evidence;Row=$row}
}
$seen=Observe @($main) @((Socket 10 50001)) @((Engine $app 50001))
Check ($seen.Row.Mode -eq 'managed' -and $seen.Row.Managed -and $seen.Row.CanLaunch) 'A managed program has a distinct launchable mode'
Check ($seen.Row.Loaded -and $seen.Evidence.Counts.b -eq 1 -and $seen.Evidence.LocalUnknown -eq 0 -and -not $seen.Row.NeedsRelaunch) 'A private ingress socket is correlated with its real engine route, not an unregistered upstream'
$mixed=Observe @($main,$worker) @((Socket 10 50001),(Socket 11 50002)) @((Engine $app 50001 'b' 'b'),(Engine $child 50002 'Direct' 'Direct'))
Check ($mixed.Row.Loaded -and $mixed.Row.Status -match '网站分流' -and $mixed.Row.Status -notmatch '旧线路') 'Current website policy may legitimately mix direct and proxied connections in one program'
Check ($mixed.Evidence.ChildProxyObserved -eq 1 -and $mixed.Row.Status -match '子进程') 'A verified worker''s private ingress route appears in its parent row'
$stale=Observe @($main) @((Socket 10 50001)) @((Engine $app 50001 'a' 'b'))
Check (-not $stale.Row.Loaded -and $stale.Evidence.PolicyMismatch -eq 1 -and $stale.Row.Status -match '不符合当前线路') 'A connection retained on old A after selecting B remains visibly stale'
$unknownPolicy=Engine $app 50001;$unknownPolicy.policyMatches=$null;$unknownPolicy.expectedRoute='Unknown'
$seen=Observe @($main) @((Socket 10 50001)) @($unknownPolicy)
Check (-not $seen.Row.Loaded -and $seen.Row.Status -match '选路状态待确认') 'Unknown controller policy cannot be promoted to a successful route change'
$unknownPolicy.expectedRoute='b'
$seen=Observe @($main) @((Socket 10 50001)) @($unknownPolicy)
Check (-not $seen.Row.Loaded -and $seen.Evidence.PolicyUnknown -eq 1) 'Explicitly unknown policy verification cannot be replaced with a guessed expected-route comparison'
$blocked=Engine $app 50001 'Blocked' 'Blocked'
$seen=Observe @($main) @((Socket 10 50001)) @($blocked)
Check (-not $seen.Row.Loaded) 'An intentionally blocked or exhausted route is not reported as successful connectivity'
$seen=Observe @($main) @((Socket 10 50001 21001))
Check ($seen.Row.NeedsRelaunch -and -not $seen.Row.Loaded -and $seen.Row.Status -match '尚未接入固定程序入口') 'A running program still dialing A is told to reenter through its stable managed entry'
$script:Session=$true
$seen=Observe @($main) @((Socket 10 50001 21001))
Check ($seen.Row.NeedsRelaunch -and -not $seen.Row.Loaded) 'A recorded managed launch cannot overrule actual connections still using old A'
$script:Session=$false
$seen=Observe @($main) @((Socket 10 50001 22111 'SynSent'))
Check (-not $seen.Row.Loaded -and $seen.Evidence.ManagedPending -eq 1 -and $seen.Evidence.OutsidePending -eq 0) 'Pending private ingress connections remain pending without being mislabeled outside the proxy'
$wrongPath=Engine $child 50001
$seen=Observe @($main) @((Socket 10 50001)) @($wrongPath)
Check (-not $seen.Row.Loaded -and $seen.Evidence.GatewayUnknown -eq 1) 'Equal source ports cannot claim another executable''s connection'
$wrongAddress=Engine $app 50001;$wrongAddress.sourceAddress='127.0.0.2'
$seen=Observe @($main) @((Socket 10 50001)) @($wrongAddress)
Check (-not $seen.Row.Loaded -and $seen.Evidence.GatewayUnknown -eq 1) 'Source-address mismatch cannot certify the program exit'
$wrongIngress=Engine $app 50001;$wrongIngress.inboundName='FS-Program-other'
$seen=Observe @($main) @((Socket 10 50001)) @($wrongIngress)
Check (-not $seen.Row.Loaded -and $seen.Evidence.GatewayUnknown -eq 1) 'Contradictory ingress identity is not accepted through one matching field'
$unknownIngress=Engine $app 50001;$unknownIngress.ingressId='';$unknownIngress.inboundName=''
$seen=Observe @($main) @((Socket 10 50001)) @($unknownIngress)
Check (-not $seen.Row.Loaded -and $seen.Evidence.GatewayUnknown -eq 1) 'A private port without controller ingress identity stays unverified'
$notReady=$script:Ingress.PSObject.Copy();$notReady.ready=$false
$seen=Observe @($main) @((Socket 10 50001)) @((Engine $app 50001)) $notReady
Check (-not $seen.Row.Loaded -and $seen.Row.Status -match '未就绪') 'A saved or previously observed route does not override current ingress readiness failure'
$partial=$script:ManagedCore.PSObject.Copy();$partial.connectionsAvailable=$false
$seen=Observe @($main) @((Socket 10 50001)) @((Engine $app 50001)) $script:Ingress $null $partial
Check (-not $seen.Row.Loaded -and $seen.Row.Status -match '连接读取失败') 'Unavailable engine connection evidence cannot be certified by cached sockets'
$unknownFamily=[pscustomobject]@{UnknownIds=@(11);RetainedIds=@();Members=@();Available=$true}
$seen=Observe @() @() @() $script:Ingress $unknownFamily
Check ($seen.Row.ObservationState -eq 'Unknown' -and $seen.Row.Status -notmatch '未运行' -and $seen.Row.FamilyUnknownIds -contains 11) 'Unreadable tracked identity appears as unknown, not a stopped program'
$retainedFamily=[pscustomobject]@{UnknownIds=@();RetainedIds=@(11);Members=@($worker);Available=$true}
$seen=Observe @($worker) @((Socket 11 50002)) @((Engine $child 50002)) $script:Ingress $retainedFamily
Check ($seen.Row.FamilyRetained -and $seen.Row.Loaded -and $seen.Row.Status -match '主进程已退出') 'A verified background worker may continue reporting its actual managed exit after the root closes'
Check (-not $seen.Row.AuthenticationVerified) 'Managed route evidence never certifies an account login'

# Full inventory integration: persisted managed entries take precedence, retain helpers, and do not change policies.
$script:IntegratedProcesses=@($main,$worker);$script:IntegratedTcp=@((Socket 10 50001),(Socket 11 50002))
$script:ManagedCore.connections=@((Engine $app 50001),(Engine $child 50002))
function Get-RoutingSnapshot {[pscustomobject]@{entries=@();launchEntries=@([pscustomobject]@{path=$app;route='a';adapter='chromium'});programIngresses=@($script:Ingress);defaultRoute='b'}}
function Invoke-AppRouter {return $script:ManagedCore}
function Get-ProcessInventory {return $script:IntegratedProcesses}
$snapshot=Get-ApplicationRoutes -TcpRows $script:IntegratedTcp
$parent=$snapshot.Rows|Where-Object Path -eq $app
Check ($snapshot.RuleCount -eq 1 -and $parent.Mode -eq 'managed' -and $parent.Policy -eq 'b') 'A stable managed entry takes priority over its older launch record without double-counting rules'
Check (@($snapshot.Rows|Where-Object Path -eq $child).Count -eq 0 -and $parent.PIDs -match '11') 'A helper without its own policy is folded into the managed program'
$script:IntegratedProcesses=@($worker);$script:IntegratedTcp=@((Socket 11 50002));$script:ManagedCore.connections=@((Engine $child 50002))
$snapshot=Get-ApplicationRoutes -TcpRows $script:IntegratedTcp;$parent=$snapshot.Rows|Where-Object Path -eq $app
Check ($parent.PIDs -eq '11' -and $parent.FamilyRetained -and $parent.Loaded) 'Inventory refresh keeps the managed program row when only its previously verified worker survives'
Check (@($snapshot.Rows|Where-Object Path -eq $child).Count -eq 0) 'Root exit does not create a misleading duplicate unassigned worker row'
Check ($snapshot.RuleCount -eq 1 -and (Get-RoutingSnapshot).launchEntries[0].route -eq 'a') 'All observation and family refreshes leave saved routes unchanged'
Write-Output ('PASS: '+$script:Pass+' managed observation assertions; isolated synthetic TCP and controller snapshots only.')
