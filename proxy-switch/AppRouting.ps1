$script:AppRouterRoot=$PSScriptRoot
function Invoke-AppRouter($Request) {
    $psi=New-Object Diagnostics.ProcessStartInfo
    $node=Get-Command node.exe -ErrorAction SilentlyContinue
    if(-not $node){throw '找不到已安装的 Node.js，无法管理程序规则。'}
    $psi.FileName=$node.Source
    $psi.Arguments='"' + (Join-Path $script:AppRouterRoot 'AppRouter.cjs') + '"'
    $psi.UseShellExecute=$false;$psi.CreateNoWindow=$true
    $psi.EnvironmentVariables['PROXY_SWITCH_DATA_DIR']=$script:DataRoot
    $psi.EnvironmentVariables['PROXY_SWITCH_PROFILES']=($script:Profiles | ConvertTo-Json -Depth 5 -Compress)
    $psi.RedirectStandardInput=$true;$psi.RedirectStandardOutput=$true;$psi.RedirectStandardError=$true
    $psi.StandardOutputEncoding=New-Object Text.UTF8Encoding($false)
    $proc=New-Object Diagnostics.Process;$proc.StartInfo=$psi
    try{
        [void]$proc.Start()
        $outTask=$proc.StandardOutput.ReadToEndAsync();$errTask=$proc.StandardError.ReadToEndAsync()
        $inputBytes=[Text.Encoding]::UTF8.GetBytes(($Request | ConvertTo-Json -Depth 5 -Compress))
        $proc.StandardInput.BaseStream.Write($inputBytes,0,$inputBytes.Length);$proc.StandardInput.BaseStream.Flush();$proc.StandardInput.Close()
        if(-not $proc.WaitForExit(55000)){
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
        if($Route -notin (@('Direct','Follow')+(Get-ProfileKeys))){throw '所选代理已不在列表中，请刷新。'}
        if(-not [IO.Path]::IsPathRooted($Executable) -or $Executable -notmatch '(?i)\.exe$' -or $Executable -match '[,\r\n\x00]'){throw '请选择有效 EXE 路径。'}
        if($Route -ne 'Follow' -and -not (Test-Path -LiteralPath $Executable -PathType Leaf)){throw '程序已不存在，请重新添加。'}
        foreach($p in $script:Profiles.Profiles){if($Executable -ieq $p.CorePath -or $Executable -ieq $p.AppPath){throw '不能给代理程序自身分流，以免形成回路。'}}
        $gateway=Get-GatewayKey
        if(-not $gateway -or -not (Get-Listener (Get-Profile $gateway))){throw '按程序分流需要本地分流引擎，请在「代理管理」设置并启动引擎。'}
        if($Route -notin @('Direct','Follow') -and -not (Get-Listener (Get-Profile $Route))){throw '所选代理入口未就绪，请先连接后再设置程序线路。'}
        $before=Get-SystemSnapshot;$beforeEnv=Get-UserProxyEnv;$rules=Get-RoutingSnapshot
        $default=$rules.defaultRoute;$beforeKey=Get-SystemKey $before
        if(-not $default -and $beforeKey -ne $gateway){
            if($beforeKey -ne 'Direct' -and $beforeKey -notin (Get-ProfileKeys)){throw '当前系统入口未知，请先统一切换到已配置的线路。'}
            $default=$beforeKey
        }
        $entries=@($rules.entries | Where-Object {$_.path -ine $Executable})
        if($Route -ne 'Follow'){$entries+=[pscustomobject]@{path=$Executable;route=$Route}}
        $targetRules=[pscustomobject]@{entries=$entries;defaultRoute=$default}
        $p=Get-Profile $gateway;$target=[pscustomobject]@{Flags=3;Server=(Get-EndpointAddress $p);Bypass=$before.Bypass}
        $selection=[pscustomobject]@{Key=$gateway;NetworkKey=$(if($default){$default}else{$gateway});Unified=($entries.Count -eq 0 -and [bool]$default);ChangedAt=(Get-Date).ToString('o')}
        $backup=Invoke-ProxyTransaction $target (New-EnvTarget $beforeEnv $gateway) $selection $before $beforeEnv $targetRules $rules
        [pscustomobject]@{Backup=$backup;Message=('该程序已设为「'+(Get-RouteName $Route)+'」。新连接生效，其他程序继续使用当前默认线路。')}
    }
}
function Sync-ApplicationRoutes {Use-ChangeLock {Invoke-AppRouter @{action='sync'}}}
function Get-ApplicationRoutes {
    try{$core=Invoke-AppRouter @{action='status'}}catch{
        $saved=Get-RoutingSnapshot
        $core=[pscustomobject]@{available=$false;error=$_.Exception.Message;entries=@($saved.entries | ForEach-Object {[pscustomobject]@{path=$_.path;route=$_.route;loaded=$false}});connections=@();defaultRoute=$saved.defaultRoute;defaultLoaded=$false}
    }
    $processes=@(Get-Process);$byId=@{};$apps=@{};$clientPaths=@($script:Profiles.Profiles | ForEach-Object {$_.CorePath;$_.AppPath} | Where-Object {$_})
    foreach($p in $processes){
        if(-not $p.Path -or $p.Path -in $clientPaths -or $p.ProcessName -in @('powershell','pwsh','System','Registry','Idle')){continue}
        $byId[[int]$p.Id]=$p
        if($p.MainWindowHandle -ne [IntPtr]::Zero){$apps[$p.Path.ToLowerInvariant()]=[pscustomobject]@{Path=$p.Path;Name=$p.ProcessName}}
    }
    $tcp=@(Get-NetTCPConnection -State Established -ErrorAction SilentlyContinue);$entrances=@{}
    foreach($c in $tcp){
        $entrance=Get-ConnectionProfile $c;$entrances[[int]$c.LocalPort]= $entrance
        $p=$byId[[int]$c.OwningProcess]
        if($p -and $entrance){$apps[$p.Path.ToLowerInvariant()]=[pscustomobject]@{Path=$p.Path;Name=$p.ProcessName}}
    }
    foreach($rule in $core.entries){$apps[$rule.path.ToLowerInvariant()]=[pscustomobject]@{Path=$rule.path;Name=[IO.Path]::GetFileNameWithoutExtension($rule.path)}}
    $corePorts=@{};foreach($c in $core.connections){$corePorts[[int]$c.sourcePort]=$c}
    $gateway=Get-GatewayKey;$rows=@()
    foreach($app in $apps.Values){
        $ids=@($processes | Where-Object {$_.Path -and $_.Path -ieq $app.Path} | ForEach-Object Id)
        $counts=@{};$outside=0;$unknown=0
        foreach($c in $tcp){
            if($ids -notcontains [int]$c.OwningProcess){continue}
            $entrance=$entrances[[int]$c.LocalPort];$route=$null
            if($entrance){
                if($entrance -eq $gateway){if($corePorts.ContainsKey([int]$c.LocalPort)){$route=$corePorts[[int]$c.LocalPort].route}else{$unknown++}}
                else{$route=$entrance}
            }elseif($c.RemoteAddress -notin @('127.0.0.1','::1','::ffff:127.0.0.1')){$outside++}
            if($route){if(-not $counts.ContainsKey($route)){$counts[$route]=0};$counts[$route]++}
        }
        $rule=$core.entries | Where-Object {$_.path -ieq $app.Path} | Select-Object -First 1
        $policy='Follow';$loaded=$false;if($rule){$policy=$rule.route;$loaded=[bool]$rule.loaded}
        $actual=@();foreach($route in @('Direct')+(Get-ProfileKeys)+@('Blocked','Unknown')){if($counts.ContainsKey($route)){$actual+=((Get-RouteName $route)+' ×'+$counts[$route])}}
        if($unknown){$actual+='引擎入口 / 出口待确认'};if($outside){$actual+='入口外连接 ×'+$outside};if(-not $actual.Count){$actual=@('暂无连接')}
        $status='跟随当前线路'
        if($policy -ne 'Follow'){$status=$(if($loaded){'已加载；新连接生效'}else{'尚未加载；请重载规则'});if($loaded -and (@($counts.Keys | Where-Object {$_ -ne $policy}).Count -or $outside)){$status='已加载；存在旧连接或独立入口'}}
        if(-not (Test-Path -LiteralPath $app.Path)){$status='路径已失效，请移除后重新添加'}elseif(-not $ids.Count -and $policy -ne 'Follow'){$status+=' · 未运行'}
        $rows+=[pscustomobject]@{Name=$app.Name;Path=$app.Path;Policy=$policy;PolicyName=(Get-RouteName $policy);Loaded=$loaded;Actual=($actual -join '，');Status=$status;PIDs=($ids -join ',')}
    }
    [pscustomobject]@{Available=[bool]$core.available;Error=$core.error;Mode=$core.mode;Rows=@($rows | Sort-Object @{Expression={if($_.Policy -ne 'Follow'){0}else{1}}},Name);RuleCount=@($core.entries).Count;DefaultRoute=$core.defaultRoute;DefaultLoaded=[bool]$core.defaultLoaded;GatewayKey=$gateway}
}
