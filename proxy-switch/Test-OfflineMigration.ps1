[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$RuntimeDirectory)
$ErrorActionPreference='Stop'
$qa=Join-Path $env:TEMP ('FlowSwitch-offline-migration-'+[Guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($qa)
$repository=$PSScriptRoot;$fixture=$null;$checks=0;$scenarioRoots=@()
$savedEnvironment=@{}
foreach($key in @('PROXY_SWITCH_DATA_DIR','PROXY_SWITCH_TEST_ENGINE_DIR','PROXY_SWITCH_TEST_PIPE','PROXY_SWITCH_TEST_HEALTH_URL','PROXY_SWITCH_PROFILES')){$savedEnvironment[$key]=[Environment]::GetEnvironmentVariable($key,'Process')}
function Check($Value,$Message){if(-not $Value){throw $Message};$script:checks++;Write-Output ('PASS: '+$Message)}
function New-TestPort {
    $listener=New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback,0)
    try{$listener.Start();return [int]$listener.LocalEndpoint.Port}finally{$listener.Stop()}
}
function Get-TestBytes([string]$Path){[Convert]::ToBase64String([IO.File]::ReadAllBytes($Path))}
try{
    $node=Join-Path $RuntimeDirectory 'node.exe';$sourceCore=Join-Path $RuntimeDirectory 'FlowSwitch.Core.exe'
    $testCore=Join-Path $qa 'FlowSwitch-TestEngine.exe';Copy-Item -LiteralPath $sourceCore -Destination $testCore
    $fixtureScript=Join-Path $qa 'servers.cjs';$portsFile=Join-Path $qa 'ports.json'
    [IO.File]::WriteAllText($fixtureScript,@'
const http=require('node:http'),fs=require('node:fs');
Promise.all(['A','B','D'].map(marker=>new Promise(resolve=>{
 const server=http.createServer((q,r)=>{r.writeHead(200,{'Content-Length':1});r.end(marker)});
 server.on('connect',(q,c)=>{c.write('HTTP/1.1 200 Connection Established\r\n\r\n');c.once('data',()=>c.end('HTTP/1.1 200 OK\r\nContent-Length: 1\r\nConnection: close\r\n\r\n'+marker));});
 server.listen(0,'127.0.0.1',()=>resolve(server.address().port));
}))).then(ports=>fs.writeFileSync(process.argv[2],JSON.stringify(ports)));
'@)
    $fixture=Start-Process -FilePath $node -ArgumentList ('"'+$fixtureScript+'" "'+$portsFile+'"') -WindowStyle Hidden -PassThru
    $deadline=[DateTime]::UtcNow.AddSeconds(10)
    while(-not [IO.File]::Exists($portsFile) -and [DateTime]::UtcNow -lt $deadline){Start-Sleep -Milliseconds 100}
    $ports=[IO.File]::ReadAllText($portsFile)|ConvertFrom-Json
    $env:PROXY_SWITCH_TEST_HEALTH_URL='http://127.0.0.1:'+$ports[2]+'/health'
    $env:PROXY_SWITCH_PROFILES=$null
    . (Join-Path $repository 'ProxyBackend.ps1') -DataDirectory (Join-Path $qa 'bootstrap')
    # Import before defining the allocation-only stub: this module exports functions.
    Import-Module NetTCPIP -ErrorAction Stop

    # Build genuinely owned external objects with the shipping generator. No external core is run.
    $seedScript=Join-Path $qa 'external-fixture.cjs'
    [IO.File]::WriteAllText($seedScript,@'
const fs=require('node:fs'),path=require('node:path');
const [action,root,scenario,a,b,offline]=process.argv.slice(2);
const r=require(path.join(root,'AppRouter.cjs')),yaml=require(path.join(root,'vendor/js-yaml'));
const data=path.join(scenario,'data'),engine=path.join(scenario,'engine');
const files={runtime:path.join(engine,'clash-verge.yaml'),script:path.join(engine,'profiles','Script.js'),state:path.join(data,'app-rules.json'),settings:path.join(data,'config.json')};
if(action==='seed'){
 fs.mkdirSync(data,{recursive:true});fs.mkdirSync(path.join(engine,'profiles'),{recursive:true});
 const options={Version:3,Profiles:[
  {Id:'clash',Name:'Offline external fixture',Protocol:'http',Host:'127.0.0.1',Port:Number(offline),CorePath:path.join(scenario,'missing-fixture-core.exe'),AutoPort:false},
  {Id:'a',Name:'A',Protocol:'http',Host:'127.0.0.1',Port:Number(a)},
  {Id:'b',Name:'B',Protocol:'http',Host:'127.0.0.1',Port:Number(b)}
 ],Routing:{Adapter:'clash-verge',ProfileId:'clash',UnifiedMode:'gateway'}};
 const entries=[{path:path.join(scenario,'LegacyIDE.exe'),route:'a'}];
 const originalScript='function main(config) { config.userField = "preserved"; return config; }\r\n';
 const base={mode:'rule','mixed-port':Number(offline),secret:'SYNTHETIC_FIXTURE_SECRET',dns:{enable:true,nameserver:['1.1.1.1']},
  proxies:[{name:'SubscriptionNode',type:'http',server:'proxy.example.invalid',port:8080,username:'fixture-user',password:'SYNTHETIC_FIXTURE_PASSWORD'}],
  'proxy-groups':[{name:'Primary',type:'select',proxies:['SubscriptionNode']}],rules:['DOMAIN,example.com,DIRECT','MATCH,Primary'],'user-custom':{preserve:true}};
 const state={version:2,installed:true,entries,defaultRoute:'a',primary:'Primary',originalFind:{present:false},fingerprint:r.fingerprint(entries,'a',options)};
 const values={runtime:yaml.dump(r.makeConfig(base,entries,'a',options,'Primary',state.originalFind),{lineWidth:-1,noRefs:true}),script:r.makeScript(originalScript,entries,'a',options,'Primary',state.originalFind),state:JSON.stringify(state,null,2),settings:JSON.stringify(options,null,2)};
 for(const [key,value] of Object.entries(values))fs.writeFileSync(files[key],'\uFEFF'+value);
 fs.writeFileSync(path.join(scenario,'expected-external.json'),JSON.stringify({base,originalScript}));
 fs.writeFileSync(path.join(engine,'verge.yaml'),'enable_system_proxy: true\r\nenable_tun_mode: false\r\nenable_proxy_guard: false\r\n');
 fs.writeFileSync(path.join(data,'program-proxies.json'),'\uFEFF'+JSON.stringify({version:1,entries:[{path:entries[0].path,route:'a',adapter:'chromium'}]}));
}else if(action==='clean'){
 const expected=JSON.parse(fs.readFileSync(path.join(scenario,'expected-external.json'),'utf8'));
 const canonical=v=>v&&typeof v==='object'?Array.isArray(v)?v.map(canonical):Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])):v;
 const runtime=yaml.load(fs.readFileSync(files.runtime,'utf8'));
 process.stdout.write(JSON.stringify({runtime:JSON.stringify(canonical(runtime))===JSON.stringify(canonical(expected.base)),script:fs.readFileSync(files.script,'utf8').replace(/^\uFEFF/,'')===expected.originalScript}));
}else throw Error('Unknown fixture action');
'@)
    function Get-SystemSnapshot {$script:FakeSystem}
    function Get-UserProxyEnv {$script:FakeEnv}
    function Set-SystemSnapshot($Value){$script:WindowsWrites++;$script:FakeSystem=$Value}
    function Set-UserProxyEnv($Value){$script:WindowsWrites++;$script:FakeEnv=$Value}
    function Use-ChangeLock([scriptblock]$Action){& $Action}
    function Get-NodeRuntimePath {$node}
    function Get-IndependentCoreSource {$testCore}
    function Get-ClientInterference {$script:ClientReads++;[pscustomobject]@{Running=$true;Tun=$false;Guard=$false;SystemProxy=$true}}
    function Get-ItemPropertyValue {param($LiteralPath,$Name,$ErrorAction);throw 'Isolated registration absent'}
    function Set-ItemProperty {throw 'Must not alter real RunOnce or third-party settings'}
    function Remove-ItemProperty {throw 'Must not alter real RunOnce or third-party settings'}
    function Start-IndependentProtection([int]$OwnerPID,$BeforeSystem,$BeforeEnv,$TargetSystem,$TargetEnv){
        $owned=Get-Content -LiteralPath (Join-Path $script:DataRoot 'gateway\process.json') -Raw|ConvertFrom-Json
        Write-LocalJson (Get-IndependentSessionPath) @{OwnerPID=$OwnerPID;OwnerStart=(Get-ProcessStartTicks $OwnerPID);CorePID=$owned.core;CoreStart=(Get-ProcessStartTicks $owned.core);SupervisorPID=$owned.supervisor;SupervisorStart=(Get-ProcessStartTicks $owned.supervisor);BeforeSystem=$BeforeSystem;BeforeEnv=$BeforeEnv;TargetSystem=$TargetSystem;TargetEnv=$TargetEnv;Started=(Get-Date).ToString('o')}
    }
    # Keep the production allocation algorithm, excluding all but a verified test-only free candidate.
    # Actual listener ownership and readiness still run in the real core and helper processes.
    function Get-NetTCPConnection {
        [CmdletBinding()]param([string[]]$State,[uint16[]]$LocalPort)
        if($script:AllocatingGateway -and $State -contains 'Listen' -and $LocalPort.Count -eq 1 -and $LocalPort[0] -ge 18790 -and $LocalPort[0] -le 18890 -and $LocalPort[0] -ne $script:GatewayPort){return [pscustomobject]@{State='Listen';LocalPort=$LocalPort[0]}}
        NetTCPIP\Get-NetTCPConnection @PSBoundParameters
    }
    function Read-TestBody([int]$ProxyPort){
        $tcp=New-Object Net.Sockets.TcpClient
        try{
            $tcp.Connect('127.0.0.1',$ProxyPort);$stream=$tcp.GetStream();$stream.ReadTimeout=4000
            $bytes=[Text.Encoding]::ASCII.GetBytes("GET http://127.0.0.1:$($ports[2])/probe HTTP/1.1`r`nHost: 127.0.0.1:$($ports[2])`r`nConnection: close`r`n`r`n")
            $stream.Write($bytes,0,$bytes.Length);$reader=New-Object IO.StreamReader($stream);$reply=$reader.ReadToEnd()
            if($reply -notmatch '^HTTP/1.[01] 200'){throw 'Isolated HTTP probe failed'}
            return $reply.Substring($reply.IndexOf("`r`n`r`n")+4).Trim()
        }finally{$tcp.Dispose()}
    }
    function Test-ProxyRoute([string]$Key,[switch]$Fast){
        if($script:PreflightEdit -and $Key -eq 'b' -and -not $script:PreflightEdited){
            $file=$script:ExternalFiles[$script:PreflightEdit]
            $value=Get-Content -LiteralPath $file -Raw -Encoding UTF8|ConvertFrom-Json
            if($script:PreflightEdit -eq 'settings'){$value.Profiles[1].Name='Concurrent A label'}else{$value.defaultRoute='b';$value.entries[0].route='b'}
            Write-LocalJson $file $value
            $script:PreflightBytes=Get-TestBytes $file;$script:PreflightEdited=$true
        }
        $p=Get-Profile $Key;$body=Read-TestBody $p.Port
        [pscustomobject]@{Key=$Key;Usable=($body -in @('A','B','D'));Results=@()}
    }
    $realRouter=${function:Invoke-AppRouter}
    function Invoke-AppRouter($Request,[int]$TimeoutMilliseconds=55000){
        $script:Actions+=@([string]$Request.action)
        if($Request.action -eq 'start'){
            $script:AllocatingGateway=$false
            if($script:FailBeforeStart){
                $script:StartInjected++
                if($script:ConcurrentEdit){
                    [IO.File]::AppendAllText($script:ExternalFiles.script,"`r`n// fixture concurrent user edit`r`n")
                    $script:ConcurrentBytes=Get-TestBytes $script:ExternalFiles.script
                    $script:AtFailureRuntime=Get-TestBytes $script:ExternalFiles.runtime
                }
                throw 'Injected isolated failure before core start'
            }
        }
        $result=& $realRouter $Request $TimeoutMilliseconds
        if($Request.action -eq 'detach-offline'){$script:Detached=$result}
        return $result
    }
    function Initialize-TestScenario([string]$Name){
        $script:Scenario=Join-Path $qa $Name;$script:scenarioRoots+=@($script:Scenario)
        $script:DataRoot=Join-Path $script:Scenario 'data';$script:ConfigPath=Join-Path $script:DataRoot 'config.json';$script:StatePath=Join-Path $script:DataRoot 'selection.json';$script:BackupDir=Join-Path $script:DataRoot 'backups'
        $env:PROXY_SWITCH_DATA_DIR=$script:DataRoot;$env:PROXY_SWITCH_TEST_ENGINE_DIR=Join-Path $script:Scenario 'engine';$env:PROXY_SWITCH_TEST_PIPE='\\.\pipe\ProxySwitch-Test-'+[Guid]::NewGuid().ToString('N')
        $offlinePort=New-TestPort
        & $node $seedScript 'seed' $repository $script:Scenario $ports[0] $ports[1] $offlinePort
        if($LASTEXITCODE -ne 0){throw 'Could not generate isolated external fixture'}
        $script:Profiles=Read-ProfileSettings
        $script:ExternalFiles=@{settings=$script:ConfigPath;state=(Join-Path $script:DataRoot 'app-rules.json');runtime=(Join-Path $env:PROXY_SWITCH_TEST_ENGINE_DIR 'clash-verge.yaml');script=(Join-Path $env:PROXY_SWITCH_TEST_ENGINE_DIR 'profiles\Script.js')}
        $script:BeforeBytes=@{};foreach($key in $script:ExternalFiles.Keys){$script:BeforeBytes[$key]=Get-TestBytes $script:ExternalFiles[$key]}
        $script:ClientSettings=Join-Path $env:PROXY_SWITCH_TEST_ENGINE_DIR 'verge.yaml';$script:ClientBytes=Get-TestBytes $script:ClientSettings
        $script:FakeSystem=[pscustomobject]@{Flags=3;Server=('127.0.0.1:'+$offlinePort);Bypass='localhost'}
        $script:FakeEnv=[pscustomobject]@{HTTP_PROXY=('http://127.0.0.1:'+$offlinePort);HTTPS_PROXY=('http://127.0.0.1:'+$offlinePort);ALL_PROXY=('http://127.0.0.1:'+$offlinePort);NO_PROXY='localhost'}
        $script:BeforeSystem=$script:FakeSystem;$script:BeforeEnv=$script:FakeEnv;$script:WindowsWrites=0;$script:ClientReads=0
        $script:Actions=@();$script:Detached=$null;$script:FailBeforeStart=$false;$script:ConcurrentEdit=$false;$script:StartInjected=0;$script:GatewayPort=0;$script:PreflightEdit='';$script:PreflightEdited=$false
        foreach($candidate in 18890..18790){
            $listener=New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback,$candidate)
            try{$listener.Server.ExclusiveAddressUse=$true;$listener.Start();$script:GatewayPort=$candidate;break}catch{}finally{$listener.Stop()}
        }
        if(-not $script:GatewayPort){throw 'No isolated gateway candidate available'}
        $script:AllocatingGateway=$true
    }

    Initialize-TestScenario 'success'
    $oldStatus=Invoke-AppRouter @{action='status'} -TimeoutMilliseconds 9000
    Check (-not $oldStatus.available -and (Get-RoutingSnapshot).installed -and (Get-RoutingSnapshot).entries.Count -eq 1) 'Saved external rules exist while the old controller is offline'
    Check (-not (Test-Path -LiteralPath (Get-Profile 'clash').CorePath) -and -not @(NetTCPIP\Get-NetTCPConnection -State Listen -LocalPort (Get-Profile 'clash').Port -ErrorAction SilentlyContinue).Count) 'Old external core and proxy listener are both absent'
    $result=Set-UniversalProxy 'b'
    Check ($script:Actions -contains 'detach-offline' -and $script:Detached.detached -and $script:Actions.IndexOf('detach-offline') -lt $script:Actions.IndexOf('start')) 'Real unified switch detaches offline rules before starting the owned core'
    $gateway=Get-Profile (Get-GatewayKey);$live=Invoke-AppRouter @{action='status'}
    Check ($script:Profiles.Routing.Adapter -eq 'standalone' -and $gateway.Port -eq $script:GatewayPort -and $live.available -and $live.defaultLoaded -and $live.effectiveDefaultRoute -eq 'b') 'Owned standalone entry and actual selector are ready on B'
    Check ((Read-TestBody $gateway.Port) -ceq 'B') 'An actual HTTP request through the new fixed entry returns B'
    Check ($script:FakeSystem.Server -eq ('127.0.0.1:'+$gateway.Port) -and $script:FakeEnv.HTTPS_PROXY -eq ('http://127.0.0.1:'+$gateway.Port)) 'Windows write stubs now point to the verified fixed entry'
    $clean=& $node $seedScript 'clean' $repository $script:Scenario|ConvertFrom-Json
    Check ($LASTEXITCODE -eq 0 -and $clean.runtime -and $clean.script) 'Only owned external routing objects and script suffix were removed'
    $saved=Get-RoutingSnapshot;$backup=Get-Content -LiteralPath $result.Backup -Raw -Encoding UTF8|ConvertFrom-Json
    Check ($saved.entries.Count -eq 0 -and $saved.defaultRoute -eq 'b' -and $saved.launchEntries[0].route -eq 'Follow') 'Unified migration clears old EXE overrides and follows B for saved launch entries'
    Check ($backup.Routing.entries.Count -eq 1 -and $backup.Routing.defaultRoute -eq 'a' -and $backup.Routing.launchEntries[0].route -eq 'a') 'Unified undo snapshot retains the prior rules and saved default'
    Check ($script:ClientReads -gt 0 -and (Get-TestBytes $script:ClientSettings) -ceq $script:ClientBytes -and $result.Message -match '系统代理') 'A third-party SystemProxy-only client permits explicit switching and retains its own toggles with a warning'
    $coreOwner=Get-Content -LiteralPath (Join-Path $script:DataRoot 'gateway\process.json') -Raw|ConvertFrom-Json
    Restore-IndependentSession
    Check (-not (Test-SessionProcess $coreOwner.core $coreOwner.coreStartTicks)) 'Explicit test stop ends only the owned migrated core'

    Initialize-TestScenario 'start-failure'
    $script:FailBeforeStart=$true;$failure=''
    try{Set-UniversalProxy 'b'|Out-Null}catch{$failure=$_.Exception.Message}
    Check ($script:StartInjected -eq 1 -and $script:Detached.detached -and $script:Actions -contains 'restore-offline-detach' -and $failure -match '已恢复启用前设置') 'Failure before core start invokes the paired offline restore and reports recovery'
    foreach($key in @('settings','runtime','script','state')){Check ((Get-TestBytes $script:ExternalFiles[$key]) -ceq $script:BeforeBytes[$key]) ('Failed startup restores original '+$key+' bytes including BOM')}
    Check ($script:WindowsWrites -eq 0 -and (Test-SameSnapshot $script:FakeSystem $script:BeforeSystem) -and (Test-SameEnv $script:FakeEnv $script:BeforeEnv)) 'Failed migration never writes Windows proxy or environment settings'
    Check (-not [IO.File]::Exists((Join-Path $script:DataRoot 'gateway\process.json')) -and -not [IO.File]::Exists((Get-IndependentSessionPath))) 'Injected pre-start failure creates no owned core or protection session'

    Initialize-TestScenario 'concurrent-edit'
    $script:FailBeforeStart=$true;$script:ConcurrentEdit=$true;$failure=''
    try{Set-UniversalProxy 'b'|Out-Null}catch{$failure=$_.Exception.Message}
    Check ($script:StartInjected -eq 1 -and $script:Actions -contains 'restore-offline-detach' -and $failure -match '迁移回滚未完成' -and $failure -notmatch '已恢复启用前设置') 'Concurrent external edit produces an explicit incomplete rollback result'
    Check ((Get-TestBytes $script:ExternalFiles.script) -ceq $script:ConcurrentBytes) 'Rollback preserves the external actor latest script bytes'
    Check ((Get-TestBytes $script:ExternalFiles.runtime) -ceq $script:AtFailureRuntime) 'Paired external rollback refuses partial restoration when script ownership has changed'
    Check ((Get-TestBytes $script:ExternalFiles.settings) -ceq $script:BeforeBytes.settings -and (Get-TestBytes $script:ClientSettings) -ceq $script:ClientBytes) 'Original adapter config is restored while third-party toggles remain untouched'
    Check ($script:WindowsWrites -eq 0 -and (Test-SameSnapshot $script:FakeSystem $script:BeforeSystem) -and (Test-SameEnv $script:FakeEnv $script:BeforeEnv)) 'Concurrent-edit failure also leaves Windows settings unchanged'
    $receipt=Get-Content -LiteralPath $script:Detached.backup -Raw -Encoding UTF8|ConvertFrom-Json
    $retained=Join-Path $env:PROXY_SWITCH_TEST_ENGINE_DIR ('proxy-switch-backups\offline-detach-'+$receipt.id+'\script.before')
    Check ((Get-TestBytes $retained) -ceq $script:BeforeBytes.script -and (Get-Content -LiteralPath $script:Detached.backup -Raw) -notmatch 'SYNTHETIC_FIXTURE') 'Original external bytes remain in the private engine backup and public receipt contains no fixture credentials'
    foreach($changed in @('settings','state')){
        Initialize-TestScenario ('preflight-'+$changed)
        $script:PreflightEdit=$changed;$failure=''
        try{Set-UniversalProxy 'b'|Out-Null}catch{$failure=$_.Exception.Message}
        Check ($script:PreflightEdited -and $failure -match '改变|变化|改动' -and $script:Actions -notcontains 'detach-offline' -and $script:Actions -notcontains 'start') ('Concurrent '+$changed+' change during preflight refuses migration before detach or startup')
        foreach($key in @('settings','runtime','script','state')){
            $expected=$script:BeforeBytes[$key];if($key -eq $changed){$expected=$script:PreflightBytes}
            Check ((Get-TestBytes $script:ExternalFiles[$key]) -ceq $expected) ('Preflight '+$changed+' race preserves latest '+$key+' bytes')
        }
        Check ($script:WindowsWrites -eq 0 -and (Test-SameSnapshot $script:FakeSystem $script:BeforeSystem) -and (Test-SameEnv $script:FakeEnv $script:BeforeEnv)) ('Preflight '+$changed+' race never changes Windows settings')
    }
    Write-Output ('PASS: '+$checks+' offline migration chain checks; real Set-UniversalProxy, offline detach, core, HTTP and exclusive file CAS; Windows/RunOnce writes isolated. Fixture: '+$qa)
}finally{
    if($script:DataRoot -and [IO.File]::Exists((Join-Path $script:DataRoot 'gateway-session.json'))){try{Restore-IndependentSession}catch{}}
    $cleanupIncomplete=$false
    foreach($scenarioRoot in $scenarioRoots){
        $stop=Join-Path $scenarioRoot 'data\gateway\stop'
        if([IO.Directory]::Exists([IO.Path]::GetDirectoryName($stop))){[IO.File]::WriteAllText($stop,'stop')}
        $ownedFile=Join-Path $scenarioRoot 'data\gateway\process.json'
        if([IO.File]::Exists($ownedFile)){
            $owned=Get-Content -LiteralPath $ownedFile -Raw|ConvertFrom-Json;$deadline=[DateTime]::UtcNow.AddSeconds(12)
            do{
                $remaining=(Test-SessionProcess $owned.core $owned.coreStartTicks) -or (Test-SessionProcess $owned.supervisor $owned.supervisorStartTicks)
                if($remaining){Start-Sleep -Milliseconds 100}
            }while($remaining -and [DateTime]::UtcNow -lt $deadline)
            if($remaining){$cleanupIncomplete=$true}
        }
    }
    if($fixture){if(-not $fixture.HasExited){$fixture.Kill();[void]$fixture.WaitForExit(3000)};$fixture.Dispose()}
    foreach($key in $savedEnvironment.Keys){[Environment]::SetEnvironmentVariable($key,$savedEnvironment[$key],'Process')}
    if($cleanupIncomplete){throw ('Owned fixture shutdown was not confirmed: '+$qa)}
}
