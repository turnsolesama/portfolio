param([string]$PreviewPath,[switch]$SmokeTest,[switch]$PreviewMenu,[switch]$Demo,[string]$PreviewView='Programs',[string]$DataDirectory='',[string]$InitialLaunchProgram='')
. (Join-Path $PSScriptRoot 'ProxyBackend.ps1') -DataDirectory $DataDirectory
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
if(-not ('FlowSwitchDesktop' -as [type])){Add-Type -Path (Join-Path $PSScriptRoot 'DesktopBranding.cs')}
[FlowSwitchDesktop]::Initialize()
if(-not ('FlowSwitch.UI.Palette' -as [type])){Add-Type -Path (Join-Path $PSScriptRoot 'FlowTheme.cs') -ReferencedAssemblies System.Windows.Forms,System.Drawing}
function Assert-ConfiguredLaunchRequest([string]$Executable) {
    if(-not [IO.Path]::IsPathRooted($Executable)){throw '程序启动路径无效，请从流向重新创建代理启动入口。'}
    try{$configured=[bool](Get-ManagedProgramIngress $Executable) -or @((Get-ProgramLaunchEntries)|Where-Object {$_.path -ieq $Executable}).Count -gt 0}
    catch{throw '程序线路记录无法读取，目标程序尚未启动。请在流向中修复或恢复本机规则后重试。'}
    if(-not $configured){throw '此程序尚未配置代理启动入口。请在流向中添加程序并选择线路，再从生成的入口打开。'}
}
if($InitialLaunchProgram){
    try{Assert-ConfiguredLaunchRequest $InitialLaunchProgram}catch{[void][Windows.Forms.MessageBox]::Show($_.Exception.Message,'程序代理启动','OK','Warning');return}
}
$script:WindowLease=$null
if(-not $SmokeTest -and -not $Demo -and -not $PreviewPath){
    $script:WindowLease=New-Object FlowSwitchWindowLease($script:DataRoot)
    if($InitialLaunchProgram){
        try{if(-not $script:WindowLease.RequestLaunch($InitialLaunchProgram)){throw '启动请求未接收，请等待当前操作完成后重试；目标程序尚未启动。'}}
        catch{[void][Windows.Forms.MessageBox]::Show('无法将启动请求交给后台流向。请打开流向窗口，等待当前操作完成后重试。','程序代理启动','OK','Warning');$script:WindowLease.Dispose();return}
    }
    if(-not $script:WindowLease.IsPrimary){$script:WindowLease.Dispose();return}
}
[Windows.Forms.Application]::EnableVisualStyles()
$script:Worker=$null;$script:LastState=$null;$script:LastApps=$null;$script:NextPoll=[DateTime]::MinValue
$script:Controls=@();$script:RouteButtons=@{};$script:UiRoot=$PSScriptRoot
$script:MenuOpen=$false;$script:DialogOpen=$false
$script:DiscoveryStatus='正在自动识别';$script:ChoiceDirty=$false;$script:DiscoveryCache=@()
$ink=[Drawing.ColorTranslator]::FromHtml('#EDF0F5')
$muted=[Drawing.ColorTranslator]::FromHtml('#ADB6C4')
$mint=[Drawing.ColorTranslator]::FromHtml('#ACC8F0')
$paper=[Drawing.ColorTranslator]::FromHtml('#14171C')
$form=New-Object Windows.Forms.Form
$form.Text='流向 · 网络代理管家 | FlowSwitch '+$script:ProductVersion
$form.ClientSize=New-Object Drawing.Size(1260,840)
$form.MinimumSize=New-Object Drawing.Size(1180,790)
$form.StartPosition='CenterScreen';$form.AutoScaleMode='Dpi';$form.BackColor=$paper
$form.Font=New-Object Drawing.Font('Microsoft YaHei UI',10)
$form.KeyPreview=$true;$form.AllowDrop=$true
$iconPath=Join-Path $PSScriptRoot 'assets\FlowSwitch.ico'
if(Test-Path -LiteralPath $iconPath){$form.Icon=New-Object Drawing.Icon($iconPath)}
function Quote-DesktopArgument([string]$Value){return '"'+[regex]::Replace($Value,'(\\+)$','$1$1')+'"'}
$desktopLauncher=Join-Path ([IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))) 'FlowSwitch.exe'
if(Test-Path -LiteralPath $desktopLauncher){
    $desktopCommand=(Quote-DesktopArgument $desktopLauncher)+' --data-directory '+(Quote-DesktopArgument $script:DataRoot)
}else{
    $desktopShell=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $desktopCommand=(Quote-DesktopArgument $desktopShell)+' -NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File '+(Quote-DesktopArgument (Join-Path $PSScriptRoot 'ProxySwitch.ps1'))+' -DataDirectory '+(Quote-DesktopArgument $script:DataRoot)
}
$form.Add_HandleCreated({$script:TaskbarRelaunchReady=[FlowSwitchDesktop]::ConfigureWindow($form.Handle,$desktopCommand,$iconPath)})
function New-Label($Parent,$Text,$X,$Y,$W,$H,$Size=10,$Bold=$false) {
    $l=New-Object Windows.Forms.Label;$l.Text=$Text;$l.AutoEllipsis=$true
    $l.SetBounds($X,$Y,$W,$H);$style=[Drawing.FontStyle]::Regular
    if($Bold){$style=[Drawing.FontStyle]::Bold}
    $l.Font=New-Object Drawing.Font('Microsoft YaHei UI',$Size,$style);$l.ForeColor=$ink
    $Parent.Controls.Add($l);return $l
}
function New-Button($Parent,$Text,$X,$Y,$W,$H,$Action) {
    $b=New-Object FlowSwitch.UI.ActionButton;$b.Text=$Text;$b.SetBounds($X,$Y,$W,$H)
    $b.FlatStyle='Flat';$b.FlatAppearance.BorderSize=0;$b.BackColor=[Drawing.ColorTranslator]::FromHtml('#282E38')
    $b.ForeColor=$ink;$b.Cursor=[Windows.Forms.Cursors]::Hand;$b.Add_Click($Action)
    $Parent.Controls.Add($b);$script:Controls+=$b;return $b
}
function Write-Activity([string]$Text) {
    if(-not $Text){return}
    if($logBox.TextLength -gt 14000){$logBox.Text=$logBox.Text.Substring($logBox.TextLength-9000)}
    $logBox.AppendText('['+(Get-Date -Format 'HH:mm:ss')+'] '+$Text+"`r`n`r`n")
    $logBox.SelectionStart=$logBox.TextLength;$logBox.ScrollToCaret()
    $actionLabel.Text=($Text -split "`r?`n")[0]
}
$layout=New-Object Windows.Forms.TableLayoutPanel
$layout.Dock='Fill';$layout.Padding=New-Object Windows.Forms.Padding(24,16,24,12)
$layout.ColumnCount=1;$layout.RowCount=7
foreach($height in @(76,104,54,54)) {[void]$layout.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Absolute,$height)))}
[void]$layout.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Percent,100)))
[void]$layout.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Absolute,35)))
[void]$layout.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Absolute,24)))
$shellLayout=New-Object Windows.Forms.TableLayoutPanel;$shellLayout.Dock='Fill';$shellLayout.ColumnCount=2;$shellLayout.RowCount=1;$shellLayout.Margin=New-Object Windows.Forms.Padding(0)
[void]$shellLayout.ColumnStyles.Add((New-Object Windows.Forms.ColumnStyle([Windows.Forms.SizeType]::Absolute,180)))
[void]$shellLayout.ColumnStyles.Add((New-Object Windows.Forms.ColumnStyle([Windows.Forms.SizeType]::Percent,100)))
$form.Controls.Add($shellLayout)
$sidebar=New-Object Windows.Forms.Panel;$sidebar.Dock='Fill';$sidebar.Margin=New-Object Windows.Forms.Padding(0);$sidebar.BackColor=[Drawing.ColorTranslator]::FromHtml('#181C23');$shellLayout.Controls.Add($sidebar,0,0)
$shellLayout.Controls.Add($layout,1,0)
$sideIcon=New-Object Windows.Forms.PictureBox;$sideIcon.SetBounds(22,28,42,42);$sideIcon.SizeMode='Zoom';$sideIcon.Image=(New-Object Drawing.Icon($iconPath,64,64)).ToBitmap();$sidebar.Controls.Add($sideIcon)
$null=New-Label $sidebar 'FlowSwitch' 20 84 150 30 17 $true
$sideSubtitle=New-Label $sidebar '流向 · 网络代理管家' 22 118 150 24 9;$sideSubtitle.ForeColor=$muted
$sectionLabel=New-Label $sidebar '工作空间' 24 158 130 25 9;$sectionLabel.ForeColor=$muted
$sideFoot=New-Label $sidebar ("每条连接，自由选择。`r`nFlowSwitch "+$script:ProductVersion) 22 740 150 54 9;$sideFoot.ForeColor=$muted;$sideFoot.Anchor='Bottom,Left'
$sidebar.Add_SizeChanged({$sideFoot.Top=$sidebar.ClientSize.Height-84})
$header=New-Object Windows.Forms.Panel;$header.Dock='Fill';$header.BackColor=$paper;$header.Margin=New-Object Windows.Forms.Padding(0,0,0,12)
$layout.Controls.Add($header,0,0)
$brand=New-Label $header '程序分流' 0 1 240 36 20 $true;$brand.ForeColor=[Drawing.Color]::White
$sub=New-Label $header '网络工作台' 250 15 280 26 10;$sub.ForeColor=[Drawing.ColorTranslator]::FromHtml('#ACC8F0')
$tagline=New-Label $header '为每个程序选择线路，查看连接的实际去向。' 2 39 670 24 9;$tagline.ForeColor=[Drawing.ColorTranslator]::FromHtml('#ADB6C4')
$help=New-Button $header '使用指南' 816 17 92 34 {Show-Guide};$help.Anchor='Top,Right'
$settings=New-Button $header '代理管理' 916 17 96 34 {$tabs.SelectedTab=$proxyPage};$settings.Anchor='Top,Right'
$settings.Visible=$false;$sub.Visible=$false
$header.Add_SizeChanged({$help.Left=$header.ClientSize.Width-$help.Width})
$cards=New-Object Windows.Forms.TableLayoutPanel;$cards.Dock='Fill';$cards.ColumnCount=3;$cards.Margin=New-Object Windows.Forms.Padding(0)
for($i=0;$i -lt 3;$i++){[void]$cards.ColumnStyles.Add((New-Object Windows.Forms.ColumnStyle([Windows.Forms.SizeType]::Percent,33.333)))}
$layout.Controls.Add($cards,0,1)
$panels=@()
for($i=0;$i -lt 3;$i++){$p=New-Object FlowSwitch.UI.SurfacePanel;$p.Dock='Fill';$p.BackColor=[FlowSwitch.UI.Palette]::Surface;$p.Margin=New-Object Windows.Forms.Padding(0,0,$(if($i -lt 2){12}else{0}),12);$cards.Controls.Add($p,$i,0);$panels+=$p}
$cardCaption=New-Label $panels[0] '当前默认出口' 16 10 260 22 9;$cardCaption.ForeColor=$muted
$entryValue=New-Label $panels[0] '正在读取…' 16 30 280 29 15 $true
$systemLabel=New-Label $panels[0] 'Windows / 浏览器 / 命令行' 16 62 290 21 9;$systemLabel.ForeColor=$muted
$cardCaption=New-Label $panels[1] '可用代理入口' 16 10 260 22 9;$cardCaption.ForeColor=$muted
$portsLabel=New-Label $panels[1] '检测本地入口…' 16 32 290 27 13 $true
$envLabel=New-Label $panels[1] '正在核对代理变量' 16 62 290 21 9;$envLabel.ForeColor=$muted
$cardCaption=New-Label $panels[2] '程序专用线路' 16 10 260 22 9;$cardCaption.ForeColor=$muted
$ruleValue=New-Label $panels[2] '正在读取…' 16 30 285 29 15 $true
$ruleMeta=New-Label $panels[2] '右键程序即可指定线路' 16 62 290 21 9;$ruleMeta.ForeColor=$muted
$switchRow=New-Object Windows.Forms.Panel;$switchRow.Dock='Fill';$switchRow.Margin=New-Object Windows.Forms.Padding(0)
$layout.Controls.Add($switchRow,0,2)
$null=New-Label $switchRow '统一使用' 0 8 86 32 11 $true
$networkChoice=New-Object FlowSwitch.UI.RouteChoice;$networkChoice.DropDownStyle='DropDownList';$networkChoice.DisplayMember='Name';$networkChoice.SetBounds(92,3,442,36);$switchRow.Controls.Add($networkChoice)
$networkChoice.Add_SelectionChangeCommitted({$script:ChoiceDirty=$true;$noticeLabel.Text='已选择待应用目标；点击「统一切换」才会更改网络。'})
$unify=New-Button $switchRow '统一切换' 548 0 156 36 {
    if($networkChoice.SelectedItem){Start-Work 'Switch' $networkChoice.SelectedItem.Id}else{Write-Activity '请先选择目标线路。'}
};$unify.Primary=$true;$unify.BackColor=$mint;$unify.ForeColor=[Drawing.ColorTranslator]::FromHtml('#172333')
$undo=New-Button $switchRow '撤回上次更改' 786 0 174 36 {Start-Work 'Restore' ''}
$switchRow.Add_Layout({$gap=[Math]::Max(12,[int]($form.Font.Height*0.7));$undo.Left=$switchRow.ClientSize.Width-$undo.Width;$unify.Left=$undo.Left-$unify.Width-$gap;$networkChoice.Width=[Math]::Max(80,$unify.Left-$networkChoice.Left-$gap)})
$noticePanel=New-Object Windows.Forms.Panel;$noticePanel.Dock='Fill';$noticePanel.Margin=New-Object Windows.Forms.Padding(0,0,0,8)
$statusLabel=New-Label $noticePanel '正在核对配置' 0 0 1020 22 10 $true;$statusLabel.Anchor='Top,Left,Right'
$noticeLabel=New-Label $noticePanel '打开面板只读取状态。' 0 23 1020 22 9;$noticeLabel.ForeColor=$muted;$noticeLabel.Anchor='Top,Left,Right'
$layout.Controls.Add($noticePanel,0,3)
$tabs=New-Object FlowSwitch.UI.PageHost;$tabs.Dock='Fill';$tabs.Padding=New-Object Drawing.Point(18,8);$tabs.Margin=New-Object Windows.Forms.Padding(0)
$programPage=New-Object Windows.Forms.TabPage('程序分流');$programPage.BackColor=[FlowSwitch.UI.Palette]::Surface
$toolsPage=New-Object Windows.Forms.TabPage('诊断与工具');$toolsPage.BackColor=[FlowSwitch.UI.Palette]::Surface
$proxyPage=New-Object Windows.Forms.TabPage('代理管理');$proxyPage.BackColor=[FlowSwitch.UI.Palette]::Surface
$tabs.TabPages.AddRange(@($programPage,$proxyPage,$toolsPage));$layout.Controls.Add($tabs,0,4)
$programGrid=New-Object Windows.Forms.TableLayoutPanel;$programGrid.Dock='Fill';$programGrid.Padding=New-Object Windows.Forms.Padding(12);$programGrid.RowCount=3;$programGrid.ColumnCount=1
[void]$programGrid.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Absolute,44)))
[void]$programGrid.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Percent,100)))
[void]$programGrid.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Absolute,43)))
$programPage.Controls.Add($programGrid)
$toolbar=New-Object Windows.Forms.Panel;$toolbar.Dock='Fill';$toolbar.Margin=New-Object Windows.Forms.Padding(0)
$programGrid.Controls.Add($toolbar,0,0)
$null=New-Label $toolbar '搜索程序' 0 6 74 26 10
$searchBox=New-Object Windows.Forms.TextBox;$searchBox.SetBounds(76,4,260,29);$toolbar.Controls.Add($searchBox)
$searchField=New-Object FlowSwitch.UI.SurfacePanel;$searchField.SetBounds(76,2,260,34);$searchField.BackColor=[FlowSwitch.UI.Palette]::Raised;$toolbar.Controls.Add($searchField)
$searchBox.BorderStyle='None';$searchField.Controls.Add($searchBox);$searchBox.SetBounds(10,7,240,22)
$savedOnly=New-Object Windows.Forms.CheckBox;$savedOnly.Text='只看已设规则';$savedOnly.SetBounds(352,4,140,30);$toolbar.Controls.Add($savedOnly)
$add=New-Button $toolbar '添加程序 / 快捷方式' 653 1 212 34 {Add-ProgramRule};$add.Anchor='Top,Right'
$refresh=New-Button $toolbar '刷新' 875 1 100 34 {Start-Work 'Status' ''};$refresh.Anchor='Top,Right'
$liveHost=New-Object FlowSwitch.UI.ListHost;$liveHost.Dock='Fill';$liveHost.Margin=New-Object Windows.Forms.Padding(0);$liveList=$liveHost.List;$liveList.Margin=New-Object Windows.Forms.Padding(0)
$liveList.View='Details';$liveList.FullRowSelect=$true;$liveList.GridLines=$false;$liveList.BorderStyle='None';$liveList.MultiSelect=$false
$liveList.HideSelection=$false;$liveList.HeaderStyle='Nonclickable';$liveList.ShowItemToolTips=$true;$liveList.ForeColor=$ink
foreach($column in @(@('程序',185),@('指定线路',100),@('已观察到的连接 / 线路',355),@('规则状态',320))){[void]$liveList.Columns.Add($column[0],[int]$column[1])}
$programGrid.Controls.Add($liveHost,0,1)
$emptyLabel=New-Label $liveList '未找到匹配程序。可清空搜索或添加 EXE / 快捷方式。' 25 65 700 50 11;$emptyLabel.ForeColor=$muted;$emptyLabel.Visible=$false
$bottom=New-Object Windows.Forms.Panel;$bottom.Dock='Fill';$bottom.Margin=New-Object Windows.Forms.Padding(0)
$programGrid.Controls.Add($bottom,0,2)
$programHint=New-Label $bottom '右键设置线路；也可拖入 EXE 或快捷方式。' 0 11 615 27 9;$programHint.ForeColor=$muted;$programHint.Anchor='Top,Left,Right'
$websiteButton=New-Button $bottom '网站分流…' 595 6 114 32 {Start-Work 'WebsiteRules' ''};$websiteButton.Anchor='Top,Right'
$detail=New-Button $bottom '程序详情' 719 6 114 32 {Show-AppDetails};$detail.Anchor='Top,Right'
$routeButton=New-Button $bottom '设置线路 ▾' 843 6 132 32 {Show-SelectedMenu};$routeButton.Anchor='Top,Right'
$toolbar.Add_SizeChanged({$refresh.Left=$toolbar.ClientSize.Width-$refresh.Width;$add.Left=$refresh.Left-$add.Width-10})
$bottom.Add_SizeChanged({$routeButton.Left=$bottom.ClientSize.Width-$routeButton.Width;$detail.Left=$routeButton.Left-$detail.Width-10;$websiteButton.Left=$detail.Left-$websiteButton.Width-10;$programHint.Width=[Math]::Max(100,$websiteButton.Left-10)})
$toolsGrid=New-Object Windows.Forms.TableLayoutPanel;$toolsGrid.Dock='Fill';$toolsGrid.Padding=New-Object Windows.Forms.Padding(14);$toolsGrid.RowCount=3;$toolsGrid.ColumnCount=1
foreach($h in @(48,56)){[void]$toolsGrid.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Absolute,$h)))}
[void]$toolsGrid.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Percent,100)))
$toolsPage.Controls.Add($toolsGrid)
$toolsBar=New-Object Windows.Forms.FlowLayoutPanel;$toolsBar.Dock='Fill';$toolsBar.WrapContents=$false;$toolsBar.Margin=New-Object Windows.Forms.Padding(0)
$toolsGrid.Controls.Add($toolsBar,0,0)
$null=New-Button $toolsBar '检测所选代理' 0 0 153 36 {if($networkChoice.SelectedItem -and $networkChoice.SelectedItem.Id -ne 'Direct'){Start-Work 'Diagnose' $networkChoice.SelectedItem.Id}else{Write-Activity '请先在上方选择一个代理。'}}
$null=New-Button $toolsBar 'Google 登录诊断' 0 0 158 36 {Start-Work 'LoginDiagnostic' ''}
$null=New-Button $toolsBar '重载程序规则' 0 0 153 36 {Start-Work 'AppSync' ''}
$null=New-Button $toolsBar '导出诊断报告' 0 0 170 36 {Export-Diagnostics}
$clientBar=New-Object Windows.Forms.FlowLayoutPanel;$clientBar.Dock='Fill';$clientBar.WrapContents=$false;$clientBar.Margin=New-Object Windows.Forms.Padding(0)
$toolsGrid.Controls.Add($clientBar,0,1)
$null=New-Button $clientBar '打开所选代理程序' 0 0 212 36 {if($networkChoice.SelectedItem -and $networkChoice.SelectedItem.Id -ne 'Direct'){Open-Client $networkChoice.SelectedItem.Id}else{Write-Activity '请先选择已关联程序的代理。'}}
$null=New-Button $clientBar '代理管理' 0 0 153 36 {$tabs.SelectedTab=$proxyPage}
$null=New-Label $clientBar '统一切换重置程序专线，保留网站例外；可撤回。' 0 0 510 36 9
$logHost=New-Object FlowSwitch.UI.LogHost;$logHost.Dock='Fill';$logBox=$logHost.Log;$logBox.Multiline=$true;$logBox.ReadOnly=$true;$logBox.ScrollBars='Vertical';$logBox.Dock='None'
$logBox.BackColor=[Drawing.ColorTranslator]::FromHtml('#1C2027');$logBox.ForeColor=$ink;$logBox.BorderStyle='None'
$toolsGrid.Controls.Add($logHost,0,2)
$actionLabel=New-Label $layout '选择目标 → 统一切换。也可右键程序指定单独线路。' 0 0 1000 32 9
$actionLabel.Dock='Fill';$actionLabel.TextAlign='MiddleLeft';$actionLabel.ForeColor=$muted;$layout.SetCellPosition($actionLabel,(New-Object Windows.Forms.TableLayoutPanelCellPosition(0,5)))
$footer=New-Object Windows.Forms.Panel;$footer.Dock='Fill';$footer.Margin=New-Object Windows.Forms.Padding(0);$layout.Controls.Add($footer,0,6)
$autoRefresh=New-Object Windows.Forms.CheckBox;$autoRefresh.Text='自动刷新';$autoRefresh.Checked=$true;$autoRefresh.SetBounds(0,0,105,24);$autoRefresh.ForeColor=$muted;$footer.Controls.Add($autoRefresh)
$autoDiscovery=New-Object Windows.Forms.CheckBox;$autoDiscovery.Text='自动发现代理';$autoDiscovery.Checked=$true;$autoDiscovery.SetBounds(110,0,140,24);$autoDiscovery.ForeColor=$muted;$footer.Controls.Add($autoDiscovery)
$autoDiscovery.Add_CheckedChanged({$script:NextPoll=[DateTime]::MinValue})
$countLabel=New-Label $footer '' 260 1 440 24 9;$countLabel.ForeColor=$muted
$checkedLabel=New-Label $footer '' 732 1 300 24 9;$checkedLabel.Anchor='Top,Right';$checkedLabel.TextAlign='TopRight';$checkedLabel.ForeColor=$muted
$footer.Add_SizeChanged({$checkedLabel.Left=$footer.ClientSize.Width-$checkedLabel.Width;$countLabel.Width=[Math]::Max(160,$checkedLabel.Left-$countLabel.Left-12)})
$appMenu=New-Object Windows.Forms.ContextMenuStrip;$appMenu.Font=$form.Font;$appMenu.ShowImageMargin=$false;$appMenu.Renderer=New-Object FlowSwitch.UI.MenuRenderer;$appMenu.BackColor=[FlowSwitch.UI.Palette]::Surface;$appMenu.ForeColor=$ink
$menuTitle=New-Object Windows.Forms.ToolStripMenuItem('程序分流');$menuTitle.Enabled=$false;[void]$appMenu.Items.Add($menuTitle)
foreach($option in @(@('跟随统一线路','Follow'),@('直连','Direct'))){
    $item=New-Object Windows.Forms.ToolStripMenuItem($option[0]);$item.Tag=$option[1]
    $item.Add_Click({if($script:AppTarget){Request-ApplicationRoute ([string]$this.Tag)}})
    [void]$appMenu.Items.Add($item)
}
[void]$appMenu.Items.Add((New-Object Windows.Forms.ToolStripSeparator))
$repairItem=New-Object Windows.Forms.ToolStripMenuItem('修复程序路径记录…');$repairItem.Add_Click({if($script:AppTarget.SavedPath){Start-Work 'AppRepairPlan' $script:AppTarget.SavedPath}});[void]$appMenu.Items.Add($repairItem)
$launchItem=New-Object Windows.Forms.ToolStripMenuItem('按指定线路打开（请先退出程序）');$launchItem.Add_Click({if($script:AppTarget){Start-Work 'AppLaunch' $script:AppTarget.Path}});[void]$appMenu.Items.Add($launchItem)
$entryRepairItem=New-Object Windows.Forms.ToolStripMenuItem('修复旧代理启动入口…');$entryRepairItem.Add_Click({if($script:AppTarget){Start-Work 'AppEntryRepair' $script:AppTarget.Path}});[void]$appMenu.Items.Add($entryRepairItem)
$websiteProgramItem=New-Object Windows.Forms.ToolStripMenuItem('此程序的网站分流…');$websiteProgramItem.Add_Click({if($script:AppTarget){Start-Work 'WebsiteRules' $script:AppTarget.Path}});[void]$appMenu.Items.Add($websiteProgramItem)
$removeSettingItem=New-Object Windows.Forms.ToolStripMenuItem('移除此程序设置');$removeSettingItem.Add_Click({if($script:AppTarget){$saved=$script:AppTarget.SavedPath;if(-not $saved){$saved=$script:AppTarget.Path};Start-Work 'AppRemove' $saved}});[void]$appMenu.Items.Add($removeSettingItem)
$reconnectItem=New-Object Windows.Forms.ToolStripMenuItem('重连此程序的旧线路连接…');$reconnectItem.Add_Click({if($script:AppTarget){Start-Work 'AppReconnectPlan' $script:AppTarget.Path}});[void]$appMenu.Items.Add($reconnectItem)
$entryItem=New-Object Windows.Forms.ToolStripMenuItem('复制代理启动入口');$entryItem.Add_Click({
    try{$entries=@(Get-VerifiedProgramShortcuts $script:AppTarget.Path);if(-not $entries.Count){throw '没有可验证的代理入口，请重新指定该程序线路。'};[Windows.Forms.Clipboard]::SetText(($entries -join "`r`n"));Write-Activity ('已复制代理入口：'+($entries -join '；'))}catch{Write-Activity $_.Exception.Message}
});[void]$appMenu.Items.Add($entryItem)
$copyItem=New-Object Windows.Forms.ToolStripMenuItem('复制程序路径');$copyItem.Add_Click({if($script:AppTarget){[Windows.Forms.Clipboard]::SetText($script:AppTarget.Path);Write-Activity '已复制所选程序的路径。'}});[void]$appMenu.Items.Add($copyItem)
$appMenu.Add_Opening({
    if(-not $script:AppTarget.Path -or ($script:Worker -and $script:Worker.Kind -ne 'Status')){$_.Cancel=$true;return}
    $script:MenuOpen=$true;$menuTitle.Text=$script:AppTarget.Name;$launchItem.Enabled=[bool]$script:AppTarget.CanLaunch;$entryItem.Enabled=[bool]$script:AppTarget.CanLaunch
    $launchItem.Visible=[bool]$script:AppTarget.CanLaunch;$entryItem.Visible=[bool]$script:AppTarget.CanLaunch;$reconnectItem.Enabled=([bool](Get-GatewayKey) -and -not $script:AppTarget.RequiresRepair -and $script:LastApps.Available -and $script:LastApps.RulesAvailable -and ($script:AppTarget.Mode -eq 'engine' -or ($script:LastApps.DefaultRoute -and $script:LastApps.DefaultLoaded)));$repairItem.Visible=[bool]$script:AppTarget.RequiresRepair;$repairItem.Enabled=[bool]$script:AppTarget.CanRepair
    foreach($item in @($appMenu.Items)){if($item.Tag -and $item.Tag -notin @('Follow','Direct')){$appMenu.Items.Remove($item);$item.Dispose()}}
    $entryRepairItem.Visible=($script:AppTarget.Mode -in @('launch','managed') -and -not $script:AppTarget.RequiresRepair)
    $websiteProgramItem.Enabled=(-not $script:AppTarget.RequiresRepair)
    $removeSettingItem.Visible=[bool]($script:AppTarget.SavedPath -or $script:AppTarget.HasSavedRule)
    $insert=3
    foreach($p in $script:Profiles.Profiles){
        if($script:Profiles.Routing.Adapter -eq 'standalone' -and $p.Id -eq (Get-GatewayKey)){continue}
        $item=New-Object Windows.Forms.ToolStripMenuItem($p.Name);$item.Tag=$p.Id
        $item.Add_Click({if($script:AppTarget){Request-ApplicationRoute ([string]$this.Tag)}})
        $appMenu.Items.Insert($insert,$item);$insert++
    }
    foreach($item in $appMenu.Items){if($item -is [Windows.Forms.ToolStripMenuItem] -and $item.Tag){$item.Checked=($item.Tag -eq $script:AppTarget.Policy);$item.Enabled=(-not $script:AppTarget.RequiresRepair)}}
})
$appMenu.Add_Closed({$script:MenuOpen=$false;if($script:DeferredApps){Show-Applications $script:DeferredApps;$script:DeferredApps=$null}})
$liveList.Add_MouseDown({if($_.Button -eq 'Right'){$hit=$liveList.GetItemAt($_.X,$_.Y);if($hit){$hit.Selected=$true;$script:AppTarget=$hit.Tag;$appMenu.Show($liveList,$_.Location)}}})
$liveList.Add_DoubleClick({Show-AppDetails})
$searchBox.Add_TextChanged({if($script:LastApps){Show-Applications $script:LastApps}})
$savedOnly.Add_CheckedChanged({if($script:LastApps){Show-Applications $script:LastApps}})
$form.Add_KeyDown({if($_.Control -and $_.KeyCode -eq 'F'){$tabs.SelectedIndex=0;$searchBox.Focus();$_.SuppressKeyPress=$true};if($_.KeyCode -eq 'F5'){Start-Work 'Status' '';$_.SuppressKeyPress=$true}})
$form.Add_DragEnter({if($_.Data.GetDataPresent([Windows.Forms.DataFormats]::FileDrop)){$_.Effect='Copy'}})
$form.Add_DragDrop({$files=$_.Data.GetData([Windows.Forms.DataFormats]::FileDrop);if($files.Count -eq 1){Add-ProgramRule $files[0]}else{Write-Activity '每次拖入一个程序，便于确认对应线路。'}})
$proxyGrid=New-Object Windows.Forms.TableLayoutPanel;$proxyGrid.Dock='Fill';$proxyGrid.Padding=New-Object Windows.Forms.Padding(14);$proxyGrid.ColumnCount=1;$proxyGrid.RowCount=4
foreach($height in @(50,88)){[void]$proxyGrid.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Absolute,$height)))}
[void]$proxyGrid.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Percent,100)))
[void]$proxyGrid.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Absolute,42)))
$proxyPage.Controls.Add($proxyGrid)
$intro=New-Label $proxyGrid '自动识别后台代理，持续观察程序连接；使用哪条线路由你决定。' 0 0 980 46 10;$intro.Dock='Fill';$proxyGrid.SetCellPosition($intro,(New-Object Windows.Forms.TableLayoutPanelCellPosition(0,0)))
$proxyBar=New-Object Windows.Forms.FlowLayoutPanel;$proxyBar.Dock='Fill';$proxyBar.WrapContents=$true;$proxyGrid.Controls.Add($proxyBar,0,1)
$null=New-Button $proxyBar '添加代理' 0 0 128 35 {Show-ProfileEditor}
$null=New-Button $proxyBar '编辑' 0 0 92 35 {Edit-SelectedProfile}
$null=New-Button $proxyBar '删除' 0 0 92 35 {Remove-SelectedProfile}
$null=New-Button $proxyBar '检测并添加后台代理' 0 0 174 35 {Start-Work 'Discover' ''}
$null=New-Button $proxyBar '检测选中项' 0 0 145 35 {if($proxyList.SelectedItems.Count){Start-Work 'Diagnose' $proxyList.SelectedItems[0].Tag.Id}else{Write-Activity '请先选中一个代理。'}}
$null=New-Button $proxyBar '配置分流引擎' 0 0 132 35 {Start-Work 'ConfigureGateway' ''}
$null=New-Button $proxyBar '启用独立分流' 0 0 132 35 {Start-Work 'Independent' ''}
$null=New-Button $proxyBar '自动接替设置' 0 0 132 35 {Show-FailoverEditor}
$proxyHost=New-Object FlowSwitch.UI.ListHost;$proxyHost.Dock='Fill';$proxyList=$proxyHost.List;$proxyList.View='Details';$proxyList.FullRowSelect=$true;$proxyList.MultiSelect=$false;$proxyList.HideSelection=$false
foreach($column in @(@('名称',240),@('协议',100),@('地址',245),@('端口',85),@('用途',135),@('状态',150))){[void]$proxyList.Columns.Add($column[0],[int]$column[1])}
$proxyGrid.Controls.Add($proxyHost,0,2);$proxyList.Add_DoubleClick({Edit-SelectedProfile})
$proxyEmpty=New-Label $proxyList '正在自动识别后台代理；也可添加自定义地址。发现代理不会自动切换网络。' 28 60 750 45 12;$proxyEmpty.ForeColor=$muted
$engineLabel=New-Label $proxyGrid '' 0 0 980 36 9;$engineLabel.Dock='Fill';$engineLabel.TextAlign='MiddleLeft';$engineLabel.ForeColor=$muted;$proxyGrid.SetCellPosition($engineLabel,(New-Object Windows.Forms.TableLayoutPanelCellPosition(0,3)))
function Request-ApplicationRoute([string]$Route) {
    if($script:AppTarget.RequiresRepair){Write-Activity '程序路径已变化，请先修复路径记录；也可移除旧设置后重新添加。';return}
    Start-Work 'ManagedAppRoute' (@{path=$script:AppTarget.Path;route=$Route}|ConvertTo-Json -Compress)
}
function Get-ApplicationDisplayKey($App) {if($App.RowKey){return $App.RowKey};return $App.Path}
function Show-SelectedMenu {
    if(-not $liveList.SelectedItems.Count){Write-Activity '请先选中一个程序。';return}
    $script:AppTarget=$liveList.SelectedItems[0].Tag;$appMenu.Show($routeButton,(New-Object Drawing.Point(0,$routeButton.Height)))
}
function Add-ProgramRule([string]$TargetPath='') {
    if($script:Worker -and $script:Worker.Kind -ne 'Status'){return}
    $script:DialogOpen=$true
    try{
        if(-not $TargetPath){
            $picker=New-Object Windows.Forms.OpenFileDialog;$picker.Filter='程序或快捷方式 (*.exe;*.lnk)|*.exe;*.lnk';$picker.Title='选择程序或桌面快捷方式';$picker.DereferenceLinks=$false
            try{if($picker.ShowDialog($form) -ne 'OK'){return};$TargetPath=$picker.FileName}finally{$picker.Dispose()}
        }
        $path=Resolve-ProgramTarget $TargetPath
        $match=$script:LastApps.Rows | Where-Object {$_.Path -ieq $path} | Select-Object -First 1
        $policy='Follow';if($match){$policy=$match.Policy}
        if($match){$script:AppTarget=$match}else{$script:AppTarget=[pscustomobject]@{Path=$path;Name=[IO.Path]::GetFileNameWithoutExtension($path);Policy=$policy;SavedPath='';RequiresRepair=$false;CanRepair=$false}}
        $appMenu.Show([Windows.Forms.Cursor]::Position)
    }catch{Write-Activity $_.Exception.Message}finally{$script:DialogOpen=$false}
}
function Show-AppDetails {
    if(-not $liveList.SelectedItems.Count){Write-Activity '请先选中一个程序。';return}
    $app=$liveList.SelectedItems[0].Tag;$script:DialogOpen=$true
    try{
        $entryText=''
        if($app.CanLaunch){$entries=@(Get-VerifiedProgramShortcuts $app.Path);$entryText="`r`n`r`n代理启动入口：`r`n"+$(if($entries.Count){$entries -join "`r`n"}else{'入口不存在或已被修改，请重新指定线路。'})+"`r`n请完整退出后使用上述入口，或右键「按指定线路打开」。其他启动入口未接入此设置。"}
        [void][Windows.Forms.MessageBox]::Show($form,($app.Name+"`r`n`r`n程序路径："+$app.Path+"`r`n保存的路径："+$app.SavedPath+"`r`n身份识别："+$app.IdentityReason+"`r`n`r`n进程 ID："+$(if($app.PIDs){$app.PIDs}else{'未运行'})+"`r`n实际连接："+$app.Actual+"`r`n线路状态："+$app.Status+$entryText+"`r`n`r`n已识别子进程："+$app.ChildNames+"。接入固定入口的主程序与继承入口的子进程可一起改线；仍保留旧代理地址的进程需要完整重开。未经过入口的连接不能靠保存设置强制改变。`r`n`r`n观察范围："+$app.Coverage+"`r`n未观察到连接不等于断网；已建立连接也不证明登录成功。"),'程序详情','OK','Information')
    }finally{$script:DialogOpen=$false}
}
function Show-Guide {
    $script:DialogOpen=$true
    try{[void][Windows.Forms.MessageBox]::Show($form,@'
① 添加代理
自动读取当前代理配置与端口所属进程；属于代理程序的入口可自动识别协议并加入列表。成功结果缓存，避免每次刷新重复探测。游戏的实际连接仍持续观察；不向游戏通信端口发送代理握手。

② 统一切换
在上方选择直连或已添加代理，点击「统一切换」。它会同步统一出口，将程序专用线路重置为跟随，并保留网站例外；切换前设置会备份，支持撤回。

③ 按程序指定线路
右键程序选择直连、代理或跟随统一线路。工具会选择适用的接入方式，并说明是否需要完整重开。受支持程序通过代理启动入口打开后，主程序及继承此入口的子进程一起使用稳定入口；以后切换出口无需更换其代理地址。已有进程的旧地址不会被强行改写。

④ 同一浏览器的网站分流
点击「网站分流」添加只需直连或只需代理的域名，可应用到所有程序或已接入的指定程序。同一浏览器可按不同网站使用不同线路。同一范围内更具体域名优先；同名时「仅此域名」优先。只填域名，不填写登录链接、查询参数或凭据。网站例外在统一切换时保留。

⑤ 程序升级或路径变更
注册商店应用升级后会关联同一包内的程序；旧规则仍标为待修复。右键「修复程序路径记录」可核对旧、新路径并保存，已有线路选择保留。歧义候选不自动套用。普通程序移动后可移除旧记录，再重新添加。

⑥ 旧连接处理
切换不会自动断开对话、下载或游戏。需要时右键「重连此程序的旧线路连接」，核对数量后确认。只处理此 EXE 经过引擎且仍走旧线路的连接，不结束进程；由应用自行重连。规则变化或预览超时后拒绝执行。

统一切换只影响遵循系统代理或分流引擎的新连接。已有连接、独立代理与 VPN 隧道可能仍需手动处理；本工具不会结束程序或自动启用 TUN。

拖入 EXE / 快捷方式可添加程序；Ctrl+F 搜索，F5 刷新。本机设置与备份默认位于 %USERPROFILE%\.proxyswitch。
'@,'使用指南','OK','Information')}finally{$script:DialogOpen=$false}
}
function ConvertTo-WebsiteRuleDomain([string]$Value) {
    $domain=$Value.Trim().TrimEnd('.')
    if(-not $domain -or $domain -match '[:/\\?#@\s*]'){throw '只填写域名，例如 example.com；不要粘贴网址、登录链接、端口或授权信息。'}
    try{$domain=(New-Object Globalization.IdnMapping).GetAscii($domain).ToLowerInvariant()}catch{throw '域名格式无效，请检查拼写。'}
    if($domain.Length -gt 253 -or $domain -notmatch '^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$'){throw '域名格式无效，请只填写有效域名。'}
    $ip=$null;if([Net.IPAddress]::TryParse($domain,[ref]$ip)){throw '请填写域名；此编辑器不保存 IP 地址规则。'}
    return $domain
}
function Update-WebsiteRuleList($Dialog) {
    $state=$Dialog.Tag;$state.List.BeginUpdate();$state.List.Items.Clear()
    foreach($entry in $state.Entries){
        $scope=$(if($entry.Executable){[IO.Path]::GetFileNameWithoutExtension($entry.Executable)}else{'所有程序'})
        $item=New-Object Windows.Forms.ListViewItem($scope);$item.Tag=$entry;$item.ToolTipText=$entry.Executable
        foreach($value in @($entry.Domain,$(if($entry.Match -eq 'suffix'){'域名及其子域'}else{'仅此域名'}),(Get-RouteName $entry.Route))){[void]$item.SubItems.Add($value)}
        [void]$state.List.Items.Add($item)
    }
    $state.List.EndUpdate();$state.Count.Text='共 '+$state.Entries.Count+' 条网站例外；保存后应用，取消不会更改线路。'
}
function New-WebsiteRuleEditor($Snapshot) {
    $dialog=New-Object Windows.Forms.Form;$dialog.Text='网站分流';$dialog.ClientSize=New-Object Drawing.Size(930,590);$dialog.MinimumSize=New-Object Drawing.Size(850,560)
    $dialog.Font=$form.Font;$dialog.StartPosition='CenterParent';$dialog.MaximizeBox=$false;$dialog.MinimizeBox=$false;$dialog.BackColor=$paper;$dialog.ForeColor=$ink
    $grid=New-Object Windows.Forms.TableLayoutPanel;$grid.Dock='Fill';$grid.Padding=New-Object Windows.Forms.Padding(18);$grid.ColumnCount=1;$grid.RowCount=6
    foreach($height in @(64,38)){[void]$grid.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Absolute,$height)))}
    [void]$grid.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Percent,100)))
    foreach($height in @(82,43,42)){[void]$grid.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Absolute,$height)))}
    $dialog.Controls.Add($grid)
    $intro=New-Label $grid '同一个浏览器，不同网站可以分别直连或走代理。只保存域名，不填写登录链接。指定程序的网站例外优先于全局例外；同一范围内更具体域名优先，同名时「仅此域名」优先。网站例外优先于程序线路，统一切换会保留这些例外。' 0 0 880 60 10;$intro.Dock='Fill';$grid.SetCellPosition($intro,(New-Object Windows.Forms.TableLayoutPanelCellPosition(0,0)))
    $ruleState=$(if(-not $Snapshot.Available){'入口状态不可用，现有规则是否生效尚未确认'}elseif(-not $Snapshot.Loaded){'网站规则尚未加载'}else{'网站规则已加载'})
    $status=New-Label $grid ($ruleState+' · '+$(if($Snapshot.Message){$Snapshot.Message}else{'保存并应用后会重新核验；实际使用仍以连接证据为准。'})) 0 0 880 34 9;$status.ForeColor=$muted;$status.Dock='Fill';$grid.SetCellPosition($status,(New-Object Windows.Forms.TableLayoutPanelCellPosition(0,1)))
    $hostPanel=New-Object FlowSwitch.UI.ListHost;$hostPanel.Dock='Fill';$list=$hostPanel.List;$list.View='Details';$list.FullRowSelect=$true;$list.MultiSelect=$false;$list.HideSelection=$false;$list.ShowItemToolTips=$true
    foreach($column in @(@('范围',180),@('域名',320),@('匹配',145),@('线路',200))){[void]$list.Columns.Add($column[0],[int]$column[1])};$list.SetColumnWeights([double[]]@(0.22,0.36,0.18,0.24));$grid.Controls.Add($hostPanel,0,2)
    $editor=New-Object Windows.Forms.TableLayoutPanel;$editor.Dock='Fill';$editor.ColumnCount=4;$editor.RowCount=2
    foreach($width in @(26,34,20,20)){[void]$editor.ColumnStyles.Add((New-Object Windows.Forms.ColumnStyle([Windows.Forms.SizeType]::Percent,$width)))}
    [void]$editor.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Absolute,27)));[void]$editor.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Percent,100)))
    $grid.Controls.Add($editor,0,3)
    $scope=New-Object FlowSwitch.UI.RouteChoice;$scope.Name='WebsiteScope';$scope.DropDownStyle='DropDownList';$scope.DisplayMember='Name';$scope.Dock='Top'
    [void]$scope.Items.Add([pscustomobject]@{Name='所有程序';Executable=''})
    $paths=@($Snapshot.ContextExecutable)+@($Snapshot.Entries|ForEach-Object Executable)
    foreach($path in @($paths|Where-Object {$_}|Select-Object -Unique)){[void]$scope.Items.Add([pscustomobject]@{Name=[IO.Path]::GetFileNameWithoutExtension($path);Executable=$path})};$scope.SelectedIndex=0
    if($Snapshot.ContextExecutable){for($i=0;$i -lt $scope.Items.Count;$i++){if($scope.Items[$i].Executable -ieq $Snapshot.ContextExecutable){$scope.SelectedIndex=$i;break}}}
    $domain=New-Object Windows.Forms.TextBox;$domain.Name='WebsiteDomain';$domain.Dock='Top';$domain.MaxLength=253
    $match=New-Object FlowSwitch.UI.RouteChoice;$match.Name='WebsiteMatch';$match.DropDownStyle='DropDownList';$match.DisplayMember='Name';$match.Dock='Top'
    [void]$match.Items.Add([pscustomobject]@{Name='仅此域名';Id='exact'});[void]$match.Items.Add([pscustomobject]@{Name='域名及其子域';Id='suffix'});$match.SelectedIndex=1
    $route=New-Object FlowSwitch.UI.RouteChoice;$route.Name='WebsiteRoute';$route.DropDownStyle='DropDownList';$route.DisplayMember='Name';$route.Dock='Top';[void]$route.Items.Add([pscustomobject]@{Name='直连';Id='Direct'})
    foreach($profile in $script:Profiles.Profiles){if($script:Profiles.Routing.Adapter -eq 'standalone' -and $profile.Id -eq (Get-GatewayKey)){continue};[void]$route.Items.Add([pscustomobject]@{Name=$profile.Name;Id=$profile.Id})};$route.SelectedIndex=0
    $controls=@($scope,$domain,$match,$route);$labels=@('适用范围','域名，例如 example.com','匹配方式','使用线路')
    for($i=0;$i -lt 4;$i++){$label=New-Label $editor $labels[$i] 0 0 200 25 9;$label.Dock='Fill';$editor.SetCellPosition($label,(New-Object Windows.Forms.TableLayoutPanelCellPosition($i,0)));$controls[$i].Margin=New-Object Windows.Forms.Padding(0,0,10,0);$editor.Controls.Add($controls[$i],$i,1)}
    $editBar=New-Object Windows.Forms.Panel;$editBar.Dock='Fill';$grid.Controls.Add($editBar,0,4)
    $addRule=New-Object FlowSwitch.UI.ActionButton;$addRule.Name='WebsiteAdd';$addRule.Text='添加 / 更新';$addRule.SetBounds(0,0,120,33);$editBar.Controls.Add($addRule)
    $removeRule=New-Object FlowSwitch.UI.ActionButton;$removeRule.Name='WebsiteRemove';$removeRule.Text='删除选中';$removeRule.SetBounds(130,0,110,33);$editBar.Controls.Add($removeRule)
    $errorLabel=New-Label $editBar '' 252 4 620 34 9;$errorLabel.ForeColor=[Drawing.ColorTranslator]::FromHtml('#E5A6A2');$errorLabel.Anchor='Top,Left,Right'
    $bottom=New-Object Windows.Forms.Panel;$bottom.Dock='Fill';$grid.Controls.Add($bottom,0,5)
    $count=New-Label $bottom '' 0 5 600 32 9;$count.Name='WebsiteCount';$count.ForeColor=$muted;$count.Anchor='Top,Left,Right'
    $cancel=New-Object FlowSwitch.UI.ActionButton;$cancel.Text='取消';$cancel.Name='WebsiteCancel';$cancel.SetBounds(655,0,94,34);$cancel.Anchor='Top,Right';$cancel.DialogResult='Cancel';$bottom.Controls.Add($cancel)
    $save=New-Object FlowSwitch.UI.ActionButton;$save.Name='WebsiteSave';$save.Text='保存并应用';$save.SetBounds(760,0,134,34);$save.Anchor='Top,Right';$save.Primary=$true;$bottom.Controls.Add($save);$dialog.CancelButton=$cancel
    $bottom.Add_Layout({$saveButton=$this.Controls['WebsiteSave'];$cancelButton=$this.Controls['WebsiteCancel'];$saveButton.Left=$this.ClientSize.Width-$saveButton.Width;$cancelButton.Left=$saveButton.Left-$cancelButton.Width-10;$this.Controls['WebsiteCount'].Width=[Math]::Max(100,$cancelButton.Left-10)})
    $entries=New-Object Collections.ArrayList
    foreach($entry in @($Snapshot.Entries)){if($entry){[void]$entries.Add([pscustomobject]@{Id=$entry.Id;Domain=$entry.Domain;Match=$entry.Match;Route=$entry.Route;Executable=$entry.Executable})}}
    $dialog.Tag=[pscustomobject]@{Entries=$entries;Revision=$Snapshot.Revision;List=$list;Scope=$scope;Domain=$domain;Match=$match;Route=$route;Error=$errorLabel;Count=$count;Status=$status;Result=$null}
    $addRule.Add_Click({
        $window=$this.FindForm();$state=$window.Tag
        try{
            $value=ConvertTo-WebsiteRuleDomain $state.Domain.Text
            if(-not $state.Scope.SelectedItem -or -not $state.Match.SelectedItem -or -not $state.Route.SelectedItem){throw '请选择有效的范围、匹配方式和线路；原代理可能已从列表中移除。'}
            $executable=$state.Scope.SelectedItem.Executable;$matchId=$state.Match.SelectedItem.Id;$routeId=$state.Route.SelectedItem.Id
            $existing=@($state.Entries|Where-Object {$_.Domain -ieq $value -and $_.Match -eq $matchId -and $_.Executable -ieq $executable})|Select-Object -First 1
            if($existing){$existing.Route=$routeId}else{[void]$state.Entries.Add([pscustomobject]@{Id=[Guid]::NewGuid().ToString('N');Domain=$value;Match=$matchId;Route=$routeId;Executable=$executable})}
            $state.Error.Text='';$state.Domain.Text='';Update-WebsiteRuleList $window
        }catch{$state.Error.Text=$_.Exception.Message}
    })
    $removeRule.Add_Click({$window=$this.FindForm();$state=$window.Tag;if($state.List.SelectedItems.Count){$state.Entries.Remove($state.List.SelectedItems[0].Tag);$state.Error.Text='';$state.Domain.Text='';Update-WebsiteRuleList $window}else{$state.Error.Text='请先选中要删除的网站规则。'}})
    $list.Add_SelectedIndexChanged({
        if($this.SelectedItems.Count){$state=$this.FindForm().Tag;$entry=$this.SelectedItems[0].Tag;$state.Domain.Text=$entry.Domain;$state.Route.SelectedIndex=-1
            foreach($pair in @(@($state.Scope,'Executable',$entry.Executable),@($state.Match,'Id',$entry.Match),@($state.Route,'Id',$entry.Route))){for($i=0;$i -lt $pair[0].Items.Count;$i++){if($pair[0].Items[$i].($pair[1]) -ieq $pair[2]){$pair[0].SelectedIndex=$i;break}}}
        }
    })
    $save.Add_Click({$window=$this.FindForm();$state=$window.Tag
        if($state.Domain.Text.Trim()){
            $existing=@($state.Entries|Where-Object {$_.Domain -ieq $state.Domain.Text.Trim().TrimEnd('.') -and $_.Executable -ieq $state.Scope.SelectedItem.Executable -and $_.Match -eq $state.Match.SelectedItem.Id -and $_.Route -eq $state.Route.SelectedItem.Id})
            if(-not $existing.Count){$state.Error.Text='输入尚未加入列表，请先点击「添加 / 更新」，或清空域名输入后保存。';return}
        }
        $state.Result=[pscustomobject]@{Entries=@($state.Entries.ToArray());Revision=$state.Revision};$window.DialogResult='OK';$window.Close()
    })
    [FlowSwitch.UI.Palette]::Apply($dialog);Update-WebsiteRuleList $dialog
    return $dialog
}
function Show-WebsiteRulesEditor($Snapshot) {
    $script:DialogOpen=$true;$dialog=$null
    try{
        $dialog=New-WebsiteRuleEditor $Snapshot
        if($dialog.ShowDialog($form) -eq 'OK'){$script:PendingAction=[pscustomobject]@{Kind='WebsiteRulesSave';Key=($dialog.Tag.Result|ConvertTo-Json -Depth 8 -Compress)}}
    }catch{Write-Activity $_.Exception.Message}finally{if($dialog){$dialog.Dispose()};$script:DialogOpen=$false}
}
function Show-ProfileEditor($Profile=$null) {
    $script:DialogOpen=$true
    $current=Read-ProfileSettings
    if(-not $Profile){$Profile=[pscustomobject]@{Id=('p'+[Guid]::NewGuid().ToString('N').Substring(0,12));Name='新代理';Protocol='http';Host='127.0.0.1';Port=8080;AppPath='';CorePath='';AutoPort=$false}}
    $dialog=New-Object Windows.Forms.Form;$dialog.Text='编辑代理';$dialog.ForeColor=$ink;$dialog.ClientSize=New-Object Drawing.Size(730,518);$dialog.Font=$form.Font;$dialog.BackColor=$paper
    $dialog.StartPosition='CenterParent';$dialog.FormBorderStyle='FixedDialog';$dialog.MaximizeBox=$false;$dialog.MinimizeBox=$false
    $null=New-Label $dialog '代理入口' 20 15 400 30 16 $true
    $fields=@{}
    $specs=@(@('Name','名称',62),@('Host','地址',142),@('AppPath','关联程序（可选）',222),@('CorePath','分流内核（可选）',262))
    foreach($spec in $specs){
        $null=New-Label $dialog $spec[1] 20 $spec[2] 167 28 10
        $box=New-Object Windows.Forms.TextBox;$box.SetBounds(190,$spec[2],435,28);$box.Text=$Profile.($spec[0]);$dialog.Controls.Add($box);$fields[$spec[0]]=$box
        if($spec[0] -in @('AppPath','CorePath')){
            $browse=New-Button $dialog '选择' 636 ($spec[2]-1) 74 30 {$p=New-Object Windows.Forms.OpenFileDialog;$p.Filter='Windows 程序 (*.exe)|*.exe';try{if($p.ShowDialog($dialog) -eq 'OK'){$this.Tag.Text=$p.FileName}}finally{$p.Dispose()}};$browse.Tag=$box
        }
    }
    $null=New-Label $dialog '协议' 20 102 150 28 10
    $protocol=New-Object Windows.Forms.ComboBox;$protocol.DropDownStyle='DropDownList';$protocol.SetBounds(190,102,190,29);[void]$protocol.Items.Add('HTTP');[void]$protocol.Items.Add('SOCKS5');$protocol.SelectedItem=$Profile.Protocol.ToUpperInvariant();$dialog.Controls.Add($protocol)
    $null=New-Label $dialog '端口' 20 182 150 28 10
    $port=New-Object Windows.Forms.NumericUpDown;$port.SetBounds(190,182,150,29);$port.Minimum=1;$port.Maximum=65535;$port.Value=$Profile.Port;$dialog.Controls.Add($port)
    $engine=New-Object Windows.Forms.CheckBox;$engine.Text='用作程序分流引擎（Clash Verge 的 HTTP / 混合入口）';$engine.SetBounds(20,310,685,30);$engine.Checked=($current.Routing.ProfileId -eq $Profile.Id);$dialog.Controls.Add($engine)
    $auto=New-Object Windows.Forms.CheckBox;$auto.Text='自动读取分流引擎的端口';$auto.SetBounds(20,348,660,28);$auto.Checked=[bool]$Profile.AutoPort;$auto.Enabled=$engine.Checked;$dialog.Controls.Add($auto)
    $fixed=New-Object Windows.Forms.CheckBox;$fixed.Text='固定本地入口：切换 HTTP / SOCKS5 / 直连时只更改引擎出口';$fixed.SetBounds(20,383,690,30);$fixed.Checked=($current.Routing.UnifiedMode -eq 'gateway' -or $current.Routing.Adapter -eq 'none');$fixed.Enabled=$engine.Checked;$dialog.Controls.Add($fixed)
    $engine.Add_CheckedChanged({$auto.Enabled=$engine.Checked;$fixed.Enabled=$engine.Checked})
    $null=New-Label $dialog '引擎需保持运行；不遵循代理的程序不会自动被接管。保存后再手动切换。' 20 425 690 27 9
    $save=New-Button $dialog '保存代理' 570 467 140 35 {
        try{
            $entry=[pscustomobject]@{Id=$Profile.Id;Name=$fields.Name.Text;Protocol=$protocol.SelectedItem.ToString().ToLowerInvariant();Host=$fields.Host.Text;Port=[int]$port.Value;AppPath=$fields.AppPath.Text;CorePath=$fields.CorePath.Text;AutoPort=($engine.Checked -and $auto.Checked)}
            $value=Read-ProfileSettings;$value.Profiles=@($value.Profiles | Where-Object {$_.Id -ne $entry.Id})+@($entry)
            if($engine.Checked){$value.Routing=[pscustomobject]@{Adapter='clash-verge';ProfileId=$entry.Id;UnifiedMode=$(if($fixed.Checked){'gateway'}else{'system'})}}
            elseif($value.Routing.ProfileId -eq $entry.Id){$value.Routing=[pscustomobject]@{Adapter='none';ProfileId=''}}
            Save-ProfileSettings $value;$dialog.DialogResult='OK';$dialog.Close()
        }catch{[void][Windows.Forms.MessageBox]::Show($dialog,$_.Exception.Message,'无法保存','OK','Warning')}
    }
    [FlowSwitch.UI.Palette]::Apply($dialog)
    try{if($dialog.ShowDialog($form) -eq 'OK'){Reload-ProfileViews;Write-Activity '代理已保存。选择目标后点击「统一切换」应用到网络；已有程序规则可重新载入。';$script:NextPoll=[DateTime]::MinValue}}
    finally{$dialog.Dispose();$script:DialogOpen=$false;$script:Controls=@($script:Controls | Where-Object {-not $_.IsDisposed})}
}
function Show-FailoverEditor {
    if($script:Profiles.Routing.Adapter -ne 'standalone'){Write-Activity '请先启用独立分流，再设置备用顺序。';return}
    $dialog=New-Object Windows.Forms.Form;$dialog.Text='自动接替设置';$dialog.ClientSize=New-Object Drawing.Size(570,410);$dialog.Font=$form.Font;$dialog.StartPosition='CenterParent'
    $enabled=New-Object Windows.Forms.CheckBox;$enabled.Text='代理失效时自动使用备用线路';$enabled.SetBounds(20,15,500,28);$enabled.Checked=$script:Profiles.Routing.Failover.Enabled;$dialog.Controls.Add($enabled)
    $list=New-Object Windows.Forms.ListBox;$list.SetBounds(20,52,425,215);$list.DisplayMember='Name';$dialog.Controls.Add($list)
    foreach($id in $script:Profiles.Routing.Failover.Order){$p=Get-Profile $id;[void]$list.Items.Add($p)}
    foreach($spec in @(@('上移',-1,60),@('下移',1,105))){$button=New-Object Windows.Forms.Button;$button.Text=$spec[0];$button.Tag=$spec[1];$button.SetBounds(462,$spec[2],85,34);$dialog.Controls.Add($button);$button.Add_Click({$index=$list.SelectedIndex;$next=$index+[int]$this.Tag;if($index -ge 0 -and $next -ge 0 -and $next -lt $list.Items.Count){$item=$list.Items[$index];$list.Items.RemoveAt($index);$list.Items.Insert($next,$item);$list.SelectedIndex=$next}})}
    $direct=New-Object Windows.Forms.CheckBox;$direct.Text='全部代理失效时允许直连（默认关闭）';$direct.SetBounds(20,282,525,28);$direct.Checked=$script:Profiles.Routing.Failover.AllowDirect;$dialog.Controls.Add($direct)
    $note=New-Object Windows.Forms.Label;$note.Text='每个程序先使用它指定的线路，再按上面顺序尝试。连续失败后切换；恢复后保留可用备用线路，避免来回跳。';$note.SetBounds(20,316,525,46);$dialog.Controls.Add($note)
    $save=New-Object Windows.Forms.Button;$save.Text='保存';$save.SetBounds(445,365,100,32);$dialog.Controls.Add($save)
    $save.Add_Click({try{
        $value=Read-ProfileSettings;$value.Routing.Failover=[pscustomobject]@{Enabled=$enabled.Checked;Order=@($list.Items|ForEach-Object Id);AllowDirect=$direct.Checked}
        $before=Read-ProfileSettings
        Save-ProfileSettings $value
        try{Sync-ApplicationRoutes | Out-Null}catch{Save-ProfileSettings $before;throw}
        Reload-ProfileViews $value;Write-Activity '自动接替策略已保存并载入。';$dialog.Close()
    }catch{[void][Windows.Forms.MessageBox]::Show($dialog,$_.Exception.Message,'设置未完成','OK','Warning')}})
    try{[void]$dialog.ShowDialog($form)}finally{$dialog.Dispose()}
}
function Edit-SelectedProfile {
    if(-not $proxyList.SelectedItems.Count){Write-Activity '请先在代理管理中选中一个代理。';return}
    Show-ProfileEditor $proxyList.SelectedItems[0].Tag
}
function Remove-SelectedProfile {
    if(-not $proxyList.SelectedItems.Count){Write-Activity '请先选择一个代理。';return}
    try{
        $selected=$proxyList.SelectedItems[0].Tag;$value=Read-ProfileSettings
        $value.Profiles=@($value.Profiles | Where-Object {$_.Id -ne $selected.Id})
        if($selected.Host -in @('127.0.0.1','::1','localhost')){$value.DiscoveryIgnored=@($value.DiscoveryIgnored)+@((Get-LocalEndpointId $selected.Host $selected.Port))}
        if($value.Routing.ProfileId -eq $selected.Id){$value.Routing=[pscustomobject]@{Adapter='none';ProfileId=''}}
        Save-ProfileSettings $value;Reload-ProfileViews;Write-Activity '该代理已从列表移除，修改前设置已备份。'
    }catch{Write-Activity $_.Exception.Message}
}
function Reload-ProfileViews($Settings=$null) {
    if($Settings){$script:Profiles=$Settings}elseif(-not $Demo){$script:Profiles=Read-ProfileSettings}
    $chosen=$null;if($networkChoice.SelectedItem){$chosen=$networkChoice.SelectedItem.Id}
    $networkChoice.Items.Clear();[void]$networkChoice.Items.Add([pscustomobject]@{Id='Direct';Name='直连 · 不使用代理'})
    foreach($p in $script:Profiles.Profiles){if($script:Profiles.Routing.Adapter -eq 'standalone' -and $p.Id -eq (Get-GatewayKey)){continue};[void]$networkChoice.Items.Add([pscustomobject]@{Id=$p.Id;Name=($p.Name+'  ·  '+$p.Protocol.ToUpperInvariant()+'  '+$p.Host+':'+$p.Port)})}
    $index=0;for($i=0;$i -lt $networkChoice.Items.Count;$i++){if($networkChoice.Items[$i].Id -eq $chosen){$index=$i}}
    $networkChoice.SelectedIndex=$index;Show-ProxyCatalog
}
function Show-ProxyCatalog {
    $selected=$null;if($proxyList.SelectedItems.Count){$selected=$proxyList.SelectedItems[0].Tag.Id}
    $proxyList.BeginUpdate();$proxyList.Items.Clear()
    foreach($p in $script:Profiles.Profiles){
        $item=New-Object Windows.Forms.ListViewItem($p.Name);$item.Tag=$p;$item.ToolTipText=$p.Protocol+'://'+(Get-EndpointAddress $p)
        foreach($value in @($p.Protocol.ToUpperInvariant(),$p.Host,[string]$p.Port,$(if($script:Profiles.Routing.ProfileId -eq $p.Id){'分流引擎'}else{'代理入口'}))){[void]$item.SubItems.Add($value)}
        $state=$script:LastState.Listeners | Where-Object {$_.Key -eq $p.Id} | Select-Object -First 1
        [void]$item.SubItems.Add($(if($state){if($state.Remote){'远程入口 · 可手动检测'}elseif($state.Ready){'本地端口正在监听'}elseif($null -eq $state.Ready){'监听状态未知'}else{'本地端口未监听'}}else{'等待检测'}));[void]$proxyList.Items.Add($item)
        if($selected -eq $p.Id){$item.Selected=$true}
    }
    $proxyList.EndUpdate();$proxyEmpty.Visible=($proxyList.Items.Count -eq 0)
    if($proxyList.Items.Count -eq 0 -and $script:DiscoveryStatus -ne '正在自动识别'){$proxyEmpty.Text='暂未识别到可用 HTTP / SOCKS5 入口。可重新检测，或手动填写地址与端口。'}
    $intro.Text='自动发现 · '+$script:DiscoveryStatus+'。识别代理与观察游戏连接均保留，线路切换由你控制。'
    $engineKey=Get-GatewayKey
    if($script:Profiles.Routing.Adapter -eq 'standalone'){$engineLabel.Text='独立分流入口 · 自动接替 '+$(if($script:Profiles.Routing.Failover.Enabled){'已开启'}else{'已关闭'})+' · '+$(if(Test-Path -LiteralPath (Get-IndependentSessionPath)){'托盘停止服务时恢复网络'}else{'服务未启动；统一切换或代理启动入口会检查并启动'});return}
    $engineLabel.Text=$(if($engineKey){'分流引擎：'+(Get-RouteName $engineKey)+$(if($script:Profiles.Routing.UnifiedMode -eq 'gateway'){' · 固定入口模式：引擎保持运行，出口由你选择。'}else{' · 系统入口模式；可编辑引擎启用固定入口。'})}else{'尚未建立流向固定入口。选择目标并点击「统一切换」会建立入口；普通程序选线也会检查接入。'})
}
function Export-Diagnostics {
    if(-not $script:LastState -or -not $script:LastApps){Write-Activity '请等待读取到状态后再导出。';return}
    $picker=New-Object Windows.Forms.SaveFileDialog;$picker.Filter='JSON 诊断报告 (*.json)|*.json';$picker.FileName='FlowSwitch-diagnostics-'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'.json';$script:DialogOpen=$true
    try{if($picker.ShowDialog($form) -eq 'OK'){
        $report=New-SupportReport $script:LastState $script:LastApps
        $report|Add-Member NoteProperty SnapshotStale ([bool]$script:ObservationStale)
        Write-LocalJson $picker.FileName $report
        Write-Activity '诊断报告已导出：仅含线路、端口和规则数量，不含账号、节点、程序名称和本机路径。'
    }}catch{Write-Activity $_.Exception.Message}finally{$picker.Dispose();$script:DialogOpen=$false}
}
function Mark-ObservationStale {
    $script:ObservationStale=$true
    $statusLabel.Text='状态刷新失败 · 请重试';$checkedLabel.Text='上次记录已过期'
    foreach($row in $liveList.Items){$row.SubItems[2].Text='读取失败 · 上次连接已过期';$row.SubItems[3].Text='请刷新后查看当前状态';$row.ForeColor=$muted}
}
function Show-Applications($Apps) {
    if($script:MenuOpen){$script:DeferredApps=$Apps;return}
    $script:LastApps=$Apps;$selectedPath=$null
    if($liveList.SelectedItems.Count){$selectedPath=Get-ApplicationDisplayKey $liveList.SelectedItems[0].Tag}
    $topPath=$null;if($liveList.TopItem){$topPath=Get-ApplicationDisplayKey $liveList.TopItem.Tag}
    $liveList.BeginUpdate();$liveList.Items.Clear()
    $policies=@{Follow='跟随统一线路';Direct='直连'};foreach($p in $script:Profiles.Profiles){$policies[$p.Id]=$p.Name}
    $rows=@(Select-ApplicationRows $Apps.Rows $searchBox.Text.Trim() $savedOnly.Checked)
    foreach($app in $rows){
        $item=New-Object Windows.Forms.ListViewItem($app.Name);$item.Tag=$app;$item.ToolTipText=$app.Path
        [void]$item.SubItems.Add($(if($app.PolicyName){$app.PolicyName}else{Get-RouteName $app.Policy}));[void]$item.SubItems.Add($app.Actual)
        $note=$app.Status
        if($app.Mode -eq 'engine' -and -not $app.RequiresRepair -and $script:LastState.Key -ne (Get-GatewayKey)){$note+=' · 系统入口未接入引擎'}
        [void]$item.SubItems.Add($note)
        if($app.Policy -ne 'Follow'){$item.ForeColor=$mint;if(-not $app.Loaded -or $note -match '旧连接|失效|切回'){$item.ForeColor=[Drawing.ColorTranslator]::FromHtml('#DEC395')}}
        if($app.NeedsRelaunch -or $app.RequiresRepair){$item.ForeColor=[Drawing.ColorTranslator]::FromHtml('#DEC395')}
        [void]$liveList.Items.Add($item);if($selectedPath -and $selectedPath -ieq (Get-ApplicationDisplayKey $app)){$item.Selected=$true}
        if($topPath -and $topPath -ieq (Get-ApplicationDisplayKey $app)){$liveList.TopItem=$item}
    }
    $liveList.EndUpdate();$emptyLabel.Visible=($rows.Count -eq 0)
    if($script:ObservationStale){Mark-ObservationStale}
    $countLabel.Text='显示 '+$rows.Count+' / '+@($Apps.Rows).Count+' 个程序   ·   Ctrl+F 搜索'
    $ruleValue.Text=[string]$Apps.RuleCount+' 条';$ruleValue.ForeColor=$ink
    $loaded=@($Apps.Rows | Where-Object {$_.Policy -ne 'Follow' -and $_.Loaded}).Count
    $ruleMeta.Text='已加载线路设置 '+$loaded+' 条 · 实际使用见连接列'
    if($Apps.DefaultRoute){$ruleMeta.Text='首选：'+(Get-RouteName $Apps.DefaultRoute)+' · '+$(if($Apps.EffectiveDefaultRoute){'当前：'+(Get-RouteName $Apps.EffectiveDefaultRoute)}elseif($Apps.DefaultLoaded){'已加载'}else{'待重载'})}
    elseif(-not (Get-GatewayKey)){$ruleMeta.Text='程序分流引擎未配置'}
    elseif(-not $Apps.Available){$ruleMeta.Text='引擎状态不可用 · 生效待确认';$ruleValue.ForeColor=$muted}
    if($Apps.LaunchRuleCount){$ruleMeta.Text='启动代理 '+$Apps.LaunchRuleCount+' 条 · 生效状态见程序列表'}
    if($Apps.ManagedRuleCount){$ruleMeta.Text='程序固定入口 '+$Apps.ManagedRuleCount+' 个 · 实际使用见连接列'}
    $programHint.Text='选程序设置线路；网站分流可同时访问直连和代理页面。空闲不代表断网。'
    if($Apps.RepairCount){$ruleMeta.Text+=' · '+$Apps.RepairCount+' 条路径待修复'}
    if(-not (Test-ObservationFlag $Apps 'TcpAvailable')){$countLabel.Text+=' · 连接采集失败'}
    if((Get-GatewayKey) -and -not (Test-ObservationFlag $Apps 'RulesAvailable' ([bool]$Apps.Available))){$ruleMeta.Text+=' · 规则读取未知'}
    if($Apps.DefaultRoute -and $Apps.DefaultLoaded -eq $false){$noticeLabel.Text='统一路由尚未加载，请检查分流引擎的规则模式并重载。'}
    if($script:Profiles.Routing.Adapter -eq 'standalone' -and $Apps.Available){
        $events=@($Apps.Failover.events | Where-Object {$_ -and $_.id})
        if($events.Count){
            $last=$events[-1]
            if($script:LastFailoverEvent -ne $last.id){
                $reason=switch($last.reason){'listener-closed'{'原代理已退出'};'probe-timeout'{'原线路连续检测超时'};'probe-failed'{'原线路连续检测失败'};default{'线路恢复可用'}}
                Write-Activity ('自动接替 '+$last.at+'：'+(Get-RouteName $last.from)+' → '+(Get-RouteName $last.to)+'（'+$reason+'）。新连接生效。')
                $script:LastFailoverEvent=$last.id
            }
        }
        if($Apps.EffectiveDefaultRoute -eq 'Unknown'){$noticeLabel.Text='当前出口读取失败，接替状态未知；请刷新后确认。'}
        elseif($Apps.EffectiveDefaultRoute -eq 'Blocked'){$noticeLabel.Text='默认代理出口已暂停。直连网站例外或其他程序线路可能继续可用，以各自的实际连接为准；请检查默认上游。'}
        elseif($Apps.EffectiveDefaultRoute -in (@('Direct')+(Get-ProfileKeys)) -and $Apps.EffectiveDefaultRoute -ne $Apps.DefaultRoute){$noticeLabel.Text='已自动接替：'+(Get-RouteName $Apps.DefaultRoute)+' → '+(Get-RouteName $Apps.EffectiveDefaultRoute)+'。旧连接如未恢复，可右键该程序预览重连。'}
        if($Apps.EffectiveDefaultRoute -ne 'Unknown' -and $Apps.Failover.updated -and ([DateTimeOffset]::UtcNow-[DateTimeOffset]::Parse($Apps.Failover.updated)).TotalSeconds -gt 30){$noticeLabel.Text='自动检测记录已超过 30 秒未更新，暂不能确认接替状态；当前显示为内核实读出口。'}
        elseif($Apps.EffectiveDefaultRoute -ne 'Unknown' -and $Apps.Failover.details -and @($Apps.Failover.details.PSObject.Properties | Where-Object {$_.Value.healthy -eq $null -or $_.Value.selectionError}).Count){$noticeLabel.Text='自动检测或出口切换未完成；已保留当前线路，请查看诊断。'}
    }

}
function Open-Client([string]$Key) {
    try{$profile=Get-Profile $Key;if(-not $profile.AppPath -or -not (Test-Path -LiteralPath $profile.AppPath)){throw '客户端路径无效，请在「代理管理」编辑并关联已安装的程序。'}
        Start-Process -FilePath $profile.AppPath -WindowStyle Hidden
        Write-Activity ('已请求打开 '+$profile.Name+'。连接完成后再点击「统一切换」。');$script:NextPoll=[DateTime]::MinValue
    }catch{Write-Activity $_.Exception.Message}
}
function Show-State($State) {
    $first=($null -eq $script:LastState);$script:LastState=$State;$headline='入口配置一致';$color=$mint
    if(-not $State.Aligned){$headline='系统入口与代理变量尚未统一';$color=[Drawing.ColorTranslator]::FromHtml('#DEC395')}
    if($State.Drift){$headline='当前入口与上次选择不同 · 保留当前设置';$color=$muted}
    if($State.EndpointReady -eq $false){$headline+=' · 入口未就绪';$color=[Drawing.ColorTranslator]::FromHtml('#E5A6A2')}
    $statusLabel.Text=$headline;$statusLabel.ForeColor=$color;$entryValue.Text=$State.NetworkName;$entryValue.ForeColor=$color
    $systemLabel.Text='系统入口：'+$(if($State.Key -eq 'Direct'){'直连'}else{$State.Server})
    $portsLabel.Text='代理 '+@($State.Listeners).Count+' 个 · 运行中 '+@($State.Listeners | Where-Object Ready).Count+' 个'
    $envLabel.Text='本地监听 '+@($State.Listeners | Where-Object Ready).Count+' 个 · 变量'+$(if($State.EnvConflict){'存在冲突'}elseif($State.Aligned){'已同步'}else{'未完整设置'})
    if(-not (Test-ObservationFlag $State 'TcpAvailable')){$portsLabel.Text='代理 '+@($State.Listeners).Count+' 个 · 监听状态未知';$envLabel.Text='端口采集失败 · 不代表断网'}
    $noticeLabel.Text='自动发现不改变网络选择；切换与程序分流照常使用。已有连接和启动器可能仍保留旧代理。'
    if(-not $State.EnvConflict -and -not $State.Aligned -and $State.EndpointReady -ne $false){$statusLabel.Text='系统入口已读取 · 命令行代理变量未完整设置';$statusLabel.ForeColor=$muted}
    if($script:Profiles.Routing.Adapter -eq 'standalone'){$noticeLabel.Text='独立入口的自动接替'+$(if($script:Profiles.Routing.Failover.Enabled){'已开启'}else{'已关闭'})+'；关闭窗口驻留托盘，托盘菜单可停止服务。已有连接由应用自行重连。'}
    if(@($State.Warnings).Count){$noticeLabel.Text=$State.Warnings -join ' '}
    if($State.EndpointReady -eq $false){$noticeLabel.Text='当前代理入口未就绪。请先启动并等待就绪后重试登录；已有应用可能保留旧代理地址，保存工作后完整重开。'}
    if($script:Profiles.Routing.Adapter -eq 'standalone' -and -not (Test-Path -LiteralPath (Get-IndependentSessionPath))){$statusLabel.Text+=' · 流向服务未启动';$noticeLabel.Text='流向服务未启动，本次打开未更改网络。点击「统一切换」或使用程序代理启动入口会检查并启动服务。'}
    if($script:ChoiceDirty){$noticeLabel.Text='下拉框是待应用目标；当前实际入口以上方卡片为准。'}
    if(-not $script:ChoiceDirty){$networkChoice.SelectedIndex=-1;for($i=0;$i -lt $networkChoice.Items.Count;$i++){if($networkChoice.Items[$i].Id -eq $State.NetworkKey){$networkChoice.SelectedIndex=$i;break}}}
    Show-ProxyCatalog;$checkedLabel.Text='最近读取 '+$State.CheckedAt
}
function Set-DemoCatalog {
    $script:DiscoveryStatus='已识别 2 个入口 · 演示数据'
    $script:Profiles=[pscustomobject]@{Version=3;Routing=[pscustomobject]@{Adapter='clash-verge';ProfileId='office';UnifiedMode='gateway'};Profiles=@(
        [pscustomobject]@{Id='office';Name='办公网络';Protocol='http';Host='127.0.0.1';Port=7890;CorePath='C:\Apps\Engine\mihomo.exe';AppPath='';AutoPort=$false},
        [pscustomobject]@{Id='backup';Name='备用网络';Protocol='socks5';Host='127.0.0.1';Port=1080;CorePath='';AppPath='';AutoPort=$false}
    )}
}
function Get-DemoState {
    [pscustomobject]@{Key='office';Current='办公网络';NetworkKey='office';NetworkName='办公网络';Server='127.0.0.1:7890';Aligned=$true;EnvConflict=$false;EndpointReady=$true;Drift=$false;Environment=@();Listeners=@([pscustomobject]@{Key='office';Ready=$true},[pscustomobject]@{Key='backup';Ready=$true});OldConnections=@();CheckedAt='12:30:00'}
}
function Get-DemoApps {
    [pscustomobject]@{Available=$true;Mode='rule';RuleCount=2;LaunchRuleCount=0;DefaultRoute='office';DefaultLoaded=$true;Rows=@(
        [pscustomobject]@{Name='浏览器';Path='C:\Apps\Browser\browser.exe';Policy='office';Loaded=$true;Actual='办公网络 ×8';Status='已观察到指定线路连接';PIDs='2200,2201';Mode='engine';CanLaunch=$false;ChildNames='network_helper'},
        [pscustomobject]@{Name='开发工具';Path='C:\Apps\Editor\editor.exe';Policy='Follow';PolicyName='未单独指定';Loaded=$false;Actual='运行中 · 未观察到 TCP 连接';Status='未设专用规则 · 以实际连接为准';PIDs='1200'},
        [pscustomobject]@{Name='本地工作台';Path='C:\Apps\Studio\studio.exe';Policy='Direct';Loaded=$true;Actual='直连 ×2';Status='已加载；新连接生效';PIDs='3300'},
        [pscustomobject]@{Name='文件同步';Path='C:\Apps\Sync\sync.exe';Policy='Follow';Loaded=$false;Actual='运行中 · 未观察到 TCP 连接';Status='跟随当前线路';PIDs='4400'}
    )}
}
function Format-Diagnostics($Items) {
    $lines=@()
    foreach($entry in $Items){
        $lines+='【' + $entry.Name + '】'
        if($entry.Error){$lines+=$entry.Error;continue}
        foreach($r in $entry.Results){$lines+=($r.Site + '：' + $r.Note + '  (' + $r.Seconds + ' s)')}
    }
    $lines+='只读探测不携带账户凭据。ChatGPT 403 不等同于断网，也不证明登录后可用。'
    return $lines -join "`r`n"
}
function Start-Work([string]$Kind,[string]$Key) {
    if($script:Worker){
        if($script:Worker.Kind -eq 'Status' -and $Kind -ne 'Status'){
            $script:PendingAction=[pscustomobject]@{Kind=$Kind;Key=$Key}
            $script:Worker.Cancellation.Cancel()
            Write-Activity '正在读取状态，随后执行你的选择…'
        }
        return
    }
    if($Kind -ne 'Status'){
        foreach($b in $script:Controls){$b.Enabled=$false}
        Write-Activity ('正在' + $(if($Kind -eq 'Switch'){'检测并统一设置'}elseif($Kind -eq 'Restore'){'恢复配置'}elseif($Kind -in @('AppRoute','ManagedAppRoute')){'切换程序线路'}elseif($Kind -eq 'WebsiteRules'){'读取网站规则'}elseif($Kind -eq 'WebsiteRulesSave'){'保存并应用网站规则'}elseif($Kind -eq 'Discover'){'查找本机端口'}else{'检测线路'}) + '，请稍候。界面仍可响应。')
    }
    $ps=[PowerShell]::Create();$progress=New-Object 'System.Collections.Concurrent.ConcurrentQueue[string]';$cancellation=New-Object Threading.CancellationTokenSource
    $scan=($Kind -eq 'Discover')
    $automatic=($Kind -eq 'Status' -and $autoDiscovery.Checked -and -not $SmokeTest)
    $code={param($Root,$Kind,$Key,$DataDirectory,$Scan,$Automatic,$Cache,$Progress,$Cancellation)
        $ErrorActionPreference='Stop'
        try{. (Join-Path $Root 'ProxyBackend.ps1') -DataDirectory $DataDirectory}
        catch{return [pscustomobject]@{OK=$false;Kind=$Kind;Stage='initialization';Error='流向无法读取当前配置或运行组件，未执行操作。请检查配置与程序包完整性；原设置未被重置。'}}
        $script:OperationProgress=$Progress
        $result=$null;$discovery=$null;$discoveryError=''
        try {
            if($Scan){try{$discovery=Sync-LocalProxyDiscovery}catch{$discoveryError=$_.Exception.Message}}
            elseif($Automatic){try{$discovery=Sync-AutomaticProxyDiscovery $Cache $Cancellation}catch{$discoveryError=$_.Exception.Message}}
            if($Cancellation.IsCancellationRequested){return [pscustomobject]@{OK=$true;Cancelled=$true}}
            switch($Kind){
                'Switch'{$result=Set-UniversalProxy $Key}
                'Restore'{$result=Restore-ProxyBackup}
                'ConfigureGateway'{$result=Enable-LocalGateway}
                'Independent'{$result=Enable-IndependentGateway $PID}
                'Discover'{$result=$discovery}
                'AppRoute'{$change=$Key | ConvertFrom-Json;$result=Set-ApplicationRoute $change.path $change.route}
                'ManagedAppRoute'{$change=$Key | ConvertFrom-Json;$result=Set-ManagedApplicationRoute $change.path $change.route}
                'WebsiteRules'{$result=Get-WebsiteRules;$result|Add-Member NoteProperty ContextExecutable $Key -Force}
                'WebsiteRulesSave'{$change=$Key|ConvertFrom-Json;$result=Set-WebsiteRules -Entries @($change.Entries) -ExpectedRevision $change.Revision}
                'AppSync'{$result=Sync-ApplicationRoutes}
                'AppRepairPlan'{$result=Get-ProgramRuleRepairPlan -SavedPath $Key}
                'AppRepair'{$result=Repair-ProgramRule -Plan ($Key|ConvertFrom-Json)}
                'AppRemove'{$result=Remove-SavedProgramRule -SavedPath $Key}
                'AppLaunch'{
                    try{$configured=[bool](Get-ManagedProgramIngress $Key) -or @((Get-ProgramLaunchEntries)|Where-Object {$_.path -ieq $Key}).Count -gt 0}
                    catch{throw '程序线路记录无法读取，目标程序尚未启动。请在流向中修复或恢复本机规则后重试。'}
                    if(-not $configured){throw '此程序的代理入口已移除，请重新设置线路后再打开。'}
                    $result=Start-ManagedProgram $Key
                }
                'AppLaunchRoute'{$change=$Key|ConvertFrom-Json;$result=Set-ProgramLaunchRoute $change.path $change.route}
                'AppEntryRepair'{$result=Repair-ProgramProxyEntry $Key}
                'AppReconnectPlan'{$result=Get-ApplicationReconnectPlan $Key}
                'AppReconnect'{$result=Invoke-ApplicationReconnect ($Key | ConvertFrom-Json)}
                'LoginDiagnostic'{$result=Test-LoginChain $Key}
                'Diagnose'{
                    $result=@()
                    foreach($route in @($Key)){
                        try{$result+=Test-ProxyRoute $route}catch{$result+=[pscustomobject]@{Name=$route;Error=$_.Exception.Message}}
                    }
                }
            }
            # Display failure must never erase a successfully applied operation or its backup.
            try{
                $tcpSnapshot=Get-TcpObservationSnapshot;$tcpRows=$tcpSnapshot.Rows
                $apps=Get-ApplicationRoutes -TcpRows $tcpRows -TcpAvailable $tcpSnapshot.Available
                $state=Get-ProxyStatus $apps -TcpRows $tcpRows -TcpAvailable $tcpSnapshot.Available
                [pscustomobject]@{OK=$true;Kind=$Kind;Result=$result;State=$state;Apps=$apps;Settings=$script:Profiles;Discovery=$discovery;DiscoveryError=$discoveryError;Scanned=($Scan -or $Automatic);Automatic=$Automatic;RefreshError=''}
            }catch{
                if($Kind -eq 'Status' -or $null -eq $result){throw}
                [pscustomobject]@{OK=$true;Kind=$Kind;Result=$result;State=$null;Apps=$null;Settings=$script:Profiles;Discovery=$discovery;DiscoveryError=$discoveryError;Scanned=($Scan -or $Automatic);Automatic=$Automatic;RefreshError='状态刷新失败，请重试；操作结果已保留。'}
            }
        } catch { [pscustomobject]@{OK=$false;Kind=$Kind;Error=$_.Exception.Message} }
    }
    [void]$ps.AddScript($code.ToString()).AddArgument($script:UiRoot).AddArgument($Kind).AddArgument($Key).AddArgument($script:DataRoot).AddArgument($scan).AddArgument($automatic).AddArgument(@($script:DiscoveryCache)).AddArgument($progress).AddArgument($cancellation.Token)
    $script:Worker=[pscustomobject]@{PowerShell=$ps;Handle=$ps.BeginInvoke();Kind=$Kind;Progress=$progress;Started=[DateTime]::Now;Cancellation=$cancellation}
}

