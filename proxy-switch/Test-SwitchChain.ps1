[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$RuntimeDirectory)
$ErrorActionPreference='Stop'
$qa=Join-Path $env:TEMP ('FlowSwitch-switch-chain-'+[Guid]::NewGuid().ToString('N'))
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
const s=http.createServer((q,r)=>{r.writeHead(200);r.end(marker)});
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
    Check (-not [IO.File]::Exists((Get-IndependentSessionPath))) 'Cold start has no existing proxy session'
    $script:RejectProbe=$true;$failure='';try{Set-SelectedProxy 'a'|Out-Null}catch{$failure=$_.Exception.Message};$script:RejectProbe=$false
    Check ($failure -match '检测未通过' -and -not [IO.File]::Exists((Get-IndependentSessionPath))) 'Failed cold-start preflight cannot start a session or claim success'
    Check ((Test-SameSnapshot $script:FakeSystem $originalSystem) -and (Test-SameEnv $script:FakeEnv $originalEnv)) 'Failed cold-start preflight preserves original settings'
    $coldResult=Set-SelectedProxy 'a'
    $coldBackup=Get-Content -LiteralPath $coldResult.Backup -Raw|ConvertFrom-Json
    Check ($null -ne $coldBackup.Routing -and $coldBackup.System.Flags -eq 1) 'Cold unified switch has a complete undo snapshot including original rules'
    Check ((Read-TestBody $port) -match 'A') 'Actual unified switch starts stopped configured gateway and routes A'
    $originalCore=(Get-Content -LiteralPath (Join-Path $script:DataRoot 'gateway\process.json') -Raw|ConvertFrom-Json).core
    foreach($choice in @('b','a','Direct','b')){
        Set-SelectedProxy $choice|Out-Null
        $expected=$(if($choice -eq 'Direct'){'D'}else{$choice.ToUpperInvariant()})
        $live=Invoke-AppRouter @{action='status'}
        Check ((Read-TestBody $port) -match $expected -and $live.effectiveDefaultRoute -eq $choice) ('Real request and controller agree after switch to '+$choice)
        Check ($script:FakeSystem.Server -eq ('127.0.0.1:'+$port) -and $script:FakeEnv.HTTPS_PROXY -eq ('http://127.0.0.1:'+$port)) 'Fixed gateway address stays stable across route changes'
    }
    Set-SelectedProxy 'a'|Out-Null
    $forceFile=Join-Path $qa 'force-backup.cjs'
    [IO.File]::WriteAllText($forceFile,'const r=require(process.argv[2]);r.api("PUT","/proxies/PSW-App-route-a",{name:"FS-Up-b"}).catch(()=>process.exitCode=1);')
    $env:PROXY_SWITCH_DATA_DIR=$script:DataRoot
    & $node $forceFile (Join-Path $PSScriptRoot 'IndependentRouter.cjs');if($LASTEXITCODE -ne 0){throw 'Could not set isolated backup'}
    Check ((Read-TestBody $port) -match 'B') 'Fixture has actual backup B while preferred remains A'
    Set-SelectedProxy 'a'|Out-Null
    Check ((Read-TestBody $port) -match 'A') 'Explicit reselection of A returns from healthy backup B to A'
    $realRouter=${function:Invoke-AppRouter}
    function Invoke-AppRouter($Request,[int]$TimeoutMilliseconds=55000){
        if($script:WrongSelector -and $Request.action -eq 'status'){return [pscustomobject]@{available=$true;defaultLoaded=$true;defaultRoute='b';effectiveDefaultRoute='a'}}
        & $realRouter $Request $TimeoutMilliseconds
    }
    $script:WrongSelector=$true;$failure='';try{Set-SelectedProxy 'b'|Out-Null}catch{$failure=$_.Exception.Message};$script:WrongSelector=$false
    Check ($failure -match '实际出口没有到达所选线路') 'Healthy HTTP plus mismatched actual selector cannot report switch success'
    Check ((Read-TestBody $port) -match 'A' -and (Get-RoutingSnapshot).defaultRoute -eq 'a') 'Failed actual-route verification restores the previous real route'
    Check ((Get-Content -LiteralPath (Join-Path $script:DataRoot 'gateway\process.json') -Raw|ConvertFrom-Json).core -eq $originalCore) 'Route changes do not restart the proxy core'
    $apps=Get-ApplicationRoutes;$status=Get-ProxyStatus $apps
    Check ($status.NetworkKey -eq 'a' -and $status.EndpointReady) ('Displayed current route matches real A request: '+(@{Key=$status.Key;NetworkKey=$status.NetworkKey;Ready=$status.EndpointReady;Tcp=$status.TcpAvailable;Available=$apps.Available;Default=$apps.DefaultRoute;Loaded=$apps.DefaultLoaded;Effective=$apps.EffectiveDefaultRoute}|ConvertTo-Json -Compress))
    Restore-IndependentSession
    Check ((Test-SameSnapshot $script:FakeSystem $originalSystem) -and (Test-SameEnv $script:FakeEnv $originalEnv)) 'Explicit stop restores the isolated settings'
    Set-SelectedProxy 'b'|Out-Null
    Check ((Read-TestBody $port) -match 'B') 'After a full stop, unified switch restarts the same gateway on chosen B'
    Restore-IndependentSession
    Write-Output ('PASS: '+$checks+' real switch-chain checks; actual backend, core and HTTP requests, Windows writes stubbed.')
}finally{
    if($script:DataRoot -and [IO.File]::Exists((Join-Path $script:DataRoot 'gateway-session.json'))){try{Restore-IndependentSession}catch{}}
    $stop=Join-Path $qa 'data\gateway\stop';if([IO.Directory]::Exists([IO.Path]::GetDirectoryName($stop))){[IO.File]::WriteAllText($stop,'stop')}
    if($fixture){if(-not $fixture.HasExited){$fixture.Kill();[void]$fixture.WaitForExit(3000)};$fixture.Dispose()}
}
