[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Destination)
$ErrorActionPreference='Stop'
$destinationPath=[IO.Path]::GetFullPath($Destination)
if(Test-Path -LiteralPath $destinationPath){throw '输出目录已存在，请使用新目录以保留原发布包。'}
$compiler=Join-Path $env:SystemRoot 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if(-not (Test-Path -LiteralPath $compiler)){throw '构建需要 Windows x64 与 .NET Framework C# 编译器；程序不会下载依赖。'}
$runtime=@(
    'ProxySwitch.ps1','ProxyWindow.ps1','ProxyBackend.ps1','Preferences.ps1','Storage.ps1','ProgramLaunch.ps1',
    'ProcessInventory.ps1','ProxyDiscovery.ps1','AppRouting.ps1','AppRouter.cjs','config.defaults.json','Install-Shortcut.ps1',
    'assets/ProxySwitch.ico','vendor/js-yaml/package.json','vendor/js-yaml/LICENSE','vendor/js-yaml/dist/js-yaml.cjs.js'
)
foreach($name in ($runtime+@('Launcher.cs','Windows-QuickStart.txt','LICENSE','THIRD_PARTY_NOTICES.md'))){
    if(-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot $name) -PathType Leaf)){throw ('缺少构建文件：'+$name)}
}
$package=Join-Path $destinationPath 'ProxySwitch';$app=Join-Path $package 'app'
[void][IO.Directory]::CreateDirectory($app)
foreach($name in $runtime){
    $target=Join-Path $app $name;[void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target))
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination $target
}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Windows-QuickStart.txt') -Destination (Join-Path $package '使用说明.txt')
foreach($name in @('LICENSE','THIRD_PARTY_NOTICES.md')){Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $package $name)}
$exe=Join-Path $package 'ProxySwitch.exe'
& $compiler /nologo /target:winexe /platform:x64 /optimize+ /codepage:65001 /reference:System.Windows.Forms.dll ('/win32icon:'+(Join-Path $PSScriptRoot 'assets/ProxySwitch.ico')) ('/out:'+$exe) (Join-Path $PSScriptRoot 'Launcher.cs')
if($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $exe)){throw 'EXE 编译失败。'}
$shortcutCmd='@echo off'+"`r`n"+'start "" "%~dp0ProxySwitch.exe" --install-shortcut'+"`r`n"
[IO.File]::WriteAllText((Join-Path $package '创建桌面快捷方式.cmd'),$shortcutCmd,[Text.Encoding]::ASCII)
$manifest=@(Get-ChildItem -LiteralPath $package -File -Recurse | ForEach-Object {
    [pscustomobject]@{path=$_.FullName.Substring($package.Length+1).Replace('\','/');bytes=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
})
[IO.File]::WriteAllText((Join-Path $package 'manifest.json'),($manifest|ConvertTo-Json -Depth 4),(New-Object Text.UTF8Encoding($false)))
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive=Join-Path $destinationPath 'ProxySwitch-v3.1.2-Windows-x64.zip'
[IO.Compression.ZipFile]::CreateFromDirectory($package,$archive,[IO.Compression.CompressionLevel]::Optimal,$true)
$hash=(Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
[IO.File]::WriteAllText((Join-Path $destinationPath 'SHA256SUMS.txt'),($hash+'  '+[IO.Path]::GetFileName($archive)+"`r`n"),(New-Object Text.UTF8Encoding($false)))
[pscustomobject]@{Directory=$package;Executable=$exe;Archive=$archive;Bytes=(Get-Item -LiteralPath $archive).Length;Files=($manifest.Count+1);SHA256=$hash}
