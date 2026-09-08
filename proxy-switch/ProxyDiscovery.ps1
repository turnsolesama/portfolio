# Protocol discovery inspects local listeners only. It never changes system routes.
function Get-LocalEndpointId([string]$Address,[int]$Port) {
    $name=$Address.Trim('[',']').ToLowerInvariant()
    if($name -in @('localhost','127.0.0.1','::1')){$name='loopback'}
    return $name+':'+$Port
}
function Get-ProxyDiscoveryListeners {
    $rows=@()
    try{$rows=@(Get-NetTCPConnection -State Listen -ErrorAction Stop)}catch{
        foreach($line in (& netstat.exe -ano -p tcp)){
            if($line -match '^\s*TCP\s+(\S+)\s+\S+\s+LISTENING\s+(\d+)\s*$'){
                $endpoint=$Matches[1];$ownerId=[int]$Matches[2]
                if($endpoint -match '^(.+):(\d+)$'){$rows+=[pscustomobject]@{LocalAddress=$Matches[1].Trim('[',']');LocalPort=[int]$Matches[2];OwningProcess=$ownerId}}
            }
        }
    }
    $processes=@{};Get-Process -ErrorAction SilentlyContinue | ForEach-Object {$processes[[int]$_.Id]=$_}
    $seen=@{};$result=@()
    foreach($row in $rows){
        if($row.LocalAddress -notin @('127.0.0.1','0.0.0.0','::1','::')){continue}
        $address='127.0.0.1';if($row.LocalAddress -in @('::1','::')){$address='::1'}
        $key=$address+':'+$row.LocalPort;if($seen.ContainsKey($key)){continue};$seen[$key]=$true
        $owner=$processes[[int]$row.OwningProcess];$name=[string]$owner.ProcessName;$exe=''
        try{$exe=[string]$owner.Path}catch{}
        $known=@($script:Profiles.Profiles | Where-Object {$_.Host -in @('localhost','127.0.0.1','::1') -and $_.Port -eq $row.LocalPort}).Count -gt 0
        $hint=$known -or $name -match '(?i)clash|mihomo|sing.?box|v2ray|xray|upnet|ss-local|shadowsocks|gost|hiddify|nekoray'
        # Unknown user applications are probed too; system services are not scanned indiscriminately.
        if(-not $hint -and (-not $owner -or $owner.SessionId -eq 0 -or $name -match '^(System|Idle|lsass|services|svchost|wininit|winlogon)$')){continue}
        $result+=[pscustomobject]@{Host=$address;Port=[int]$row.LocalPort;Name=$(if($name){$name}else{'本机代理'});Path=$exe;Priority=$(if($hint){0}else{1})}
    }
    @($result | Sort-Object Priority,Port,Host | Select-Object -First 48)
}
function Test-LocalProxyProtocol([string]$Address,[int]$Port,[ValidateSet('http','socks5')][string]$Protocol,[int]$Timeout=1000) {
    if($Address -notin @('127.0.0.1','::1','localhost')){return $false}
    $client=New-Object Net.Sockets.TcpClient
    try{
        $pending=$client.BeginConnect($Address,$Port,$null,$null)
        try{if(-not $pending.AsyncWaitHandle.WaitOne([Math]::Min(400,$Timeout))){return $false};$client.EndConnect($pending)}finally{$pending.AsyncWaitHandle.Close()}
        $stream=$client.GetStream();$stream.ReadTimeout=$Timeout;$stream.WriteTimeout=$Timeout
        if($Protocol -eq 'socks5'){
            $hello=[byte[]]@(5,1,0);$stream.Write($hello,0,$hello.Length)
            $answer=New-Object byte[] 2;$offset=0
            while($offset -lt 2){$read=$stream.Read($answer,$offset,2-$offset);if($read -le 0){return $false};$offset+=$read}
            return ($answer[0] -eq 5 -and $answer[1] -eq 0)
        }
        $request=[Text.Encoding]::ASCII.GetBytes("CONNECT www.microsoft.com:443 HTTP/1.1`r`nHost: www.microsoft.com:443`r`n`r`n")
        $stream.Write($request,0,$request.Length);$header='';$watch=[Diagnostics.Stopwatch]::StartNew()
        while($header.Length -lt 4096 -and -not $header.EndsWith("`r`n`r`n")){
            if($watch.ElapsedMilliseconds -ge $Timeout){return $false}
            $stream.ReadTimeout=[Math]::Max(1,$Timeout-[int]$watch.ElapsedMilliseconds)
            $next=$stream.ReadByte();if($next -lt 0){return $false};$header+=[char]$next
        }
        # A successful CONNECT response differs from an ordinary HTTP page or control API.
        return ($header.EndsWith("`r`n`r`n") -and $header -match '^HTTP/1\.[01] 200 (?:Connection [Ee]stablished|[Cc]onnection established|[Oo][Kk])\r\n' -and $header -notmatch '(?im)^(Content-Length:\s*[1-9]|Content-Type:|Transfer-Encoding:)')
    }catch{return $false}finally{$client.Close()}
}
function Find-LocalProxies {
    $items=@();$seen=@{};$watch=[Diagnostics.Stopwatch]::StartNew()
    foreach($endpoint in @(Get-ProxyDiscoveryListeners)){
        if($watch.ElapsedMilliseconds -gt 12000){break}
        $key=Get-LocalEndpointId $endpoint.Host $endpoint.Port
        if($seen.ContainsKey($key)){continue}
        $saved=$script:Profiles.Profiles | Where-Object {(Get-LocalEndpointId $_.Host $_.Port) -eq $key} | Select-Object -First 1
        # HTTP wins for mixed ports, so basic system switching remains available without an engine.
        $protocol='';$order=@('http','socks5');if($saved.Protocol -eq 'socks5'){$order=@('socks5','http')}
        foreach($candidate in $order){if(Test-LocalProxyProtocol $endpoint.Host $endpoint.Port $candidate){$protocol=$candidate;break}}
        if(-not $protocol){continue};$seen[$key]=$true
        $sha=[Security.Cryptography.SHA256]::Create()
        try{$id='p'+([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($key)))).Replace('-','').Substring(0,12).ToLowerInvariant()}finally{$sha.Dispose()}
        $name=$endpoint.Name;if($name.Length -gt 20){$name=$name.Substring(0,20)}
        $items+=[pscustomobject]@{Id=$id;Name=($name+' '+$protocol.ToUpperInvariant()+' :'+$endpoint.Port);Protocol=$protocol;Host=$endpoint.Host;Port=$endpoint.Port;AppPath='';CorePath=$endpoint.Path;AutoPort=$false}
    }
    return $items
}
function Merge-DiscoveredProfiles($Settings,$Candidates) {
    $value=ConvertTo-ValidProfileSettings $Settings;$added=@();$keys=@{};$names=@{};$ids=@{}
    foreach($p in $value.Profiles){$keys[(Get-LocalEndpointId $p.Host $p.Port)]=$true;$names[$p.Name]=$true;$ids[$p.Id]=$true}
    foreach($p in $Candidates){
        $key=Get-LocalEndpointId $p.Host $p.Port
        if($keys.ContainsKey($key) -or $key -in $value.DiscoveryIgnored -or $value.Profiles.Count -ge 32){continue}
        $copy=$p | Select-Object Id,Name,Protocol,Host,Port,AppPath,CorePath,AutoPort
        if($copy.Host -notin @('127.0.0.1','::1','localhost') -or $copy.Protocol -notin @('http','socks5')){continue}
        if($ids.ContainsKey($copy.Id)){$copy.Id='p'+[Guid]::NewGuid().ToString('N').Substring(0,12)}
        if($names.ContainsKey($copy.Name)){$copy.Name=$copy.Name.Substring(0,[Math]::Min(26,$copy.Name.Length))+' '+$copy.Id.Substring(1,8)}
        $value.Profiles+=@($copy);$added+=@($copy);$keys[$key]=$true;$names[$copy.Name]=$true;$ids[$copy.Id]=$true
    }
    [pscustomobject]@{Settings=(ConvertTo-ValidProfileSettings $value);Added=@($added)}
}
function Sync-LocalProxyDiscovery {
    $candidates=@(Find-LocalProxies)
    Use-ChangeLock {
        # Re-read under the same lock as the editor to retain changes made while probing.
        $fresh=Read-ProfileSettings;$merged=Merge-DiscoveredProfiles $fresh $candidates
        if($merged.Added.Count){Save-ProfileSettings $merged.Settings}
        $script:Profiles=Read-ProfileSettings
        [pscustomobject]@{Detected=$candidates.Count;Added=$merged.Added.Count;Names=@($merged.Added | ForEach-Object Name);CheckedAt=(Get-Date).ToString('HH:mm:ss')}
    }
}
