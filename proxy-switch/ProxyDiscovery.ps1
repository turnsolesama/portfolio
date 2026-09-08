# Protocol discovery inspects local listeners only. It never changes system routes.
function Get-LocalEndpointId([string]$Address,[int]$Port) {
    $name=$Address.Trim('[',']').ToLowerInvariant()
    if($name -in @('localhost','127.0.0.1','::1')){$name='loopback'}
    return $name+':'+$Port
}
function Get-LocalListenerInventory {
    $rows=@()
    try{$rows=@(Get-NetTCPConnection -State Listen -ErrorAction Stop)}catch{
        foreach($line in (& netstat.exe -ano -p tcp)){
            if($line -match '^\s*TCP\s+(\S+)\s+\S+\s+LISTENING\s+(\d+)\s*$'){
                $endpoint=$Matches[1];$ownerId=[int]$Matches[2]
                if($endpoint -match '^(.+):(\d+)$'){$rows+=[pscustomobject]@{LocalAddress=$Matches[1].Trim('[',']');LocalPort=[int]$Matches[2];OwningProcess=$ownerId}}
            }
        }
    }
    $processes=@{};Get-ProcessInventory | ForEach-Object {$processes[[int]$_.Id]=$_}
    $seen=@{};$result=@()
    foreach($row in $rows){
        if($row.LocalAddress -notin @('127.0.0.1','0.0.0.0','::1','::')){continue}
        $address='127.0.0.1';if($row.LocalAddress -in @('::1','::')){$address='::1'}
        $key=$address+':'+$row.LocalPort;if($seen.ContainsKey($key)){continue};$seen[$key]=$true
        $owner=$processes[[int]$row.OwningProcess];$name=[string]$owner.ProcessName;$exe=''
        try{$exe=[string]$owner.Path}catch{}
        $started='';try{if($owner.StartTime -and $owner.StartTime -ne [DateTime]::MinValue){$started=$owner.StartTime.ToUniversalTime().Ticks.ToString()}}catch{}
        $result+=[pscustomobject]@{Host=$address;Port=[int]$row.LocalPort;Name=$(if($name){$name}else{'本机代理'});Path=$exe;PID=[int]$row.OwningProcess;Started=$started;Priority=0}
    }
    @($result | Sort-Object Port,Host)
}
function Test-RecognizedProxyOwner($Endpoint) {
    # Exact executable identities, not substring matches or a well-known port alone.
    if(-not $Endpoint.Path -or [IO.Path]::GetFileNameWithoutExtension($Endpoint.Path) -ine $Endpoint.Name){return $false}
    if($Endpoint.Name -match '^(?i:clash(?:-verge|-meta)?|verge-mihomo|mihomo(?:-alpha)?|sing-box|v2ray|xray|upnet|ss-local|shadowsocks(?:r)?|gost|hiddify|nekoray|nekobox)$'){return $true}
    return @($script:Profiles.Profiles | Where-Object {$_.CorePath -and $_.CorePath -ieq $Endpoint.Path}).Count -gt 0
}
function Get-ProxyDiscoveryListeners([switch]$Automatic,$Inventory=$null) {
    if($null -eq $Inventory){$Inventory=@(Get-LocalListenerInventory)}
    $result=@()
    foreach($endpoint in $Inventory){
        $known=@($script:Profiles.Profiles | Where-Object {$_.Host -in @('localhost','127.0.0.1','::1') -and $_.Port -eq $endpoint.Port -and (-not $_.CorePath -or $_.CorePath -ieq $endpoint.Path)}).Count -gt 0
        $recognized=Test-RecognizedProxyOwner $endpoint
        if($recognized -or (-not $Automatic -and $known)){$result+=@($endpoint)}
    }
    @($result | Select-Object -First 48)
}
function Test-DiscoveryOwnerStillListening($Endpoint) {
    if(-not $Endpoint.PID){return $true} # Explicit, synthetic endpoints used by isolated tests.
    $owner=Get-ProcessInventory -Id $Endpoint.PID
    if(-not $owner -or $owner.ProcessName -ine $Endpoint.Name){return $false}
    try{if($Endpoint.Path -and $owner.Path -ine $Endpoint.Path){return $false};if($Endpoint.Started -and $owner.StartTime.ToUniversalTime().Ticks.ToString() -ne $Endpoint.Started){return $false}}catch{return $false}
    try{
        return @(Get-NetTCPConnection -State Listen -LocalPort $Endpoint.Port -ErrorAction Stop | Where-Object {$_.OwningProcess -eq $Endpoint.PID -and $_.LocalAddress -in @('127.0.0.1','0.0.0.0','::1','::')}).Count -gt 0
    }catch{
        # Keep the netstat fallback usable when the Windows TCP provider is unavailable.
        return @(Get-LocalListenerInventory | Where-Object {$_.Port -eq $Endpoint.Port -and $_.PID -eq $Endpoint.PID -and $_.Path -ieq $Endpoint.Path}).Count -gt 0
    }
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
function Find-LocalProxies($Endpoints=$null,$Cancellation=$null) {
    $items=@();$seen=@{};$watch=[Diagnostics.Stopwatch]::StartNew()
    if($null -eq $Endpoints){$Endpoints=@(Get-ProxyDiscoveryListeners)}
    foreach($endpoint in $Endpoints){
        if($Cancellation -and $Cancellation.IsCancellationRequested){break}
        if($watch.ElapsedMilliseconds -gt 12000){break}
        $key=Get-LocalEndpointId $endpoint.Host $endpoint.Port
        if($seen.ContainsKey($key)){continue}
        $saved=$script:Profiles.Profiles | Where-Object {(Get-LocalEndpointId $_.Host $_.Port) -eq $key} | Select-Object -First 1
        # HTTP wins for mixed ports, so basic system switching remains available without an engine.
        $protocol='';$order=@('http','socks5');if($saved.Protocol -eq 'socks5'){$order=@('socks5','http')}
        foreach($candidate in $order){
            if($Cancellation -and $Cancellation.IsCancellationRequested){break}
            if(-not (Test-DiscoveryOwnerStillListening $endpoint)){break}
            if(Test-LocalProxyProtocol $endpoint.Host $endpoint.Port $candidate){$protocol=$candidate;break}
        }
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
function Save-DiscoveredCandidates($Candidates) {
    Use-ChangeLock {
        # Re-read under the same lock as the editor to retain changes made while probing.
        $fresh=Read-ProfileSettings;$merged=Merge-DiscoveredProfiles $fresh $Candidates
        if($merged.Added.Count){Save-ProfileSettings $merged.Settings}
        $script:Profiles=Read-ProfileSettings
        [pscustomobject]@{Detected=@($Candidates).Count;Added=$merged.Added.Count;Names=@($merged.Added | ForEach-Object Name);CheckedAt=(Get-Date).ToString('HH:mm:ss')}
    }
}
function Sync-LocalProxyDiscovery {Save-DiscoveredCandidates @(Find-LocalProxies)}

function Get-ConfiguredLocalProxies($Inventory) {
    # Protocol comes from an existing setting, never from guessing a game's open port.
    $sources=@();$snapshot=Get-SystemSnapshot
    if(($snapshot.Flags -band 2) -and -not ($snapshot.Flags -band 12) -and $snapshot.Server -notmatch '[;=]'){$sources+=@([pscustomobject]@{Value=$snapshot.Server;Source='系统配置'})}
    $environment=Get-UserProxyEnv
    foreach($name in @('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY')){if($environment.$name){$sources+=@([pscustomobject]@{Value=$environment.$name;Source='代理变量'})}}
    $seen=@{}
    foreach($source in $sources){
        try{
            $raw=[string]$source.Value;if($raw -notmatch '^[a-z]+://'){$raw='http://'+$raw};$uri=[uri]$raw
            $address=$uri.Host.Trim('[',']');if($address -notin @('localhost','127.0.0.1','::1') -or $uri.UserInfo -or $uri.Query -or $uri.AbsolutePath -notin @('','/') -or $uri.Port -lt 1){continue}
            $protocol=$(if($uri.Scheme -eq 'http'){'http'}elseif($uri.Scheme -in @('socks5','socks5h')){'socks5'}else{''});if(-not $protocol){continue}
            $key=Get-LocalEndpointId $address $uri.Port;if($seen.ContainsKey($key)){continue}
            $owner=$Inventory | Where-Object {(Get-LocalEndpointId $_.Host $_.Port) -eq $key} | Select-Object -First 1
            if(-not $owner){continue};$seen[$key]=$true
            $sha=[Security.Cryptography.SHA256]::Create()
            try{$id='p'+([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($key)))).Replace('-','').Substring(0,12).ToLowerInvariant()}finally{$sha.Dispose()}
            $name=[string]$owner.Name;if($name.Length -gt 16){$name=$name.Substring(0,16)}
            [pscustomobject]@{Id=$id;Name=($name+' '+$protocol.ToUpperInvariant()+' :'+$uri.Port);Host=$address;Port=$uri.Port;Protocol=$protocol;CorePath='';AppPath='';AutoPort=$false}
        }catch{continue}
    }
}
function Sync-AutomaticProxyDiscovery($Cache=@(),$Cancellation=$null) {
    $inventory=@(Get-LocalListenerInventory);$endpoints=@(Get-ProxyDiscoveryListeners -Automatic -Inventory $inventory)
    $configured=@(Get-ConfiguredLocalProxies $inventory);$candidates=@();$next=@();$probed=0;$now=[DateTime]::UtcNow
    foreach($endpoint in $endpoints){
        if($Cancellation -and $Cancellation.IsCancellationRequested){break}
        $key=(Get-LocalEndpointId $endpoint.Host $endpoint.Port)+'|'+$endpoint.PID+'|'+$endpoint.Started+'|'+$endpoint.Path
        $cached=$Cache | Where-Object {$_.Key -eq $key -and [DateTime]::Parse($_.Expires).ToUniversalTime() -gt $now} | Select-Object -First 1
        if($cached){$next+=@($cached);if($cached.Profile){$candidates+=@($cached.Profile)};continue}
        # Bound background work; a manual switch cooperatively cancels inspection.
        if($probed -ge 2){continue};$probed++
        $found=@(Find-LocalProxies @($endpoint) $Cancellation) | Select-Object -First 1
        $expiry=$now.AddSeconds(30);if($found){$candidates+=@($found);$expiry=$now.AddMinutes(10)}
        $next+=@([pscustomobject]@{Key=$key;Expires=$expiry.ToString('o');Profile=$found})
    }
    # Verified protocols win over a configured protocol when both describe the same port.
    $all=@($candidates)+@($configured);$unique=@{};$merged=@()
    foreach($candidate in $all){$key=Get-LocalEndpointId $candidate.Host $candidate.Port;if(-not $unique.ContainsKey($key)){$unique[$key]=$true;$merged+=@($candidate)}}
    if($Cancellation -and $Cancellation.IsCancellationRequested){return $null}
    $result=Save-DiscoveredCandidates $merged
    $result | Add-Member NoteProperty Cache @($next)
    $result | Add-Member NoteProperty Probed $probed
    $result | Add-Member NoteProperty Configured $configured.Count
    return $result
}
