$script:AppRouterRoot=$PSScriptRoot
function Invoke-AppRouter($Request,[int]$TimeoutMilliseconds=55000) {
    $psi=New-Object Diagnostics.ProcessStartInfo
    $psi.FileName=Get-NodeRuntimePath
    $psi.Arguments='"' + (Join-Path $script:AppRouterRoot 'AppRouter.cjs') + '"'
    $psi.UseShellExecute=$false;$psi.CreateNoWindow=$true
    $psi.EnvironmentVariables['PROXY_SWITCH_DATA_DIR']=$script:DataRoot
    $psi.EnvironmentVariables.Remove('NODE_OPTIONS');$psi.EnvironmentVariables.Remove('NODE_PATH')
    $psi.EnvironmentVariables['PROXY_SWITCH_PROFILES']=($script:Profiles | ConvertTo-Json -Depth 5 -Compress)
    $psi.RedirectStandardInput=$true;$psi.RedirectStandardOutput=$true;$psi.RedirectStandardError=$true
    $psi.StandardOutputEncoding=New-Object Text.UTF8Encoding($false)
    $proc=New-Object Diagnostics.Process;$proc.StartInfo=$psi
    try{
        [void]$proc.Start()
        $outTask=$proc.StandardOutput.ReadToEndAsync();$errTask=$proc.StandardError.ReadToEndAsync()
        $inputBytes=[Text.Encoding]::UTF8.GetBytes(($Request | ConvertTo-Json -Depth 5 -Compress))
        $proc.StandardInput.BaseStream.Write($inputBytes,0,$inputBytes.Length);$proc.StandardInput.BaseStream.Flush();$proc.StandardInput.Close()
        if(-not $proc.WaitForExit($TimeoutMilliseconds)){
            # Do not kill a writer in the middle of rollback. Read-only requests are safe to stop.
            if($Request.action -eq 'status'){$proc.Kill()}
            throw '程序规则操作超时，请等待后台操作完成后刷新，勿重复切换。'
        }
        try{$result=$outTask.Result | ConvertFrom-Json}catch{throw '程序规则引擎返回异常，请检查 Node.js 与 vendor 文件是否齐全。'}
        if($proc.ExitCode -ne 0 -or ($result.PSObject.Properties['ok'] -and -not $result.ok)){
            if($result.error){throw $result.error};throw '程序规则操作未完成。'
        }
        return $result
    }finally{$proc.Dispose()}
}

