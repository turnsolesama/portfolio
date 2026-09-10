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
$result=Set-SelectedProxy 'alpha'
Assert ($script:SavedSelection.Unified -and $script:SavedRules.defaultRoute -eq 'alpha' -and $script:SavedRules.entries.Count -eq 0) 'Full unified action clears exceptions and records intended network'
Assert ((Get-SystemKey $script:SavedSystem) -eq 'alpha' -and (Test-SameEnv $script:SavedEnv $targetEnv)) 'Full unified action synchronizes Windows and environment'
$script:SavedSystem=$before;$script:SavedEnv=$beforeEnv;$script:SavedRules=$beforeRules;$script:SavedSelection=$null
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
Write-Output ('PASS: ' + $script:Pass + ' assertions; no real network settings written.')
