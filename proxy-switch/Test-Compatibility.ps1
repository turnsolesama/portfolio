$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProxyBackend.ps1')
$script:Pass=0
function Check($Value,[string]$Message){if(-not $Value){throw $Message};$script:Pass++}
function Throws([scriptblock]$Action,[string]$Pattern){$message='';try{& $Action | Out-Null}catch{$message=$_.Exception.Message};Check ($message -match $Pattern) ('Expected '+$Pattern+'; got '+$message)}
$script:Profiles=[pscustomobject]@{Version=3;Profiles=@(
    [pscustomobject]@{Id='alpha';Name='Engine';Protocol='http';Host='127.0.0.1';Port=7897;CorePath=''},
    [pscustomobject]@{Id='beta';Name='HTTP proxy';Protocol='http';Host='127.0.0.1';Port=29758;CorePath=''},
    [pscustomobject]@{Id='socks';Name='SOCKS proxy';Protocol='socks5';Host='127.0.0.1';Port=1080;CorePath=''}
);Routing=[pscustomobject]@{Adapter='clash-verge';ProfileId='alpha'}}
$script:System=[pscustomobject]@{Flags=3;Server='127.0.0.1:7897';Bypass=''}
$script:Environment=[pscustomobject]@{HTTP_PROXY=$null;HTTPS_PROXY=$null;ALL_PROXY=$null;NO_PROXY='localhost'}
$script:Selection=[pscustomobject]@{Key='alpha';NetworkKey='beta'}
$script:Rules=[pscustomobject]@{entries=@();defaultRoute=$null;installed=$false}
$script:Writes=0
function Get-SystemSnapshot {$script:System}
function Get-UserProxyEnv {$script:Environment}
function Get-Selection {$script:Selection}
function Get-RoutingSnapshot {$script:Rules}
function Get-ClientWarnings {}
function Get-OverrideWarnings {}
function Get-LiveConnections {}
function Set-SystemSnapshot($Value){$script:Writes++;$script:System=$Value;if($script:InjectSystem){$script:System=$script:Outside;$script:InjectSystem=$false}}
function Set-UserProxyEnv($Value){$script:Writes++;$script:Environment=$Value;if($script:InjectEnv){$script:Environment=$script:OutsideEnv;$script:InjectEnv=$false}}
function Save-Selection($Value){$script:Selection=$Value}
function Save-Backup {'in-memory-backup'}
function Set-RoutingSnapshot($Value){$script:Rules=$Value}

# Passive inventory must exclude game IPC and unrelated applications.
function Get-ProcessInventory {param($Id)
    $all=@(
        [pscustomobject]@{Id=10;ProcessName='CalabiYau';Path='';SessionId=1;MainWindowHandle=[IntPtr]1},
        [pscustomobject]@{Id=11;ProcessName='Upnet';Path='C:\Apps\Upnet.exe';SessionId=1;MainWindowHandle=[IntPtr]0},
        [pscustomobject]@{Id=12;ProcessName='Unrelated';Path='';SessionId=1;MainWindowHandle=[IntPtr]0}
    )
    if($Id){$all | Where-Object {$_.Id -eq $Id}}else{$all}
}
function Get-NetTCPConnection {param($State,$LocalPort)
    @(
        [pscustomobject]@{LocalAddress='127.0.0.1';LocalPort=44531;OwningProcess=10},
        [pscustomobject]@{LocalAddress='127.0.0.1';LocalPort=29758;OwningProcess=11},
        [pscustomobject]@{LocalAddress='127.0.0.1';LocalPort=8088;OwningProcess=12}
    ) | Where-Object {-not $LocalPort -or $_.LocalPort -eq $LocalPort}
}
$candidates=@(Get-ProxyDiscoveryListeners)
Check ($candidates.Count -eq 1 -and $candidates[0].Port -eq 29758) 'Never probe game IPC or unrelated user ports'
$saved=[pscustomobject]@{Id='custom';Name='Custom';Protocol='http';Host='127.0.0.1';Port=8088;CorePath=''}
$script:Profiles.Profiles+=@($saved)
Check (@(Get-ProxyDiscoveryListeners | Where-Object {$_.Port -eq 8088}).Count -eq 1) 'Explicitly configured unfamiliar proxy remains discoverable'

