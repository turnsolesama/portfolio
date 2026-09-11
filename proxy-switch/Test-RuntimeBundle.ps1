[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$PackageDirectory)
$ErrorActionPreference='Stop'
$app=Join-Path ([IO.Path]::GetFullPath($PackageDirectory)) 'app'
$qa=Join-Path $env:TEMP ('FlowSwitch-Runtime-'+[Guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($qa)
$oldPath=$env:PATH;$oldNodeOptions=$env:NODE_OPTIONS;$oldHealth=$env:PROXY_SWITCH_TEST_HEALTH_URL
$fixture=$null;$checks=0
function Check($Value,$Message){if(-not $Value){throw $Message};$script:checks++}
try{
    $js=Join-Path $qa 'fixture.cjs';$portFile=Join-Path $qa 'port.txt'
    [IO.File]::WriteAllText($js,'const fs=require("fs"),http=require("http");const s=http.createServer((q,r)=>{r.writeHead(200);r.end("fixture");});s.on("connect",(q,c)=>{c.write("HTTP/1.1 200 Connection Established\r\n\r\n");c.once("data",()=>c.end("HTTP/1.1 200 OK\r\nContent-Length: 7\r\nConnection: close\r\n\r\nfixture"));});s.listen(0,"127.0.0.1",()=>fs.writeFileSync(process.argv[2],String(s.address().port)));')
    $fixture=Start-Process -FilePath (Join-Path $app 'runtime\node.exe') -ArgumentList ('"'+$js+'" "'+$portFile+'"') -WindowStyle Hidden -PassThru
    $deadline=[DateTime]::UtcNow.AddSeconds(10);while(-not (Test-Path -LiteralPath $portFile) -and [DateTime]::UtcNow -lt $deadline){Start-Sleep -Milliseconds 100}
    $port=[int][IO.File]::ReadAllText($portFile)
    $env:PATH='';$env:NODE_OPTIONS='--require deliberately-missing-fixture-module'
    $env:PROXY_SWITCH_TEST_HEALTH_URL='http://127.0.0.1:'+$port+'/health'
    . (Join-Path $app 'ProxyBackend.ps1') -DataDirectory $qa
    $script:Profiles=ConvertTo-ValidProfileSettings ([pscustomobject]@{Version=3;Profiles=@([pscustomobject]@{Id='upstream';Name='Fixture';Protocol='http';Host='127.0.0.1';Port=$port;CorePath='';AppPath='';AutoPort=$false});Routing=[pscustomobject]@{Adapter='none';ProfileId=''}})
    Write-LocalJson $script:ConfigPath $script:Profiles
    Write-LocalJson (Join-Path $qa 'app-rules.json') ([pscustomobject]@{version=2;entries=@();defaultRoute=$null;installed=$false})
    $script:FakeSystem=[pscustomobject]@{Flags=1;Server='';Bypass='localhost'}
    $script:FakeEnv=[pscustomobject]@{HTTP_PROXY=$null;HTTPS_PROXY=$null;ALL_PROXY=$null;NO_PROXY='localhost'}
    $originalSystem=$script:FakeSystem;$originalEnv=$script:FakeEnv
    function Get-SystemSnapshot {$script:FakeSystem}
    function Get-UserProxyEnv {$script:FakeEnv}
    function Set-SystemSnapshot($Value){$script:FakeSystem=$Value}
    function Set-UserProxyEnv($Value){$script:FakeEnv=$Value}
    function Get-ClientInterference {[pscustomobject]@{Running=$false;Tun=$false;Guard=$false;SystemProxy=$false}}
    function Get-ProcessInventory {throw 'Must not search installed proxy clients when the bundled core exists'}
    function Get-ItemPropertyValue {param($LiteralPath,$Name,$ErrorAction);throw 'Isolated registration absent'}
    function Remove-ItemProperty {throw 'Must not change real recovery registration'}
    function Start-IndependentProtection([int]$OwnerPID,$BeforeSystem,$BeforeEnv,$TargetSystem,$TargetEnv){
        $owned=Get-Content -LiteralPath (Join-Path $script:DataRoot 'gateway\process.json') -Raw | ConvertFrom-Json
        $session=[pscustomobject]@{OwnerPID=$OwnerPID;OwnerStart=(Get-ProcessStartTicks $OwnerPID);CorePID=$owned.core;CoreStart=(Get-ProcessStartTicks $owned.core);SupervisorPID=$owned.supervisor;SupervisorStart=(Get-ProcessStartTicks $owned.supervisor);BeforeSystem=$BeforeSystem;BeforeEnv=$BeforeEnv;TargetSystem=$TargetSystem;TargetEnv=$TargetEnv;Started=(Get-Date).ToString('o')}
        Write-LocalJson (Get-IndependentSessionPath) $session
    }
    Check (-not (Get-Command node.exe -ErrorAction SilentlyContinue)) 'External Node is still visible'
    Check ((Get-NodeRuntimePath) -eq (Join-Path $app 'runtime\node.exe')) 'Bundled Node not selected'
    $selectedCore=Get-IndependentCoreSource $script:Profiles
    Check ($selectedCore -in @((Join-Path $app 'runtime\FlowSwitch.Core.exe'),(Join-Path $app 'runtime\FlowSwitch.Core.Compat.exe'))) 'Bundled core not selected'
    Check (Test-CoreRuntimeCompatible (Join-Path $app 'runtime\FlowSwitch.Core.Compat.exe')) 'Compatibility core cannot start'
    $realProbe=${function:Test-CoreRuntimeCompatible}
    function Test-CoreRuntimeCompatible([string]$Path){return $Path.EndsWith('FlowSwitch.Core.Compat.exe')}
    try{Check ((Get-IndependentCoreSource $script:Profiles) -eq (Join-Path $app 'runtime\FlowSwitch.Core.Compat.exe')) 'Unsupported CPU did not select the compatibility build'}finally{${function:Test-CoreRuntimeCompatible}=$realProbe}
    Enable-IndependentGateway $PID | Out-Null
    Invoke-AppRouter @{action='replace';entries=@();defaultRoute='upstream'} | Out-Null
    $live=Invoke-AppRouter @{action='status'}
    Check ($live.available -and $live.defaultLoaded -and $live.defaultRoute -eq 'upstream') 'Fresh independent migration failed without installed dependencies'
    Check ($script:FakeSystem.Server -match '^127.0.0.1:' -and $script:FakeEnv.HTTP_PROXY -match '^http://127.0.0.1:') 'Fixed entrance not applied to isolated Windows settings'
    Check ((Get-FileHash -LiteralPath (Join-Path $qa 'gateway\runtime\FlowSwitch.Core.exe')).Hash -eq (Get-FileHash -LiteralPath $selectedCore).Hash) 'Bundled core was altered during staging'
    $deadline=[DateTime]::UtcNow.AddSeconds(12)
    do{$live=Invoke-AppRouter @{action='status'};if($live.failover.health.upstream){break};Start-Sleep -Milliseconds 200}while([DateTime]::UtcNow -lt $deadline)
    Check ([bool]$live.failover.health.upstream) 'Health check depended on PATH curl'
    $gateway=Get-Profile (Get-GatewayKey);$tcp=New-Object Net.Sockets.TcpClient
    try{$tcp.Connect('127.0.0.1',$gateway.Port);$stream=$tcp.GetStream();$stream.ReadTimeout=5000;$request=[Text.Encoding]::ASCII.GetBytes("GET http://127.0.0.1:$port/check HTTP/1.1`r`nHost: 127.0.0.1:$port`r`nConnection: close`r`n`r`n");$stream.Write($request,0,$request.Length);$reader=New-Object IO.StreamReader($stream);$reply=$reader.ReadToEnd();Check ($reply -match '200 OK' -and $reply -match 'fixture') ('Bundled gateway did not forward real HTTP: '+$reply)}finally{$tcp.Dispose()}
    $script:Profiles.Routing.Failover.AllowDirect=$true;Write-LocalJson $script:ConfigPath $script:Profiles
    Invoke-AppRouter @{action='sync'} | Out-Null
    $fixture.Kill();$fixture.WaitForExit()
    $deadline=[DateTime]::UtcNow.AddSeconds(15)
    do{$live=Invoke-AppRouter @{action='status'};if($live.effectiveDefaultRoute -eq 'Direct'){break};Start-Sleep -Milliseconds 200}while([DateTime]::UtcNow -lt $deadline)
    Check ($live.effectiveDefaultRoute -eq 'Direct') 'Exited fixture did not reach the explicitly allowed fallback'
    Restore-IndependentSession
    Check ((Test-SameSnapshot $script:FakeSystem $originalSystem) -and (Test-SameEnv $script:FakeEnv $originalEnv)) 'Exit restoration changed with the bundled runtime'
    Check (-not (Test-Path -LiteralPath (Get-IndependentSessionPath))) 'Session was not cleaned up'
    $script:RuntimeAppRoot=Join-Path $qa 'empty-app';[void][IO.Directory]::CreateDirectory($script:RuntimeAppRoot)
    Check ((Get-NodeRuntimePath) -eq (Join-Path $qa 'gateway\runtime\node.exe')) 'Existing runtime copy cannot operate independently of the package'
    Enable-IndependentGateway $PID | Out-Null
    $restarted=Invoke-AppRouter @{action='status'}
    Check $restarted.available 'Restart could not reuse its staged runtime'
    Check ($restarted.effectiveDefaultRoute -eq 'Direct') 'Full window enable reset a verified fallback to the exited preferred route'
    Restore-IndependentSession
    $script:DataRoot=Join-Path $qa 'empty-data';$script:Profiles.Routing.Adapter='none'
    $missing=$false;try{Get-NodeRuntimePath|Out-Null}catch{$missing=$_.Exception.Message -match '运行组件不完整'}
    Check $missing 'Missing source dependencies did not give an actionable error'
    Write-Output ('PASS: '+$checks+' bundled runtime checks; empty PATH, no installed clients, real core/HTTP, inherited Node options isolated, restart and exit restoration. Windows writes were stubbed.')
}finally{
    if(Test-Path -LiteralPath (Join-Path $qa 'gateway-session.json')){try{$script:DataRoot=$qa;Restore-IndependentSession}catch{}}
    if($fixture){if(-not $fixture.HasExited){$fixture.Kill()};$fixture.Dispose()}
    $env:PATH=$oldPath;$env:NODE_OPTIONS=$oldNodeOptions;$env:PROXY_SWITCH_TEST_HEALTH_URL=$oldHealth
}
