$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$taskServer = Join-Path $taskRoot 'server.py'
$taskQuoted = [Regex]::Escape($taskServer)
$taskPattern = '(?i)(?:^|\s)(?:"' + $taskQuoted + '"|' + $taskQuoted + ')(?=\s|$)'
Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" | ForEach-Object {
    if ($_.CommandLine -and $_.CommandLine -match $taskPattern) {
        Stop-Process -Id $_.ProcessId
    }
}
Write-Output '映序本地服务已停止。项目和素材文件保留。'
