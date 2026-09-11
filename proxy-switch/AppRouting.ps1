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
            if($Request.action -eq 'reconnect' -and $result.failed -gt 0 -and $result.Message){return $result}
            if($result.error){throw $result.error};if($result.Message){throw $result.Message};throw '程序规则操作未完成。'
        }
        return $result
    }finally{$proc.Dispose()}
}

function Set-ApplicationRoute([string]$Executable,[string]$Route) {
    if(Get-ManagedProgramIngress $Executable){return Set-ManagedApplicationRoute $Executable $Route}
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
        if($Route -ne 'Follow'){$entries+=[pscustomobject]@{path=$Executable;route=$Route;identity=(Get-ProgramIdentityDescriptor -Path $Executable -Context (New-ProgramIdentityContext))}}
        # Legacy launchers may remain for compatibility, but no longer override this engine rule.
        $launchEntries=@($rules.launchEntries | ForEach-Object {if($_.path -ieq $Executable){[pscustomobject]@{path=$_.path;route='Follow';adapter=$_.adapter;identity=$_.identity}}else{$_}})
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
function Find-EngineConnection($Candidates,[string]$ProcessPath,$TcpConnection=$null) {
    if(-not $ProcessPath){return $null}
    $matches=@($Candidates|Where-Object {
        if(-not $_.path -or $_.path -ine $ProcessPath -or $_.network -ine 'tcp'){return $false}
        if($TcpConnection){
            if($_.sourceAddress -and -not (Test-SameIpAddress $_.sourceAddress $TcpConnection.LocalAddress)){return $false}
            if($_.inbound -ieq 'Tun'){
                if($_.destinationAddress -and -not (Test-SameIpAddress $_.destinationAddress $TcpConnection.RemoteAddress)){return $false}
                if($_.destinationPort -and [int]$_.destinationPort -ne [int]$TcpConnection.RemotePort){return $false}
            }
        }
        return $true
    })
    if($matches.Count -eq 1){return $matches[0]}
    return $null
}
function New-ApplicationCandidate([string]$Path,[string]$Name,[int]$ProcessId=0) {
    [pscustomobject]@{Path=$Path;Name=$Name;PID=$ProcessId;SavedPath='';RowKey=$(if($Path){$Path.ToLowerInvariant()}else{'pid:'+$ProcessId});CoreRule=$null;LaunchRule=$null;Identity=$null;Conflict=$false}
}
function Get-ApplicationRoutes($TcpRows=$null,[bool]$TcpAvailable=$true) {
    . (Join-Path $PSScriptRoot 'ProgramFamilyTracking.ps1')
    $saved=Get-RoutingSnapshot
    try{$core=Invoke-AppRouter @{action='status'} -TimeoutMilliseconds 9000}catch{
        $core=[pscustomobject]@{available=$false;error='引擎状态读取失败或超时';rulesAvailable=$false;connectionsAvailable=$false;entries=@($saved.entries|ForEach-Object {[pscustomobject]@{path=$_.path;route=$_.route;identity=$_.identity;loaded=$null}});connections=@();programIngresses=@($saved.programIngresses|Where-Object {$_ -and $_.path}|ForEach-Object {[pscustomobject]@{id=$_.id;path=$_.path;port=$_.port;route=$_.route;identity=$_.identity;managed=$true;loaded=$null;ready=$null}});defaultRoute=$saved.defaultRoute;defaultLoaded=$null}
    }
    $processesAvailable=$true;$processes=@();$processSnapshotStarted=[DateTime]::UtcNow
    try{$processes=@(Get-ProcessInventory)}catch{$processesAvailable=$false}
    $context=New-ProgramIdentityContext -Processes $processes
    $context.Created=$processSnapshotStarted
    $byId=@{};$apps=@{};$clientPaths=@($script:Profiles.Profiles|ForEach-Object {$_.CorePath;$_.AppPath}|Where-Object {$_})
    foreach($p in $processes){
        $byId[[int]$p.Id]=$p
        if($p.Path -in $clientPaths -or $p.ProcessName -in @('powershell','pwsh','System','Registry','Idle')){continue}
        if($p.MainWindowHandle -ne [IntPtr]::Zero){$apps[(Get-ProcessRowKey $p)]=New-ApplicationCandidate $p.Path $p.ProcessName $p.Id}
    }
    if($null -eq $TcpRows){$snapshot=Get-TcpObservationSnapshot;$TcpRows=$snapshot.Rows;$TcpAvailable=$snapshot.Available}
    $tcp=@($TcpRows|Where-Object {$_.State -in @('Established','SynSent')})
    if($TcpAvailable){foreach($c in $tcp){
        $p=$byId[[int]$c.OwningProcess]
        if($p -and $p.Path -notin $clientPaths -and (Get-ConnectionProfile $c)){$apps[(Get-ProcessRowKey $p)]=New-ApplicationCandidate $p.Path $p.ProcessName $p.Id}
    }}
    $records=@();$launchEntries=@($saved.launchEntries)
    $managedEntries=@($saved.programIngresses|Where-Object {$_ -and $_.path})
    foreach($entry in $managedEntries){
        $live=$core.programIngresses|Where-Object {$_.id -eq $entry.id -and $_.path -ieq $entry.path -and [int]$_.port -eq [int]$entry.port}|Select-Object -First 1
        if($live){$rule=$live|Select-Object *}else{$rule=[pscustomobject]@{id=$entry.id;path=$entry.path;port=$entry.port;route=$entry.route;ready=$null;loaded=$null}}
        $rule|Add-Member managed $true -Force
        $records+=[pscustomobject]@{Path=$entry.path;Rule=$rule;Launch=$null;Identity=$entry.identity}
    }
    foreach($rule in @($core.entries|Where-Object {$_.path -and $_.path -notin @($managedEntries.path)})){
        $stored=$saved.entries|Where-Object {$_.path -ieq $rule.path}|Select-Object -First 1
        $records+=[pscustomobject]@{Path=$rule.path;Rule=$rule;Launch=$null;Identity=$stored.identity}
    }
    foreach($entry in $launchEntries){if($entry.path -notin @($managedEntries.path) -and -not @($core.entries|Where-Object {$_.path -ieq $entry.path}).Count){$records+=[pscustomobject]@{Path=$entry.path;Rule=$null;Launch=$entry;Identity=$entry.identity}}}
    foreach($record in $records){
        if(-not $record.Path){continue}
        $identity=Resolve-ProgramIdentity -Path $record.Path -Processes $processes -Context $context -SavedIdentity $record.Identity
        $current=$identity.CurrentPath;if(-not $current){$current=$record.Path}
        $key=$current.ToLowerInvariant();$row=$apps[$key]
        if($row -and $row.SavedPath -and $row.SavedPath -ine $record.Path){
            $row.Conflict=$true;$key='saved:'+$record.Path.ToLowerInvariant();$row=New-ApplicationCandidate $current ([IO.Path]::GetFileNameWithoutExtension($current)+'（保存记录）');$row.Conflict=$true
        }
        if(-not $row){$row=New-ApplicationCandidate $current ([IO.Path]::GetFileNameWithoutExtension($current))}
        $row.SavedPath=$record.Path;$row.RowKey='saved:'+$record.Path.ToLowerInvariant();$row.CoreRule=$record.Rule;$row.LaunchRule=$record.Launch;$row.Identity=$identity;$apps[$key]=$row
    }
    # Fold same-installation helper processes only when they have no explicit rule of their own.
    $familySnapshots=@{}
    foreach($primary in @($apps.Values)){
        if(-not $primary.Path){continue}
        $snapshot=Get-ProgramFamilyTrackingSnapshot $primary.Path $processes $context $processesAvailable
        $familySnapshots[$primary.RowKey]=$snapshot
        if(-not $primary.SavedPath -and -not @($processes|Where-Object {$_.Path -ieq $primary.Path -and $_.MainWindowHandle -ne [IntPtr]::Zero}).Count){continue}
        foreach($member in @($snapshot.Members)){
            if(-not $member.Path -or $member.Path -ieq $primary.Path){continue}
            $memberKey=$member.Path.ToLowerInvariant();if($apps.ContainsKey($memberKey) -and -not $apps[$memberKey].SavedPath){$apps.Remove($memberKey)}
        }
    }
    $gateway=Get-GatewayKey;$rows=@()
    $independentApps=@($apps.Values|Where-Object {$_.SavedPath -and $_.Path})
    foreach($app in $apps.Values){
        $family=@();$familySnapshot=$null
        if($app.Path){$familySnapshot=$familySnapshots[$app.RowKey];if(-not $familySnapshot){$familySnapshot=Get-ProgramFamilyTrackingSnapshot $app.Path $processes $context $processesAvailable};$family=@($familySnapshot.Members)}elseif($app.PID -and $byId.ContainsKey($app.PID)){$family=@($byId[$app.PID])}
        # A separately saved child rule owns its own observation row and descendant evidence.
        # Compare verified current paths, never display names or obsolete saved path strings.
        if($app.Path -and $family.Count){
            $excluded=@{}
            foreach($independent in $independentApps){
                if(Test-ProgramPathEquivalent $app.Path $independent.Path $context){continue}
                if(-not @($family|Where-Object {$_.Path -and (Test-ProgramPathEquivalent $_.Path $independent.Path $context)}).Count){continue}
                foreach($member in @(Get-ProgramFamily $independent.Path $processes $context)){$excluded[[int]$member.Id]=$true}
            }
            if($excluded.Count){$family=@($family|Where-Object {-not $excluded.ContainsKey([int]$_.Id)})}
        }
        $evidence=Get-ApplicationConnectionEvidence $family $tcp $core.connections $gateway $byId $app.Path $TcpAvailable $managedEntries
        $rows+=Get-ApplicationObservationRow $app $family $evidence $core $app.CoreRule $app.LaunchRule $app.Identity $processesAvailable $familySnapshot
    }
    $rulesAvailable=Test-ObservationFlag $core 'rulesAvailable' ([bool]$core.available)
    $connectionsAvailable=Test-ObservationFlag $core 'connectionsAvailable' ([bool]$core.available)
    [pscustomobject]@{Available=[bool]$core.available;RulesAvailable=$rulesAvailable;ConnectionsAvailable=$connectionsAvailable;ProcessesAvailable=$processesAvailable;TcpAvailable=$TcpAvailable;Error=$core.error;Mode=$core.mode;Rows=@($rows|Sort-Object @{Expression={if($_.HasSavedRule){0}else{1}}},Name);RuleCount=(@($core.entries|Where-Object {$_.path -notin @($managedEntries.path)}).Count+$managedEntries.Count+@($launchEntries|Where-Object {$_.route -ne 'Follow' -and $_.path -notin @($managedEntries.path)}).Count);LaunchRuleCount=@($launchEntries|Where-Object {$_.route -ne 'Follow' -and $_.path -notin @($managedEntries.path)}).Count;ManagedRuleCount=$managedEntries.Count;RepairCount=@($rows|Where-Object CanRepair).Count;DefaultRoute=$core.defaultRoute;EffectiveDefaultRoute=$core.effectiveDefaultRoute;Failover=$core.failover;DefaultLoaded=$core.defaultLoaded;GatewayKey=$gateway;ObservedAt=[DateTimeOffset]::UtcNow.ToString('o');Coverage='TCP 快照；UDP/QUIC、短时请求和未进入入口的流量需分别诊断'}
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
