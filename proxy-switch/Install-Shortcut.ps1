[CmdletBinding()]
param([string]$Name='ProxySwitch 网络代理管家')
$ErrorActionPreference='Stop'
if($Name -match '[<>:"/\\|?*\x00-\x1f]' -or -not $Name.Trim()){throw '快捷方式名称无效。'}
$entry=Join-Path $PSScriptRoot 'ProxySwitch.ps1'
if(-not (Test-Path -LiteralPath $entry)){throw '请先解压完整程序包。'}
. (Join-Path $PSScriptRoot 'Storage.ps1')
$dataRoot=Resolve-ProxyDataDirectory '' $env:PROXY_SWITCH_DATA_DIR ([Environment]::GetFolderPath('UserProfile')) $env:LOCALAPPDATA
if(-not $env:PROXY_SWITCH_DATA_DIR){Initialize-ProxyDataDirectory $dataRoot (Join-Path $env:LOCALAPPDATA 'ProxySwitch')}
$desktop=[Environment]::GetFolderPath('Desktop')
$destination=Join-Path $desktop ($Name+'.lnk')
$shell=New-Object -ComObject WScript.Shell
try{
    if(Test-Path -LiteralPath $destination){
        $previous=$shell.CreateShortcut($destination)
        if($previous.Arguments -notlike '*ProxySwitch.ps1*'){throw '此名称已被其他快捷方式使用，请换一个名称。'}
        $backupDir=Join-Path $dataRoot 'backups'
        [void][IO.Directory]::CreateDirectory($backupDir)
        Copy-Item -LiteralPath $destination -Destination (Join-Path $backupDir ('shortcut-'+(Get-Date -Format 'yyyyMMdd-HHmmss-fff')+'.lnk'))
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($previous)
    }
    $link=$shell.CreateShortcut($destination)
    $link.TargetPath=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $link.Arguments='-NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File "'+$entry+'" -DataDirectory "'+$dataRoot+'"'
    $link.WorkingDirectory=$PSScriptRoot;$link.WindowStyle=7
    $link.Description='ProxySwitch 3.1.1：管理自定义代理，一键统一切换，按程序指定线路。'
    $icon=Join-Path $PSScriptRoot 'assets\ProxySwitch.ico'
    if(Test-Path -LiteralPath $icon){$link.IconLocation=$icon+',0'}
    $link.Save()
    Write-Output ('Desktop shortcut ready: '+$destination)
}finally{if($link){[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($link)};[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell)}
