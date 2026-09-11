[CmdletBinding()]
param([string]$Name='流向 FlowSwitch',[string]$LauncherPath='')
$ErrorActionPreference='Stop'
if($Name -match '[<>:"/\\|?*\x00-\x1f]' -or -not $Name.Trim()){throw '快捷方式名称无效。'}
$entry=Join-Path $PSScriptRoot 'ProxySwitch.ps1'
if(-not (Test-Path -LiteralPath $entry)){throw '请先解压完整程序包。'}
if($LauncherPath){
    $LauncherPath=[IO.Path]::GetFullPath($LauncherPath)
    $expected=Join-Path ([IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))) 'FlowSwitch.exe'
    if($LauncherPath -ine $expected -or -not (Test-Path -LiteralPath $LauncherPath -PathType Leaf)){throw '桌面入口必须指向完整程序包中的 FlowSwitch.exe。'}
}
. (Join-Path $PSScriptRoot 'Storage.ps1')
$dataRoot=Resolve-ProxyDataDirectory '' $env:PROXY_SWITCH_DATA_DIR ([Environment]::GetFolderPath('UserProfile')) $env:LOCALAPPDATA
if(-not $env:PROXY_SWITCH_DATA_DIR){Initialize-ProxyDataDirectory $dataRoot (Join-Path $env:LOCALAPPDATA 'ProxySwitch')}
$quotedDataDirectory='"'+[regex]::Replace($dataRoot,'(\\+)$','$1$1')+'"'
$desktop=[Environment]::GetFolderPath('Desktop')
$destination=Join-Path $desktop ($Name+'.lnk')
$shell=New-Object -ComObject WScript.Shell
try{
    if(Test-Path -LiteralPath $destination){
        $previous=$shell.CreateShortcut($destination)
        $ownedExe=([IO.Path]::GetFileName($previous.TargetPath) -in @('FlowSwitch.exe','ProxySwitch.exe') -and ($previous.Description -like 'FlowSwitch *' -or $previous.Description -like 'ProxySwitch *'))
        if($previous.Arguments -notlike '*ProxySwitch.ps1*' -and -not $ownedExe){throw '此名称已被其他快捷方式使用，请换一个名称。'}
        $backupDir=Join-Path $dataRoot 'backups'
        [void][IO.Directory]::CreateDirectory($backupDir)
        Copy-Item -LiteralPath $destination -Destination (Join-Path $backupDir ('shortcut-'+(Get-Date -Format 'yyyyMMdd-HHmmss-fff')+'.lnk'))
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($previous)
    }
    $link=$shell.CreateShortcut($destination)
    $link.TargetPath=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $link.Arguments='-NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File "'+$entry+'" -DataDirectory '+$quotedDataDirectory
    $link.WorkingDirectory=$PSScriptRoot;$link.WindowStyle=7
    if($LauncherPath){
        $link.TargetPath=$LauncherPath;$link.Arguments='--data-directory '+$quotedDataDirectory
        $link.WorkingDirectory=[IO.Path]::GetDirectoryName($LauncherPath)
    }
    $versionText=[IO.File]::ReadAllText((Join-Path $PSScriptRoot 'Preferences.ps1'))
    $version=[regex]::Match($versionText,"ProductVersion='([0-9.]+)'").Groups[1].Value
    $link.Description='FlowSwitch '+$version+' · 流向：关闭窗口驻留托盘；通过托盘停止服务。'
    $icon=Join-Path $PSScriptRoot 'assets\FlowSwitch.ico'
    if(Test-Path -LiteralPath $icon){$link.IconLocation=$icon+',0'}
    $link.Save()
    Write-Output ('Desktop shortcut ready: '+$destination)
}finally{if($link){[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($link)};[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell)}
