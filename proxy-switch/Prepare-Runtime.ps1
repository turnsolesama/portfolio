[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Destination,[string]$ArchiveDirectory='')
$ErrorActionPreference='Stop'
$target=[IO.Path]::GetFullPath($Destination)
if(Test-Path -LiteralPath $target){throw '运行组件目录已存在，请使用新目录。'}
$lock=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'runtime.lock.json') -Raw -Encoding UTF8 | ConvertFrom-Json
[void][IO.Directory]::CreateDirectory($target)
Add-Type -AssemblyName System.IO.Compression.FileSystem
if(-not $ArchiveDirectory){$ArchiveDirectory=Join-Path $target 'downloads'}
[void][IO.Directory]::CreateDirectory($ArchiveDirectory)
function Acquire($Url,$Hash,$Name){
    $file=Join-Path $ArchiveDirectory $Name
    if(-not (Test-Path -LiteralPath $file)){
        [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $Url -OutFile $file -UseBasicParsing
    }
    if((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ine $Hash){throw ('官方发布文件 SHA-256 不匹配：'+$Name)}
    return $file
}
function Extract-Entry($Archive,$Entry,$Destination){
    $zip=[IO.Compression.ZipFile]::OpenRead($Archive)
    try{$item=$zip.Entries|Where-Object {$_.FullName.Replace('\','/') -ceq $Entry}|Select-Object -First 1;if(-not $item){throw ('缺少组件：'+$Entry)};[IO.Compression.ZipFileExtensions]::ExtractToFile($item,$Destination)}finally{$zip.Dispose()}
}
$node=Acquire $lock.node.url $lock.node.sha256 'node-v24.19.0-win-x64.zip'
$core=Acquire $lock.mihomo.url $lock.mihomo.sha256 'mihomo-v2.zip'
$compatible=Acquire $lock.mihomoCompat.url $lock.mihomoCompat.sha256 'mihomo-v1.zip'
$source=Acquire $lock.mihomo.sourceUrl $lock.mihomo.sourceSHA256 'mihomo-source.zip'
Extract-Entry $node $lock.node.executable (Join-Path $target 'node.exe')
Extract-Entry $node $lock.node.license (Join-Path $target 'NODE-LICENSE.txt')
Extract-Entry $core $lock.mihomo.executable (Join-Path $target 'FlowSwitch.Core.exe')
Extract-Entry $compatible $lock.mihomoCompat.executable (Join-Path $target 'FlowSwitch.Core.Compat.exe')
Extract-Entry $source $lock.mihomo.sourceLicense (Join-Path $target 'MIHOMO-LICENSE.txt')
[void][IO.Directory]::CreateDirectory((Join-Path $target 'sources'))
Copy-Item -LiteralPath $source -Destination (Join-Path $target 'sources\mihomo-v1.19.29-source.zip')
$files=@('node.exe','FlowSwitch.Core.exe','FlowSwitch.Core.Compat.exe','NODE-LICENSE.txt','MIHOMO-LICENSE.txt','sources/mihomo-v1.19.29-source.zip')
$manifest=[ordered]@{Platform=$lock.platform;Node=$lock.node;Mihomo=$lock.mihomo;MihomoCompat=$lock.mihomoCompat;Files=@($files|ForEach-Object {$path=Join-Path $target $_;[pscustomobject]@{path=$_;bytes=(Get-Item -LiteralPath $path).Length;sha256=(Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant()}})}
[IO.File]::WriteAllText((Join-Path $target 'runtime-manifest.json'),($manifest|ConvertTo-Json -Depth 8),(New-Object Text.UTF8Encoding($false)))
[pscustomobject]@{RuntimeDirectory=$target;Node=$lock.node.version;Mihomo=$lock.mihomo.version;Architecture=$lock.mihomo.architecture;Verified=$true}
