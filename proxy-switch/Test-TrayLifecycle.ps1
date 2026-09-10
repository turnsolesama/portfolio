[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$CorePath)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[Windows.Forms.Application]::SetUnhandledExceptionMode([Windows.Forms.UnhandledExceptionMode]::ThrowException)
$env:PROXY_SWITCH_DATA_DIR=Join-Path $env:TEMP ('FlowSwitch-Tray-'+[Guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($env:PROXY_SWITCH_DATA_DIR)
$ownedCore=Join-Path $env:PROXY_SWITCH_DATA_DIR 'FlowSwitch-TestEngine.exe';Copy-Item -LiteralPath $CorePath -Destination $ownedCore
. (Join-Path $PSScriptRoot 'ProxyBackend.ps1')
$reserve=New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback,0);$reserve.Start();$port=$reserve.LocalEndpoint.Port;$reserve.Stop()
$script:Profiles=ConvertTo-ValidProfileSettings ([pscustomobject]@{Version=3;Profiles=@([pscustomobject]@{Id='gateway';Name='Fixture gateway';Protocol='http';Host='127.0.0.1';Port=$port;CorePath=$ownedCore;AppPath='';AutoPort=$false});Routing=[pscustomobject]@{Adapter='standalone';ProfileId='gateway';UnifiedMode='gateway';Failover=[pscustomobject]@{Enabled=$true;Order=@();AllowDirect=$false}}})
Write-LocalJson $script:ConfigPath $script:Profiles
Write-LocalJson (Join-Path $script:DataRoot 'app-rules.json') ([pscustomobject]@{version=2;installed=$true;entries=@();defaultRoute='Direct'})
$script:FakeSystem=[pscustomobject]@{Flags=1;Server='';Bypass='localhost'}
$script:FakeEnv=[pscustomobject]@{HTTP_PROXY=$null;HTTPS_PROXY=$null;ALL_PROXY=$null;NO_PROXY='localhost'}
$originalSystem=$script:FakeSystem;$originalEnv=$script:FakeEnv;$script:FailRecovery=$false
function Get-SystemSnapshot {$script:FakeSystem}
function Get-UserProxyEnv {$script:FakeEnv}
function Set-SystemSnapshot($Value){if($script:FailRecovery){throw 'isolated simulated restore failure'};$script:FakeSystem=$Value}
function Set-UserProxyEnv($Value){$script:FakeEnv=$Value}
function Get-ItemPropertyValue {param($LiteralPath,$Name,$ErrorAction);throw 'No actual registry registration'}
function Remove-ItemProperty {throw 'Real registry mutation is forbidden'}
$checks=0
function Check($Value,$Message){if(-not $Value){throw $Message};$script:checks++;Write-Output ('PASS: '+$Message)}
$form=$null;$timer=$null;$failure='';$ticks=0
try{
    Invoke-AppRouter @{action='start'}|Out-Null
    $owned=Get-Content (Join-Path $script:DataRoot 'gateway\process.json') -Raw|ConvertFrom-Json
    $target=[pscustomobject]@{Flags=3;Server=('127.0.0.1:'+$port);Bypass='localhost'}
    $targetEnv=[pscustomobject]@{HTTP_PROXY=('http://127.0.0.1:'+$port);HTTPS_PROXY=('http://127.0.0.1:'+$port);ALL_PROXY=('http://127.0.0.1:'+$port);NO_PROXY='localhost'}
    Write-LocalJson (Get-IndependentSessionPath) ([pscustomobject]@{OwnerPID=$PID;OwnerStart=(Get-ProcessStartTicks $PID);SupervisorPID=$owned.supervisor;SupervisorStart=(Get-ProcessStartTicks $owned.supervisor);CorePID=$owned.core;CoreStart=(Get-ProcessStartTicks $owned.core);BeforeSystem=$originalSystem;BeforeEnv=$originalEnv;TargetSystem=$target;TargetEnv=$targetEnv;Started=[DateTimeOffset]::UtcNow.ToString('o')})
    $script:FakeSystem=$target;$script:FakeEnv=$targetEnv
    $tokens=$null;$errors=$null;$ast=[Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot 'ProxyWindow.ps1'),[ref]$tokens,[ref]$errors)
    foreach($name in @('Read-WindowPreferences','Show-FlowWindow','Request-FlowExit','Initialize-FlowTray','Invoke-FlowWindowClose')){
        $fn=$ast.Find({param($a)$a -is [Management.Automation.Language.FunctionDefinitionAst] -and $a.Name -eq $name},$true);Invoke-Expression $fn.Extent.Text
    }
    function Write-Activity($Message){$script:LastActivity=$Message}
    $form=New-Object Windows.Forms.Form;$form.Text='FlowSwitch isolated tray test';$form.Icon=New-Object Drawing.Icon((Join-Path $PSScriptRoot 'assets\FlowSwitch.ico'));$form.Opacity=0
    Initialize-FlowTray
    $form.Add_FormClosing({Invoke-FlowWindowClose $_})
    $timer=New-Object Windows.Forms.Timer;$timer.Interval=200
    $timer.Add_Tick({
        try{
            $script:ticks++
            switch($script:ticks){
                1 {$form.Close()}
                2 {
                    Check (-not $form.Visible -and $script:Tray.Visible -and -not $form.IsDisposed) 'close button hides to real NotifyIcon without terminating message loop'
                    Check ((Invoke-AppRouter @{action='status'}).available) 'fixed entry and controller survive close to tray'
                    Check (Test-SameSnapshot $script:FakeSystem $target) 'close to tray does not restore or change proxy settings'
                    $script:TrayOpen.PerformClick()
                }
                3 {
                    Check $form.Visible 'tray open menu restores main window'
                    $script:FailRecovery=$true;$script:TrayExit.PerformClick()
                }
                4 {
                    Check ($form.Visible -and -not $form.IsDisposed -and (Test-Path (Get-IndependentSessionPath))) 'failed restoration keeps visible UI and session journal'
                    Check ((Invoke-AppRouter @{action='status'}).available) 'failed restoration keeps core running'
                    Check ($script:LastActivity -match '尚未完成') 'failed stop is explained to user'
                    $script:FailRecovery=$false
                    # A replacement core must still be stopped through its owning supervisor.
                    Stop-Process -Id $owned.core
                }
                {$_ -ge 5} {
                    $life=Get-GatewayLifecycle
                    if($life.phase -ne 'ready' -or $life.core -eq $owned.core){if($script:ticks -gt 90){throw 'Restart timed out'};break}
                    Check ($life.core -ne $owned.core) 'new core PID is live before explicit tray exit'
                    $script:ReplacedCore=$life.core
                    # Preserve a later external system choice while restoring owned variables.
                    $script:FakeSystem=[pscustomobject]@{Flags=3;Server='127.0.0.1:29999';Bypass='external'}
                    $script:TrayExit.PerformClick()
                }
            }
        }catch{$script:failure=$_.Exception.ToString();$script:FailRecovery=$false;$script:ExitRequested=$true;$form.Close()}
    })
    $timer.Start();[Windows.Forms.Application]::Run($form)
    if($failure){throw $failure}
    Check (-not (Test-Path (Get-IndependentSessionPath))) 'explicit tray exit completes and archives session'
    Check ($script:FakeSystem.Server -eq '127.0.0.1:29999') 'exit preserves other software later proxy settings'
    Check (-not (Get-Process -Id $script:ReplacedCore -ErrorAction SilentlyContinue)) 'explicit exit stops the restarted core, not only original PID'
    Check (-not (Test-RecoveryEndpoint ('127.0.0.1:'+$port))) 'fixed listener is closed after verified restoration'
    Write-Output ('PASS: '+$checks+' tray lifecycle checks with real NotifyIcon and real isolated core; no Windows proxy writes.')
}finally{
    if($timer){$timer.Stop();$timer.Dispose()};if($script:Tray){$script:Tray.Visible=$false;$script:Tray.Dispose();$script:TrayMenu.Dispose()}
    $script:FailRecovery=$false;try{Restore-IndependentSession}catch{}
    try{Invoke-AppRouter @{action='stop'}|Out-Null}catch{}
    if($form){$form.Dispose()}
}
