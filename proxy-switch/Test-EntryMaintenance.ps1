$ErrorActionPreference='Stop'
$qa=Join-Path $env:TEMP ('FlowSwitch-entry-maintenance-'+[Guid]::NewGuid().ToString('N'))
$env:PROXY_SWITCH_DATA_DIR=Join-Path $qa 'data'
. (Join-Path $PSScriptRoot 'ProxyBackend.ps1')
$script:Pass=0
function Check($Value,$Message){if(-not $Value){throw $Message};$script:Pass++}
function Throws([scriptblock]$Action,$Pattern){$message='';try{& $Action|Out-Null}catch{$message=$_.Exception.Message};Check ($message -match $Pattern) ('Expected '+$Pattern+', got '+$message)}
function Set-SystemSnapshot {throw 'Real Windows writes are forbidden'}
function Set-UserProxyEnv {throw 'Real environment writes are forbidden'}
function Invoke-AppRouter {throw 'Real engine changes are forbidden'}
function Use-ChangeLock([scriptblock]$Action){& $Action}
function Set-Link($Path,$Target,$Arguments){
    $shell=New-Object -ComObject WScript.Shell
    try{$link=$shell.CreateShortcut($Path);try{$link.TargetPath=$Target;$link.Arguments=$Arguments;$link.Save()}finally{[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($link)}}finally{[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell)}
}
$app=Join-Path $qa 'app';$desktop=Join-Path $qa 'desktop'
[void][IO.Directory]::CreateDirectory($app);[void][IO.Directory]::CreateDirectory($desktop)
$exe=Join-Path $app 'fixture.exe';[IO.File]::WriteAllText($exe,'inert fixture')
foreach($name in @('resources.pak','chrome_100_percent.pak')){[IO.File]::WriteAllText((Join-Path $app $name),'fixture')}
$script:Profiles=ConvertTo-ValidProfileSettings ([pscustomobject]@{Version=3;Profiles=@([pscustomobject]@{Id='upstream';Name='Fixture';Protocol='http';Host='127.0.0.1';Port=18082;CorePath='';AppPath='';AutoPort=$false});Routing=@{Adapter='none';ProfileId=''}})
Write-LocalJson (Join-Path $script:DataRoot 'config.json') $script:Profiles
Write-LocalJson (Join-Path $script:DataRoot 'program-proxies.json') @{version=1;entries=@(@{path=$exe;route='upstream';adapter='chromium'})}
$shortcut=Join-Path $desktop 'fixture.lnk';Set-Link $shortcut $exe ''
$originalHash=(Get-FileHash -LiteralPath $shortcut).Hash
Install-ProgramProxyShortcut $exe $desktop|Out-Null
Check (@(Get-VerifiedProgramShortcuts $exe).Count -eq 1) 'Current owned backend entry is ready'
$record=@(Get-ProgramShortcutRecords)[0];$backup=$record.originalBackup
$currentArgs=$record.managedArguments;$oldBackend=Join-Path $qa 'removed-version\ProxySwitch.ps1'
$record.managedArguments=$currentArgs.Replace((Join-Path $script:Root 'ProxySwitch.ps1'),$oldBackend)
Set-Link $shortcut $record.managedTarget $record.managedArguments
$external=Join-Path $desktop 'external.lnk';Copy-Item -LiteralPath $shortcut -Destination $external
$externalRecord=$record|ConvertTo-Json|ConvertFrom-Json;$externalRecord.shortcut=$external
Set-Link $external $record.managedTarget '-NoProfile -ExternalChoice';$externalHash=(Get-FileHash -LiteralPath $external).Hash
Write-LocalJson (Join-Path $script:DataRoot 'program-shortcuts.json') @{version=1;entries=@($record,$externalRecord)}
Check (@(Get-VerifiedProgramShortcuts $exe).Count -eq 0) 'Missing backend cannot be certified just because shortcut matches the record'
$health=@(Get-ProgramProxyShortcutHealth $exe)
Check ($health[0].State -eq 'missing-backend' -and $health[0].CanRefresh) 'Owned missing backend is repairable'
Check ($health[1].State -eq 'externally-modified' -and -not $health[1].CanRefresh) 'External shortcut is never considered repairable'
[void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($oldBackend));[IO.File]::WriteAllText($oldBackend,'# old fixture')
Check ((@(Get-ProgramProxyShortcutHealth $exe)[0]).State -eq 'old-backend') 'Existing old version is distinguished from current backend'
$result=Repair-ProgramProxyEntry $exe
Check (@(Get-VerifiedProgramShortcuts $exe).Count -eq 1) 'Repair points owned entry at current backend'
Check ((Get-ProgramLaunchEntries).route -eq 'upstream') 'Entry repair preserves selected route'
Check ((Get-FileHash -LiteralPath $backup).Hash -eq $originalHash) 'Original launcher backup stays byte identical'
Check ((Get-FileHash -LiteralPath $external).Hash -eq $externalHash -and $result.PreservedShortcuts -eq 1) 'Repair preserves externally edited shortcut'
Throws {Repair-ProgramProxyEntry $exe} '没有仍归本工具'
Write-LocalJson (Join-Path $script:DataRoot 'app-rules.json') @{version=2;installed=$true;entries=@(@{path=$exe;route='upstream'});defaultRoute='Direct'}
Throws {Set-ProgramLaunchRoute $exe 'Direct'} '已有引擎规则'

# Exercise real bootstrap failure in a child PowerShell, with isolated invalid data.
$bad=Join-Path $qa 'bad-data';[void][IO.Directory]::CreateDirectory($bad)
$config=Join-Path $bad 'config.json';[IO.File]::WriteAllText($config,'{"privateMarker":"MUST_NOT_LEAK", invalid')
$beforeHash=(Get-FileHash -LiteralPath $config).Hash
$psi=New-Object Diagnostics.ProcessStartInfo
$psi.FileName=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$psi.Arguments='-NoProfile -ExecutionPolicy Bypass -File '+(ConvertTo-ProgramArgument (Join-Path $PSScriptRoot 'ProxySwitch.ps1'))+' -NoUI -DataDirectory '+(ConvertTo-ProgramArgument $bad)+' -LaunchProgram '+(ConvertTo-ProgramArgument $exe)
$psi.UseShellExecute=$false;$psi.CreateNoWindow=$true;$psi.RedirectStandardOutput=$true;$psi.RedirectStandardError=$true
$child=[Diagnostics.Process]::Start($psi)
try{$stdout=$child.StandardOutput.ReadToEnd();$stderr=$child.StandardError.ReadToEnd();Check ($child.WaitForExit(15000) -and $child.ExitCode -eq 1) 'Invalid initialization exits nonzero instead of silently losing IDE launch'}finally{$child.Dispose()}
$reports=@(Get-ChildItem -LiteralPath $bad -Filter 'last-startup-failure.json')
Check ($reports.Count -eq 1) 'Initialization failure records a local diagnostic even before backend is loaded'
$reportText=[IO.File]::ReadAllText($reports[0].FullName);$report=$reportText|ConvertFrom-Json
Check ($report.Stage -eq 'initialization' -and $report.ErrorCode -eq 'backend-initialization' -and ($stdout+$stderr+$reportText) -notmatch 'MUST_NOT_LEAK') 'Failure output uses safe stage and code without config contents'
Check ((Get-FileHash -LiteralPath $config).Hash -eq $beforeHash) 'Invalid user configuration is preserved unchanged'
$child=[Diagnostics.Process]::Start($psi)
try{$null=$child.StandardOutput.ReadToEnd();$null=$child.StandardError.ReadToEnd();[void]$child.WaitForExit(15000)}finally{$child.Dispose()}
Check (@(Get-ChildItem -LiteralPath $bad -Filter '*startup-failure*.json').Count -eq 1 -and (Get-Item -LiteralPath $reports[0].FullName).Length -lt 4096) 'Repeated startup failure keeps one bounded diagnostic record'
Write-Output ('PASS: '+$script:Pass+' entry maintenance assertions; isolated shortcuts, configuration and child process only.')
