$ErrorActionPreference='Stop'
$qa=Join-Path $env:TEMP ('FlowSwitch-managed-removal-'+[Guid]::NewGuid().ToString('N'))
$env:PROXY_SWITCH_DATA_DIR=Join-Path $qa 'initial'
. (Join-Path $PSScriptRoot 'ProxyBackend.ps1')
. (Join-Path $PSScriptRoot 'ProgramFamilyTracking.ps1')
$script:Pass=0
function Check($Value,[string]$Message){if(-not $Value){throw $Message};$script:Pass++}
function Use-ChangeLock([scriptblock]$Action){& $Action}
function Set-SystemSnapshot {throw 'No real Windows proxy writes are permitted'}
function Set-UserProxyEnv {throw 'No real Windows environment writes are permitted'}
function Start-ManagedProgram {throw 'No user application launches are permitted'}
function Get-ProcessInventory {if($script:ProcessesFail){throw 'simulated process query failure'};@($script:Processes)}
$realTcp=${function:Get-TcpObservationSnapshot}
function Get-NetTCPConnection {throw 'simulated unavailable TCP inventory'}
function Get-TcpObservationSnapshot {if($script:RealTcpFailure){return & $realTcp};[pscustomobject]@{Available=$script:TcpAvailable;Rows=@($script:TcpRows)}}
function Invoke-AppRouter($Request){
    if($Request.action -eq 'status'){
        if($script:ControllerFails){throw 'simulated unavailable controller'}
        return [pscustomobject]@{available=$true;rulesAvailable=$true;mode='rule';connectionsAvailable=$script:ConnectionsAvailable;connections=@($script:Connections)}
    }
    if($Request.action -ne 'replace'){throw 'Unexpected engine operation'}
    $script:ReplaceCalls++
    if($script:RejectRace){throw 'Fixed entrance became active under the engine writer lock'}
    $file=Read-RuleMaintenanceFile (Join-Path $script:DataRoot 'app-rules.json');$settings=Read-RuleMaintenanceFile $script:ConfigPath
    if($Request.expectedStateHash -cne $file.TextHash -or $Request.expectedSettingsHash -cne $settings.TextHash){throw 'Expected exact conditional engine state'}
    $next=[pscustomobject]@{version=3;installed=$true;entries=@($Request.entries);defaultRoute=$Request.defaultRoute;programIngresses=@($Request.programIngresses);siteRules=@($Request.siteRules)}
    Write-LocalJson $file.Path $next
    [pscustomobject]@{stateHash=(Read-RuleMaintenanceFile $file.Path).TextHash}
}
function New-Case([string]$Name){
    $root=Join-Path $qa $Name;$script:DataRoot=Join-Path $root 'data';$script:ConfigPath=Join-Path $script:DataRoot 'config.json';$script:BackupDir=Join-Path $script:DataRoot 'backups';$script:Desktop=Join-Path $root 'desktop'
    [void][IO.Directory]::CreateDirectory($script:DataRoot);[void][IO.Directory]::CreateDirectory($script:Desktop)
    $script:App=Join-Path $root 'IDE.exe';$script:Child=Join-Path $root 'worker.exe'
    foreach($file in @($script:App,$script:Child)){[IO.File]::WriteAllText($file,'inert executable identity fixture')}
    $script:Profiles=ConvertTo-ValidProfileSettings ([pscustomobject]@{Version=3;Profiles=@(
        @{Id='gateway';Name='Gateway';Protocol='http';Host='127.0.0.1';Port=18790;CorePath='C:\Fixture\core.exe'},
        @{Id='b';Name='B';Protocol='http';Host='127.0.0.1';Port=18792}
    );Routing=@{Adapter='standalone';ProfileId='gateway';UnifiedMode='gateway'}})
    Write-LocalJson $script:ConfigPath $script:Profiles
    $script:Ingress=[pscustomobject]@{id='1234567890abcdef1234567890abcdef';path=$script:App;port=19080;route='b';identity=(Get-ProgramIdentityDescriptor $script:App (New-ProgramIdentityContext -Packages @()))}
    Write-LocalJson (Join-Path $script:DataRoot 'app-rules.json') @{version=3;installed=$true;entries=@();defaultRoute='b';programIngresses=@($script:Ingress);siteRules=@()}
    $script:Shortcut=Join-Path $script:Desktop 'IDE.lnk'
    $shell=New-Object -ComObject WScript.Shell
    try{$link=$shell.CreateShortcut($script:Shortcut);try{$link.TargetPath=$script:App;$link.Save()}finally{[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($link)}}finally{[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell)}
    $script:OriginalShortcutHash=(Get-FileHash -LiteralPath $script:Shortcut).Hash
    Install-ProgramProxyShortcut $script:App $script:Desktop|Out-Null
    $script:Processes=@();$script:ProcessesFail=$false;$script:Connections=@();$script:ConnectionsAvailable=$true;$script:ControllerFails=$false;$script:TcpRows=@();$script:TcpAvailable=$true;$script:RealTcpFailure=$false;$script:RejectRace=$false;$script:ReplaceCalls=0
}
function Refuses([string]$Pattern){
    $before=Get-RuleMaintenanceSnapshot $script:App;$calls=$script:ReplaceCalls;$message=''
    try{Remove-SavedProgramRule $script:App|Out-Null}catch{$message=$_.Exception.Message}
    Check ($message -match $Pattern) ('Expected refusal '+$Pattern+', got '+$message)
    Check ((Get-RuleMaintenanceSnapshot $script:App).Fingerprint -ceq $before.Fingerprint -and $script:ReplaceCalls -eq $calls) 'Refusal leaves ingress state and shortcut bytes unchanged without a replacement request'
}
function Tcp([int]$RemotePort=19080,[string]$State='Established',[string]$RemoteAddress='127.0.0.1',[int]$LocalPort=51000){
    [pscustomobject]@{OwningProcess=456;LocalAddress='127.0.0.1';LocalPort=$LocalPort;RemoteAddress=$RemoteAddress;RemotePort=$RemotePort;State=$State}
}
New-Case 'orphan-controller-id'
$script:Connections=@([pscustomobject]@{ingressId=$script:Ingress.id;inboundName='';path=$script:Child})
Refuses '活动连接'
New-Case 'orphan-controller-inbound'
$script:Connections=@([pscustomobject]@{ingressId='';inboundName=('FS-Program-'+$script:Ingress.id);path=''})
Refuses '活动连接'
New-Case 'controller-unknown'
$script:ConnectionsAvailable=$false
Refuses '状态未知'
New-Case 'controller-failed'
$script:ControllerFails=$true
Refuses '连接读取失败'
New-Case 'tcp-established'
$script:TcpRows=@((Tcp))
Refuses '活动或正在建立'
New-Case 'tcp-synsent'
$script:TcpRows=@((Tcp -State 'SynSent'))
Refuses '活动或正在建立'
New-Case 'tcp-v4-mapped'
$script:TcpRows=@((Tcp -RemoteAddress '::ffff:127.0.0.1'))
Refuses '活动或正在建立'
New-Case 'tcp-server-side'
$script:TcpRows=@((Tcp -RemotePort 52000 -LocalPort 19080))
Refuses '活动或正在建立'
New-Case 'tcp-unknown'
$script:TcpAvailable=$false
Refuses 'TCP.*未知'
New-Case 'tcp-query-error'
$script:RealTcpFailure=$true
Refuses 'TCP.*未知'
New-Case 'process-query-error'
$script:ProcessesFail=$true
Refuses '进程身份读取失败'
New-Case 'identity-unknown'
$birth=[DateTime]::UtcNow.AddMinutes(-1)
$rootProcess=[pscustomobject]@{Id=10;ParentId=1;Path=$script:App;PathStatus='Available';StartTime=$birth}
$workerProcess=[pscustomobject]@{Id=11;ParentId=10;Path=$script:Child;PathStatus='Available';StartTime=$birth.AddSeconds(1)}
Get-ProgramFamily $script:App @($rootProcess,$workerProcess)|Out-Null
$unknownWorker=$workerProcess.PSObject.Copy();$unknownWorker.Path='';$unknownWorker.PathStatus='AccessDenied';$unknownWorker.StartTime=[DateTime]::MinValue
$script:Processes=@($unknownWorker)
Refuses '身份不可读'
New-Case 'known-living-worker'
$rootProcess.Path=$script:App;$workerProcess.Path=$script:Child
Get-ProgramFamily $script:App @($rootProcess,$workerProcess)|Out-Null
$script:Processes=@($workerProcess)
Refuses '仍在运行'
New-Case 'website-reference'
$state=Get-Content -LiteralPath (Join-Path $script:DataRoot 'app-rules.json') -Raw|ConvertFrom-Json
$state.siteRules=@(@{id='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';scope=$script:Ingress.id;type='domain';domain='example.com';route='Direct'})
Write-LocalJson (Join-Path $script:DataRoot 'app-rules.json') $state
Refuses '网站例外'
New-Case 'idle-remove'
$script:TcpRows=@((Tcp -State 'Listen' -RemotePort 0 -LocalPort 19080),(Tcp -State 'TimeWait'))
$result=Remove-SavedProgramRule $script:App
Check ($result.Removed -and @((Get-RoutingSnapshot).programIngresses).Count -eq 0 -and $script:ReplaceCalls -eq 1) 'No active clients permits conditional removal of the saved stable ingress'
Check ((Get-FileHash -LiteralPath $script:Shortcut).Hash -eq $script:OriginalShortcutHash) 'An idle removal restores the still-owned native shortcut byte for byte'
New-Case 'external-shortcut'
$shell=New-Object -ComObject WScript.Shell
try{$link=$shell.CreateShortcut($script:Shortcut);try{$link.Arguments='-NoProfile -UserChoice';$link.Save()}finally{[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($link)}}finally{[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell)}
$externalHash=(Get-FileHash -LiteralPath $script:Shortcut).Hash
$result=Remove-SavedProgramRule $script:App
Check ($result.Removed -and $result.PreservedShortcuts -eq 1 -and (Get-FileHash -LiteralPath $script:Shortcut).Hash -eq $externalHash) 'An idle removal preserves a shortcut independently edited by the user'
New-Case 'connection-arrives-at-engine-lock'
$script:RejectRace=$true;$before=Get-RuleMaintenanceSnapshot $script:App;$failure=''
try{Remove-SavedProgramRule $script:App|Out-Null}catch{$failure=$_.Exception.Message}
Check ($failure -match 'became active' -and (Get-RuleMaintenanceSnapshot $script:App).Fingerprint -ceq $before.Fingerprint) 'Engine-lock refusal after the preflight leaves the original entry and shortcut intact'
Write-Output ('PASS: '+$script:Pass+' managed removal checks; isolated state and real temporary shortcuts, with unavailable and orphan-client evidence fixtures.')
