$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Windows.Forms
$qaSource=$PSScriptRoot
$qaRoot=Join-Path $env:TEMP ('discovery-ui-'+[Guid]::NewGuid().ToString('N').Substring(0,8))
[void][IO.Directory]::CreateDirectory($qaRoot)
foreach($name in @('ProxySwitch.ps1','ProxyWindow.ps1','ProxyBackend.ps1','Preferences.ps1','Storage.ps1','ProxyDiscovery.ps1','ProcessInventory.ps1','ProgramLaunch.ps1','AppRouting.ps1','AppRouter.cjs','config.defaults.json')){Copy-Item -LiteralPath (Join-Path $qaSource $name) -Destination $qaRoot}
# Isolated Windows fixtures must not contend with the real manager or other test windows.
$qaBackend=Join-Path $qaRoot 'ProxyBackend.ps1'
$qaBackendText=[IO.File]::ReadAllText($qaBackend).Replace("'Local\UnifiedProxySwitch-'",("'Local\ProxySwitch-QA-"+[IO.Path]::GetFileName($qaRoot)+"-'"))
[IO.File]::WriteAllText($qaBackend,$qaBackendText,(New-Object Text.UTF8Encoding($true)))
$qaData=Join-Path $qaRoot 'settings'
$env:PROXY_SWITCH_DATA_DIR=Join-Path $qaRoot 'other-environment'
[void][IO.Directory]::CreateDirectory($env:PROXY_SWITCH_DATA_DIR)
$discoveryPath=Join-Path $qaRoot 'ProxyBackend.ps1'
[IO.File]::AppendAllText($discoveryPath,@'

function Get-ProxyDiscoveryListeners {@([pscustomobject]@{Host='127.0.0.1';Port=18081;Name='QA background proxy';Path=''})}
function Test-LocalProxyProtocol($Address,$Port,$Protocol){$Protocol -eq 'http'}
function Sync-AutomaticProxyDiscovery($Cache){[pscustomobject]@{Detected=0;Added=0;Names=@();Cache=@();CheckedAt='12:00:00'}}
function Set-SystemSnapshot {throw 'UI test attempted to change system network'}
function Set-UserProxyEnv {throw 'UI test attempted to change proxy variables'}
function Get-SystemSnapshot {[pscustomobject]@{Flags=1;Server='';Bypass=''}}
function Get-Selection {$null}
'@,(New-Object Text.UTF8Encoding($true)))
$windowPath=Join-Path $qaRoot 'ProxyWindow.ps1';$window=[IO.File]::ReadAllText($windowPath)
$window=$window.Replace('$timer.Start();[void]$form.ShowDialog()','$form.Opacity=0;$form.ShowInTaskbar=$false;$timer.Start();[void]$form.ShowDialog()')
[IO.File]::WriteAllText($windowPath,$window,(New-Object Text.UTF8Encoding($true)))
function Find-QAControl($Parent,[string]$Text){foreach($c in $Parent.Controls){if($c.Text -eq $Text){return $c};$found=Find-QAControl $c $Text;if($found){return $found}}}
function Find-QAType($Parent,[type]$Type){foreach($c in $Parent.Controls){if($c -is $Type){$c};Find-QAType $c $Type}}
$global:discoveryStep=-1;$global:discoveryTicks=0;$global:discoveryFailure=$null
$qaTimer=New-Object Windows.Forms.Timer;$qaTimer.Interval=300
$qaTimer.Add_Tick({
    $global:discoveryTicks++
    try{
        if($global:discoveryTicks -gt 120){throw 'Discovery UI timed out'}
        $main=[Windows.Forms.Application]::OpenForms | Where-Object {$_.Text -like 'ProxySwitch 3.1.1*'} | Select-Object -First 1
        if(-not $main){return}
        $combo=Find-QAType $main ([Windows.Forms.ComboBox]) | Select-Object -First 1
        $list=Find-QAType $main ([Windows.Forms.ListView]) | Where-Object {$_.Columns.Count -eq 6} | Select-Object -First 1
        $file=Join-Path $qaData 'config.json'
        if($global:discoveryStep -eq -1 -and $combo.Items.Count -eq 1 -and (Find-QAControl $main '检测并添加后台代理').Enabled){
            (Find-QAControl $main '代理管理').PerformClick()
            (Find-QAControl $main '检测并添加后台代理').PerformClick();$global:discoveryStep=0
        }elseif($global:discoveryStep -eq 0 -and $combo.Items.Count -eq 2 -and $list.Items.Count -eq 1){
            $value=Get-Content -LiteralPath $file -Raw -Encoding UTF8|ConvertFrom-Json
            if($value.Profiles.Count -ne 1 -or $combo.Items[1].Id -ne $value.Profiles[0].Id){throw 'Manual discovery did not populate settings and dropdown'}
            $value.Profiles[0].Name='QA externally renamed'
            [IO.File]::WriteAllText($file,($value|ConvertTo-Json -Depth 8),(New-Object Text.UTF8Encoding($false)))
            (Find-QAControl $main '刷新').PerformClick();$global:discoveryStep=1
        }elseif($global:discoveryStep -eq 1 -and $list.Items.Count -eq 1 -and $list.Items[0].Text -eq 'QA externally renamed'){
            if($combo.Items[1].Name -notlike 'QA externally renamed*'){throw 'Dropdown failed to refresh external settings'}
            (Find-QAControl $main '代理管理').PerformClick();$list.Items[0].Selected=$true
            (Find-QAControl $main '删除').PerformClick();$global:discoveryStep=2
        }elseif($global:discoveryStep -eq 2 -and $list.Items.Count -eq 0 -and $combo.Items.Count -eq 1){
            $value=Get-Content -LiteralPath $file -Raw -Encoding UTF8|ConvertFrom-Json
            if('loopback:18081' -notin $value.DiscoveryIgnored){throw 'Delete failed to suppress rediscovery'}
            (Find-QAControl $main '检测并添加后台代理').PerformClick();$global:discoveryStep=3
        }elseif($global:discoveryStep -eq 3){
            $log=Find-QAType $main ([Windows.Forms.TextBox]) | Where-Object {$_.Multiline} | Select-Object -First 1
            if($log.Text -match '新增 0 个代理'){
                if($list.Items.Count -ne 0 -or $combo.Items.Count -ne 1){throw 'Deleted endpoint returned after scan'}
                $global:discoveryStep=4;$qaTimer.Stop();$main.Close()
            }
        }
    }catch{$global:discoveryFailure=$_.Exception.Message;$qaTimer.Stop();foreach($w in @([Windows.Forms.Application]::OpenForms)){$w.Close()}}
})
$qaTimer.Start()
try{& (Join-Path $qaRoot 'ProxySwitch.ps1') -DataDirectory $qaData}finally{$qaTimer.Stop();$qaTimer.Dispose()}
if($global:discoveryFailure){throw $global:discoveryFailure}
if($global:discoveryStep -ne 4){throw 'Discovery UI incomplete'}
if(Test-Path -LiteralPath (Join-Path $env:PROXY_SWITCH_DATA_DIR 'config.json')){throw 'UI or worker ignored the explicit data directory'}
'PASS: manual discovery, dropdown, external config refresh, delete and re-scan; explicit data directory preserved by UI and workers. Settings isolated; network writers prohibited.'
