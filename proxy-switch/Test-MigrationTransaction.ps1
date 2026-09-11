$ErrorActionPreference='Stop'
$qa=Join-Path $env:TEMP ('FlowSwitch-migration-transaction-'+[Guid]::NewGuid().ToString('N'))
. (Join-Path $PSScriptRoot 'ProxyBackend.ps1') -DataDirectory (Join-Path $qa 'bootstrap')
$checks=0
function Check($Value,[string]$Message){if(-not $Value){throw $Message};$script:checks++}
function Bytes([string]$Path){$image=Read-RuleMaintenanceFile $Path;if(-not $image.Exists){return '<missing>'};[Convert]::ToBase64String($image.Bytes)}
function Write-FixtureJson([string]$Path,$Value){[IO.File]::WriteAllText($Path,(($Value|ConvertTo-Json -Depth 16)+"`r`n"),(New-Object Text.UTF8Encoding($true)))}
function Use-ChangeLock([scriptblock]$Action){& $Action}
function Get-SystemSnapshot {[pscustomobject]@{Flags=1;Server='';Bypass='localhost'}}
function Get-UserProxyEnv {[pscustomobject]@{HTTP_PROXY=$null;HTTPS_PROXY=$null;ALL_PROXY=$null;NO_PROXY='localhost'}}
function Get-Selection {$null}
function Get-ClientInterference {[pscustomobject]@{Tun=$false;Guard=$false;SystemProxy=$false}}
function Get-NodeRuntimePath {Join-Path $env:WINDIR 'System32\whoami.exe'}
function Get-IndependentCoreSource {Join-Path $env:WINDIR 'System32\whoami.exe'}
function Get-NetTCPConnection {param($State,$LocalPort);@()}
function Set-SystemSnapshot {throw 'Must not write Windows settings'}
function Set-UserProxyEnv {throw 'Must not write user environment'}
function Set-ProgramLaunchEntries {throw 'Migration must use byte-owned launch CAS, without shortcut side effects'}
function Test-ProxyRoute {
    param($Key,[switch]$Fast)
    if($script:PreflightEdit -and $Key -eq 'b' -and -not $script:Edited){
        [IO.File]::AppendAllText($script:Files[$script:PreflightEdit],"`r`n ");$script:Edited=$true
        $script:OutsideBytes=Bytes $script:Files[$script:PreflightEdit]
    }
    if($script:Failure -eq 'launch-before-write' -and $Key -eq 'gateway'){
        [IO.File]::AppendAllText($script:Files.launch,"`r`n ");$script:OutsideBytes=Bytes $script:Files.launch
    }
    [pscustomobject]@{Usable=$true}
}
function Start-IndependentProtection {
    param($OwnerPID,$BeforeSystem,$BeforeEnv,$TargetSystem,$TargetEnv)
    [IO.File]::WriteAllText((Get-IndependentSessionPath),'{}')
    if($script:Failure -eq 'launch-after-write'){
        [IO.File]::AppendAllText($script:Files.launch,"`r`n ");$script:OutsideBytes=Bytes $script:Files.launch
    }
    if($script:Failure -eq 'launch-locked'){$script:LaunchLock=New-Object IO.FileStream($script:Files.launch,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)}
    if($script:Failure -in @('protection','launch-after-write','launch-locked')){throw 'Injected protection failure'}
}
function Restore-IndependentSession {$script:Restores++;[IO.File]::Delete((Get-IndependentSessionPath))}
function Invoke-ProxyTransaction {
    param($TargetSystem,$TargetEnv,$Selection,$BeforeSystem,$BeforeEnv,$BackupRouting)
    $script:Commits++;'isolated-backup'
}
function Invoke-AppRouter {
    param($Request,[int]$TimeoutMilliseconds=55000)
    $script:Actions+=@($Request.action)
    if($Request.action -eq 'start'){return [pscustomobject]@{ok=$true}}
    if($Request.action -eq 'status'){return [pscustomobject]@{available=$true;defaultLoaded=$true;effectiveDefaultRoute='b'}}
    if($Request.action -ne 'replace'){throw 'Unexpected router action'}
    $current=Read-RuleMaintenanceFile $script:Files.state;$expected=$current.TextHash
    if(-not $current.Exists){$expected=Get-RuleMaintenanceHash ([Text.Encoding]::UTF8.GetBytes('<missing>'))}
    Check ($Request.expectedStateHash -cmatch '^[a-f0-9]{64}$' -and $Request.expectedStateHash -ceq $expected) 'Controller CAS uses a SHA256 even for a missing state file'
    $state=[pscustomobject]@{version=3;installed=$true;entries=@($Request.entries);defaultRoute=$Request.defaultRoute;programIngresses=@($Request.programIngresses);siteRules=@($Request.siteRules)}
    $hash=Set-MigrationJson $script:Files.state $state $current.TextHash
    [pscustomobject]@{ok=$true;stateHash=$hash}
}
function Initialize-Scenario([string]$Name,[switch]$Missing){
    $script:DataRoot=Join-Path $qa $Name;[void][IO.Directory]::CreateDirectory($script:DataRoot)
    $script:ConfigPath=Join-Path $script:DataRoot 'config.json';$script:BackupDir=Join-Path $script:DataRoot 'backups'
    $script:Files=@{config=$script:ConfigPath;state=(Join-Path $script:DataRoot 'app-rules.json');launch=(Join-Path $script:DataRoot 'program-proxies.json')}
    $config=[pscustomobject]@{Version=3;Profiles=@(
        @{Id='gateway';Name='Gateway';Protocol='http';Host='127.0.0.1';Port=18790;CorePath=(Join-Path $env:WINDIR 'System32\whoami.exe')},
        @{Id='a';Name='A';Protocol='http';Host='127.0.0.1';Port=18791},
        @{Id='b';Name='B';Protocol='http';Host='127.0.0.1';Port=18792}
    );Routing=@{Adapter='standalone';ProfileId='gateway';UnifiedMode='gateway'}}
    Write-FixtureJson $script:Files.config $config
    if(-not $Missing){
        Write-FixtureJson $script:Files.state @{version=3;installed=$true;entries=@();defaultRoute='a';programIngresses=@();siteRules=@()}
        Write-FixtureJson $script:Files.launch @{version=1;entries=@(@{path=(Join-Path $qa 'fixture.exe');route='a';adapter='chromium'});localMetadata='retain'}
    }
    $script:Before=@{};foreach($key in $script:Files.Keys){$script:Before[$key]=Bytes $script:Files[$key]}
    $script:Failure='';$script:PreflightEdit='';$script:Edited=$false;$script:OutsideBytes='';$script:Actions=@();$script:Commits=0;$script:Restores=0;$script:LaunchLock=$null
}
function Fail-Migration([string]$Pattern){
    $message='';try{Enable-IndependentGateway -OwnerPID $PID -InitialRoute b -UnifiedSwitch|Out-Null}catch{$message=$_.Exception.Message}
    Check ($message -match $Pattern) ('Expected '+$Pattern+', got '+$message)
}

