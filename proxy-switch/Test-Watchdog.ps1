$ErrorActionPreference='Stop'
$qa=Join-Path $env:TEMP ('FlowSwitch-Watchdog-'+[Guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($qa)
$utf8=New-Object Text.UTF8Encoding($true)
$source='using System.Threading;class Fixture{static void Main(){Thread.Sleep(60000);}}'
$cs=Join-Path $qa 'Owner.cs';$exe=Join-Path $qa 'Owner.exe';[IO.File]::WriteAllText($cs,$source)
& (Join-Path $env:SystemRoot 'Microsoft.NET\Framework64\v4.0.30319\csc.exe') /nologo /target:winexe ('/out:'+$exe) $cs
if($LASTEXITCODE -ne 0){throw 'Fixture compile failed'}
$body=[IO.File]::ReadAllText((Join-Path $PSScriptRoot 'GatewayWatchdog.ps1'))
$body=$body.Substring($body.IndexOf('$path=Get-IndependentSessionPath'))
$mock=@'
function Get-SystemSnapshot {Get-Content (Join-Path $script:DataRoot 'fake-system.json') -Raw|ConvertFrom-Json}
function Get-UserProxyEnv {Get-Content (Join-Path $script:DataRoot 'fake-env.json') -Raw|ConvertFrom-Json}
function Set-SystemSnapshot($v){Write-LocalJson (Join-Path $script:DataRoot 'fake-system.json') $v}
function Set-UserProxyEnv($v){Write-LocalJson (Join-Path $script:DataRoot 'fake-env.json') $v}
function Remove-ItemProperty {param($LiteralPath,$Name,$ErrorAction)}
function Get-ItemPropertyValue {param($LiteralPath,$Name,$ErrorAction);throw 'No registration in isolated fixture'}
function Test-RecoveryEndpoint([string]$value){if($value -eq '127.0.0.1:18790'){return (Test-Path (Join-Path $script:DataRoot 'listener-ready'))};return $false}
'@
$shell=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$checks=0
foreach($case in @('owner-crash','core-crash','external-change')){
    $data=Join-Path $qa $case;[void][IO.Directory]::CreateDirectory((Join-Path $data 'gateway'))
    $owner=Start-Process -FilePath $exe -WindowStyle Hidden -PassThru
    $watch=$null
    try{
        $proxy=@{Flags=3;Server='127.0.0.1:18790';Bypass='localhost'};$direct=@{Flags=1;Server='';Bypass='localhost'}
        $targetEnv=@{HTTP_PROXY='http://127.0.0.1:18790';HTTPS_PROXY='http://127.0.0.1:18790';ALL_PROXY='http://127.0.0.1:18790';NO_PROXY='localhost'}
        $oldEnv=@{HTTP_PROXY=$null;HTTPS_PROXY=$null;ALL_PROXY=$null;NO_PROXY='localhost'}
        $session=@{OwnerPID=$owner.Id;OwnerStart=$owner.StartTime.ToUniversalTime().Ticks.ToString();Started=[Guid]::NewGuid().ToString();BeforeSystem=$direct;TargetSystem=$proxy;BeforeEnv=$oldEnv;TargetEnv=$targetEnv}
        [IO.File]::WriteAllText((Join-Path $data 'gateway-session.json'),($session|ConvertTo-Json -Depth 5),$utf8)
        $system=$proxy;if($case -eq 'external-change'){$system=@{Flags=3;Server='127.0.0.1:20000';Bypass='external'}}
        [IO.File]::WriteAllText((Join-Path $data 'fake-system.json'),($system|ConvertTo-Json),$utf8)
        [IO.File]::WriteAllText((Join-Path $data 'fake-env.json'),($targetEnv|ConvertTo-Json),$utf8)
        [IO.File]::WriteAllText((Join-Path $data 'listener-ready'),'ready')
        $fixture=Join-Path $data 'Watch.ps1'
        $prefix='$ErrorActionPreference=''Stop'''+"`r`n"+('. '''+(Join-Path $PSScriptRoot 'ProxyBackend.ps1').Replace("'","''")+''' -DataDirectory '''+$data.Replace("'","''")+'''')+"`r`n"
        [IO.File]::WriteAllText($fixture,($prefix+$mock+"`r`n"+$body),$utf8)
        $watch=Start-Process -FilePath $shell -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File "'+$fixture+'"') -WindowStyle Hidden -PassThru
        $deadline=[DateTime]::Now.AddSeconds(10);while(-not (Test-Path (Join-Path $data 'gateway\watchdog-ready.json')) -and [DateTime]::Now -lt $deadline){Start-Sleep -Milliseconds 100}
        if(-not (Test-Path (Join-Path $data 'gateway\watchdog-ready.json'))){throw 'Watchdog did not become ready'}
        if($case -eq 'core-crash'){[IO.File]::Delete((Join-Path $data 'listener-ready'))}else{$owner.Kill()}
        if(-not $watch.WaitForExit(10000)){throw ('Watchdog did not recover '+$case)}
        $after=Get-Content (Join-Path $data 'fake-system.json') -Raw|ConvertFrom-Json
        if($case -eq 'external-change'){if($after.Server -ne '127.0.0.1:20000'){throw 'Overwrote external choice'}}elseif($after.Flags -ne 1 -or $after.Server){throw 'Dead proxy was left behind'}
        if((Test-Path (Join-Path $data 'gateway-session.json')) -or -not (Test-Path (Join-Path $data 'gateway\stop'))){throw 'Recovery order/journal failure'}
        $checks++;Write-Output ('PASS: watchdog '+$case)
    }finally{if($watch){if(-not $watch.HasExited){$watch.Kill()};$watch.Dispose()};if(-not $owner.HasExited){$owner.Kill()};$owner.Dispose()}
}
Write-Output ('PASS: '+$checks+' real watchdog process lifecycle checks with isolated Windows-setting stubs.')
