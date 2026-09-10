param([string]$DataDirectory,[switch]$RecoverOnly)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProxyBackend.ps1') -DataDirectory $DataDirectory
$path=Get-IndependentSessionPath
if(-not (Test-Path -LiteralPath $path)){return}
$session=Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
if($RecoverOnly){Restore-IndependentSession;return}
Write-LocalJson (Join-Path $script:DataRoot 'gateway\watchdog-ready.json') ([pscustomobject]@{PID=$PID;StartTicks=(Get-ProcessStartTicks $PID);Session=$session.Started})
$misses=0
while(Test-Path -LiteralPath $path){
    $current=Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
    if($current.Started -ne $session.Started){return}
    $alive=Test-SessionProcess $session.OwnerPID $session.OwnerStart
    $listener=Test-RecoveryEndpoint $session.TargetSystem.Server
    if($session.SupervisorPID -and -not (Test-SessionProcess $session.SupervisorPID $session.SupervisorStart)){$listener=$false}
    if(-not $listener){$misses++}else{$misses=0}
    if(-not $alive -or $misses -ge 2){try{Restore-IndependentSession;return}catch{Start-Sleep -Seconds 1;continue}}
    Start-Sleep -Seconds 1
}
