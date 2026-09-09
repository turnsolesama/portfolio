[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$PackageDirectory)
$ErrorActionPreference='Stop'
$package=[IO.Path]::GetFullPath($PackageDirectory)
$qaRoot=Join-Path $env:TEMP ('ProxySwitch-package-'+[Guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($qaRoot)
$relocated=Join-Path $qaRoot ('Moved '+[char]0x4e2d+[char]0x6587+' package')
Copy-Item -LiteralPath $package -Destination $relocated -Recurse
$exe=Join-Path $relocated 'ProxySwitch.exe'
$dataRoot=Join-Path $qaRoot 'isolated settings'
[void][IO.Directory]::CreateDirectory($dataRoot)
$utf8=New-Object Text.UTF8Encoding($false)
$config=@{Version=3;Profiles=@(@{Id='qa';Name='QA explicit directory';Protocol='http';Host='127.0.0.1';Port=18123;AppPath='';CorePath='';AutoPort=$false});Routing=@{Adapter='none';ProfileId=''};DiscoveryIgnored=@()}
[IO.File]::WriteAllText((Join-Path $dataRoot 'config.json'),($config|ConvertTo-Json -Depth 6),$utf8)
$script:Pass=0
function Check($Value,$Message){if(-not $Value){throw $Message};$script:Pass++}
function Invoke-Fixture([string]$Arguments){
    $psi=New-Object Diagnostics.ProcessStartInfo
    $psi.FileName=$exe;$psi.Arguments=$Arguments;$psi.WorkingDirectory=$qaRoot
    $psi.UseShellExecute=$false;$psi.CreateNoWindow=$true;$psi.WindowStyle='Hidden'
    $psi.RedirectStandardOutput=$true;$psi.RedirectStandardError=$true
    $psi.EnvironmentVariables['PROXY_SWITCH_DATA_DIR']=Join-Path $qaRoot 'wrong environment'
    $p=[Diagnostics.Process]::Start($psi)
    try{
        $stdout=$p.StandardOutput.ReadToEndAsync();$stderr=$p.StandardError.ReadToEndAsync()
        if(-not $p.WaitForExit(30000)){$p.Kill();throw 'Isolated package check timed out.'}
        [pscustomobject]@{Code=$p.ExitCode;Out=$stdout.Result;Error=$stderr.Result}
    }finally{$p.Dispose()}
}
$manifest=Get-Content -LiteralPath (Join-Path $relocated 'manifest.json') -Raw -Encoding UTF8|ConvertFrom-Json
$valid=$true
foreach($item in $manifest){$file=Join-Path $relocated $item.path;if((Get-FileHash -LiteralPath $file).Hash.ToLowerInvariant() -ne $item.sha256 -or (Get-Item -LiteralPath $file).Length -ne $item.bytes){$valid=$false}}
Check $valid 'Program package manifest mismatch.'
Check ((Get-ChildItem -LiteralPath $relocated -Recurse -File).Count -eq ($manifest.Count+1)) 'Unexpected file in program package.'
$verified=Invoke-Fixture '--verify'
Check ($verified.Code -eq 0 -and $verified.Out -match 'PASS') ('EXE verification failed: '+$verified.Error)
# Include a trailing separator so both launcher and PowerShell argument parsing are exercised.
$quotedData='"'+$dataRoot+'\\"'
$smoke=Invoke-Fixture ('--smoke-test --data-directory '+$quotedData)
Check ($smoke.Code -eq 0 -and $smoke.Out -match 'PASS: UI background status worker completed') ('Relocated EXE could not open and close its real UI: '+$smoke.Error)
$status=Invoke-Fixture ('--status --data-directory '+$quotedData)
if($status.Code -ne 0){throw $status.Error};$value=$status.Out|ConvertFrom-Json
Check ($value.Listeners.Count -eq 1 -and $value.Listeners[0].Key -eq 'qa') 'EXE did not pass its explicit settings directory.'
Check (-not (Test-Path -LiteralPath (Join-Path $qaRoot 'wrong environment\config.json'))) 'Package wrote to the inherited environment directory.'
$dependency=Join-Path $relocated 'app\Storage.ps1';$held=$dependency+'.held'
[IO.File]::Move($dependency,$held)
try{$missing=Invoke-Fixture '--verify';Check ($missing.Code -ne 0 -and $missing.Error -match 'Storage.ps1') 'Incomplete package was accepted.'}finally{[IO.File]::Move($held,$dependency)}
# Redirect only this temporary copy of the installer; never write to the user's desktop.
$desktop=Join-Path $qaRoot 'Desktop';[void][IO.Directory]::CreateDirectory($desktop)
$installer=Join-Path $relocated 'app\Install-Shortcut.ps1'
$original=[IO.File]::ReadAllText($installer)
$needle='$desktop=[Environment]::GetFolderPath(''Desktop'')'
if(-not $original.Contains($needle)){throw 'Installer isolation hook missing.'}
$isolated=$original.Replace($needle,('$desktop='''+$desktop.Replace("'","''")+''''))
[IO.File]::WriteAllText($installer,$isolated,(New-Object Text.UTF8Encoding($true)))
$installed=Invoke-Fixture ('--install-shortcut --quiet --data-directory '+$quotedData)
Check ($installed.Code -eq 0) ('EXE shortcut installer failed: '+$installed.Error)
$shell=New-Object -ComObject WScript.Shell
try{
    $shortcut=Get-ChildItem -LiteralPath $desktop -Filter '*.lnk'|Select-Object -First 1
    $link=$shell.CreateShortcut($shortcut.FullName)
    Check ($link.TargetPath -ieq $exe -and $link.WorkingDirectory -ieq $relocated -and $link.Arguments -match 'isolated settings') 'Desktop shortcut does not target the relocated EXE and selected data directory.'
    $fromShortcut=Invoke-Fixture ($link.Arguments+' --smoke-test')
    Check ($fromShortcut.Code -eq 0 -and $fromShortcut.Out -match 'PASS: UI') ('Saved shortcut arguments did not reopen the UI: '+$fromShortcut.Error)
    [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($link)
}finally{[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell)}
Write-Output ('PASS: '+$script:Pass+' Windows package checks; compiled EXE, relocated Unicode/space path, real UI smoke test, explicit settings, missing-file rejection and isolated desktop shortcut. No real network writes.')
