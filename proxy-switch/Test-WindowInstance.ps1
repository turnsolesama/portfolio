param([Parameter(Mandatory=$true)][string]$PackageDirectory)
$ErrorActionPreference='Stop'
$qa=Join-Path $env:TEMP ('FlowSwitch-WindowInstance-'+[Guid]::NewGuid().ToString('N'));[void][IO.Directory]::CreateDirectory($qa)
[IO.File]::WriteAllText((Join-Path $qa 'config.json'),'{"Version":3,"Profiles":[],"Routing":{"Adapter":"none","ProfileId":""}}')
[IO.File]::WriteAllText((Join-Path $qa 'ui-settings.json'),'{"CloseToTray":false}')
$exe=Join-Path ([IO.Path]::GetFullPath($PackageDirectory)) 'FlowSwitch.exe'
$productVersion=[regex]::Match([IO.File]::ReadAllText((Join-Path $PackageDirectory 'app\Preferences.ps1')),"ProductVersion='([0-9.]+)'").Groups[1].Value
Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices;public static class FlowTestWindow{[DllImport("user32.dll")]public static extern bool ShowWindow(IntPtr h,int command);}'
$first=$null;$second=$null;$window=$null;$checks=0
function Check($Value,$Message){if(-not $Value){throw $Message};$script:checks++;Write-Output ('PASS: '+$Message)}
try{
    $first=Start-Process -FilePath $exe -ArgumentList ('--data-directory "'+$qa+'"') -WindowStyle Hidden -PassThru
    $deadline=[DateTime]::UtcNow.AddSeconds(20)
    do {
        $child=Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe'"|Where-Object {$_.ParentProcessId -eq $first.Id -and $_.CommandLine -like ('*'+$qa+'*')}|Select-Object -First 1
        if($child){$window=Get-Process -Id $child.ProcessId;if($window.MainWindowHandle -ne 0){break}}
        Start-Sleep -Milliseconds 200
    }while([DateTime]::UtcNow -lt $deadline)
    Check ($window -and $window.MainWindowHandle -ne 0 -and $window.MainWindowTitle.Contains('FlowSwitch '+$productVersion)) 'complete application opens a real window with current version'
    [void][FlowTestWindow]::ShowWindow($window.MainWindowHandle,0)
    $second=Start-Process -FilePath $exe -ArgumentList ('--data-directory "'+$qa+'"') -WindowStyle Hidden -PassThru
    Check ($second.WaitForExit(15000) -and $second.ExitCode -eq 0) 'duplicate launcher exits successfully after notifying existing window'
    $deadline=[DateTime]::UtcNow.AddSeconds(8)
    do{$window.Refresh();if($window.MainWindowHandle -ne 0){break};Start-Sleep -Milliseconds 200}while([DateTime]::UtcNow -lt $deadline)
    Check (-not $window.HasExited -and $window.MainWindowHandle -ne 0) 'second launch restores the original hidden window'
    $events=Get-Content (Join-Path $qa 'gateway\lifecycle-session.jsonl')|ForEach-Object {$_|ConvertFrom-Json}
    Check (@($events|Where-Object event -eq 'window-start').Count -eq 1 -and @($events|Where-Object event -eq 'window-shown').Count -ge 1) 'one tray owner remains for the shared data directory'
    [void]$window.CloseMainWindow()
    Check ($first.WaitForExit(15000) -and $first.ExitCode -eq 0) 'saved close-to-tray opt-out exits cleanly'
    Write-Output ('PASS: '+$checks+' complete application single-instance checks; isolated settings, no proxy switching.')
}finally{
    if($window){$window.Refresh();if(-not $window.HasExited){[void]$window.CloseMainWindow();if(-not $window.WaitForExit(15000)){$window.Kill()}};$window.Dispose()}
    foreach($p in @($first,$second)){if($p){if(-not $p.HasExited){$p.Kill()};$p.Dispose()}}
}
