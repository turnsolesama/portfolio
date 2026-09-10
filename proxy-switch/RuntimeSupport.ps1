$script:RuntimeAppRoot=$PSScriptRoot
function Get-NodeRuntimePath {
    $owned=Join-Path $script:DataRoot 'gateway\runtime\node.exe'
    if($script:Profiles.Routing.Adapter -eq 'standalone' -and (Test-Path -LiteralPath $owned -PathType Leaf)){return $owned}
    $bundled=Join-Path $script:RuntimeAppRoot 'runtime\node.exe'
    if(Test-Path -LiteralPath $bundled -PathType Leaf){return $bundled}
    $installed=Get-Command node.exe -ErrorAction SilentlyContinue
    if($installed){return $installed.Source}
    throw '运行组件不完整，请重新完整解压 FlowSwitch 程序包。源码运行需准备 Node.js 22+。'
}
function Get-SystemCurlPath {
    $bundledWithWindows=Join-Path $env:SystemRoot 'System32\curl.exe'
    if(Test-Path -LiteralPath $bundledWithWindows -PathType Leaf){return $bundledWithWindows}
    $installed=Get-Command curl.exe -ErrorAction SilentlyContinue
    if($installed){return $installed.Source}
    throw '找不到 Windows 的网络检测组件 curl.exe。请使用 Windows 10 1809 或更新版本，并检查系统组件完整性。'
}
function Test-CoreRuntimeCompatible([string]$Path) {
    $info=New-Object Diagnostics.ProcessStartInfo
    $info.FileName=$Path;$info.Arguments='-v';$info.UseShellExecute=$false;$info.CreateNoWindow=$true
    $info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    $process=[Diagnostics.Process]::Start($info)
    try{
        $out=$process.StandardOutput.ReadToEndAsync();$err=$process.StandardError.ReadToEndAsync()
        if(-not $process.WaitForExit(5000)){$process.Kill();throw '内核启动检查超时，请检查程序文件是否受到系统拦截。'}
        if($process.ExitCode -eq 0){return $true}
        if(($out.Result+$err.Result) -match 'AMD64 processors with v[234] microarchitecture support'){return $false}
        throw '内核启动检查失败，请检查程序文件完整性和 Windows 支持版本。'
    }finally{$process.Dispose()}
}
function Get-IndependentCoreSource($Settings) {
    $owned=Join-Path $script:DataRoot 'gateway\runtime\FlowSwitch.Core.exe'
    if(Test-Path -LiteralPath $owned -PathType Leaf){return $owned}
    $bundled=Join-Path $script:RuntimeAppRoot 'runtime\FlowSwitch.Core.exe'
    if(Test-Path -LiteralPath $bundled -PathType Leaf){
        if(Test-CoreRuntimeCompatible $bundled){return $bundled}
        $compatible=Join-Path $script:RuntimeAppRoot 'runtime\FlowSwitch.Core.Compat.exe'
        if((Test-Path -LiteralPath $compatible -PathType Leaf) -and (Test-CoreRuntimeCompatible $compatible)){return $compatible}
        throw '这台电脑需要兼容内核，请重新完整解压包含兼容组件的程序包。'
    }
    $configured=@($Settings.Profiles | ForEach-Object CorePath | Where-Object {$_ -and [IO.Path]::GetFileName($_) -match '(mihomo|FlowSwitch.Core)' -and (Test-Path -LiteralPath $_ -PathType Leaf)}) | Select-Object -First 1
    if($configured){return $configured}
    $client=Get-ProcessInventory | Where-Object {$_.ProcessName -eq 'clash-verge' -and $_.Path} | Select-Object -First 1
    if($client){$path=Join-Path ([IO.Path]::GetDirectoryName($client.Path)) 'verge-mihomo.exe';if(Test-Path -LiteralPath $path -PathType Leaf){return $path}}
    throw '分流内核不完整，请重新完整解压 FlowSwitch 程序包。源码运行需另行提供 mihomo 内核。'
}
