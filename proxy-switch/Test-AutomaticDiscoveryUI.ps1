$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Windows.Forms
$source=$PSScriptRoot
$qaRoot=Join-Path $env:TEMP ('ProxySwitch-auto-ui-'+[Guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($qaRoot)
foreach($name in @('ProxySwitch.ps1','ProxyWindow.ps1','ProxyBackend.ps1','Preferences.ps1','ProxyDiscovery.ps1','ProcessInventory.ps1','ProgramLaunch.ps1','AppRouting.ps1','AppRouter.cjs','config.defaults.json')){Copy-Item -LiteralPath (Join-Path $source $name) -Destination $qaRoot}
# Isolated Windows fixtures must not contend with the real manager or other test windows.
$qaBackend=Join-Path $qaRoot 'ProxyBackend.ps1'
$qaBackendText=[IO.File]::ReadAllText($qaBackend).Replace("'Local\UnifiedProxySwitch-'",("'Local\ProxySwitch-QA-"+[IO.Path]::GetFileName($qaRoot)+"-'"))
[IO.File]::WriteAllText($qaBackend,$qaBackendText,(New-Object Text.UTF8Encoding($true)))
$env:PROXY_SWITCH_DATA_DIR=Join-Path $qaRoot 'settings'
$encoding=New-Object Text.UTF8Encoding($true)
[IO.File]::WriteAllText((Join-Path $qaRoot 'port.txt'),'19081')
[IO.File]::AppendAllText((Join-Path $qaRoot 'ProxyBackend.ps1'),@'

function Get-SystemSnapshot {[pscustomobject]@{Flags=1;Server='';Bypass=''}}
function Get-UserProxyEnv {[pscustomobject]@{HTTP_PROXY=$null;HTTPS_PROXY=$null;ALL_PROXY=$null}}
function Get-Selection {$null}
function Set-SystemSnapshot {throw 'Unexpected network writer'}
function Set-UserProxyEnv {throw 'Unexpected variable writer'}
function Set-RoutingSnapshot {throw 'Unexpected rule writer'}
function Get-LiveConnections {}
function Get-LocalListenerInventory {@(
    [pscustomobject]@{Host='127.0.0.1';Port=[int][IO.File]::ReadAllText((Join-Path $PSScriptRoot 'port.txt'));Name='mihomo';Path='C:\Apps\mihomo.exe';PID=20;Started='1000'},
    [pscustomobject]@{Host='127.0.0.1';Port=44531;Name='CalabiYau';Path='C:\Games\CalabiYau.exe';PID=30;Started='1001'}
)}
function Test-DiscoveryOwnerStillListening($Endpoint){$Endpoint.PID -eq 20}
function Test-LocalProxyProtocol($Address,$Port,$Protocol){
    if($Port -eq 44531){throw 'Game port probed'}
    [IO.File]::AppendAllText((Join-Path $PSScriptRoot 'probes.log'),([string]$Port+"`n"));return $Protocol -eq 'http'
}
function Get-ApplicationRoutes {[pscustomobject]@{Available=$false;RuleCount=0;Rows=@([pscustomobject]@{Name='CalabiYau';Path='';PIDs='30';Policy='Follow';Loaded=$false;Actual='入口外连接 ×3';Status='路径不可读，仅观察'})}}
'@,$encoding)
$path=Join-Path $qaRoot 'ProxyWindow.ps1';$text=[IO.File]::ReadAllText($path).Replace('$timer.Start();[void]$form.ShowDialog()','$form.Opacity=0;$form.ShowInTaskbar=$false;$timer.Start();[void]$form.ShowDialog()');[IO.File]::WriteAllText($path,$text,$encoding)
function Find-Type($Parent,[type]$Type){foreach($c in $Parent.Controls){if($c -is $Type){$c};Find-Type $c $Type}}
$global:step=0;$global:failure='';$clock=[Diagnostics.Stopwatch]::StartNew()
$qaTimer=New-Object Windows.Forms.Timer;$qaTimer.Interval=250
$qaTimer.Add_Tick({
    try{
        if($clock.Elapsed.TotalSeconds -gt 40){throw 'Automatic UI timed out'}
        $main=[Windows.Forms.Application]::OpenForms|Where-Object Text -like 'ProxySwitch 3.1.0*'|Select-Object -First 1
        if(-not $main){return}
        $combo=Find-Type $main ([Windows.Forms.ComboBox])|Select-Object -First 1
        $lists=@(Find-Type $main ([Windows.Forms.ListView]));$program=$lists|Where-Object {$_.Columns.Count -eq 4}|Select-Object -First 1
        if($global:step -eq 0 -and $combo.Items.Count -eq 2){
            if($program.Items.Count -ne 1 -or $program.Items[0].Text -ne 'CalabiYau'){throw 'Game monitoring disappeared'}
            $global:step=1
        }elseif($global:step -eq 1 -and $clock.Elapsed.TotalSeconds -gt 12){
            if(@(Get-Content -LiteralPath (Join-Path $qaRoot 'probes.log')).Count -ne 1){throw 'Cached proxy was repeatedly probed'}
            [IO.File]::WriteAllText((Join-Path $qaRoot 'port.txt'),'19082');$global:step=2
        }elseif($global:step -eq 2 -and $combo.Items.Count -eq 3){
            if(@(Get-Content -LiteralPath (Join-Path $qaRoot 'probes.log')).Count -ne 2){throw 'New port detection did not run once'}
            if($program.Items.Count -ne 1){throw 'Program monitoring lost after discovery'}
            $global:step=3;$qaTimer.Stop();$main.Close()
        }
    }catch{$global:failure=$_.Exception.Message;$qaTimer.Stop();foreach($w in @([Windows.Forms.Application]::OpenForms)){$w.Close()}}
})
$qaTimer.Start();try{& (Join-Path $qaRoot 'ProxySwitch.ps1')}finally{$qaTimer.Stop();$qaTimer.Dispose()}
if($global:failure){throw $global:failure};if($global:step -ne 3){throw 'Automatic UI incomplete'}
'PASS: proxy autodiscovery on startup, cached refresh, new port detection, game monitoring retained, no network setting writes.'
