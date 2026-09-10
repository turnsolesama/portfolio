param([string]$DataDirectory='')
$ErrorActionPreference = 'Stop'
$script:Root = $PSScriptRoot
. (Join-Path $PSScriptRoot 'Preferences.ps1') -DataDirectory $DataDirectory
. (Join-Path $PSScriptRoot 'RuntimeSupport.ps1')
. (Join-Path $PSScriptRoot 'ProcessInventory.ps1')
. (Join-Path $PSScriptRoot 'ProgramLaunch.ps1')
. (Join-Path $PSScriptRoot 'ProxyDiscovery.ps1')
. (Join-Path $PSScriptRoot 'IndependentGateway.ps1')
$script:Profiles = Read-ProfileSettings
$script:StatePath = Join-Path $script:DataRoot 'selection.json'
$script:BackupDir = Join-Path $script:DataRoot 'backups'
$script:ProxyNames = @('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY')

if (-not ('LocalProxySwitch.Native' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
namespace LocalProxySwitch {
    public sealed class Snapshot {
        public int Flags;
        public string Server;
        public string Bypass;
    }
    public static class Native {
        [DllImport("kernel32.dll", SetLastError=true)]
        private static extern bool GetNamedPipeServerProcessId(Microsoft.Win32.SafeHandles.SafePipeHandle pipe, out uint processId);
        public static int ControllerProcessId() {
            try {
                using(var pipe = new System.IO.Pipes.NamedPipeClientStream(".", "verge-mihomo", System.IO.Pipes.PipeDirection.InOut)) {
                    pipe.Connect(300); uint id;
                    return GetNamedPipeServerProcessId(pipe.SafePipeHandle, out id) ? (int)id : 0;
                }
            } catch { return 0; }
        }
        [StructLayout(LayoutKind.Explicit)]
        private struct Value {
            [FieldOffset(0)] public int Number;
            [FieldOffset(0)] public IntPtr Text;
            [FieldOffset(0)] public long FileTime;
        }
        [StructLayout(LayoutKind.Sequential)]
        private struct Option { public int Id; public Value Data; }
        [StructLayout(LayoutKind.Sequential)]
        private struct OptionList {
            public int Size;
            public IntPtr Connection;
            public int Count;
            public int Error;
            public IntPtr Options;
        }
        [DllImport("wininet.dll", EntryPoint="InternetQueryOptionW", SetLastError=true)]
        private static extern bool Query(IntPtr handle, int option, ref OptionList value, ref int size);
        [DllImport("wininet.dll", EntryPoint="InternetSetOptionW", SetLastError=true)]
        private static extern bool Set(IntPtr handle, int option, ref OptionList value, int size);
        [DllImport("wininet.dll", EntryPoint="InternetSetOptionW", SetLastError=true)]
        private static extern bool Notify(IntPtr handle, int option, IntPtr value, int size);
        [DllImport("kernel32.dll")]
        private static extern IntPtr GlobalFree(IntPtr memory);
        public static Snapshot Read() {
            int step = Marshal.SizeOf(typeof(Option));
            IntPtr memory = Marshal.AllocHGlobal(step * 3);
            try {
                for (int i=0; i<3; i++) {
                    Option item = new Option(); item.Id = i+1;
                    Marshal.StructureToPtr(item, IntPtr.Add(memory, i*step), false);
                }
                OptionList list = new OptionList();
                list.Size = Marshal.SizeOf(typeof(OptionList)); list.Count=3; list.Options=memory;
                int size=list.Size;
                if (!Query(IntPtr.Zero,75,ref list,ref size)) throw new Win32Exception(Marshal.GetLastWin32Error());
                Option flags=(Option)Marshal.PtrToStructure(memory,typeof(Option));
                Option server=(Option)Marshal.PtrToStructure(IntPtr.Add(memory,step),typeof(Option));
                Option bypass=(Option)Marshal.PtrToStructure(IntPtr.Add(memory,step*2),typeof(Option));
                Snapshot result=new Snapshot(); result.Flags=flags.Data.Number;
                result.Server=Marshal.PtrToStringUni(server.Data.Text) ?? "";
                result.Bypass=Marshal.PtrToStringUni(bypass.Data.Text) ?? "";
                return result;
            } finally {
                for(int i=1;i<3;i++) {
                    Option item=(Option)Marshal.PtrToStructure(IntPtr.Add(memory,i*step),typeof(Option));
                    if(item.Data.Text!=IntPtr.Zero) GlobalFree(item.Data.Text);
                }
                Marshal.FreeHGlobal(memory);
            }
        }
        public static void Write(int flags,string server,string bypass) {
            int step=Marshal.SizeOf(typeof(Option));
            IntPtr memory=Marshal.AllocHGlobal(step*3);
            IntPtr serverText=IntPtr.Zero; IntPtr bypassText=IntPtr.Zero;
            try {
                serverText=Marshal.StringToHGlobalUni(server ?? "");
                bypassText=Marshal.StringToHGlobalUni(bypass ?? "");
                Option a=new Option(); a.Id=1; a.Data.Number=flags;
                Option b=new Option(); b.Id=2; b.Data.Text=serverText;
                Option c=new Option(); c.Id=3; c.Data.Text=bypassText;
                Marshal.StructureToPtr(a,memory,false);
                Marshal.StructureToPtr(b,IntPtr.Add(memory,step),false);
                Marshal.StructureToPtr(c,IntPtr.Add(memory,step*2),false);
                OptionList list=new OptionList(); list.Size=Marshal.SizeOf(typeof(OptionList));
                list.Count=3; list.Options=memory;
                if(!Set(IntPtr.Zero,75,ref list,list.Size)) throw new Win32Exception(Marshal.GetLastWin32Error());
                if(!Notify(IntPtr.Zero,95,IntPtr.Zero,0)) throw new Win32Exception(Marshal.GetLastWin32Error());
                if(!Notify(IntPtr.Zero,37,IntPtr.Zero,0)) throw new Win32Exception(Marshal.GetLastWin32Error());
            } finally {
                if(serverText!=IntPtr.Zero) Marshal.FreeHGlobal(serverText);
                if(bypassText!=IntPtr.Zero) Marshal.FreeHGlobal(bypassText);
                Marshal.FreeHGlobal(memory);
            }
        }
    }
}
'@
}

function Get-Profile([string]$Key) {
    $source=$script:Profiles.Profiles | Where-Object {$_.Id -eq $Key} | Select-Object -First 1
    if(-not $source){throw '所选代理不存在，请先到代理管理添加。'}
    $port=[int]$source.Port
    if($script:Profiles.Routing.Adapter -eq 'clash-verge' -and $Key -eq (Get-GatewayKey) -and $source.AutoPort){
        $path=Join-Path $env:APPDATA 'io.github.clash-verge-rev.clash-verge-rev\verge.yaml'
        if(Test-Path -LiteralPath $path){$m=Select-String -LiteralPath $path -Pattern '^verge_mixed_port:\s*(\d+)\s*$' | Select-Object -First 1;if($m){$port=[int]$m.Matches[0].Groups[1].Value}}
    }
    if($port -lt 1 -or $port -gt 65535){throw '代理端口无效。'}
    [pscustomobject]@{Key=$Key;Id=$Key;Name=$source.Name;Protocol=$source.Protocol;Host=$source.Host;Port=$port;CorePath=$source.CorePath;AppPath=$source.AppPath;AutoPort=$source.AutoPort}
}

function Get-SystemSnapshot { [LocalProxySwitch.Native]::Read() }
function Set-SystemSnapshot($Snapshot) { [LocalProxySwitch.Native]::Write([int]$Snapshot.Flags,[string]$Snapshot.Server,[string]$Snapshot.Bypass) }
function Get-UserProxyEnv {
    $result = [ordered]@{}
    foreach ($name in $script:ProxyNames) { $result[$name] = [Environment]::GetEnvironmentVariable($name,'User') }
    [pscustomobject]$result
}
function Set-UserProxyEnv($Values) {
    foreach ($name in $script:ProxyNames) {
        $value = $Values.$name
        if ($null -ne $value) { $value = [string]$value }
        if([string][Environment]::GetEnvironmentVariable($name,'User') -cne [string]$value){[Environment]::SetEnvironmentVariable($name,$value,'User')}
    }
}
function Get-Selection {
    if (Test-Path -LiteralPath $script:StatePath) {
        try { Get-Content -LiteralPath $script:StatePath -Raw -Encoding UTF8 | ConvertFrom-Json } catch { $null }
    }
}
function Save-Selection($Selection) {
    [void][IO.Directory]::CreateDirectory($script:DataRoot)
    $temp = $script:StatePath + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
    $Selection | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $temp -Encoding UTF8
    if (Test-Path -LiteralPath $script:StatePath) { [IO.File]::Replace($temp,$script:StatePath,[NullString]::Value) }
    else { [IO.File]::Move($temp,$script:StatePath) }
}
function Protect-Endpoint([string]$Value) {
    if (-not $Value) { return '未设置' }
    return (($Value -replace '(?<=://)[^/@\s]+@','[已隐藏凭据]@') -replace '[?].*$','?[已隐藏参数]')
}
function Get-EndpointKey([string]$Value) {
    if(-not $Value){return 'Unset'}
    try{
        $inputValue=$Value;if($inputValue -notmatch '^[a-z]+://'){$inputValue='http://'+$inputValue}
        $uri=[uri]$inputValue
        if($uri.UserInfo -or $uri.Query -or $uri.AbsolutePath -notin @('','/')){return 'Other'}
        foreach($key in (Get-ProfileKeys)){
            $p=Get-Profile $key;$same=($uri.Host.Trim('[',']') -ieq $p.Host)
            if($uri.Host.Trim('[',']') -in @('localhost','127.0.0.1','::1') -and $p.Host -in @('localhost','127.0.0.1','::1')){$same=$true}
            $protocol=($uri.Scheme -eq 'http' -and $p.Protocol -eq 'http') -or ($uri.Scheme -in @('socks5','socks5h') -and $p.Protocol -eq 'socks5')
            if($same -and $protocol -and $uri.Port -eq $p.Port){return $key}
        }
    }catch{}
    return 'Other'
}

function Get-SystemKey($Snapshot) {
    if ($Snapshot.Flags -band 12) { return 'Other' }
    if (-not ($Snapshot.Flags -band 2)) { return 'Direct' }
    $key = Get-EndpointKey $Snapshot.Server
    if ($key -eq 'Unset') { return 'Other' }
    return $key
}
function Get-GatewayControllerPID {[LocalProxySwitch.Native]::ControllerProcessId()}
function Test-GatewayServiceOwner($Profile,$Owner) {
    # Elevated service image paths may be unreadable. Match the existing controller's OS identity instead.
    if(-not $Owner -or $Owner.Path -or -not $Profile.CorePath){return $false}
    if($Profile.Id -ne (Get-GatewayKey) -and $script:Profiles.Routing.Adapter -ne 'standalone'){return $false}
    if($Owner.ProcessName -notmatch '^verge-mihomo(?:-alpha)?$' -or [IO.Path]::GetFileNameWithoutExtension($Profile.CorePath) -ine $Owner.ProcessName){return $false}
    return ((Get-GatewayControllerPID) -eq $Owner.Id)
}
function Get-Listener($Profile,[switch]$ProbeRemote,$TcpRows=$null) {
    if($Profile.Host -in @('localhost','127.0.0.1','::1')){
        if($null -eq $TcpRows){$entries=@(Get-NetTCPConnection -State Listen -LocalPort $Profile.Port -ErrorAction SilentlyContinue)}
        else{$entries=@($TcpRows | Where-Object {$_.State -eq 'Listen' -and $_.LocalPort -eq $Profile.Port})}
        $entries=@($entries | Where-Object {$_.LocalAddress -in @('127.0.0.1','0.0.0.0','::','::1')})
        foreach($entry in $entries){
            $owner=Get-ProcessInventory -Id $entry.OwningProcess
            if($owner -and (-not $Profile.CorePath -or $owner.Path -ieq $Profile.CorePath -or (Test-GatewayServiceOwner $Profile $owner))){return [pscustomobject]@{PID=$owner.Id;Name=$owner.ProcessName}}
        }
    }elseif($ProbeRemote){
        $tcp=New-Object Net.Sockets.TcpClient;$connect=$null
        try{$connect=$tcp.BeginConnect($Profile.Host,$Profile.Port,$null,$null);if($connect.AsyncWaitHandle.WaitOne(800)){$tcp.EndConnect($connect);return [pscustomobject]@{PID=0;Name='TCP'}}}catch{}finally{if($connect){$connect.AsyncWaitHandle.Close()};$tcp.Close()}
    }
    return $null
}

function Get-ClientInterference {
    $result=[pscustomobject]@{Running=$false;Tun=$false;Guard=$false;SystemProxy=$false}
    $result.Running=[bool](Get-Process -Name 'clash-verge','verge-mihomo' -ErrorAction SilentlyContinue)
    $path=Join-Path $env:APPDATA 'io.github.clash-verge-rev.clash-verge-rev\verge.yaml'
    if($result.Running -and (Test-Path -LiteralPath $path)){
        $result.Tun=[bool](Select-String -LiteralPath $path -Pattern '^enable_tun_mode:\s*true\s*$' -Quiet)
        $result.Guard=[bool](Select-String -LiteralPath $path -Pattern '^enable_proxy_guard:\s*true\s*$' -Quiet)
        $result.SystemProxy=[bool](Select-String -LiteralPath $path -Pattern '^enable_system_proxy:\s*true\s*$' -Quiet)
    }
    return $result
}
function Assert-ClientCompatibility([string]$Entrance,[bool]$Managed) {
    $client=Get-ClientInterference
    if($script:Profiles.Routing.Adapter -eq 'standalone'){
        if($client.Tun -or $client.Guard -or $client.SystemProxy){throw '独立模式需要关闭其他客户端的 TUN、代理守卫与系统代理开关；保留上游运行。'}
        if(-not (Test-Path -LiteralPath (Get-IndependentSessionPath))){throw '独立入口已停止，请先点击启用独立分流。'}
        return
    }
    if(-not ($client.Tun -or $client.Guard)){return}
    if($Managed -and $Entrance -eq (Get-GatewayKey) -and $script:Profiles.Routing.UnifiedMode -eq 'gateway'){
        $live=Invoke-AppRouter @{action='status'}
        if(-not $live.available -or $live.mode -ne 'rule'){throw '固定入口尚未就绪，请检查本机内核路径、控制接口和规则模式。'}
        return
    }
    throw 'Clash 的 TUN / 代理守卫正在接管网络。请在代理管理启用固定入口分流，或先关闭 TUN / 代理守卫后使用系统入口切换。'
}
function Get-ClientWarnings {
    $client=Get-ClientInterference
    if($client.Tun -or $client.Guard){
        if($script:Profiles.Routing.UnifiedMode -eq 'gateway'){'固定入口模式：现有 TUN / 代理守卫保留运行，切换在引擎内进行。请勿退出承载入口的 Clash。'}
        else{'Clash 的 TUN / 代理守卫正在接管网络，系统入口切换会被阻止；请配置固定入口分流。'}
    }elseif($client.SystemProxy){'Clash 开着系统代理；启动或退出它可能改写系统入口，请在这里重新应用。'}
}
function Get-OverrideWarnings([string]$Key) {
    foreach($name in @('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY')){
        $value=[Environment]::GetEnvironmentVariable($name,'Machine')
        if($value -and $Key -eq 'Direct'){"机器级 $name 仍存在，用户级直连不能覆盖它。"}
    }
}

function Get-ConnectionProfile($Connection) {
    foreach($key in (Get-ProfileKeys)){
        $p=Get-Profile $key
        $same=($Connection.RemoteAddress -ieq $p.Host)
        if($p.Host -in @('127.0.0.1','localhost','::1') -and $Connection.RemoteAddress -in @('127.0.0.1','::1','::ffff:127.0.0.1')){$same=$true}
        if($same -and [int]$Connection.RemotePort -eq $p.Port){return $key}
    }
    return ''
}
function Get-LiveConnections($TcpRows=$null) {
    $processes=@{};Get-ProcessInventory | ForEach-Object {$processes[[int]$_.Id]=$_.ProcessName}
    $items=@();if($null -eq $TcpRows){$tcp=@(Get-NetTCPConnection -State Established -ErrorAction SilentlyContinue)}else{$tcp=@($TcpRows|Where-Object State -eq 'Established')}
    foreach($c in $tcp){$route=Get-ConnectionProfile $c;if($route){$items+=[pscustomobject]@{PID=[int]$c.OwningProcess;Route=$route}}}
    foreach($group in ($items | Group-Object PID,Route)){$c=$group.Group[0];[pscustomobject]@{Process=$processes[$c.PID];PID=$c.PID;Route=$c.Route;Count=$group.Count}}
}

function Get-ProxyStatus($RoutingStatus=$null,$TcpRows=$null) {
    $snapshot=Get-SystemSnapshot;$key=Get-SystemKey $snapshot;$envValues=Get-UserProxyEnv;$selection=Get-Selection
    $aligned=($key -ne 'Other');$envConflict=($key -eq 'Other');$environment=@()
    foreach($name in @('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY')){
        $route=Get-EndpointKey $envValues.$name
        $environment+=[pscustomobject]@{Name=$name;Value=(Protect-Endpoint $envValues.$name);Route=$route}
        if(($key -eq 'Direct' -and $route -ne 'Unset') -or ($key -ne 'Direct' -and $route -ne $key)){$aligned=$false}
        if($route -ne 'Unset' -and $route -ne $key){$envConflict=$true}
    }
    $listeners=@();foreach($id in (Get-ProfileKeys)){
        $p=Get-Profile $id;$remote=$p.Host -notin @('localhost','127.0.0.1','::1');$l=Get-Listener $p -TcpRows $TcpRows
        $listeners+=[pscustomobject]@{Key=$id;Name=$p.Name;Protocol=$p.Protocol;Port=$p.Port;Remote=$remote;Ready=$(if($remote){$null}else{$null -ne $l})}
    }
    $ready=$key -eq 'Direct'
    if($key -ne 'Direct'){$entry=$listeners | Where-Object {$_.Key -eq $key} | Select-Object -First 1;$ready=$(if($entry){$entry.Ready}else{$null})}
    $live=@(Get-LiveConnections -TcpRows $TcpRows);$warnings=@(Get-ClientWarnings)+@(Get-OverrideWarnings $key)
    $drift=($null -ne $selection -and $selection.Key -and $selection.Key -ne $key)
    $oldConnections=@($live | Where-Object {$_.Route -ne $key})
    # Historical intent is not evidence of the engine's live route.
    $network=$key
    if($key -eq (Get-GatewayKey) -and $RoutingStatus.Available -and $RoutingStatus.DefaultLoaded -and $RoutingStatus.DefaultRoute){$network=$RoutingStatus.DefaultRoute;if($RoutingStatus.EffectiveDefaultRoute){$network=$RoutingStatus.EffectiveDefaultRoute}}
    [pscustomobject]@{Key=$key;Current=(Get-RouteName $key);NetworkKey=$network;NetworkName=(Get-RouteName $network);Server=(Protect-Endpoint $snapshot.Server);Flags=$snapshot.Flags;Environment=$environment;Aligned=$aligned;EnvConflict=$envConflict;EndpointReady=$ready;Listeners=$listeners;Selected=$selection;Drift=[bool]$drift;Connections=$live;OldConnections=$oldConnections;Warnings=$warnings;GatewayKey=(Get-GatewayKey);CheckedAt=(Get-Date).ToString('HH:mm:ss')}
}

function Start-HttpEndpointProbe($Profile,[string]$Url,[bool]$Fast=$false) {
    $psi=New-Object Diagnostics.ProcessStartInfo
    $psi.FileName=Get-SystemCurlPath
    $connect=6;$maximum=10;if($Fast){$connect=3;$maximum=5}
    $psi.Arguments='--silent --show-error --head --output NUL --connect-timeout '+$connect+' --max-time '+$maximum+' --proxy '+$(if($Profile.Protocol -eq 'socks5'){'socks5h://'}else{'http://'})+(Get-EndpointAddress $Profile)+' --noproxy "" --write-out "%{http_code} %{time_total} %{http_connect}" '+$Url
    $psi.UseShellExecute=$false;$psi.CreateNoWindow=$true;$psi.RedirectStandardOutput=$true;$psi.RedirectStandardError=$true
    $process=New-Object Diagnostics.Process;$process.StartInfo=$psi
    try{
        [void]$process.Start()
        [pscustomobject]@{Process=$process;Output=$process.StandardOutput.ReadToEndAsync();Error=$process.StandardError.ReadToEndAsync();Url=$Url}
    }catch{$process.Dispose();throw}
}
function Read-HttpEndpointProbe($Probe) {
    $fields=$Probe.Output.Result.Trim() -split '\s+';$code=0;$seconds=0.0
    if($fields.Count -ge 2){
        [void][int]::TryParse($fields[0],[ref]$code)
        [void][double]::TryParse($fields[1],[Globalization.NumberStyles]::Float,[Globalization.CultureInfo]::InvariantCulture,[ref]$seconds)
    }
    $reachable=($Probe.Process.ExitCode -eq 0 -and $code -gt 0)
    $accepted=$reachable -and (($code -ge 200 -and $code -lt 400) -or ($Probe.Url -eq 'https://api.openai.com/v1/models' -and $code -eq 401))
    $note='无法连接 / 超时'
    if($reachable){$note='HTTP '+$code;if($code -eq 401){$note+='；已到达接口，未携带登录凭据'};if($code -eq 403){$note+='；站点拒绝或验证，不能据此确认网页可用'}}
    [pscustomobject]@{Site=([uri]$Probe.Url).Host;Code=$code;Seconds=$seconds;Reachable=$reachable;Accepted=$accepted;Note=$note}
}
function Close-HttpEndpointProbe($Probe) {
    try{if(-not $Probe.Process.HasExited){$Probe.Process.Kill();[void]$Probe.Process.WaitForExit(1000)}}finally{$Probe.Process.Dispose()}
}
function Test-HttpEndpoint($Profile,[string]$Url) {
    $probe=Start-HttpEndpointProbe $Profile $Url
    try{if(-not $probe.Process.WaitForExit(12000)){throw '检测进程超时。'};Read-HttpEndpointProbe $probe}finally{Close-HttpEndpointProbe $probe}
}
function Test-ProxyRoute([string]$Key,[switch]$Fast) {
    $profile=Get-Profile $Key
    if(-not (Get-Listener $profile -ProbeRemote)){throw ($profile.Name+' 入口未就绪，请启动关联程序或检查地址与端口。未修改代理。')}
    $urls=@('https://www.google.com/generate_204','https://api.openai.com/v1/models','https://chatgpt.com/')
    $results=@()
    if($Fast){
        $probes=@();$finished=@{};$clock=[Diagnostics.Stopwatch]::StartNew()
        try{
            foreach($url in $urls){$probes+=@(Start-HttpEndpointProbe $profile $url $true)}
            while($clock.Elapsed.TotalSeconds -lt 7){
                foreach($probe in $probes){
                    if(-not $finished.ContainsKey($probe.Url) -and $probe.Process.HasExited){$finished[$probe.Url]=$true;$result=Read-HttpEndpointProbe $probe;$results+=@($result)}
                }
                if(@($results | Where-Object Accepted).Count -gt 0 -or $finished.Count -eq $probes.Count){break}
                Start-Sleep -Milliseconds 30
            }
        }finally{foreach($probe in $probes){Close-HttpEndpointProbe $probe}}
    }else{foreach($url in $urls){$results+=@(Test-HttpEndpoint $profile $url)}}
    [pscustomobject]@{Key=$Key;Name=$profile.Name;Ready=$true;Usable=(@($results | Where-Object Accepted).Count -gt 0);Results=$results}
}
function Write-OperationProgress([string]$Message) {
    if($script:OperationProgress){$script:OperationProgress.Enqueue($Message)}
}
function Test-SameSnapshot($A,$B) { ($A.Flags -eq $B.Flags -and $A.Server -eq $B.Server -and $A.Bypass -eq $B.Bypass) }
function Test-SameEnv($A,$B) {
    foreach ($name in $script:ProxyNames) { if ([string]$A.$name -cne [string]$B.$name) { return $false } }
    return $true
}
function New-EnvTarget($Before,[string]$Key) {
    $target=[ordered]@{}
    foreach ($name in $script:ProxyNames) { $target[$name]=$Before.$name }
    $proxy=$null
    if ($Key -ne 'Direct') { $profile=Get-Profile $Key; $proxy='http://' + (Get-EndpointAddress $profile) }
    foreach ($name in @('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY')) { $target[$name]=$proxy }
    if ($Key -ne 'Direct') {
        $bypass=@(([string]$Before.NO_PROXY -split ',') | ForEach-Object {$_.Trim()} | Where-Object {$_})
        foreach ($local in @('localhost','127.0.0.1','::1')) { if ($bypass -notcontains $local) { $bypass += $local } }
        $target.NO_PROXY=$bypass -join ','
    }
    [pscustomobject]$target
}
function Save-Backup($Snapshot) {
    [void][IO.Directory]::CreateDirectory($script:BackupDir)
    $path=Join-Path $script:BackupDir ('proxy-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [Guid]::NewGuid().ToString('N').Substring(0,6) + '.json')
    $Snapshot | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $path -Encoding UTF8
    return $path
}
function Test-SameRouting($A,$B) {
    $aText=@{entries=@($A.entries | ForEach-Object {@{path=$_.path;route=$_.route}});defaultRoute=$A.defaultRoute;launchEntries=@($A.launchEntries|Where-Object {$_})}|ConvertTo-Json -Depth 6 -Compress
    $bText=@{entries=@($B.entries | ForEach-Object {@{path=$_.path;route=$_.route}});defaultRoute=$B.defaultRoute;launchEntries=@($B.launchEntries|Where-Object {$_})}|ConvertTo-Json -Depth 6 -Compress
    return $aText -ceq $bText
}
function Set-RoutingSnapshot($Snapshot) {
    $current=Get-RoutingSnapshot
    $hasLaunch=$null -ne $Snapshot.PSObject.Properties['launchEntries']
    if($hasLaunch){Set-ProgramLaunchEntries @($Snapshot.launchEntries)}
    try{
        if($current.installed -or @($current.entries).Count -or $current.defaultRoute -or @($Snapshot.entries).Count -or $Snapshot.defaultRoute){Invoke-AppRouter @{action='replace';entries=@($Snapshot.entries);defaultRoute=$Snapshot.defaultRoute} | Out-Null}
    }catch{if($hasLaunch){Set-ProgramLaunchEntries @($current.launchEntries)};throw}
}
function Invoke-ProxyTransaction($TargetSystem,$TargetEnv,$Selection,$BeforeSystem,$BeforeEnv,$TargetRouting=$null,$BeforeRouting=$null,[scriptblock]$VerifyAction=$null) {
    if(-not (Test-SameSnapshot $BeforeSystem (Get-SystemSnapshot)) -or -not (Test-SameEnv $BeforeEnv (Get-UserProxyEnv))){throw '检测期间其他程序改动了代理，请稍后重试。未写入设置。'}
    if($null -ne $BeforeRouting -and -not (Test-SameRouting $BeforeRouting (Get-RoutingSnapshot))){throw '程序规则被其他窗口改动，请刷新后重试。'}
    $beforeSelection=Get-Selection
    $backup=Save-Backup ([pscustomobject]@{Version=3;Time=(Get-Date).ToString('o');System=$BeforeSystem;Environment=$BeforeEnv;Selection=$beforeSelection;Routing=$BeforeRouting})
    $routesWritten=$false;$nativeStarted=$false;$systemStarted=$false
    try{
        if($null -ne $TargetRouting){Write-OperationProgress '正在更新程序规则并核对引擎…';Set-RoutingSnapshot $TargetRouting;$routesWritten=$true}
        if($VerifyAction){& $VerifyAction | Out-Null}
        # A controller reload can take seconds; recheck before touching Windows settings.
        if(-not (Test-SameSnapshot $BeforeSystem (Get-SystemSnapshot)) -or -not (Test-SameEnv $BeforeEnv (Get-UserProxyEnv))){throw '重载期间系统入口发生变化，请重试。'}
        Write-OperationProgress '正在同步用户代理变量…'
        $nativeStarted=$true;Set-UserProxyEnv $TargetEnv
        if(-not (Test-SameSnapshot $BeforeSystem (Get-SystemSnapshot))){throw '写入变量期间其他程序改动了系统代理。'}
        Write-OperationProgress '正在写入系统入口并实读校验…'
        $systemStarted=$true;Set-SystemSnapshot $TargetSystem
        if(-not (Test-SameSnapshot $TargetSystem (Get-SystemSnapshot)) -or -not (Test-SameEnv $TargetEnv (Get-UserProxyEnv))){throw '写入后校验失败，或其他客户端改写了入口。'}
        Save-Selection $Selection
        Write-OperationProgress '系统入口与变量已核对，正在刷新实际连接…'
    }catch{
        $errorText=$_.Exception.Message;$rollbackErrors=@();$preserved=@()
        if($routesWritten -and $null -ne $BeforeRouting){
            try{if(Test-SameRouting (Get-RoutingSnapshot) $TargetRouting){Set-RoutingSnapshot $BeforeRouting}else{$preserved+='程序规则'}}catch{$rollbackErrors+='程序规则'}
        }
        if($nativeStarted){
            # Restore only values still owned by this transaction; preserve outside choices.
            try{
                $currentEnv=Get-UserProxyEnv;$rollbackEnv=[ordered]@{}
                foreach($name in $script:ProxyNames){
                    if([string]$currentEnv.$name -ceq [string]$TargetEnv.$name){$rollbackEnv[$name]=$BeforeEnv.$name}
                    else{$rollbackEnv[$name]=$currentEnv.$name;if([string]$currentEnv.$name -cne [string]$BeforeEnv.$name){$preserved+='环境变量'}}
                }
                if(-not (Test-SameEnv $currentEnv ([pscustomobject]$rollbackEnv))){Set-UserProxyEnv ([pscustomobject]$rollbackEnv)}
            }catch{$rollbackErrors+='环境变量'}
            if($systemStarted){try{
                $currentSystem=Get-SystemSnapshot
                if(Test-SameSnapshot $currentSystem $TargetSystem){Set-SystemSnapshot $BeforeSystem}
                elseif(-not (Test-SameSnapshot $currentSystem $BeforeSystem)){$preserved+='系统代理'}
            }catch{$rollbackErrors+='系统代理'}}
            elseif(-not (Test-SameSnapshot (Get-SystemSnapshot) $BeforeSystem)){$preserved+='系统代理'}
            try{Save-Selection $beforeSelection}catch{$rollbackErrors+='选择记录'}
        }
        if($rollbackErrors.Count){throw ($errorText+'；回滚未完成：'+($rollbackErrors -join '、')+'。备份：'+$backup)}
        if($preserved.Count){throw ($errorText+'；已撤销本次可回滚的更改，保留其他程序的最新设置：'+(($preserved | Select-Object -Unique) -join '、')+'。')}
        throw ($errorText+'；已恢复切换前配置。')
    }
    return $backup
}

function Use-ChangeLock([scriptblock]$Action) {
    $mutex=New-Object Threading.Mutex($false,('Local\UnifiedProxySwitch-' + $env:USERNAME))
    $held=$false
    try {
        try { $held=$mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $held=$true }
        if (-not $held) { throw '另一个切换器正在修改代理，请稍后重试。' }
        & $Action
    } finally { if ($held) { $mutex.ReleaseMutex() }; $mutex.Dispose() }
}
function Get-UnifiedPlan([string]$Key,$BeforeRouting) {
    if($Key -ne 'Direct' -and $Key -notin (Get-ProfileKeys)){throw '请先添加并选择需要统一使用的代理。'}
    $gateway=Get-GatewayKey;$useEngine=$false
    if($script:Profiles.Routing.Adapter -eq 'standalone' -and $Key -eq $gateway){throw '独立入口用于承载流量，请选择一个上游或直连。'}
    if($gateway){$useEngine=($null -ne (Get-Listener (Get-Profile $gateway)))}
    if($BeforeRouting.installed -and -not $useEngine){throw '已有程序规则需要撤回，但分流引擎未运行。请启动引擎后再统一切换。'}
    $entrance=$Key;$default=$null
    if($script:Profiles.Routing.UnifiedMode -eq 'gateway'){
        if(-not $useEngine){throw '固定入口的分流引擎未运行，保留当前线路。请启动引擎；不会偷偷改用另一端口。'}
        $entrance=$gateway;$default=$Key
    }elseif($Key -ne 'Direct'){
        if($useEngine -and ($Key -eq $gateway -or (Get-Profile $Key).Protocol -ne 'http')){$entrance=$gateway;$default=$Key}
        elseif((Get-Profile $Key).Protocol -ne 'http'){throw 'SOCKS5 统一切换需要本地分流引擎提供 HTTP 入口，请在代理管理设置引擎。'}
    }
    [pscustomobject]@{Entrance=$entrance;NetworkKey=$Key;Routing=[pscustomobject]@{entries=@();defaultRoute=$default;launchEntries=@($BeforeRouting.launchEntries|Where-Object {$_}|ForEach-Object {[pscustomobject]@{path=$_.path;route='Follow';adapter=$_.adapter}})};ClearedRules=(@($BeforeRouting.entries).Count+@($BeforeRouting.launchEntries|Where-Object {$_ -and $_.route -ne 'Follow'}).Count)}
}
function Set-SelectedProxy([string]$Key) {
    Use-ChangeLock {
        $before=Get-SystemSnapshot;$beforeEnv=Get-UserProxyEnv;$beforeRules=Get-RoutingSnapshot
        $plan=Get-UnifiedPlan $Key $beforeRules
        Write-OperationProgress '正在检查目标入口（并行检测，单项最多 5 秒）…'
        $overrides=@(Get-OverrideWarnings $plan.Entrance);if($overrides.Count){throw ($overrides -join "`n")}
        $test=$null
        if($Key -ne 'Direct' -and $Key -ne (Get-GatewayKey)){$test=Test-ProxyRoute $Key -Fast;if(-not $test.Usable){throw '所选代理检测未通过，保留原配置。'}}
        Assert-ClientCompatibility $plan.Entrance ([bool]$plan.Routing.defaultRoute)
        $server='';$flags=1
        if($plan.Entrance -ne 'Direct'){$p=Get-Profile $plan.Entrance;if(-not (Get-Listener $p -ProbeRemote)){throw '所选入口已退出，保留原设置。'};$server=Get-EndpointAddress $p;$flags=3}
        $target=[pscustomobject]@{Flags=$flags;Server=$server;Bypass=$before.Bypass}
        $selection=[pscustomobject]@{Key=$plan.Entrance;NetworkKey=$Key;Unified=$true;ChangedAt=(Get-Date).ToString('o')}
        $rules=$plan.Routing
        if(-not $beforeRules.installed -and -not $rules.defaultRoute -and -not @($beforeRules.launchEntries|Where-Object {$_}).Count){$rules=$null}
        $verify={
            if($Key -ne 'Direct' -and $rules.defaultRoute -and -not (Test-ProxyRoute $plan.Entrance -Fast).Usable){throw '统一线路的实际检测未通过。'}
            if($plan.Entrance -ne 'Direct' -and -not (Get-Listener (Get-Profile $plan.Entrance) -ProbeRemote)){throw '提交前入口已退出，未写入失效端口。'}
        }
        $backup=Invoke-ProxyTransaction $target (New-EnvTarget $beforeEnv $plan.Entrance) $selection $before $beforeEnv $rules $beforeRules $verify
        [pscustomobject]@{Key=$Key;Backup=$backup;Test=$test;Message=('已将新连接的统一线路设为「'+(Get-RouteName $Key)+'」，撤销 '+$plan.ClearedRules+' 条程序专用规则。'+$(if($script:Profiles.Routing.UnifiedMode -eq 'gateway'){'本地入口保持 '+$server+'；旧连接可在程序右键菜单中单独重连。'}else{'系统入口与命令行变量已同步，现有连接需刷新。'}))}
    }
}

function Restore-ProxyBackup {
    Use-ChangeLock {
        $latest=Get-ChildItem -LiteralPath $script:BackupDir -Filter 'proxy-*.json' -ErrorAction SilentlyContinue | Sort-Object Name -Descending | Select-Object -First 1
        if(-not $latest){throw '还没有可恢复的配置备份。'}
        $saved=Get-Content -LiteralPath $latest.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
        if($saved.Version -notin @(2,3) -or -not $saved.System -or -not $saved.Environment){throw '备份格式不兼容，未修改设置。'}
        $key=Get-SystemKey $saved.System
        if($key -in (Get-ProfileKeys) -and -not (Get-Listener (Get-Profile $key) -ProbeRemote)){throw '备份指向的入口未就绪，请先启动它。'}
        if($key -eq 'Other'){throw '备份指向的代理已不在当前列表，请先恢复对应代理配置。'}
        Assert-RestorableEnvironment $saved.Environment
        $routing=$null;$beforeRules=$null
        if($saved.Version -eq 3 -and $null -ne $saved.Routing){$routing=$saved.Routing;$beforeRules=Get-RoutingSnapshot}
        $backup=Invoke-ProxyTransaction $saved.System $saved.Environment $saved.Selection (Get-SystemSnapshot) (Get-UserProxyEnv) $routing $beforeRules
        [pscustomobject]@{Message='已恢复切换前的系统代理、环境变量与已备份的程序规则。现有连接可能需要重开。';Backup=$backup}
    }
}

function Assert-RestorableEnvironment($Values) {
    foreach($name in @('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY')){
        $value=[string]$Values.$name;if(-not $value){continue}
        try{$uri=[uri]$(if($value -match '^[a-z]+://'){$value}else{'http://'+$value})}catch{throw ('备份的 '+$name+' 地址无效，未恢复。')}
        if($uri.Host.Trim('[',']') -in @('localhost','127.0.0.1','::1')){
            $profile=[pscustomobject]@{Host=$uri.Host.Trim('[',']');Port=$uri.Port;CorePath=''}
            if(-not (Get-Listener $profile)){throw ('备份的 '+$name+' 指向未监听的本地端口 '+$uri.Port+'，未恢复任何设置。')}
        }
    }
}



. (Join-Path $PSScriptRoot 'AppRouting.ps1')

