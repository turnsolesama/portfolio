$ErrorActionPreference='Stop'
$env:PROXY_SWITCH_DATA_DIR=Join-Path $env:TEMP ('ProxySwitch-unit-'+[Guid]::NewGuid().ToString('N'))
. (Join-Path $PSScriptRoot 'ProxyBackend.ps1')
$script:Profiles=[pscustomobject]@{Version=3;Profiles=@(
    [pscustomobject]@{Id='alpha';Name='办公';Protocol='http';Host='127.0.0.1';Port=7897},
    [pscustomobject]@{Id='beta';Name='备用';Protocol='http';Host='127.0.0.1';Port=29758},
    [pscustomobject]@{Id='socks';Name='远程 SOCKS';Protocol='socks5';Host='192.0.2.1';Port=1080}
);Routing=[pscustomobject]@{Adapter='clash-verge';ProfileId='alpha'}}
function Get-ClientInterference {[pscustomobject]@{Running=$false;Tun=$false;Guard=$false;SystemProxy=$false}}
$script:Pass=0
function Assert($Condition,[string]$Message){if(-not $Condition){throw $Message};$script:Pass++}
function Assert-Throws([scriptblock]$Action,[string]$Pattern){
    $caught=$null;try{& $Action | Out-Null}catch{$caught=$_.Exception.Message}
    Assert ($caught -and $caught -match $Pattern) ('Expected failure: ' + $Pattern + '; got: ' + $caught)
}
# All mutation boundaries are replaced with in-memory stubs.
$script:SavedSystem=[pscustomobject]@{Flags=3;Server='localhost:29758';Bypass='<local>;127.*'}
$script:SavedEnv=[pscustomobject]@{HTTP_PROXY='http://127.0.0.1:29758';HTTPS_PROXY='http://127.0.0.1:29758';ALL_PROXY=$null;NO_PROXY='localhost,127.0.0.1,example.local'}
$script:SavedSelection=$null;$script:Writes=0;$script:Backups=0;$script:FailSystem=$false;$script:FailEnv=$false;$script:FailSelection=$false
function Get-SystemSnapshot{$script:SavedSystem}
function Set-SystemSnapshot($Snapshot){$script:Writes++;if($script:FailSystem){$script:FailSystem=$false;throw 'test native failure'};$script:SavedSystem=$Snapshot}
function Get-UserProxyEnv{$script:SavedEnv}
function Set-UserProxyEnv($Values){$script:Writes++;$script:SavedEnv=$Values;if($script:FailEnv){$script:FailEnv=$false;throw 'test env failure'}}
function Get-Selection{$script:SavedSelection}
function Save-Selection($Selection){if($script:FailSelection){$script:FailSelection=$false;throw 'test selection failure'};$script:SavedSelection=$Selection}
function Save-Backup($Snapshot){$script:Backups++;return 'in-memory-backup'}
function Get-Listener($Profile){[pscustomobject]@{PID=1;Name='test'}}
function Get-OverrideWarnings([string]$Key){}
function Get-ClientWarnings{}
function Get-LiveConnections{
    [pscustomobject]@{Process='codex';PID=11;Route='beta';Count=2}
    [pscustomobject]@{Process='chrome';PID=12;Route='alpha';Count=1}
}
function Test-ProxyRoute([string]$Key){[pscustomobject]@{Name=$Key;Usable=$true}}

