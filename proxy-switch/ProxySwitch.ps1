[CmdletBinding()]
param(
    [switch]$Status,
    [switch]$LoginDiagnostic,
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
try {
    . (Join-Path $PSScriptRoot 'ProxyBackend.ps1') -DataDirectory $DataDirectory
} catch {
    # Initialization can fail before storage and logging helpers are available.
    # Never include raw JSON, command arguments or exception text in this record.
    $notice='流向无法加载配置或运行组件，目标程序尚未启动。错误代码：backend-initialization。请检查配置文件及程序包完整性；原配置和账号数据未被重置。'
    $failure=[ordered]@{Time=[DateTimeOffset]::UtcNow.ToString('o');Outcome='failed';Stage='initialization';ErrorCode='backend-initialization';ErrorType=$_.Exception.GetType().Name}
    $failureRoot=$DataDirectory
    if(-not $failureRoot){$failureRoot=$env:PROXY_SWITCH_DATA_DIR}
    if(-not $failureRoot){$failureRoot=Join-Path ([Environment]::GetFolderPath('UserProfile')) '.proxyswitch'}
    try{
        if([IO.Path]::IsPathRooted($failureRoot) -and [IO.Directory]::Exists($failureRoot)){
            $failurePath=Join-Path $failureRoot 'last-startup-failure.json'
            [IO.File]::WriteAllText($failurePath,($failure|ConvertTo-Json),(New-Object Text.UTF8Encoding($false)))
            $notice+="`r`n本地报告："+$failurePath
        }
    }catch{}
    if(-not $NoUI -and -not ($Status -or $Check -or $Switch -or $AppStatus -or $ExportReport -or $SmokeTest -or $Independent -or $RecoverNetwork -or $ConfigureGateway -or $Discover -or $AppRoute -or $LoginDiagnostic -or $Restore)){
        try{Add-Type -AssemblyName System.Windows.Forms;[void][Windows.Forms.MessageBox]::Show($notice,'流向启动失败','OK','Error')}catch{}
    }
    Write-Error $notice -ErrorAction Continue
    exit 1
}
if($LaunchProgram -and -not $NoUI){
    # Keep gateway ownership in the resident UI instead of a short lived launcher.
    & (Join-Path $PSScriptRoot 'ProxyWindow.ps1') -DataDirectory $script:DataRoot -InitialLaunchProgram $LaunchProgram
    return
}
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
        if($NoUI){Write-Error $launchNotice -ErrorAction Continue;exit 1}
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
if($LoginDiagnostic){Test-LoginChain $Check | ConvertTo-Json -Depth 6;return}
if($Status){Get-ProxyStatus | ConvertTo-Json -Depth 8;return}
if($Check){Test-ProxyRoute $Check | ConvertTo-Json -Depth 6;return}
if($Switch){Set-SelectedProxy $Switch | ConvertTo-Json -Depth 6;return}
if($Restore){Restore-ProxyBackup | ConvertTo-Json -Depth 6;return}
& (Join-Path $PSScriptRoot 'ProxyWindow.ps1') -DataDirectory $script:DataRoot -PreviewPath $PreviewPath -SmokeTest:$SmokeTest -PreviewMenu:$PreviewMenu -Demo:$Demo -PreviewView $PreviewView