# Hide only the window; its message loop, status worker, supervisor and watchdog remain alive.
function Read-WindowPreferences {
    $closeToTray=$true
    try{$value=Get-Content -LiteralPath (Join-Path $script:DataRoot 'ui-settings.json') -Raw -Encoding UTF8|ConvertFrom-Json;if($value.CloseToTray -is [bool]){$closeToTray=$value.CloseToTray}}catch{}
    [pscustomobject]@{CloseToTray=$closeToTray}
}
function Show-FlowWindow {
    $form.ShowInTaskbar=$true;$form.Show();$form.WindowState='Normal';$form.Activate()
    Write-LifecycleEvent 'window-shown' 'user-request'
}
function Request-FlowExit {
    $script:ExitRequested=$true;$form.Close()
}
function Initialize-FlowTray {
    $script:ExitRequested=$false;$script:TrayHintShown=$false;$script:LastLifecycleNotice=''
    $script:WindowPreferences=Read-WindowPreferences
    $script:TrayMenu=New-Object Windows.Forms.ContextMenuStrip
    $script:TrayOpen=$script:TrayMenu.Items.Add('打开主界面');$script:TrayOpen.Add_Click({Show-FlowWindow})
    $script:TrayMode=$script:TrayMenu.Items.Add('关闭窗口后驻留托盘');$script:TrayMode.CheckOnClick=$true;$script:TrayMode.Checked=$script:WindowPreferences.CloseToTray
    $script:TrayMode.Add_CheckedChanged({
        try{Write-LocalJson (Join-Path $script:DataRoot 'ui-settings.json') ([pscustomobject]@{CloseToTray=$script:TrayMode.Checked});$script:WindowPreferences.CloseToTray=$script:TrayMode.Checked}
        catch{Write-Activity '托盘设置保存失败，本次使用原设置。'}
    })
    [void]$script:TrayMenu.Items.Add((New-Object Windows.Forms.ToolStripSeparator))
    $script:TrayExit=$script:TrayMenu.Items.Add('停止代理服务并退出');$script:TrayExit.Add_Click({Request-FlowExit})
    $script:Tray=New-Object Windows.Forms.NotifyIcon;$script:Tray.Icon=$form.Icon;$script:Tray.ContextMenuStrip=$script:TrayMenu
    $script:Tray.Text='FlowSwitch '+$script:ProductVersion+' · 正在读取状态';$script:Tray.Visible=$true
    $script:Tray.Add_DoubleClick({Show-FlowWindow});$script:Tray.Add_BalloonTipClicked({Show-FlowWindow})
    Write-LifecycleEvent 'window-start' 'tray-ready'
}
function Update-LifecycleNotice {
    if(-not $script:Tray){return}
    $life=Get-GatewayLifecycle;$recovery=$null
    try{$recovery=Get-Content -LiteralPath (Join-Path $script:DataRoot 'gateway\recovery-status.json') -Raw -Encoding UTF8|ConvertFrom-Json}catch{}
    $description='状态读取中';$notice='';$key=''
    if($script:LastState){$description=$(if($script:ObservationStale -or $null -eq $script:LastState.EndpointReady){'入口状态未知'}elseif($script:LastState.Key -eq 'Direct'){'系统直连'}elseif($script:LastState.EndpointReady){'入口可连接'}else{'入口未就绪'})}
    if($script:Profiles.Routing.Adapter -eq 'standalone'){
        if($life.phase -eq 'restarting'){$description='内核恢复中';$notice='内核意外停止，正在限次重启。入口恢复前请暂停登录。';$key='restarting-'+$life.attempt}
        elseif($life.phase -eq 'failed'){$description='内核恢复失败';$notice='内核恢复失败，正在尝试恢复本会话代理设置。已有应用可能保留旧地址；请打开主界面检查，保存工作后重开应用。';$key='failed-'+$life.startedAt}
        elseif($script:LastApps.EffectiveDefaultRoute -eq 'Blocked'){$description='默认代理已暂停';$notice='默认代理出口已暂停。直连网站例外或其他程序线路可能继续可用；不会把全部请求自动切为直连。';$key='blocked'}
        if($recovery.phase -eq 'restore-failed'){$description='设置恢复失败';$notice='网络设置或内核停止尚未通过校验。请打开主界面处理；会话记录已保留，请勿删除数据目录。';$key='restore-failed-'+$recovery.at}
    }
    if($recovery.phase -eq 'restored' -and $life.phase -eq 'failed'){$description='代理设置已恢复';$notice='内核恢复失败后，本会话代理设置已恢复。已运行应用仍可能缓存旧地址，请保存工作后完整重开应用。';$key='restored-'+$recovery.at}
    if(-not $notice -and $script:LastState.EndpointReady -eq $false -and $script:Profiles.Routing.Adapter -eq 'standalone'){$description='固定入口未就绪';$notice='固定入口不可用。请点击「统一切换」或使用程序代理启动入口检查并启动服务。恢复设置不会刷新已有应用缓存的代理地址。';$key='entry-unavailable'}
    $script:Tray.Text='FlowSwitch '+$script:ProductVersion+' · '+$description
    if($notice -and $key -ne $script:LastLifecycleNotice){
        $script:LastLifecycleNotice=$key;Write-Activity $notice
        $script:Tray.ShowBalloonTip(8000,'FlowSwitch 需要关注',$notice,[Windows.Forms.ToolTipIcon]::Warning)
    }
    if(-not $notice){$script:LastLifecycleNotice=''}
}
function Invoke-FlowWindowClose($Event) {
    if($PreviewPath -or $SmokeTest -or $Demo){return}
    if($Event.CloseReason -eq [Windows.Forms.CloseReason]::UserClosing -and -not $script:ExitRequested -and $script:WindowPreferences.CloseToTray){
        $Event.Cancel=$true;$form.Hide();$form.ShowInTaskbar=$false
        Write-LifecycleEvent 'window-hidden' 'tray-resident'
        if(-not $script:TrayHintShown){$script:TrayHintShown=$true;$script:Tray.ShowBalloonTip(5000,'流向仍在后台运行','已启动的代理入口继续运行；服务未启动时可打开窗口选择线路。双击托盘图标可打开；右键可停止代理服务并退出。',[Windows.Forms.ToolTipIcon]::Info)}
        return
    }
    if($script:Worker -and $script:Worker.Kind -ne 'Status'){$Event.Cancel=$true;$script:ExitRequested=$false;Show-FlowWindow;Write-Activity '正在完成网络操作，完成后再停止服务。';return}
    try{
        if(Test-Path -LiteralPath (Get-IndependentSessionPath)){
            $session=Get-Content -LiteralPath (Get-IndependentSessionPath) -Raw -Encoding UTF8|ConvertFrom-Json
            if($session.OwnerPID -eq $PID){Restore-IndependentSession}
        }
        Write-LifecycleEvent 'window-stop' 'explicit-or-system-close'
    }catch{
        $Event.Cancel=$true;$script:ExitRequested=$false;Show-FlowWindow
        Write-Activity ('停止服务尚未完成，窗口与会话记录保留：'+$_.Exception.Message)
        $script:Tray.ShowBalloonTip(8000,'停止服务未完成','请查看主界面恢复结果。尚未确认停止，不会假报已退出。',[Windows.Forms.ToolTipIcon]::Error)
    }
}

