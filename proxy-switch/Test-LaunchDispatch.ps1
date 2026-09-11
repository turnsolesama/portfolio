$ErrorActionPreference='Stop'
$qa=Join-Path $env:TEMP ('FlowSwitch-launch-dispatch-'+[Guid]::NewGuid().ToString('N'));[void][IO.Directory]::CreateDirectory($qa)
$script:Checks=0
function Check($Value,[string]$Message){if(-not $Value){throw $Message};$script:Checks++}
Add-Type -Path (Join-Path $PSScriptRoot 'DesktopBranding.cs')
Add-Type -TypeDefinition @'
using System;using System.IO;using System.Threading;
public sealed class FlowSlowLaunchRead : Stream {
    public override bool CanRead{get{return true;}}public override bool CanSeek{get{return false;}}public override bool CanWrite{get{return false;}}
    public override long Length{get{throw new NotSupportedException();}}public override long Position{get{throw new NotSupportedException();}set{throw new NotSupportedException();}}
    public override int Read(byte[] buffer,int offset,int count){Thread.Sleep(100);buffer[offset]=1;return 1;}
    public override void Flush(){}public override long Seek(long o,SeekOrigin s){throw new NotSupportedException();}public override void SetLength(long v){throw new NotSupportedException();}public override void Write(byte[] b,int o,int c){throw new NotSupportedException();}
}
'@
$lease=New-Object FlowSwitchWindowLease((Join-Path $qa 'lease'))
try{
    Check $lease.IsPrimary 'First lease owns its isolated data directory'
    Check ($lease.RequestLaunch('C:\Fixtures\editor.exe') -and $lease.RequestLaunch('C:\Fixtures\editor.exe')) 'Duplicate pending launch requests are accepted once'
    Check ($lease.ConsumeLaunch() -eq 'C:\Fixtures\editor.exe' -and $null -eq $lease.ConsumeLaunch()) 'Queued launch is consumed exactly once'
    foreach($bad in @('relative.exe','C:\Fixtures\script.ps1',('C:\Fixtures\app.exe'+"`n"),('C:\'+('a'*2049)+'.exe'))){Check (-not $lease.RequestLaunch($bad)) 'Invalid or oversized executable request is rejected'}
    foreach($n in 1..4){Check ($lease.RequestLaunch(('C:\Fixtures\app'+$n+'.exe'))) 'Bounded launch queue accepts available slot'}
    Check (-not $lease.RequestLaunch('C:\Fixtures\overflow.exe')) 'Launch queue rejects overflow instead of unlimited backlog'
    foreach($n in 1..4){Check ($lease.ConsumeLaunch() -eq ('C:\Fixtures\app'+$n+'.exe')) 'Accepted queued requests preserve their order'}
    $enqueue=$lease.GetType().GetMethod('EnqueueLaunch',[Reflection.BindingFlags]'Instance,NonPublic')
    Check (-not $enqueue.Invoke($lease,@('C:\Fixtures\stale.exe',[DateTime]::UtcNow.AddSeconds(-31).Ticks))) 'Expired request cannot be replayed'
    Check (-not $enqueue.Invoke($lease,@('C:\Fixtures\future.exe',[DateTime]::UtcNow.AddSeconds(10).Ticks))) 'Future timestamp cannot extend launch validity'
    $queue=$lease.GetType().GetField('launches',[Reflection.BindingFlags]'Instance,NonPublic').GetValue($lease)
    [void]$lease.RequestLaunch('C:\Fixtures\expired-queued.exe');$pending=$queue.Peek();$pending.GetType().GetField('Expires').SetValue($pending,[DateTime]::UtcNow.AddSeconds(-1).Ticks)
    Check ($lease.ConsumeExpiredLaunchCount() -eq 1 -and $null -eq $lease.ConsumeLaunch()) 'Expired queued request produces a user-notice count and cannot execute'
    $slow=New-Object FlowSlowLaunchRead;$read=$lease.GetType().GetMethod('ReadBounded',[Reflection.BindingFlags]'Static,NonPublic');$clock=[Diagnostics.Stopwatch]::StartNew();$rejected=$false
    try{[void]$read.Invoke($null,@($slow,40))}catch{$rejected=$true}finally{$slow.Dispose()}
    Check ($rejected -and $clock.Elapsed.TotalSeconds -lt 2.5) 'A slow stream has one absolute read deadline instead of extending timeout for every byte'
}finally{$lease.Dispose()}

# Real cold and hot script entry points use one persistent UI. The only launch
# implementation in this copied fixture records a counter; no user app runs.
$fixture=Join-Path $qa 'app';[void][IO.Directory]::CreateDirectory($fixture)
foreach($name in @('ProxySwitch.ps1','ProxyWindow.ps1','ProxyBackend.ps1','Preferences.ps1','Storage.ps1','RuntimeSupport.ps1','IndependentGateway.ps1','GatewayWatchdog.ps1','IndependentRouter.cjs','RoutePolicy.cjs','GatewayPortOwnership.ps1','DesktopBranding.cs','FlowTheme.cs','ProgramLaunch.ps1','ProcessInventory.ps1','ProgramIdentity.ps1','ApplicationObservation.ps1','RuleMaintenance.ps1','ProxyDiscovery.ps1','AppRouting.ps1','AppRouter.cjs','config.defaults.json','ManagedRouting.ps1','ProgramFamilyTracking.ps1','RoutePolicy.ps1')){if(Test-Path -LiteralPath (Join-Path $PSScriptRoot $name)){Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination $fixture}}
[void][IO.Directory]::CreateDirectory((Join-Path $fixture 'assets'));Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'assets\FlowSwitch.ico') -Destination (Join-Path $fixture 'assets\FlowSwitch.ico')
$data=Join-Path $qa 'settings';[void][IO.Directory]::CreateDirectory($data)
[IO.File]::WriteAllText((Join-Path $data 'config.json'),' {"Version":3,"Profiles":[],"Routing":{"Adapter":"none","ProfileId":""}}')
[IO.File]::WriteAllText((Join-Path $data 'ui-settings.json'),'{"CloseToTray":false}')
[IO.File]::WriteAllText((Join-Path $fixture 'fixture.exe'),'inert fixture, never executed')
[IO.File]::AppendAllText((Join-Path $fixture 'ProxyBackend.ps1'),@'

function Get-ManagedProgramIngress([string]$Executable){if($Executable -ieq (Join-Path $PSScriptRoot 'fixture.exe')){[pscustomobject]@{path=$Executable;id=('a'*32);port=18099;route='Follow'}}}
function Get-ProgramLaunchEntries {@()}
function Set-SystemSnapshot {throw 'Real network writes forbidden'}
function Set-UserProxyEnv {throw 'Real environment writes forbidden'}
function Invoke-AppRouter {throw 'Real engine writes forbidden'}
function Enable-IndependentGateway {throw 'No gateway starts in launch-dispatch fixture'}
function Set-UniversalProxy {throw 'No network switching in launch-dispatch fixture'}
function Get-TcpObservationSnapshot {[pscustomobject]@{Available=$true;Rows=@()}}
function Get-ApplicationRoutes {[pscustomobject]@{Available=$false;RulesAvailable=$false;TcpAvailable=$true;RuleCount=0;Rows=@()}}
function Get-ProxyStatus {[pscustomobject]@{Key='Direct';NetworkKey='Direct';NetworkName='Fixture direct';Aligned=$true;EnvConflict=$false;EndpointReady=$true;Drift=$false;Environment=@();Listeners=@();Warnings=@();CheckedAt='12:00:00';TcpAvailable=$true}}
function Sync-AutomaticProxyDiscovery {[pscustomobject]@{Detected=0;Added=0;Names=@();Cache=@();CheckedAt='12:00:00'}}
function Start-ManagedProgram([string]$Executable){
    if(-not (Get-ManagedProgramIngress $Executable)){throw 'Unconfigured launch forbidden'}
    $path=Join-Path $script:DataRoot 'dispatch.json';$items=@();if(Test-Path -LiteralPath $path){$items=@((Get-Content -LiteralPath $path -Raw|ConvertFrom-Json).Entries)}
    $items+=@([pscustomobject]@{OwnerPID=$PID;Sequence=$items.Count+1})
    Write-LocalJson $path ([pscustomobject]@{Entries=$items})
    [pscustomobject]@{PID=0;Message='Fixture launch received by resident UI'}
}
'@,(New-Object Text.UTF8Encoding($true)))
function Start-Fixture([switch]$NoUI){
    $psi=New-Object Diagnostics.ProcessStartInfo;$psi.FileName=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $psi.Arguments='-NoProfile -STA -ExecutionPolicy Bypass -File "'+(Join-Path $fixture 'ProxySwitch.ps1')+'" -DataDirectory "'+$data+'" -LaunchProgram "'+(Join-Path $fixture 'fixture.exe')+'"'+$(if($NoUI){' -NoUI'}else{''})
    $psi.UseShellExecute=$false;$psi.CreateNoWindow=$true;[Diagnostics.Process]::Start($psi)
}
function Wait-Dispatch([int]$Count){
    $deadline=[DateTime]::UtcNow.AddSeconds(20);$path=Join-Path $data 'dispatch.json'
    do{if(Test-Path -LiteralPath $path){try{$entries=@((Get-Content -LiteralPath $path -Raw|ConvertFrom-Json).Entries);if($entries.Count -ge $Count){return $entries}}catch{}};Start-Sleep -Milliseconds 100}while([DateTime]::UtcNow -lt $deadline)
    throw ('Launch dispatch did not reach expected count '+$Count)
}
$cold=$null;$hot=$null;$sync=$null
try{
    $cold=Start-Fixture;$first=@(Wait-Dispatch 1)
    Check (-not $cold.HasExited -and $first[0].OwnerPID -eq $cold.Id) 'Cold shortcut owns a resident UI before launching the application'
    $hot=Start-Fixture
    Check ($hot.WaitForExit(15000) -and $hot.ExitCode -eq 0) 'Hot shortcut exits after acknowledged handoff to existing UI'
    $second=@(Wait-Dispatch 2)
    Check ($second.Count -eq 2 -and $second[1].OwnerPID -eq $cold.Id) 'Hot request executes exactly once in the same resident owner'
    $sync=Start-Fixture -NoUI
    Check ($sync.WaitForExit(15000) -and $sync.ExitCode -eq 0) 'Explicit NoUI keeps synchronous test and command behavior'
    $third=@(Wait-Dispatch 3)
    Check ($third[2].OwnerPID -eq $sync.Id -and -not $cold.HasExited) 'Synchronous fixture cannot replace or terminate the resident UI'
    $cold.Refresh();Check ($cold.MainWindowHandle -ne 0) 'Resident UI remains accessible after both shortcut launchers finish'
    [void]$cold.CloseMainWindow();Check ($cold.WaitForExit(15000) -and $cold.ExitCode -eq 0) 'Explicit close exits the isolated owner without leaked dispatch server'
}finally{
    foreach($process in @($hot,$sync,$cold)){if($process){if(-not $process.HasExited){[void]$process.CloseMainWindow();if(-not $process.WaitForExit(2000)){$process.Kill();$process.WaitForExit()}};$process.Dispose()}}
}
Write-Output ('PASS: '+$script:Checks+' launch dispatch assertions; real cold/hot UI and same-user IPC, bounded queue, stale request rejection, isolated launch recorder only.')
