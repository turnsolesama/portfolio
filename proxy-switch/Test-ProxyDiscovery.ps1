$ErrorActionPreference='Stop'
$env:PROXY_SWITCH_DATA_DIR=Join-Path $env:TEMP ('ProxySwitch-unit-'+[Guid]::NewGuid().ToString('N'))
. (Join-Path $PSScriptRoot 'ProxyBackend.ps1')
$script:pass=0
function Check($Condition,[string]$Message){if(-not $Condition){throw $Message};$script:pass++}
$empty=[pscustomobject]@{Version=3;Profiles=@();Routing=[pscustomobject]@{Adapter='none';ProfileId=''}}
$first=[pscustomobject]@{Id='detected1';Name='Custom network';Protocol='http';Host='127.0.0.1';Port=18081;CorePath='';AppPath='';AutoPort=$false}
$second=[pscustomobject]@{Id='detected2';Name='Backup network';Protocol='socks5';Host='::1';Port=18082;CorePath='';AppPath='';AutoPort=$false}
$merged=Merge-DiscoveredProfiles $empty @($first,$second)
Check ($merged.Added.Count -eq 2 -and $merged.Settings.Profiles.Count -eq 2) 'Fresh install discovers both protocols without predefined brands'
$again=Merge-DiscoveredProfiles $merged.Settings @($first,$second)
Check ($again.Added.Count -eq 0) 'Repeated scan does not duplicate profiles'
$merged.Settings.Profiles[0].Name='User chosen name';$merged.Settings.Profiles[0].Id='stableRuleId'
$again=Merge-DiscoveredProfiles $merged.Settings @($first)
Check ($again.Settings.Profiles[0].Id -eq 'stableRuleId' -and $again.Settings.Profiles[0].Name -eq 'User chosen name') 'Saved identity, name and rules are preserved'
$duplicate=$first | Select-Object *;$duplicate.Host='::1';$duplicate.Protocol='socks5'
Check ((Merge-DiscoveredProfiles $merged.Settings @($duplicate)).Added.Count -eq 0) 'Dual-stack and mixed ports are deduplicated'
$ignored=ConvertTo-ValidProfileSettings $empty;$ignored.DiscoveryIgnored=@('loopback:18081')
Check ((Merge-DiscoveredProfiles $ignored @($first)).Added.Count -eq 0) 'Deleted endpoints are not silently re-added'
$remote=$first | Select-Object *;$remote.Host='proxy.example.org'
Check ((Merge-DiscoveredProfiles $empty @($remote)).Added.Count -eq 0) 'Discovery never imports unverified remote endpoints'
$collision=$second | Select-Object *;$collision.Name=$first.Name;$collision.Id=$first.Id
$merged=Merge-DiscoveredProfiles $empty @($first,$collision)
Check ($merged.Settings.Profiles[0].Name -ne $merged.Settings.Profiles[1].Name -and $merged.Settings.Profiles[0].Id -ne $merged.Settings.Profiles[1].Id) 'Discovery resolves naming and id collisions'
$script:Profiles=ConvertTo-ValidProfileSettings $empty
$realProbe=${function:Test-LocalProxyProtocol};$realListeners=${function:Get-ProxyDiscoveryListeners}
function Get-ProxyDiscoveryListeners {@([pscustomobject]@{Host='127.0.0.1';Port=18081;Name='UnbrandedClient';Path=''},[pscustomobject]@{Host='::1';Port=18081;Name='UnbrandedClient';Path=''},[pscustomobject]@{Host='127.0.0.1';Port=18082;Name='OtherClient';Path=''},[pscustomobject]@{Host='127.0.0.1';Port=18083;Name='ControlAPI';Path=''})}
function Test-LocalProxyProtocol($Address,$Port,$Protocol){($Port -eq 18081) -or ($Port -eq 18082 -and $Protocol -eq 'socks5')}
$found=@(Find-LocalProxies)
Check ($found.Count -eq 2 -and $found[0].Protocol -eq 'http' -and $found[1].Protocol -eq 'socks5') 'Protocol validation, mixed-port preference and control-port exclusion'
Check ($found[0].CorePath -eq '' -and $found[0].Name -like 'UnbrandedClient*') 'Missing process path and unfamiliar client names do not block discovery'
$again=@(Find-LocalProxies);Check ($found[0].Id -eq $again[0].Id) 'Discovered identity is stable between scans'
${function:Test-LocalProxyProtocol}=$realProbe;${function:Get-ProxyDiscoveryListeners}=$realListeners

