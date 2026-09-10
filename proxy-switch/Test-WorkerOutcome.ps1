$ErrorActionPreference='Stop'
$script:Pass=0
function Check($Value,[string]$Message){if(-not $Value){throw $Message};$script:Pass++}
$qa=Join-Path $env:TEMP ('FlowSwitch-worker-outcome-'+[Guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($qa)
# Execute the actual background worker with an isolated backend, not a copied implementation.
$tokens=$null;$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot 'ProxyWindow.ps1'),[ref]$tokens,[ref]$errors)
if($errors){throw 'Window source failed parsing'}
$matches=@($ast.FindAll({param($node)
    $node -is [Management.Automation.Language.AssignmentStatementAst] -and $node.Left.Extent.Text -eq '$code' -and $node.Right.Extent.Text -match 'param\(\$Root,\$Kind'
},$true))
Check ($matches.Count -eq 1) 'A single actual UI background worker is selected'
$source=$matches[0].Right.Extent.Text
$worker=[scriptblock]::Create($source.Substring(1,$source.Length-2))
$backend=@'
$script:Profiles=[pscustomobject]@{Version=3;Profiles=@();Routing=@{Adapter='none'}}
function Set-SelectedProxy {
    param($Key)
    if($Key -eq 'fail-before'){throw 'fixture operation rejected before writing'}
    $script:MutationCount++
    [pscustomobject]@{Message='fixture switch completed';Backup='fixture-backup';Route=$Key}
}
function Invoke-ApplicationReconnect {
    param($Plan)
    $script:ReconnectCount++
    [pscustomobject]@{ok=$false;closed=1;failed=1;Message='fixture: one connection closed, one failed'}
}
function Get-TcpObservationSnapshot {
    if(-not $script:DisplayWorks){throw 'fixture display snapshot unavailable'}
    [pscustomobject]@{Rows=@();Available=$true}
}
function Get-ApplicationRoutes {param($TcpRows,$TcpAvailable) [pscustomobject]@{Available=$false;Rows=@();TcpAvailable=$TcpAvailable}}
function Get-ProxyStatus {param($Apps,$TcpRows,$TcpAvailable) [pscustomobject]@{Key='fixture';TcpAvailable=$TcpAvailable}}
'@
[IO.File]::WriteAllText((Join-Path $qa 'ProxyBackend.ps1'),$backend,(New-Object Text.UTF8Encoding($true)))
$script:MutationCount=0;$script:ReconnectCount=0;$script:DisplayWorks=$false
function Run-Worker([string]$Kind,[string]$Key){
    $queue=New-Object 'System.Collections.Concurrent.ConcurrentQueue[string]'
    & $worker $qa $Kind $Key $qa $false $false @() $queue ([Threading.CancellationToken]::None)
}
$reply=Run-Worker 'Switch' 'upstream'
Check ($script:MutationCount -eq 1 -and $reply.OK -and $reply.Result.Backup -eq 'fixture-backup' -and $reply.Result.Message -eq 'fixture switch completed') 'A successful switch retains its result and rollback backup when display refresh fails'
Check ($reply.RefreshError -and $null -eq $reply.State -and $null -eq $reply.Apps) 'Failed post-operation observation is explicitly stale instead of inventing current status'
$reply=Run-Worker 'AppReconnect' '{}'
Check ($script:ReconnectCount -eq 1 -and $reply.OK -and -not $reply.Result.ok -and $reply.Result.closed -eq 1 -and $reply.Result.failed -eq 1 -and $reply.RefreshError) 'Partial reconnection evidence survives a subsequent display failure without becoming complete success'
$reply=Run-Worker 'Switch' 'fail-before'
Check (-not $reply.OK -and $reply.Error -match 'operation rejected' -and $script:MutationCount -eq 1) 'An actual operation failure is still reported as failure without implying writes succeeded'
$reply=Run-Worker 'Status' ''
Check (-not $reply.OK -and $reply.Error -match 'snapshot unavailable') 'A plain status failure cannot borrow an unrelated successful mutation result'
$script:DisplayWorks=$true
$reply=Run-Worker 'Switch' 'upstream'
Check ($reply.OK -and -not $reply.RefreshError -and $reply.State.Key -eq 'fixture' -and $reply.Result.Backup -eq 'fixture-backup') 'A successful operation with a successful refresh returns both current evidence and its result'
Write-Output ('PASS: '+$script:Pass+' worker outcome assertions; actual worker AST with isolated backend only.')
