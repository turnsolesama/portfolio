$ErrorActionPreference='Stop'
$qa=Join-Path $env:TEMP ('ProxySwitch-launch-'+[Guid]::NewGuid().ToString('N'));$env:PROXY_SWITCH_DATA_DIR=Join-Path $qa 'data'
. (Join-Path $PSScriptRoot 'ProxyBackend.ps1')
$script:Pass=0
function Check($Value,$Message){if(-not $Value){throw $Message};$script:Pass++}
function Throws([scriptblock]$Action,$Pattern){$errorText='';try{& $Action|Out-Null}catch{$errorText=$_.Exception.Message};Check ($errorText -match $Pattern) ('Expected '+$Pattern+', got '+$errorText)}
function Use-ChangeLock([scriptblock]$Action){& $Action}
$script:Profiles=ConvertTo-ValidProfileSettings ([pscustomobject]@{Version=3;Profiles=@([pscustomobject]@{Id='upstream';Name='Fixture';Protocol='http';Host='127.0.0.1';Port=18082;CorePath='';AppPath='';AutoPort=$false});Routing=@{Adapter='none';ProfileId=''}})
$script:Sys=[pscustomobject]@{Flags=3;Server='127.0.0.1:18082';Bypass=''}
$script:Env=[pscustomobject]@{HTTP_PROXY=$null;HTTPS_PROXY=$null;ALL_PROXY=$null;NO_PROXY='localhost'}
function Get-SystemSnapshot {$script:Sys}
function Get-UserProxyEnv {$script:Env}
function Set-SystemSnapshot($Value){$script:Sys=$Value}
function Set-UserProxyEnv($Value){$script:Env=$Value}
function Invoke-AppRouter {throw 'Clash must not be used for a native app route'}
function Get-Listener($Profile){[pscustomobject]@{PID=1;Name='Fixture'}}
$directory=Join-Path $qa 'app';$desktop=Join-Path $qa 'desktop';[void][IO.Directory]::CreateDirectory($directory);[void][IO.Directory]::CreateDirectory($desktop)
$exe=Join-Path $directory 'FixtureApp.exe';$child=Join-Path $directory 'worker.exe'
$code=@'
using System;
using System.IO;
using System.Diagnostics;
using System.Threading;
public static class ProxyFixture {
 public static void Main(string[] args) {
  if(args.Length>0 && args[0]=="--child") {
   File.WriteAllLines(Environment.GetEnvironmentVariable("PROXY_SWITCH_FIXTURE_OUTPUT"),new string[]{Environment.GetEnvironmentVariable("HTTP_PROXY")??"",Environment.GetEnvironmentVariable("HTTPS_PROXY")??"",Environment.GetEnvironmentVariable("ALL_PROXY")??"",Environment.GetEnvironmentVariable("NO_PROXY")??"",Environment.GetEnvironmentVariable("PROXY_SWITCH_FIXTURE_FLAGS")??""});
   return;
  }
  Environment.SetEnvironmentVariable("PROXY_SWITCH_FIXTURE_FLAGS",String.Join(" ",args));
  var info=new ProcessStartInfo(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"worker.exe"),"--child");info.UseShellExecute=false;info.CreateNoWindow=true;
  using(var child=Process.Start(info)){child.WaitForExit(5000);}Thread.Sleep(1500);
 }
}
'@
Add-Type -TypeDefinition $code -OutputAssembly $exe -OutputType WindowsApplication
Copy-Item -LiteralPath $exe -Destination $child
foreach($name in @('resources.pak','chrome_100_percent.pak')){[IO.File]::WriteAllText((Join-Path $directory $name),'fixture')}
Check ((Get-ProgramProxyAdapter $exe) -eq 'chromium') 'Chromium adapter discovered from program files'
$plan=Get-ProgramLaunchPlan $exe 'upstream'
Check ($plan.Arguments -contains '--proxy-server=http://127.0.0.1:18082' -and $plan.Environment.HTTPS_PROXY -eq 'http://127.0.0.1:18082') 'UI and child process proxy are both planned'
Check ($plan.Environment.NO_PROXY -eq 'localhost,127.0.0.1,::1') 'Broad inherited bypass cannot silently bypass the selected proxy'
$direct=Get-ProgramLaunchPlan $exe 'Direct'
Check ($direct.Arguments -contains '--no-proxy-server' -and $null -eq $direct.Environment.HTTPS_PROXY -and $direct.Environment.NO_PROXY -eq '*') 'Direct config clears inherited proxy and overrides system proxy for Chromium'
$script:Profiles.Profiles+=@([pscustomobject]@{Id='socks';Name='Socks';Protocol='socks5';Host='127.0.0.1';Port=18083;CorePath='';AppPath='';AutoPort=$false})
Throws {Get-ProgramLaunchPlan $exe 'socks'} 'HTTP'
$script:Profiles.Profiles[0].AppPath=$exe
Throws {Get-ProgramLaunchPlan $exe 'upstream'} '代理程序自身'
$script:Profiles.Profiles[0].AppPath=''
$shell=New-Object -ComObject WScript.Shell;$shortcut=Join-Path $desktop 'FixtureApp.lnk'
try{$link=$shell.CreateShortcut($shortcut);$link.TargetPath=$exe;$link.WorkingDirectory=$directory;$link.IconLocation=$exe+',0';$link.Save();[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($link)}finally{[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell)}
$originalHash=(Get-FileHash -LiteralPath $shortcut).Hash
$realShortcut=${function:Install-ProgramProxyShortcut}
function Install-ProgramProxyShortcut($Executable){& $realShortcut $Executable $desktop}
$result=Set-ProgramLaunchRoute $exe 'upstream'
Check (@(Get-ProgramLaunchEntries).Count -eq 1 -and (Get-ProgramLaunchEntries).route -eq 'upstream') 'Program route saves without any Clash engine or Windows proxy write'
$record=Get-ProgramShortcutRecords|Select-Object -First 1
Check ($result.Message.Contains($shortcut) -and $result.Message -notmatch '原图标|原入口已备份') 'Route result identifies the actual managed entry without promising every original launcher was replaced'
Check (@(Get-VerifiedProgramShortcuts $exe).Count -eq 1) 'Verified entry reads the shortcut target and arguments'
Check ($record.shortcut -eq $shortcut -and (Get-FileHash -LiteralPath $record.originalBackup).Hash -eq $originalHash) 'Original desktop shortcut is backed up byte for byte'
$shell=New-Object -ComObject WScript.Shell
try{$link=$shell.CreateShortcut($shortcut);Check ($link.Arguments -match '-LaunchProgram' -and $link.IconLocation -eq ($exe+',0') -and $link.WorkingDirectory -eq $directory) 'Managed shortcut preserves the program icon and working directory';[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($link)}finally{[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell)}
$recorded=Get-RoutingSnapshot;$unified=Get-UnifiedPlan 'upstream' $recorded
Check ($unified.ClearedRules -eq 1 -and $unified.Routing.launchEntries[0].route -eq 'Follow') 'Unified switch clears native app exceptions and keeps working launchers'
Set-RoutingSnapshot $unified.Routing
Check ((Get-ProgramLaunchEntries).route -eq 'Follow') 'Unified rule write handles native launch routes without a running engine'
Set-RoutingSnapshot $recorded
$beforeSys=$script:Sys;$beforeEnv=$script:Env
$target=[pscustomobject]@{Flags=1;Server='';Bypass=''}
Throws {Invoke-ProxyTransaction $target (New-EnvTarget $beforeEnv 'Direct') $null $beforeSys $beforeEnv $unified.Routing $recorded {throw 'verification failure'}} '已恢复'
Check ((Get-ProgramLaunchEntries).route -eq 'upstream' -and (Test-SameSnapshot $beforeSys $script:Sys)) 'Failed unified operation restores native app routes as well as Windows state'

$env:PROXY_SWITCH_FIXTURE_OUTPUT=Join-Path $qa 'child-environment.txt'
$oldHttp=$env:HTTP_PROXY;$oldHttps=$env:HTTPS_PROXY;$oldBypass=$env:NO_PROXY
try{
    $env:HTTP_PROXY='http://127.0.0.1:7897';$env:HTTPS_PROXY=$env:HTTP_PROXY;$env:NO_PROXY='*'
    $started=Start-ManagedProgram $exe
    $clock=[Diagnostics.Stopwatch]::StartNew();while(-not (Test-Path -LiteralPath $env:PROXY_SWITCH_FIXTURE_OUTPUT) -and $clock.Elapsed.TotalSeconds -lt 8){Start-Sleep -Milliseconds 50}
    $actual=@(Get-Content -LiteralPath $env:PROXY_SWITCH_FIXTURE_OUTPUT)
    Check ($actual[0] -eq 'http://127.0.0.1:18082' -and $actual[1] -eq $actual[0] -and $actual[2] -eq $actual[0]) 'Actual spawned child inherits the selected proxy instead of stale 7897'
    Check ($actual[3] -eq 'localhost,127.0.0.1,::1' -and $actual[4] -match '--proxy-server=http://127.0.0.1:18082') 'Actual main-process flags and child bypass match the route'
    Check ($env:HTTP_PROXY -eq 'http://127.0.0.1:7897' -and $env:NO_PROXY -eq '*') 'Launching one program does not mutate its caller or Windows proxy environment'
    Throws {Start-ManagedProgram $exe} '仍在运行'
    $owned=Get-Process -Id $started.PID -ErrorAction SilentlyContinue;if($owned){[void]$owned.WaitForExit(6000);$owned.Dispose()}
}finally{$env:HTTP_PROXY=$oldHttp;$env:HTTPS_PROXY=$oldHttps;$env:NO_PROXY=$oldBypass}

$birth=[DateTime]::UtcNow
function Get-ProcessInventory {param($Id)
    @([pscustomobject]@{Id=10;ParentId=0;ProcessName='FixtureApp';Path=$exe;MainWindowHandle=[IntPtr]1;StartTime=$birth},[pscustomobject]@{Id=11;ParentId=10;ProcessName='worker';Path=$child;MainWindowHandle=[IntPtr]::Zero;StartTime=$birth})
}
$script:ChildPending=$true
function Get-NetTCPConnection {param($State)
    [pscustomobject]@{LocalPort=50010;RemoteAddress='127.0.0.1';RemotePort=18082;OwningProcess=10;State='Established'}
    if($script:ChildIdle){return}
    [pscustomobject]@{LocalPort=50011;RemoteAddress=$(if($script:ChildPending){'203.0.113.2'}else{'127.0.0.1'});RemotePort=$(if($script:ChildPending){443}else{18082});OwningProcess=11;State=$(if($script:ChildPending){'SynSent'}else{'Established'})}
}
$row=(Get-ApplicationRoutes).Rows|Where-Object Path -eq $exe
Check ($row.PIDs -match '11' -and $row.ChildNames -eq 'worker' -and $row.OutsidePending -eq 1) 'Window row includes a separately named child bypassing the proxy'
Check (-not $row.Loaded -and $row.Status -match '联网子进程') 'A successful UI connection never conceals a failing network child'
Write-LocalJson (Join-Path $script:DataRoot 'program-launches.json') @{version=1;entries=@(@{path=$exe;pid=10;started=$birth.ToUniversalTime().Ticks.ToString();route='upstream';endpoint='http://127.0.0.1:18082'})}
$script:ChildPending=$false
$row=(Get-ApplicationRoutes).Rows|Where-Object Path -eq $exe
Check ($row.Loaded -and $row.Actual -match 'Fixture ×2') 'Main and child connections are observed on the intended route after a matching managed launch'
Check ((Get-ApplicationRoutes).Rows.Count -eq 1) 'Private helper is folded into its app instead of misleadingly shown as unassigned'
$script:ChildIdle=$true
$row=(Get-ApplicationRoutes).Rows|Where-Object Path -eq $exe
Check (-not $row.Loaded -and $row.Status -match '子进程连接待验证') 'Main-process traffic alone does not certify an idle helper'
Set-ProgramLaunchEntries @()
Check ((Get-FileHash -LiteralPath $shortcut).Hash -eq $originalHash) 'Removing a native route restores the original desktop entry byte for byte'
$newExe=Join-Path $directory 'StoreApp.exe';Copy-Item -LiteralPath $exe -Destination $newExe
$newResult=Set-ProgramLaunchRoute $newExe 'upstream'
$newShortcut=Join-Path $desktop 'StoreApp（指定代理）.lnk'
Check ($newResult.Shortcuts -contains $newShortcut -and $newResult.Message.Contains($newShortcut)) 'App without a matching desktop entry explicitly reports the separately created proxy launcher'
Check (@(Get-VerifiedProgramShortcuts $newExe).Count -eq 1) 'New separate launcher is verified'
$shell=New-Object -ComObject WScript.Shell
try{$link=$shell.CreateShortcut($newShortcut);$link.Arguments='-NoProfile';$link.Save();[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($link)}finally{[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell)}
Check (@(Get-VerifiedProgramShortcuts $newExe).Count -eq 0) 'Independently edited entry is not recommended as a working proxy launcher'
Set-ProgramLaunchEntries @()
Check (Test-Path -LiteralPath $newShortcut) 'Removing the rule preserves a user-modified shortcut'
Write-Output ('PASS: '+$script:Pass+' program launch and child-process assertions; isolated shortcuts, files and processes only.')
