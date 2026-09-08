$ErrorActionPreference='Stop'
foreach($file in Get-ChildItem -LiteralPath $PSScriptRoot -Filter '*.ps1'){
    $tokens=$null;$errors=$null
    [void][Management.Automation.Language.Parser]::ParseFile($file.FullName,[ref]$tokens,[ref]$errors)
    if($errors){throw ($file.Name+': '+(($errors | ForEach-Object Message)-join '; '))}
}
$windowsPowerShell=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
foreach($name in @('Test-ProxySwitch.ps1','Test-Preferences.ps1')){
    & $windowsPowerShell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot $name)
    if($LASTEXITCODE -ne 0){throw ($name+' failed')}
}
& node --check (Join-Path $PSScriptRoot 'AppRouter.cjs')
if($LASTEXITCODE -ne 0){throw 'Node syntax check failed'}
& node (Join-Path $PSScriptRoot 'Test-AppRouter.cjs')
if($LASTEXITCODE -ne 0){throw 'Routing tests failed'}
Write-Output 'PASS: all static and unit checks completed.'
