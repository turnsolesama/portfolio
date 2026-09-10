param([string]$DataDirectory,[switch]$RecoverOnly)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProxyBackend.ps1') -DataDirectory $DataDirectory
$path=Get-IndependentSessionPath
if(-not (Test-Path -LiteralPath $path)){return}
$session=Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
if($RecoverOnly){
    # A delayed next-logon recovery must not terminate a fresh, live UI session.
    if(Test-SessionProcess $session.OwnerPID $session.OwnerStart){Write-LifecycleEvent 'recovery-skipped' 'owner-still-running';return}
    Restore-IndependentSession -ExpectedSession $session.Started;return
}
Write-LocalJson (Join-Path $script:DataRoot 'gateway\watchdog-ready.json') ([pscustomobject]@{PID=$PID;StartTicks=(Get-ProcessStartTicks $PID);Session=$session.Started})
$misses=0;$restoreAttempts=0;$missingSince=$null
while(Test-Path -LiteralPath $path){
    $current=Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
    if($current.Started -ne $session.Started){return}
    $alive=Test-SessionProcess $session.OwnerPID $session.OwnerStart
    $listener=Test-RecoveryEndpoint $session.TargetSystem.Server
    if($session.SupervisorPID -and -not (Test-SessionProcess $session.SupervisorPID $session.SupervisorStart)){$listener=$false}
    if(-not $listener){$misses++;if(-not $missingSince){$missingSince=[DateTime]::UtcNow}}else{$misses=0;$missingSince=$null}
    $grace=Test-GatewayRecoveryGrace $session $misses
    if($missingSince -and ([DateTime]::UtcNow-$missingSince).TotalSeconds -ge 45){$grace=$false}
    if(-not $alive -or ($misses -ge 2 -and -not $grace)){
        Write-LifecycleEvent 'watchdog-recovery' $(if(-not $alive){'owner-exited'}else{'entry-unavailable'})
        try{Restore-IndependentSession -ExpectedSession $session.Started;return}catch{
            $restoreAttempts++;Write-LifecycleEvent 'watchdog-restore-failed' 'restore-retry' $restoreAttempts
            if($restoreAttempts -ge 3){Write-LifecycleEvent 'watchdog-recovery-exhausted' 'manual-action-required';return}
            Start-Sleep -Seconds ([Math]::Pow(2,$restoreAttempts-1));continue
        }
    }
    Start-Sleep -Seconds 1
}
