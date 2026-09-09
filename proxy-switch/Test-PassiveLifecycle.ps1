$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Windows.Forms
[Windows.Forms.Application]::SetUnhandledExceptionMode([Windows.Forms.UnhandledExceptionMode]::ThrowException)
$qaSource=$PSScriptRoot
$qaRoot=Join-Path $env:TEMP ('passive-ui-'+[Guid]::NewGuid().ToString('N').Substring(0,8))
[void][IO.Directory]::CreateDirectory($qaRoot)
foreach($name in @('ProxySwitch.ps1','ProxyWindow.ps1','DesktopBranding.cs','ProxyBackend.ps1','Preferences.ps1','Storage.ps1','ProxyDiscovery.ps1','ProcessInventory.ps1','ProgramLaunch.ps1','AppRouting.ps1','AppRouter.cjs','config.defaults.json')){Copy-Item -LiteralPath (Join-Path $qaSource $name) -Destination $qaRoot}
[void][IO.Directory]::CreateDirectory((Join-Path $qaRoot 'assets'))
Copy-Item -LiteralPath (Join-Path $qaSource 'assets/FlowSwitch.ico') -Destination (Join-Path $qaRoot 'assets/FlowSwitch.ico')
# Isolated Windows fixtures must not contend with the real manager or other test windows.
$qaBackend=Join-Path $qaRoot 'ProxyBackend.ps1'
$qaBackendText=[IO.File]::ReadAllText($qaBackend).Replace("'Local\UnifiedProxySwitch-'",("'Local\ProxySwitch-QA-"+[IO.Path]::GetFileName($qaRoot)+"-'"))
[IO.File]::WriteAllText($qaBackend,$qaBackendText,(New-Object Text.UTF8Encoding($true)))
$env:PROXY_SWITCH_DATA_DIR=Join-Path $qaRoot 'settings';[void][IO.Directory]::CreateDirectory($env:PROXY_SWITCH_DATA_DIR)
$canary=New-Object Net.Sockets.TcpListener([Net.IPAddress]::Any,0);$canary.Start()
$config=[pscustomobject]@{Version=3;Routing=@{Adapter='none';ProfileId=''};Profiles=@(
    @{Id='alpha';Name='QA Alpha';Protocol='http';Host='127.0.0.1';Port=18081;CorePath='';AppPath='';AutoPort=$false},
    @{Id='beta';Name='QA Beta';Protocol='http';Host='127.0.0.1';Port=18082;CorePath='';AppPath='';AutoPort=$false},
    @{Id='remote';Name='QA Canary';Protocol='http';Host='127.0.0.2';Port=$canary.LocalEndpoint.Port;CorePath='';AppPath='';AutoPort=$false}
)}
$encoding=New-Object Text.UTF8Encoding($true)
[IO.File]::WriteAllText((Join-Path $env:PROXY_SWITCH_DATA_DIR 'config.json'),($config|ConvertTo-Json -Depth 8),$encoding)
$global:qaSystemPath=Join-Path $qaRoot 'system.json'
[IO.File]::WriteAllText($global:qaSystemPath,'{"Flags":3,"Server":"127.0.0.1:18082","Bypass":""}')
$backend=Join-Path $qaRoot 'ProxyBackend.ps1'
[IO.File]::AppendAllText($backend,@'

function Get-SystemSnapshot {[IO.File]::AppendAllText((Join-Path $PSScriptRoot 'reads.log'),"read`n");Get-Content -LiteralPath (Join-Path $PSScriptRoot 'system.json') -Raw | ConvertFrom-Json}
function Get-UserProxyEnv {[pscustomobject]@{HTTP_PROXY=$null;HTTPS_PROXY=$null;ALL_PROXY=$null;NO_PROXY=$null}}
function Get-Selection {[pscustomobject]@{Key='alpha';NetworkKey='alpha'}}
function Get-ClientWarnings {}
function Get-OverrideWarnings {}
function Get-LiveConnections {}
function Get-ApplicationRoutes {[pscustomobject]@{Available=$false;Rows=@();RuleCount=0;DefaultRoute=$null;DefaultLoaded=$false}}
function Deny-QAWrite {[IO.File]::AppendAllText((Join-Path $PSScriptRoot 'writes.log'),"write`n");throw 'Unexpected settings writer'}
function Set-SystemSnapshot {Deny-QAWrite}
function Set-UserProxyEnv {Deny-QAWrite}
function Save-Selection {Deny-QAWrite}
function Set-RoutingSnapshot {Deny-QAWrite}
function Test-LocalProxyProtocol {[IO.File]::AppendAllText((Join-Path $PSScriptRoot 'probes.log'),"probe`n");throw 'Unexpected protocol probe'}
'@,$encoding)
$windowPath=Join-Path $qaRoot 'ProxyWindow.ps1';$window=[IO.File]::ReadAllText($windowPath)
$window=$window.Replace('$timer.Start();[void]$form.ShowDialog()','$autoDiscovery.Checked=$false;$form.Opacity=0;$form.ShowInTaskbar=$false;$timer.Start();[void]$form.ShowDialog()')
[IO.File]::WriteAllText($windowPath,$window,$encoding)
$configHash=(Get-FileHash -LiteralPath (Join-Path $env:PROXY_SWITCH_DATA_DIR 'config.json')).Hash
function Find-Control($Parent,[string]$Text){foreach($c in $Parent.Controls){if($c.Text -eq $Text){return $c};$found=Find-Control $c $Text;if($found){return $found}}}
function Find-Type($Parent,[type]$Type){foreach($c in $Parent.Controls){if($c -is $Type){$c};Find-Type $c $Type}}
$global:qaStep=0;$global:qaFailure=$null;$clock=[Diagnostics.Stopwatch]::StartNew()
$qaTimer=New-Object Windows.Forms.Timer;$qaTimer.Interval=300
$qaTimer.Add_Tick({
    try{
        if($clock.Elapsed.TotalSeconds -gt 95){throw 'Lifecycle test timed out'}
        $main=[Windows.Forms.Application]::OpenForms | Where-Object {$_.Text -like '*FlowSwitch*'} | Select-Object -First 1
        if(-not $main){return}
        if($canary.Pending()){throw 'Passive status opened a socket'}
        if(Test-Path -LiteralPath (Join-Path $qaRoot 'writes.log')){throw 'Lifecycle wrote network settings'}
        if(Test-Path -LiteralPath (Join-Path $qaRoot 'probes.log')){throw 'Lifecycle ran protocol discovery'}
        $combo=Find-Type $main ([Windows.Forms.ComboBox]) | Select-Object -First 1
        if($global:qaStep -eq 0 -and $combo.SelectedItem.Id -eq 'beta'){
            if(-not (Find-Control $main 'QA Beta')){throw 'Card does not reflect actual entry'}
            [IO.File]::WriteAllText($global:qaSystemPath,'{"Flags":1,"Server":"127.0.0.1:7897","Bypass":""}')
            (Find-Control $main '刷新').PerformClick();$global:qaStep=1
        }elseif($global:qaStep -eq 1 -and $combo.SelectedItem.Id -eq 'Direct'){
            if(-not (Find-Control $main '直连')){throw 'Disabled stale server misreported as active proxy'}
            $combo.SelectedIndex=1
            $method=$combo.GetType().GetMethod('OnSelectionChangeCommitted',[Reflection.BindingFlags]'Instance,NonPublic')
            [void]$method.Invoke($combo,@([EventArgs]::Empty))
            [IO.File]::WriteAllText($global:qaSystemPath,'{"Flags":3,"Server":"127.0.0.1:18082","Bypass":""}')
            (Find-Control $main '刷新').PerformClick();$global:qaStep=2
        }elseif($global:qaStep -eq 2 -and (Find-Control $main 'QA Beta')){
            if($combo.SelectedItem.Id -ne 'alpha'){throw 'Refresh overwrote unsubmitted user choice'}
            $global:qaStep=3
        }elseif($global:qaStep -eq 3 -and $clock.Elapsed.TotalSeconds -ge 72){
            if($combo.SelectedItem.Id -ne 'alpha'){throw 'Timer overwrote unsubmitted user choice'}
            $global:qaStep=4;$qaTimer.Stop();$main.Close()
        }
    }catch{$global:qaFailure=$_.Exception.Message;$qaTimer.Stop();foreach($form in @([Windows.Forms.Application]::OpenForms)){$form.Close()}}
})
$qaTimer.Start()
try{& (Join-Path $qaRoot 'ProxySwitch.ps1')}finally{$qaTimer.Stop();$qaTimer.Dispose();$canary.Stop()}
if($global:qaFailure){throw $global:qaFailure}
if($global:qaStep -ne 4){throw 'Lifecycle test incomplete'}
if((Test-Path -LiteralPath (Join-Path $qaRoot 'writes.log')) -or (Test-Path -LiteralPath (Join-Path $qaRoot 'probes.log'))){throw 'Exit attempted a write or probe'}
if((Get-FileHash -LiteralPath (Join-Path $env:PROXY_SWITCH_DATA_DIR 'config.json')).Hash -ne $configHash){throw 'Passive lifecycle modified profiles'}
$reads=@(Get-Content -LiteralPath (Join-Path $qaRoot 'reads.log')).Count
if($reads -lt 8){throw 'Insufficient automatic refresh cycles'}
'PASS: startup, manual refresh, '+$reads+' passive reads over 72 seconds, external choices, unsaved dropdown choice, exit; no socket probes or network/config writes.'
