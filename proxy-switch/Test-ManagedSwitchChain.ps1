[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$RuntimeDirectory)
$ErrorActionPreference='Stop'
$qa=Join-Path $env:TEMP ('FlowSwitch-managed-chain-'+[Guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($qa)
$fixture=$null;$checks=0
function Check($Value,$Message){if(-not $Value){throw $Message};$script:checks++;Write-Output ('PASS: '+$Message)}
try{
    $node=Join-Path $RuntimeDirectory 'node.exe';$sourceCore=Join-Path $RuntimeDirectory 'FlowSwitch.Core.exe'
    $testCore=Join-Path $qa 'FlowSwitch-TestEngine.exe';Copy-Item -LiteralPath $sourceCore -Destination $testCore
    $fixtureScript=Join-Path $qa 'servers.cjs';$portsFile=Join-Path $qa 'ports.json'
    [IO.File]::WriteAllText($fixtureScript,@'
const http=require('http'),fs=require('fs');
Promise.all(['A','B','D'].map(marker=>new Promise(resolve=>{
const s=http.createServer((q,r)=>{r.writeHead(200,{'Content-Length':1});r.end(marker)});
s.on('connect',(q,c)=>{c.write('HTTP/1.1 200 Connection Established\r\n\r\n');c.once('data',()=>c.end('HTTP/1.1 200 OK\r\nContent-Length: 1\r\nConnection: close\r\n\r\n'+marker));});
s.listen(0,'127.0.0.1',()=>resolve(s.address().port));
}))).then(ports=>fs.writeFileSync(process.argv[2],JSON.stringify(ports)));
'@)
    $fixture=Start-Process -FilePath $node -ArgumentList ('"'+$fixtureScript+'" "'+$portsFile+'"') -WindowStyle Hidden -PassThru
    $deadline=[DateTime]::UtcNow.AddSeconds(10);while(-not [IO.File]::Exists($portsFile) -and [DateTime]::UtcNow -lt $deadline){Start-Sleep -Milliseconds 100}
    $ports=[IO.File]::ReadAllText($portsFile)|ConvertFrom-Json
    $reserve=New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback,0);$reserve.Start();$port=$reserve.LocalEndpoint.Port;$reserve.Stop()
    $env:PROXY_SWITCH_TEST_HEALTH_URL='http://127.0.0.1:'+$ports[2]+'/health'
    . (Join-Path $PSScriptRoot 'ProxyBackend.ps1') -DataDirectory (Join-Path $qa 'data')
    $script:Profiles=ConvertTo-ValidProfileSettings ([pscustomobject]@{Version=3;Profiles=@(
        @{Id='gateway';Name='Isolated gateway';Protocol='http';Host='127.0.0.1';Port=$port;CorePath=$testCore},
        @{Id='a';Name='A';Protocol='http';Host='127.0.0.1';Port=$ports[0];CorePath=''},
        @{Id='b';Name='B';Protocol='http';Host='127.0.0.1';Port=$ports[1];CorePath=''}
    );Routing=@{Adapter='standalone';ProfileId='gateway';UnifiedMode='gateway';Failover=@{Enabled=$true;Order=@('a','b');AllowDirect=$false}}})
    Write-LocalJson $script:ConfigPath $script:Profiles
    $script:FakeSystem=[pscustomobject]@{Flags=1;Server='';Bypass='localhost'}
    $script:FakeEnv=[pscustomobject]@{HTTP_PROXY=$null;HTTPS_PROXY=$null;ALL_PROXY=$null;NO_PROXY='localhost'}
    $originalSystem=$script:FakeSystem;$originalEnv=$script:FakeEnv
    function Get-SystemSnapshot {$script:FakeSystem}
    function Get-UserProxyEnv {$script:FakeEnv}
    function Set-SystemSnapshot($Value){$script:FakeSystem=$Value}
    function Set-UserProxyEnv($Value){$script:FakeEnv=$Value}
    function Use-ChangeLock([scriptblock]$Action){& $Action}
    function Get-NodeRuntimePath {$node}
    function Get-IndependentCoreSource {$testCore}
    function Get-ClientInterference {[pscustomobject]@{Running=$false;Tun=$false;Guard=$false;SystemProxy=$false}}
    function Get-ItemPropertyValue {param($LiteralPath,$Name,$ErrorAction);throw 'Isolated registration absent'}
    function Remove-ItemProperty {throw 'Must not alter real RunOnce'}
    function Start-IndependentProtection([int]$OwnerPID,$BeforeSystem,$BeforeEnv,$TargetSystem,$TargetEnv){
        $owned=Get-Content -LiteralPath (Join-Path $script:DataRoot 'gateway\process.json') -Raw|ConvertFrom-Json
        Write-LocalJson (Get-IndependentSessionPath) @{OwnerPID=$OwnerPID;OwnerStart=(Get-ProcessStartTicks $OwnerPID);CorePID=$owned.core;CoreStart=(Get-ProcessStartTicks $owned.core);SupervisorPID=$owned.supervisor;SupervisorStart=(Get-ProcessStartTicks $owned.supervisor);BeforeSystem=$BeforeSystem;BeforeEnv=$BeforeEnv;TargetSystem=$TargetSystem;TargetEnv=$TargetEnv;Started=(Get-Date).ToString('o')}
    }
    function Read-TestBody([int]$ProxyPort){
        $tcp=New-Object Net.Sockets.TcpClient
        try{$tcp.Connect('127.0.0.1',$ProxyPort);$stream=$tcp.GetStream();$stream.ReadTimeout=3000
            $bytes=[Text.Encoding]::ASCII.GetBytes("GET http://127.0.0.1:$($ports[2])/probe HTTP/1.1`r`nHost: 127.0.0.1:$($ports[2])`r`nConnection: close`r`n`r`n")
            $stream.Write($bytes,0,$bytes.Length);$reader=New-Object IO.StreamReader($stream);$reply=$reader.ReadToEnd()
            if($reply -notmatch 'HTTP/1.[01] 200'){throw 'Isolated HTTP probe failed'}
            return $reply.Substring($reply.IndexOf("`r`n`r`n")+4).Trim()
        }finally{$tcp.Dispose()}
    }
    # Replace public health targets only; probes still traverse real sockets and actual core.
    function Test-ProxyRoute([string]$Key,[switch]$Fast){
        if($script:RejectProbe){return [pscustomobject]@{Key=$Key;Usable=$false;Results=@()}}
        $p=Get-Profile $Key;$body=Read-TestBody $p.Port
        [pscustomobject]@{Key=$Key;Usable=($body -match '[ABD]');Results=@()}
    }

    $desktop=Join-Path $qa 'desktop';[void][IO.Directory]::CreateDirectory($desktop)
    $realShortcut=${function:Install-ProgramProxyShortcut}
    function Install-ProgramProxyShortcut($Executable){& $realShortcut $Executable $desktop}
    $appDir=Join-Path $qa 'browser';[void][IO.Directory]::CreateDirectory($appDir)
    $exe=Join-Path $appDir 'BrowserFixture.exe';$workerExe=Join-Path $appDir 'NetworkingFixture.exe'
    $code=@'
using System;using System.IO;using System.Net.Sockets;using System.Diagnostics;using System.Threading;
public static class BrowserFixture {
 public static void Main(string[] args) {
  bool child=args.Length>0&&args[0]=="--child";
  string root=Environment.GetEnvironmentVariable("FS_FIXTURE_DIR");
  if(!child) {var psi=new ProcessStartInfo(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"NetworkingFixture.exe"),"--child");psi.UseShellExecute=false;psi.CreateNoWindow=true;using(var p=Process.Start(psi))File.WriteAllText(Path.Combine(root,"worker.pid"),p.Id.ToString());}
  string role=child?"worker":"root";
  File.WriteAllText(Path.Combine(root,role+".endpoint"),Environment.GetEnvironmentVariable("HTTPS_PROXY")??"");
  while(!File.Exists(Path.Combine(root,"stop-clients"))) {
   try {var uri=new Uri(Environment.GetEnvironmentVariable("HTTPS_PROXY"));string target=File.ReadAllText(Path.Combine(root,"request.url"));using(var c=new TcpClient()) {c.Connect(uri.Host,uri.Port);c.ReceiveTimeout=1500;var stream=c.GetStream();var bytes=System.Text.Encoding.ASCII.GetBytes("GET "+target+" HTTP/1.1\r\nHost: "+new Uri(target).Authority+"\r\nConnection: close\r\n\r\n");stream.Write(bytes,0,bytes.Length);string response=new StreamReader(stream).ReadToEnd();File.WriteAllText(Path.Combine(root,role+".result"),response);}}
   catch {File.WriteAllText(Path.Combine(root,role+".result"),"FAILED");}
   Thread.Sleep(150);
  }
 }
}
'@
    Add-Type -TypeDefinition $code -OutputAssembly $exe -OutputType WindowsApplication
    Copy-Item -LiteralPath $exe -Destination $workerExe
    foreach($name in @('resources.pak','chrome_100_percent.pak')){[IO.File]::WriteAllText((Join-Path $appDir $name),'fixture')}
    $env:FS_FIXTURE_DIR=$qa
    [IO.File]::WriteAllText((Join-Path $qa 'request.url'),('http://network.invalid:'+$ports[2]+'/test'))
    function Wait-ClientResult([string]$Marker){
        $deadline=[DateTime]::UtcNow.AddSeconds(8)
        do{
            $ok=$true;foreach($role in @('root','worker')){try{$body=[IO.File]::ReadAllText((Join-Path $qa ($role+'.result')));if(-not $body.EndsWith($Marker)){$ok=$false}}catch{$ok=$false}}
            if($ok){return $true};Start-Sleep -Milliseconds 100
        }while([DateTime]::UtcNow -lt $deadline)
        return $false
    }
    Set-UniversalProxy 'a'|Out-Null
    $configured=Set-ManagedApplicationRoute $exe 'a'
    $ingress=Get-ManagedProgramIngress $exe
    Check ($configured.Managed -and $ingress.port -ne $port) 'Standard program action creates separately verified stable entrance'
    $start=Start-ManagedProgram $exe
    Check (Wait-ClientResult 'A') 'Actual launcher and its networking child both reach A through stable program entrance'
    $parent=[Diagnostics.Process]::GetProcessById($start.PID);$childPID=[int][IO.File]::ReadAllText((Join-Path $qa 'worker.pid'));$child=[Diagnostics.Process]::GetProcessById($childPID)
    Check ([IO.File]::ReadAllText((Join-Path $qa 'root.endpoint')) -ceq [IO.File]::ReadAllText((Join-Path $qa 'worker.endpoint'))) 'Real child inherits exactly the root stable proxy endpoint'
    Set-ManagedApplicationRoute $exe 'b'|Out-Null
    Check (Wait-ClientResult 'B') 'Existing root and child requests move from A to B using unchanged processes'
    Check (-not $parent.HasExited -and -not $child.HasExited -and (Get-ManagedProgramIngress $exe).port -eq $ingress.port) 'Manual switch preserves application processes and entrance port'
    $read=Get-WebsiteRules
    Set-WebsiteRules @(@{Id='';Domain='localhost';Match='exact';Route='Direct';Executable=$exe}) $read.Revision|Out-Null
    [IO.File]::WriteAllText((Join-Path $qa 'request.url'),('http://localhost:'+$ports[2]+'/test'))
    Check (Wait-ClientResult 'D') 'Actual PS website editor backend sends direct-only site direct for root and child'
    [IO.File]::WriteAllText((Join-Path $qa 'request.url'),('http://network.invalid:'+$ports[2]+'/test'))
    Check (Wait-ClientResult 'B') 'Same program still uses proxy B for other websites'
    Set-UniversalProxy 'a'|Out-Null
    Check ((Get-ManagedProgramIngress $exe).route -eq 'Follow' -and (Get-WebsiteRules).Entries.Count -eq 1) 'Unified switch retains program entrance and website exception'
    Check (Wait-ClientResult 'A') 'Existing root and child follow new unified A without restart'
    $read=Get-WebsiteRules;Set-WebsiteRules @() $read.Revision|Out-Null
    Set-ManagedApplicationRoute $exe 'Direct'|Out-Null
    [IO.File]::WriteAllText((Join-Path $qa 'request.url'),('http://localhost:'+$ports[2]+'/test'))
    Check (Wait-ClientResult 'D') 'Explicit program Direct works through same stable entrance'
    Set-ManagedApplicationRoute $exe 'b'|Out-Null
    Check (Wait-ClientResult 'B') 'Direct to B on same processes is a real transport switch'
    [IO.File]::WriteAllText((Join-Path $qa 'stop-clients'),'stop');[void]$parent.WaitForExit(4000);[void]$child.WaitForExit(4000)
    Check ($parent.HasExited -and $child.HasExited) 'Test clients finish through their own stop fixture'
    $parent.Dispose();$child.Dispose()
    Restore-IndependentSession
    Check ((Test-SameSnapshot $script:FakeSystem $originalSystem) -and (Test-SameEnv $script:FakeEnv $originalEnv)) 'Explicit stop restores isolated original Windows state'
    $defaultBefore=(Get-RoutingSnapshot).defaultRoute
    Set-ManagedApplicationRoute $exe 'b'|Out-Null
    Check ((Get-RoutingSnapshot).defaultRoute -eq $defaultBefore -and (Get-ManagedProgramIngress $exe).route -eq 'b') 'Cold program B selection preserves the separately saved unified default'
    Restore-IndependentSession
    Start-ManagedProgram $exe|Out-Null
    $reopened=Invoke-AppRouter @{action='status'}
    Check ($reopened.programIngresses[0].ready -and $reopened.programIngresses[0].effectiveRoute -eq 'b' -and (Get-ManagedProgramIngress $exe).port -eq $ingress.port) 'Managed launch after full service stop restores saved program B before opening app'
    Restore-IndependentSession
    Write-Output ('PASS: '+$checks+' real managed switching checks; real launcher, parent, child, core and HTTP; only Windows and RunOnce writes stubbed.')
}finally{
    if($qa){[IO.File]::WriteAllText((Join-Path $qa 'stop-clients'),'stop')}
    if($script:DataRoot -and [IO.File]::Exists((Join-Path $script:DataRoot 'gateway-session.json'))){try{Restore-IndependentSession}catch{}}
    $stop=Join-Path $qa 'data\gateway\stop';if([IO.Directory]::Exists([IO.Path]::GetDirectoryName($stop))){[IO.File]::WriteAllText($stop,'stop')}
    if($fixture){if(-not $fixture.HasExited){$fixture.Kill();[void]$fixture.WaitForExit(3000)};$fixture.Dispose()}
}
