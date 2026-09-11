$ErrorActionPreference='Stop'
$qa=Join-Path $env:TEMP ('FlowSwitch-managed-rules-'+[Guid]::NewGuid().ToString('N'))
. (Join-Path $PSScriptRoot 'ProxyBackend.ps1') -DataDirectory $qa
$checks=0
function Check($Value,$Message){if(-not $Value){throw $Message};$script:checks++}
function Throws([scriptblock]$Action,[string]$Pattern){$message='';try{& $Action|Out-Null}catch{$message=$_.Exception.Message};Check ($message -match $Pattern) ('Expected '+$Pattern+', got '+$message)}
function Use-ChangeLock([scriptblock]$Action){& $Action}
function Get-SystemSnapshot {[pscustomobject]@{Flags=3;Server='127.0.0.1:18790';Bypass='localhost'}}
function Get-UserProxyEnv {[pscustomobject]@{HTTP_PROXY='http://127.0.0.1:18790';HTTPS_PROXY='http://127.0.0.1:18790';ALL_PROXY='http://127.0.0.1:18790';NO_PROXY='localhost'}}
function Set-SystemSnapshot {throw 'Must not change Windows'}
function Set-UserProxyEnv {throw 'Must not change Windows'}
function Ensure-ManagedGateway {Invoke-AppRouter @{action='status'}}
function Test-ProxyRoute {param($Key,[switch]$Fast);[pscustomobject]@{Usable=(-not $script:RejectProbe)}}
function Install-ProgramProxyShortcut {param($Executable);@()}
function Get-ProcessInventory {if($script:FailObservation){throw 'Synthetic observation unavailable'};@()}
function Get-Listener {param($Profile,[switch]$ProbeRemote);[pscustomobject]@{PID=999}}
$script:Profiles=ConvertTo-ValidProfileSettings ([pscustomobject]@{Version=3;Profiles=@(
 @{Id='gateway';Name='Gateway';Protocol='http';Host='127.0.0.1';Port=18790;CorePath='C:\Test\core.exe'},
 @{Id='a';Name='A';Protocol='http';Host='127.0.0.1';Port=18791},
 @{Id='b';Name='B';Protocol='http';Host='127.0.0.1';Port=18792}
);Routing=@{Adapter='standalone';ProfileId='gateway';UnifiedMode='gateway'}})
Write-LocalJson $script:ConfigPath $script:Profiles
$script:StateFile=Join-Path $qa 'app-rules.json'
Write-LocalJson $script:StateFile @{version=3;installed=$true;entries=@();defaultRoute='a';programIngresses=@();siteRules=@()}
function Invoke-AppRouter($Request,[int]$TimeoutMilliseconds=55000){
 $state=Get-Content -LiteralPath $script:StateFile -Raw -Encoding UTF8|ConvertFrom-Json
 if($Request.action -eq 'replace'){
  Check ($Request.expectedStateHash -ceq (Read-RuleMaintenanceFile $script:StateFile).TextHash) 'Mutation binds to exact prior state'
  $state.entries=@($Request.entries);$state.defaultRoute=$Request.defaultRoute
  foreach($field in @('programIngresses','siteRules')){if($Request.ContainsKey($field)){$state.$field=@($Request[$field])}}
  $script:LastRequest=$Request;Write-LocalJson $script:StateFile $state
  return [pscustomobject]@{ok=$true;stateHash=(Read-RuleMaintenanceFile $script:StateFile).TextHash}
 }
 $ingresses=@($state.programIngresses|ForEach-Object {$entry=Copy-RoutingSnapshot $_;$entry|Add-Member NoteProperty loaded (-not $script:RejectReadiness);$entry|Add-Member NoteProperty ready (-not $script:RejectReadiness);$entry|Add-Member NoteProperty effectiveRoute $(if($_.route -eq 'Follow'){$state.defaultRoute}else{$_.route});$entry})
 [pscustomobject]@{available=$true;rulesAvailable=$true;defaultLoaded=$true;effectiveDefaultRoute=$state.defaultRoute;programIngresses=$ingresses;siteRulesLoaded=$true}
}
$dir=Join-Path $qa 'fixture';[void][IO.Directory]::CreateDirectory($dir)
$exe=Join-Path $dir 'fixture.exe';Copy-Item -LiteralPath (Join-Path $env:WINDIR 'System32\whoami.exe') -Destination $exe
foreach($name in @('resources.pak','chrome_100_percent.pak')){[IO.File]::WriteAllText((Join-Path $dir $name),'fixture')}
$a=Set-ManagedApplicationRoute $exe 'a';$first=Get-ManagedProgramIngress $exe
Check ($a.Managed -and $first.id -cmatch '^[a-f0-9]{32}$' -and $first.route -eq 'a') 'Normal application selection creates a stable entrance'
Check ($script:LastRequest.resetIngressSelections -contains $first.id) 'Explicit selection resets only the requested program selector'
$aPlan=Get-ProgramLaunchPlan $exe 'a'
Set-ManagedApplicationRoute $exe 'b'|Out-Null;$b=Get-ManagedProgramIngress $exe;$bPlan=Get-ProgramLaunchPlan $exe 'b'
Check ($first.id -ceq $b.id -and $first.port -eq $b.port -and $aPlan.Endpoint -ceq $bPlan.Endpoint) 'A to B keeps exact child environment and Chromium endpoint stable'
Check ($bPlan.Environment.HTTPS_PROXY -ceq $aPlan.Environment.HTTPS_PROXY -and $bPlan.Environment.NO_PROXY -eq 'localhost,127.0.0.1,::1') 'Children inherit stable proxy with explicit loopback bypass'
Set-ManagedApplicationRoute $exe 'Direct'|Out-Null;$direct=Get-ProgramLaunchPlan $exe 'Direct'
Check ($direct.Endpoint -ceq $aPlan.Endpoint -and $direct.Arguments -notcontains '--no-proxy-server') 'Direct remains behind stable entrance so subsequent proxy switch works'
Set-ManagedApplicationRoute $exe 'Follow'|Out-Null
Check ((Get-ManagedProgramIngress $exe).port -eq $first.port) 'Follow retains entrance instead of disabling running applications'
$read=Get-WebsiteRules
$rules=@(@{Id='';Domain='EXAMPLE.com.';Match='suffix';Route='Direct';Executable=''},@{Id='';Domain='login.example.com';Match='exact';Route='b';Executable=$exe})
Set-WebsiteRules $rules $read.Revision|Out-Null
$sites=Get-WebsiteRules
Check ($sites.Entries.Count -eq 2 -and $sites.Entries[0].Domain -eq 'example.com' -and $sites.Entries[1].Executable -eq $exe) 'Website rules round-trip global and program scope'
Check (-not $script:LastRequest.ContainsKey('resetIngressSelections')) 'Website changes do not reset active failover selections'
Throws {Set-WebsiteRules @() $read.Revision} '已改变'
Throws {Set-WebsiteRules @(@{Domain='https://example.com/?code=SECRET';Match='exact';Route='a'}) $sites.Revision} '只输入域名'
Throws {Set-WebsiteRules @(@{Domain='*.example.com';Match='suffix';Route='a'}) $sites.Revision} '只输入域名'
Throws {Set-WebsiteRules @(@{Domain='127.0.0.1';Match='exact';Route='a'}) $sites.Revision} 'IP'
Throws {Set-WebsiteRules @(@{Domain='example.com';Match='exact';Route='gateway'}) $sites.Revision} '有效上游'
Throws {Set-WebsiteRules @(@{Domain='example.com';Match='exact';Route='a';Executable=(Join-Path $qa 'unknown.exe')}) $sites.Revision} '先为这个程序'
Throws {Set-WebsiteRules @(@{Domain='example.com';Match='exact';Route='a'},@{Domain='EXAMPLE.COM';Match='exact';Route='b'}) $sites.Revision} '重复'
$before=Get-RoutingSnapshot;$plan=Get-UnifiedPlan 'b' $before
Check ($plan.Routing.programIngresses[0].route -eq 'Follow' -and $plan.Routing.siteRules.Count -eq 2) 'Unified switching retains stable entrances and website exceptions'
$oldTarget=[pscustomobject]@{entries=@();defaultRoute='b'}
Set-RoutingSnapshot $oldTarget $before
Check ((Get-RoutingSnapshot).siteRules.Count -eq 2 -and (Get-RoutingSnapshot).programIngresses[0].id -ceq $first.id) 'Legacy snapshot without new fields cannot erase website or entrance records'
$before=Get-RoutingSnapshot;$script:RejectReadiness=$true
Throws {Set-ManagedApplicationRoute $exe 'a'} '未通过实读校验'
$script:RejectReadiness=$false
Check (Test-SameRouting $before (Get-RoutingSnapshot)) 'Failed loaded/listening check rolls back complete policy'
$script:RejectProbe=$true;Throws {Set-ManagedApplicationRoute $exe 'b'} '检测未通过';$script:RejectProbe=$false
Check (Test-SameRouting $before (Get-RoutingSnapshot)) 'Unreachable upstream does not mutate routing'
$script:FailObservation=$true;$committed=Set-ManagedApplicationRoute $exe 'b';$script:FailObservation=$false
Check ($committed.ObservationUnknown -and $committed.Backup -and (Get-ManagedProgramIngress $exe).route -eq 'b') 'Post-commit observation failure preserves switch result and backup'
$before=Get-RoutingSnapshot
$changed=Copy-RoutingSnapshot $before;$changed.siteRules[0].route='a'
Check (-not (Test-SameRouting $before $changed)) 'Routing ownership includes website policy'
$changed=Copy-RoutingSnapshot $before;$changed.programIngresses[0].port++
Check (-not (Test-SameRouting $before $changed)) 'Routing ownership includes stable entrance port'
$remove=Copy-RoutingSnapshot $script:Profiles;$remove.Profiles=@($remove.Profiles|Where-Object Id -ne 'b')
Throws {Save-ProfileSettings $remove} '仍被'
Throws {Remove-SavedProgramRule $exe} '网站例外'
$before=Get-RoutingSnapshot
$pak=Join-Path $dir 'resources.pak';[IO.File]::Delete($pak)
Throws {Set-ManagedApplicationRoute $exe 'b'} '已无法核验原启动适配'
Check (Test-SameRouting $before (Get-RoutingSnapshot)) 'Missing resources on a previously managed program preserves its entry without recursive fallback'
[IO.File]::WriteAllText($pak,'fixture')
$sites=Get-WebsiteRules
$sitesBefore=(Get-RoutingSnapshot).siteRules|ConvertTo-Json -Depth 16 -Compress
function Ensure-ManagedGateway {
 $state=Get-Content -LiteralPath $script:StateFile -Raw -Encoding UTF8|ConvertFrom-Json
 $state.programIngresses[0].path=Join-Path $qa 'changed-program.exe'
 Write-LocalJson $script:StateFile $state
}
Throws {Set-WebsiteRules $sites.Entries $sites.Revision} '程序入口已改变'
Check (((Get-RoutingSnapshot).siteRules|ConvertTo-Json -Depth 16 -Compress) -ceq $sitesBefore) 'Program scope changed during startup cannot receive stale website policy'
Write-Output ('PASS: '+$checks+' stable entrance, domain policy, CAS, rollback and compatibility checks; Windows and process launch are stubbed.')
