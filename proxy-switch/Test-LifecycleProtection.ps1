$ErrorActionPreference='Stop'
$env:PROXY_SWITCH_DATA_DIR=Join-Path $env:TEMP ('FlowSwitch-LifecycleProtection-'+[Guid]::NewGuid().ToString('N'))
. (Join-Path $PSScriptRoot 'ProxyBackend.ps1')
$script:checks=0
function Check($Value,$Message){if(-not $Value){throw $Message};$script:checks++;Write-Output ('PASS: '+$Message)}
$profile=[pscustomobject]@{Id='gateway';Name='Fixture';Host='127.0.0.1';Port=18790;Protocol='http';CorePath='C:\Fixture.exe'}
$script:Profiles=[pscustomobject]@{Routing=[pscustomobject]@{Adapter='standalone';ProfileId='gateway';UnifiedMode='gateway'};Profiles=@($profile)}
$system=[pscustomobject]@{Flags=3;Server='127.0.0.1:18790';Bypass='localhost'}
$environment=[pscustomobject]@{HTTP_PROXY='http://127.0.0.1:18790';HTTPS_PROXY='http://127.0.0.1:18790';ALL_PROXY='http://127.0.0.1:18790'}
$script:life=[pscustomobject]@{phase='restarting';supervisor=$PID;updatedAt=[DateTimeOffset]::UtcNow.ToString('o');attempt=1}
function Get-GatewayLifecycle {$script:life}
$session=[pscustomobject]@{SupervisorPID=$PID;SupervisorStart=(Get-ProcessStartTicks $PID)}
Check (Test-GatewayRecoveryGrace $session 3) 'live supervisor with fresh recovery heartbeat keeps restoration from racing restart'
Check (-not (Test-GatewayRecoveryGrace $session 46)) 'recovery grace has a hard time limit'
$script:life.phase='failed';Check (-not (Test-GatewayRecoveryGrace $session 3)) 'exhausted recovery receives no grace'
$script:life.phase='restarting';$script:life.updatedAt=[DateTimeOffset]::UtcNow.AddSeconds(-8).ToString('o')
Check (-not (Test-GatewayRecoveryGrace $session 3)) 'stale heartbeat cannot hold settings indefinitely'
$script:life.updatedAt=[DateTimeOffset]::UtcNow.ToString('o');$session.SupervisorStart='1'
Check (-not (Test-GatewayRecoveryGrace $session 3)) 'PID reuse cannot extend restart grace'
$warnings=@(Get-EntryLifecycleWarnings $system $environment @([pscustomobject]@{Key='gateway';Ready=$false}))
Check (($warnings -join ' ') -match '未监听.*仍指向') 'dead entry still referenced by Windows and environment is diagnosed'
Check (($warnings -join ' ') -match '缓存.*完整重开') 'cached application proxy receives an actionable relaunch instruction'
$script:life.phase='ready';$script:listenerReads=0;$script:statusReads=0
function Get-Listener {param($Profile,[switch]$ProbeRemote);$script:listenerReads++;if($script:listenerReads -ge 3){[pscustomobject]@{PID=999}}}
function Invoke-AppRouter($InputObject){$script:statusReads++;[pscustomobject]@{available=$true;defaultLoaded=$true;effectiveDefaultRoute='upstream'}}
Wait-ManagedProxyReady gateway 1500
Check ($script:listenerReads -ge 3 -and $script:statusReads -gt 0) 'managed startup waits for late entry and checks controller route'
function Invoke-AppRouter($InputObject){[pscustomobject]@{available=$true;defaultLoaded=$true;effectiveDefaultRoute='Blocked'}}
$failed=$false;try{Wait-ManagedProxyReady gateway 250}catch{$failed=$_.Exception.Message -match '未启动应用'}
Check $failed 'all-upstream failure rejects managed launch despite listening port'
$script:life.phase='failed';$failed=$false;try{Wait-ManagedProxyReady gateway 250}catch{$failed=$true}
Check $failed 'exhausted core restart rejects managed launch'
$diag=ConvertTo-LoginDiagnostic $false http 7 0 0
Check ($diag.Stage -eq 'local-entry' -and -not $diag.AuthenticationVerified) 'connection refusal is local entry failure, not Google authentication'
$diag=ConvertTo-LoginDiagnostic $true http 56 502 0
Check ($diag.Stage -eq 'proxy-handshake' -and -not $diag.HandshakeReady) 'listening but bad HTTP CONNECT is handshake failure'
$diag=ConvertTo-LoginDiagnostic $true http 60 200 0
Check ($diag.Stage -eq 'target-https' -and $diag.HandshakeReady -and -not $diag.HttpsReachable) 'TLS certificate failure is separate from successful CONNECT'
$diag=ConvertTo-LoginDiagnostic $true http 0 200 404
Check ($diag.HttpsReachable -and $diag.HttpCode -eq 404 -and -not $diag.AuthenticationVerified) 'Google 404 proves HTTPS response only, never successful login'
$diag=ConvertTo-LoginDiagnostic $true socks5 0 0 401
Check ($diag.HttpsReachable -and -not $diag.AuthenticationVerified) 'SOCKS HTTPS 401 is reachable but authentication unverified'
$diag=ConvertTo-LoginDiagnostic $true http -1 0 0
Check (-not $diag.HttpsReachable) 'missing probe tool cannot report healthy'
Write-LifecycleEvent 'diagnostic' 'token=https://private.invalid'
$log=Get-Content -LiteralPath (Join-Path $script:DataRoot 'gateway\lifecycle-session.jsonl') -Raw
Check ($log -notmatch 'private.invalid|token=') 'lifecycle logger refuses unstructured private data'
Write-Output ('PASS: '+$script:checks+' lifecycle protection and login diagnostic checks; no real network writes or credentials.')
