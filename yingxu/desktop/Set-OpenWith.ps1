param([switch]$Unregister)
$ErrorActionPreference = 'Stop'
$appRoot = Split-Path -Parent $PSScriptRoot
$executable = Join-Path $appRoot 'YingXu.exe'
if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) { throw '未找到映序程序。请保留完整程序目录。' }
$operation = if ($Unregister) { '--unregister-open-with' } else { '--register-open-with' }
# Only this user's OpenWith candidates are registered. Never writes UserChoice/defaults.
Start-Process -FilePath $executable -ArgumentList @($operation) -WorkingDirectory $appRoot -Wait