# Real loopback sockets verify fragmented replies, authentication, false positives and timeout handling.
Add-Type -TypeDefinition @'
using System; using System.Net; using System.Net.Sockets; using System.Text; using System.Threading;
public sealed class ProxyDiscoveryFixture : IDisposable {
    TcpListener listener; Thread worker; volatile bool stopped; string mode;
    public int Port { get; private set; }
    public ProxyDiscoveryFixture(string value) {
        mode=value; listener=new TcpListener(IPAddress.Loopback,0); listener.Start();
        Port=((IPEndPoint)listener.LocalEndpoint).Port; worker=new Thread(Run); worker.IsBackground=true; worker.Start();
    }
    void Run() {
        while(!stopped) { try { using(var client=listener.AcceptTcpClient()) {
            client.ReceiveTimeout=1000; client.SendTimeout=1000; var stream=client.GetStream();
            var data=new byte[1024]; int count=stream.Read(data,0,data.Length); if(count==0) continue;
            if(mode=="silent") {Thread.Sleep(150);continue;}
            if(mode=="socks" || mode=="auth") {
                if(data[0]!=5) continue; stream.WriteByte(5); Thread.Sleep(10); stream.WriteByte((byte)(mode=="auth"?2:0));
            } else {
                if(data[0]!=(byte)'C') continue;
                string response=mode=="http" ? "HTTP/1.1 200 Connection established\r\n\r\n" :
                    mode=="page" ? "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 2\r\n\r\n{}" :
                    "HTTP/1.1 407 Proxy Authentication Required\r\n\r\n";
                var bytes=Encoding.ASCII.GetBytes(response); stream.Write(bytes,0,bytes.Length);
            }
        }} catch {if(stopped) return;} }
    }
    public void Dispose(){stopped=true;listener.Stop();worker.Join(1500);}
}
'@
foreach($case in @(@('http','http',$true),@('socks','socks5',$true),@('page','http',$false),@('auth','socks5',$false),@('rejected','http',$false),@('silent','http',$false))){
    $server=New-Object ProxyDiscoveryFixture($case[0]);$clock=[Diagnostics.Stopwatch]::StartNew()
    try{Check ((Test-LocalProxyProtocol '127.0.0.1' $server.Port $case[1] 100) -eq $case[2]) ('Local protocol fixture: '+$case[0]);if($case[0] -eq 'silent'){Check ($clock.ElapsedMilliseconds -lt 1500) 'Probe timeout is bounded'}}finally{$server.Dispose()}
}
Check (-not (Test-LocalProxyProtocol 'example.org' 80 'http')) 'Protocol probe is restricted to localhost'

# A scan saves only profile metadata in a temporary directory. Network writers must never be called.
$testDir=Join-Path $env:TEMP ('ProxySwitch-discovery-'+[Guid]::NewGuid().ToString('N'))
$script:DataRoot=$testDir;$script:ConfigPath=Join-Path $testDir 'config.json';$script:StatePath=Join-Path $testDir 'selection.json';$script:BackupDir=Join-Path $testDir 'backups'
function Set-SystemSnapshot {throw 'Unexpected system proxy mutation'}
function Set-UserProxyEnv {throw 'Unexpected environment mutation'}
function Get-SystemSnapshot {[pscustomobject]@{Flags=1;Server='';Bypass=''}}
function Get-Selection {$null}
function Find-LocalProxies {@($first,$second)}
Write-LocalJson $script:ConfigPath (ConvertTo-ValidProfileSettings $empty)
$result=Sync-LocalProxyDiscovery
Check ($result.Added -eq 2 -and (Read-ProfileSettings).Profiles.Count -eq 2) 'Verified proxies are saved atomically without network writes'
Check (@(Get-ChildItem -LiteralPath $script:BackupDir -File).Count -eq 1) 'Discovery preserves a previous settings backup'
$before=(Get-FileHash -LiteralPath $script:ConfigPath -Algorithm SHA256).Hash
$result=Sync-LocalProxyDiscovery
Check ($result.Added -eq 0 -and (Get-FileHash -LiteralPath $script:ConfigPath -Algorithm SHA256).Hash -eq $before) 'No settings rewrite when scan finds nothing new'
$other=Join-Path $testDir 'explicit';[void][IO.Directory]::CreateDirectory($other)
Write-LocalJson (Join-Path $other 'config.json') (ConvertTo-ValidProfileSettings $empty)
$worker=[PowerShell]::Create()
try{[void]$worker.AddScript({param($Root,$Data);. (Join-Path $Root 'ProxyBackend.ps1') -DataDirectory $Data;[pscustomobject]@{Path=$script:ConfigPath;Count=@($script:Profiles.Profiles).Count}}.ToString()).AddArgument($PSScriptRoot).AddArgument($other);$reply=@($worker.Invoke());Check (-not $worker.HadErrors -and $reply[-1].Count -eq 0 -and $reply[-1].Path -eq (Join-Path $other 'config.json')) 'UI worker uses the explicit configuration directory'}finally{$worker.Dispose()}
Write-Output ('PASS: '+$script:pass+' discovery assertions; loopback fixtures and isolated settings only.')