Assert ((Get-EndpointKey 'http://localhost:7897/') -eq 'alpha') 'localhost normalization'
Assert ((Get-EndpointKey 'http://127.0.0.1:29758') -eq 'beta') 'beta normalization'
Assert ((Get-EndpointKey '') -eq 'Unset') 'unset normalization'
Assert ((Protect-Endpoint 'http://user:secret@host:123/?token=secret') -notmatch 'secret') 'credentials must be hidden'
$before=$script:SavedSystem;$beforeEnv=$script:SavedEnv
$target=[pscustomobject]@{Flags=3;Server='127.0.0.1:7897';Bypass=$before.Bypass}
$targetEnv=New-EnvTarget $beforeEnv 'alpha'
Assert ($targetEnv.ALL_PROXY -eq 'http://127.0.0.1:7897') 'ALL_PROXY must align'
Assert ($targetEnv.NO_PROXY -match 'example.local' -and $targetEnv.NO_PROXY -match '::1') 'preserve bypass and add loopback'
$direct=New-EnvTarget $targetEnv 'Direct'
Assert ($null -eq $direct.HTTP_PROXY -and $null -eq $direct.HTTPS_PROXY -and $null -eq $direct.ALL_PROXY) 'Direct must clear all three variables'
Assert ($direct.NO_PROXY -eq $targetEnv.NO_PROXY) 'Direct preserves exclusions'
$selection=[pscustomobject]@{Key='alpha'}
Invoke-ProxyTransaction $target $targetEnv $selection $before $beforeEnv | Out-Null
Assert ((Test-SameSnapshot $target $script:SavedSystem) -and (Test-SameEnv $targetEnv $script:SavedEnv)) 'success must update both'
Assert ($script:SavedSelection.Key -eq 'alpha' -and $script:Backups -eq 1) 'selection saved after backup'
$state=Get-ProxyStatus
Assert ($state.Aligned -and $state.OldConnections.Count -eq 1 -and $state.OldConnections[0].Process -eq 'codex') 'must expose old Codex connections'
$script:SavedSystem=$before
$state=Get-ProxyStatus
Assert ($state.Drift -and -not $state.Aligned) 'must detect outside rewrite'
$n=$script:Writes
Assert-Throws {Invoke-ProxyTransaction $target $targetEnv $selection $target $targetEnv} '其他程序'
Assert ($script:Writes -eq $n) 'race before write must not mutate'
$script:SavedEnv=$beforeEnv;$script:SavedSelection=$null
foreach($failure in @('FailSystem','FailEnv','FailSelection')){
    Set-Variable -Scope Script -Name $failure -Value $true
    Assert-Throws {Invoke-ProxyTransaction $target $targetEnv $selection $before $beforeEnv} '已恢复'
    Assert ((Test-SameSnapshot $before $script:SavedSystem) -and (Test-SameEnv $beforeEnv $script:SavedEnv) -and $null -eq $script:SavedSelection) ('rollback: ' + $failure)
}
function Test-ProxyRoute([string]$Key){[pscustomobject]@{Name=$Key;Usable=$false}}
$n=$script:Writes
Assert-Throws {Set-SelectedProxy 'beta'} '检测未通过'
Assert ($script:Writes -eq $n) 'failed probe must not mutate'
$realGetRoutingSnapshot=${function:Get-RoutingSnapshot};$realSetRoutingSnapshot=${function:Set-RoutingSnapshot}
function Get-RoutingSnapshot{$script:SavedRules}
function Set-RoutingSnapshot($Snapshot){if($script:FailRouting){$script:FailRouting=$false;throw 'router validation failure'};$script:SavedRules=$Snapshot}
$script:SavedSystem=$before;$script:SavedEnv=$beforeEnv;$script:SavedSelection=$null
$script:SavedRules=[pscustomobject]@{entries=@([pscustomobject]@{path='C:\Apps\editor.exe';route='beta'});defaultRoute=$null;installed=$true}
$beforeRules=$script:SavedRules
$nextRules=[pscustomobject]@{entries=@();defaultRoute='alpha';installed=$true}
$plan=Get-UnifiedPlan 'alpha' $beforeRules
Assert ($plan.Routing.entries.Count -eq 0 -and $plan.ClearedRules -eq 1 -and $plan.Routing.defaultRoute -eq 'alpha') 'Unified plan removes individual exceptions and adds catch-all'
$plan=Get-UnifiedPlan 'Direct' $beforeRules
Assert ($plan.Entrance -eq 'Direct' -and -not $plan.Routing.defaultRoute) 'Direct removes managed routing and bypasses proxy'
$script:FailSelection=$true
Assert-Throws {Invoke-ProxyTransaction $target $targetEnv $selection $before $beforeEnv $nextRules $beforeRules} '已恢复'
Assert ((Test-SameRouting $script:SavedRules $beforeRules) -and (Test-SameEnv $script:SavedEnv $beforeEnv)) 'Failed final step restores routing and environment together'
$script:FailRouting=$true
Assert-Throws {Invoke-ProxyTransaction $target $targetEnv $selection $before $beforeEnv $nextRules $beforeRules} '已恢复'
Assert ((Test-SameRouting $script:SavedRules $beforeRules) -and (Test-SameSnapshot $script:SavedSystem $before)) 'Failed rule application preserves system and app rules'
$n=$script:Writes
Assert-Throws {Invoke-ProxyTransaction $target $targetEnv $selection $before $beforeEnv $nextRules $beforeRules {throw 'actual route unavailable'}} '已恢复'
Assert ((Test-SameRouting $script:SavedRules $beforeRules) -and $script:Writes -eq $n) 'Failed actual routing probe restores rules without touching Windows'
$outside=[pscustomobject]@{Flags=1;Server='';Bypass='changed-elsewhere'}
Assert-Throws {Invoke-ProxyTransaction $target $targetEnv $selection $before $beforeEnv $nextRules $beforeRules {$script:SavedSystem=$outside}} '已恢复'
Assert ((Test-SameSnapshot $script:SavedSystem $outside) -and (Test-SameRouting $script:SavedRules $beforeRules)) 'External change before native write must be preserved'
$script:SavedSystem=$before
Invoke-ProxyTransaction $target $targetEnv $selection $before $beforeEnv $nextRules $beforeRules | Out-Null
Assert ($script:SavedRules.entries.Count -eq 0 -and $script:SavedRules.defaultRoute -eq 'alpha') 'Unified write changes rules and system as one operation'
$script:SavedSystem=$before;$script:SavedEnv=$beforeEnv;$script:SavedRules=$beforeRules;$script:SavedSelection=$null
function Test-ProxyRoute([string]$Key){[pscustomobject]@{Name=$Key;Usable=$true}}
function Invoke-AppRouter($Request){[pscustomobject]@{available=$true;defaultLoaded=$true;defaultRoute=$script:SavedRules.defaultRoute}}
$result=Set-SelectedProxy 'alpha'
Assert ($script:SavedSelection.Unified -and $script:SavedRules.defaultRoute -eq 'alpha' -and $script:SavedRules.entries.Count -eq 0) 'Full unified action clears exceptions and records intended network'
Assert ((Get-SystemKey $script:SavedSystem) -eq 'alpha' -and (Test-SameEnv $script:SavedEnv $targetEnv)) 'Full unified action synchronizes Windows and environment'
$script:SavedSystem=$before;$script:SavedEnv=$beforeEnv;$script:SavedRules=$beforeRules;$script:SavedSelection=$null
function Invoke-AppRouter($Request){[pscustomobject]@{available=$true;defaultLoaded=$true;defaultRoute='wrong-route'}}
Assert-Throws {Set-SelectedProxy 'alpha'} '目标规则尚未通过实读校验'
Assert ((Test-SameSnapshot $script:SavedSystem $before) -and (Test-SameRouting $script:SavedRules $beforeRules)) 'Wrong actual route cannot be reported successful or committed to Windows'
function Invoke-AppRouter($Request){[pscustomobject]@{available=$true;defaultLoaded=$true;defaultRoute=$script:SavedRules.defaultRoute}}
function Test-ProxyRoute([string]$Key){[pscustomobject]@{Name=$Key;Usable=$false}}
Assert-Throws {Set-SelectedProxy 'alpha'} '实际检测未通过'
Assert ((Test-SameRouting $script:SavedRules $beforeRules) -and (Test-SameSnapshot $script:SavedSystem $before) -and (Test-SameEnv $script:SavedEnv $beforeEnv)) 'Failed post-application probe restores full original network'
$script:Profiles.Routing=[pscustomobject]@{Adapter='none';ProfileId=''}
$emptyRules=[pscustomobject]@{entries=@();defaultRoute=$null;installed=$false}
$plan=Get-UnifiedPlan 'beta' $emptyRules
Assert ($plan.Entrance -eq 'beta' -and -not $plan.Routing.defaultRoute) 'HTTP unified switch works without any gateway'
Assert-Throws {Get-UnifiedPlan 'socks' $emptyRules} 'SOCKS5'
Assert-Throws {Get-UnifiedPlan 'alpha' $beforeRules} '已有程序规则'
Assert ((Get-EndpointKey 'http://user:password@localhost:7897') -eq 'Other') 'Credential-bearing endpoint not misidentified'
Assert ((Get-EndpointKey 'http://localhost:7897/path') -eq 'Other') 'Nonproxy URI path rejected'