$timer=New-Object Windows.Forms.Timer;$timer.Interval=150
$timer.Add_Tick({
    if($script:WindowLease -and $script:WindowLease.ConsumeWake()){Show-FlowWindow}
    if($script:WindowLease -and $script:WindowLease.ConsumeExpiredLaunchCount()){
        Write-Activity '启动请求等待已超过 30 秒，程序尚未启动。请等待当前操作完成后，再次打开代理启动入口。';$tabs.SelectedTab=$toolsPage
    }
    if($script:WindowLease -and -not $script:Worker -and -not $script:PendingAction -and -not $script:DialogOpen){
        $launchRequest=$script:WindowLease.ConsumeLaunch()
        if($launchRequest){
            try{Assert-ConfiguredLaunchRequest $launchRequest;Start-Work 'AppLaunch' $launchRequest}
            catch{Write-Activity $_.Exception.Message;$tabs.SelectedTab=$toolsPage}
        }
    }
    if(-not $script:NextLifePoll -or [DateTime]::UtcNow -ge $script:NextLifePoll){Update-LifecycleNotice;$script:NextLifePoll=[DateTime]::UtcNow.AddSeconds(2)}
    if($script:Worker -and $script:Worker.Kind -ne 'Status'){
        $message='';while($script:Worker.Progress.TryDequeue([ref]$message)){Write-Activity $message}
        $checkedLabel.Text='操作进行中 · '+[int]([DateTime]::Now-$script:Worker.Started).TotalSeconds+' 秒'
    }
    if($script:Worker -and $script:Worker.Handle.IsCompleted){
        $job=$script:Worker;$script:Worker=$null
        try{
            $messages=@($job.PowerShell.EndInvoke($job.Handle))
            $reply=$messages | Select-Object -Last 1
            if(-not $reply){throw '无法取得状态，请重试。'}
            if($reply.Cancelled){}elseif($reply.OK){
                $beforeSettings=$script:Profiles | ConvertTo-Json -Depth 8 -Compress
                $afterSettings=$reply.Settings | ConvertTo-Json -Depth 8 -Compress
                if($beforeSettings -ne $afterSettings -and -not $script:DialogOpen){Reload-ProfileViews $reply.Settings}
                if($reply.Scanned){
                    if($reply.Automatic -and $reply.Discovery){$script:DiscoveryCache=@($reply.Discovery.Cache)}
                    if($reply.DiscoveryError){$script:DiscoveryStatus='检测未完成，可重试';Write-Activity ('后台代理检测：'+$reply.DiscoveryError)}
                    else{
                        $script:DiscoveryStatus='已识别 '+$reply.Discovery.Detected+' 个入口 · '+$reply.Discovery.CheckedAt
                        if($reply.Discovery.Added -or $reply.Kind -eq 'Discover'){Write-Activity ('检测到 '+$reply.Discovery.Detected+' 个入口，新增 '+$reply.Discovery.Added+' 个代理。网络设置未更改。')}
                    }
                }
                if($reply.Kind -in @('Switch','Restore','AppRoute','ManagedAppRoute')){$script:ChoiceDirty=$false}
                if($reply.State -and $reply.Apps){$script:ObservationStale=$false;Show-State $reply.State;Show-Applications $reply.Apps}
                elseif($reply.RefreshError){Mark-ObservationStale;Write-Activity $reply.RefreshError}
                if($reply.Kind -eq 'WebsiteRules'){Show-WebsiteRulesEditor $reply.Result}
                elseif($reply.Kind -eq 'AppRepairPlan'){
                    $plan=$reply.Result;$script:DialogOpen=$true
                    try{if([Windows.Forms.MessageBox]::Show($form,($plan.Message+"`r`n`r`n旧路径："+$plan.SavedPath+"`r`n新路径："+$plan.CurrentPath+"`r`n`r`n"+$plan.Impact),'修复程序记录','OKCancel','Information') -eq 'OK'){$script:PendingAction=[pscustomobject]@{Kind='AppRepair';Key=($plan|ConvertTo-Json -Depth 12 -Compress)}}}finally{$script:DialogOpen=$false}
                }
                elseif($reply.Kind -eq 'AppReconnectPlan'){
                    $plan=$reply.Result;$number=@($plan.connections).Count
                    if(-not $number){Write-Activity '没有发现此 EXE 经过引擎的旧线路连接。未接管的连接和独立子程序不会被强制处理。'}
                    else{
                        $script:DialogOpen=$true
                        try{if([Windows.Forms.MessageBox]::Show($form,('将关闭「'+[IO.Path]::GetFileName($plan.path)+'」的 '+$number+' 条旧线路连接，让应用有机会重新连接。进行中的对话、下载或登录可能中断；不会退出应用，也不会关闭其他程序的连接。是否继续？'),'确认重连旧连接','OKCancel','Warning') -eq 'OK'){$script:PendingAction=[pscustomobject]@{Kind='AppReconnect';Key=($plan | ConvertTo-Json -Depth 6 -Compress)}}}finally{$script:DialogOpen=$false}
                    }
                }
                elseif($reply.Kind -eq 'LoginDiagnostic'){Write-Activity ('本次检测：当前系统代理入口。'+$reply.Result.Message+' 浏览器回调是否到达 IDE、IDE 账号是否登录成功尚未验证。');$tabs.SelectedTab=$toolsPage}
                elseif($reply.Kind -eq 'Diagnose'){Write-Activity (Format-Diagnostics $reply.Result);$tabs.SelectedTab=$toolsPage}
                elseif($reply.Kind -notin @('Status','Discover')){
                    Write-Activity $reply.Result.Message
                    if($reply.Result.Backup -and $reply.Kind -notin @('AppRepair','AppRemove')){$logBox.AppendText("`r`n切换前配置已保存，可用「撤回上次更改」恢复。")}
                    if($reply.Result.Test){$logBox.AppendText("`r`n" + (Format-Diagnostics @($reply.Result.Test)))}
                    if($reply.State.Warnings.Count){$logBox.AppendText("`r`n" + ($reply.State.Warnings -join "`r`n"))}
                }
            }else{throw $reply.Error}
        }catch{
            Write-Activity $_.Exception.Message
            if($job.Kind -eq 'Status'){Mark-ObservationStale}else{$tabs.SelectedTab=$toolsPage}
        }
        finally{$job.PowerShell.Dispose();$job.Cancellation.Dispose();foreach($b in $script:Controls){$b.Enabled=$true};$script:NextPoll=[DateTime]::Now.AddSeconds(5)}
        if($SmokeTest){
            $brandProperties=@{5='FlowSwitch.Desktop'}
            if($script:TaskbarRelaunchReady){$brandProperties[4]='流向 · FlowSwitch';$brandProperties[3]=$iconPath+',0';$brandProperties[2]=$desktopCommand}
            foreach($propertyId in $brandProperties.Keys){
                if([FlowSwitchDesktop]::ReadWindowProperty($form.Handle,[uint32]$propertyId) -cne $brandProperties[$propertyId]){$script:SmokeFailed=$true}
            }
            if($desktopCommand -notlike ('*'+$script:DataRoot.TrimEnd('\')+'*')){$script:SmokeFailed=$true}
            $searchBox.Text='__no_match_proxy_switch__'
            if($liveList.Items.Count -ne 0){$script:SmokeFailed=$true}
            $searchBox.Clear();$savedOnly.Checked=$true
            if(@($liveList.Items | Where-Object {$_.Tag.Policy -eq 'Follow'}).Count){$script:SmokeFailed=$true}
            $savedOnly.Checked=$false
            $expected=@((Read-ProfileSettings).Profiles).Count
            if(-not $script:LastState -or $networkChoice.Items.Count -ne ($expected+1-$(if($script:Profiles.Routing.Adapter -eq 'standalone'){1}else{0})) -or @($script:LastState.Listeners).Count -ne $expected){$script:SmokeFailed=$true}
            $form.Close();return
        }
        if($script:PendingAction){
            $pending=$script:PendingAction;$script:PendingAction=$null
            Start-Work $pending.Kind $pending.Key
        }
    }
    if(-not $script:Worker -and -not $script:MenuOpen -and -not $script:DialogOpen -and $autoRefresh.Checked -and [DateTime]::Now -ge $script:NextPoll){Start-Work 'Status' ''}
})
$form.Add_FormClosing({Invoke-FlowWindowClose $_})
$form.Add_FormClosed({
    if($script:Tray){$script:Tray.Visible=$false;$script:Tray.Dispose();$script:TrayMenu.Dispose()}
    if($script:WindowLease){$script:WindowLease.Dispose();$script:WindowLease=$null}
    $timer.Stop()
    if($script:Worker){$script:Worker.Cancellation.Cancel();$script:Worker.PowerShell.Stop();$script:Worker.PowerShell.Dispose();$script:Worker.Cancellation.Dispose();$script:Worker=$null}
    $timer.Dispose()
})
$navigation=@()
foreach($nav in @(@('程序分流',0,194),@('代理管理',1,248),@('诊断与工具',2,302))){
    $navButton=New-Button $sidebar $nav[0] 14 $nav[2] 152 44 {$tabs.SelectedIndex=[int]$this.Tag}
    $navButton.Tag=$nav[1];$navButton.Navigation=$true;$navButton.BackColor=$sidebar.BackColor;$navigation+=$navButton
}
function Update-WorkspaceNavigation {
    foreach($n in $navigation){$n.Selected=([int]$n.Tag -eq $tabs.SelectedIndex);$n.Invalidate()}
    $brand.Text=$tabs.SelectedTab.Text
    $tagline.Text=@('为每个程序选择线路，查看连接的实际去向。','整理代理入口，按需发现、检测和修改。','检查线路连接，查看操作记录与诊断结果。')[$tabs.SelectedIndex]
}
$tabs.Add_SelectedIndexChanged({Update-WorkspaceNavigation})
Update-WorkspaceNavigation
$form.Add_Shown({if($tabs.SelectedIndex -lt 0){$tabs.SelectedIndex=0};Update-WorkspaceNavigation;if($PreviewPath){$navigation[$tabs.SelectedIndex].Focus()}})
[FlowSwitch.UI.Palette]::Apply($form)
$shellLayout.RowStyles.Clear();[void]$shellLayout.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Percent,100)))
foreach($grid in @($layout,$programGrid,$proxyGrid,$toolsGrid)){
    $grid.ColumnStyles.Clear();[void]$grid.ColumnStyles.Add((New-Object Windows.Forms.ColumnStyle([Windows.Forms.SizeType]::Percent,100)))
}
$networkChoice.FlatStyle='Flat'
$liveList.SetColumnWeights([double[]]@(0.21,0.19,0.30,0.30))
$proxyList.SetColumnWeights([double[]]@(0.22,0.10,0.23,0.09,0.15,0.21))
if($Demo){Set-DemoCatalog}
Reload-ProfileViews
if($PreviewPath){
    if($PreviewView -in @('Settings','Proxies')){$tabs.SelectedTab=$proxyPage}
    if($Demo){Show-State (Get-DemoState);Show-Applications (Get-DemoApps);$checkedLabel.Text='演示数据 · 展示界面用法'}else{Show-State (Get-ProxyStatus);Show-Applications (Get-ApplicationRoutes)}
    if($PreviewView -eq 'Tools'){$tabs.SelectedTab=$toolsPage;Write-Activity '可检测所选代理、重载程序规则或导出匿名诊断报告。'}
    $form.Opacity=0;$form.ShowInTaskbar=$false;$form.Show()
    [Windows.Forms.Application]::DoEvents();$form.PerformLayout()
    $bitmap=New-Object Drawing.Bitmap($form.Width,$form.Height)
    try{
        $form.DrawToBitmap($bitmap,(New-Object Drawing.Rectangle(0,0,$form.Width,$form.Height)))
        if($PreviewMenu -and $liveList.Items.Count){
            $script:AppTarget=$liveList.Items[0].Tag
            $appMenu.Show($liveList,(New-Object Drawing.Point(260,30)))
            [Windows.Forms.Application]::DoEvents()
            $appMenu.DrawToBitmap($bitmap,(New-Object Drawing.Rectangle(505,470,$appMenu.Width,$appMenu.Height)))
            $appMenu.Close()
        }
        $bitmap.Save($PreviewPath,[Drawing.Imaging.ImageFormat]::Png)
    }
    finally{$bitmap.Dispose();$form.Close();$form.Dispose()}
    return
}
if($SmokeTest){$form.Opacity=0;$form.ShowInTaskbar=$false}
Write-Activity '关闭窗口默认驻留系统托盘；停止服务后，已运行应用可能仍需重开。自动发现代理与程序连接观察已开启；发现结果只补充代理列表，不改系统入口或程序规则。'
# Passive opening never starts or reclaims a gateway. Explicit switching and
# managed launch requests start the service through their guarded worker paths.
if(-not $SmokeTest -and -not $Demo){Initialize-FlowTray}
$timer.Start();[Windows.Forms.Application]::Run($form);$form.Dispose()
if($SmokeTest){if($script:SmokeFailed){throw 'UI worker smoke test failed'};Write-Output 'PASS: UI background status worker completed.'}