# A configured remote-looking loopback endpoint is a canary for accidental status probes.
$canary=New-Object Net.Sockets.TcpListener([Net.IPAddress]::Parse('127.0.0.2'),0);$canary.Start()
try{
    $script:Profiles.Profiles+=@([pscustomobject]@{Id='remote';Name='Remote';Protocol='http';Host='127.0.0.2';Port=$canary.LocalEndpoint.Port;CorePath=''})
    $state=Get-ProxyStatus
    Check (-not $canary.Pending()) 'Status sends no connections to remote endpoints'
    Check ($null -eq ($state.Listeners | Where-Object Key -eq 'remote').Ready) 'Remote status is unknown until explicitly tested'
    Check ($state.NetworkKey -eq 'alpha') 'Historical network selection cannot masquerade as the live route'
    $state=Get-ProxyStatus ([pscustomobject]@{Available=$true;DefaultLoaded=$true;DefaultRoute='beta'})
    Check ($state.NetworkKey -eq 'beta') 'Only verified live engine routing changes the displayed route'
    Check ($script:Writes -eq 0) 'Reading state and inventory never writes settings'
}finally{$canary.Stop()}

$realListener=${function:Get-Listener}
function Get-Listener($Profile){[pscustomobject]@{PID=11;Name='test'}}
$plan=Get-UnifiedPlan 'beta' $script:Rules
Check ($plan.Entrance -eq 'beta' -and -not $plan.Routing.defaultRoute) 'HTTP selection does not depend on a different running proxy'
$plan=Get-UnifiedPlan 'socks' $script:Rules
Check ($plan.Entrance -eq 'alpha' -and $plan.Routing.defaultRoute -eq 'socks') 'SOCKS still uses the explicitly configured HTTP gateway'

# Another client writes after our setter. Rollback must preserve that latest choice.
$before=$script:System;$beforeEnv=$script:Environment
$target=[pscustomobject]@{Flags=3;Server='127.0.0.1:29758';Bypass=''}
$targetEnv=New-EnvTarget $beforeEnv 'beta'
$script:Outside=[pscustomobject]@{Flags=1;Server='';Bypass='user-choice'}
$script:InjectSystem=$true
Throws {Invoke-ProxyTransaction $target $targetEnv $null $before $beforeEnv} '保留其他程序'
Check ((Test-SameSnapshot $script:System $script:Outside) -and (Test-SameEnv $script:Environment $beforeEnv)) 'Post-write outside system choice survives rollback'
$script:System=$before;$script:Environment=$beforeEnv
$script:OutsideEnv=[pscustomobject]@{HTTP_PROXY='http://127.0.0.1:1080';HTTPS_PROXY=$targetEnv.HTTPS_PROXY;ALL_PROXY=$targetEnv.ALL_PROXY;NO_PROXY=$targetEnv.NO_PROXY}
$script:InjectEnv=$true
Throws {Invoke-ProxyTransaction $target $targetEnv $null $before $beforeEnv} '保留其他程序'
Check ($script:Environment.HTTP_PROXY -eq 'http://127.0.0.1:1080' -and -not $script:Environment.HTTPS_PROXY -and (Test-SameSnapshot $script:System $before)) 'Rollback restores own variables and preserves externally changed values'

# A valid system proxy in a backup must not conceal a dead environment proxy.
${function:Get-Listener}=$realListener
Throws {Assert-RestorableEnvironment ([pscustomobject]@{HTTPS_PROXY='http://127.0.0.1:7897'})} '7897'
Assert-RestorableEnvironment ([pscustomobject]@{HTTPS_PROXY='http://localhost:29758'})
Check $true 'Live environment endpoint is restorable'
$qaRoot=Join-Path $env:TEMP ('ProxySwitch-compat-'+[Guid]::NewGuid().ToString('N'))
$script:BackupDir=Join-Path $qaRoot 'backups';[void][IO.Directory]::CreateDirectory($script:BackupDir)
$backup=[pscustomobject]@{Version=3;System=$target;Environment=[pscustomobject]@{HTTP_PROXY='http://localhost:7897'};Selection=$null;Routing=$null}
Write-LocalJson (Join-Path $script:BackupDir 'proxy-20990101.json') $backup
$n=$script:Writes
Throws {Restore-ProxyBackup} '7897'
Check ($script:Writes -eq $n) 'Restore refuses dead environment ports before any mutation'

# Protected game paths can still be observed; SYN attempts are not successful exits.
function Invoke-AppRouter {[pscustomobject]@{available=$false;entries=@();connections=@();defaultRoute=$null;defaultLoaded=$false}}
function Get-NetTCPConnection {param($State)
    [pscustomobject]@{LocalPort=50000;RemoteAddress='127.0.0.1';RemotePort=7897;OwningProcess=10;State='SynSent'}
}
$apps=Get-ApplicationRoutes;$game=$apps.Rows | Where-Object Name -eq 'CalabiYau'
Check ($game -and -not $game.Path -and $game.PIDs -eq '10') 'Protected game appears by PID without memory access'
Check ($game.Actual -match 'SynSent.*7897' -and $game.Status -match '尚未建立') 'Failed proxy attempts are visible and never reported as successful routing'
Write-Output ('PASS: '+$script:Pass+' compatibility assertions; isolated fixtures only.')
