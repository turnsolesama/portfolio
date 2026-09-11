# The session journal is written before Windows points at the owned listener.
function Get-IndependentSessionPath {Join-Path $script:DataRoot 'gateway-session.json'}
function Test-SessionProcess($ProcessId,$Ticks) {
    try{$p=[Diagnostics.Process]::GetProcessById([int]$ProcessId);try{return $p.StartTime.ToUniversalTime().Ticks.ToString() -eq [string]$Ticks}finally{$p.Dispose()}}catch{return $false}
}
function Get-ProcessStartTicks([int]$ProcessId) {$p=[Diagnostics.Process]::GetProcessById($ProcessId);try{$p.StartTime.ToUniversalTime().Ticks.ToString()}finally{$p.Dispose()}}
function Test-RecoveryEndpoint([string]$Endpoint) {
    if(-not $Endpoint){return $false}
    try{
        $raw=$Endpoint;if($raw -notmatch '^[a-z]+://'){$raw='http://'+$raw};$uri=[uri]$raw
        if($uri.Host -notin @('localhost','127.0.0.1','[::1]','::1')){return $true}
        $tcp=New-Object Net.Sockets.TcpClient
        try{$connect=$tcp.ConnectAsync($uri.Host.Trim('[',']'),$uri.Port);return ($connect.Wait(500) -and $tcp.Connected)}finally{$tcp.Dispose()}
    }catch{return $false}
}
function Test-SameRecoveryEndpoint([string]$First,[string]$Second) {
    if(-not $First -or -not $Second){return $false}
    try{
        $a=$First;$b=$Second;if($a -notmatch '^[a-z]+://'){$a='http://'+$a};if($b -notmatch '^[a-z]+://'){$b='http://'+$b}
        $a=[uri]$a;$b=[uri]$b;$firstHost=$a.Host.Trim('[',']').ToLowerInvariant();$secondHost=$b.Host.Trim('[',']').ToLowerInvariant()
        if($firstHost -in @('localhost','127.0.0.1','::1')){$firstHost='loopback'};if($secondHost -in @('localhost','127.0.0.1','::1')){$secondHost='loopback'}
        return ($firstHost -ceq $secondHost -and $a.Port -eq $b.Port)
    }catch{return $false}
}
function New-ExitRecoveryPlan($Session,$CurrentSystem,$CurrentEnv) {
    $system=$CurrentSystem
    if(Test-SameSnapshot $CurrentSystem $Session.TargetSystem){
        $system=$Session.BeforeSystem
        if(($system.Flags -band 2) -and ((Test-SameRecoveryEndpoint $system.Server $Session.TargetSystem.Server) -or -not (Test-RecoveryEndpoint $system.Server))){$system=[pscustomobject]@{Flags=1;Server='';Bypass=$system.Bypass}}
    }
    $values=[ordered]@{}
    foreach($name in $script:ProxyNames){
        $values[$name]=$CurrentEnv.$name
        if([string]$CurrentEnv.$name -ceq [string]$Session.TargetEnv.$name){
            $values[$name]=$Session.BeforeEnv.$name
            if($name -ne 'NO_PROXY' -and $values[$name] -and ((Test-SameRecoveryEndpoint $values[$name] $Session.TargetSystem.Server) -or -not (Test-RecoveryEndpoint $values[$name]))){$values[$name]=$null}
        }
    }
    [pscustomobject]@{System=$system;Environment=[pscustomobject]$values}
}
function Restore-IndependentSession([string]$ExpectedSession='') {
    Write-LifecycleEvent 'restore-request' 'stop-or-failure'
    $outcome=[pscustomobject]@{Restored=$false}
    try { Use-ChangeLock {
        $path=Get-IndependentSessionPath
        if(-not (Test-Path -LiteralPath $path)){return}
        $session=Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
        if($ExpectedSession -and [string]$session.Started -cne $ExpectedSession){return}
        $before=Get-SystemSnapshot;$envBefore=Get-UserProxyEnv;$plan=New-ExitRecoveryPlan $session $before $envBefore
        if(-not (Test-SameSnapshot $before (Get-SystemSnapshot)) -or -not (Test-SameEnv $envBefore (Get-UserProxyEnv))){throw '恢复期间网络设置发生变化，稍后重试。'}
        # Restore Windows first. Never stop a core while Windows still points at it.
        if(-not (Test-SameSnapshot $before $plan.System)){Set-SystemSnapshot $plan.System}
        # A system setter can yield to another proxy client. Re-read environment
        # ownership at the point of writing instead of replaying the old snapshot.
        $envBefore=Get-UserProxyEnv
        $plan.Environment=(New-ExitRecoveryPlan $session $plan.System $envBefore).Environment
        if(-not (Test-SameEnv $envBefore $plan.Environment)){Set-UserProxyEnv $plan.Environment}
        if(-not (Test-SameSnapshot (Get-SystemSnapshot) $plan.System) -or -not (Test-SameEnv (Get-UserProxyEnv) $plan.Environment)){throw '退出恢复尚未通过实读校验，内核继续运行。'}
        $archive=Join-Path $script:DataRoot ('backups\gateway-exit-'+(Get-Date -Format 'yyyyMMdd-HHmmss-fff')+'.json')
        Write-LocalJson $archive $session
        [IO.File]::WriteAllText((Join-Path $script:DataRoot 'gateway\stop'),'stop')
        # Let the owning supervisor stop its current child, including a restarted core.
        # Old session CorePID is insufficient after automatic recovery.
        if($session.SupervisorPID){
            $deadline=[DateTime]::UtcNow.AddSeconds(12)
            while((Test-SessionProcess $session.SupervisorPID $session.SupervisorStart) -and [DateTime]::UtcNow -lt $deadline){Start-Sleep -Milliseconds 100}
            if(Test-SessionProcess $session.SupervisorPID $session.SupervisorStart){throw '网络设置已恢复，但内核停止尚未确认；会话记录保留，请重试停止。'}
        }
        # A crashed supervisor can leave its latest child alive. Verify PID, parent,
        # start time and configured executable before stopping that tracked child.
        if($session.SupervisorPID){
            $processFile=Join-Path $script:DataRoot 'gateway\process.json'
            if(Test-Path -LiteralPath $processFile){
                $tracked=Get-Content -LiteralPath $processFile -Raw -Encoding UTF8|ConvertFrom-Json
                if($tracked.supervisor -eq $session.SupervisorPID -and $tracked.core){
                    $running=Get-CimInstance Win32_Process -Filter ('ProcessId = '+[int]$tracked.core) -ErrorAction SilentlyContinue
                    if($running){
                        $coreProfile=Get-Profile (Get-GatewayKey)
                        $ownedProcess=[Diagnostics.Process]::GetProcessById([int]$tracked.core)
                        try{
                            # Retain the process handle through validation and kill, so a
                            # rapidly reused PID cannot redirect termination to another process.
                            [void]$ownedProcess.Handle
                            $ticks=$ownedProcess.StartTime.ToUniversalTime().Ticks.ToString()
                            $expectedTicks=$tracked.coreStartTicks
                            if(-not $expectedTicks -and $tracked.core -eq $session.CorePID){$expectedTicks=$session.CoreStart}
                            if(-not $expectedTicks -or $ticks -cne [string]$expectedTicks -or $running.ParentProcessId -ne $session.SupervisorPID -or $running.ExecutablePath -ine $coreProfile.CorePath -or ($tracked.supervisorStartTicks -and [string]$tracked.supervisorStartTicks -cne [string]$session.SupervisorStart)){throw '内核身份已变化或缺少精确启动记录，未结束未知进程；请检查会话记录。'}
                            $ownedProcess.Kill()
                            if(-not $ownedProcess.WaitForExit(3000)){throw '内核停止尚未确认；会话记录保留。'}
                            Write-LifecycleEvent 'orphan-core-stop' 'verified-session-child'
                        }finally{$ownedProcess.Dispose()}
                    }
                }
            }
        }
        foreach($kind in @('Core')){
            $pidKey=$kind+'PID';$ticksKey=$kind+'Start'
            if($session.$pidKey -and (Test-SessionProcess $session.$pidKey $session.$ticksKey)){
                $ownedProcess=[Diagnostics.Process]::GetProcessById([int]$session.$pidKey)
                try{[void]$ownedProcess.Handle;if($ownedProcess.StartTime.ToUniversalTime().Ticks.ToString() -ceq [string]$session.$ticksKey){$ownedProcess.Kill();if(-not $ownedProcess.WaitForExit(3000)){throw '内核停止尚未确认；会话记录保留。'}}}finally{$ownedProcess.Dispose()}
            }
        }
        [IO.File]::Delete($path)
        # A completed recovery no longer needs the next-logon safety net.
        $key='HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce'
        $savedCommand=$null
        try{$savedCommand=Get-ItemPropertyValue -LiteralPath $key -Name 'FlowSwitchRecovery' -ErrorAction Stop}catch{}
        if($session.RecoveryCommand -and $savedCommand -ceq $session.RecoveryCommand){Remove-ItemProperty -LiteralPath $key -Name 'FlowSwitchRecovery' -ErrorAction SilentlyContinue}
        $outcome.Restored=$true
    }
    if(-not $outcome.Restored){return}
    Write-LifecycleEvent 'restore-complete' 'settings-verified'
    Write-LocalJson (Join-Path $script:DataRoot 'gateway\recovery-status.json') ([pscustomobject]@{phase='restored';at=[DateTimeOffset]::UtcNow.ToString('o')})
    }catch{
        Write-LifecycleEvent 'restore-failed' 'settings-or-stop-unverified'
        try{Write-LocalJson (Join-Path $script:DataRoot 'gateway\recovery-status.json') ([pscustomobject]@{phase='restore-failed';at=[DateTimeOffset]::UtcNow.ToString('o')})}catch{}
        throw
    }
}
function Start-IndependentProtection([int]$OwnerPID,$BeforeSystem,$BeforeEnv,$TargetSystem,$TargetEnv) {
    if($OwnerPID -le 0){$OwnerPID=$PID}
    $owned=Get-Content -LiteralPath (Join-Path $script:DataRoot 'gateway\process.json') -Raw -Encoding UTF8|ConvertFrom-Json
    $session=[pscustomobject]@{CorePID=$owned.core;CoreStart=(Get-ProcessStartTicks $owned.core);SupervisorPID=$owned.supervisor;SupervisorStart=(Get-ProcessStartTicks $owned.supervisor);Version=1;OwnerPID=$OwnerPID;OwnerStart=(Get-ProcessStartTicks $OwnerPID);BeforeSystem=$BeforeSystem;BeforeEnv=$BeforeEnv;TargetSystem=$TargetSystem;TargetEnv=$TargetEnv;Started=(Get-Date).ToString('o')}
    Write-LifecycleEvent 'session-start' 'entry-ready'
    Write-LocalJson (Join-Path $script:DataRoot 'gateway\recovery-status.json') ([pscustomobject]@{phase='protected';at=[DateTimeOffset]::UtcNow.ToString('o')})
    $path=Get-IndependentSessionPath
    if(Test-Path -LiteralPath $path){$existing=Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json;if(Test-SessionProcess $existing.OwnerPID $existing.OwnerStart){throw '已有独立分流会话，请先退出原窗口。'};Restore-IndependentSession}
    Write-LocalJson $path $session
    $watcher=Join-Path $script:Root 'GatewayWatchdog.ps1'
    $shell=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $args='-NoProfile -ExecutionPolicy Bypass -File "'+$watcher+'" -DataDirectory "'+$script:DataRoot+'"'
    $runOnce='"'+$shell+'" '+$args+' -RecoverOnly'
    $session | Add-Member NoteProperty RecoveryCommand $runOnce
    Write-LocalJson $path $session
    [void](New-Item -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce' -Force)
    Set-ItemProperty -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce' -Name 'FlowSwitchRecovery' -Value $runOnce
    $ready=Join-Path $script:DataRoot 'gateway\watchdog-ready.json';if(Test-Path -LiteralPath $ready){[IO.File]::Delete($ready)}
    Start-Process -FilePath $shell -ArgumentList $args -WindowStyle Hidden
    for($i=0;$i -lt 50;$i++){if(Test-Path -LiteralPath $ready){$r=Get-Content -LiteralPath $ready -Raw -Encoding UTF8 | ConvertFrom-Json;if($r.Session -eq $session.Started -and (Test-SessionProcess $r.PID $r.StartTicks)){return}};Start-Sleep -Milliseconds 100}
    throw '退出恢复保护未启动，尚未更改 Windows 代理。'
}
function Enable-IndependentGateway([int]$OwnerPID=0,[string]$InitialRoute='',[switch]$UnifiedSwitch,[switch]$AllowMigration) {
    Use-ChangeLock {
        $script:Profiles=Read-ProfileSettings
        if($UnifiedSwitch -and -not $AllowMigration -and $script:Profiles.Routing.Adapter -ne 'standalone'){throw '入口配置已经变化，请刷新后重试；未自动迁移其他引擎。'}
        if($script:Profiles.Routing.Adapter -eq 'standalone'){
            $sessionPath=Get-IndependentSessionPath
            if(Test-Path -LiteralPath $sessionPath){$session=Get-Content -LiteralPath $sessionPath -Raw -Encoding UTF8 | ConvertFrom-Json;if(Test-SessionProcess $session.OwnerPID $session.OwnerStart){
                $live=Invoke-AppRouter @{action='status'};$life=Get-GatewayLifecycle
                if($live.available -and $life.phase -eq 'ready'){return [pscustomobject]@{Message='独立入口与控制接口已就绪，退出恢复保护正在运行。'}}
                if($life.phase -in @('starting','restarting','degraded')){return [pscustomobject]@{Message='独立入口正在恢复，尚未就绪；请等待，暂勿启动登录。'}}
                throw '已有会话的入口未就绪，不能报告已启用。请先通过托盘停止代理服务；若恢复失败，请按提示处理并保留会话日志。'
            };Restore-IndependentSession}
        }
        # Derive the migration plan and its CAS/rollback images from the same bytes.
        # A fresh hash captured after probing must never authorize a plan made from older records.
        $migration=Get-RuleMaintenanceSnapshot
        $old=Get-RuleMaintenanceProfiles $migration;$script:Profiles=$old
        if($UnifiedSwitch -and -not $AllowMigration -and $old.Routing.Adapter -ne 'standalone'){throw '入口配置已经变化，请刷新后重试；未自动迁移其他引擎。'}
        $engine=$migration.Engine
        if(-not $engine.installed -and (@($engine.entries).Count -gt 0 -or @($engine.programIngresses|Where-Object {$_}).Count -gt 0 -or @($engine.siteRules|Where-Object {$_}).Count -gt 0 -or $engine.defaultRoute)){throw '程序规则状态不一致，请先从备份恢复规则文件。'}
        foreach($entry in @($migration.Launch.entries)){
            if(-not [IO.Path]::IsPathRooted($entry.path) -or $entry.path -notmatch '(?i)\.exe$' -or $entry.path -match '["\r\n\x00]' -or $entry.adapter -ne 'chromium' -or $entry.route -notin (@('Direct','Follow')+(Get-ProfileKeys))){throw '程序启动代理配置无效，请从备份恢复。'}
        }
        $rules=[pscustomobject]@{entries=@($engine.entries);defaultRoute=$engine.defaultRoute;installed=[bool]$engine.installed;programIngresses=@($engine.programIngresses|Where-Object {$_});siteRules=@($engine.siteRules|Where-Object {$_});launchEntries=@($migration.Launch.entries)}
        $originalConfig=$migration.Files['config.json'];$originalState=$migration.Files['app-rules.json'];$originalLaunch=$migration.Files['program-proxies.json']
        $statePath=$originalState.Path
        $before=Get-SystemSnapshot;$beforeEnv=Get-UserProxyEnv;$selection=Get-Selection
        $client=Get-ClientInterference
        if($client.Tun -or $client.Guard){throw '启用独立入口前，请关闭其他客户端的 TUN 和代理守卫；保留上游代理服务运行。'}
        $upstreams=@($old.Profiles | Where-Object {$_.Id -ne $old.Routing.ProfileId -or $old.Routing.Adapter -ne 'standalone'})
        if(-not $upstreams.Count){throw '请先添加至少一个上游代理入口。'}
        if($UnifiedSwitch){
            if($InitialRoute -notin (@('Direct')+@($upstreams|ForEach-Object Id))){throw '请选择一个有效上游或直连，未启动独立入口。'}
            if($InitialRoute -ne 'Direct' -and -not (Test-ProxyRoute $InitialRoute -Fast).Usable){throw '所选代理检测未通过，保留原配置，未启动独立入口。'}
        }
        $node=Get-NodeRuntimePath
        $core=Get-IndependentCoreSource $old
        $directory=Join-Path $script:DataRoot 'gateway';$runtime=Join-Path $directory 'runtime';[void][IO.Directory]::CreateDirectory($runtime)
        $ownedCore=Join-Path $runtime 'FlowSwitch.Core.exe';$ownedNode=Join-Path $runtime 'node.exe'
        if(-not (Test-Path -LiteralPath $ownedCore)){Copy-Item -LiteralPath $core -Destination $ownedCore}
        if(-not (Test-Path -LiteralPath $ownedNode)){Copy-Item -LiteralPath $node -Destination $ownedNode}
        $gateway=$old.Profiles | Where-Object {$_.Id -eq $old.Routing.ProfileId -and $old.Routing.Adapter -eq 'standalone'} | Select-Object -First 1
        if(-not $gateway){$port=18790;while(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue){$port++;if($port -gt 18890){throw '没有可用的独立入口端口'}};$gateway=[pscustomobject]@{Id=('fs'+[Guid]::NewGuid().ToString('N').Substring(0,10));Name='FlowSwitch 独立入口';Protocol='http';Host='127.0.0.1';Port=$port;CorePath=$ownedCore;AppPath='';AutoPort=$false}}
        $new=$old | ConvertTo-Json -Depth 12 | ConvertFrom-Json
        $new.Profiles=@($upstreams)+@($gateway)
        $new.Routing=[pscustomobject]@{Adapter='standalone';ProfileId=$gateway.Id;UnifiedMode='gateway';Failover=[pscustomobject]@{Enabled=$true;Order=@($upstreams|ForEach-Object Id);AllowDirect=$false}}
        if($old.Routing.Adapter -eq 'standalone'){$new.Routing.Failover=$old.Routing.Failover}
        $new=ConvertTo-ValidProfileSettings $new
        $route=$rules.defaultRoute;if(-not $route){$route=Get-SystemKey $before};if($route -notin (@('Direct')+@($upstreams|ForEach-Object Id))){$route=$upstreams[0].Id}
        $nextIngresses=@($rules.programIngresses|Where-Object {$_});$nextSites=@($rules.siteRules|Where-Object {$_});$nextEntries=@($rules.entries);$nextLaunch=@($rules.launchEntries)
        if($InitialRoute){$route=$InitialRoute}
        if($UnifiedSwitch){$nextIngresses=@($nextIngresses|ForEach-Object {$copy=$_|ConvertTo-Json -Depth 16|ConvertFrom-Json;$copy.route='Follow';$copy});$route=$InitialRoute;$nextEntries=@();$nextLaunch=@($rules.launchEntries|Where-Object {$_}|ForEach-Object {[pscustomobject]@{path=$_.path;route='Follow';adapter=$_.adapter;identity=$_.identity}})}
        foreach($original in @($originalConfig,$originalState,$originalLaunch)){
            if((Read-RuleMaintenanceFile $original.Path).Hash -cne $original.Hash){throw '代理配置或程序记录在预检期间已改变，保留最新内容；请刷新后重试。'}
        }
        $stash=Join-Path $script:BackupDir ('independent-migration-'+(Get-Date -Format 'yyyyMMdd-HHmmss-fff')+'.json')
        Write-LocalJson $stash ([pscustomobject]@{Profiles=$old;Rules=$rules;System=$before;Environment=$beforeEnv;Selection=$selection})
        $switched=$false;$removed=$false;$started=$false;$offlineDetach=$null
        $ownedConfigHash='';$ownedStateHash='';$ownedLaunchHash=''
        try{
            if($old.Routing.Adapter -ne 'standalone' -and $rules.installed){
                $external=Invoke-AppRouter @{action='status'} -TimeoutMilliseconds 9000
                if($external.available){
                    $detached=Invoke-AppRouter @{action='replace';entries=@();defaultRoute=$null;expectedStateHash=$originalState.TextHash;expectedSettingsHash=$originalConfig.TextHash}
                }else{
                    Write-OperationProgress '原分流引擎已离线，正在核对并备份本工具拥有的旧规则…'
                    $detached=Invoke-AppRouter @{action='detach-offline';expectedStateHash=$originalState.TextHash;expectedSettingsHash=$originalConfig.TextHash}
                    $offlineDetach=$detached
                }
                if(-not $detached.stateHash){throw '旧规则撤离未返回写入归属，未继续改变入口。'}
                $ownedStateHash=[string]$detached.stateHash;$removed=$true
            }
            $ownedConfigHash=Set-MigrationJson $script:ConfigPath $new $originalConfig.TextHash;$script:Profiles=$new
            if($old.Routing.Adapter -ne 'standalone'){
                $priorStateHash=$originalState.TextHash;if($ownedStateHash){$priorStateHash=$ownedStateHash}
                $ownedStateHash=Set-MigrationJson $statePath ([pscustomobject]@{version=3;installed=$false;entries=@();defaultRoute=$null;programIngresses=@();siteRules=@()}) $priorStateHash
            }else{$ownedStateHash=$originalState.TextHash}
            $started=$true;Invoke-AppRouter @{action='start'} | Out-Null
            # The file CAS uses a literal missing sentinel; the controller protocol hashes that sentinel.
            $controllerStateHash=$ownedStateHash
            if($controllerStateHash -ceq '<missing>'){$controllerStateHash=Get-RuleMaintenanceHash ([Text.Encoding]::UTF8.GetBytes('<missing>'))}
            $applied=Invoke-AppRouter @{action='replace';entries=$nextEntries;defaultRoute=$route;programIngresses=$nextIngresses;siteRules=$nextSites;resetDefaultSelection=([bool]$UnifiedSwitch);expectedStateHash=$controllerStateHash;expectedSettingsHash=$ownedConfigHash}
            if(-not $applied.stateHash){throw '新入口未返回规则写入归属，尚未更改 Windows 入口。'}
            $ownedStateHash=[string]$applied.stateHash
            if($UnifiedSwitch){
                $live=Invoke-AppRouter @{action='status'}
                if(-not $live.available -or -not $live.defaultLoaded -or $live.effectiveDefaultRoute -ne $route){throw '启动后的实际出口未通过核验，尚未切换系统入口。'}
                if($route -ne 'Direct' -and -not (Test-ProxyRoute $gateway.Id -Fast).Usable){throw '启动后的实际代理请求未通过，尚未切换系统入口。'}
                # Unified switching retains every saved path; no shortcut removal is needed here.
                $nextLaunchState=$migration.Launch|ConvertTo-Json -Depth 16|ConvertFrom-Json;$nextLaunchState.entries=@($nextLaunch)
                $ownedLaunchHash=Set-MigrationJson $originalLaunch.Path $nextLaunchState $originalLaunch.TextHash
            }
            $target=[pscustomobject]@{Flags=3;Server=(Get-EndpointAddress $gateway);Bypass=$before.Bypass};$targetEnv=New-EnvTarget $beforeEnv $gateway.Id
            Start-IndependentProtection $OwnerPID $before $beforeEnv $target $targetEnv
            $switched=$true
            $transactionBackup=Invoke-ProxyTransaction $target $targetEnv ([pscustomobject]@{Key=$gateway.Id;NetworkKey=$route;Unified=$true;ChangedAt=(Get-Date).ToString('o')}) $before $beforeEnv -BackupRouting $(if($UnifiedSwitch){$rules}else{$null})
            if($UnifiedSwitch){return [pscustomobject]@{Key=$route;Backup=$transactionBackup;Message=('独立入口已启动，新连接的统一线路已核验为「'+(Get-RouteName $route)+'」。已有程序可能保留旧代理地址；首次接入的程序需从代理入口重新打开。'+$(if($live.partialIngressFailure){' 另有程序固定入口未就绪，请修复对应入口；这些程序尚未恢复。'})+$(if($client.SystemProxy){' 上游客户端仍开启系统代理，随后启动或退出它可能改写入口；建议关闭其系统代理开关并保留服务。'}))}}
            [pscustomobject]@{Message='独立分流已启用。代理失效会自动接替；关闭窗口将驻留托盘；通过托盘「停止代理服务并退出」恢复网络并关闭内核。';Backup=$stash}
        }catch{
            $failure=$_.Exception.Message
            $rollbackFailures=@()
            if($ownedLaunchHash){
                try{Restore-MigrationFile $originalLaunch $ownedLaunchHash}
                catch{$rollbackFailures+='程序启动记录未能回滚，已保留当前内容'}
            }
            try{
                if($switched -or (Test-Path -LiteralPath (Get-IndependentSessionPath))){Restore-IndependentSession}
                if($started){
                    [IO.File]::WriteAllText((Join-Path $directory 'stop'),'stop')
                    $ownedProcessFile=Join-Path $directory 'process.json'
                    if(Test-Path -LiteralPath $ownedProcessFile){
                        $ownedProcessState=Get-Content -LiteralPath $ownedProcessFile -Raw -Encoding UTF8|ConvertFrom-Json
                        $stopDeadline=[DateTime]::UtcNow.AddSeconds(12)
                        while((Test-SessionProcess $ownedProcessState.supervisor $ownedProcessState.supervisorStartTicks) -and [DateTime]::UtcNow -lt $stopDeadline){Start-Sleep -Milliseconds 100}
                        if(Test-SessionProcess $ownedProcessState.supervisor $ownedProcessState.supervisorStartTicks){throw '本次自有内核停止尚未确认，保留迁移配置以便恢复'}
                    }
                }
                if($ownedStateHash -and (Read-RuleMaintenanceFile $statePath).TextHash -cne $ownedStateHash){throw '程序规则已被外部改动，未覆盖关联配置'}
                if($ownedConfigHash){Restore-MigrationFile $originalConfig $ownedConfigHash}
                $script:Profiles=$old
                if($offlineDetach){
                    # Restore only our exact detached state image before restoring the paired external files.
                    $current=Read-RuleMaintenanceFile $statePath
                    if($current.TextHash -cne $ownedStateHash){throw '程序规则已被外部改动，未覆盖最新规则'}
                    Set-RuleMaintenanceFile $current ([Text.Encoding]::UTF8.GetBytes([string]$offlineDetach.stateText)) $false
                    Invoke-AppRouter @{action='restore-offline-detach';backup=$offlineDetach.backup;expectedSettingsHash=$originalConfig.TextHash}|Out-Null
                }elseif($removed){
                    Invoke-AppRouter @{action='replace';entries=@($rules.entries);defaultRoute=$rules.defaultRoute;expectedStateHash=$ownedStateHash;expectedSettingsHash=$originalConfig.TextHash}|Out-Null
                }elseif($ownedStateHash){Restore-MigrationFile $originalState $ownedStateHash}
            }catch{$rollbackFailures+='入口或关联配置未能完全恢复'}
            if($rollbackFailures.Count){throw ($failure+'；迁移回滚未完成（'+($rollbackFailures -join '；')+'），保留外部最新设置和本机备份：'+$stash+'。请检查原引擎和入口状态。')}
            throw ($failure+'；已恢复启用前设置。')
        }
    }
}


# Only fixed event codes and numeric counters are persisted; never log exception text or URLs.
function Write-LifecycleEvent([string]$Event,[string]$Reason='',[int]$Attempt=0) {
    if($Event -notmatch '^[a-z-]{1,64}$' -or ($Reason -and $Reason -notmatch '^[a-z-]{1,64}$')){return}
    try {
        $directory=Join-Path $script:DataRoot 'gateway';[void][IO.Directory]::CreateDirectory($directory)
        $file=Join-Path $directory 'lifecycle-session.jsonl'
        $stream=New-Object IO.FileStream($file,[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::Read)
        try {
            if($stream.Length -gt 262144){$stream.SetLength(0)}
            [void]$stream.Seek(0,[IO.SeekOrigin]::End)
            $row=[ordered]@{at=[DateTimeOffset]::UtcNow.ToString('o');version=$script:ProductVersion;event=$Event;reason=$Reason;pid=$PID;attempt=$Attempt}
            $bytes=[Text.Encoding]::UTF8.GetBytes(($row|ConvertTo-Json -Compress)+"`n");$stream.Write($bytes,0,$bytes.Length)
        }finally{$stream.Dispose()}
    }catch{} # Logging failure must not bring down the proxy.
}
function Get-GatewayLifecycle {
    $file=Join-Path $script:DataRoot 'gateway\lifecycle-state.json'
    try{Get-Content -LiteralPath $file -Raw -Encoding UTF8|ConvertFrom-Json}catch{return $null}
}
function Test-GatewayRecoveryGrace($Session,[int]$Misses) {
    if(-not $Session.SupervisorPID -or -not (Test-SessionProcess $Session.SupervisorPID $Session.SupervisorStart)){return $false}
    $life=Get-GatewayLifecycle
    if(-not $life -or $life.supervisor -ne $Session.SupervisorPID -or $life.phase -notin @('ready','starting','restarting','degraded') -or $life.attempt -gt 3 -or $Misses -gt 45){return $false}
    try{$age=([DateTimeOffset]::UtcNow-[DateTimeOffset]::Parse($life.updatedAt)).TotalSeconds;return ($age -ge 0 -and $age -lt 6)}catch{return $false}
}
function Wait-ManagedProxyReady([string]$Key,[int]$TimeoutMilliseconds=12000) {
    if($script:Profiles.Routing.Adapter -ne 'standalone' -or $Key -ne (Get-GatewayKey)){return}
    $deadline=[DateTime]::UtcNow.AddMilliseconds($TimeoutMilliseconds)
    do {
        $life=Get-GatewayLifecycle
        # A stale stopped journal may precede a concurrent fresh UI start. Wait for the bounded deadline.
        if(Get-Listener (Get-Profile $Key)){
            try{$remaining=[Math]::Max(250,[Math]::Min(1500,[int]($deadline-[DateTime]::UtcNow).TotalMilliseconds));$state=Invoke-AppRouter @{action='status'} -TimeoutMilliseconds $remaining;if($state.available -and $state.defaultLoaded -and $state.effectiveDefaultRoute -notin @('Blocked','Unknown',$null,'')){return}}catch{}
        }
        Start-Sleep -Milliseconds 200
    }while([DateTime]::UtcNow -lt $deadline)
    Write-LifecycleEvent 'managed-launch-blocked' 'entry-not-ready'
    throw 'FlowSwitch 固定入口未就绪或出口已暂停，未启动应用。请先打开流向并启动独立分流，等待入口和出口就绪后再重试。已经运行的应用可能保留旧代理地址；保存工作后完整退出并重新打开该应用。'
}
function Get-EntryLifecycleWarnings($Snapshot,$Environment,$Listeners) {
    $gateway=Get-GatewayKey
    if($script:Profiles.Routing.Adapter -ne 'standalone' -or -not $gateway){return @()}
    $own=Get-Profile $gateway;$references=@()
    if(($Snapshot.Flags -band 2) -and (Get-EndpointKey $Snapshot.Server) -eq $gateway){$references+='Windows 系统代理'}
    foreach($name in @('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY')){if((Get-EndpointKey $Environment.$name) -eq $gateway){$references+=$name}}
    $row=$Listeners|Where-Object Key -eq $gateway|Select-Object -First 1
    $messages=@();$life=Get-GatewayLifecycle
    if($references.Count -and -not $row.Ready){$messages+=('固定入口 '+(Get-EndpointAddress $own)+' 未监听，但 '+($references -join '、')+' 仍指向它。请先启动流向并等待入口就绪，再重试登录；尚未到达认证接口。')}
    if($life.phase -eq 'restarting'){$messages+='内核异常退出，正在有限重启；入口恢复前请暂停启动登录。'}
    if($life.phase -eq 'failed'){$messages+='独立内核恢复失败。请检查生命周期记录；已运行应用可能缓存旧入口，保存工作后完整重开应用。'}
    if($references.Count -or $life.phase -in @('failed','stopped')){$messages+='恢复系统代理不会刷新已运行应用的环境变量或缓存。若仍报旧端口拒绝连接，请保存工作后完整重开应用及其启动器；本工具不会结束它们。'}
    @($messages)
}
function ConvertTo-LoginDiagnostic([bool]$LocalReady,[string]$Protocol,[int]$ExitCode,[int]$ConnectCode,[int]$HttpCode) {
    $stage='local-entry';$message='本地入口不可用，请先启动代理服务并等待就绪。';$handshake=$false;$https=$false
    if($LocalReady){
        $handshake=($Protocol -eq 'http' -and $ConnectCode -eq 200) -or ($Protocol -eq 'socks5' -and $HttpCode -gt 0)
        $https=$ExitCode -eq 0 -and $HttpCode -ge 100 -and $handshake
        if($https){$stage='https-response';$message='HTTPS 请求已到达 Google OAuth 接口，HTTP '+$HttpCode+'；未发送令牌或登录请求，不代表账号登录成功。'}
        elseif($handshake){$stage='target-https';$message='代理握手成功，但目标 HTTPS / TLS 请求未完成。请检查出口、证书或目标可达性。'}
        else{$stage='proxy-handshake';$message='本地端口可连接，但代理握手未通过；端口占用或上游故障均可能导致此结果。'}
    }
    [pscustomobject]@{Version=$script:ProductVersion;Target='Google OAuth';Stage=$stage;LocalReady=$LocalReady;HandshakeReady=$handshake;HttpsReachable=$https;HttpCode=$HttpCode;ConnectCode=$ConnectCode;ExitCode=$ExitCode;AuthenticationVerified=$false;Message=$message}
}
function Test-LoginChain([string]$Key='') {
    if(-not $Key){$Key=Get-SystemKey (Get-SystemSnapshot)}
    if($Key -in @('Direct','Other','Unset') -or $Key -notin (Get-ProfileKeys)){throw '请先选择一个已配置的代理入口进行登录链路诊断。'}
    $profile=Get-Profile $Key
    if(-not (Get-Listener $profile -ProbeRemote)){return (ConvertTo-LoginDiagnostic $false $profile.Protocol 7 0 0)}
    $probe=$null
    try {
        # Fixed URL and HEAD only. No URL input, request body, authorization, cookie, or token.
        $probe=Start-HttpEndpointProbe $profile 'https://oauth2.googleapis.com/token'
        if(-not $probe.Process.WaitForExit(12000)){return (ConvertTo-LoginDiagnostic $true $profile.Protocol 28 0 0)}
        $parts=$probe.Output.Result.Trim() -split '\s+';$http=0;$connect=0
        if($parts.Count -ge 3){[void][int]::TryParse($parts[0],[ref]$http);[void][int]::TryParse($parts[2],[ref]$connect)}
        ConvertTo-LoginDiagnostic $true $profile.Protocol $probe.Process.ExitCode $connect $http
    }catch{ConvertTo-LoginDiagnostic $true $profile.Protocol -1 0 0}
    finally{if($probe){Close-HttpEndpointProbe $probe}}
}
