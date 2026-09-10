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
function New-ExitRecoveryPlan($Session,$CurrentSystem,$CurrentEnv) {
    $system=$CurrentSystem
    if(Test-SameSnapshot $CurrentSystem $Session.TargetSystem){
        $system=$Session.BeforeSystem
        if(($system.Flags -band 2) -and -not (Test-RecoveryEndpoint $system.Server)){$system=[pscustomobject]@{Flags=1;Server='';Bypass=$system.Bypass}}
    }
    $values=[ordered]@{}
    foreach($name in $script:ProxyNames){
        $values[$name]=$CurrentEnv.$name
        if([string]$CurrentEnv.$name -ceq [string]$Session.TargetEnv.$name){
            $values[$name]=$Session.BeforeEnv.$name
            if($name -ne 'NO_PROXY' -and $values[$name] -and -not (Test-RecoveryEndpoint $values[$name])){$values[$name]=$null}
        }
    }
    [pscustomobject]@{System=$system;Environment=[pscustomobject]$values}
}
function Restore-IndependentSession {
    Use-ChangeLock {
        $path=Get-IndependentSessionPath
        if(-not (Test-Path -LiteralPath $path)){return}
        $session=Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
        $before=Get-SystemSnapshot;$envBefore=Get-UserProxyEnv;$plan=New-ExitRecoveryPlan $session $before $envBefore
        if(-not (Test-SameSnapshot $before (Get-SystemSnapshot)) -or -not (Test-SameEnv $envBefore (Get-UserProxyEnv))){throw '恢复期间网络设置发生变化，稍后重试。'}
        # Restore Windows first. Never stop a core while Windows still points at it.
        if(-not (Test-SameSnapshot $before $plan.System)){Set-SystemSnapshot $plan.System}
        if(-not (Test-SameEnv $envBefore $plan.Environment)){Set-UserProxyEnv $plan.Environment}
        if(-not (Test-SameSnapshot (Get-SystemSnapshot) $plan.System) -or -not (Test-SameEnv (Get-UserProxyEnv) $plan.Environment)){throw '退出恢复尚未通过实读校验，内核继续运行。'}
        $archive=Join-Path $script:DataRoot ('backups\gateway-exit-'+(Get-Date -Format 'yyyyMMdd-HHmmss-fff')+'.json')
        Write-LocalJson $archive $session
        [IO.File]::WriteAllText((Join-Path $script:DataRoot 'gateway\stop'),'stop')
        foreach($kind in @('Core','Supervisor')){
            $pidKey=$kind+'PID';$ticksKey=$kind+'Start'
            if($session.$pidKey -and (Test-SessionProcess $session.$pidKey $session.$ticksKey)){Stop-Process -Id $session.$pidKey -ErrorAction SilentlyContinue}
        }
        [IO.File]::Delete($path)
        # A completed recovery no longer needs the next-logon safety net.
        $key='HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce'
        $savedCommand=$null
        try{$savedCommand=Get-ItemPropertyValue -LiteralPath $key -Name 'FlowSwitchRecovery' -ErrorAction Stop}catch{}
        if($session.RecoveryCommand -and $savedCommand -ceq $session.RecoveryCommand){Remove-ItemProperty -LiteralPath $key -Name 'FlowSwitchRecovery' -ErrorAction SilentlyContinue}
    }
}
function Start-IndependentProtection([int]$OwnerPID,$BeforeSystem,$BeforeEnv,$TargetSystem,$TargetEnv) {
    if($OwnerPID -le 0){$OwnerPID=$PID}
    $owned=Get-Content -LiteralPath (Join-Path $script:DataRoot 'gateway\process.json') -Raw -Encoding UTF8|ConvertFrom-Json
    $session=[pscustomobject]@{CorePID=$owned.core;CoreStart=(Get-ProcessStartTicks $owned.core);SupervisorPID=$owned.supervisor;SupervisorStart=(Get-ProcessStartTicks $owned.supervisor);Version=1;OwnerPID=$OwnerPID;OwnerStart=(Get-ProcessStartTicks $OwnerPID);BeforeSystem=$BeforeSystem;BeforeEnv=$BeforeEnv;TargetSystem=$TargetSystem;TargetEnv=$TargetEnv;Started=(Get-Date).ToString('o')}
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
function Enable-IndependentGateway([int]$OwnerPID=0) {
    Use-ChangeLock {
        $script:Profiles=Read-ProfileSettings
        if($script:Profiles.Routing.Adapter -eq 'standalone'){
            $sessionPath=Get-IndependentSessionPath
            if(Test-Path -LiteralPath $sessionPath){$session=Get-Content -LiteralPath $sessionPath -Raw -Encoding UTF8 | ConvertFrom-Json;if(Test-SessionProcess $session.OwnerPID $session.OwnerStart){return [pscustomobject]@{Message='独立分流入口已启用，退出恢复保护正在运行。'}};Restore-IndependentSession}
        }
        $old=$script:Profiles;$before=Get-SystemSnapshot;$beforeEnv=Get-UserProxyEnv;$rules=Get-RoutingSnapshot;$selection=Get-Selection
        $client=Get-ClientInterference
        if($client.Tun -or $client.Guard -or $client.SystemProxy){throw '启用独立入口前，请关闭 Clash 的 TUN 和代理守卫，并关闭各上游的系统代理开关；保留上游客户端运行。这样退出某个上游不会覆盖独立入口。'}
        $upstreams=@($old.Profiles | Where-Object {$_.Id -ne $old.Routing.ProfileId -or $old.Routing.Adapter -ne 'standalone'})
        if(-not $upstreams.Count){throw '请先添加至少一个上游代理入口。'}
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
        $stash=Join-Path $script:BackupDir ('independent-migration-'+(Get-Date -Format 'yyyyMMdd-HHmmss-fff')+'.json')
        Write-LocalJson $stash ([pscustomobject]@{Profiles=$old;Rules=$rules;System=$before;Environment=$beforeEnv;Selection=$selection})
        $switched=$false;$removed=$false
        try{
            if($old.Routing.Adapter -ne 'standalone' -and $rules.installed){Invoke-AppRouter @{action='replace';entries=@();defaultRoute=$null} | Out-Null;$removed=$true}
            Write-LocalJson $script:ConfigPath $new;$script:Profiles=$new
            if($old.Routing.Adapter -ne 'standalone'){Write-LocalJson (Join-Path $script:DataRoot 'app-rules.json') ([pscustomobject]@{version=2;installed=$false;entries=@();defaultRoute=$null})}
            Invoke-AppRouter @{action='start'} | Out-Null
            Invoke-AppRouter @{action='replace';entries=@($rules.entries);defaultRoute=$route} | Out-Null
            $target=[pscustomobject]@{Flags=3;Server=(Get-EndpointAddress $gateway);Bypass=$before.Bypass};$targetEnv=New-EnvTarget $beforeEnv $gateway.Id
            Start-IndependentProtection $OwnerPID $before $beforeEnv $target $targetEnv
            $switched=$true
            Invoke-ProxyTransaction $target $targetEnv ([pscustomobject]@{Key=$gateway.Id;NetworkKey=$route;Unified=$true;ChangedAt=(Get-Date).ToString('o')}) $before $beforeEnv | Out-Null
            [pscustomobject]@{Message='独立分流已启用。代理失效会自动接替；退出本窗口时先恢复网络再关闭内核。';Backup=$stash}
        }catch{
            $failure=$_.Exception.Message
            if($switched -or (Test-Path -LiteralPath (Get-IndependentSessionPath))){Restore-IndependentSession}
            [IO.File]::WriteAllText((Join-Path $directory 'stop'),'stop')
            Write-LocalJson $script:ConfigPath $old;$script:Profiles=$old
            Write-LocalJson (Join-Path $script:DataRoot 'app-rules.json') ([pscustomobject]@{version=2;installed=$false;entries=@();defaultRoute=$null})
            if($removed){Invoke-AppRouter @{action='replace';entries=@($rules.entries);defaultRoute=$rules.defaultRoute} | Out-Null}
            elseif($old.Routing.Adapter -eq 'standalone'){Write-LocalJson (Join-Path $script:DataRoot 'app-rules.json') ([pscustomobject]@{version=2;installed=$rules.installed;entries=@($rules.entries);defaultRoute=$rules.defaultRoute})}
            throw ($failure+'；已恢复启用前设置。')
        }
    }
}