function Set-ApplicationRoute([string]$Executable,[string]$Route) {
    Use-ChangeLock {
        if($script:Profiles.Routing.Adapter -eq 'standalone' -and $Route -eq (Get-GatewayKey)){throw '请选择上游代理，不能把独立入口作为自己的出口。'}
        if($Route -notin (@('Direct','Follow')+(Get-ProfileKeys))){throw '所选代理已不在列表中，请刷新。'}
        if(-not [IO.Path]::IsPathRooted($Executable) -or $Executable -notmatch '(?i)\.exe$' -or $Executable -match '[,\r\n\x00]'){throw '请选择有效 EXE 路径。'}
        if($Route -ne 'Follow' -and -not (Test-Path -LiteralPath $Executable -PathType Leaf)){throw '程序已不存在，请重新添加。'}
        foreach($p in $script:Profiles.Profiles){if($Executable -ieq $p.CorePath -or $Executable -ieq $p.AppPath){throw '不能给代理程序自身分流，以免形成回路。'}}
        $gateway=Get-GatewayKey
        if(-not $gateway -or -not (Get-Listener (Get-Profile $gateway))){throw '尚未接入分流引擎，不能接管此程序。请在「代理管理」编辑引擎入口并启用固定入口模式；本次没有保存假规则或创建启动图标。'}
        Assert-ClientCompatibility $gateway ($true)
        if($Route -notin @('Direct','Follow') -and -not (Get-Listener (Get-Profile $Route) -ProbeRemote)){throw '所选代理入口未就绪，请先连接后再设置程序线路。'}
        $before=Get-SystemSnapshot;$beforeEnv=Get-UserProxyEnv;$rules=Get-RoutingSnapshot
        $default=$rules.defaultRoute;$beforeKey=Get-SystemKey $before
        if(-not $default -and $beforeKey -ne $gateway){
            if($beforeKey -ne 'Direct' -and $beforeKey -notin (Get-ProfileKeys)){throw '当前系统入口未知，请先统一切换到已配置的线路。'}
            $default=$beforeKey
        }
        $entries=@($rules.entries | Where-Object {$_.path -ine $Executable})
        if($Route -ne 'Follow'){$entries+=[pscustomobject]@{path=$Executable;route=$Route}}
        # Legacy launchers may remain for compatibility, but no longer override this engine rule.
        $launchEntries=@($rules.launchEntries | ForEach-Object {if($_.path -ieq $Executable){[pscustomobject]@{path=$_.path;route='Follow';adapter=$_.adapter}}else{$_}})
        $targetRules=[pscustomobject]@{entries=$entries;defaultRoute=$default;launchEntries=$launchEntries}
        $p=Get-Profile $gateway;$target=[pscustomobject]@{Flags=3;Server=(Get-EndpointAddress $p);Bypass=$before.Bypass}
        $selection=[pscustomobject]@{Key=$gateway;NetworkKey=$(if($default){$default}else{$gateway});Unified=($entries.Count -eq 0 -and [bool]$default);ChangedAt=(Get-Date).ToString('o')}
        $backup=Invoke-ProxyTransaction $target (New-EnvTarget $beforeEnv $gateway) $selection $before $beforeEnv $targetRules $rules
        [pscustomobject]@{Backup=$backup;Message=('「'+[IO.Path]::GetFileNameWithoutExtension($Executable)+'」的引擎规则已载入：'+(Get-RouteName $Route)+'。继续使用原来的软件入口；经过分流引擎的新连接按此规则选择出口。旧连接可右键单独重连，未经过引擎的连接会显示未接管。')}
    }
}
function Sync-ApplicationRoutes {Use-ChangeLock {Invoke-AppRouter @{action='sync'}}}
function Get-ApplicationReconnectPlan([string]$Executable) {Invoke-AppRouter @{action='reconnect-plan';path=$Executable}}
function Invoke-ApplicationReconnect($Plan) {Use-ChangeLock {Invoke-AppRouter @{action='reconnect';plan=$Plan}}}
function Find-EngineConnection($Candidates,[string]$ProcessPath) {
    if(-not $ProcessPath){return $null}
    $matches=@($Candidates | Where-Object {$_.path -and $_.path -ieq $ProcessPath -and $_.network -ieq 'tcp'})
    if($matches.Count -eq 1){return $matches[0]}
    return $null
}
function Get-ApplicationRoutes($TcpRows=$null) {
    try{$core=Invoke-AppRouter @{action='status'}}catch{
        $saved=Get-RoutingSnapshot
        $core=[pscustomobject]@{available=$false;error=$_.Exception.Message;entries=@($saved.entries | ForEach-Object {[pscustomobject]@{path=$_.path;route=$_.route;loaded=$false}});connections=@();defaultRoute=$saved.defaultRoute;defaultLoaded=$false}
    }
    $processes=@(Get-ProcessInventory);$byId=@{};$apps=@{};$clientPaths=@($script:Profiles.Profiles | ForEach-Object {$_.CorePath;$_.AppPath} | Where-Object {$_})
    foreach($p in $processes){
        if($p.Path -in $clientPaths -or $p.ProcessName -in @('powershell','pwsh','System','Registry','Idle')){continue}
        $byId[[int]$p.Id]=$p
        if($p.MainWindowHandle -ne [IntPtr]::Zero){
            $appKey=Get-ProcessRowKey $p
            $apps[$appKey]=[pscustomobject]@{Path=[string]$p.Path;Name=$p.ProcessName;PID=[int]$p.Id}
        }
    }
    if($null -eq $TcpRows){$tcp=@(Get-NetTCPConnection -State Established,SynSent -ErrorAction SilentlyContinue)}else{$tcp=@($TcpRows|Where-Object {$_.State -in @('Established','SynSent')})};$entrances=@{}
    foreach($c in $tcp){
        $entrance=Get-ConnectionProfile $c;$entrances[[int]$c.LocalPort]= $entrance
        $p=$byId[[int]$c.OwningProcess]
        if($p -and $entrance){$apps[(Get-ProcessRowKey $p)]=[pscustomobject]@{Path=[string]$p.Path;Name=$p.ProcessName;PID=[int]$p.Id}}
    }
    foreach($rule in $core.entries){$apps[$rule.path.ToLowerInvariant()]=[pscustomobject]@{Path=$rule.path;Name=[IO.Path]::GetFileNameWithoutExtension($rule.path)}}
    $corePorts=@{};foreach($c in $core.connections){$port=[int]$c.sourcePort;$corePorts[$port]=@($corePorts[$port])+@($c)}
    $gateway=Get-GatewayKey;$rows=@();$launchEntries=@(Get-ProgramLaunchEntries)
    foreach($entry in $launchEntries){$apps[$entry.path.ToLowerInvariant()]=[pscustomobject]@{Path=$entry.path;Name=[IO.Path]::GetFileNameWithoutExtension($entry.path)}}
    # Fold private helper processes into the visible app unless they have their own explicit rule.
    foreach($primary in @($apps.Values)){
        if(-not $primary.Path -or -not @($processes|Where-Object {$_.Path -ieq $primary.Path -and $_.MainWindowHandle -ne [IntPtr]::Zero}).Count){continue}
        foreach($member in @(Get-ProgramFamily $primary.Path $processes)){
            if(-not $member.Path -or $member.Path -ieq $primary.Path){continue}
            if(@($core.entries|Where-Object {$_.path -ieq $member.Path}).Count -or @($launchEntries|Where-Object {$_.path -ieq $member.Path}).Count){continue}
            $apps.Remove($member.Path.ToLowerInvariant())
        }
    }
    foreach($app in $apps.Values){
        $family=@();if($app.Path){$family=@(Get-ProgramFamily $app.Path $processes)}
        $ids=@($family|ForEach-Object Id);if(-not $app.Path){$ids=@($app.PID)}
        $childNames=@($family|Where-Object {$_.Path -ine $app.Path}|ForEach-Object ProcessName|Select-Object -Unique)
        $counts=@{};$outside=0;$unknown=0;$pending=@{};$outsidePending=0;$childPending=0;$childProxyObserved=0
        foreach($c in $tcp){
            if($ids -notcontains [int]$c.OwningProcess){continue}
            $entrance=$entrances[[int]$c.LocalPort];$route=$null
            $engineConnection=Find-EngineConnection $corePorts[[int]$c.LocalPort] ([string]$byId[[int]$c.OwningProcess].Path)
            if([string]$c.State -eq 'SynSent'){
                if($entrance){$endpoint=$c.RemoteAddress+':'+$c.RemotePort;if(-not $pending.ContainsKey($endpoint)){$pending[$endpoint]=0};$pending[$endpoint]++}
                else{$outsidePending++;if($c.OwningProcess -in @($family|Where-Object {$_.Path -ine $app.Path}|ForEach-Object Id)){$childPending++}}
                continue
            }
            if($entrance){
                if($entrance -eq $gateway){if($engineConnection){$route=$engineConnection.route}else{$unknown++}}
                else{$route=$entrance}
            }elseif($engineConnection -and $engineConnection.inbound -ieq 'Tun'){$route=$engineConnection.route}
            elseif($c.RemoteAddress -notin @('127.0.0.1','::1','::ffff:127.0.0.1')){$outside++}
            if($route){if($c.OwningProcess -in @($family|Where-Object {$_.Path -ine $app.Path}|ForEach-Object Id)){$childProxyObserved++};if(-not $counts.ContainsKey($route)){$counts[$route]=0};$counts[$route]++}
        }
        $rule=$core.entries | Where-Object {$_.path -ieq $app.Path} | Select-Object -First 1
        $policy='Follow';$loaded=$false;if($rule){$policy=$rule.route;$loaded=[bool]$rule.loaded}
        $launch=$launchEntries|Where-Object {$_.path -ieq $app.Path}|Select-Object -First 1
        if($rule -or ($script:Profiles.Routing.UnifiedMode -eq 'gateway' -and $launch.route -eq 'Follow')){$launch=$null}
        if($launch){$policy=$launch.route}
        $actual=@();foreach($route in @('Direct')+(Get-ProfileKeys)+@('Blocked','Unknown')){if($counts.ContainsKey($route)){$actual+=((Get-RouteName $route)+' ×'+$counts[$route])}}
        if($unknown){$actual+='引擎入口 / 出口待确认'};if($outside){$actual+='入口外连接 ×'+$outside};if(-not $actual.Count){$actual=@('暂无连接')}
        foreach($endpoint in $pending.Keys){$actual+=('连接中 / SynSent '+$endpoint+' ×'+$pending[$endpoint])}
        if($pending.Count){$actual=@($actual | Where-Object {$_ -ne '暂无连接'})}
        if($outsidePending){$actual=@($actual|Where-Object {$_ -ne '暂无连接'})+@('入口外连接失败 / SynSent ×'+$outsidePending)}
        $observedPolicy=$policy;if($rule.effectiveRoute){$observedPolicy=$rule.effectiveRoute}
        $status='未单独指定 · 仅观察实际连接'
        if($policy -ne 'Follow'){$status=$(if($loaded){'已加载；新连接生效'}else{'尚未加载；请重载规则'});if($loaded -and (@($counts.Keys | Where-Object {$_ -ne $observedPolicy}).Count -or $outside)){$status='已加载；存在旧连接或独立入口'}}
        $mode='observe';if($rule){$mode='engine'}
        if($rule -and $loaded){
            $observedPolicy=$policy;if($rule.effectiveRoute){$observedPolicy=$rule.effectiveRoute}
            $loaded=$false;$status='规则已载入；等待实际连接'
            if($outside -or $unknown -or $pending.Count -or $outsidePending){$status='规则已载入；存在未接管或失败连接'}
            elseif(@($counts.Keys | Where-Object {$_ -ne $observedPolicy}).Count){$status='规则已载入；仍有旧线路连接，可右键重连'}
            elseif($counts.ContainsKey($observedPolicy)){$loaded=$true;$status='已观察到指定线路连接';if($observedPolicy -ne $policy){$status='已自动接替到 '+(Get-RouteName $observedPolicy)}}
        }
        if($launch){
            $mode='launch';$session=Test-ManagedProgramSession $app.Path $processes $policy
            $loaded=$false;$status='目标已保存；请使用代理启动入口'
            if($ids.Count){$status='未确认使用代理入口；当前连接见左栏'}
            if($session){
                $wanted=$policy;if($wanted -eq 'Follow'){$wanted=Get-SystemKey (Get-SystemSnapshot)}
                $status='已按目标启动；等待连接验证'
                if($counts.ContainsKey($wanted) -and -not $outsidePending -and -not $pending.Count -and -not $outside -and -not @($counts.Keys|Where-Object {$_ -ne $wanted}).Count){$loaded=$true;$status='已观察到目标代理连接';if($childNames.Count -and -not $childProxyObserved){$loaded=$false;$status='主程序已通过代理；子进程连接待验证'}elseif($childProxyObserved){$status+='（含子进程）'}}
                elseif($outsidePending -or $outside -or $pending.Count){$status='已按目标启动；仍有绕过或失败连接'}
            }
        }
        if($childPending){$status+=' · 联网子进程未通过代理建立连接'}
        if(-not $app.Path){$status+=' · 路径不可读，仅观察'}
        elseif(-not (Test-Path -LiteralPath $app.Path)){$status='路径已失效，请移除后重新添加'}elseif(-not $ids.Count -and $policy -ne 'Follow'){$status+=' · 未运行'}
        if($pending.Count){$status='代理连接尚未建立；请检查目标端口 · '+$status}
        $policyName=Get-RouteName $policy;if($mode -eq 'observe'){$policyName='未单独指定'}
        $rows+=[pscustomobject]@{Name=$app.Name;Path=$app.Path;Policy=$policy;PolicyName=$policyName;Mode=$mode;Loaded=$loaded;Actual=($actual -join '，');Status=$status;PIDs=($ids -join ',');ChildNames=($childNames -join '、');OutsidePending=$outsidePending;CanLaunch=($mode -eq 'launch' -and $script:Profiles.Routing.UnifiedMode -ne 'gateway')}
    }
    [pscustomobject]@{Available=[bool]$core.available;Error=$core.error;Mode=$core.mode;Rows=@($rows | Sort-Object @{Expression={if($_.Policy -ne 'Follow'){0}else{1}}},Name);RuleCount=(@($core.entries).Count+@($launchEntries|Where-Object {$_.route -ne 'Follow'}).Count);LaunchRuleCount=@($launchEntries|Where-Object {$_.route -ne 'Follow'}).Count;DefaultRoute=$core.defaultRoute;EffectiveDefaultRoute=$core.effectiveDefaultRoute;Failover=$core.failover;DefaultLoaded=[bool]$core.defaultLoaded;GatewayKey=$gateway}
}

