# Stable application entrances and domain policy. Writers are explicit user actions.
function Get-ManagedProgramIngress([string]$Executable) {
    (Get-RoutingSnapshot).programIngresses|Where-Object {$_.path -ieq $Executable}|Select-Object -First 1
}
function Get-ManagedIngressEndpoint($Entry) {'http://127.0.0.1:'+([int]$Entry.port)}
function Copy-RoutingSnapshot($Snapshot) {$Snapshot|ConvertTo-Json -Depth 16|ConvertFrom-Json}
function Assert-ManagedRoute([string]$Route,[switch]$AllowFollow) {
    $keys=@('Direct')+(Get-ProfileKeys);if($AllowFollow){$keys+=@('Follow')}
    if($Route -notin $keys -or ($Route -eq (Get-GatewayKey) -and $script:Profiles.Routing.Adapter -eq 'standalone')){throw '请选择有效上游、直连或跟随统一线路，不能把流向入口作为自己的出口。'}
}
function Ensure-ManagedGateway([string]$InitialRoute='') {
    if($InitialRoute -eq 'Follow'){$InitialRoute=''}
    if($script:Profiles.Routing.Adapter -eq 'standalone' -and (Test-Path -LiteralPath (Get-IndependentSessionPath))){
        $session=Get-Content -LiteralPath (Get-IndependentSessionPath) -Raw -Encoding UTF8|ConvertFrom-Json
        $life=Get-GatewayLifecycle
        if(-not (Test-SessionProcess $session.OwnerPID $session.OwnerStart) -or -not (Test-SessionProcess $session.SupervisorPID $session.SupervisorStart) -or ($life.phase -in @('failed','stopped'))){
            # Only an explicit user action retries a fully stopped/exhausted service.
            # Restore owned settings and stop the verified old child before reusing ports.
            Restore-IndependentSession -ExpectedSession $session.Started
        }
    }
    if($script:Profiles.Routing.Adapter -ne 'standalone' -or -not (Test-Path -LiteralPath (Get-IndependentSessionPath))){
        if($InitialRoute){Assert-ManagedRoute $InitialRoute}
        Enable-IndependentGateway -OwnerPID $PID -InitialRoute $InitialRoute | Out-Null
    }
    $deadline=[DateTime]::UtcNow.AddSeconds(12)
    do {
        $remaining=[int]($deadline-[DateTime]::UtcNow).TotalMilliseconds
        if($remaining -le 0){break}
        $live=Invoke-AppRouter @{action='status'} -TimeoutMilliseconds ([Math]::Min(2500,$remaining))
        if($live.available -and $live.rulesAvailable -and $live.defaultLoaded){return $live}
        Start-Sleep -Milliseconds 200
    }while([DateTime]::UtcNow -lt $deadline)
    throw '流向入口尚未就绪，未启动目标程序。请打开流向查看服务状态，或停止服务后重新启动。'
}
function Set-UniversalProxy([string]$Key) {
    Use-ChangeLock {
        Assert-ManagedRoute $Key
        if($script:Profiles.Routing.Adapter -ne 'standalone'){return Enable-IndependentGateway -OwnerPID $PID -InitialRoute $Key -UnifiedSwitch -AllowMigration}
        if(Test-Path -LiteralPath (Get-IndependentSessionPath)){Ensure-ManagedGateway $Key|Out-Null}
        Set-SelectedProxy $Key
    }
}
function New-ManagedIngressPort($Snapshot) {
    $used=@($script:Profiles.Profiles|ForEach-Object Port)+@($Snapshot.programIngresses|ForEach-Object port)
    for($port=19080;$port -lt 20080;$port++){
        if($port -in $used){continue}
        $listener=New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback,$port)
        try{$listener.Server.ExclusiveAddressUse=$true;$listener.Start();return $port}catch{}finally{$listener.Stop()}
    }
    throw '没有可用的程序固定入口端口；未复用其他软件的监听端口。'
}
function Invoke-ManagedRoutingChange($Before,$Next,[scriptblock]$Verify) {
    $backup=Save-Backup ([pscustomobject]@{Version=3;Time=(Get-Date).ToString('o');System=(Get-SystemSnapshot);Environment=(Get-UserProxyEnv);Selection=(Get-Selection);Routing=$Before})
    $written=$false
    try{
        Set-RoutingSnapshot $Next $Before;$written=$true
        if($Verify){& $Verify|Out-Null}
    }catch{
        $failure=$_.Exception.Message
        if($written){
            try{if(Test-SameRouting (Get-RoutingSnapshot) $Next){Set-RoutingSnapshot $Before $Next}else{throw '记录已被其他操作更改'}}
            catch{throw ($failure+'；未完成规则回滚，保留当前记录与备份：'+$backup)}
        }
        throw ($failure+'；原规则已保留或恢复。')
    }
    return $backup
}
function Set-ManagedApplicationRoute([string]$Path,[string]$Route) {
    Use-ChangeLock {
        $executable=Resolve-ProgramTarget $Path;Assert-ManagedRoute $Route -AllowFollow
        foreach($profile in $script:Profiles.Profiles){if($executable -ieq $profile.CorePath -or $executable -ieq $profile.AppPath){throw '不能给代理程序自身分流，以免形成回路。'}}
        $adapter=Get-ProgramProxyAdapter $executable
        if($adapter -ne 'chromium' -and (Get-ManagedProgramIngress $executable)){throw '此程序当前版本已无法核验原启动适配，原固定入口和规则保持不变。请检查程序路径及安装是否完整，再修复程序记录。'}
        if($Route -notin @('Direct','Follow') -and -not (Test-ProxyRoute $Route -Fast).Usable){throw '所选上游检测未通过，未保存切换成功状态。请先检查这个代理入口。'}
        # A program action never replaces the saved global default during cold start.
        Ensure-ManagedGateway|Out-Null
        if($adapter -ne 'chromium'){
            $result=Set-ApplicationRoute $executable $Route
            $result.Message+=' 此程序没有可核验的原生代理启动适配；仍指向已退出旧代理的进程，需要在程序内改为流向入口或自行重开。'
            return $result
        }
        $before=Get-RoutingSnapshot;$next=Copy-RoutingSnapshot $before
        $entry=$before.programIngresses|Where-Object {$_.path -ieq $executable}|Select-Object -First 1
        $created=-not $entry
        if($created){
            if(@($before.programIngresses).Count -ge 64){throw '程序固定入口最多 64 个，请先移除不再使用的记录。'}
            $entry=[pscustomobject]@{id=[Guid]::NewGuid().ToString('N');path=$executable;port=(New-ManagedIngressPort $before);route=$Route;identity=(Get-ProgramIdentityDescriptor $executable (New-ProgramIdentityContext))}
        }else{$entry=Copy-RoutingSnapshot $entry;$entry.route=$Route}
        $next.programIngresses=@($before.programIngresses|Where-Object {$_.path -ine $executable})+@($entry)
        $next.entries=@($before.entries|Where-Object {$_.path -ine $executable})
        # Keep already owned shortcuts while upgrading legacy direct-upstream launch records.
        $next.launchEntries=@($before.launchEntries|ForEach-Object {if($_.path -ieq $executable){$copy=Copy-RoutingSnapshot $_;$copy.route='Follow';$copy}else{$_}})
        $next|Add-Member NoteProperty resetIngressSelections @($entry.id) -Force
        $verify={
            $live=Invoke-AppRouter @{action='status'}
            $loaded=$live.programIngresses|Where-Object {$_.id -ceq $entry.id}|Select-Object -First 1
            if(-not $live.available -or -not $loaded.loaded -or -not $loaded.ready){throw '程序固定入口或线路规则未通过实读校验，不能确认切换。'}
            $wanted=$Route;if($wanted -eq 'Follow'){$wanted=$live.effectiveDefaultRoute}
            if(-not $wanted -or $loaded.effectiveRoute -ne $wanted -or $wanted -in @('Blocked','Unknown')){throw '实际出口尚未到达所选线路，不能确认切换成功。'}
        }
        $backup=Invoke-ManagedRoutingChange $before $next $verify
        $shortcuts=@();$shortcutNotice=''
        try{$shortcuts=@(Install-ProgramProxyShortcut $executable)}catch{$shortcutNotice=' 原桌面入口未接入；请使用流向的“按指定线路打开”。已有快捷方式和外部修改保持原样。'}
        $family=@();$managed=$false;$observationUnknown=$false
        try{
            $family=@(Get-ProgramFamily $executable @(Get-ProcessInventory))
            $managed=Test-ManagedProgramSession $executable $family $Route
            if($family.Count -and -not $managed){
                $observation=Get-ApplicationRoutes
                $row=$observation.Rows|Where-Object {$_.Path -ieq $executable -and $_.Mode -eq 'managed'}|Select-Object -First 1
                if($row -and $row.Loaded -and -not $row.NeedsRelaunch){$managed=$true}
                if(-not $observation.ProcessesAvailable -or -not $observation.TcpAvailable){$observationUnknown=$true}
            }
        }catch{$observationUnknown=$true}
        $message='程序固定入口已就绪，新连接的默认出口已核验为「'+(Get-RouteName $Route)+'」。网站例外规则继续生效。'
        if($observationUnknown){$message+=' 线路已提交，但当前程序连接读取失败，生效范围待确认；请刷新查看实际连接。'}
        elseif($family.Count -and -not $managed){$message+=' 当前进程未确认接入固定入口：请保存任务并完整退出，再从流向打开或使用已接入的桌面入口；旧进程记住的代理地址不能通过保存规则修改。'}
        elseif($family.Count){$message+=' 已接入程序及继承入口的后台进程无需重开；已有长连接保持原状，可预览后单独重连。'}
        else{$message+=' 请从流向或已接入的桌面入口打开程序。'}
        [pscustomobject]@{Backup=$backup;Message=($message+$shortcutNotice);Shortcuts=$shortcuts;Managed=$true;IngressId=$entry.id;ObservationUnknown=$observationUnknown;NeedsRelaunch=($family.Count -gt 0 -and -not $managed -and -not $observationUnknown)}
    }
}
function Get-WebsiteRules {
    $snapshot=Get-RuleMaintenanceSnapshot ''; $entries=@()
    foreach($rule in @($snapshot.Engine.siteRules|Where-Object {$_})){
        $executable='';if($rule.scope -ne 'global'){$ingress=$snapshot.Engine.programIngresses|Where-Object {$_.id -ceq $rule.scope}|Select-Object -First 1;if(-not $ingress){throw '网站规则引用的程序入口不存在，请从本机备份恢复。'};$executable=$ingress.path}
        $entries+=@([pscustomobject]@{Id=$rule.id;Domain=$rule.domain;Match=$(if($rule.type -eq 'domain'){'exact'}else{'suffix'});Route=$rule.route;Executable=$executable})
    }
    $available=$false;$loaded=$false
    try{$live=Invoke-AppRouter @{action='status'} -TimeoutMilliseconds 9000;$available=[bool]$live.available;$loaded=$live.siteRulesLoaded -eq $true}catch{}
    [pscustomobject]@{Entries=$entries;Revision=$snapshot.Files['app-rules.json'].TextHash;Available=$available;Loaded=$loaded;Message='按目标域名分流：程序网站例外优先于全局例外，然后使用程序线路。只作用于进入流向的新连接。'}
}
function ConvertTo-WebsiteDomain([string]$Domain) {
    $text=$Domain.Trim().TrimEnd('.').ToLowerInvariant()
    if(-not $text -or $text -match '[/\\:@?#*\s\x00]'){throw '请只输入域名，例如 example.com，不要输入网址、端口、通配符或登录链接。'}
    try{$text=(New-Object Globalization.IdnMapping).GetAscii($text)}catch{throw '域名格式无效。'}
    if($text.Length -gt 253 -or $text -notmatch '^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$'){throw '请输入有效的完整域名。'}
    $address=$null;if([Net.IPAddress]::TryParse($text,[ref]$address)){throw '网站规则使用域名，暂不支持 IP 地址规则。'}
    return $text
}
function Set-WebsiteRules($Entries,[string]$ExpectedRevision) {
    Use-ChangeLock {
        $snapshot=Get-RuleMaintenanceSnapshot ''
        if(-not $ExpectedRevision -or $snapshot.Files['app-rules.json'].TextHash -cne $ExpectedRevision){throw '网站或程序规则已改变，请重新打开网站规则后再保存。'}
        if(@($Entries).Count -gt 128){throw '网站规则最多 128 条。'}
        $rules=@();$keys=@{};$ids=@{}
        foreach($entry in @($Entries)){
            Assert-ManagedRoute $entry.Route
            $domain=ConvertTo-WebsiteDomain $entry.Domain
            if($entry.Match -notin @('exact','suffix')){throw '请选择精确域名或包含子域名。'}
            $scope='global'
            if($entry.Executable){$ingress=$snapshot.Engine.programIngresses|Where-Object {$_.path -ieq $entry.Executable}|Select-Object -First 1;if(-not $ingress){throw '请先为这个程序设置线路，建立固定入口，再添加程序网站例外。'};$scope=$ingress.id}
            $key=$scope+'|'+$entry.Match+'|'+$domain;if($keys.ContainsKey($key)){throw '同一范围存在重复的网站规则，请合并后保存。'};$keys[$key]=$true
            $id=[string]$entry.Id;if(-not $id){$id=[Guid]::NewGuid().ToString('N')}
            if($id -cnotmatch '^[a-f0-9]{32}$' -or $ids.ContainsKey($id)){throw '网站规则标识无效或重复，请重新添加该行。'};$ids[$id]=$true
            $rules+=@([pscustomobject]@{id=$id;scope=$scope;type=$(if($entry.Match -eq 'exact'){'domain'}else{'suffix'});domain=$domain;route=$entry.Route})
        }
        Ensure-ManagedGateway|Out-Null
        $before=Get-RoutingSnapshot
        $originalSites=ConvertTo-RoutingComparableValue @($snapshot.Engine.siteRules|Where-Object {$_})|ConvertTo-Json -Depth 16 -Compress
        $currentSites=ConvertTo-RoutingComparableValue @($before.siteRules|Where-Object {$_})|ConvertTo-Json -Depth 16 -Compress
        if($originalSites -cne $currentSites){throw '入口启动期间网站规则已改变，请重新打开规则后保存。'}
        $originalIngresses=ConvertTo-RoutingComparableValue @($snapshot.Engine.programIngresses|Where-Object {$_})|ConvertTo-Json -Depth 16 -Compress
        $currentIngresses=ConvertTo-RoutingComparableValue @($before.programIngresses|Where-Object {$_})|ConvertTo-Json -Depth 16 -Compress
        if($originalIngresses -cne $currentIngresses){throw '入口启动期间程序入口已改变，请重新打开规则后保存。'}
        $next=Copy-RoutingSnapshot $before;$next.siteRules=$rules
        $verify={$live=Invoke-AppRouter @{action='status'};if(-not $live.available -or -not $live.siteRulesLoaded){throw '网站规则未通过引擎实读校验。'}}
        $backup=Invoke-ManagedRoutingChange $before $next $verify
        [pscustomobject]@{Backup=$backup;Message='网站规则已载入并核对。进入流向的新连接按域名选择出口；请刷新页面，已有连接不会被自动断开。'}
    }
}

# Migration writes share the same exclusive file CAS used by explicit rule maintenance.
function Set-MigrationJson([string]$Path,$Value,[string]$ExpectedHash) {
    $before=Read-RuleMaintenanceFile $Path
    if($before.TextHash -cne $ExpectedHash){throw '代理配置在迁移期间已改变，保留最新内容。'}
    $bytes=ConvertTo-RuleMaintenanceBytes $Value
    Set-RuleMaintenanceFile $before $bytes $false
    Get-RuleMaintenanceHash $bytes
}
function Restore-MigrationFile($Original,[string]$OwnedHash) {
    $current=Read-RuleMaintenanceFile $Original.Path
    if($current.TextHash -cne $OwnedHash){throw '迁移文件已被外部更改，未覆盖最新内容。'}
    Set-RuleMaintenanceFile $current $Original.Bytes (-not $Original.Exists)
}
