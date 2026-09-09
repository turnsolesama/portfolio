$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Windows.Forms
[Windows.Forms.Application]::SetUnhandledExceptionMode([Windows.Forms.UnhandledExceptionMode]::ThrowException)
$source=$PSScriptRoot
$qaRoot=Join-Path $env:TEMP ('ProxySwitch-action-ui-'+[Guid]::NewGuid().ToString('N'));[void][IO.Directory]::CreateDirectory($qaRoot)
foreach($name in @('ProxySwitch.ps1','ProxyWindow.ps1','DesktopBranding.cs','FlowTheme.cs','ProxyBackend.ps1','Preferences.ps1','Storage.ps1','ProxyDiscovery.ps1','ProcessInventory.ps1','ProgramLaunch.ps1','AppRouting.ps1','AppRouter.cjs','config.defaults.json')){Copy-Item -LiteralPath (Join-Path $source $name) -Destination $qaRoot}
[void][IO.Directory]::CreateDirectory((Join-Path $qaRoot 'assets'))
Copy-Item -LiteralPath (Join-Path $source 'assets/FlowSwitch.ico') -Destination (Join-Path $qaRoot 'assets/FlowSwitch.ico')
# Isolated Windows fixtures must not contend with the real manager or other test windows.
$qaBackend=Join-Path $qaRoot 'ProxyBackend.ps1'
$qaBackendText=[IO.File]::ReadAllText($qaBackend).Replace("'Local\UnifiedProxySwitch-'",("'Local\ProxySwitch-QA-"+[IO.Path]::GetFileName($qaRoot)+"-'"))
[IO.File]::WriteAllText($qaBackend,$qaBackendText,(New-Object Text.UTF8Encoding($true)))
$env:PROXY_SWITCH_DATA_DIR=Join-Path $qaRoot 'settings';[void][IO.Directory]::CreateDirectory($env:PROXY_SWITCH_DATA_DIR)
$encoding=New-Object Text.UTF8Encoding($true)
$config=@{Version=3;Routing=@{Adapter='none';ProfileId=''};Profiles=@(@{Id='alpha';Name='QA Alpha';Protocol='http';Host='127.0.0.1';Port=18081;CorePath='';AppPath='';AutoPort=$false},@{Id='beta';Name='QA Beta';Protocol='http';Host='127.0.0.1';Port=18082;CorePath='';AppPath='';AutoPort=$false})}
[IO.File]::WriteAllText((Join-Path $env:PROXY_SWITCH_DATA_DIR 'config.json'),($config|ConvertTo-Json -Depth 5),$encoding)
[IO.File]::WriteAllText((Join-Path $qaRoot 'system.json'),'{"Flags":1,"Server":"","Bypass":""}')
[IO.File]::WriteAllText((Join-Path $qaRoot 'env.json'),'{"HTTP_PROXY":null,"HTTPS_PROXY":null,"ALL_PROXY":null,"NO_PROXY":null}')
[IO.File]::AppendAllText((Join-Path $qaRoot 'ProxyBackend.ps1'),@'

function Get-SystemSnapshot {Get-Content -LiteralPath (Join-Path $PSScriptRoot 'system.json') -Raw|ConvertFrom-Json}
function Get-UserProxyEnv {Get-Content -LiteralPath (Join-Path $PSScriptRoot 'env.json') -Raw|ConvertFrom-Json}
function Set-SystemSnapshot($Value){Write-LocalJson (Join-Path $PSScriptRoot 'system.json') $Value}
function Set-UserProxyEnv($Value){Write-LocalJson (Join-Path $PSScriptRoot 'env.json') $Value}
function Get-Process {param($Name)}
function Get-ClientWarnings {}
function Get-OverrideWarnings {}
function Get-LiveConnections {}
function Get-ApplicationRoutes {[pscustomobject]@{Available=$false;RuleCount=0;Rows=@()}}
function Get-Listener($Profile){[pscustomobject]@{PID=1;Name='fixture'}}
function Test-ProxyRoute($Key,[switch]$Fast){if(-not $Fast){throw 'Switch requested the slow diagnostics path'};[pscustomobject]@{Usable=$true;Results=@()}}
function Sync-AutomaticProxyDiscovery($Cache,$Cancellation){
    [IO.File]::WriteAllText((Join-Path $PSScriptRoot 'inspection-started'),'yes')
    for($i=0;$i -lt 50;$i++){if($Cancellation.IsCancellationRequested){return $null};Start-Sleep -Milliseconds 100}
    [pscustomobject]@{Detected=0;Added=0;Names=@();Cache=@();CheckedAt='12:00:00'}
}
'@,$encoding)
$path=Join-Path $qaRoot 'ProxyWindow.ps1';$text=[IO.File]::ReadAllText($path).Replace('$timer.Start();[void]$form.ShowDialog()','$form.Opacity=0;$form.ShowInTaskbar=$false;$timer.Start();[void]$form.ShowDialog()');[IO.File]::WriteAllText($path,$text,$encoding)
function Find-Control($Parent,[string]$Text){foreach($c in $Parent.Controls){if($c.Text -eq $Text){return $c};$found=Find-Control $c $Text;if($found){return $found}}}
function Find-Type($Parent,[type]$Type){foreach($c in $Parent.Controls){if($c -is $Type){$c};Find-Type $c $Type}}
$global:step=0;$global:failure='';$clock=[Diagnostics.Stopwatch]::StartNew();$global:clickedAt=0.0
$qaTimer=New-Object Windows.Forms.Timer;$qaTimer.Interval=100
$qaTimer.Add_Tick({
    try{
        if($clock.Elapsed.TotalSeconds -gt 20){throw 'Switch UI timed out'}
        $main=[Windows.Forms.Application]::OpenForms|Where-Object Text -like '*FlowSwitch*'|Select-Object -First 1
        if(-not $main){return};$combo=Find-Type $main ([Windows.Forms.ComboBox])|Select-Object -First 1
        if($global:step -eq 0 -and (Test-Path -LiteralPath (Join-Path $qaRoot 'inspection-started'))){
            $combo.SelectedIndex=2
            [void]$combo.GetType().GetMethod('OnSelectionChangeCommitted',[Reflection.BindingFlags]'Instance,NonPublic').Invoke($combo,@([EventArgs]::Empty))
            $global:clickedAt=$clock.Elapsed.TotalSeconds;(Find-Control $main '统一切换').PerformClick();$global:step=1
        }elseif($global:step -eq 1 -and (Find-Control $main 'QA Beta')){
            $system=Get-Content -LiteralPath (Join-Path $qaRoot 'system.json') -Raw|ConvertFrom-Json
            $environment=Get-Content -LiteralPath (Join-Path $qaRoot 'env.json') -Raw|ConvertFrom-Json
            if($system.Server -ne '127.0.0.1:18082' -or $environment.HTTPS_PROXY -ne 'http://127.0.0.1:18082'){throw 'UI changed without applying both settings'}
            if(($clock.Elapsed.TotalSeconds-$global:clickedAt) -ge 5){throw 'Explicit switch waited behind the full background scan'}
            $log=Find-Type $main ([Windows.Forms.TextBox])|Where-Object Multiline|Select-Object -First 1
            if($log.Text -notmatch '正在写入系统入口'){throw 'Switch progress was not displayed'}
            $global:step=2;$qaTimer.Stop();$main.Close()
        }
    }catch{$global:failure=$_.Exception.Message;$qaTimer.Stop();foreach($w in @([Windows.Forms.Application]::OpenForms)){$w.Close()}}
})
$qaTimer.Start();try{& (Join-Path $qaRoot 'ProxySwitch.ps1')}finally{$qaTimer.Stop();$qaTimer.Dispose()}
if($global:failure){throw $global:failure};if($global:step -ne 2){throw 'Switch UI incomplete'}
'PASS: manual switch preempted inspection, used fast checks, applied system and environment snapshots, displayed progress and verified UI state.'
