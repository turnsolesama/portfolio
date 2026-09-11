$ErrorActionPreference='Stop'
$qa=Join-Path $env:TEMP ('FlowSwitch-family-'+[Guid]::NewGuid().ToString('N'))
$script:DataRoot=Join-Path $qa 'private-data'
[void][IO.Directory]::CreateDirectory($qa)
. (Join-Path $PSScriptRoot 'ProcessInventory.ps1')
. (Join-Path $PSScriptRoot 'ProgramIdentity.ps1')
. (Join-Path $PSScriptRoot 'ProgramFamilyTracking.ps1')
$script:Pass=0
function Check($Value,[string]$Message){if(-not $Value){throw $Message};$script:Pass++}
$app=Join-Path $qa 'IDE.exe';$worker=Join-Path $qa 'worker.exe';$grand=Join-Path $qa 'grandchild.exe';$unrelated=Join-Path $qa 'unrelated.exe'
$outsideDirectory=Join-Path $qa 'other-install';[void][IO.Directory]::CreateDirectory($outsideDirectory);$outside=Join-Path $outsideDirectory 'worker.exe'
foreach($path in @($app,$worker,$grand,$unrelated,$outside)){[IO.File]::WriteAllText($path,'identity fixture only')}
$birth=[DateTime]::UtcNow.AddMinutes(-1)
function ProcessRow([int]$Id,[int]$ParentId,[string]$Path,[int]$Age=0){[pscustomobject]@{Id=$Id;ParentId=$ParentId;Path=$Path;PathStatus='Available';ProcessName=[IO.Path]::GetFileNameWithoutExtension($Path);StartTime=$birth.AddSeconds($Age)}}
function Observe($Rows,[bool]$Available=$true,$Context=$null){
    if(-not $Context){$Context=New-ProgramIdentityContext -Processes $Rows -Packages @()}
    Get-ProgramFamilyTrackingSnapshot $app $Rows $Context $Available
}
function Reset-Family {[LocalProxySwitch.ProgramFamilyTracker]::Clear((Get-ProgramFamilyTrackingScope $app))}
$main=ProcessRow 100 1 $app;$child=ProcessRow 101 100 $worker 1;$grandchild=ProcessRow 102 101 $grand 2
$stranger=ProcessRow 103 1 $unrelated 1
$first=Observe @($main,$child,$stranger)
Check (($first.Members.Id -join ',') -match '100' -and $first.Members.Id -contains 101 -and $first.Members.Id -notcontains 103) 'Only observed parent-child relations are joined, not unrelated programs in the directory'
$orphan=Observe @($child,$stranger)
Check ($orphan.Members.Id -contains 101 -and $orphan.RetainedIds -contains 101) 'A living verified worker remains associated after its root exits'
$next=Observe @($child,$grandchild,$stranger)
Check ($next.Members.Id -contains 101 -and $next.Members.Id -contains 102 -and $next.Members.Id -notcontains 103) 'An observed retained worker may later create a verified grandchild'
$unreadable=$child.PSObject.Copy();$unreadable.Path='';$unreadable.PathStatus='AccessDenied';$unreadable.StartTime=[DateTime]::MinValue
$unknown=Observe @($unreadable)
Check ($unknown.Members.Count -eq 0 -and $unknown.UnknownIds -contains 101) 'Unavailable process identity is unknown and cannot be claimed from cache'
$restored=Observe @($child)
Check ($restored.Members.Id -contains 101) 'Identity can be revalidated after a transient unavailable read'
$failure=Observe @() $false
Check (-not $failure.Available -and $failure.Members.Count -eq 0 -and $failure.UnknownIds -contains 101) 'Failed whole inventory preserves only unknown relationship evidence'
Check ((Observe @($child)).Members.Id -contains 101) 'An unavailable snapshot cannot erase the previously observed relationship'
$reused=ProcessRow 101 1 $worker 20
Check ((Observe @($reused)).Members.Count -eq 0) 'PID reuse with another start time never inherits the former worker membership'
Check ((Observe @($child)).Members.Count -eq 0) 'Once disproved, a cached member cannot be resurrected by an old identity alone'
Reset-Family
$lateChild=ProcessRow 104 100 $worker -2
Check ((Observe @($main,$lateChild)).Members.Id -notcontains 104) 'A process predating its apparent parent is not a child'
$otherRoot=Join-Path ([IO.Path]::GetDirectoryName($qa)) ('other-family-'+[Guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($otherRoot);$externalExe=Join-Path $otherRoot 'worker.exe';[IO.File]::WriteAllText($externalExe,'external fixture')
$external=ProcessRow 105 100 $externalExe 3
Check ((Observe @($main,$external)).Members.Id -notcontains 105) 'A real parent relationship cannot claim a worker outside the installation directory'
$noTicks=ProcessRow 106 100 $worker 2;$noTicks.StartTime=[DateTime]::MinValue
$partial=Observe @($main,$noTicks)
Check ($partial.Members.Id -notcontains 106 -and $partial.UnknownIds -contains 106) 'A child without creation-time evidence is unknown'
Reset-Family
$partialRoot=$main.PSObject.Copy();$partialRoot.StartTime=[DateTime]::MinValue
$partial=Observe @($partialRoot,$child)
Check ($partial.Members.Id -contains 100 -and $partial.Members.Id -notcontains 101 -and $partial.UnknownIds -contains 100) 'Direct root presence survives missing ticks but cannot authorize child inheritance'
Reset-Family
$null=Observe @($main,$child)
$priorScope=$script:DataRoot;$script:DataRoot=Join-Path $qa 'other-data'
Check ((Observe @($child)).Members.Count -eq 0) 'Independent configuration directories cannot inherit each other''s family evidence'
$script:DataRoot=$priorScope
Check ((Observe @($child)).Members.Id -contains 101) 'Returning to the original scope retains its own verified relation'
Reset-Family
$null=Observe @($main,$child)
$changed=$child.PSObject.Copy();$changed.Path=$unrelated
Check ((Observe @($changed)).Members.Count -eq 0) 'Equal PID and ticks with another executable cannot reuse membership'
Reset-Family
$null=Observe @($main,$child)
$empty=Observe @()
Check ((Observe @($child)).Members.Count -eq 0) 'A confirmed empty inventory expires previous members'
Reset-Family
$null=Observe @($main,$child)
$originalWorker=$worker+'.original';[IO.File]::Move($worker,$originalWorker);[IO.File]::WriteAllText($worker,'replacement identity fixture')
try{Check ((Observe @($child)).Members.Count -eq 0) 'A replaced executable file cannot retain old membership through equal PID, ticks and pathname'}
finally{[IO.File]::Delete($worker);[IO.File]::Move($originalWorker,$worker)}
Reset-Family
$oldContext=New-ProgramIdentityContext -Packages @()
Start-Sleep -Milliseconds 10
$null=Observe @($main,$child,$grandchild)
$null=Observe @($main) $true $oldContext
Check ((Observe @($child,$grandchild)).Members.Count -eq 2) 'An older overlapping snapshot cannot replace a later runspace''s evidence'

# Genuine shared-host runspaces, with thread-safe native identity values and no shared mutable PSObject state.
$context=New-ProgramIdentityContext -Packages @();$file=Get-ProgramIdentityDescriptor $app $context;$workerFile=Get-ProgramIdentityDescriptor $worker $context
$nativeRoot=New-Object LocalProxySwitch.ProgramFamilyEvidence;$nativeRoot.Id=201;$nativeRoot.ParentId=1;$nativeRoot.Path=$file.CanonicalPath;$nativeRoot.FileId=$file.FileId;$nativeRoot.StartTicks=$birth.Ticks;$nativeRoot.Verified=$true;$nativeRoot.Root=$true;$nativeRoot.Inside=$true
$nativeChild=New-Object LocalProxySwitch.ProgramFamilyEvidence;$nativeChild.Id=202;$nativeChild.ParentId=201;$nativeChild.Path=$workerFile.CanonicalPath;$nativeChild.FileId=$workerFile.FileId;$nativeChild.StartTicks=$birth.AddSeconds(1).Ticks;$nativeChild.Verified=$true;$nativeChild.Inside=$true
$concurrentScope=(Get-ProgramFamilyTrackingScope $app)+'|concurrency';$jobs=@()
try{
    for($n=0;$n -lt 8;$n++){
        $ps=[PowerShell]::Create()
        [void]$ps.AddScript('param($scope,$root,$child) 1..25|ForEach-Object {$r=[LocalProxySwitch.ProgramFamilyTracker]::Observe($scope,@($root,$child),[DateTime]::UtcNow.Ticks,$true);if($r.MemberIds.Length -ne 2){throw "Lost member during parallel refresh"}};"complete"').AddArgument($concurrentScope).AddArgument($nativeRoot).AddArgument($nativeChild)
        $jobs+=@([pscustomobject]@{PowerShell=$ps;Handle=$ps.BeginInvoke()})
    }
    foreach($job in $jobs){$result=$job.PowerShell.EndInvoke($job.Handle);Check (-not $job.PowerShell.HadErrors -and $result -contains 'complete') 'Concurrent runspace snapshots remain coherent'}
    $retained=[LocalProxySwitch.ProgramFamilyTracker]::Observe($concurrentScope,@($nativeChild),[DateTime]::UtcNow.Ticks,$true)
    Check ($retained.MemberIds -contains 202 -and $retained.RetainedIds -contains 202) 'Shared runspace evidence survives a subsequent root exit'
}finally{foreach($job in $jobs){$job.PowerShell.Dispose()}}
for($n=0;$n -lt 80;$n++){[void][LocalProxySwitch.ProgramFamilyTracker]::Observe(($concurrentScope+'|bounded-'+$n),@($nativeRoot,$nativeChild),[DateTime]::UtcNow.Ticks,$true)}
Check ([LocalProxySwitch.ProgramFamilyTracker]::FamilyCount -le 64) 'Session evidence has a hard scope bound even while many programs are observed'

# Real, isolated processes: observe both while alive, let the root exit itself, then create a grandchild.
$realDirectory=Join-Path $qa 'real-processes';[void][IO.Directory]::CreateDirectory($realDirectory)
$realApp=Join-Path $realDirectory 'FixtureIDE.exe';$realWorker=Join-Path $realDirectory 'worker.exe';$owned=@()
$source=@'
using System;
using System.IO;
using System.Diagnostics;
using System.Threading;
public static class FamilyFixture {
 public static void Main(string[] args) {
  string mode=args[0],dir=args[1];
  if(mode=="root") {
   var info=new ProcessStartInfo(Path.Combine(dir,"worker.exe"),"worker \""+dir+"\"");info.UseShellExecute=false;info.CreateNoWindow=true;
   using(var child=Process.Start(info)){File.WriteAllText(Path.Combine(dir,"worker.pid"),child.Id.ToString());}
   File.WriteAllText(Path.Combine(dir,"root.ready"),"ready");
   while(!File.Exists(Path.Combine(dir,"root.stop"))&&!File.Exists(Path.Combine(dir,"all.stop")))Thread.Sleep(25);
  } else {
   File.WriteAllText(Path.Combine(dir,mode+".ready"),"ready");bool spawned=false;
   while(!File.Exists(Path.Combine(dir,"all.stop"))) {
    if(mode=="worker"&&!spawned&&File.Exists(Path.Combine(dir,"grand.start"))) {
     var info=new ProcessStartInfo(Path.Combine(dir,"worker.exe"),"grand \""+dir+"\"");info.UseShellExecute=false;info.CreateNoWindow=true;
     using(var child=Process.Start(info)){File.WriteAllText(Path.Combine(dir,"grand.pid"),child.Id.ToString());}spawned=true;
    }
    Thread.Sleep(25);
   }
  }
 }
}
'@
Add-Type -TypeDefinition $source -OutputAssembly $realApp -OutputType ConsoleApplication
Copy-Item -LiteralPath $realApp -Destination $realWorker
function Wait-File([string]$Path){$until=[DateTime]::UtcNow.AddSeconds(10);while(-not [IO.File]::Exists($Path) -and [DateTime]::UtcNow -lt $until){Start-Sleep -Milliseconds 25};if(-not [IO.File]::Exists($Path)){throw 'Isolated fixture did not become ready'}}
function Real-Observe {$rows=@(Get-ProcessInventory);Get-ProgramFamilyTrackingSnapshot $realApp $rows (New-ProgramIdentityContext -Processes $rows -Packages @())}
try{
    $rootProcess=Start-Process -FilePath $realApp -ArgumentList @('root',('"'+$realDirectory+'"')) -WindowStyle Hidden -PassThru;$owned+=@($rootProcess)
    Wait-File (Join-Path $realDirectory 'root.ready');Wait-File (Join-Path $realDirectory 'worker.ready')
    $workerId=[int][IO.File]::ReadAllText((Join-Path $realDirectory 'worker.pid'));$owned+=@([Diagnostics.Process]::GetProcessById($workerId))
    $first=Real-Observe
    Check ($first.Members.Id -contains $rootProcess.Id -and $first.Members.Id -contains $workerId) 'Limited-query inventory observes the real isolated parent and worker'
    [IO.File]::WriteAllText((Join-Path $realDirectory 'root.stop'),'stop');Check ($rootProcess.WaitForExit(5000)) 'The real root exits normally without terminating its worker'
    $orphan=Real-Observe
    Check ($orphan.Members.Id -contains $workerId -and $orphan.RetainedIds -contains $workerId) 'The real surviving worker remains associated after root exit'
    [IO.File]::WriteAllText((Join-Path $realDirectory 'grand.start'),'start');Wait-File (Join-Path $realDirectory 'grand.ready');Wait-File (Join-Path $realDirectory 'grand.pid')
    $grandId=[int][IO.File]::ReadAllText((Join-Path $realDirectory 'grand.pid'));$owned+=@([Diagnostics.Process]::GetProcessById($grandId))
    $expanded=Real-Observe
    Check ($expanded.Members.Id -contains $workerId -and $expanded.Members.Id -contains $grandId) 'A real orphan worker''s later grandchild joins through verified creation-time and executable evidence'
    Check (-not (Test-Path -LiteralPath $script:DataRoot)) 'Family observation creates no persistent private record or configuration directory'
}finally{
    [IO.File]::WriteAllText((Join-Path $realDirectory 'all.stop'),'stop')
    foreach($process in $owned){try{if(-not $process.WaitForExit(5000)){$process.Kill();$process.WaitForExit()}}finally{$process.Dispose()}}
}
Check (@(Get-ProcessInventory|Where-Object {$_.Path -in @($realApp,$realWorker)}).Count -eq 0) 'All isolated fixture processes exit; no user applications were touched'
Write-Output ('PASS: '+$script:Pass+' family tracking assertions, including real orphan workers and concurrent runspaces; no network changes or persisted process evidence.')
