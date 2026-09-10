$ErrorActionPreference='Stop'
$env:PROXY_SWITCH_DATA_DIR=Join-Path $env:TEMP ('FlowSwitch-Recovery-'+[Guid]::NewGuid().ToString('N'))
. (Join-Path $PSScriptRoot 'ProxyBackend.ps1')
$script:checks=0
function Check($value,$message){if(-not $value){throw $message};$script:checks++}
$script:Ready=@('127.0.0.1:19001','http://127.0.0.1:19001')
function Test-RecoveryEndpoint([string]$value){$value -in $script:Ready}
$direct=[pscustomobject]@{Flags=1;Server='';Bypass='localhost'}
$prior=[pscustomobject]@{Flags=3;Server='127.0.0.1:19001';Bypass='localhost'}
$target=[pscustomobject]@{Flags=3;Server='127.0.0.1:18790';Bypass='localhost'}
$oldEnv=[pscustomobject]@{HTTP_PROXY='http://127.0.0.1:19001';HTTPS_PROXY='http://127.0.0.1:19001';ALL_PROXY=$null;NO_PROXY='localhost'}
$targetEnv=[pscustomobject]@{HTTP_PROXY='http://127.0.0.1:18790';HTTPS_PROXY='http://127.0.0.1:18790';ALL_PROXY='http://127.0.0.1:18790';NO_PROXY='localhost'}
$session=[pscustomobject]@{BeforeSystem=$prior;BeforeEnv=$oldEnv;TargetSystem=$target;TargetEnv=$targetEnv}
$p=New-ExitRecoveryPlan $session $target $targetEnv
Check (Test-SameSnapshot $p.System $prior) 'Normal exit restores a live original proxy'
Check (Test-SameEnv $p.Environment $oldEnv) 'Normal exit restores original user variables'
$script:Ready=@();$p=New-ExitRecoveryPlan $session $target $targetEnv
Check (Test-SameSnapshot $p.System $direct) 'Exited original upstream restores direct instead of a dead port'
Check (-not $p.Environment.HTTP_PROXY -and -not $p.Environment.HTTPS_PROXY -and -not $p.Environment.ALL_PROXY) 'Dead original environment ports removed'
$outside=[pscustomobject]@{Flags=3;Server='127.0.0.1:20000';Bypass='external'}
$envOutside=[pscustomobject]@{HTTP_PROXY='http://127.0.0.1:20000';HTTPS_PROXY=$targetEnv.HTTPS_PROXY;ALL_PROXY=$targetEnv.ALL_PROXY;NO_PROXY='changed'}
$p=New-ExitRecoveryPlan $session $outside $envOutside
Check (Test-SameSnapshot $p.System $outside) 'Concurrent external system selection is preserved'
Check ($p.Environment.HTTP_PROXY -eq $envOutside.HTTP_PROXY -and $p.Environment.NO_PROXY -eq 'changed' -and -not $p.Environment.HTTPS_PROXY) 'Restore only still-owned environment fields'
$script:Sys=$target;$script:Env=$targetEnv;$script:Trace=@();$script:Fail=$false
function Get-SystemSnapshot {$script:Sys}
function Get-UserProxyEnv {$script:Env}
function Set-SystemSnapshot($value){$script:Trace+='system';if($script:Fail){throw 'write failed'};$script:Sys=$value}
function Set-UserProxyEnv($value){$script:Trace+='environment';$script:Env=$value}
function Get-ItemPropertyValue {param($LiteralPath,$Name,$ErrorAction);throw 'Recovery registration was removed externally'}
function Remove-ItemProperty {param($LiteralPath,$Name,$ErrorAction);throw 'Missing registration must not be removed'}
function Stop-Process {param($Id,$ErrorAction);throw 'No arbitrary process should be stopped'}
[void][IO.Directory]::CreateDirectory((Join-Path $script:DataRoot 'gateway'))
Write-LocalJson (Get-IndependentSessionPath) $session
Restore-IndependentSession
Check ($script:Trace[0] -eq 'system' -and (Test-SameSnapshot $script:Sys $direct)) 'System restored before stopping gateway'
Check ((Test-Path -LiteralPath (Join-Path $script:DataRoot 'gateway\stop')) -and -not (Test-Path -LiteralPath (Get-IndependentSessionPath))) 'Stop request only after verification and journal archived'
[IO.File]::Delete((Join-Path $script:DataRoot 'gateway\stop'))
$script:Sys=$target;$script:Env=$targetEnv;$script:Fail=$true;Write-LocalJson (Get-IndependentSessionPath) $session
try{Restore-IndependentSession}catch{}
Check ((Test-Path -LiteralPath (Get-IndependentSessionPath)) -and -not (Test-Path -LiteralPath (Join-Path $script:DataRoot 'gateway\stop'))) 'Failed restoration retains journal and live core'
Check (Test-SessionProcess $PID (Get-ProcessStartTicks $PID)) 'Real current owner identity verified'
Check (-not (Test-SessionProcess $PID '1')) 'PID reuse cannot impersonate owner'
Write-Output ('PASS: '+$script:checks+' exit recovery assertions; no Windows proxy settings written.')
