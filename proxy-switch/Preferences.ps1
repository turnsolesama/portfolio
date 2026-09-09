param([string]$DataDirectory='')
$script:ProductVersion='3.3.2'
. (Join-Path $PSScriptRoot 'Storage.ps1')
$script:LegacyDataRoot=Join-Path $env:LOCALAPPDATA 'ProxySwitch'
$script:DataRoot=Resolve-ProxyDataDirectory $DataDirectory $env:PROXY_SWITCH_DATA_DIR ([Environment]::GetFolderPath('UserProfile')) $env:LOCALAPPDATA
if(-not $DataDirectory -and -not $env:PROXY_SWITCH_DATA_DIR){Initialize-ProxyDataDirectory $script:DataRoot $script:LegacyDataRoot}
$script:ConfigPath=Join-Path $script:DataRoot 'config.json'
function Convert-LegacySettings($Value) {
    if($Value.Version -eq 3){return $Value}
    $items=@()
    foreach($key in @('Clash','Upnet')){
        if($Value.$key){$p=$Value.$key;$items+=[pscustomobject]@{Id=$key;Name=$p.Name;Protocol='http';Host='127.0.0.1';Port=$p.Port;AppPath=$p.AppPath;CorePath=$p.CorePath;AutoPort=($key -eq 'Clash' -and (-not $p.PSObject.Properties['AutoPort'] -or $p.AutoPort))}}
    }
    if(-not $items.Count){throw '无法识别代理配置版本。'}
    [pscustomobject]@{Version=3;Profiles=$items;Routing=[pscustomobject]@{Adapter=$(if($Value.Clash){'clash-verge'}else{'none'});ProfileId=$(if($Value.Clash){'Clash'}else{''})}}
}
function ConvertTo-ValidProfileSettings($Value) {
    if($Value.Version -ne 3){throw '代理配置版本无效。'}
    $ids=@{};$names=@{};$endpoints=@{};$items=@()
    if(@($Value.Profiles).Count -gt 32){throw '最多保存 32 个代理。'}
    foreach($p in $Value.Profiles){
        $id=[string]$p.Id;$name=([string]$p.Name).Trim();$protocol=([string]$p.Protocol).ToLowerInvariant()
        $hostName=([string]$p.Host).Trim().Trim('[',']').ToLowerInvariant()
        if($id -notmatch '^[A-Za-z0-9][A-Za-z0-9_-]{0,47}$' -or $id -in @('Direct','Follow','Other','Unset','Blocked','Unknown') -or $ids.ContainsKey($id)){throw '代理标识无效或重复。'}
        if(-not $name -or $name.Length -gt 40 -or $name -match '[\r\n\x00-\x1f]' -or $names.ContainsKey($name)){throw '代理名称不能为空、重复或超过 40 字。'}
        if($protocol -notin @('http','socks5')){throw '目前支持 HTTP 和 SOCKS5 代理入口。'}
        $address=$null
        if(-not [Net.IPAddress]::TryParse($hostName,[ref]$address) -and $hostName -notmatch '^(?=.{1,253}$)[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$'){throw '地址只填写 IP 或域名，不含协议、账号、路径或参数。'}
        if($hostName -match '[%\s,@/\\"\x00]'){throw '代理地址包含不支持的字符。'}
        $port=0;if(-not [int]::TryParse([string]$p.Port,[ref]$port) -or $port -lt 1 -or $port -gt 65535){throw '端口必须为 1 到 65535 的整数。'}
        $hostKey=$hostName;if($hostName -in @('localhost','127.0.0.1','::1')){$hostKey='loopback'}
        $endpoint=$hostKey+':'+$port
        if($endpoints.ContainsKey($endpoint)){throw '同一地址和端口只需添加一次，避免线路识别冲突。'}
        $entry=[ordered]@{Id=$id;Name=$name;Protocol=$protocol;Host=$hostName;Port=$port;AutoPort=[bool]$p.AutoPort}
        foreach($field in @('AppPath','CorePath')){
            $target=[Environment]::ExpandEnvironmentVariables([string]$p.$field).Trim()
            if($target -and (-not [IO.Path]::IsPathRooted($target) -or $target -notmatch '(?i)\.exe$' -or $target -match '[\r\n\x00"%]')){throw '关联程序和内核请选择完整的 EXE 路径。'}
            $entry[$field]=$target
        }
        $ids[$id]=$true;$names[$name]=$true;$endpoints[$endpoint]=$true;$items+=[pscustomobject]$entry
    }
    $adapter=[string]$Value.Routing.Adapter;$gateway=[string]$Value.Routing.ProfileId
    if($adapter -notin @('none','clash-verge')){throw '不支持的程序分流引擎。'}
    if($adapter -eq 'none'){$gateway=''}else{
        $engine=$items | Where-Object {$_.Id -eq $gateway} | Select-Object -First 1
        if(-not $engine -or $engine.Protocol -ne 'http' -or $engine.Host -notin @('localhost','127.0.0.1','::1') -or -not $engine.CorePath){throw '分流引擎需要本地 HTTP / 混合入口与 Clash Verge 内核路径。'}
    }
    $ignored=@($Value.DiscoveryIgnored | Where-Object {$_ -match '^loopback:[0-9]{1,5}$'} | Select-Object -Unique -First 128)
    $unifiedMode=[string]$Value.Routing.UnifiedMode
    if(-not $unifiedMode){$unifiedMode='system'}
    if($unifiedMode -notin @('system','gateway')){throw '统一切换模式无效。'}
    if($unifiedMode -eq 'gateway' -and $adapter -eq 'none'){throw '固定入口模式需要配置分流引擎。'}
    [pscustomobject]@{Version=3;Profiles=@($items);Routing=[pscustomobject]@{Adapter=$adapter;ProfileId=$gateway;UnifiedMode=$unifiedMode};DiscoveryIgnored=$ignored}
}
function Read-ProfileSettings {
    $path=$script:ConfigPath;if(-not (Test-Path -LiteralPath $path)){$path=Join-Path $PSScriptRoot 'config.defaults.json'}
    try{$value=Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json}catch{throw '本机代理配置无法读取，请检查 config.json。'}
    ConvertTo-ValidProfileSettings (Convert-LegacySettings $value)
}
function Write-LocalJson([string]$Path,$Value) {
    [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($Path));$temp=$Path+'.'+[Guid]::NewGuid().ToString('N')+'.tmp'
    try{
        [IO.File]::WriteAllText($temp,($Value | ConvertTo-Json -Depth 12),(New-Object Text.UTF8Encoding($false)))
        if(Test-Path -LiteralPath $Path){[IO.File]::Replace($temp,$Path,[NullString]::Value)}else{[IO.File]::Move($temp,$Path)}
    }finally{if(Test-Path -LiteralPath $temp){[IO.File]::Delete($temp)}}
}
function Get-RoutingSnapshot {
    $path=Join-Path $script:DataRoot 'app-rules.json'
    if(-not (Test-Path -LiteralPath $path)){return [pscustomobject]@{entries=@();defaultRoute=$null;installed=$false;launchEntries=@(Get-ProgramLaunchEntries)}}
    try{$state=Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json}catch{throw '程序规则文件无法读取，已停止更改。'}
    if($state.version -notin @(1,2)){throw '程序规则版本不兼容。'}
    if(-not $state.installed -and (@($state.entries).Count -gt 0 -or $state.defaultRoute)){throw '程序规则状态不一致，请先从备份恢复规则文件。'}
    [pscustomobject]@{entries=@($state.entries);defaultRoute=$state.defaultRoute;installed=[bool]$state.installed;launchEntries=@(Get-ProgramLaunchEntries)}
}
function Save-ProfileSettings($Value) {
    $clean=ConvertTo-ValidProfileSettings $Value
    Use-ChangeLock {
        $saved=Get-RoutingSnapshot;$selection=Get-Selection
        $inUse=@($saved.entries | ForEach-Object route)+@($saved.launchEntries | ForEach-Object route)+@($saved.defaultRoute,$selection.Key,$selection.NetworkKey,(Get-SystemKey (Get-SystemSnapshot)))
        foreach($id in $inUse){if($id -and $id -notin @('Direct','Other','Follow') -and $id -notin @($clean.Profiles | ForEach-Object Id)){throw '该代理仍被当前入口或程序规则使用，请先统一切换到其他线路再删除。'}}
        if($saved.installed -and ($clean.Routing.Adapter -ne $script:Profiles.Routing.Adapter -or $clean.Routing.ProfileId -ne $script:Profiles.Routing.ProfileId)){throw '请先取消固定入口模式并保存，再统一切换到直连以撤除规则，然后更换分流引擎。'}
        if(Test-Path -LiteralPath $script:ConfigPath){[void][IO.Directory]::CreateDirectory($script:BackupDir);Copy-Item -LiteralPath $script:ConfigPath -Destination (Join-Path $script:BackupDir ('settings-'+(Get-Date -Format 'yyyyMMdd-HHmmss-fff')+'.json'))}
        Write-LocalJson $script:ConfigPath $clean;$script:Profiles=$clean
    }
}
function Get-ProfileKeys { @($script:Profiles.Profiles | ForEach-Object Id) }
function Get-GatewayKey { if($script:Profiles.Routing.Adapter -eq 'clash-verge'){[string]$script:Profiles.Routing.ProfileId}else{''} }
function Get-RouteName([string]$Key) {
    switch($Key){'Direct'{return '直连'};'Follow'{return '跟随统一线路'};'Unset'{return '未设置'};'Other'{return '其他 / 自动代理'};'Unknown'{return '出口待确认'};'Blocked'{return '已拦截'}}
    $p=$script:Profiles.Profiles | Where-Object {$_.Id -eq $Key} | Select-Object -First 1
    if($p){return [string]$p.Name};return '已移除的代理'
}
function Get-EndpointAddress($Profile) {
    $h=$Profile.Host;if($h.Contains(':')){$h='['+$h+']'};return $h+':'+$Profile.Port
}
function Resolve-ProgramTarget([string]$Path) {
    if(-not (Test-Path -LiteralPath $Path -PathType Leaf)){throw '找不到所选文件。'}
    $target=[IO.Path]::GetFullPath($Path)
    if([IO.Path]::GetExtension($target) -ieq '.lnk'){
        $shell=New-Object -ComObject WScript.Shell
        try{$link=$shell.CreateShortcut($target);$target=[Environment]::ExpandEnvironmentVariables([string]$link.TargetPath)}
        finally{if($link){[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($link)};[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell)}
    }
    if(-not [IO.Path]::IsPathRooted($target) -or $target -notmatch '(?i)\.exe$' -or $target -match '[,\r\n\x00]' -or -not (Test-Path -LiteralPath $target -PathType Leaf)){throw '请选择指向 EXE 程序的快捷方式或 EXE 文件。网页、商店应用入口和脚本快捷方式暂不支持。'}
    if([IO.Path]::GetFileName($target) -match '^(?i:cmd|powershell|pwsh|wscript|cscript|explorer|rundll32)\.exe$'){throw '这个快捷方式由系统宿主启动，请从运行列表选择实际联网的程序。'}
    return [IO.Path]::GetFullPath($target)
}
function Select-ApplicationRows($Rows,[string]$Query,[bool]$SavedOnly) {
    foreach($row in $Rows){
        if($SavedOnly -and $row.Policy -eq 'Follow'){continue}
        if($Query -and ($row.Name+' '+$row.Path).IndexOf($Query,[StringComparison]::OrdinalIgnoreCase) -lt 0){continue}
        $row
    }
}
function New-SupportReport($State,$Apps) {
    $labels=@{Direct='Direct';Follow='Follow';Other='Other';Unset='Unset'};$index=0
    foreach($p in $script:Profiles.Profiles){$index++;$labels[$p.Id]='Proxy'+$index}
    $envRows=@($State.Environment | ForEach-Object {if($_.Name -in @('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY')){[pscustomobject]@{Name=$_.Name;Route=$(if($labels.ContainsKey([string]$_.Route)){$labels[$_.Route]}else{'Other'})}}})
    $listeners=@($State.Listeners | ForEach-Object {if($labels.ContainsKey([string]$_.Key)){[pscustomobject]@{Id=$labels[$_.Key];Port=[int]$_.Port;Ready=[bool]$_.Ready}}})
    $rules=@($Apps.Rows | Where-Object {$_.Policy -ne 'Follow'} | Group-Object Policy | ForEach-Object {[pscustomobject]@{Route=$(if($labels.ContainsKey($_.Name)){$labels[$_.Name]}else{'Other'});Count=$_.Count;Loaded=@($_.Group | Where-Object Loaded).Count}})
    [pscustomobject]@{Product='ProxySwitch';Version=$script:ProductVersion;GeneratedAt=(Get-Date).ToString('o');SystemRoute=$(if($labels.ContainsKey([string]$State.Key)){$labels[$State.Key]}else{'Other'});Aligned=[bool]$State.Aligned;EndpointReady=[bool]$State.EndpointReady;Drift=[bool]$State.Drift;Environment=$envRows;Listeners=$listeners;ApplicationCount=@($Apps.Rows).Count;RuleEngineAvailable=[bool]$Apps.Available;Rules=$rules;Privacy='不含代理名称、地址、账号、程序名称、路径或完整环境变量。'}
}
