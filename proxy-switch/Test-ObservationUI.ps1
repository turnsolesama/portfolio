$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Windows.Forms
$qa=Join-Path $env:TEMP ('FlowSwitch-observation-ui-'+[Guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($qa)
foreach($name in @('ProxySwitch.ps1','ProxyWindow.ps1','ProxyBackend.ps1','Preferences.ps1','Storage.ps1','RuntimeSupport.ps1','IndependentGateway.ps1','GatewayWatchdog.ps1','IndependentRouter.cjs','RoutePolicy.cjs','GatewayPortOwnership.ps1','DesktopBranding.cs','FlowTheme.cs','ProgramLaunch.ps1','ProcessInventory.ps1','ProgramIdentity.ps1','ApplicationObservation.ps1','RuleMaintenance.ps1','ProxyDiscovery.ps1','AppRouting.ps1','AppRouter.cjs','config.defaults.json')){Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination $qa}
[void][IO.Directory]::CreateDirectory((Join-Path $qa 'assets'))
foreach($name in @('ManagedRouting.ps1','ProgramFamilyTracking.ps1','RoutePolicy.ps1')){if(Test-Path -LiteralPath (Join-Path $PSScriptRoot $name)){Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination $qa}}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'assets/FlowSwitch.ico') -Destination (Join-Path $qa 'assets/FlowSwitch.ico')
$checks=@'
        $script:Checks=0
        function Check-UI($Value,[string]$Message){if(-not $Value){throw $Message};$script:Checks++}
        $old='C:\Fixtures\old\app.exe';$current='C:\Fixtures\new\app.exe'
        $row=[pscustomobject]@{Name='更新后的程序';Path=$current;SavedPath=$old;RowKey='saved:'+ $old;Policy='office';PolicyName='办公网络';Mode='launch';Loaded=$false;Actual='办公网络 ×3';Status='已识别路径变更 · 规则待修复';PIDs='42';CanLaunch=$false;RequiresRepair=$true;CanRepair=$true;HasSavedRule=$true;Coverage='TCP 快照'}
        $apps=[pscustomobject]@{Rows=@($row);RuleCount=1;LaunchRuleCount=1;RepairCount=1;Available=$false;RulesAvailable=$false;TcpAvailable=$true}
        Show-Applications $apps
        Check-UI ($liveList.Items.Count -eq 1 -and $liveList.Items[0].SubItems[2].Text -eq '办公网络 ×3') 'Upgraded program must retain observed connections'
        Check-UI ($liveList.Items[0].SubItems[3].Text -match '路径变更' -and $ruleMeta.Text -match '待修复') 'Repair evidence must not be replaced by generic engine status'
        $liveList.Items[0].Selected=$true;$liveList.Items[0].Focused=$true
        $row.Path='C:\Fixtures\newer\app.exe';Show-Applications $apps
        Check-UI ($liveList.SelectedItems.Count -eq 1) 'Selection must survive current path changes using saved record key'
        $script:AppTarget=$row;$appMenu.Show($liveList,(New-Object Drawing.Point(1,1)));[Windows.Forms.Application]::DoEvents()
        Check-UI ($repairItem.Visible -and $repairItem.Enabled) 'Verified unique migration exposes repair action'
        Check-UI (-not $launchItem.Available -and -not $reconnectItem.Enabled) 'Pending repair cannot launch old path or reconnect unrelated traffic'
        Check-UI (@($appMenu.Items|Where-Object {$_.Tag -and $_.Tag -ne 'Follow' -and $_.Enabled}).Count -eq 0) 'Pending repair cannot silently create conflicting rules'
        Check-UI ($removeSettingItem.Visible -and $removeSettingItem.Enabled) 'Obsolete saved record can still be removed using its explicit action'
        $appMenu.Close()
        function Start-Work([string]$Kind,[string]$Key){$script:Requested=[pscustomobject]@{Kind=$Kind;Key=$Key}}
        $removeSettingItem.PerformClick()
        Check-UI ($script:Requested.Kind -eq 'AppRemove' -and $script:Requested.Key -ceq $old) 'Remove acts on saved old path, not observed new path'
        $script:Requested=$null;Request-ApplicationRoute 'backup'
        Check-UI ($null -eq $script:Requested) 'Route changes refuse unresolved migration'
        $row.RequiresRepair=$false;$row.CanRepair=$false;$row.SavedPath=$row.Path
        Request-ApplicationRoute 'backup';$payload=$script:Requested.Key|ConvertFrom-Json
        Check-UI ($script:Requested.Kind -eq 'ManagedAppRoute' -and $payload.path -ceq $row.Path -and $payload.route -eq 'backup') 'Changing a saved launch route goes through common managed switching'
        $state=Get-DemoState;$state|Add-Member NoteProperty TcpAvailable $false
        foreach($listener in $state.Listeners){$listener.Ready=$null};Show-State $state
        Check-UI ($portsLabel.Text -match '未知' -and $envLabel.Text -match '不代表断网') 'Collection failure must not present zero live proxies as a network outage'
        $apps.TcpAvailable=$false;Show-Applications $apps
        Check-UI ($countLabel.Text -match '采集失败') 'Connection collection failure remains visible'
        Check-UI (@($proxyList.Items|Where-Object {$_.SubItems[5].Text -match '未监听'}).Count -eq 0 -and @($proxyList.Items|Where-Object {$_.SubItems[5].Text -match '未知'}).Count -eq 2) 'Unknown listeners must remain unknown in the proxy catalog'
        $script:Profiles.Routing.Adapter='standalone';$apps|Add-Member NoteProperty EffectiveDefaultRoute 'Unknown';$apps|Add-Member NoteProperty DefaultRoute 'office';$apps.Available=$true
        Show-Applications $apps
        Check-UI ($noticeLabel.Text -match '出口读取失败' -and $noticeLabel.Text -notmatch '已自动接替') ('Unavailable selector must not claim failover to Unknown: '+$noticeLabel.Text)
        Mark-ObservationStale;Show-Applications $apps
        Check-UI ($liveList.Items[0].SubItems[2].Text -match '过期') 'Searching or filtering must not turn stale evidence into current evidence'
        $script:ObservationStale=$false;Show-Applications $apps
        Check-UI ($liveList.Items[0].SubItems[2].Text -eq '办公网络 ×3') 'Fresh snapshots replace stale labels'

        function Get-GatewayKey {'office'}
        $apps.Available=$true;$apps.RulesAvailable=$true;$apps|Add-Member NoteProperty DefaultLoaded $true -Force
        $row.Mode='observe';$row.SavedPath='';Show-Applications $apps;$script:AppTarget=$row
        $appMenu.Show($liveList,(New-Object Drawing.Point(1,1)));[Windows.Forms.Application]::DoEvents()
        Check-UI $reconnectItem.Enabled 'Default-route programs can preview their old connections'
        $appMenu.Close();$apps.RulesAvailable=$false
        $appMenu.Show($liveList,(New-Object Drawing.Point(1,1)));[Windows.Forms.Application]::DoEvents()
        Check-UI (-not $reconnectItem.Enabled) 'Unknown rules cannot expose reconnect as ready'
        $appMenu.Close();$apps.RulesAvailable=$true;$apps.DefaultLoaded=$false
        $appMenu.Show($liveList,(New-Object Drawing.Point(1,1)));[Windows.Forms.Application]::DoEvents()
        Check-UI (-not $reconnectItem.Enabled) 'Unloaded default route cannot expose reconnect as ready'
        $appMenu.Close();$row.Mode='engine';Request-ApplicationRoute 'backup'
        Check-UI ($script:Requested.Kind -eq 'ManagedAppRoute') 'Existing engine rules go through the common operation with backend compatibility handling'
        $fixture=Join-Path $script:DataRoot 'family-fixture';[void][IO.Directory]::CreateDirectory($fixture)
        foreach($name in @('app.exe','resources.pak','chrome_100_percent.pak')){[IO.File]::WriteAllText((Join-Path $fixture $name),'inert fixture')}
        $row.Path=Join-Path $fixture 'app.exe';$row.Mode='observe'
        $appMenu.Show($liveList,(New-Object Drawing.Point(1,1)));[Windows.Forms.Application]::DoEvents()
        Check-UI $websiteProgramItem.Enabled 'Selected programs expose a contextual website rules editor'
        $choice=@($appMenu.Items|Where-Object Tag -eq 'backup')[0];$choice.PerformClick()
        $payload=$script:Requested.Key|ConvertFrom-Json
        Check-UI ($script:Requested.Kind -eq 'ManagedAppRoute' -and $payload.path -eq $row.Path -and $payload.route -eq 'backup') 'Actual route menu requests one operation without internal mode selection'
        $appMenu.Close();$row.Mode='engine'
        $appMenu.Show($liveList,(New-Object Drawing.Point(1,1)));[Windows.Forms.Application]::DoEvents()
        Check-UI (@($appMenu.Items|Where-Object {$_.Text -match '^启动代理：'}).Count -eq 0) 'Normal menu does not ask users to choose an internal launch mode'
        $appMenu.Close();$script:Requested=$null
        $tabs.SelectedTab=$toolsPage;[Windows.Forms.Application]::DoEvents()
        $login=@($toolsBar.Controls|Where-Object Text -eq 'Google 登录诊断')[0];$login.PerformClick()
        Check-UI ($script:Requested.Kind -eq 'LoginDiagnostic' -and $script:Requested.Key -eq '') 'Actual login diagnostic button resolves system proxy instead of configured gateway'
        $state=Get-DemoState;$state|Add-Member NoteProperty Warnings @() -Force;$script:Profiles.Routing.Adapter='standalone';$script:Profiles.Routing|Add-Member NoteProperty Failover ([pscustomobject]@{Enabled=$false}) -Force
        Show-State $state
        Check-UI ($statusLabel.Text -match '服务未启动' -and $noticeLabel.Text -match '本次打开未更改网络' -and $noticeLabel.Text -match '统一切换') 'Configured standalone without session reports stopped service and explicit startup actions'
        $sessionFile=Get-IndependentSessionPath;[IO.File]::WriteAllText($sessionFile,'{}')
        try{Show-State $state;Check-UI ($noticeLabel.Text -match '自动接替已关闭' -and $noticeLabel.Text -notmatch '自动接替已启用') ('Disabled failover is never described as enabled: '+$noticeLabel.Text);$script:Profiles.Routing.Failover.Enabled=$true;Show-State $state;Check-UI ($noticeLabel.Text -match '自动接替已开启') 'Enabled failover has distinct accurate notice'}finally{[IO.File]::Delete($sessionFile)}
        $apps.EffectiveDefaultRoute='Blocked';Show-Applications $apps
        Check-UI ($noticeLabel.Text -match '默认代理出口已暂停' -and $noticeLabel.Text -match '直连网站例外或其他程序线路' -and $noticeLabel.Text -notmatch '全部代理检测失败') 'Default-route pause does not imply website exceptions and every program are blocked'
        function Get-GatewayKey {''};$script:Profiles.Routing.Adapter='none';Show-ProxyCatalog
        Check-UI ($engineLabel.Text -match '统一切换.*建立入口' -and $engineLabel.Text -notmatch '仅能切换系统代理') 'Unconfigured gateway view explains the normal fixed-entry switching action'
        Write-Output ('PASS: '+$script:Checks+' observation UI assertions; actual WinForms controls, isolated data and no network writes.')
'@
$path=Join-Path $qa 'ProxyWindow.ps1';$source=[IO.File]::ReadAllText($path)
$source=$source.Replace('$bitmap=New-Object Drawing.Bitmap($form.Width,$form.Height)',$checks+"`r`n"+'$bitmap=New-Object Drawing.Bitmap($form.Width,$form.Height)')
[IO.File]::WriteAllText($path,$source,(New-Object Text.UTF8Encoding($true)))
& (Join-Path $qa 'ProxySwitch.ps1') -Demo -DataDirectory (Join-Path $qa 'data') -PreviewPath (Join-Path $qa 'observation.png')
