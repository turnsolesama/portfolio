[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Destination)
$ErrorActionPreference='Stop'
$destinationPath=[IO.Path]::GetFullPath($Destination)
if(Test-Path -LiteralPath $destinationPath){throw '输出目录已存在，请使用一个新目录，以保留原发布包。'}
$files=@(
    'ProxySwitch.ps1','ProxyBackend.ps1','ProxyWindow.ps1','AppRouting.ps1','AppRouter.cjs','IndependentRouter.cjs','IndependentGateway.ps1','GatewayWatchdog.ps1','Preferences.ps1','ProxyDiscovery.ps1','ProcessInventory.ps1','ProgramLaunch.ps1','Storage.ps1','RuntimeSupport.ps1','Prepare-Runtime.ps1','runtime.lock.json','Test-RuntimeBundle.ps1','Test-RuntimePerformance.cjs','Test-StatusSnapshot.ps1','DesktopBranding.cs','FlowTheme.cs',
    'config.defaults.json','启动代理切换.cmd','Install-Shortcut.ps1','Test-All.ps1','Test-IndependentRouter.cjs','Test-IndependentIntegration.cjs','Test-ExitRecovery.ps1','Test-Watchdog.ps1','Test-GatewayControl.ps1','Test-GatewayIntegration.cjs','Test-ProxySwitch.ps1','Test-AppRouter.cjs','Test-Preferences.ps1','Test-ProxyDiscovery.ps1',
    'Build-Release.ps1','Build-WindowsPackage.ps1','Launcher.cs','Windows-QuickStart.txt','Test-WindowsPackage.ps1','Test-Compatibility.ps1','Test-AutomaticDiscovery.ps1','Test-ProgramLaunch.ps1','Test-Storage.ps1','Test-AutomaticDiscoveryUI.ps1','Test-SwitchInteraction.ps1','Test-PassiveLifecycle.ps1','Test-DiscoveryUI.ps1','Test-FailoverDisplay.ps1','README.md','CHANGELOG.md','LICENSE','THIRD_PARTY_NOTICES.md','AGENTS.md','.gitignore','.gitattributes',
    'DESIGN.md','Test-VisualTheme.ps1','assets/FlowSwitch.ico','assets/FlowSwitch.png','assets/screenshot.png','assets/program-menu.png','assets/proxy-management.png',
    'vendor/js-yaml/package.json','vendor/js-yaml/LICENSE','vendor/js-yaml/dist/js-yaml.cjs.js'
)
foreach($relative in $files){if(-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot $relative) -PathType Leaf)){throw ('缺少发布文件：'+$relative)}}
$tree=Join-Path $destinationPath 'proxy-switch';[void][IO.Directory]::CreateDirectory($tree)
$manifest=@()
foreach($relative in $files){
    $source=Join-Path $PSScriptRoot $relative;$target=Join-Path $tree $relative
    [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target));Copy-Item -LiteralPath $source -Destination $target
    $manifest+=[pscustomobject]@{path=$relative;bytes=(Get-Item -LiteralPath $target).Length;sha256=(Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()}
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $tree 'manifest.json') -Encoding UTF8
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive=Join-Path $destinationPath 'FlowSwitch-v3.5.1-Windows-Source.zip'
[IO.Compression.ZipFile]::CreateFromDirectory($tree,$archive,[IO.Compression.CompressionLevel]::Optimal,$true)
$hash=(Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
[IO.File]::WriteAllText((Join-Path $destinationPath 'SHA256SUMS.txt'),($hash+'  '+[IO.Path]::GetFileName($archive)+"`r`n"),(New-Object Text.UTF8Encoding($false)))
[pscustomobject]@{Directory=$tree;Archive=$archive;Bytes=(Get-Item -LiteralPath $archive).Length;SHA256=$hash}
