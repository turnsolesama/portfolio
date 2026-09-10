[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Destination,[Parameter(Mandatory=$true)][string]$RuntimeDirectory)
$ErrorActionPreference='Stop'
$productVersion=[regex]::Match([IO.File]::ReadAllText((Join-Path $PSScriptRoot 'Preferences.ps1')),"ProductVersion='([0-9.]+)'").Groups[1].Value
if($productVersion -notmatch '^\d+\.\d+\.\d+$'){throw '产品版本无效'}
$destinationPath=[IO.Path]::GetFullPath($Destination)
if(Test-Path -LiteralPath $destinationPath){throw '输出目录已存在，请使用新目录以保留原发布包。'}
$compiler=Join-Path $env:SystemRoot 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if(-not (Test-Path -LiteralPath $compiler)){throw '构建需要 Windows x64 与 .NET Framework C# 编译器；程序不会下载依赖。'}
$runtime=@(
    'ProxySwitch.ps1','ProxyWindow.ps1','ProxyBackend.ps1','Preferences.ps1','Storage.ps1','DesktopBranding.cs','FlowTheme.cs','ProgramLaunch.ps1',
    'ProcessInventory.ps1','ProxyDiscovery.ps1','RuntimeSupport.ps1','AppRouting.ps1','AppRouter.cjs','IndependentRouter.cjs','IndependentGateway.ps1','GatewayWatchdog.ps1','config.defaults.json','Install-Shortcut.ps1',
    'assets/FlowSwitch.ico','vendor/js-yaml/package.json','vendor/js-yaml/LICENSE','vendor/js-yaml/dist/js-yaml.cjs.js'
)
foreach($name in ($runtime+@('Launcher.cs','Windows-QuickStart.txt','LICENSE','THIRD_PARTY_NOTICES.md'))){
    if(-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot $name) -PathType Leaf)){throw ('缺少构建文件：'+$name)}
}
$package=Join-Path $destinationPath 'FlowSwitch';$app=Join-Path $package 'app'
$bundleFiles=@('node.exe','FlowSwitch.Core.exe','FlowSwitch.Core.Compat.exe','NODE-LICENSE.txt','MIHOMO-LICENSE.txt','sources/mihomo-v1.19.29-source.zip')
$bundleManifest=Get-Content -LiteralPath (Join-Path $RuntimeDirectory 'runtime-manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$locked=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'runtime.lock.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if($bundleManifest.Node.sha256 -ne $locked.node.sha256 -or $bundleManifest.Mihomo.sha256 -ne $locked.mihomo.sha256){throw '运行组件版本不匹配锁定文件。'}
if((Get-FileHash -LiteralPath (Join-Path $RuntimeDirectory 'node.exe')).Hash -ine $locked.node.executableSHA256 -or (Get-FileHash -LiteralPath (Join-Path $RuntimeDirectory 'FlowSwitch.Core.exe')).Hash -ine $locked.mihomo.executableSHA256){throw '运行文件与锁定的官方二进制不一致。'}
if((Get-FileHash -LiteralPath (Join-Path $RuntimeDirectory 'FlowSwitch.Core.Compat.exe')).Hash -ine $locked.mihomoCompat.executableSHA256){throw '兼容内核与锁定的官方二进制不一致。'}
foreach($name in $bundleFiles){$entry=$bundleManifest.Files|Where-Object path -ceq $name;if(@($entry).Count -ne 1 -or (Get-FileHash -LiteralPath (Join-Path $RuntimeDirectory $name)).Hash -ine $entry.sha256){throw ('运行组件校验失败：'+$name)}}
[void][IO.Directory]::CreateDirectory($app)
foreach($name in ($bundleFiles+@('runtime-manifest.json'))){$out=Join-Path $app ('runtime/'+$name);[void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($out));Copy-Item -LiteralPath (Join-Path $RuntimeDirectory $name) -Destination $out}
foreach($name in $runtime){
    $target=Join-Path $app $name;[void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target))
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination $target
}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Windows-QuickStart.txt') -Destination (Join-Path $package '使用说明.txt')
foreach($name in @('LICENSE','THIRD_PARTY_NOTICES.md')){Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $package $name)}
$exe=Join-Path $package 'FlowSwitch.exe'
& $compiler /nologo /target:winexe /platform:x64 /optimize+ /codepage:65001 /reference:System.Windows.Forms.dll ('/win32icon:'+(Join-Path $PSScriptRoot 'assets/FlowSwitch.ico')) ('/out:'+$exe) (Join-Path $PSScriptRoot 'Launcher.cs')
if($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $exe)){throw 'EXE 编译失败。'}
$shortcutCmd='@echo off'+"`r`n"+'start "" "%~dp0FlowSwitch.exe" --install-shortcut'+"`r`n"
[IO.File]::WriteAllText((Join-Path $package '创建桌面快捷方式.cmd'),$shortcutCmd,[Text.Encoding]::ASCII)
$manifest=@(Get-ChildItem -LiteralPath $package -File -Recurse | ForEach-Object {
    [pscustomobject]@{path=$_.FullName.Substring($package.Length+1).Replace('\','/');bytes=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
})
[IO.File]::WriteAllText((Join-Path $package 'manifest.json'),($manifest|ConvertTo-Json -Depth 4),(New-Object Text.UTF8Encoding($false)))
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive=Join-Path $destinationPath ('FlowSwitch-v'+$productVersion+'-Windows-x64.zip')
[IO.Compression.ZipFile]::CreateFromDirectory($package,$archive,[IO.Compression.CompressionLevel]::Optimal,$true)
$hash=(Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
[IO.File]::WriteAllText((Join-Path $destinationPath 'SHA256SUMS.txt'),($hash+'  '+[IO.Path]::GetFileName($archive)+"`r`n"),(New-Object Text.UTF8Encoding($false)))
[pscustomobject]@{Directory=$package;Executable=$exe;Archive=$archive;Bytes=(Get-Item -LiteralPath $archive).Length;Files=($manifest.Count+1);SHA256=$hash}
