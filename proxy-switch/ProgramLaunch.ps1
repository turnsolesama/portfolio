# App-native proxy adapters. They configure the launched app, never Windows or other processes.
function Get-ProgramProxyAdapter([string]$Executable) {
    if(-not $Executable -or -not (Test-Path -LiteralPath $Executable -PathType Leaf)){return ''}
    $directory=[IO.Path]::GetDirectoryName($Executable)
    if((Test-Path -LiteralPath (Join-Path $directory 'resources.pak')) -and (Test-Path -LiteralPath (Join-Path $directory 'chrome_100_percent.pak'))){return 'chromium'}
    return ''
}
function Get-ProgramLaunchEntries {
    $path=Join-Path $script:DataRoot 'program-proxies.json'
    if(-not (Test-Path -LiteralPath $path)){return @()}
    $state=Get-Content -LiteralPath $path -Raw -Encoding UTF8|ConvertFrom-Json
    if($state.version -ne 1){throw '程序启动代理配置版本不兼容。'}
    foreach($entry in @($state.entries)){
        if(-not [IO.Path]::IsPathRooted($entry.path) -or $entry.path -notmatch '(?i)\.exe$' -or $entry.path -match '["\r\n\x00]' -or $entry.adapter -ne 'chromium' -or $entry.route -notin (@('Direct','Follow')+(Get-ProfileKeys))){throw '程序启动代理配置无效，请从备份恢复。'}
    }
    @($state.entries)
}
function Set-ProgramLaunchEntries($Entries) {
    $before=@(Get-ProgramLaunchEntries)
    Write-LocalJson (Join-Path $script:DataRoot 'program-proxies.json') ([pscustomobject]@{version=1;entries=@($Entries)})
    try{foreach($entry in $before){if(-not @($Entries|Where-Object {$_.path -ieq $entry.path}).Count){Restore-ProgramProxyShortcuts $entry.path}}}
    catch{Write-LocalJson (Join-Path $script:DataRoot 'program-proxies.json') ([pscustomobject]@{version=1;entries=$before});throw}
}
function Get-ProgramFamily([string]$Executable,$Processes,$IdentityContext=$null) {
    . (Join-Path $PSScriptRoot 'ProgramFamilyTracking.ps1')
    @((Get-ProgramFamilyTrackingSnapshot $Executable $Processes $IdentityContext).Members)
}
function ConvertTo-ProgramArgument([string]$Value) {
    '"'+[regex]::Replace([regex]::Replace($Value,'(\\*)"','$1$1\"'),'(\\+)$','$1$1')+'"'
}
function Get-ProgramLaunchPlan([string]$Executable,[string]$Route) {
    if((Get-ProgramProxyAdapter $Executable) -ne 'chromium'){throw '此程序暂不支持启动代理适配；不能把保存设置当作流量已接管。可使用已配置的分流引擎。'}
    foreach($p in $script:Profiles.Profiles){if($Executable -ieq $p.CorePath -or $Executable -ieq $p.AppPath){throw '不能给代理程序自身设置启动代理，以免形成回路。'}}
    $ingress=Get-ManagedProgramIngress $Executable
    if($ingress){
        $endpoint=Get-ManagedIngressEndpoint $ingress
        $environment=[pscustomobject]@{HTTP_PROXY=$endpoint;HTTPS_PROXY=$endpoint;ALL_PROXY=$endpoint;NO_PROXY='localhost,127.0.0.1,::1'}
        return [pscustomobject]@{Path=$Executable;Route=$ingress.route;Adapter='chromium';Arguments=@(('--proxy-server='+$endpoint),'--proxy-bypass-list=localhost;127.0.0.1;[::1]');Environment=$environment;Endpoint=$endpoint;IngressId=$ingress.id}
    }
    $key=$Route
    if($key -eq 'Follow'){$key=Get-SystemKey (Get-SystemSnapshot)}
    if($key -notin (@('Direct')+(Get-ProfileKeys))){throw '当前系统代理无法解析为已配置入口，请先选择具体代理。'}
    $environment=[ordered]@{};$arguments=@();$endpoint=''
    if($key -eq 'Direct'){
        foreach($name in @('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY')){$environment[$name]=$null}
        $environment.NO_PROXY='*';$arguments=@('--no-proxy-server')
    }else{
        $profile=Get-Profile $key
        if($profile.Protocol -ne 'http'){throw '界面与联网子进程共同使用的启动代理目前需要 HTTP 入口；请选择 HTTP 代理，或使用分流引擎。'}
        if(-not (Get-Listener $profile -ProbeRemote)){throw '所选代理入口未运行，未启动程序，也未切换到其他代理。'}
        $endpoint='http://'+(Get-EndpointAddress $profile)
        foreach($name in @('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY')){$environment[$name]=$endpoint}
        $environment.NO_PROXY='localhost,127.0.0.1,::1'
        $arguments=@(("--proxy-server="+$endpoint),'--proxy-bypass-list=localhost;127.0.0.1;[::1]')
    }
    [pscustomobject]@{Path=$Executable;Route=$key;Adapter='chromium';Arguments=$arguments;Environment=[pscustomobject]$environment;Endpoint=$endpoint}
}
function Get-ProgramShortcutRecords {
    $path=Join-Path $script:DataRoot 'program-shortcuts.json'
    if(Test-Path -LiteralPath $path){@((Get-Content -LiteralPath $path -Raw -Encoding UTF8|ConvertFrom-Json).entries)}else{@()}
}
function Get-ProgramProxyShortcutHealth([string]$Executable) {
    $shell=New-Object -ComObject WScript.Shell
    try{
        foreach($record in @(Get-ProgramShortcutRecords|Where-Object {$_.program -ieq $Executable})){
            $state='missing-shortcut';$owned=$false;$backend='';$ready=$false
            if(Test-Path -LiteralPath $record.shortcut -PathType Leaf){
                $link=$shell.CreateShortcut($record.shortcut)
                try{
                    $owned=$link.TargetPath -ieq $record.managedTarget -and $link.Arguments -ceq $record.managedArguments
                    if(-not $owned){$state='externally-modified'}else{
                        $match=[regex]::Match($link.Arguments,'(?i)(?:^|\s)-File\s+(?:"([^"]+)"|(\S+))')
                        if($match.Success){$backend=$match.Groups[1].Value;if(-not $backend){$backend=$match.Groups[2].Value}}
                        if(-not $backend -or -not [IO.File]::Exists($backend) -or -not [IO.File]::Exists($link.TargetPath)){$state='missing-backend'}
                        elseif($backend -ine (Join-Path $script:Root 'ProxySwitch.ps1')){$state='old-backend'}
                        else{$state='ready';$ready=$true}
                    }
                }finally{[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($link)}
            }
            [pscustomobject]@{Shortcut=$record.shortcut;Owned=$owned;State=$state;Ready=$ready;Backend=$backend;CanRefresh=($owned -and $state -in @('missing-backend','old-backend'))}
        }
    }finally{[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell)}
}
function Get-VerifiedProgramShortcuts([string]$Executable) {
    @(Get-ProgramProxyShortcutHealth $Executable|Where-Object Ready|ForEach-Object Shortcut)
}
function Repair-ProgramProxyEntry([string]$Executable) {
    Use-ChangeLock {
        $snapshot=Get-RuleMaintenanceSnapshot $Executable
        if(-not @(@($snapshot.Launch.entries)+@($snapshot.Engine.programIngresses)|Where-Object {$_.path -ieq $Executable}).Count){throw '此程序没有启动代理记录，未修改入口。'}
        if(@($snapshot.Engine.entries|Where-Object {$_.path -ieq $Executable}).Count){throw '此程序同时有引擎规则，请先核对规则模式。'}
        if(-not [IO.File]::Exists($Executable)){throw '程序路径已失效，请先修复程序路径记录。'}
        if(-not @(Get-ProgramProxyShortcutHealth $Executable|Where-Object CanRefresh).Count){throw '没有仍归本工具且需要更新的旧入口；外部修改保持原样。'}
        $identity=Get-ProgramIdentityDescriptor -Path $Executable -Context (New-ProgramIdentityContext)
        $result=Invoke-RuleMaintenanceChange $snapshot $Executable $Executable $identity
        $result.Message='代理启动入口已更新到当前流向，原线路与原始入口备份保留。外部修改的入口保持原样；正在运行的程序未重启。'
        $result
    }
}
function Restore-ProgramProxyShortcuts([string]$Executable) {
    $records=@(Get-ProgramShortcutRecords);$keep=@();$shell=New-Object -ComObject WScript.Shell
    try{
        foreach($record in $records){
            if($record.program -ine $Executable){$keep+=@($record);continue}
            if(-not (Test-Path -LiteralPath $record.shortcut -PathType Leaf)){continue}
            $link=$shell.CreateShortcut($record.shortcut)
            try{$owned=($link.TargetPath -ieq $record.managedTarget -and $link.Arguments -ceq $record.managedArguments)}finally{[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($link)}
            if(-not $owned){continue} # User edits win; never restore over an independently changed shortcut.
            if($record.originalBackup -and (Test-Path -LiteralPath $record.originalBackup -PathType Leaf)){Copy-Item -LiteralPath $record.originalBackup -Destination $record.shortcut -Force}
            elseif(-not $record.originalBackup){Remove-Item -LiteralPath $record.shortcut -Force}
            else{throw '原始快捷方式备份缺失，未覆盖当前入口。'}
        }
        if(@($records|Where-Object {$_.program -ieq $Executable}).Count){Write-LocalJson (Join-Path $script:DataRoot 'program-shortcuts.json') ([pscustomobject]@{version=1;entries=$keep})}
    }finally{[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell)}
}
function Install-ProgramProxyShortcut([string]$Executable,[string]$DesktopDirectory='') {
    if(-not $DesktopDirectory){$DesktopDirectory=[Environment]::GetFolderPath('Desktop')}
    $records=@(Get-ProgramShortcutRecords);$existing=@($records|Where-Object {$_.program -ieq $Executable})
    $shell=New-Object -ComObject WScript.Shell;$updates=@();$written=@()
    try{
        foreach($file in @(Get-ChildItem -LiteralPath $DesktopDirectory -Filter '*.lnk')){
            $link=$shell.CreateShortcut($file.FullName)
            try{
                $record=$existing|Where-Object {$_.shortcut -ieq $file.FullName}|Select-Object -First 1
                if($link.TargetPath -ine $Executable -and -not ($record -and $link.TargetPath -ieq $record.managedTarget -and $link.Arguments -ceq $record.managedArguments)){continue}
                # Preserve arbitrary user launch arguments; they need explicit adapter support.
                if(-not $record -and $link.Arguments){continue}
                $updates+=@([pscustomobject]@{Path=$file.FullName;Existing=$record;Icon=$link.IconLocation;Description=$link.Description})
            }finally{[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($link)}
        }
        if(-not $updates.Count){
            $destination=Join-Path $DesktopDirectory ([IO.Path]::GetFileNameWithoutExtension($Executable)+'（指定代理）.lnk')
            if(Test-Path -LiteralPath $destination){throw '代理启动快捷方式名称已存在，未覆盖该文件。'}
            $updates=@([pscustomobject]@{Path=$destination;Existing=$null;Icon=($Executable+',0');Description=''})
        }
        $binary=Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
        $arguments='-NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File '+(ConvertTo-ProgramArgument (Join-Path $script:Root 'ProxySwitch.ps1'))+' -DataDirectory '+(ConvertTo-ProgramArgument $script:DataRoot)+' -LaunchProgram '+(ConvertTo-ProgramArgument $Executable)
        foreach($update in $updates){
            $backup='';if(Test-Path -LiteralPath $update.Path){
                $directory=Join-Path $script:DataRoot 'backups\shortcuts';[void][IO.Directory]::CreateDirectory($directory)
                $backup=Join-Path $directory ([Guid]::NewGuid().ToString('N')+'.lnk');Copy-Item -LiteralPath $update.Path -Destination $backup
            }
            $written+=@([pscustomobject]@{Path=$update.Path;Backup=$backup})
            $link=$shell.CreateShortcut($update.Path)
            try{
                $link.TargetPath=$binary;$link.Arguments=$arguments;$link.WorkingDirectory=[IO.Path]::GetDirectoryName($Executable)
                $link.IconLocation=$update.Icon;$link.Description='按 ProxySwitch 为该程序指定的线路启动（包含子进程）';$link.WindowStyle=7;$link.Save()
            }finally{[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($link)}
            $verify=$shell.CreateShortcut($update.Path)
            try{if($verify.TargetPath -ine $binary -or $verify.Arguments -cne $arguments){throw '快捷方式写入核对失败。'}}finally{[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($verify)}
            $original=$backup;if($update.Existing){$original=$update.Existing.originalBackup}
            $records=@($records|Where-Object {$_.shortcut -ine $update.Path})+@([pscustomobject]@{program=$Executable;shortcut=$update.Path;originalBackup=$original;managedTarget=$binary;managedArguments=$arguments})
        }
        Write-LocalJson (Join-Path $script:DataRoot 'program-shortcuts.json') ([pscustomobject]@{version=1;entries=$records})
        @($updates|ForEach-Object Path)
    }catch{
        foreach($item in $written){if($item.Backup){Copy-Item -LiteralPath $item.Backup -Destination $item.Path -Force}else{Remove-Item -LiteralPath $item.Path -Force -ErrorAction SilentlyContinue}}
        throw
    }finally{[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell)}
}
function Set-ProgramLaunchRoute([string]$Executable,[string]$Route) {
    Use-ChangeLock {
        if(@((Get-RoutingSnapshot).entries|Where-Object {$_.path -ieq $Executable}).Count){throw '此程序已有引擎规则。请先明确移除该规则，再改用主程序和子进程启动代理，避免两种方式冲突。'}
        $plan=Get-ProgramLaunchPlan $Executable $Route
        $before=@(Get-ProgramLaunchEntries);$next=@($before|Where-Object {$_.path -ine $Executable})+@([pscustomobject]@{path=$Executable;route=$Route;adapter='chromium';identity=(Get-ProgramIdentityDescriptor -Path $Executable -Context (New-ProgramIdentityContext))})
        $backup=Save-Backup ([pscustomobject]@{Version=3;Time=(Get-Date).ToString('o');System=(Get-SystemSnapshot);Environment=(Get-UserProxyEnv);Selection=(Get-Selection);Routing=(Get-RoutingSnapshot)})
        try{Set-ProgramLaunchEntries $next;$shortcuts=@(Install-ProgramProxyShortcut $Executable)}catch{Set-ProgramLaunchEntries $before;throw}
        [pscustomobject]@{Backup=$backup;Message=('已保存「'+[IO.Path]::GetFileNameWithoutExtension($Executable)+'」的目标「'+(Get-RouteName $Route)+'」，尚未验证生效。请保存任务并完整退出，再使用以下代理入口，或右键选择「按指定线路打开」：'+"`r`n"+($shortcuts -join "`r`n")+"`r`n"+'其他入口（开始菜单、任务栏、Listary 等）未接入此启动设置，重复从那些入口重开不会应用这里保存的代理。');Shortcuts=$shortcuts}
    }
}
function Start-ManagedProgram([string]$Executable) {
    Use-ChangeLock {
    $ingress=Get-ManagedProgramIngress $Executable
    $entry=$ingress;if(-not $entry){$entry=Get-ProgramLaunchEntries|Where-Object {$_.path -ieq $Executable}|Select-Object -First 1}
    if(-not $entry){throw '此程序尚未配置启动代理，请先在管理器中指定线路。'}
    if(@(Get-ProgramFamily $Executable @(Get-ProcessInventory)).Count){throw '该程序仍在运行。请先保存任务并完整退出，再从这个入口打开，才能让界面和联网子进程同时使用新线路。没有结束现有进程。'}
    $limitedDirect=$false;$launchNotice=''
    if($ingress){
        $live=Ensure-ManagedGateway
        $ready=$live.programIngresses|Where-Object {$_.id -ceq $ingress.id}|Select-Object -First 1
        if(-not $ready.loaded -or -not $ready.ready -or -not $ready.effectiveRoute -or $ready.effectiveRoute -eq 'Unknown'){throw '程序固定入口或出口尚未就绪，未启动程序。请打开流向切换到可用线路。'}
        if($ready.effectiveRoute -eq 'Blocked'){
            $directSites=@($live.siteRules|Where-Object {$_.loaded -eq $true -and $_.route -ceq 'Direct' -and ($_.scope -ceq 'global' -or $_.scope -ceq $ingress.id)})
            if($live.siteRulesLoaded -ne $true -or -not $directSites.Count){throw '程序默认代理当前不可用，且没有适用于此程序的已加载直连网站例外；未启动程序。请先切换到可用线路。'}
            $limitedDirect=$true;$launchNotice=' 默认代理出口已暂停，仅匹配直连网站例外的请求可用；其他请求仍会失败，请切换到可用代理后重试。'
        }
    }else{
        $readyKey=$entry.route;if($readyKey -eq 'Follow'){$readyKey=Get-SystemKey (Get-SystemSnapshot)}
        Wait-ManagedProxyReady $readyKey
    }
    $plan=Get-ProgramLaunchPlan $Executable $entry.route
    $psi=New-Object Diagnostics.ProcessStartInfo;$psi.FileName=$Executable;$psi.WorkingDirectory=[IO.Path]::GetDirectoryName($Executable)
    $psi.UseShellExecute=$false;$psi.CreateNoWindow=$false;$psi.Arguments=(@($plan.Arguments|ForEach-Object {ConvertTo-ProgramArgument $_}) -join ' ')
    foreach($name in @('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY')){
        foreach($existing in @($psi.EnvironmentVariables.Keys)){if([string]$existing -ieq $name){$psi.EnvironmentVariables.Remove([string]$existing)}}
        if($null -ne $plan.Environment.$name){$psi.EnvironmentVariables[$name]=[string]$plan.Environment.$name}
    }
    $process=[Diagnostics.Process]::Start($psi)
    try{
        $records=@();$path=Join-Path $script:DataRoot 'program-launches.json'
        if(Test-Path -LiteralPath $path){$records=@((Get-Content -LiteralPath $path -Raw -Encoding UTF8|ConvertFrom-Json).entries|Where-Object {$_.path -ine $Executable})}
        # Process.Start owns this handle; inventory may already have lost a short-lived bootstrap.
        [void]$process.Handle;$started=$process.StartTime.ToUniversalTime().Ticks.ToString()
        $records+=@([pscustomobject]@{path=$Executable;pid=$process.Id;started=$started;route=$plan.Route;endpoint=$plan.Endpoint})
        Write-LocalJson $path ([pscustomobject]@{version=1;entries=$records})
        [pscustomobject]@{Message=('已按指定线路启动，等待观察实际连接。'+$launchNotice);PID=$process.Id;Route=$plan.Route;ObservationUnknown=$false;LimitedDirect=$limitedDirect}
    }catch{
        # A launch-record failure cannot turn a successfully started app into a failed launch.
        Write-LifecycleEvent 'program-launch' 'observation-unavailable'
        [pscustomobject]@{Message=('程序已启动，但启动记录或进程观察未完成，请刷新实际连接；没有重复启动程序。'+$launchNotice);PID=$process.Id;Route=$plan.Route;ObservationUnknown=$true;LimitedDirect=$limitedDirect}
    }finally{$process.Dispose()}
    }
}
function Test-ManagedProgramSession([string]$Executable,$Processes,[string]$Route) {
    $path=Join-Path $script:DataRoot 'program-launches.json';if(-not (Test-Path -LiteralPath $path)){return $false}
    try{$record=(Get-Content -LiteralPath $path -Raw -Encoding UTF8|ConvertFrom-Json).entries|Where-Object {$_.path -ieq $Executable}|Select-Object -First 1}catch{return $false}
    if(-not $record){return $false}
    $ingress=Get-ManagedProgramIngress $Executable
    if($ingress){
        if($record.endpoint -cne (Get-ManagedIngressEndpoint $ingress)){return $false}
        return @($Processes|Where-Object {$_.Id -eq $record.pid -and $_.Path -ieq $Executable -and $_.StartTime -and $_.StartTime.ToUniversalTime().Ticks.ToString() -eq $record.started}).Count -gt 0
    }
    $key=$Route;if($key -eq 'Follow'){$key=Get-SystemKey (Get-SystemSnapshot)}
    if($record.route -ne $key){return $false}
    if($key -ne 'Direct' -and $record.endpoint -cne ('http://'+(Get-EndpointAddress (Get-Profile $key)))){return $false}
    return @($Processes|Where-Object {$_.Id -eq $record.pid -and $_.Path -ieq $Executable -and $_.StartTime.ToUniversalTime().Ticks.ToString() -eq $record.started}).Count -gt 0
}