function Get-ProcessRowKey($Process) {
    if($Process.Path){return $Process.Path.ToLowerInvariant()}
    return 'pid:'+[string]$Process.Id
}

function Enable-LocalGateway {
    Use-ChangeLock {
        $script:Profiles=Read-ProfileSettings
        $before=$script:Profiles
        $clients=@(Get-ProcessInventory | Where-Object {$_.ProcessName -eq 'clash-verge' -and $_.Path})
        $cores=@($clients | ForEach-Object {Join-Path ([IO.Path]::GetDirectoryName($_.Path)) 'verge-mihomo.exe'} | Where-Object {Test-Path -LiteralPath $_ -PathType Leaf} | Select-Object -Unique)
        if($cores.Count -ne 1){throw '未找到唯一的本机 Clash Verge 内核。请先启动 Clash，或编辑入口手动填写本机内核路径。'}
        $core=$cores[0];$clientPath=$clients[0].Path
        $verge=Join-Path $env:APPDATA 'io.github.clash-verge-rev.clash-verge-rev\verge.yaml'
        if(-not (Test-Path -LiteralPath $verge)){throw '未找到本机 Clash Verge 配置。'}
        $portMatch=[regex]::Match([IO.File]::ReadAllText($verge),'(?m)^verge_mixed_port:\s*(\d+)\s*$')
        if(-not $portMatch.Success){throw '无法读取本机混合端口，请编辑代理入口手动配置。'}
        $port=[int]$portMatch.Groups[1].Value
        $value=$before | ConvertTo-Json -Depth 8 | ConvertFrom-Json
        $entry=$value.Profiles | Where-Object {$_.Host -in @('localhost','127.0.0.1','::1') -and $_.Port -eq $port} | Select-Object -First 1
        if(-not $entry){
            $entry=[pscustomobject]@{Id=('p'+[Guid]::NewGuid().ToString('N').Substring(0,12));Name=('本机分流引擎 :'+$port);Host='127.0.0.1';Port=$port;Protocol='http';AppPath=$clientPath;CorePath=$core;AutoPort=$true}
            $value.Profiles+=@($entry)
        }
        $entry.Protocol='http';$entry.CorePath=$core;$entry.AppPath=$clientPath;$entry.AutoPort=$true
        $value.Routing=[pscustomobject]@{Adapter='clash-verge';ProfileId=$entry.Id;UnifiedMode='gateway'}
        try{
            $script:Profiles=ConvertTo-ValidProfileSettings $value
            if(-not (Get-Listener (Get-Profile $entry.Id))){throw '本机分流入口未运行，请先启动 Clash。'}
            $live=Invoke-AppRouter @{action='status'}
            if(-not $live.available){throw ('本机分流引擎检查失败：'+$live.error)}
            if($live.mode -ne 'rule'){throw '请先在 Clash 切换到规则模式，再配置分流引擎。'}
        }finally{$script:Profiles=$before}
        Save-ProfileSettings $value
        [pscustomobject]@{Message='本机固定入口已配置并检查。请在顶部选择目标后统一切换；Clash 承载分流入口，需保持运行。仅保存设置尚未改变网络。'}
    }
}
