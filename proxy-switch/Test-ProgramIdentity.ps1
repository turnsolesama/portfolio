$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProcessInventory.ps1')
. (Join-Path $PSScriptRoot 'ProgramIdentity.ps1')
$script:Pass=0
function Check($Value,[string]$Message){if(-not $Value){throw $Message};$script:Pass++}
function New-TestProcess([int]$ProcessId,[string]$Path){[pscustomobject]@{Id=$ProcessId;Path=$Path;ProcessName='IdentityTest'}}
$testRoot=Join-Path ([IO.Path]::GetTempPath()) ('FlowSwitch-identity-'+[Guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($testRoot)
$alias=Join-Path $testRoot 'alias';$hardlink=Join-Path $testRoot 'hardlink.exe'
try{
    $real=Join-Path $testRoot 'real';$other=Join-Path $testRoot 'other'
    [void][IO.Directory]::CreateDirectory($real);[void][IO.Directory]::CreateDirectory($other)
    $exe=Join-Path $real 'client.exe';$otherExe=Join-Path $other 'client.exe'
    [IO.File]::WriteAllText($exe,'test fixture only');[IO.File]::WriteAllText($otherExe,'same name and bytes, different file')
    [void](New-Item -ItemType Junction -Path $alias -Target $real)
    [void](New-Item -ItemType HardLink -Path $hardlink -Target $exe)
    $processes=@((New-TestProcess 101 $exe),(New-TestProcess 202 ''),(New-TestProcess 303 $otherExe))
    $context=New-ProgramIdentityContext -Processes $processes -Packages @()
    $a=Get-ProgramIdentityDescriptor $exe $context
    Check ($a.Exists -and $a.FileId -and $a.CanonicalPath -ieq $exe) 'Native file metadata provides canonical path and file ID'
    Check ([object]::ReferenceEquals($a,(Get-ProgramIdentityDescriptor $exe $context))) 'File identity is cached only inside the refresh context'
    Check (Test-ProgramPathEquivalent $exe (Join-Path $alias 'client.exe') $context) 'A real junction aliases the same executable'
    Check (Test-ProgramPathEquivalent $exe $hardlink $context) 'A real hardlink aliases the same executable'
    Check (-not (Test-ProgramPathEquivalent $exe $otherExe $context)) 'Same filename in another directory is never equivalent'
    Check (-not (Test-ProgramPathEquivalent '' '' $context)) 'Unreadable paths are not equal identities'
    Check (-not (ConvertTo-ProgramIdentityPath 'client.exe')) 'Relative executable paths cannot become implicit identities'
    Check (-not (ConvertTo-ProgramIdentityPath '\\.\PhysicalDrive0')) 'Device paths are excluded'
    $network=Get-ProgramIdentityDescriptor '\\no-such-server\share\client.exe' $context
    Check ($network.PathStatus -eq 'NetworkPathUnverified' -and -not $network.Exists) 'Passive inventory never probes an SMB path'
    $match=Resolve-ProgramIdentity $exe -Context $context
    Check ($match.Reason -eq 'ExactPath' -and $match.PIDs.Count -eq 1 -and $match.PIDs[0] -eq 101 -and -not $match.RequiresRepair) 'Exact paths match incomplete process fixture records without requiring package fields'
    $match=Resolve-ProgramIdentity (Join-Path $alias 'client.exe') -Context $context
    Check ($match.Reason -eq 'SameFile' -and $match.CurrentPath -ieq $exe -and $match.PIDs[0] -eq 101) 'Junction rule finds the real running image'
    Check ($match.RequiresRepair -and $match.CanRepair) 'An alias identity cannot silently assert that a literal engine PROCESS-PATH rule applies'
    $match=Resolve-ProgramIdentity (Join-Path $testRoot 'missing\client.exe') -Context $context
    Check ($match.Reason -eq 'MissingPath' -and -not $match.CanRepair -and -not $match.PIDs.Count) 'A missing arbitrary path never attaches to a same-name process'
    $match=Resolve-ProgramIdentity '' -Context $context
    Check ($match.Reason -eq 'PathUnavailable' -and -not $match.CanRepair) 'Unavailable paths remain unknown'
    $before=[IO.File]::ReadAllText($exe)
    # Registration fixtures exercise package matching without installing a package or writing Windows settings.
    $store=Join-Path $testRoot 'WindowsApps'
    $oldFull='FlowSwitch.IdentityTest_1.0.0.0_x64__8wekyb3d8bbwe'
    $newFull='FlowSwitch.IdentityTest_2.0.0.0_x64__8wekyb3d8bbwe'
    $family=[LocalProxySwitch.ProgramFileIdentity]::FamilyFromFullName($newFull)
    Check ($family -eq 'FlowSwitch.IdentityTest_8wekyb3d8bbwe') 'Windows parses the package family from a valid package full name'
    Check (-not [LocalProxySwitch.ProgramFileIdentity]::FamilyFromFullName('client.exe')) 'Windows rejects an invalid package full name'
    $newRoot=Join-Path $store $newFull;$newExe=Join-Path $newRoot 'app\client.exe'
    [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($newExe));[IO.File]::WriteAllText($newExe,'package fixture')
    $oldExe=Join-Path (Join-Path $store $oldFull) 'app\client.exe'
    $registration=[pscustomobject]@{InstallLocation=$newRoot;PackageFamilyName=$family;PackageFullName=$newFull;Verified=$true}
    $newProcess=New-TestProcess 404 $newExe
    $packageContext=New-ProgramIdentityContext -Processes @($newProcess) -Packages @($registration)
    $match=Resolve-ProgramIdentity $oldExe -Context $packageContext
    Check ($match.Reason -eq 'PackageUpgradeCandidate' -and $match.Confidence -eq 'Candidate' -and $match.CurrentPath -ieq $newExe) 'Legacy missing MSIX path produces a uniquely verified installed candidate'
    Check ($match.RequiresRepair -and $match.CanRepair -and $match.PIDs[0] -eq 404) 'Legacy candidate explicitly requires repair and can show current process evidence'
    Check ($match.Identity.PackageVerified -and $match.Identity.RelativeExecutable -eq 'app\client.exe') 'Candidate identity records the package-internal executable path'
    $deniedContext=New-ProgramIdentityContext -Processes @($newProcess) -Packages @($registration)
    $denied=Get-ProgramIdentityDescriptor $oldExe $deniedContext;$denied.PathStatus='AccessDenied'
    $deniedResult=Resolve-ProgramIdentity $oldExe -Context $deniedContext
    Check ($deniedResult.Reason -eq 'PathUnavailable' -and -not $deniedResult.CanRepair) 'Access denial is unknown and does not prove that an old installation needs replacement'
    $saved=$match.Identity | ConvertTo-Json | ConvertFrom-Json
    $saved.Path=$oldExe;$saved.PackageFullName=$oldFull
    $match=Resolve-ProgramIdentity $oldExe -Context $packageContext -SavedIdentity $saved
    Check ($match.Reason -eq 'PackageIdentity' -and $match.Confidence -eq 'Verified' -and $match.RequiresRepair) 'Recorded package identity recognizes an upgrade without applying a rule'
    $saved.Path=Join-Path $testRoot 'unrelated.exe'
    $match=Resolve-ProgramIdentity $oldExe -Context $packageContext -SavedIdentity $saved
    Check ($match.Confidence -eq 'Candidate') 'Saved identity bound to a different path cannot promote a legacy guess to verified'
    $match=Resolve-ProgramIdentity (Join-Path (Join-Path $store $oldFull) 'tools\client.exe') -Context $packageContext
    Check (-not $match.CanRepair -and -not $match.PIDs.Count) 'Same package and filename at another relative path is not the same application'
    $spoofFull='FlowSwitch.IdentityTest_1.0.0.0_x64__cw5n1h2txyewy'
    $match=Resolve-ProgramIdentity (Join-Path (Join-Path $store $spoofFull) 'app\client.exe') -Context $packageContext
    Check (-not $match.CanRepair -and -not $match.PIDs.Count) 'A different publisher is never a package match'
    $untrusted=$registration|ConvertTo-Json|ConvertFrom-Json;$untrusted.Verified=$false
    $match=Resolve-ProgramIdentity $oldExe -Context (New-ProgramIdentityContext -Processes @($newProcess) -Packages @($untrusted))
    Check (-not $match.CanRepair) 'An unverified package registration is rejected'
    $impostorLink=Join-Path $newRoot 'impostor';[void](New-Item -ItemType Junction -Path $impostorLink -Target $other)
    try{
        $impostor=Get-ProgramIdentityDescriptor (Join-Path $impostorLink 'client.exe') $packageContext
        Check (-not $impostor.PackageVerified -and $impostor.CanonicalPath -ieq $otherExe) 'A package-looking path redirected outside its registered root cannot impersonate package identity'
    }finally{[IO.Directory]::Delete($impostorLink)}
    $forgedProcess=New-TestProcess 405 $newExe;$forgedProcess|Add-Member NoteProperty PackageFamilyName 'Different.Publisher_cw5n1h2txyewy'
    $match=Resolve-ProgramIdentity $oldExe -Context (New-ProgramIdentityContext -Processes @($forgedProcess) -Packages @($registration))
    Check (-not $match.CanRepair) 'A process package contradiction cannot be repaired or merged'
    $thirdFull='FlowSwitch.IdentityTest_3.0.0.0_x64__8wekyb3d8bbwe';$thirdRoot=Join-Path $store $thirdFull
    $thirdExe=Join-Path $thirdRoot 'app\client.exe';[void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($thirdExe));[IO.File]::WriteAllText($thirdExe,'another valid candidate')
    $thirdRegistration=[pscustomobject]@{InstallLocation=$thirdRoot;PackageFamilyName=$family;PackageFullName=$thirdFull;Verified=$true}
    $match=Resolve-ProgramIdentity $oldExe -Context (New-ProgramIdentityContext -Processes @($newProcess) -Packages @($registration,$thirdRegistration))
    Check ($match.Reason -eq 'Ambiguous' -and -not $match.CurrentPath -and -not $match.CanRepair -and $match.CandidatePaths.Count -eq 2) 'Two installed versions remain ambiguous even when only one is observed running'
    $match=Resolve-ProgramIdentity $newExe -Context (New-ProgramIdentityContext -Processes @() -Packages @($registration,$thirdRegistration))
    Check ($match.Reason -eq 'NotRunning' -and -not $match.RequiresRepair -and $match.CurrentPath -eq $newExe) 'An existing exact executable is not silently upgraded to another installed version'
    $match=Resolve-ProgramIdentity $oldExe -Context (New-ProgramIdentityContext -Processes @((New-TestProcess 406 '')) -Packages @($registration))
    Check ($match.CanRepair -and -not $match.PIDs.Count) 'An installed candidate is not evidence that a path-unreadable PID belongs to it'
    Check ([IO.File]::ReadAllText($exe) -ceq $before -and -not (Test-Path -LiteralPath $oldExe)) 'Resolution writes neither source programs nor missing legacy paths'
    $canary=Join-Path $testRoot 'cache-canary.exe';[IO.File]::WriteAllText($canary,'cache fixture')
    $cached=Get-ProgramIdentityDescriptor $canary $context;[IO.File]::Delete($canary)
    Check ($cached.Exists -and -not (Get-ProgramIdentityDescriptor $canary (New-ProgramIdentityContext -Packages @())).Exists) 'A fresh context never carries old file existence across display rounds'
    $native=@(Get-ProcessInventory -Id $PID)
    Check ($native.Count -eq 1 -and $native[0].Path -and $native[0].PathStatus -eq 'Available') 'Native limited-query inventory reads this test process'
    Check ([LocalProxySwitch.ProcessCatalog]::QueryAccess -eq 0x1000) 'Inventory requests PROCESS_QUERY_LIMITED_INFORMATION only'
    Check (@(Get-ProcessInventory -Id 2147483647).Count -eq 0) 'A nonexistent PID returns no fabricated process identity'
    $source=[IO.File]::ReadAllText((Join-Path $PSScriptRoot 'ProgramIdentity.ps1'))
    Check ($source -notmatch 'Get-AuthenticodeSignature|Get-Process\.Path|\.MainModule|ReadProcessMemory') 'Identity matching does not enumerate modules, signatures or process memory'
    # Every call creates a fresh runspace, exactly like the application refresh worker.
    # Mock only Windows registration enumeration; the real process-static cache is exercised.
    $cacheWorker=@'
param($Module,$FullName,$Force,$Observed)
. $Module
$script:QueryCount=0;$script:FixtureFullName=$FullName
function Get-AppxPackage {
    $script:QueryCount++
    [pscustomobject]@{IsDevelopmentMode=$false;SignatureKind='Store';Status='Ok';InstallLocation=('C:\Program Files\WindowsApps\'+$script:FixtureFullName);PackageFullName=$script:FixtureFullName;PackageFamilyName=[LocalProxySwitch.ProgramFileIdentity]::FamilyFromFullName($script:FixtureFullName)}
}
$processes=@();if($Observed){$processes=@([pscustomobject]@{Id=99;Path='';PackageFullName=$Observed})}
$context=New-ProgramIdentityContext -Processes $processes -RefreshPackages:$Force
[pscustomobject]@{Queries=$script:QueryCount;Count=$context.Packages.Count;FullName=[string]$context.Packages[0].PackageFullName}
'@
    function Invoke-CacheWorker([string]$FullName,[bool]$Force,[string]$Observed=''){
        $worker=[powershell]::Create()
        try{
            [void]$worker.AddScript($cacheWorker).AddArgument((Join-Path $PSScriptRoot 'ProgramIdentity.ps1')).AddArgument($FullName).AddArgument($Force).AddArgument($Observed)
            $result=@($worker.Invoke());if($worker.HadErrors){throw ($worker.Streams.Error|Out-String)}
            $result[0]
        }finally{$worker.Dispose()}
    }
    $first=Invoke-CacheWorker $oldFull $true
    $second=Invoke-CacheWorker $newFull $false
    Check ($first.Queries -eq 1 -and $second.Queries -eq 0 -and $second.FullName -eq $oldFull) 'Two fresh runspaces share immutable registration metadata without repeating the OS query'
    $forced=Invoke-CacheWorker $newFull $true
    Check ($forced.Queries -eq 1 -and $forced.FullName -eq $newFull) 'Explicit RefreshPackages invalidates the process-wide cache'
    $upgraded=Invoke-CacheWorker $thirdFull $false $thirdFull
    Check ($upgraded.Queries -eq 1 -and $upgraded.FullName -eq $thirdFull) 'An unseen running PackageFullName invalidates stale metadata immediately'
    $reused=Invoke-CacheWorker $oldFull $false $thirdFull
    Check ($reused.Queries -eq 0 -and $reused.FullName -eq $thirdFull) 'An already known running package reuses metadata across another fresh runspace'
    $unknown='FlowSwitch.UnknownTest_1.0.0.0_x64__8wekyb3d8bbwe'
    $unavailable=Invoke-CacheWorker $thirdFull $false $unknown
    $stillUnavailable=Invoke-CacheWorker $thirdFull $false $unknown
    Check ($unavailable.Queries -eq 1 -and $stillUnavailable.Queries -eq 0) 'An unregistered observed package triggers one refresh and cannot cause repeated expensive queries'
    $parallelFull='FlowSwitch.IdentityTest_4.0.0.0_x64__8wekyb3d8bbwe';$workers=@();$results=@()
    try{
        foreach($index in 1..4){
            $worker=[powershell]::Create();[void]$worker.AddScript($cacheWorker).AddArgument((Join-Path $PSScriptRoot 'ProgramIdentity.ps1')).AddArgument($parallelFull).AddArgument($false).AddArgument($parallelFull)
            $workers+=@([pscustomobject]@{Worker=$worker;Handle=$worker.BeginInvoke()})
        }
        foreach($item in $workers){$results+=@($item.Worker.EndInvoke($item.Handle));if($item.Worker.HadErrors){throw ($item.Worker.Streams.Error|Out-String)}}
        Check (($results|Measure-Object Queries -Sum).Sum -eq 1 -and @($results|Where-Object {$_.FullName -ne $parallelFull}).Count -eq 0) 'Concurrent fresh runspaces serialize one registration refresh and receive the same metadata'
    }finally{foreach($item in $workers){$item.Worker.Dispose()}}
    Write-Output ('PASS: '+$script:Pass+' program identity checks; real junction/hardlink and isolated package fixtures.')
}finally{
    if(Test-Path -LiteralPath $alias){[IO.Directory]::Delete($alias)}
    $resolved=[IO.Path]::GetFullPath($testRoot);$tempPrefix=[IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')+'\'
    if($resolved.StartsWith($tempPrefix,[StringComparison]::OrdinalIgnoreCase) -and [IO.Path]::GetFileName($resolved).StartsWith('FlowSwitch-identity-')){Remove-Item -LiteralPath $resolved -Recurse -Force}
}