# Engine identity metadata is part of ownership, regardless of JSON property order.
$identityRules=[pscustomobject]@{entries=@([pscustomobject]@{path='C:\Apps\editor.exe';route='alpha';identity=[pscustomobject][ordered]@{Version=1;Kind='File';Path='C:\Apps\editor.exe';FileId='owned-file'}});defaultRoute='alpha';launchEntries=@()}
$reordered=$identityRules|ConvertTo-Json -Depth 12|ConvertFrom-Json
$reordered.entries[0].identity=[pscustomobject][ordered]@{FileId='owned-file';Path='C:\Apps\editor.exe';Kind='File';Version=1}
Assert (Test-SameRouting $identityRules $reordered) 'Identity property order does not make an owned rule appear changed'
$outsideIdentity=$identityRules|ConvertTo-Json -Depth 12|ConvertFrom-Json;$outsideIdentity.entries[0].identity.FileId='outside-file'
Assert (-not (Test-SameRouting $identityRules $outsideIdentity)) 'Changed identity metadata is an external rule modification'
$script:SavedRules=$beforeRules;$script:SavedSystem=$before;$script:SavedEnv=$beforeEnv;$script:SavedSelection=$null;$n=$script:Writes
Assert-Throws {Invoke-ProxyTransaction $target $targetEnv $selection $before $beforeEnv $identityRules $beforeRules {$script:SavedRules=$outsideIdentity;throw 'isolated verification failure'}} '保留其他程序'
Assert ($script:SavedRules.entries[0].identity.FileId -eq 'outside-file' -and $script:Writes -eq $n) 'Rollback preserves an outside metadata-only edit without writing Windows settings'

