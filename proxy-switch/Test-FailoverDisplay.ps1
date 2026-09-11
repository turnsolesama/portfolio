$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Windows.Forms
. (Join-Path $PSScriptRoot 'ApplicationObservation.ps1')
$tokens=$null;$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot 'ProxyWindow.ps1'),[ref]$tokens,[ref]$errors)
if($errors){throw 'UI parse failed'}
$function=$ast.Find({param($a) $a -is [Management.Automation.Language.FunctionDefinitionAst] -and $a.Name -eq 'Show-Applications'},$true)
Invoke-Expression $function.Extent.Text
$script:Profiles=[pscustomobject]@{Routing=[pscustomobject]@{Adapter='standalone'};Profiles=@()}
$script:LastState=[pscustomobject]@{Key='gateway'};$script:MenuOpen=$false;$script:Log=@()
function Get-RouteName($Key){[string]$Key}
function Get-GatewayKey {'gateway'}
function Get-ProfileKeys {@('a','b','gateway')}
function Select-ApplicationRows {param($Rows,$Search,$Saved);@()}
function Write-Activity($Message){$script:Log+=@($Message)}
$liveList=New-Object Windows.Forms.ListView;$searchBox=New-Object Windows.Forms.TextBox;$savedOnly=New-Object Windows.Forms.CheckBox
$controls=@($liveList,$searchBox,$savedOnly)
foreach($name in @('emptyLabel','countLabel','ruleValue','ruleMeta','programHint','noticeLabel')){$control=New-Object Windows.Forms.Label;Set-Variable -Name $name -Value $control;$controls+=@($control)}
$ink=[Drawing.Color]::White;$muted=[Drawing.Color]::Gray
$checks=0
function Check($Value,$Message){if(-not $Value){throw $Message};$script:checks++}
try{
    $apps='{"Available":true,"DefaultRoute":"a","EffectiveDefaultRoute":"b","DefaultLoaded":true,"RuleCount":0,"Rows":[],"Failover":{"details":{},"events":[{"id":"event-1","at":"2026-09-10T00:00:00Z","from":"a","to":"b","reason":"listener-closed"}]}}' | ConvertFrom-Json
    $apps.Failover | Add-Member updated ([DateTimeOffset]::UtcNow.ToString('o'))
    Show-Applications $apps
    Check ($ruleMeta.Text -match 'a' -and $ruleMeta.Text -match 'b') 'Requested and effective route are not both visible'
    Check ($noticeLabel.Text -match 'a.*b' -and $script:Log.Count -eq 1) 'Fallback reason and active backup are not visible'
    Show-Applications $apps
    Check ($script:Log.Count -eq 1) 'A status refresh repeated the same failover event'
    $apps.EffectiveDefaultRoute='Blocked';Show-Applications $apps
    Check ($noticeLabel.Text -match '暂停') 'Blocked state was reported as a working route'
    $apps.Failover.updated=[DateTimeOffset]::UtcNow.AddSeconds(-40).ToString('o');Show-Applications $apps
    Check ($noticeLabel.Text -match '未更新') 'Stale health was presented as current'
    $apps.Failover.updated=[DateTimeOffset]::UtcNow.ToString('o');$apps.Failover.details='{"a":{"healthy":null,"reason":"probe-unavailable"}}' | ConvertFrom-Json
    Show-Applications $apps
    Check ($noticeLabel.Text -match '未完成') 'Probe failure was hidden'
    Write-Output ('PASS: '+$checks+' failover display checks; real controls, no live app or network changes.')
}finally{foreach($control in $controls){$control.Dispose()}}
