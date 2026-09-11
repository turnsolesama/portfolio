$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices;public static class FlowWebsiteVisual{[DllImport("user32.dll")]public static extern int GetWindowLong(IntPtr window,int index);}'
$qa=Join-Path $env:TEMP ('FlowSwitch-routing-workbench-'+[Guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($qa)
foreach($name in @('ProxySwitch.ps1','ProxyWindow.ps1','ProxyBackend.ps1','Preferences.ps1','Storage.ps1','RuntimeSupport.ps1','IndependentGateway.ps1','GatewayWatchdog.ps1','IndependentRouter.cjs','RoutePolicy.cjs','GatewayPortOwnership.ps1','DesktopBranding.cs','FlowTheme.cs','ProgramLaunch.ps1','ProcessInventory.ps1','ProgramIdentity.ps1','ApplicationObservation.ps1','RuleMaintenance.ps1','ProxyDiscovery.ps1','AppRouting.ps1','AppRouter.cjs','config.defaults.json')){Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination $qa}
[void][IO.Directory]::CreateDirectory((Join-Path $qa 'assets'))
foreach($name in @('ManagedRouting.ps1','ProgramFamilyTracking.ps1','RoutePolicy.ps1')){if(Test-Path -LiteralPath (Join-Path $PSScriptRoot $name)){Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination $qa}}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'assets/FlowSwitch.ico') -Destination (Join-Path $qa 'assets/FlowSwitch.ico')
$checks=@'
        $script:Checks=0
        function Check-UI($Value,[string]$Message){if(-not $Value){throw $Message};$script:Checks++}
        function Start-Work([string]$Kind,[string]$Key){$script:Requested=[pscustomobject]@{Kind=$Kind;Key=$Key}}
        $script:AppTarget=[pscustomobject]@{Name='Fixture Editor';Path='C:\Fixtures\editor.exe';SavedPath='C:\Fixtures\editor.exe';Mode='managed';Policy='backup';RequiresRepair=$false;HasSavedRule=$true;CanLaunch=$true}
        foreach($mode in @('launch','engine','observe','managed')){
            $script:AppTarget.Mode=$mode;Request-ApplicationRoute 'Direct';$payload=$script:Requested.Key|ConvertFrom-Json
            Check-UI ($script:Requested.Kind -eq 'ManagedAppRoute' -and $payload.route -eq 'Direct' -and $payload.path -eq $script:AppTarget.Path) ('Normal route operation must be common for '+$mode)
        }
        Request-ApplicationRoute 'Follow';$payload=$script:Requested.Key|ConvertFrom-Json
        Check-UI ($script:Requested.Kind -eq 'ManagedAppRoute' -and $payload.route -eq 'Follow') 'Follow keeps application entry rather than removing it'
        $websiteButton.PerformClick()
        Check-UI ($script:Requested.Kind -eq 'WebsiteRules' -and $script:Requested.Key -eq '') 'Main website action opens global rules'
        $script:AppTarget.Mode='managed';$script:LastApps=Get-DemoApps
        $appMenu.Show($liveList,(New-Object Drawing.Point(1,1)));[Windows.Forms.Application]::DoEvents();$websiteProgramItem.PerformClick();$appMenu.Close()
        Check-UI ($script:Requested.Kind -eq 'WebsiteRules' -and $script:Requested.Key -eq $script:AppTarget.Path) 'Program menu passes precise executable scope'
        $snapshot=[pscustomobject]@{Entries=@([pscustomobject]@{Id=('a'*32);Domain='initial.example';Match='exact';Route='Direct';Executable=''});Revision=('b'*64);Available=$true;Loaded=$true;Message='测试规则已加载';ContextExecutable='C:\Fixtures\editor.exe'}
        $editor=New-WebsiteRuleEditor $snapshot
        try{
            $editor.ShowInTaskbar=$false;$editor.Show($form);[Windows.Forms.Application]::DoEvents();$state=$editor.Tag
            $buttons=@{};foreach($control in $editor.Controls[0].Controls){foreach($child in $control.Controls){if($child.Name){$buttons[$child.Name]=$child}}}
            foreach($width in @(930,850,1100)){
                $editor.ClientSize=New-Object Drawing.Size($width,590);$editor.PerformLayout();[Windows.Forms.Application]::DoEvents()
                Check-UI ($buttons.WebsiteSave.Right -le $buttons.WebsiteSave.Parent.ClientSize.Width -and $buttons.WebsiteCancel.Right -lt $buttons.WebsiteSave.Left -and $state.Route.Right -le $state.Route.Parent.ClientSize.Width) 'Website save, cancel and route controls remain visible without overlap when resized'
                $state.List.Refresh();[Windows.Forms.Application]::DoEvents()
                Check-UI (([FlowWebsiteVisual]::GetWindowLong($state.List.Handle,-16) -band 0x100000) -eq 0) ('Website list has no native horizontal scrollbar at width '+$width+'; columns '+(($state.List.Columns|Measure-Object Width -Sum).Sum)+' client '+$state.List.ClientSize.Width)
            }
            $editor.ClientSize=New-Object Drawing.Size(930,590);$editor.PerformLayout();[Windows.Forms.Application]::DoEvents()
            $editorBitmap=New-Object Drawing.Bitmap($editor.Width,$editor.Height);try{$editor.DrawToBitmap($editorBitmap,(New-Object Drawing.Rectangle(0,0,$editor.Width,$editor.Height)));$editorBitmap.Save((Join-Path ([IO.Path]::GetDirectoryName($PreviewPath)) 'website-rules.png'))}finally{$editorBitmap.Dispose()}
            Check-UI ($state.Scope.SelectedItem.Executable -eq 'C:\Fixtures\editor.exe') 'Program editor defaults to requested full-path scope'
            Check-UI ($state.List.Items.Count -eq 1 -and $state.List.Items[0].SubItems[1].Text -eq 'initial.example') 'Existing site rules render in actual controls'
            foreach($bad in @('https://example.com/?code=secret','user:secret@example.com','example.com/path','*.example.com','127.0.0.1')){
                $state.Domain.Text=$bad;$buttons.WebsiteAdd.PerformClick()
                Check-UI ($state.Entries.Count -eq 1 -and $state.Error.Text) 'URL credentials wildcard or IP cannot enter a domain rule'
            }
            $state.Domain.Text='PROJECT.Example.';$state.Match.SelectedIndex=1;$state.Route.SelectedIndex=0;$buttons.WebsiteAdd.PerformClick()
            $added=@($state.Entries|Where-Object Domain -eq 'project.example')[0]
            Check-UI ($state.Entries.Count -eq 2 -and $added.Match -eq 'suffix' -and $added.Executable -eq 'C:\Fixtures\editor.exe') 'Domain is normalized and suffix applies to selected program'
            $id=$added.Id;$state.Domain.Text='project.example';$state.Route.SelectedIndex=$state.Route.Items.Count-1;$buttons.WebsiteAdd.PerformClick()
            Check-UI ($state.Entries.Count -eq 2 -and $added.Id -eq $id -and $added.Route -eq $state.Route.SelectedItem.Id) 'Same scope domain and match updates route without duplicating identity'
            $state.Scope.SelectedIndex=0;$state.Domain.Text='project.example';$state.Match.SelectedIndex=0;$state.Route.SelectedIndex=0;$buttons.WebsiteAdd.PerformClick()
            Check-UI ($state.Entries.Count -eq 3 -and @($state.Entries|Where-Object {$_.Domain -eq 'project.example' -and -not $_.Executable -and $_.Match -eq 'exact'}).Count -eq 1) 'Global exact rule is distinct from program suffix rule'
            Check-UI ($snapshot.Entries.Count -eq 1 -and $snapshot.Entries[0].Route -eq 'Direct') 'Editing never mutates fetched snapshot or backend state'
            $state.Domain.Text='unsaved.example';$buttons.WebsiteSave.PerformClick()
            Check-UI ($null -eq $state.Result -and $state.Error.Text -match '尚未加入') 'Save cannot silently discard an unadded domain draft'
            $state.Domain.Text='';$state.List.Items[0].Selected=$true;$state.List.Items[0].Focused=$true;[Windows.Forms.Application]::DoEvents();$buttons.WebsiteRemove.PerformClick()
            Check-UI ($state.Entries.Count -eq 2 -and $state.Domain.Text -eq '') 'Delete removes only selected staged rule and clears its edit draft'
            $buttons.WebsiteSave.PerformClick()
            Check-UI ($editor.DialogResult -eq 'OK' -and $state.Result.Revision -eq ('b'*64) -and $state.Result.Entries.Count -eq 2) 'Save returns full entries and original revision for backend concurrency validation'
            Check-UI (($state.Result|ConvertTo-Json -Depth 6) -notmatch 'code=|user:secret') 'Rejected authentication strings never enter persisted payload'
        }finally{$editor.Dispose()}
        $cancelEditor=New-WebsiteRuleEditor $snapshot
        try{$cancelEditor.ShowInTaskbar=$false;$cancelEditor.Show($form);[Windows.Forms.Application]::DoEvents();$cancelEditor.Close();Check-UI ($null -eq $cancelEditor.Tag.Result) 'Closing editor without save returns no mutation'}finally{$cancelEditor.Dispose()}
        $snapshot.Available=$false;$unknownEditor=New-WebsiteRuleEditor $snapshot
        try{Check-UI ($unknownEditor.Tag.Status.Text -match '尚未确认' -and $unknownEditor.Tag.Status.Text -notmatch '^网站规则已加载') 'Unavailable website controller cannot be presented as loaded rules'}finally{$unknownEditor.Dispose()}
        $app=[pscustomobject]@{Name='Fixture';Path='C:\Fixtures\editor.exe';Policy='backup';Mode='managed';Managed=$true;NeedsRelaunch=$true;CanLaunch=$true;Loaded=$true;Actual='未观察到 TCP 连接';Status='已保存 B；仍使用旧入口，需要完整重开';HasSavedRule=$true}
        Show-Applications ([pscustomobject]@{Rows=@($app);RuleCount=1;LaunchRuleCount=0;Available=$true;RulesAvailable=$true;TcpAvailable=$true})
        Check-UI ($liveList.Items[0].SubItems[2].Text -eq '未观察到 TCP 连接' -and $liveList.Items[0].SubItems[3].Text -match '旧入口') 'Loaded route cannot manufacture traffic evidence or hide pending restart status'
        Check-UI ($ruleMeta.Text -match '已加载线路设置' -and $ruleMeta.Text -notmatch '已观察到目标出口') 'Loaded rule count is never described as observed actual route'
        Write-Output ('PASS: '+$script:Checks+' routing workbench UI assertions; actual menus and website editor controls, isolated demo, no network writes or user applications.')
'@
$path=Join-Path $qa 'ProxyWindow.ps1';$source=[IO.File]::ReadAllText($path)
$source=$source.Replace('$bitmap=New-Object Drawing.Bitmap($form.Width,$form.Height)',$checks+"`r`n"+'$bitmap=New-Object Drawing.Bitmap($form.Width,$form.Height)')
[IO.File]::WriteAllText($path,$source,(New-Object Text.UTF8Encoding($true)))
& (Join-Path $qa 'ProxySwitch.ps1') -Demo -DataDirectory (Join-Path $qa 'data') -PreviewPath (Join-Path $qa 'routing-workbench.png')
