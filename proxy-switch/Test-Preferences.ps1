$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProxyBackend.ps1')
$script:pass=0
function Check($Condition,$Message){if(-not $Condition){throw $Message};$script:pass++}
function Throws([scriptblock]$Action){$caught=$false;try{& $Action | Out-Null}catch{$caught=$true};Check $caught 'Expected validation failure'}
$legacy=[pscustomobject]@{Clash=[pscustomobject]@{Name='Local engine';Port=7897;CorePath='C:\Apps\core.exe';AppPath='C:\Apps\client.exe'};Upnet=[pscustomobject]@{Name='My legacy proxy';Port=29758;CorePath='';AppPath=''}}
$value=ConvertTo-ValidProfileSettings (Convert-LegacySettings $legacy)
Check ($value.Version -eq 3 -and $value.Profiles[1].Name -eq 'My legacy proxy' -and $value.Profiles[1].Id -eq 'Upnet') 'Migration preserves names and stable rule ids'
$fresh=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'config.defaults.json') -Raw | ConvertFrom-Json
Check (@((ConvertTo-ValidProfileSettings $fresh).Profiles).Count -eq 0) 'Fresh install has no branded proxy defaults'
$custom=[pscustomobject]@{Id='custom';Name='Company';Protocol='socks5';Host='proxy.example.org';Port=1080;CorePath='';AppPath=''}
$value.Profiles+=@($custom);$clean=ConvertTo-ValidProfileSettings $value
Check ($clean.Profiles.Count -eq 3 -and $clean.Profiles[2].Protocol -eq 'socks5') 'More than two user-defined proxies supported'
$value.Profiles[2].Id='Direct';Throws {ConvertTo-ValidProfileSettings $value};$value.Profiles[2].Id='custom'
$value.Profiles[2].Name='Local engine';Throws {ConvertTo-ValidProfileSettings $value};$value.Profiles[2].Name='Company'
foreach($invalid in @('http://example.org','user:password@host','host;cmd','bad host','example.org/path')){$value.Profiles[2].Host=$invalid;Throws {ConvertTo-ValidProfileSettings $value}}
$value.Profiles[2].Host='2001:db8::1';Check ((ConvertTo-ValidProfileSettings $value).Profiles[2].Host -eq '2001:db8::1') 'IPv6 supported'
$value.Profiles[2].Host='localhost';$value.Profiles[2].Port=7897;Throws {ConvertTo-ValidProfileSettings $value}
$value.Profiles[2].Port=1080;$value.Profiles[2].Host='proxy.example.org';$value.Profiles[2].Protocol='unknown';Throws {ConvertTo-ValidProfileSettings $value};$value.Profiles[2].Protocol='socks5'
$value.Routing.ProfileId='custom';Throws {ConvertTo-ValidProfileSettings $value};$value.Routing.ProfileId='Clash'
$script:Profiles=$clean
$rows=@([pscustomobject]@{Name='编辑器 [工作]';Path='C:\Apps\edit.exe';Policy='custom';Loaded=$true},[pscustomobject]@{Name='Browser';Path='C:\Apps\browser.exe';Policy='Follow';Loaded=$false})
Check (@(Select-ApplicationRows $rows '[工作]' $false).Count -eq 1) 'Literal search'
Check (@(Select-ApplicationRows $rows 'BROWSER' $false).Count -eq 1) 'Case-insensitive search'
Check (@(Select-ApplicationRows $rows '' $true).Count -eq 1) 'Saved filter'
$state=[pscustomobject]@{Key='custom';Aligned=$true;EndpointReady=$true;Environment=@([pscustomobject]@{Name='HTTP_PROXY';Route='custom';Value='http://user:secret@private.example'});Listeners=@([pscustomobject]@{Key='custom';Port=1080;Ready=$true})}
$report=New-SupportReport $state ([pscustomobject]@{Rows=$rows;Available=$true});$json=$report|ConvertTo-Json -Depth 8
Check ($json -notmatch 'custom|Company|secret|private|Browser|编辑器|C:\\') 'Report anonymizes custom ids, names, addresses and paths'
Check ($report.SystemRoute -eq 'Proxy3' -and $report.Rules[0].Count -eq 1) 'Report preserves useful aggregates'
$testDir=Join-Path $env:TEMP ('ProxySwitch-model-test-'+[Guid]::NewGuid().ToString('N'));[void][IO.Directory]::CreateDirectory($testDir)
try{
    $file=Join-Path $testDir 'settings.json';Write-LocalJson $file $clean;Write-LocalJson $file $clean
    Check ((Get-Content -LiteralPath $file -Raw|ConvertFrom-Json).Profiles.Count -eq 3) 'Atomic settings replacement'
    $exe=Join-Path $testDir '例子.exe';[IO.File]::WriteAllText($exe,'fixture')
    Check ((Resolve-ProgramTarget $exe) -eq $exe) 'Unicode EXE resolution'
    $shell=New-Object -ComObject WScript.Shell;$lnk=Join-Path $testDir '例子.lnk';$link=$shell.CreateShortcut($lnk);$link.TargetPath=$exe;$link.Save()
    [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($link);[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell)
    Check ((Resolve-ProgramTarget $lnk) -eq $exe) 'Shortcut target resolved without execution'
    Throws {Resolve-ProgramTarget $file}
    $script:StatePath=Join-Path $testDir 'selection.json';$script:DataRoot=$testDir
    Save-Selection ([pscustomobject]@{Key='first'});Save-Selection ([pscustomobject]@{Key='second'})
    Check ((Get-Selection).Key -eq 'second') 'Native PowerShell null-string replacement works on repeat save'
}finally{
    foreach($name in @('settings.json','selection.json','例子.exe','例子.lnk')){$file=Join-Path $testDir $name;if(Test-Path -LiteralPath $file){[IO.File]::Delete($file)}}
    if(-not @(Get-ChildItem -LiteralPath $testDir -Force).Count){[IO.Directory]::Delete($testDir)}
}
Write-Output ('PASS: '+$pass+' profile, migration, privacy and storage assertions; no real network writes.')
