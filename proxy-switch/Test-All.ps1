$ErrorActionPreference='Stop'
foreach($file in Get-ChildItem -LiteralPath $PSScriptRoot -Filter '*.ps1'){
    $tokens=$null;$errors=$null
    [void][Management.Automation.Language.Parser]::ParseFile($file.FullName,[ref]$tokens,[ref]$errors)
    if($errors){throw ($file.Name+': '+(($errors | ForEach-Object Message)-join '; '))}
}
$windowsPowerShell=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
& $windowsPowerShell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'Test-MigrationTransaction.ps1')
if($LASTEXITCODE -ne 0){throw 'Migration transaction tests failed'}
foreach($name in @('Test-ProgramFamilyTracking.ps1','Test-ManagedRouting.ps1','Test-ManagedLaunchEvidence.ps1','Test-ManagedObservation.ps1','Test-ManagedRemoval.ps1','Test-ProxySwitch.ps1','Test-Preferences.ps1','Test-ProgramIdentity.ps1','Test-ApplicationObservation.ps1','Test-RuleMaintenance.ps1','Test-WorkerOutcome.ps1','Test-EntryMaintenance.ps1','Test-ProxyDiscovery.ps1','Test-Compatibility.ps1','Test-AutomaticDiscovery.ps1','Test-ProgramLaunch.ps1','Test-Storage.ps1','Test-GatewayControl.ps1','Test-ExitRecovery.ps1','Test-Watchdog.ps1','Test-StatusSnapshot.ps1','Test-FailoverDisplay.ps1','Test-LifecycleProtection.ps1')){
    & $windowsPowerShell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot $name)
    if($LASTEXITCODE -ne 0){throw ($name+' failed')}
}
& node --check (Join-Path $PSScriptRoot 'AppRouter.cjs')
if($LASTEXITCODE -ne 0){throw 'Node syntax check failed'}
& node (Join-Path $PSScriptRoot 'Test-AppRouter.cjs')
if($LASTEXITCODE -ne 0){throw 'Routing tests failed'}
& node (Join-Path $PSScriptRoot 'Test-IndependentRouter.cjs')
if($LASTEXITCODE -ne 0){throw 'Independent gateway tests failed'}
& node (Join-Path $PSScriptRoot 'Test-GatewayLock.cjs')
if($LASTEXITCODE -ne 0){throw 'Windows lock recovery tests failed'}
& node (Join-Path $PSScriptRoot 'Test-RoutePolicy.cjs')
if($LASTEXITCODE -ne 0){throw 'Route policy tests failed'}
& node (Join-Path $PSScriptRoot 'Test-OfflineDetach.cjs')
if($LASTEXITCODE -ne 0){throw 'Offline detach tests failed'}
Write-Output 'PASS: all static and unit checks completed.'
