$ErrorActionPreference='Stop'
$qa=Join-Path ([IO.Path]::GetTempPath()) ('FlowSwitch-rule-maintenance-'+[Guid]::NewGuid().ToString('N'))
$env:PROXY_SWITCH_DATA_DIR=Join-Path $qa 'initial-data'
. (Join-Path $PSScriptRoot 'ProxyBackend.ps1')
. (Join-Path $PSScriptRoot 'RuleMaintenance.ps1')
$script:Pass=0
function Check($Value,[string]$Message){if(-not $Value){throw $Message};$script:Pass++}
function Throws([scriptblock]$Action,[string]$Pattern){$text='';try{& $Action|Out-Null}catch{$text=$_.Exception.Message};Check ($text -match $Pattern) ('Expected '+$Pattern+'; got '+$text)}
function Use-ChangeLock([scriptblock]$Action){& $Action}
function Set-SystemSnapshot {throw 'No Windows proxy mutation is permitted'}
function Set-UserProxyEnv {throw 'No Windows environment mutation is permitted'}
function Start-ManagedProgram {throw 'No application launch is permitted'}
$oldFull='FlowSwitch.RepairTest_1.0.0.0_x64__8wekyb3d8bbwe';$newFull='FlowSwitch.RepairTest_2.0.0.0_x64__8wekyb3d8bbwe'
$oldExe=Join-Path $qa ('WindowsApps\'+$oldFull+'\app\client.exe');$newRoot=Join-Path $qa ('WindowsApps\'+$newFull);$newExe=Join-Path $newRoot 'app\client.exe'
[void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($newExe));[IO.File]::WriteAllText($newExe,'inert EXE test fixture')
foreach($name in @('resources.pak','chrome_100_percent.pak')){[IO.File]::WriteAllText((Join-Path ([IO.Path]::GetDirectoryName($newExe)) $name),'fixture')}
$script:TestPackages=@([pscustomobject]@{InstallLocation=$newRoot;PackageFullName=$newFull;PackageFamilyName=[LocalProxySwitch.ProgramFileIdentity]::FamilyFromFullName($newFull);Verified=$true})
$realContext=${function:New-ProgramIdentityContext}
function New-ProgramIdentityContext($Processes=@(),$Packages=$null,[switch]$RefreshPackages){& $realContext -Processes $Processes -Packages $script:TestPackages}
function Get-ProcessInventory {param($Id) [pscustomobject]@{Id=456;Path=$newExe;ProcessName='client'}}
$realFileExchange=${function:Set-RuleMaintenanceFile}
function Set-RuleMaintenanceFile($Before,[byte[]]$Bytes,[bool]$Remove=$false){
    if($script:FailFile -and [IO.Path]::GetFileName($Before.Path) -eq $script:FailFile){
        $script:FailFile=''
        if($script:ExternalShortcut){Set-TestShortcutArguments $script:Shortcut '-NoProfile -ExternalChoice'}
        if($script:ExternalEngine){$state=Get-Content -LiteralPath (Join-Path $script:DataRoot 'app-rules.json') -Raw|ConvertFrom-Json;$state|Add-Member NoteProperty external 'preserve' -Force;Write-LocalJson (Join-Path $script:DataRoot 'app-rules.json') $state}
        throw 'Injected isolated file write failure'
    }
    & $realFileExchange $Before $Bytes $Remove
}
function Invoke-AppRouter($Request){
    $script:EngineCalls++
    if(-not $script:EngineOnline){throw 'Engine intentionally offline'}
    if($Request.action -eq 'status'){return [pscustomobject]@{available=$true;rulesAvailable=$true;mode='rule'}}
    if($Request.action -ne 'replace'){throw 'Unexpected engine action'}
    $script:ReplaceCalls++
    $file=Read-RuleMaintenanceFile (Join-Path $script:DataRoot 'app-rules.json');$settings=Read-RuleMaintenanceFile (Join-Path $script:DataRoot 'config.json')
    if($Request.expectedStateHash -cne $file.TextHash -or $Request.expectedSettingsHash -cne $settings.TextHash){throw 'Stale engine compare and swap rejected'}
    $state=[pscustomobject]@{version=2;installed=$true;entries=@($Request.entries);defaultRoute=$Request.defaultRoute;changedAt=[DateTime]::UtcNow.ToString('o')}
    $text=$state|ConvertTo-Json -Depth 16;[IO.File]::WriteAllText($file.Path,$text,(New-Object Text.UTF8Encoding($false)))
    [pscustomobject]@{ok=$true;stateHash=(Get-RuleMaintenanceHash ([Text.Encoding]::UTF8.GetBytes($text)))}
}
function Set-TestShortcutArguments([string]$Path,[string]$Arguments){$shell=New-Object -ComObject WScript.Shell;try{$link=$shell.CreateShortcut($Path);try{$link.Arguments=$Arguments;$link.Save()}finally{[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($link)}}finally{[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell)}}
function Read-TestShortcut([string]$Path){$shell=New-Object -ComObject WScript.Shell;try{$link=$shell.CreateShortcut($Path);try{[pscustomobject]@{Target=$link.TargetPath;Arguments=$link.Arguments;WorkingDirectory=$link.WorkingDirectory;Icon=$link.IconLocation}}finally{[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($link)}}finally{[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell)}}
function New-TestCase([string]$Name,[switch]$Engine,[switch]$Mixed,[switch]$SeparateShortcut){
    $root=Join-Path $qa $Name;$script:DataRoot=Join-Path $root 'data';$script:ConfigPath=Join-Path $script:DataRoot 'config.json';$script:Desktop=Join-Path $root 'desktop';$script:Shortcut=Join-Path $script:Desktop 'client.lnk'
    [void][IO.Directory]::CreateDirectory($script:DataRoot);[void][IO.Directory]::CreateDirectory($script:Desktop)
    $script:Profiles=ConvertTo-ValidProfileSettings ([pscustomobject]@{Version=3;Profiles=@([pscustomobject]@{Id='upstream';Name='Fixture';Protocol='http';Host='127.0.0.1';Port=18082;CorePath='';AppPath='';AutoPort=$false});Routing=@{Adapter='none';ProfileId=''}})
    Write-LocalJson $script:ConfigPath $script:Profiles
    if(-not $Engine -or $Mixed){
        Write-LocalJson (Join-Path $script:DataRoot 'program-proxies.json') ([pscustomobject]@{version=1;note='preserve-launch-metadata';entries=@([pscustomobject]@{path=$oldExe;route='upstream';adapter='chromium';note='preserve-entry'})})
        if(-not $SeparateShortcut){
            $shell=New-Object -ComObject WScript.Shell;try{$link=$shell.CreateShortcut($script:Shortcut);try{$link.TargetPath=$oldExe;$link.IconLocation=$oldExe+',0';$link.Save()}finally{[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($link)}}finally{[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell)}
        }
        $links=@(Install-ProgramProxyShortcut $oldExe $script:Desktop);$script:Shortcut=$links[0]
    }
    if($Engine){Write-LocalJson (Join-Path $script:DataRoot 'app-rules.json') ([pscustomobject]@{version=2;installed=$true;entries=@([pscustomobject]@{path=$oldExe;route='upstream'});defaultRoute='Direct'})}
    $script:EngineOnline=[bool]$Engine;$script:EngineCalls=0;$script:ReplaceCalls=0;$script:FailFile='';$script:ExternalShortcut=$false;$script:ExternalEngine=$false
}
try{
    New-TestCase 'launch-repair'
    $record=Get-ProgramShortcutRecords|Select-Object -First 1;$originalBackup=$record.originalBackup;$originalHash=(Get-FileHash -LiteralPath $originalBackup).Hash
    $before=Get-RuleMaintenanceSnapshot $oldExe;$plan=Get-ProgramRuleRepairPlan $oldExe
    Check ($plan.Mode -eq 'launch' -and $plan.CurrentPath -ieq $newExe -and $plan.Impact -match '保留目标线路') 'Preview identifies the upgrade and accurately describes launch behavior'
    Check ((Get-RuleMaintenanceSnapshot $oldExe).Fingerprint -ceq $before.Fingerprint -and $script:EngineCalls -eq 0) 'Preview is read-only and does not require the engine'
    $result=Repair-ProgramRule $plan;$entries=@(Get-ProgramLaunchEntries);$updated=Get-Content -LiteralPath (Join-Path $script:DataRoot 'program-proxies.json') -Raw|ConvertFrom-Json
    Check ($entries.Count -eq 1 -and $entries[0].path -ieq $newExe -and $entries[0].route -eq 'upstream' -and $entries[0].identity.PackageVerified) 'Repair migrates the actual launch record and preserves its route'
    Check ($updated.note -eq 'preserve-launch-metadata' -and $updated.entries[0].note -eq 'preserve-entry') 'Unrelated saved metadata is retained'
    $newRecord=Get-ProgramShortcutRecords|Select-Object -First 1;$link=Read-TestShortcut $script:Shortcut
    Check ($newRecord.program -ieq $newExe -and $link.Arguments.Contains((ConvertTo-ProgramArgument $newExe)) -and $link.WorkingDirectory -ieq [IO.Path]::GetDirectoryName($newExe)) 'Owned launcher now starts the new path using the current application and data directory'
    Check ($newRecord.originalBackup -eq $originalBackup -and (Get-FileHash -LiteralPath $originalBackup).Hash -eq $originalHash) 'Original shortcut backup is preserved byte for byte and retains its reference'
    Check ((Test-Path -LiteralPath $result.Backup) -and $script:EngineCalls -eq 0 -and $result.Message -match '未重启') 'Repair records a private rollback backup without launching clients or an engine'
    Remove-SavedProgramRule $newExe|Out-Null
    Check (@(Get-ProgramLaunchEntries).Count -eq 0 -and (Read-TestShortcut $script:Shortcut).Target -ieq $newExe -and -not (Read-TestShortcut $script:Shortcut).Arguments -and $script:EngineCalls -eq 0) 'Removing a repaired launch rule works offline and restores a non-proxy launcher for the confirmed new version'
    Check ((Get-FileHash -LiteralPath $originalBackup).Hash -eq $originalHash) 'Restoring an updated native launcher still preserves the immutable original backup'
    New-TestCase 'separate-remove' -SeparateShortcut
    Remove-SavedProgramRule $oldExe|Out-Null
    Check (-not (Test-Path -LiteralPath $script:Shortcut)) 'Removing an owned separately created launcher safely deletes that launcher'
    New-TestCase 'external-shortcut'
    Set-TestShortcutArguments $script:Shortcut '-NoProfile -ExternalChoice';$externalHash=(Get-FileHash -LiteralPath $script:Shortcut).Hash
    $result=Repair-ProgramRule (Get-ProgramRuleRepairPlan $oldExe)
    Check ($result.PreservedShortcuts -eq 1 -and (Get-FileHash -LiteralPath $script:Shortcut).Hash -eq $externalHash) 'Repair preserves a shortcut modified outside FlowSwitch and reports it'
    Remove-SavedProgramRule $newExe|Out-Null
    Check ((Get-FileHash -LiteralPath $script:Shortcut).Hash -eq $externalHash) 'Removing the repaired rule also preserves the external shortcut'
    New-TestCase 'stale-plan'
    $plan=Get-ProgramRuleRepairPlan $oldExe;$state=Get-Content -LiteralPath (Join-Path $script:DataRoot 'program-proxies.json') -Raw|ConvertFrom-Json;$state.entries[0].route='Direct';Write-LocalJson (Join-Path $script:DataRoot 'program-proxies.json') $state
    Throws {Repair-ProgramRule $plan} '已经变化'
    Check ((Get-ProgramLaunchEntries).route -eq 'Direct' -and (Get-ProgramLaunchEntries).path -ieq $oldExe) 'Stale preview cannot overwrite a newer route choice'
    $plan=Get-ProgramRuleRepairPlan $oldExe;$plan.CreatedAt=[DateTime]::UtcNow.AddMinutes(-3).ToString('o')
    Throws {Repair-ProgramRule $plan} '已过期'
    $plan=Get-ProgramRuleRepairPlan $oldExe;$plan.DataDirectory=Join-Path $qa 'unrelated-data'
    Throws {Repair-ProgramRule $plan} '其他配置目录'
    $plan=Get-ProgramRuleRepairPlan $oldExe;$plan.CurrentPath=Join-Path $qa 'impostor.exe'
    Throws {Repair-ProgramRule $plan} '已经变化'
    New-TestCase 'new-version-during-plan'
    $plan=Get-ProgramRuleRepairPlan $oldExe
    $thirdFull='FlowSwitch.RepairTest_3.0.0.0_x64__8wekyb3d8bbwe';$thirdRoot=Join-Path $qa ('WindowsApps\'+$thirdFull);$thirdExe=Join-Path $thirdRoot 'app\client.exe'
    [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($thirdExe));[IO.File]::WriteAllText($thirdExe,'another version fixture')
    $script:TestPackages+=@([pscustomobject]@{InstallLocation=$thirdRoot;PackageFullName=$thirdFull;PackageFamilyName=[LocalProxySwitch.ProgramFileIdentity]::FamilyFromFullName($thirdFull);Verified=$true})
    Throws {Repair-ProgramRule $plan} '没有唯一'
    Check ((Get-ProgramLaunchEntries).path -ieq $oldExe) 'A newly appearing second package candidate invalidates a pending repair without writing'
    $script:TestPackages=@($script:TestPackages|Where-Object PackageFullName -eq $newFull)
    New-TestCase 'target-conflict'
    $state=Get-Content -LiteralPath (Join-Path $script:DataRoot 'program-proxies.json') -Raw|ConvertFrom-Json;$state.entries+=@([pscustomobject]@{path=$newExe;route='Direct';adapter='chromium'});Write-LocalJson (Join-Path $script:DataRoot 'program-proxies.json') $state
    Throws {Get-ProgramRuleRepairPlan $oldExe} '已经存在保存记录'
    New-TestCase 'file-rollback'
    $before=Get-RuleMaintenanceSnapshot $oldExe;$script:FailFile='program-proxies.json'
    Throws {Repair-ProgramRule (Get-ProgramRuleRepairPlan $oldExe)} 'Injected.*回滚'
    Check ((Get-RuleMaintenanceSnapshot $oldExe).Fingerprint -ceq $before.Fingerprint) 'A later write failure rolls back owned shortcut bytes and metadata'
    New-TestCase 'external-during-rollback'
    $script:FailFile='program-shortcuts.json';$script:ExternalShortcut=$true
    Throws {Repair-ProgramRule (Get-ProgramRuleRepairPlan $oldExe)} '保留外部修改'
    Check ((Read-TestShortcut $script:Shortcut).Arguments -eq '-NoProfile -ExternalChoice' -and (Get-ProgramLaunchEntries).path -ieq $oldExe) 'Rollback preserves an outside shortcut edit made after FlowSwitch wrote the launcher'
    New-TestCase 'compare-and-swap'
    $image=Read-RuleMaintenanceFile (Join-Path $script:DataRoot 'program-proxies.json');[IO.File]::WriteAllText($image.Path,'outside text')
    Throws {Set-RuleMaintenanceFile $image ([Text.Encoding]::UTF8.GetBytes('overwrite'))} 'changed after'
    Check ([IO.File]::ReadAllText($image.Path) -eq 'outside text') 'The file writer checks the expected bytes while holding an exclusive handle'
    New-TestCase 'engine-repair' -Engine
    $result=Repair-ProgramRule (Get-ProgramRuleRepairPlan $oldExe);$engine=Get-Content -LiteralPath (Join-Path $script:DataRoot 'app-rules.json') -Raw|ConvertFrom-Json
    Check ($engine.entries[0].path -ieq $newExe -and $engine.entries[0].route -eq 'upstream' -and $engine.defaultRoute -eq 'Direct' -and $script:ReplaceCalls -eq 1) 'Engine repair uses conditional replace and preserves the default and selected routes'
    Check ($result.EngineChanged -and -not $result.LaunchChanged) 'Engine-only repair does not manufacture a launch rule'
    Remove-SavedProgramRule $newExe|Out-Null
    Check (@((Get-Content -LiteralPath (Join-Path $script:DataRoot 'app-rules.json') -Raw|ConvertFrom-Json).entries).Count -eq 0) 'Engine record removal is applied through the same verified replace API'
    New-TestCase 'offline-engine' -Engine
    $plan=Get-ProgramRuleRepairPlan $oldExe;$script:EngineOnline=$false;$before=Get-RuleMaintenanceSnapshot $oldExe
    Throws {Repair-ProgramRule $plan} 'offline'
    Check ((Get-RuleMaintenanceSnapshot $oldExe).Fingerprint -ceq $before.Fingerprint -and $script:ReplaceCalls -eq 0) 'Offline engine repair leaves all saved files unchanged and never starts the engine'
    New-TestCase 'mixed-rollback' -Engine -Mixed
    $before=Get-RuleMaintenanceSnapshot $oldExe;$script:FailFile='program-shortcuts.json'
    Throws {Repair-ProgramRule (Get-ProgramRuleRepairPlan $oldExe)} 'Injected.*回滚'
    $engine=Get-Content -LiteralPath (Join-Path $script:DataRoot 'app-rules.json') -Raw|ConvertFrom-Json
    Check ($engine.entries[0].path -ieq $oldExe -and $script:ReplaceCalls -eq 2 -and (Get-ProgramLaunchEntries).path -ieq $oldExe) 'Mixed repair failure conditionally restores engine rules and launch records'
    New-TestCase 'external-engine-rollback' -Engine -Mixed
    $script:FailFile='program-shortcuts.json';$script:ExternalEngine=$true
    Throws {Repair-ProgramRule (Get-ProgramRuleRepairPlan $oldExe)} '保留外部修改'
    $engine=Get-Content -LiteralPath (Join-Path $script:DataRoot 'app-rules.json') -Raw|ConvertFrom-Json
    Check ($engine.external -eq 'preserve' -and $script:ReplaceCalls -eq 1) 'Mixed rollback never overwrites an engine state edited after the successful replace'
    Write-Output ('PASS: '+$script:Pass+' rule maintenance checks; isolated files, real temporary shortcuts, and a conditional engine fixture.')
}finally{
    $resolved=[IO.Path]::GetFullPath($qa);$prefix=[IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')+'\'
    if($resolved.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase) -and [IO.Path]::GetFileName($resolved).StartsWith('FlowSwitch-rule-maintenance-')){Remove-Item -LiteralPath $resolved -Recurse -Force}
}
