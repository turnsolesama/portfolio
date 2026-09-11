$ErrorActionPreference='Stop'
$env:PROXY_SWITCH_DATA_DIR=Join-Path $env:TEMP ('FlowSwitch-Recovery-'+[Guid]::NewGuid().ToString('N'))
. (Join-Path $PSScriptRoot 'ProxyBackend.ps1')
function Use-ChangeLock([scriptblock]$Action){& $Action} # All writes in this fixture are in-memory stubs.
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
$inherited=[pscustomobject]@{BeforeSystem=$target;BeforeEnv=$targetEnv;TargetSystem=$target;TargetEnv=$targetEnv}
$script:Ready+=@('127.0.0.1:18790','http://127.0.0.1:18790')
$p=New-ExitRecoveryPlan $inherited $target $targetEnv
Check (($p.System.Flags -band 2) -eq 0 -and -not $p.Environment.HTTP_PROXY -and -not $p.Environment.HTTPS_PROXY -and -not $p.Environment.ALL_PROXY) 'A stale preexisting self-reference is never restored to a core that is about to stop'
$inherited.BeforeSystem=[pscustomobject]@{Flags=3;Server='localhost:18790';Bypass='localhost'};$p=New-ExitRecoveryPlan $inherited $target $targetEnv
Check (($p.System.Flags -band 2) -eq 0) 'Loopback aliases cannot disguise the retiring FlowSwitch entry as an original upstream'
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
$script:Fail=$false;$script:Sys=$target;$script:Env=$targetEnv
function Set-SystemSnapshot($value){$script:Sys=$value;$script:Env=$envOutside}
Write-LocalJson (Get-IndependentSessionPath) $session
Restore-IndependentSession
Check ($script:Env.HTTP_PROXY -eq $envOutside.HTTP_PROXY -and $script:Env.NO_PROXY -eq 'changed') 'External variables changed during system restoration are preserved'
Check (-not $script:Env.HTTPS_PROXY -and -not $script:Env.ALL_PROXY) 'Still-owned variables are restored after concurrent external changes'
$script:Sys=$target;$script:Env=$targetEnv
$newSession=$session|ConvertTo-Json|ConvertFrom-Json;$newSession|Add-Member NoteProperty Started 'new-session'
function Use-ChangeLock([scriptblock]$Action){Write-LocalJson (Get-IndependentSessionPath) $newSession;& $Action}
[IO.File]::Delete((Join-Path $script:DataRoot 'gateway\stop'))
Restore-IndependentSession -ExpectedSession 'old-session'
Check ((Test-Path (Get-IndependentSessionPath)) -and (Test-SameSnapshot $script:Sys $target) -and -not (Test-Path (Join-Path $script:DataRoot 'gateway\stop'))) 'A delayed old watchdog cannot restore or stop a newer session'
Write-Output ('PASS: '+$script:checks+' exit recovery assertions; no Windows proxy settings written.')
