# Keep shared user settings outside AppData, where packaged parent processes can redirect new files.
function Resolve-ProxyDataDirectory([string]$ExplicitDirectory,[string]$EnvironmentDirectory,[string]$ProfileDirectory,[string]$LocalDirectory) {
    $shared=[IO.Path]::GetFullPath((Join-Path $ProfileDirectory '.proxyswitch'))
    $legacy=[IO.Path]::GetFullPath((Join-Path $LocalDirectory 'ProxySwitch'))
    if($ExplicitDirectory){
        $explicit=[IO.Path]::GetFullPath($ExplicitDirectory)
        $marker=Join-Path $shared 'storage-layout.json'
        if($explicit.TrimEnd('\') -ieq $legacy.TrimEnd('\') -and (Test-Path -LiteralPath $marker)){
            try{$layout=Get-Content -LiteralPath $marker -Raw -Encoding UTF8|ConvertFrom-Json}catch{throw '共享配置位置记录无法读取，已停止启动。'}
            if($layout.version -eq 1 -and $layout.legacyDirectory -ieq $legacy){return $shared}
        }
        return $explicit
    }
    if($EnvironmentDirectory){return [IO.Path]::GetFullPath($EnvironmentDirectory)}
    return $shared
}
function Initialize-ProxyDataDirectory([string]$Directory,[string]$LegacyDirectory) {
    if(Test-Path -LiteralPath $Directory){return}
    $destination=[IO.Path]::GetFullPath($Directory)
    $parent=[IO.Path]::GetDirectoryName($destination)
    $staging=Join-Path $parent ('.proxyswitch-migrate-'+[Guid]::NewGuid().ToString('N'))
    [void][IO.Directory]::CreateDirectory($staging)
    try{
        foreach($name in @('config.json','selection.json','app-rules.json','program-proxies.json','program-shortcuts.json','program-launches.json')){
            $source=Join-Path $LegacyDirectory $name
            if(Test-Path -LiteralPath $source -PathType Leaf){Copy-Item -LiteralPath $source -Destination (Join-Path $staging $name)}
        }
        $backupRoot=Join-Path $LegacyDirectory 'backups'
        if(Test-Path -LiteralPath $backupRoot -PathType Container){Copy-Item -LiteralPath $backupRoot -Destination (Join-Path $staging 'backups') -Recurse}
        $recordsPath=Join-Path $staging 'program-shortcuts.json'
        if(Test-Path -LiteralPath $recordsPath){
            $records=Get-Content -LiteralPath $recordsPath -Raw -Encoding UTF8|ConvertFrom-Json
            $prefix=[IO.Path]::GetFullPath($LegacyDirectory).TrimEnd('\')+'\'
            foreach($record in @($records.entries)){
                if($record.originalBackup -and $record.originalBackup.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)){
                    $record.originalBackup=Join-Path $destination $record.originalBackup.Substring($prefix.Length)
                }
            }
            [IO.File]::WriteAllText($recordsPath,($records|ConvertTo-Json -Depth 12),(New-Object Text.UTF8Encoding($false)))
        }
        $layout=[pscustomobject]@{version=1;legacyDirectory=[IO.Path]::GetFullPath($LegacyDirectory);created=(Get-Date).ToString('o')}
        [IO.File]::WriteAllText((Join-Path $staging 'storage-layout.json'),($layout|ConvertTo-Json),(New-Object Text.UTF8Encoding($false)))
        try{[IO.Directory]::Move($staging,$destination)}catch{if(-not (Test-Path -LiteralPath (Join-Path $destination 'storage-layout.json'))){throw}}
    }finally{
        # Only remove the exact temporary sibling created by this invocation; never the source or destination.
        $resolved=[IO.Path]::GetFullPath($staging)
        if($resolved -ne $destination -and [IO.Path]::GetDirectoryName($resolved) -eq $parent -and [IO.Path]::GetFileName($resolved) -match '^\.proxyswitch-migrate-[a-f0-9]{32}$' -and (Test-Path -LiteralPath $resolved)){
            Remove-Item -LiteralPath $resolved -Recurse -Force
        }
    }
}