# Real routing snapshot writer, isolated data files, and a conditional engine boundary.
${function:Get-RoutingSnapshot}=$realGetRoutingSnapshot;${function:Set-RoutingSnapshot}=$realSetRoutingSnapshot
[void][IO.Directory]::CreateDirectory($script:DataRoot)
$fixtureConfig=ConvertTo-ValidProfileSettings $script:Profiles
Write-LocalJson $script:ConfigPath $fixtureConfig
$appStatePath=Join-Path $script:DataRoot 'app-rules.json';$script:Race='';$script:RouterCalls=0
function Write-FixtureRouting($Value){Write-LocalJson $appStatePath ([pscustomobject]@{version=2;installed=$true;entries=@($Value.entries);defaultRoute=$Value.defaultRoute})}
function Invoke-AppRouter($Request){
    $script:RouterCalls++
    if($Request.action -ne 'replace'){throw 'Unexpected fixture engine action'}
    if($script:Race -in @('rule','rollback')){Write-FixtureRouting $outsideIdentity;$script:Race=''}
    elseif($script:Race -eq 'settings'){$changed=$fixtureConfig|ConvertTo-Json -Depth 10|ConvertFrom-Json;$changed.Profiles[0].Port=17898;Write-LocalJson $script:ConfigPath $changed;$script:Race=''}
    $stateImage=Read-RuleMaintenanceFile $appStatePath;$settingsImage=Read-RuleMaintenanceFile $script:ConfigPath
    if($Request.expectedStateHash -cne $stateImage.TextHash -or $Request.expectedSettingsHash -cne $settingsImage.TextHash){throw 'fixture CAS rejected an external edit'}
    Write-FixtureRouting $Request
    [pscustomobject]@{ok=$true;stateHash=(Read-RuleMaintenanceFile $appStatePath).TextHash}
}
Write-FixtureRouting $beforeRules
$baseline=Get-RoutingSnapshot
Set-RoutingSnapshot $identityRules $baseline
Assert ((Test-SameRouting (Get-RoutingSnapshot) $identityRules) -and $script:RouterCalls -eq 1) 'Ordinary replace carries matching state and settings hashes from one snapshot'
Write-FixtureRouting $beforeRules;$baseline=Get-RoutingSnapshot;$script:Race='rule';$n=$script:Writes
Assert-Throws {Set-RoutingSnapshot $identityRules $baseline} 'CAS rejected'
Assert ((Get-RoutingSnapshot).entries[0].identity.FileId -eq 'outside-file' -and $script:Writes -eq $n) 'A rule edit between PowerShell validation and Node execution is not overwritten'
Write-FixtureRouting $beforeRules;$baseline=Get-RoutingSnapshot;$script:Race='settings'
Assert-Throws {Set-RoutingSnapshot $identityRules $baseline} 'CAS rejected'
Assert ((Get-Content -LiteralPath $script:ConfigPath -Raw|ConvertFrom-Json).Profiles[0].Port -eq 17898 -and (Test-SameRouting (Get-RoutingSnapshot) $baseline)) 'A settings edit before Node execution preserves the newer settings and original rules'
$calls=$script:RouterCalls
Assert-Throws {Set-RoutingSnapshot $identityRules $baseline} '配置已改变'
Assert ($script:RouterCalls -eq $calls) 'A config changed before byte capture cannot silently replace the settings that produced the user action'
Write-LocalJson $script:ConfigPath $fixtureConfig
Write-FixtureRouting $outsideIdentity;$calls=$script:RouterCalls
Assert-Throws {Set-RoutingSnapshot $identityRules $baseline} '其他窗口改动'
Assert ($script:RouterCalls -eq $calls -and (Get-RoutingSnapshot).entries[0].identity.FileId -eq 'outside-file') 'ExpectedBefore rejects a changed snapshot before reaching the engine boundary'

