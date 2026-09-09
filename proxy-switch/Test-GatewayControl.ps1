$ErrorActionPreference='Stop'
$env:PROXY_SWITCH_DATA_DIR=Join-Path $env:TEMP ('ProxySwitch-gateway-'+[Guid]::NewGuid().ToString('N'))
. (Join-Path $PSScriptRoot 'ProxyBackend.ps1')
$script:Pass=0
function Check($Condition,$Message){if(-not $Condition){throw $Message};$script:Pass++}
function Throws([scriptblock]$Action,[string]$Pattern){$message='';try{& $Action | Out-Null}catch{$message=$_.Exception.Message};Check ($message -match $Pattern) ('Expected '+$Pattern+', got '+$message)}
$value=[pscustomobject]@{Version=3;Profiles=@(
    [pscustomobject]@{Id='engine';Name='Engine';Protocol='http';Host='127.0.0.1';Port=18081;CorePath='C:\Fixture\core.exe'},
    [pscustomobject]@{Id='upstream';Name='Upstream';Protocol='http';Host='127.0.0.1';Port=18082},
    [pscustomobject]@{Id='socks';Name='Socks';Protocol='socks5';Host='127.0.0.1';Port=18083}
);Routing=[pscustomobject]@{Adapter='clash-verge';ProfileId='engine';UnifiedMode='gateway'}}
$script:Profiles=ConvertTo-ValidProfileSettings $value
Check ($script:Profiles.Routing.UnifiedMode -eq 'gateway') 'Explicit fixed entrance mode survives config normalization'
$script:Ready=$true
function Get-Listener($Profile){if($script:Ready){[pscustomobject]@{PID=1;Name='fixture'}}}
$rules=[pscustomobject]@{entries=@();defaultRoute=$null;installed=$false;launchEntries=@()}
foreach($route in @('Direct','engine','upstream','socks')){
    $plan=Get-UnifiedPlan $route $rules
    Check ($plan.Entrance -eq 'engine' -and $plan.Routing.defaultRoute -eq $route) ('Fixed entrance for '+$route)
}
$script:Ready=$false;Throws {Get-UnifiedPlan 'upstream' $rules} '固定入口';$script:Ready=$true
$script:Profiles.Routing.UnifiedMode='system'
Check ((Get-UnifiedPlan 'upstream' $rules).Entrance -eq 'upstream') 'Existing system mode remains opt-in compatible'
$script:Profiles.Routing.UnifiedMode='gateway'
$exe=Join-Path $env:PROXY_SWITCH_DATA_DIR 'Fixture.exe';[void][IO.Directory]::CreateDirectory($env:PROXY_SWITCH_DATA_DIR);[IO.File]::WriteAllText($exe,'fixture only')
$rules.launchEntries=@([pscustomobject]@{path=$exe;route='Direct';adapter='chromium'})
function Get-RoutingSnapshot {$rules}
function Get-SystemSnapshot {[pscustomobject]@{Flags=3;Server='127.0.0.1:18081';Bypass='localhost'}}
function Get-UserProxyEnv {[pscustomobject]@{HTTP_PROXY=$null;HTTPS_PROXY=$null;ALL_PROXY=$null;NO_PROXY='localhost'}}
function Get-ProgramProxyAdapter {throw 'Normal program routing must never create a native launcher'}
function Use-ChangeLock([scriptblock]$Action){& $Action}
function Invoke-ProxyTransaction($TargetSystem,$TargetEnv,$Selection,$BeforeSystem,$BeforeEnv,$TargetRouting,$BeforeRouting){$script:Captured=$TargetRouting;$script:CapturedSystem=$TargetSystem;'fixture-backup'}
$result=Set-ApplicationRoute $exe 'upstream'
Check ($script:Captured.entries[0].route -eq 'upstream' -and $script:CapturedSystem.Server -eq '127.0.0.1:18081') 'Program rule uses the engine and original executable, even for Chromium'
Check ($script:Captured.launchEntries[0].route -eq 'Follow') 'Legacy launch override no longer conflicts with engine rule'
Check (-not (Test-Path (Join-Path $env:PROXY_SWITCH_DATA_DIR 'program-shortcuts.json'))) 'Normal program route creates no shortcut'
$script:Profiles.Routing.Adapter='none';$script:Profiles.Routing.ProfileId=''
Throws {Set-ApplicationRoute $exe 'upstream'} '没有保存假规则'
Write-Output ('PASS: '+$script:Pass+' gateway control assertions; no real settings or shortcuts changed.')
