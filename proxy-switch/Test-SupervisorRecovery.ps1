[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$CorePath)
$ErrorActionPreference='Stop'
$qa=Join-Path $env:TEMP ('FlowSwitch-Supervisor-'+[Guid]::NewGuid().ToString('N'));[void][IO.Directory]::CreateDirectory($qa)
$env:PROXY_SWITCH_DATA_DIR=$qa
$core=Join-Path $qa 'FlowSwitch-TestEngine.exe';Copy-Item -LiteralPath $CorePath -Destination $core
. (Join-Path $PSScriptRoot 'ProxyBackend.ps1')
$listener=New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback,0);$listener.Start();$port=$listener.LocalEndpoint.Port;$listener.Stop()
$script:Profiles=ConvertTo-ValidProfileSettings ([pscustomobject]@{Version=3;Profiles=@([pscustomobject]@{Id='gateway';Name='fixture';Protocol='http';Host='127.0.0.1';Port=$port;CorePath=$core;AppPath='';AutoPort=$false});Routing=[pscustomobject]@{Adapter='standalone';ProfileId='gateway';UnifiedMode='gateway'}})
Write-LocalJson $script:ConfigPath $script:Profiles
Write-LocalJson (Join-Path $qa 'app-rules.json') ([pscustomobject]@{version=2;entries=@();defaultRoute='Direct';installed=$true})
$watch=$null;$checks=0
function Check($Value,$Message){if(-not $Value){throw $Message};$script:checks++;Write-Output ('PASS: '+$Message)}
try{
    Invoke-AppRouter @{action='start'}|Out-Null
    $owned=Get-Content (Join-Path $qa 'gateway\process.json') -Raw|ConvertFrom-Json
    $direct=[pscustomobject]@{Flags=1;Server='';Bypass='localhost'};$target=[pscustomobject]@{Flags=3;Server=('127.0.0.1:'+$port);Bypass='localhost'}
    $beforeEnv=[pscustomobject]@{HTTP_PROXY=$null;HTTPS_PROXY=$null;ALL_PROXY=$null;NO_PROXY='localhost'}
    $targetEnv=[pscustomobject]@{HTTP_PROXY=('http://127.0.0.1:'+$port);HTTPS_PROXY=('http://127.0.0.1:'+$port);ALL_PROXY=('http://127.0.0.1:'+$port);NO_PROXY='localhost'}
    Write-LocalJson (Get-IndependentSessionPath) ([pscustomobject]@{OwnerPID=$PID;OwnerStart=(Get-ProcessStartTicks $PID);CorePID=$owned.core;CoreStart=(Get-ProcessStartTicks $owned.core);SupervisorPID=$owned.supervisor;SupervisorStart=(Get-ProcessStartTicks $owned.supervisor);BeforeSystem=$direct;TargetSystem=$target;BeforeEnv=$beforeEnv;TargetEnv=$targetEnv;Started=[DateTimeOffset]::UtcNow.ToString('o')})
    Write-LocalJson (Join-Path $qa 'fake-system.json') $target;Write-LocalJson (Join-Path $qa 'fake-env.json') $targetEnv
    $body=[IO.File]::ReadAllText((Join-Path $PSScriptRoot 'GatewayWatchdog.ps1'));$body=$body.Substring($body.IndexOf('$path=Get-IndependentSessionPath'))
    $mock=@'
function Get-SystemSnapshot {Get-Content (Join-Path $script:DataRoot 'fake-system.json') -Raw|ConvertFrom-Json}
function Get-UserProxyEnv {Get-Content (Join-Path $script:DataRoot 'fake-env.json') -Raw|ConvertFrom-Json}
function Set-SystemSnapshot($v){Write-LocalJson (Join-Path $script:DataRoot 'fake-system.json') $v}
function Set-UserProxyEnv($v){Write-LocalJson (Join-Path $script:DataRoot 'fake-env.json') $v}
function Get-ItemPropertyValue {param($LiteralPath,$Name,$ErrorAction);throw 'Isolated registry stub'}
function Remove-ItemProperty {throw 'Real registry is forbidden'}
'@
    $prefix=". '"+(Join-Path $PSScriptRoot 'ProxyBackend.ps1').Replace("'","''")+"' -DataDirectory '"+$qa.Replace("'","''")+"'`r`n"
    $file=Join-Path $qa 'watch.ps1';[IO.File]::WriteAllText($file,$prefix+$mock+"`r`n"+$body,(New-Object Text.UTF8Encoding($true)))
    $watch=Start-Process -FilePath (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe') -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File "'+$file+'"') -WindowStyle Hidden -PassThru -RedirectStandardError (Join-Path $qa 'watch-error.txt')
    $deadline=[DateTime]::UtcNow.AddSeconds(10);while(-not (Test-Path (Join-Path $qa 'gateway\watchdog-ready.json')) -and [DateTime]::UtcNow -lt $deadline){Start-Sleep -Milliseconds 100}
    Check (-not $watch.HasExited) 'real watchdog monitors isolated owner and supervisor'
    Stop-Process -Id $owned.core
    $deadline=[DateTime]::UtcNow.AddSeconds(18)
    do{$life=Get-GatewayLifecycle;if($life.phase -eq 'ready' -and $life.core -ne $owned.core){break};Start-Sleep -Milliseconds 150}while([DateTime]::UtcNow -lt $deadline)
    Check ($life.phase -eq 'ready' -and $life.core -ne $owned.core -and -not $watch.HasExited) 'watchdog allows supervised core recovery instead of racing restoration'
    $sys=Get-Content (Join-Path $qa 'fake-system.json') -Raw|ConvertFrom-Json
    Check (Test-SameSnapshot $sys $target) 'supervised recovery keeps owned fixed entry settings'
    $replacement=$life.core;Stop-Process -Id $owned.supervisor
    Check ($watch.WaitForExit(20000)) 'supervisor crash triggers bounded watchdog recovery'
    $sys=Get-Content (Join-Path $qa 'fake-system.json') -Raw|ConvertFrom-Json
    Check (Test-SameSnapshot $sys $direct) 'watchdog restores settings after supervisor crash'
    Check (-not (Get-Process -Id $replacement -ErrorAction SilentlyContinue)) 'orphan replacement core is stopped after identity verification'
    Check (-not (Test-Path (Get-IndependentSessionPath))) 'recovery session archived after orphan cleanup'
    Write-Output ('PASS: '+$checks+' real supervisor/watchdog recovery checks; Windows settings are file-backed stubs.')
}finally{
    [IO.File]::WriteAllText((Join-Path $qa 'gateway\stop'),'stop')
    if($watch){if(-not $watch.HasExited){$watch.Kill()};$watch.Dispose()}
    # These PIDs were explicitly created in this isolated fixture.
    foreach($id in @($owned.core,$owned.supervisor,$replacement)){if($id){Stop-Process -Id $id -ErrorAction SilentlyContinue}}
}