# Inject an edit after the byte snapshot was captured. It must not be adopted as a new hash.
$realMaintenanceSnapshot=${function:Get-RuleMaintenanceSnapshot};$script:ChangeAfterSnapshot=$true
function Get-RuleMaintenanceSnapshot([string]$SavedPath){$value=& $realMaintenanceSnapshot $SavedPath;if($script:ChangeAfterSnapshot){$script:ChangeAfterSnapshot=$false;Write-FixtureRouting $outsideIdentity};$value}
Write-FixtureRouting $beforeRules;$baseline=Get-RoutingSnapshot
Assert-Throws {Set-RoutingSnapshot $identityRules $baseline} 'CAS rejected'
Assert ((Get-RoutingSnapshot).entries[0].identity.FileId -eq 'outside-file') 'CAS hash is bound to the parsed snapshot bytes rather than a later reread'
${function:Get-RuleMaintenanceSnapshot}=$realMaintenanceSnapshot

Write-FixtureRouting $beforeRules;$baseline=Get-RoutingSnapshot;$script:SavedSystem=$before;$script:SavedEnv=$beforeEnv;$script:SavedSelection=$null;$n=$script:Writes
Assert-Throws {Invoke-ProxyTransaction $target $targetEnv $selection $before $beforeEnv $identityRules $baseline {$script:Race='rollback';throw 'isolated post-route verification failure'}} '回滚未完成'
Assert ((Get-RoutingSnapshot).entries[0].identity.FileId -eq 'outside-file' -and $script:Writes -eq $n) 'Rollback uses its own expected snapshot and refuses an edit arriving just before the engine undo'
Write-Output ('PASS: ' + $script:Pass + ' assertions; no real network settings written.')
