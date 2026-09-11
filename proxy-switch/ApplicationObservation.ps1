# Display evidence is a current snapshot, never a readiness check or permission to switch.
function Get-TcpObservationSnapshot {
    $available=$true;$errorCode='';$rows=@()
    # The CIM wrapper queries each requested State separately. A missing state
    # raises NotFound and aborts assignment, discarding rows from other states.
    # Read one complete table and filter locally so idle SynSent is harmless.
    try{$rows=@(Get-NetTCPConnection -ErrorAction Stop|Where-Object {[string]$_.State -in @('Listen','Established','SynSent')})}
    catch{if($_.FullyQualifiedErrorId -notlike 'CmdletizationQuery_NotFound*'){$available=$false;$errorCode='tcp-query-failed'}}
    [pscustomobject]@{Rows=$rows;Available=$available;ErrorCode=$errorCode;ObservedAt=[DateTimeOffset]::UtcNow.ToString('o')}
}
function Test-ObservationFlag($Value,[string]$Name,[bool]$Default=$true) {
    if($null -ne $Value -and $null -ne $Value.PSObject.Properties[$Name]){return $Value.$Name -eq $true}
    return $Default
}
function Test-SameIpAddress([string]$Left,[string]$Right) {
    $a=$null;$b=$null
    if([Net.IPAddress]::TryParse($Left,[ref]$a) -and [Net.IPAddress]::TryParse($Right,[ref]$b)){
        if($a.IsIPv4MappedToIPv6){$a=$a.MapToIPv4()};if($b.IsIPv4MappedToIPv6){$b=$b.MapToIPv4()}
        return $a.Equals($b)
    }
    return $Left -ceq $Right
}
function Get-ApplicationChildProcesses($Family,[string]$PrimaryPath) {
    $ids=@($Family|ForEach-Object Id)
    @($Family|Where-Object {$_.Path -ine $PrimaryPath -or ($_.ParentId -and $ids -contains [int]$_.ParentId)})
}
function Get-ApplicationConnectionEvidence($Family,$TcpRows,$CoreConnections,[string]$Gateway,$ById,[string]$PrimaryPath,[bool]$TcpAvailable=$true,$ManagedIngresses=@()) {
    $ids=@($Family|ForEach-Object Id);$children=@(Get-ApplicationChildProcesses $Family $PrimaryPath|ForEach-Object Id)
    $counts=@{};$outside=0;$outsidePending=0;$localUnknown=0;$unknown=0;$pending=0;$pendingEndpoints=@{};$childPending=0;$childObserved=0;$total=0;$managedObserved=0;$policyMismatch=0;$policyUnknown=0;$managedPending=0;$ingressIds=@{}
    if($TcpAvailable){foreach($c in $TcpRows){
        if([string]$c.State -notin @('Established','SynSent') -or $ids -notcontains [int]$c.OwningProcess){continue}
        $total++
        # Match each socket's own remote endpoint. LocalPort alone is not a unique socket key.
        $entry=Get-ConnectionProfile $c;$route=$null
        $owned=@($ManagedIngresses|Where-Object {$_ -and [int]$_.port -eq [int]$c.RemotePort -and $c.RemoteAddress -in @('127.0.0.1','::1','::ffff:127.0.0.1')})
        $ingress=$null;if($owned.Count -eq 1){$ingress=$owned[0]}
        if([string]$c.State -eq 'SynSent'){
            $pending++;if($children -contains [int]$c.OwningProcess){$childPending++}
            if($ingress){$managedPending++}elseif(-not $entry){$outsidePending++}
            $address=[string]$c.RemoteAddress;if($address.Contains(':')){$address='['+$address+']'}
            $endpoint=$address+':'+[int]$c.RemotePort
            if(-not $pendingEndpoints.ContainsKey($endpoint)){$pendingEndpoints[$endpoint]=0};$pendingEndpoints[$endpoint]++
            continue
        }
        $candidates=@($CoreConnections|Where-Object {[int]$_.sourcePort -eq [int]$c.LocalPort})
        if($ingress){$candidates=@($candidates|Where-Object {
            if(-not $_.sourceAddress){return $false}
            if($_.ingressId -and $_.ingressId -ne $ingress.id){return $false}
            if($_.inboundName -and $_.inboundName -ne ('FS-Program-'+$ingress.id)){return $false}
            return [bool]($_.ingressId -or $_.inboundName)
        })}
        $engine=Find-EngineConnection $candidates ([string]$ById[[int]$c.OwningProcess].Path) $c
        if($ingress){
            if($engine -and $engine.route){$route=$engine.route;$managedObserved++;$ingressIds[[string]$ingress.id]=$true
                if($route -in @('Unknown','Blocked')){$policyUnknown++}
                elseif($engine.PSObject.Properties['policyMatches']){if($null -eq $engine.policyMatches){$policyUnknown++}elseif(-not $engine.policyMatches){$policyMismatch++}}
                elseif($engine.expectedRoute -and $engine.expectedRoute -notin @('Unknown','Blocked')){if($route -ne $engine.expectedRoute){$policyMismatch++}}
                else{$policyUnknown++}
            }else{$unknown++}
        }
        elseif($entry){if($entry -eq $Gateway){if($engine -and $engine.route){$route=$engine.route}else{$unknown++}}else{$route=$entry}}
        elseif($engine -and $engine.inbound -ieq 'Tun'){if($engine.route){$route=$engine.route}else{$unknown++}}
        elseif($c.RemoteAddress -in @('127.0.0.1','::1','::ffff:127.0.0.1')){$localUnknown++}
        else{$outside++}
        if($route){if(-not $counts.ContainsKey($route)){$counts[$route]=0};$counts[$route]++;if($children -contains [int]$c.OwningProcess){$childObserved++}}
    }}
    $actual=@()
    $knownRoutes=@('Direct')+(Get-ProfileKeys)+@('Blocked','Unknown')
    foreach($route in $knownRoutes){if($counts.ContainsKey($route)){$actual+=((Get-RouteName $route)+' ×'+$counts[$route])}}
    $unrecognized=0;foreach($route in $counts.Keys){if($knownRoutes -notcontains $route){$unrecognized+=$counts[$route]}}
    if($unrecognized){$actual+='未识别线路 ×'+$unrecognized+' · 出口待确认'}
    if($unknown){$actual+='分流入口 ×'+$unknown+' · 出口待确认'}
    if($outside){$actual+='入口外 TCP ×'+$outside}
    if($localUnknown){$actual+='未登记的本机连接 ×'+$localUnknown}
    if($pending){$targets=@($pendingEndpoints.Keys|Sort-Object|ForEach-Object {$_+' ×'+$pendingEndpoints[$_]});$actual+='连接尚未建立 / SynSent ×'+$pending+'（'+($targets -join '、')+'）'}
    $state='Idle'
    if(-not $TcpAvailable){$state='Unknown';$actual=@('连接读取失败 · 状态未知')}
    elseif($counts.Count -or $outside -or $unknown -or $localUnknown){$state='Connected'}
    elseif($pending){$state='Connecting'}
    [pscustomobject]@{Counts=$counts;Outside=$outside;OutsidePending=$outsidePending;LocalUnknown=$localUnknown;GatewayUnknown=$unknown;Pending=$pending;PendingEndpoints=$pendingEndpoints;ChildPending=$childPending;ChildProxyObserved=$childObserved;Total=$total;ManagedObserved=$managedObserved;ManagedPending=$managedPending;PolicyMismatch=$policyMismatch;PolicyUnknown=$policyUnknown;ObservedIngressIds=@($ingressIds.Keys);State=$state;Actual=($actual -join '，');Available=$TcpAvailable;Layer='TCP';AuthenticationVerified=$false}
}
function Get-ApplicationObservationRow($App,$Family,$Evidence,$Core,$Rule,$Launch,$Identity,[bool]$ProcessesAvailable=$true,$FamilySnapshot=$null) {
    $ids=@($Family|ForEach-Object Id);$children=@(Get-ApplicationChildProcesses $Family $App.Path|ForEach-Object ProcessName|Select-Object -Unique)
    $policy='Follow';$mode='observe';$ruleLoaded=$false;$status='未设专用规则 · 仅观察实际 TCP 连接'
    if($Rule){$policy=$Rule.route;$mode='engine';if($Rule.managed){$mode='managed'};$ruleLoaded=$Rule.loaded -eq $true}
    elseif($Launch){$policy=$Launch.route;$mode='launch'}
    $loaded=$false;$actual=$Evidence.Actual;$observation=$Evidence.State;$repair=$false;$needsRelaunch=$false
    if($Identity){$repair=[bool]$Identity.RequiresRepair}
    $pathExists=$false;if($App.Path){$pathExists=Test-Path -LiteralPath $App.Path -PathType Leaf}
    if(-not $ProcessesAvailable){$actual='进程读取失败 · 状态未知';$observation='Unknown'}
    elseif(-not $ids.Count){
        if(-not $pathExists){$actual='程序路径已失效';$observation='Missing'}else{$actual='程序未运行';$observation='NotRunning'}
    }elseif(-not $actual){$actual='运行中 · 未观察到 TCP 连接';$observation='Idle'}
    if($mode -eq 'managed'){
        $currentIngressObserved=$Evidence.ManagedObserved -gt 0 -and -not @($Evidence.ObservedIngressIds|Where-Object {$_ -ne $Rule.id}).Count
        $session=$false;if(-not $repair){$session=Test-ManagedProgramSession $App.Path $Family $policy}
        $knownOtherEntry=$Evidence.Counts.Count -gt 0 -and -not $currentIngressObserved
        $needsRelaunch=$ids.Count -gt 0 -and -not $currentIngressObserved -and (-not $session -or $knownOtherEntry)
        $status='固定程序入口已保存 · 从托管入口启动后主程序与子进程共同使用'
        if(-not (Test-ObservationFlag $Core 'rulesAvailable' ([bool]$Core.available))){$status='规则读取失败 · 固定程序入口生效状态未知'}
        elseif(-not $ruleLoaded -or $Rule.ready -ne $true){$status='固定程序入口未就绪 · 请启动代理服务或重新应用线路'}
        elseif($needsRelaunch){$status='运行进程尚未接入固定程序入口 · 保存工作并完整退出后，从托管入口重新打开'}
        elseif($Evidence.Outside -or $Evidence.LocalUnknown -or $Evidence.GatewayUnknown){$status='固定程序入口已就绪 · 部分连接仍未确认接管'}
        elseif($Evidence.Pending){$status='固定程序入口已就绪 · TCP 正在建立连接'}
        elseif($Evidence.PolicyMismatch -gt 0){$status='仍有不符合当前线路的连接 · 可预览重连'}
        elseif($Evidence.PolicyUnknown -gt 0){$status='已连接固定程序入口 · 目标选路状态待确认'}
        elseif($currentIngressObserved){$loaded=$true;$status='已观察到固定程序入口按当前规则选路';if($Evidence.Counts.Count -gt 1){$status+='（含网站分流）'};if($Evidence.ChildProxyObserved){$status+=' · 含已验证子进程'}}
        elseif($ids.Count){$status='固定程序入口已就绪 · 运行中，等待实际连接'}
        else{$status='固定程序入口已就绪 · 从托管入口打开即可使用'}
        if(-not (Test-ObservationFlag $Core 'connectionsAvailable' ([bool]$Core.available))){$loaded=$false;$status='引擎连接读取失败 · 实际出口未知'}
        if(-not (Test-ObservationFlag $Core 'proxiesAvailable' $true)){$loaded=$false;$status='当前出口读取失败 · 选路状态未知'}
    }elseif($mode -eq 'engine'){
        if(-not (Test-ObservationFlag $Core 'rulesAvailable' ([bool]$Core.available))){$status='分流规则读取失败 · 生效状态未知'}
        elseif(-not $ruleLoaded){$status='规则尚未载入 · 请启动引擎或重载'}
        else{
            $status='规则已载入 · 等待实际连接'
            $wanted=$policy;if($Rule.effectiveRoute){$wanted=$Rule.effectiveRoute}
            if($Evidence.Outside -or $Evidence.LocalUnknown -or $Evidence.GatewayUnknown){$status='规则已载入 · 存在未确认接管的连接'}
            elseif($Evidence.Pending){$status='规则已载入 · TCP 正在建立连接'}
            elseif(@($Evidence.Counts.Keys|Where-Object {$_ -ne $wanted}).Count){$status='规则已载入 · 仍有旧线路连接，可预览重连'}
            elseif($Evidence.Counts.ContainsKey($wanted)){$loaded=$true;$status='已观察到指定线路连接';if($wanted -ne $policy){$status='已自动接替到 '+(Get-RouteName $wanted)}}
        }
        if(-not (Test-ObservationFlag $Core 'connectionsAvailable' ([bool]$Core.available)) -and $ruleLoaded){$loaded=$false;$status='规则已载入 · 引擎连接读取失败，出口未知'}
        if(-not (Test-ObservationFlag $Core 'proxiesAvailable' $true) -and $ruleLoaded){$loaded=$false;$status='规则已载入 · 当前出口读取失败，出口未知'}
    }elseif($mode -eq 'launch'){
        $status='启动代理已保存 · 下次从代理入口打开生效'
        if($ids.Count){$status='未确认使用代理启动入口 · 实际连接见左栏'}
        if(-not $repair -and (Test-ManagedProgramSession $App.Path $Family $policy)){
            $wanted=$policy;if($wanted -eq 'Follow'){$wanted=Get-SystemKey (Get-SystemSnapshot)}
            $status='已按目标启动 · 等待实际 TCP 连接'
            if($Evidence.Pending -or $Evidence.Outside -or $Evidence.LocalUnknown -or $Evidence.GatewayUnknown){$status='已按目标启动 · 部分连接仍待确认'}
            elseif($Evidence.Counts.ContainsKey($wanted) -and -not @($Evidence.Counts.Keys|Where-Object {$_ -ne $wanted}).Count){
                $loaded=$true;$status='已观察到目标代理连接'
                if($children.Count -and -not $Evidence.ChildProxyObserved){$loaded=$false;$status='主程序已通过代理 · 子进程连接待验证'}elseif($Evidence.ChildProxyObserved){$status+='（含子进程）'}
            }
        }
    }
    if($mode -eq 'launch' -and -not $repair){
        $entryHealth=@(Get-ProgramProxyShortcutHealth $App.Path)
        if(@($entryHealth|Where-Object CanRefresh).Count){$status+=' · 代理启动入口仍指向旧版或已缺失，请修复启动入口'}
        if($ids.Count -and -not (Test-ManagedProgramSession $App.Path $Family $policy)){$status+=' · 已有进程可能保留旧启动代理，保存新线路不会修改其环境或启动参数'}
    }
    if(-not $Evidence.Available -or -not $ProcessesAvailable){$loaded=$false;$status+=' · 采集失败，不代表断网'}
    if(-not $App.Path){$loaded=$false;$status='程序路径不可读 · 仅按 PID 观察，不自动套用规则'}
    elseif($ProcessesAvailable -and -not $pathExists -and -not $ids.Count){$status='旧路径不存在 · 可重新定位或移除此记录'}
    elseif($ProcessesAvailable -and -not $ids.Count -and $mode -ne 'observe'){$status+=' · 未运行'}
    if($repair){$loaded=$false;$status='已识别路径变更 · 规则待修复；左栏为当前进程连接'}
    if($Identity -and $Identity.Reason -match 'Ambiguous'){$loaded=$false;$status='发现多个候选程序 · 请手动定位，不自动套用规则'}
    if($App.Conflict){$loaded=$false;$status='同一程序有多条保存记录 · 请移除过期记录'}
    $familyUnknown=@();$familyRetained=@()
    if($FamilySnapshot){
        $familyUnknown=@($FamilySnapshot.UnknownIds);$familyRetained=@($FamilySnapshot.RetainedIds|Where-Object {$ids -contains $_})
        if($familyRetained.Count){if(@($Family|Where-Object {$_.Path -ieq $App.Path}).Count){$status+=' · 保留已验证后台子进程归属'}else{$status+=' · 主进程已退出，已验证后台子进程仍在运行'}}
        if($familyUnknown.Count){$loaded=$false;$status=$status -replace ' · 未运行$','';$status+=' · 部分进程身份不可读，归属未知';if(-not $ids.Count){$actual='程序进程身份不可读 · 归属未知';$observation='Unknown'}}
    }
    if($Evidence.ChildPending){$loaded=$false;$status+=' · 联网子进程连接尚未建立（SynSent），持续待连时请检查入口'}
    elseif($Evidence.Pending){$loaded=$false;$status+=' · TCP 连接尚未建立（SynSent），持续待连时请检查入口'}
    $policyName=Get-RouteName $policy;if($mode -eq 'observe'){$policyName='未单独指定'}
    $reason='';if($Identity){$reason=[string]$Identity.Reason}
    $canRepair=$repair -and [bool]$Identity.CanRepair -and -not $App.Conflict
    [pscustomobject]@{Name=$App.Name;Path=$App.Path;SavedPath=$App.SavedPath;RowKey=$App.RowKey;Policy=$policy;PolicyName=$policyName;Mode=$mode;Managed=($mode -eq 'managed');NeedsRelaunch=$needsRelaunch;FamilyRetained=($familyRetained.Count -gt 0);FamilyUnknownIds=$familyUnknown;Loaded=$loaded;RuleLoaded=$ruleLoaded;Actual=$actual;Status=$status;PIDs=($ids -join ',');ChildNames=($children -join '、');OutsidePending=$Evidence.OutsidePending;Pending=$Evidence.Pending;ChildPending=$Evidence.ChildPending;ObservationState=$observation;IdentityReason=$reason;RequiresRepair=$repair;CanRepair=$canRepair;Identity=$Identity.Identity;CanLaunch=($mode -in @('launch','managed') -and -not $repair);HasSavedRule=($mode -ne 'observe');AuthenticationVerified=$false;Coverage='TCP Established/SynSent；连接证据不代表代理握手、目标网站可达或账号登录成功。短时连接、UDP/QUIC 与独立隧道可能不在此快照中'}
}
