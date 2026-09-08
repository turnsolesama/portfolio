$ErrorActionPreference = 'Stop'
$script:Root = $PSScriptRoot
. (Join-Path $PSScriptRoot 'Preferences.ps1')
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
    if($Key -eq (Get-GatewayKey) -and $source.AutoPort){
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
        [Environment]::SetEnvironmentVariable($name,$value,'User')
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
function Get-Listener($Profile) {
    if($Profile.Host -in @('localhost','127.0.0.1','::1')){
        $entries=@(Get-NetTCPConnection -State Listen -LocalPort $Profile.Port -ErrorAction SilentlyContinue | Where-Object {$_.LocalAddress -in @('127.0.0.1','0.0.0.0','::','::1')})
        foreach($entry in $entries){
            $owner=Get-Process -Id $entry.OwningProcess -ErrorAction SilentlyContinue
            if($owner -and (-not $Profile.CorePath -or $owner.Path -ieq $Profile.CorePath)){return [pscustomobject]@{PID=$owner.Id;Name=$owner.ProcessName}}
        }
    }else{
        $tcp=New-Object Net.Sockets.TcpClient
        try{$connect=$tcp.BeginConnect($Profile.Host,$Profile.Port,$null,$null);if($connect.AsyncWaitHandle.WaitOne(800)){$tcp.EndConnect($connect);return [pscustomobject]@{PID=0;Name='TCP'}}}catch{}finally{$tcp.Close()}
    }
    return $null
}

function Get-ClientWarnings {
    $path = Join-Path $env:APPDATA 'io.github.clash-verge-rev.clash-verge-rev\verge.yaml'
    if (Test-Path -LiteralPath $path) {
        if (Select-String -LiteralPath $path -Pattern '^enable_system_proxy:\s*true\s*$' -Quiet) { 'Clash 开着系统代理；启动它可能覆盖选择，启动客户端后请在这里重新应用。' }
        if (Select-String -LiteralPath $path -Pattern '^(enable_tun_mode|enable_proxy_guard):\s*true\s*$' -Quiet) { 'Clash 的 TUN 或代理守卫已开启，可能覆盖手动选择。' }
    }
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
function Get-LiveConnections {
    $processes=@{};Get-Process | ForEach-Object {$processes[[int]$_.Id]=$_.ProcessName}
    $items=@();$tcp=@(Get-NetTCPConnection -State Established -ErrorAction SilentlyContinue)
    foreach($c in $tcp){$route=Get-ConnectionProfile $c;if($route){$items+=[pscustomobject]@{PID=[int]$c.OwningProcess;Route=$route}}}
    foreach($group in ($items | Group-Object PID,Route)){$c=$group.Group[0];[pscustomobject]@{Process=$processes[$c.PID];PID=$c.PID;Route=$c.Route;Count=$group.Count}}
}

function Get-ProxyStatus {
    $snapshot=Get-SystemSnapshot;$key=Get-SystemKey $snapshot;$envValues=Get-UserProxyEnv;$selection=Get-Selection
    $aligned=($key -ne 'Other');$envConflict=($key -eq 'Other');$environment=@()
    foreach($name in @('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY')){
        $route=Get-EndpointKey $envValues.$name
        $environment+=[pscustomobject]@{Name=$name;Value=(Protect-Endpoint $envValues.$name);Route=$route}
        if(($key -eq 'Direct' -and $route -ne 'Unset') -or ($key -ne 'Direct' -and $route -ne $key)){$aligned=$false}
        if($route -ne 'Unset' -and $route -ne $key){$envConflict=$true}
    }
    $listeners=@();foreach($id in (Get-ProfileKeys)){$p=Get-Profile $id;$l=Get-Listener $p;$listeners+=[pscustomobject]@{Key=$id;Name=$p.Name;Protocol=$p.Protocol;Port=$p.Port;Ready=($null -ne $l)}}
    $ready=($key -eq 'Direct' -or @($listeners | Where-Object {$_.Key -eq $key -and $_.Ready}).Count -gt 0)
    $live=@(Get-LiveConnections);$warnings=@(Get-ClientWarnings)+@(Get-OverrideWarnings $key)
    $drift=($null -ne $selection -and $selection.Key -and $selection.Key -ne $key)
    $oldConnections=@($live | Where-Object {$_.Route -ne $key})
    $network=$key;if($selection.NetworkKey -and -not $drift){$network=$selection.NetworkKey}
    [pscustomobject]@{Key=$key;Current=(Get-RouteName $key);NetworkKey=$network;NetworkName=(Get-RouteName $network);Server=(Protect-Endpoint $snapshot.Server);Flags=$snapshot.Flags;Environment=$environment;Aligned=$aligned;EnvConflict=$envConflict;EndpointReady=$ready;Listeners=$listeners;Selected=$selection;Drift=[bool]$drift;Connections=$live;OldConnections=$oldConnections;Warnings=$warnings;GatewayKey=(Get-GatewayKey);CheckedAt=(Get-Date).ToString('HH:mm:ss')}
}

function Test-HttpEndpoint($Profile,[string]$Url) {
    $psi=New-Object Diagnostics.ProcessStartInfo
    $psi.FileName=(Get-Command curl.exe -ErrorAction Stop).Source
    # Validated protocol/host/port and fixed HTTPS URLs only. No credentials or shell.
    $psi.Arguments='--silent --show-error --head --output NUL --connect-timeout 6 --max-time 10 --proxy '+$(if($Profile.Protocol -eq 'socks5'){'socks5h://'}else{'http://'})+(Get-EndpointAddress $Profile)+' --noproxy "" --write-out "%{http_code} %{time_total} %{http_connect}" ' + $Url
    $psi.UseShellExecute=$false; $psi.CreateNoWindow=$true
    $psi.RedirectStandardOutput=$true; $psi.RedirectStandardError=$true
    $process=New-Object Diagnostics.Process; $process.StartInfo=$psi
    try {
        [void]$process.Start()
        $outTask=$process.StandardOutput.ReadToEndAsync(); $errTask=$process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(12000)) { $process.Kill(); throw '检测进程超时。' }
        $raw=$outTask.Result.Trim(); $fields=$raw -split '\s+'
        $code=0; $seconds=0.0
        if ($fields.Count -ge 2) {
            [void][int]::TryParse($fields[0],[ref]$code)
            [void][double]::TryParse($fields[1],[Globalization.NumberStyles]::Float,[Globalization.CultureInfo]::InvariantCulture,[ref]$seconds)
        }
        $reachable=($process.ExitCode -eq 0 -and $code -gt 0)
        $accepted=$reachable -and (($code -ge 200 -and $code -lt 400) -or ($Url -eq 'https://api.openai.com/v1/models' -and $code -eq 401))
        $note='无法连接 / 超时'
        if ($reachable) {
            $note='HTTP ' + $code
            if ($code -eq 401) { $note+='；已到达接口，未携带登录凭据' }
            if ($code -eq 403) { $note+='；站点拒绝或验证，不能据此确认网页可用' }
        }
        [pscustomobject]@{Site=([uri]$Url).Host;Code=$code;Seconds=$seconds;Reachable=$reachable;Accepted=$accepted;Note=$note}
    } finally { $process.Dispose() }
}
function Test-ProxyRoute([string]$Key) {
    $profile=Get-Profile $Key
    if (-not (Get-Listener $profile)) { throw ($profile.Name + ' 入口未就绪，请启动关联程序或检查地址与端口。未修改代理。') }
    $results=@()
    foreach ($url in @('https://www.google.com/generate_204','https://api.openai.com/v1/models','https://chatgpt.com/')) {
        $results += Test-HttpEndpoint $profile $url
    }
    [pscustomobject]@{Key=$Key;Name=$profile.Name;Ready=$true;Usable=(@($results | Where-Object Accepted).Count -gt 0);Results=$results}
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
    $aText=@{entries=@($A.entries | ForEach-Object {@{path=$_.path;route=$_.route}});defaultRoute=$A.defaultRoute}|ConvertTo-Json -Depth 6 -Compress
    $bText=@{entries=@($B.entries | ForEach-Object {@{path=$_.path;route=$_.route}});defaultRoute=$B.defaultRoute}|ConvertTo-Json -Depth 6 -Compress
    return $aText -ceq $bText
}
function Set-RoutingSnapshot($Snapshot) {
    $current=Get-RoutingSnapshot
    if(-not $current.installed -and -not @($current.entries).Count -and -not $current.defaultRoute -and -not @($Snapshot.entries).Count -and -not $Snapshot.defaultRoute){return}
    Invoke-AppRouter @{action='replace';entries=@($Snapshot.entries);defaultRoute=$Snapshot.defaultRoute} | Out-Null
}
function Invoke-ProxyTransaction($TargetSystem,$TargetEnv,$Selection,$BeforeSystem,$BeforeEnv,$TargetRouting=$null,$BeforeRouting=$null,[scriptblock]$VerifyAction=$null) {
    if(-not (Test-SameSnapshot $BeforeSystem (Get-SystemSnapshot)) -or -not (Test-SameEnv $BeforeEnv (Get-UserProxyEnv))){throw '检测期间其他程序改动了代理，请稍后重试。未写入设置。'}
    if($null -ne $BeforeRouting -and -not (Test-SameRouting $BeforeRouting (Get-RoutingSnapshot))){throw '程序规则被其他窗口改动，请刷新后重试。'}
    $beforeSelection=Get-Selection
    $backup=Save-Backup ([pscustomobject]@{Version=3;Time=(Get-Date).ToString('o');System=$BeforeSystem;Environment=$BeforeEnv;Selection=$beforeSelection;Routing=$BeforeRouting})
    $routesWritten=$false;$nativeStarted=$false
    try{
        if($null -ne $TargetRouting){Set-RoutingSnapshot $TargetRouting;$routesWritten=$true}
        if($VerifyAction){& $VerifyAction | Out-Null}
        # A controller reload can take seconds; recheck before touching Windows settings.
        if(-not (Test-SameSnapshot $BeforeSystem (Get-SystemSnapshot)) -or -not (Test-SameEnv $BeforeEnv (Get-UserProxyEnv))){throw '重载期间系统入口发生变化，请重试。'}
        $nativeStarted=$true;Set-UserProxyEnv $TargetEnv;Set-SystemSnapshot $TargetSystem
        if(-not (Test-SameSnapshot $TargetSystem (Get-SystemSnapshot)) -or -not (Test-SameEnv $TargetEnv (Get-UserProxyEnv))){throw '写入后校验失败，或其他客户端改写了入口。'}
        Save-Selection $Selection
    }catch{
        $errorText=$_.Exception.Message;$rollbackErrors=@()
        if($routesWritten -and $null -ne $BeforeRouting){try{Set-RoutingSnapshot $BeforeRouting}catch{$rollbackErrors+='程序规则'}}
        if($nativeStarted){
            try{Set-UserProxyEnv $BeforeEnv}catch{$rollbackErrors+='环境变量'}
            try{Set-SystemSnapshot $BeforeSystem}catch{$rollbackErrors+='系统代理'}
            try{Save-Selection $beforeSelection}catch{$rollbackErrors+='选择记录'}
        }
        if($rollbackErrors.Count){throw ($errorText+'；回滚未完成：'+($rollbackErrors -join '、')+'。备份：'+$backup)}
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
    if($gateway){$useEngine=($null -ne (Get-Listener (Get-Profile $gateway)))}
    if($BeforeRouting.installed -and -not $useEngine){throw '已有程序规则需要撤回，但分流引擎未运行。请启动引擎后再统一切换。'}
    $entrance=$Key;$default=$null
    if($Key -ne 'Direct'){
        if($useEngine){$entrance=$gateway;$default=$Key}
        elseif((Get-Profile $Key).Protocol -ne 'http'){throw 'SOCKS5 统一切换需要本地分流引擎提供 HTTP 入口，请在代理管理设置引擎。'}
    }
    [pscustomobject]@{Entrance=$entrance;NetworkKey=$Key;Routing=[pscustomobject]@{entries=@();defaultRoute=$default};ClearedRules=@($BeforeRouting.entries).Count}
}
function Set-SelectedProxy([string]$Key) {
    Use-ChangeLock {
        $before=Get-SystemSnapshot;$beforeEnv=Get-UserProxyEnv;$beforeRules=Get-RoutingSnapshot
        $plan=Get-UnifiedPlan $Key $beforeRules
        $overrides=@(Get-OverrideWarnings $plan.Entrance);if($overrides.Count){throw ($overrides -join "`n")}
        $test=$null
        if($Key -ne 'Direct' -and $Key -ne (Get-GatewayKey)){$test=Test-ProxyRoute $Key;if(-not $test.Usable){throw '所选代理检测未通过，保留原配置。'}}
        $verge=Join-Path $env:APPDATA 'io.github.clash-verge-rev.clash-verge-rev\verge.yaml'
        if((Get-Process -Name 'clash-verge','verge-mihomo' -ErrorAction SilentlyContinue) -and (Test-Path -LiteralPath $verge)){
            if(Select-String -LiteralPath $verge -Pattern '^(enable_tun_mode|enable_proxy_guard):\s*true\s*$' -Quiet){throw '请先关闭正在运行的分流引擎的 TUN / 代理守卫，再统一切换。'}
        }
        $server='';$flags=1
        if($plan.Entrance -ne 'Direct'){$p=Get-Profile $plan.Entrance;if(-not (Get-Listener $p)){throw '所选入口已退出，保留原设置。'};$server=Get-EndpointAddress $p;$flags=3}
        $target=[pscustomobject]@{Flags=$flags;Server=$server;Bypass=$before.Bypass}
        $selection=[pscustomobject]@{Key=$plan.Entrance;NetworkKey=$Key;Unified=$true;ChangedAt=(Get-Date).ToString('o')}
        $rules=$plan.Routing
        if(-not $beforeRules.installed -and -not $rules.defaultRoute){$rules=$null}
        $verify=$null
        if($rules.defaultRoute){$verify={if(-not (Test-ProxyRoute $plan.Entrance).Usable){throw '统一线路的实际检测未通过。'}}}
        $backup=Invoke-ProxyTransaction $target (New-EnvTarget $beforeEnv $plan.Entrance) $selection $before $beforeEnv $rules $beforeRules $verify
        [pscustomobject]@{Key=$Key;Backup=$backup;Test=$test;Message=('已统一切换到「'+(Get-RouteName $Key)+'」，同步系统代理与命令行变量，撤销 '+$plan.ClearedRules+' 条程序专用规则。现有连接需刷新或重开程序。')}
    }
}

function Restore-ProxyBackup {
    Use-ChangeLock {
        $latest=Get-ChildItem -LiteralPath $script:BackupDir -Filter 'proxy-*.json' -ErrorAction SilentlyContinue | Sort-Object Name -Descending | Select-Object -First 1
        if(-not $latest){throw '还没有可恢复的配置备份。'}
        $saved=Get-Content -LiteralPath $latest.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
        if($saved.Version -notin @(2,3) -or -not $saved.System -or -not $saved.Environment){throw '备份格式不兼容，未修改设置。'}
        $key=Get-SystemKey $saved.System
        if($key -in (Get-ProfileKeys) -and -not (Get-Listener (Get-Profile $key))){throw '备份指向的入口未就绪，请先启动它。'}
        if($key -eq 'Other'){throw '备份指向的代理已不在当前列表，请先恢复对应代理配置。'}
        $routing=$null;$beforeRules=$null
        if($saved.Version -eq 3 -and $null -ne $saved.Routing){$routing=$saved.Routing;$beforeRules=Get-RoutingSnapshot}
        $backup=Invoke-ProxyTransaction $saved.System $saved.Environment $saved.Selection (Get-SystemSnapshot) (Get-UserProxyEnv) $routing $beforeRules
        [pscustomobject]@{Message='已恢复切换前的系统代理、环境变量与已备份的程序规则。现有连接可能需要重开。';Backup=$backup}
    }
}



. (Join-Path $PSScriptRoot 'AppRouting.ps1')