Initialize-Scenario 'missing-success' -Missing
$result=Enable-IndependentGateway -OwnerPID $PID -InitialRoute b -UnifiedSwitch
Check ($result.Key -eq 'b' -and $script:Commits -eq 1) 'Missing standalone app-rules supports cold startup and an explicit switch'
Check ((Get-Content -LiteralPath $script:Files.state -Raw|ConvertFrom-Json).defaultRoute -eq 'b') 'Cold start saves the verified selected default'

foreach($key in @('config','state','launch')){
    Initialize-Scenario ('preflight-'+$key);$script:PreflightEdit=$key
    Fail-Migration '预检期间已改变'
    Check ($script:Edited -and $script:Actions.Count -eq 0 -and $script:Commits -eq 0) ('Concurrent '+$key+' preflight write aborts before core or controller mutation')
    foreach($name in $script:Files.Keys){$expected=$script:Before[$name];if($name -eq $key){$expected=$script:OutsideBytes};Check ((Bytes $script:Files[$name]) -ceq $expected) ('Preflight race preserves latest '+$name+' bytes')}
}

foreach($missing in @($false,$true)){
    Initialize-Scenario ('rollback-'+$missing) -Missing:$missing;$script:Failure='protection'
    Fail-Migration '已恢复启用前设置'
    foreach($name in $script:Files.Keys){Check ((Bytes $script:Files[$name]) -ceq $script:Before[$name]) ('Rollback restores original BOM/CRLF or missing '+$name+' image')}
    Check ($script:Restores -eq 1 -and [IO.File]::Exists((Join-Path $script:DataRoot 'gateway\stop')) -and $script:Commits -eq 0) 'Protection failure still restores owned session and requests owned core stop'
}

Initialize-Scenario 'launch-concurrent-forward';$script:Failure='launch-before-write'
Fail-Migration '已改变'
Check ((Bytes $script:Files.launch) -ceq $script:OutsideBytes -and $script:Commits -eq 0) 'Launch CAS preserves a newer record introduced after route verification'
foreach($name in @('config','state')){Check ((Bytes $script:Files[$name]) -ceq $script:Before[$name]) ('Failed launch write restores original '+$name+' bytes')}

foreach($scenarioFailure in @('launch-after-write','launch-locked')){
    Initialize-Scenario $scenarioFailure;$script:Failure=$scenarioFailure
    try{
        Fail-Migration '迁移回滚未完成.*程序启动记录'
        foreach($name in @('config','state')){Check ((Bytes $script:Files[$name]) -ceq $script:Before[$name]) ('Launch rollback failure still restores '+$name+' bytes')}
        Check ($script:Restores -eq 1 -and [IO.File]::Exists((Join-Path $script:DataRoot 'gateway\stop')) -and $script:Commits -eq 0) 'Unreadable or externally changed launch file cannot skip safe service cleanup'
        if($scenarioFailure -eq 'launch-after-write'){Check ((Bytes $script:Files.launch) -ceq $script:OutsideBytes) 'Rollback preserves the externally modified launch record'}
    }finally{if($script:LaunchLock){$script:LaunchLock.Dispose();$script:LaunchLock=$null}}
}
Write-Output ('PASS: '+$checks+' migration snapshot, missing-state protocol, launch CAS and raw rollback checks; isolated files, no live core, Windows writes or user processes.')
