$ErrorActionPreference='Stop'
$env:PROXY_SWITCH_DATA_DIR=Join-Path $env:TEMP ('ProxySwitch-gateway-'+[Guid]::NewGuid().ToString('N'))
. (Join-Path $PSScriptRoot 'ProxyBackend.ps1')
function Get-ClientInterference {[pscustomobject]@{Running=$false;Tun=$false;Guard=$false;SystemProxy=$false}}
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
$exe=Join-Path $env:PROXY_SWITCH_DATA_DIR 'Fixture.exe';[void][IO.Directory]::CreateDirectory($env:PROXY_SWITCH_DATA_DIR);[IO.File]::WriteAllText((Join-Path $env:PROXY_SWITCH_DATA_DIR 'ui-settings.json'),'{"CloseToTray":false}');[IO.File]::WriteAllText($exe,'fixture only')
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
$script:Profiles=ConvertTo-ValidProfileSettings $value
$script:Profiles.Routing=[pscustomobject]@{Adapter='clash-verge';ProfileId='engine';UnifiedMode='gateway'}
function Get-ClientInterference {[pscustomobject]@{Running=$true;Tun=$true;Guard=$true;SystemProxy=$true}}
$script:Live=[pscustomobject]@{available=$true;mode='rule'}
function Invoke-AppRouter($Request){$script:Live}
Assert-ClientCompatibility 'engine' $true
Check $true 'Existing TUN is compatible with a verified fixed gateway'
Throws {Assert-ClientCompatibility 'upstream' $false} 'TUN'
$script:Profiles.Routing.UnifiedMode='system'
Throws {Assert-ClientCompatibility 'engine' $true} 'TUN'
$script:Profiles.Routing.UnifiedMode='gateway';$script:Live.mode='global'
Throws {Assert-ClientCompatibility 'engine' $true} '规则模式'
$script:Live.mode='rule';$script:Live.available=$false
Throws {Assert-ClientCompatibility 'engine' $true} '尚未就绪'
$profile=[pscustomobject]@{Id='engine';CorePath='C:\Fixture\verge-mihomo.exe'}
$owner=[pscustomobject]@{Id=42;ProcessName='verge-mihomo';Path=''}
function Get-GatewayControllerPID {42}
Check (Test-GatewayServiceOwner $profile $owner) 'Elevated engine listener verified by named pipe owner PID'
$owner.Id=43
Check (-not (Test-GatewayServiceOwner $profile $owner)) 'Unrelated listener cannot impersonate the controller'
$owner.Id=42;$owner.Path='C:\Other\verge-mihomo.exe'
Check (-not (Test-GatewayServiceOwner $profile $owner)) 'Readable conflicting image path cannot bypass validation'
$owner.Path='';$profile.Id='upstream'
Check (-not (Test-GatewayServiceOwner $profile $owner)) 'Controller identity fallback restricted to configured gateway'
$script:Profiles.Routing.Adapter='standalone'
Check (Test-GatewayServiceOwner $profile $owner) 'Standalone mode recognizes an elevated Clash upstream by controller identity'
$owner.Id=43
Check (-not (Test-GatewayServiceOwner $profile $owner)) 'Standalone upstream still rejects another process identity'
$owner.Id=42;$owner.ProcessName='unrelated'
Check (-not (Test-GatewayServiceOwner $profile $owner)) 'Standalone upstream still requires the configured engine name'
$owner.ProcessName='verge-mihomo';$script:Profiles.Routing.Adapter='clash-verge'
$oldAppData=$env:APPDATA
try{
    $env:APPDATA=Join-Path $env:PROXY_SWITCH_DATA_DIR 'fresh computer'
    $folder=Join-Path $env:APPDATA 'io.github.clash-verge-rev.clash-verge-rev'
    [void][IO.Directory]::CreateDirectory($folder)
    [IO.File]::WriteAllText((Join-Path $folder 'verge.yaml'),"verge_mixed_port: 18081")
    $localCore=Join-Path $env:APPDATA 'verge-mihomo.exe'
    [IO.File]::WriteAllText($localCore,'fixture only')
    function Get-ProcessInventory {[pscustomobject]@{ProcessName='clash-verge';Path=(Join-Path $env:APPDATA 'clash-verge.exe')}}
    function Read-ProfileSettings {ConvertTo-ValidProfileSettings $value}
    function Save-ProfileSettings($Settings){$script:Configured=$Settings}
    $script:Live=[pscustomobject]@{available=$true;mode='rule'}
    Enable-LocalGateway | Out-Null
    Check ($script:Configured.Routing.UnifiedMode -eq 'gateway' -and $script:Configured.Profiles[0].CorePath -eq $localCore) 'Fresh computer uses local installation path and verified fixed gateway'
    $script:Configured=$null;$script:Live.available=$false
    Throws {Enable-LocalGateway} '检查失败'
    Check ($null -eq $script:Configured) 'Failed setup does not save settings'
}finally{$env:APPDATA=$oldAppData}
$tcp=[pscustomobject]@{path='C:\Fixture\client.exe';network='tcp';inbound='Tun';route='upstream'}
$udp=[pscustomobject]@{path=$tcp.path;network='udp';inbound='Tun';route='Direct'}
Check ((Find-EngineConnection @($tcp,$udp) $tcp.path).route -eq 'upstream') 'TUN observation separates TCP and UDP sharing a source port'
Check ($null -eq (Find-EngineConnection @($tcp) 'C:\Other\client.exe')) 'Same port on another executable cannot claim the route'
Check ($null -eq (Find-EngineConnection @($tcp,$tcp) $tcp.path)) 'Ambiguous connection identity remains unverified'
Write-Output ('PASS: '+$script:Pass+' gateway control assertions; no real settings or shortcuts changed.')
