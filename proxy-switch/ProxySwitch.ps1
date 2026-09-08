[CmdletBinding()]
param(
    [switch]$Status,
    [switch]$Discover,
    [string]$Check,
    [string]$Switch,
    [switch]$Restore,
    [switch]$AppStatus,
    [string]$Program,
    [string]$AppRoute,
    [switch]$SmokeTest,
    [string]$PreviewPath,
    [switch]$PreviewMenu,
    [switch]$Demo,
    [ValidateSet('Programs','Tools','Settings','Proxies')][string]$PreviewView='Programs',
    [string]$ExportReport,
    [switch]$NoUI
)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProxyBackend.ps1')
if($NoUI){return}
if($Discover){Sync-LocalProxyDiscovery | ConvertTo-Json -Depth 5;return}
if($ExportReport){Write-LocalJson ([IO.Path]::GetFullPath($ExportReport)) (New-SupportReport (Get-ProxyStatus) (Get-ApplicationRoutes));Write-Output 'Diagnostic summary exported.';return}
if($AppStatus){Get-ApplicationRoutes | ConvertTo-Json -Depth 8;return}
if($AppRoute){Set-ApplicationRoute $Program $AppRoute | ConvertTo-Json -Depth 8;return}
if($Status){Get-ProxyStatus | ConvertTo-Json -Depth 8;return}
if($Check){Test-ProxyRoute $Check | ConvertTo-Json -Depth 6;return}
if($Switch){Set-SelectedProxy $Switch | ConvertTo-Json -Depth 6;return}
if($Restore){Restore-ProxyBackup | ConvertTo-Json -Depth 6;return}
& (Join-Path $PSScriptRoot 'ProxyWindow.ps1') -PreviewPath $PreviewPath -SmokeTest:$SmokeTest -PreviewMenu:$PreviewMenu -Demo:$Demo -PreviewView $PreviewView
