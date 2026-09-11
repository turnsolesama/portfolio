$ErrorActionPreference='Stop'
$qa=Join-Path $env:TEMP ('FlowSwitch-launch-evidence-'+[Guid]::NewGuid().ToString('N'))
. (Join-Path $PSScriptRoot 'ProxyBackend.ps1') -DataDirectory (Join-Path $qa 'data')
$script:Checks=0;$script:InventoryCalls=0;$script:FailRecord=$false;$script:Ready=$true;$script:EffectiveRoute='Direct';$script:SiteRules=@();$script:SiteRulesLoaded=$true
function Check($Value,[string]$Message){if(-not $Value){throw $Message};$script:Checks++}
function Use-ChangeLock([scriptblock]$Action){& $Action}
function Set-SystemSnapshot {throw 'Real Windows writes forbidden'}
function Set-UserProxyEnv {throw 'Real environment writes forbidden'}
function Invoke-AppRouter {throw 'No real engine is needed for launch evidence'}
function Get-ProcessInventory {$script:InventoryCalls++;if($script:InventoryCalls -gt 1){throw 'Global process inventory is unavailable after launch'};@()}
function Get-ManagedProgramIngress([string]$Executable){if($Executable -in $script:FixtureRoots){[pscustomobject]@{id=('a'*32);path=$Executable;port=19998;route='Direct'}}}
function Ensure-ManagedGateway {[pscustomobject]@{available=$true;programIngresses=@([pscustomobject]@{id=('a'*32);ready=$script:Ready;loaded=$script:Ready;effectiveRoute=$script:EffectiveRoute});siteRules=@($script:SiteRules);siteRulesLoaded=$script:SiteRulesLoaded}}
$baseWriter=${function:Write-LocalJson}
function Write-LocalJson($Path,$Value){if($script:FailRecord -and [IO.Path]::GetFileName($Path) -eq 'program-launches.json'){throw 'Fixture launch evidence disk write failure'};& $baseWriter $Path $Value}
$script:Profiles=ConvertTo-ValidProfileSettings ([pscustomobject]@{Version=3;Profiles=@();Routing=@{Adapter='none';ProfileId=''}})
$directories=@('quick','record-failure','not-ready','limited-program','limited-global','other-program-only','unknown-with-direct','unloaded-sites','unloaded-direct-row'|ForEach-Object {Join-Path $qa $_})
foreach($directory in $directories){[void][IO.Directory]::CreateDirectory($directory);foreach($name in @('resources.pak','chrome_100_percent.pak')){[IO.File]::WriteAllText((Join-Path $directory $name),'inert adapter fixture')}}
$code=@'
using System;using System.IO;using System.Diagnostics;using System.Threading;
public static class LaunchEvidenceFixture {
 public static void Main(string[] args){
  string directory=AppDomain.CurrentDomain.BaseDirectory;
  if(args.Length>0 && args[0]=="--worker"){
   File.WriteAllText(Path.Combine(directory,"worker.started"),Process.GetCurrentProcess().Id.ToString());
   var until=DateTime.UtcNow.AddSeconds(20);while(!File.Exists(Path.Combine(directory,"stop"))&&DateTime.UtcNow<until)Thread.Sleep(50);return;
  }
  File.AppendAllText(Path.Combine(directory,"root-starts.txt"),Process.GetCurrentProcess().Id+Environment.NewLine);
  var info=new ProcessStartInfo(Path.Combine(directory,"worker.exe"),"--worker");info.UseShellExecute=false;info.CreateNoWindow=true;
  using(var child=Process.Start(info))File.WriteAllText(Path.Combine(directory,"worker.pid"),child.Id.ToString());
  // The bootstrap exits immediately while the application service stays alive.
 }
}
'@
$firstExe=Join-Path $directories[0] 'fixture.exe';Add-Type -TypeDefinition $code -OutputAssembly $firstExe -OutputType WindowsApplication
foreach($directory in $directories){$target=Join-Path $directory 'fixture.exe';if($target -ne $firstExe){Copy-Item -LiteralPath $firstExe -Destination $target};Copy-Item -LiteralPath $firstExe -Destination (Join-Path $directory 'worker.exe')}
$script:FixtureRoots=@($directories|ForEach-Object {Join-Path $_ 'fixture.exe'})
function Wait-FixtureWorker([string]$Directory){$deadline=[DateTime]::UtcNow.AddSeconds(8);do{if(Test-Path -LiteralPath (Join-Path $Directory 'worker.started')){return};Start-Sleep -Milliseconds 50}while([DateTime]::UtcNow -lt $deadline);throw 'Own fixture worker did not start'}
try{
    $result=Start-ManagedProgram $script:FixtureRoots[0];Wait-FixtureWorker $directories[0]
    Check ($result.PID -gt 0 -and -not $result.ObservationUnknown) 'Quick bootstrap with live worker returns successful launch evidence from the owned process handle'
    Check ($script:InventoryCalls -eq 1) 'Global inventory is read only before start and is not required after a fast bootstrap exits'
    $bootstrap=$null;$bootstrapExited=$false
    try{$bootstrap=[Diagnostics.Process]::GetProcessById($result.PID);$bootstrapExited=$bootstrap.WaitForExit(3000)}catch [ArgumentException]{$bootstrapExited=$true}finally{if($bootstrap){$bootstrap.Dispose()}}
    $worker=[Diagnostics.Process]::GetProcessById([int][IO.File]::ReadAllText((Join-Path $directories[0] 'worker.pid')))
    try{Check ($bootstrapExited -and -not $worker.HasExited) 'Fixture proves bootstrap has exited while its application worker remains alive'}finally{$worker.Dispose()}
    $record=(Get-Content -LiteralPath (Join-Path $script:DataRoot 'program-launches.json') -Raw|ConvertFrom-Json).entries[0]
    Check ($record.pid -eq $result.PID -and $record.started -match '^\d+$') 'Launch record retains bootstrap PID and creation ticks even after it exits'
    Check ([IO.File]::ReadAllLines((Join-Path $directories[0] 'root-starts.txt')).Count -eq 1) 'Successful fast bootstrap is not launched twice'
    $script:InventoryCalls=0;$script:FailRecord=$true
    $result=Start-ManagedProgram $script:FixtureRoots[1];Wait-FixtureWorker $directories[1]
    Check ($result.PID -gt 0 -and $result.ObservationUnknown -and $result.Message -match '程序已启动') 'Evidence write failure returns started with unknown observation instead of failed launch'
    Check ([IO.File]::ReadAllLines((Join-Path $directories[1] 'root-starts.txt')).Count -eq 1 -and $script:InventoryCalls -eq 1) 'Evidence failure never retries or starts a duplicate app'
    $script:InventoryCalls=0;$script:FailRecord=$false;$script:Ready=$false;$message=''
    try{Start-ManagedProgram $script:FixtureRoots[2]|Out-Null}catch{$message=$_.Exception.Message}
    Check ($message -match '尚未就绪' -and -not (Test-Path -LiteralPath (Join-Path $directories[2] 'root-starts.txt'))) 'Gateway readiness failure occurs before Process.Start and leaves target unopened'
    $script:Ready=$true;$script:EffectiveRoute='Blocked'
    foreach($scenario in @(@{Index=3;Scope=('a'*32)},@{Index=4;Scope='global'})){
        $script:InventoryCalls=0;$script:SiteRules=@([pscustomobject]@{scope=$scenario.Scope;route='Direct';loaded=$true})
        $result=Start-ManagedProgram $script:FixtureRoots[$scenario.Index];Wait-FixtureWorker $directories[$scenario.Index]
        Check ($result.PID -gt 0 -and $result.LimitedDirect -and $result.Message -match '默认代理出口已暂停' -and $result.Message -match '仅匹配直连网站例外' -and [IO.File]::ReadAllLines((Join-Path $directories[$scenario.Index] 'root-starts.txt')).Count -eq 1) ('Blocked default permits one real launch with applicable '+$scenario.Scope+' Direct rule and explicit limited-access notice')
    }
    $script:InventoryCalls=0;$script:SiteRules=@([pscustomobject]@{scope=('b'*32);route='Direct';loaded=$true});$message=''
    try{Start-ManagedProgram $script:FixtureRoots[5]|Out-Null}catch{$message=$_.Exception.Message}
    Check ($message -match '没有适用于此程序' -and -not (Test-Path -LiteralPath (Join-Path $directories[5] 'root-starts.txt'))) 'Blocked default cannot borrow another program entrance Direct exception to launch'
    $script:InventoryCalls=0;$script:EffectiveRoute='Unknown';$script:SiteRules=@([pscustomobject]@{scope='global';route='Direct';loaded=$true});$message=''
    try{Start-ManagedProgram $script:FixtureRoots[6]|Out-Null}catch{$message=$_.Exception.Message}
    Check ($message -match '尚未就绪' -and -not (Test-Path -LiteralPath (Join-Path $directories[6] 'root-starts.txt'))) 'Unknown route remains a launch refusal even with loaded global Direct exception'
    $script:InventoryCalls=0;$script:EffectiveRoute='Blocked';$script:SiteRulesLoaded=$false;$message=''
    try{Start-ManagedProgram $script:FixtureRoots[7]|Out-Null}catch{$message=$_.Exception.Message}
    Check ($message -match '没有适用于此程序' -and -not (Test-Path -LiteralPath (Join-Path $directories[7] 'root-starts.txt'))) 'An unloaded overall website policy cannot authorize limited Direct launch'
    $script:InventoryCalls=0;$script:SiteRulesLoaded=$true;$script:SiteRules=@([pscustomobject]@{scope='global';route='Direct';loaded=$false});$message=''
    try{Start-ManagedProgram $script:FixtureRoots[8]|Out-Null}catch{$message=$_.Exception.Message}
    Check ($message -match '没有适用于此程序' -and -not (Test-Path -LiteralPath (Join-Path $directories[8] 'root-starts.txt'))) 'An unloaded Direct rule row cannot authorize limited launch'
}finally{
    foreach($directory in $directories){[IO.File]::WriteAllText((Join-Path $directory 'stop'),'stop')}
    foreach($directory in $directories){
        $pidFile=Join-Path $directory 'worker.pid';if(Test-Path -LiteralPath $pidFile){
            $ownedPID=[int][IO.File]::ReadAllText($pidFile);$process=$null
            try{$process=[Diagnostics.Process]::GetProcessById($ownedPID);if(-not $process.WaitForExit(5000)){throw 'Own evidence fixture did not stop'}}catch [ArgumentException]{}finally{if($process){$process.Dispose()}}
        }
    }
}
Write-Output ('PASS: '+$script:Checks+' managed launch evidence checks; real quick bootstrap and worker, disk failure and not-ready gate, isolated application fixtures only.')
