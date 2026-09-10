$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'Storage.ps1')
$qa=Join-Path $env:TEMP ('ProxySwitch-storage-'+[Guid]::NewGuid().ToString('N'))
$fixtureProfile=Join-Path $qa 'profile';$local=Join-Path $fixtureProfile 'AppData\Local';$legacy=Join-Path $local 'ProxySwitch';$shared=Join-Path $fixtureProfile '.proxyswitch'
[void][IO.Directory]::CreateDirectory((Join-Path $legacy 'backups\shortcuts'))
$script:Pass=0
function Check($Condition,$Message){if(-not $Condition){throw $Message};$script:Pass++}
$config=Join-Path $legacy 'config.json';[IO.File]::WriteAllText($config,'{"Version":3,"Profiles":[]}')
$program=Join-Path $legacy 'program-proxies.json';[IO.File]::WriteAllText($program,'{"version":1,"entries":[]}')
$backup=Join-Path $legacy 'backups\shortcuts\original.lnk';[IO.File]::WriteAllBytes($backup,[byte[]]@(1,2,3,4))
$records=@{version=1;entries=@(@{program='C:\Apps\Editor.exe';shortcut='C:\Desktop\Editor.lnk';originalBackup=$backup;managedArguments='old arguments'})}
[IO.File]::WriteAllText((Join-Path $legacy 'program-shortcuts.json'),($records|ConvertTo-Json -Depth 6))
$before=(Get-FileHash -LiteralPath $config).Hash
Check ((Resolve-ProxyDataDirectory '' '' $fixtureProfile $local) -eq $shared) 'Default storage is outside virtualized AppData'
Check ((Resolve-ProxyDataDirectory $legacy '' $fixtureProfile $local) -eq $legacy) 'An explicit old directory remains usable before migration'
Check ((Resolve-ProxyDataDirectory (Join-Path $qa 'explicit') (Join-Path $qa 'env') $fixtureProfile $local) -eq (Join-Path $qa 'explicit')) 'Explicit data directory takes priority'
Check ((Resolve-ProxyDataDirectory '' (Join-Path $qa 'env') $fixtureProfile $local) -eq (Join-Path $qa 'env')) 'Isolated environment override is honored'
Initialize-ProxyDataDirectory $shared $legacy
Check ((Get-FileHash -LiteralPath (Join-Path $shared 'config.json')).Hash -eq $before) 'Migration preserves configuration byte for byte'
Check ((Get-FileHash -LiteralPath $config).Hash -eq $before -and (Test-Path -LiteralPath $program)) 'Legacy files remain available for recovery'
Check ((Get-FileHash -LiteralPath (Join-Path $shared 'backups\shortcuts\original.lnk')).Hash -eq (Get-FileHash -LiteralPath $backup).Hash) 'Original shortcut backup survives migration'
$afterRecords=Get-Content -LiteralPath (Join-Path $shared 'program-shortcuts.json') -Raw|ConvertFrom-Json
Check ($afterRecords.entries[0].originalBackup -eq (Join-Path $shared 'backups\shortcuts\original.lnk') -and $afterRecords.entries[0].managedArguments -eq 'old arguments') 'Only backup storage paths are relocated; ownership checks remain intact'
Check ((Resolve-ProxyDataDirectory $legacy '' $fixtureProfile $local) -eq $shared) 'Old desktop arguments resolve to migrated shared storage'
Check ((Resolve-ProxyDataDirectory '' $legacy $fixtureProfile $local) -eq $legacy) 'Environment override is not silently redirected'
[IO.File]::WriteAllText((Join-Path $shared 'config.json'),'new user selection')
Initialize-ProxyDataDirectory $shared $legacy
Check ([IO.File]::ReadAllText((Join-Path $shared 'config.json')) -eq 'new user selection') 'Repeated startup never imports stale legacy settings over current choices'
$empty=Join-Path $qa 'fresh';Initialize-ProxyDataDirectory $empty (Join-Path $qa 'missing')
Check ((Test-Path -LiteralPath (Join-Path $empty 'storage-layout.json')) -and -not (Test-Path -LiteralPath (Join-Path $empty 'config.json'))) 'Fresh install has no invented proxy configuration'
$badLegacy=Join-Path $qa 'bad';[void][IO.Directory]::CreateDirectory($badLegacy)
[IO.File]::WriteAllText((Join-Path $badLegacy 'program-shortcuts.json'),'{invalid')
$failed=$false;try{Initialize-ProxyDataDirectory (Join-Path $qa 'failed') $badLegacy}catch{$failed=$true}
Check ($failed -and -not (Test-Path -LiteralPath (Join-Path $qa 'failed')) -and (Test-Path -LiteralPath (Join-Path $badLegacy 'program-shortcuts.json'))) 'Failed migration publishes no partial destination and retains the original'
Write-Output ('PASS: '+$script:Pass+' storage assertions; temporary data only, no Windows proxy writes.')
