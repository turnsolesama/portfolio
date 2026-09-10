[CmdletBinding()]
param(
    [switch]$Status,
    [switch]$Discover,
    [switch]$ConfigureGateway,
    [switch]$Independent,
    [switch]$RecoverNetwork,
    [int]$OwnerPID=0,
    [string]$Check,
    [string]$Switch,
    [switch]$Restore,
    [switch]$AppStatus,
    [string]$Program,
    [string]$AppRoute,
    [switch]$SmokeTest,
    [string]$PreviewPath,
    [switch]$PreviewMenu,
    [switch]$Demo,
    [ValidateSet('Programs','Tools','Settings','Proxies')][string]$PreviewView='Programs',
    [string]$ExportReport,
    [string]$DataDirectory='',
    [string]$LaunchProgram='',
    [switch]$NoUI
)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProxyBackend.ps1') -DataDirectory $DataDirectory
if($LaunchProgram){
    $launchAttempt=[ordered]@{Time=(Get-Date).ToString('o');Version=$script:ProductVersion;EntryPoint=$PSCommandPath;RequestedProgram=$LaunchProgram;DataDirectory=$script:DataRoot;PID=$PID;Outcome='starting'}
    try{
        $result=Start-ManagedProgram $LaunchProgram
        $launchAttempt.Outcome='started';$launchAttempt.ApplicationPID=$result.PID
        try{Write-LocalJson (Join-Path $script:DataRoot 'last-program-launch.json') $launchAttempt}catch{}
    }catch{
        $launchAttempt.Outcome='failed';$launchAttempt.Error=$_.Exception.Message
        try{Write-LocalJson (Join-Path $script:DataRoot 'last-program-launch.json') $launchAttempt}catch{}
        $launchNotice=$launchAttempt.Error+"`r`n`r`n"+'程序：'+[IO.Path]::GetFileNameWithoutExtension($LaunchProgram)
        Add-Type -AssemblyName System.Windows.Forms;[void][Windows.Forms.MessageBox]::Show($launchNotice,'程序代理启动','OK','Warning')
    }
    return
}
if($NoUI){return}
if($Independent){Enable-IndependentGateway $OwnerPID | ConvertTo-Json -Depth 6;return}
if($RecoverNetwork){Restore-IndependentSession;return}
if($ConfigureGateway){Enable-LocalGateway | ConvertTo-Json -Depth 5;return}
if($Discover){Sync-LocalProxyDiscovery | ConvertTo-Json -Depth 5;return}
if($ExportReport){Write-LocalJson ([IO.Path]::GetFullPath($ExportReport)) (New-SupportReport (Get-ProxyStatus) (Get-ApplicationRoutes));Write-Output 'Diagnostic summary exported.';return}
if($AppStatus){Get-ApplicationRoutes | ConvertTo-Json -Depth 8;return}
if($AppRoute){Set-ApplicationRoute $Program $AppRoute | ConvertTo-Json -Depth 8;return}
if($Status){Get-ProxyStatus | ConvertTo-Json -Depth 8;return}
if($Check){Test-ProxyRoute $Check | ConvertTo-Json -Depth 6;return}
if($Switch){Set-SelectedProxy $Switch | ConvertTo-Json -Depth 6;return}
if($Restore){Restore-ProxyBackup | ConvertTo-Json -Depth 6;return}
& (Join-Path $PSScriptRoot 'ProxyWindow.ps1') -DataDirectory $script:DataRoot -PreviewPath $PreviewPath -SmokeTest:$SmokeTest -PreviewMenu:$PreviewMenu -Demo:$Demo -PreviewView $PreviewView
