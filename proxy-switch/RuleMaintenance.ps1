# Explicit user actions only. Display refresh must never invoke these writers.
if(-not ('LocalProxySwitch.RuleFileExchange' -as [type])){
    Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using Microsoft.Win32.SafeHandles;
namespace LocalProxySwitch {
    public static class RuleFileExchange {
        [StructLayout(LayoutKind.Sequential)] struct Disposition { [MarshalAs(UnmanagedType.Bool)] public bool Delete; }
        [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern SafeFileHandle CreateFileW(string path,uint access,uint share,IntPtr security,uint creation,uint flags,IntPtr template);
        [DllImport("kernel32.dll",SetLastError=true)] static extern bool SetFileInformationByHandle(SafeFileHandle file,int kind,ref Disposition value,uint size);
        public static string Hash(byte[] bytes) {using(var sha=SHA256.Create())return BitConverter.ToString(sha.ComputeHash(bytes)).Replace("-","").ToLowerInvariant();}
        static void MarkDelete(FileStream stream){var value=new Disposition{Delete=true};if(!SetFileInformationByHandle(stream.SafeFileHandle,4,ref value,4))throw new IOException("Cannot safely remove the unchanged shortcut.");}
        public static void Apply(string path,string expectedHash,byte[] bytes,bool remove) {
            bool created=expectedHash=="<missing>";
            if(created&&remove){if(File.Exists(path))throw new IOException("File changed after the preview.");return;}
            // DELETE access allows a verified removal on this very handle, without reopening a raced path.
            using(var handle=CreateFileW(path,0xC0010000,0,IntPtr.Zero,created?1u:3u,0,IntPtr.Zero)) {
            if(handle.IsInvalid)throw new IOException("Cannot exclusively open the expected file ("+Marshal.GetLastWin32Error()+").");
            using(var file=new FileStream(handle,FileAccess.ReadWrite)) {
                byte[] before=new byte[file.Length];int offset=0;
                while(offset<before.Length){int count=file.Read(before,offset,before.Length-offset);if(count==0)throw new IOException("Incomplete file read.");offset+=count;}
                if(!created&&Hash(before)!=expectedHash)throw new IOException("File changed after the preview.");
                if(remove){MarkDelete(file);return;}
                try{file.Position=0;file.Write(bytes,0,bytes.Length);file.SetLength(bytes.Length);file.Flush(true);}
                catch{
                    // The exclusive handle still excludes outside writes while a partial write is undone.
                    if(created)MarkDelete(file);else{file.Position=0;file.Write(before,0,before.Length);file.SetLength(before.Length);file.Flush(true);}throw;
                }
            }
            }
        }
    }
}
'@
}
function Get-RuleMaintenanceHash([byte[]]$Bytes){[LocalProxySwitch.RuleFileExchange]::Hash($Bytes)}
function ConvertTo-RuleMaintenanceBytes($Value){[Text.Encoding]::UTF8.GetBytes(($Value|ConvertTo-Json -Depth 16))}
function Read-RuleMaintenanceFile([string]$Path){
    if(-not [IO.File]::Exists($Path)){return [pscustomobject]@{Path=$Path;Exists=$false;Bytes=[byte[]]@();Hash='<missing>';TextHash='<missing>'}}
    $bytes=[IO.File]::ReadAllBytes($Path);$text=[Text.Encoding]::UTF8.GetString($bytes).TrimStart([char]0xfeff)
    [pscustomobject]@{Path=$Path;Exists=$true;Bytes=$bytes;Hash=(Get-RuleMaintenanceHash $bytes);TextHash=(Get-RuleMaintenanceHash ([Text.Encoding]::UTF8.GetBytes($text)))}
}
function Read-RuleMaintenanceJson($Image,$Default){if(-not $Image.Exists){return $Default};try{[Text.Encoding]::UTF8.GetString($Image.Bytes).TrimStart([char]0xfeff)|ConvertFrom-Json}catch{throw '程序保存记录无法读取，请先检查或恢复备份。'}}
function Get-RuleMaintenanceSnapshot([string]$SavedPath){
    $files=@{};foreach($name in @('app-rules.json','program-proxies.json','program-shortcuts.json','config.json')){$files[$name]=Read-RuleMaintenanceFile (Join-Path $script:DataRoot $name)}
    $engine=Read-RuleMaintenanceJson $files['app-rules.json'] ([pscustomobject]@{version=2;installed=$false;entries=@();defaultRoute=$null})
    $launch=Read-RuleMaintenanceJson $files['program-proxies.json'] ([pscustomobject]@{version=1;entries=@()})
    $shortcuts=Read-RuleMaintenanceJson $files['program-shortcuts.json'] ([pscustomobject]@{version=1;entries=@()})
    if($engine.version -notin @(1,2) -or $launch.version -ne 1 -or $shortcuts.version -ne 1){throw '程序保存记录版本不兼容，未进行修改。'}
    $links=@{};foreach($entry in @($shortcuts.entries|Where-Object {$_.program -ieq $SavedPath})){
        $path=[string]$entry.shortcut;if(-not [IO.Path]::IsPathRooted($path) -or $path -notmatch '(?i)\.lnk$'){throw '快捷方式记录路径无效。'}
        $links[$path]=Read-RuleMaintenanceFile $path
    }
    $fingerprint=@();foreach($name in @($files.Keys|Sort-Object)){$fingerprint+=($name+'='+$files[$name].Hash)}
    foreach($path in @($links.Keys|Sort-Object)){$fingerprint+=($path.ToLowerInvariant()+'='+$links[$path].Hash)}
    [pscustomobject]@{Files=$files;Engine=$engine;Launch=$launch;Shortcuts=$shortcuts;Links=$links;Fingerprint=(Get-RuleMaintenanceHash ([Text.Encoding]::UTF8.GetBytes(($fingerprint -join "`n"))))}
}
function Get-RuleMaintenanceIdentityFingerprint($Resolution){
    $identity=$Resolution.Identity
    $value=[ordered]@{Path=[string]$Resolution.CurrentPath;Reason=[string]$Resolution.Reason;Confidence=[string]$Resolution.Confidence;FileId=[string]$identity.FileId;CanonicalPath=[string]$identity.CanonicalPath;PackageFamilyName=[string]$identity.PackageFamilyName;PackageFullName=[string]$identity.PackageFullName;RelativeExecutable=[string]$identity.RelativeExecutable}
    Get-RuleMaintenanceHash (ConvertTo-RuleMaintenanceBytes $value)
}
function Get-RuleMaintenanceProfiles($Snapshot){
    $value=Read-RuleMaintenanceJson $Snapshot.Files['config.json'] $null
    if($null -eq $value){$value=Get-Content -LiteralPath (Join-Path $script:Root 'config.defaults.json') -Raw -Encoding UTF8|ConvertFrom-Json}
    ConvertTo-ValidProfileSettings (Convert-LegacySettings $value)
}
function Get-ProgramRuleRepairPlan([string]$SavedPath){
    $path=ConvertTo-ProgramIdentityPath $SavedPath;if(-not $path -or $path -notmatch '(?i)\.exe$'){throw '请选择有效的已保存程序记录。'}
    $snapshot=Get-RuleMaintenanceSnapshot $path
    $engine=@($snapshot.Engine.entries|Where-Object {$_.path -ieq $path});$launch=@($snapshot.Launch.entries|Where-Object {$_.path -ieq $path})
    if(-not ($engine.Count+$launch.Count)){throw '该程序没有需要修复的保存记录。'}
    if($engine.Count -gt 1 -or $launch.Count -gt 1){throw '相同路径存在重复记录，请先移除冲突记录。'}
    $savedIdentity=$null;if($engine.Count){$savedIdentity=$engine[0].identity};if(-not $savedIdentity -and $launch.Count){$savedIdentity=$launch[0].identity}
    $processes=@(Get-ProcessInventory);$context=New-ProgramIdentityContext -Processes $processes -RefreshPackages
    $resolution=Resolve-ProgramIdentity $path -Processes $processes -Context $context -SavedIdentity $savedIdentity
    if(-not $resolution.CanRepair -or -not $resolution.RequiresRepair -or -not $resolution.CurrentPath){throw '没有唯一、可核对的新程序路径；请先解决路径不可读或多个候选的情况。'}
    if(@(@($snapshot.Engine.entries)+@($snapshot.Launch.entries)|Where-Object {$_.path -ine $path -and (Test-ProgramPathEquivalent $_.path $resolution.CurrentPath $context)}).Count){throw '新程序路径已经存在保存记录，请先处理冲突，未合并线路。'}
    if($launch.Count -and (Get-ProgramProxyAdapter $resolution.CurrentPath) -ne $launch[0].adapter){throw '新版本不再符合原启动代理适配方式，未迁移记录。'}
    $profiles=Get-RuleMaintenanceProfiles $snapshot
    foreach($profile in $profiles.Profiles){if((Test-ProgramPathEquivalent $resolution.CurrentPath $profile.AppPath $context) -or (Test-ProgramPathEquivalent $resolution.CurrentPath $profile.CorePath $context)){throw '不能把代理程序自身的路径作为修复目标。'}}
    $mode=$(if($engine.Count -and $launch.Count){'mixed'}elseif($engine.Count){'engine'}else{'launch'})
    $impact=$(if($engine.Count){'保留线路和默认出口，仅替换该程序路径并核对已运行引擎；新连接生效。'}else{'保留目标线路，更新仍归本工具的代理启动入口；已运行程序需要自行保存任务后重新打开。'})
    [pscustomobject]@{Version=1;DataDirectory=[IO.Path]::GetFullPath($script:DataRoot);SavedPath=$path;CurrentPath=$resolution.CurrentPath;Mode=$mode;CreatedAt=[DateTime]::UtcNow.ToString('o');SnapshotFingerprint=$snapshot.Fingerprint;IdentityFingerprint=(Get-RuleMaintenanceIdentityFingerprint $resolution);Identity=$resolution.Identity;Message=('将保存记录从 '+$path+' 修复为 '+$resolution.CurrentPath+'。');Impact=$impact}
}
function New-RuleMaintenanceBackup($Snapshot,[string]$Action,[string]$SavedPath,[string]$CurrentPath){
    $directory=Join-Path $script:DataRoot ('backups\program-maintenance\'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+[Guid]::NewGuid().ToString('N'))
    [void][IO.Directory]::CreateDirectory($directory);$records=@();$index=0
    foreach($image in @($Snapshot.Files.Values)+@($Snapshot.Links.Values)){
        $name=('{0:D3}.bin' -f $index++);if($image.Exists){[IO.File]::WriteAllBytes((Join-Path $directory $name),$image.Bytes)}
        $records+=@([pscustomobject]@{Path=$image.Path;Exists=$image.Exists;Hash=$image.Hash;BackupFile=$(if($image.Exists){$name}else{''})})
    }
    $manifest=Join-Path $directory 'record.json';Write-LocalJson $manifest ([pscustomobject]@{Version=1;Action=$Action;SavedPath=$SavedPath;CurrentPath=$CurrentPath;CreatedAt=[DateTime]::UtcNow.ToString('o');Files=$records})
    [pscustomobject]@{Directory=$directory;Path=$manifest}
}
function Get-RuleMaintenanceArguments([string]$Executable){
    '-NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File '+(ConvertTo-ProgramArgument (Join-Path $script:Root 'ProxySwitch.ps1'))+' -DataDirectory '+(ConvertTo-ProgramArgument $script:DataRoot)+' -LaunchProgram '+(ConvertTo-ProgramArgument $Executable)
}
function New-RuleMaintenanceShortcutChanges($Snapshot,[string]$SavedPath,[string]$CurrentPath,$Backup,[switch]$Remove){
    $changes=@();$records=@();$preserved=0;$restoredUpdated=0;$shell=New-Object -ComObject WScript.Shell
    try{
        foreach($entry in @($Snapshot.Shortcuts.entries)){
            if($entry.program -ine $SavedPath){$records+=@($entry);continue}
            $image=$Snapshot.Links[[string]$entry.shortcut];$owned=$false
            if($image.Exists){
                $link=$shell.CreateShortcut($entry.shortcut)
                try{$owned=$link.TargetPath -ieq $entry.managedTarget -and $link.Arguments -ceq $entry.managedArguments}finally{[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($link)}
            }
            $next=$entry|ConvertTo-Json -Depth 12|ConvertFrom-Json
            if(-not $Remove){$next.program=$CurrentPath;$next|Add-Member NoteProperty previousProgramPaths (@(@(Get-ProgramIdentityValue $entry 'previousProgramPaths' @())+@($SavedPath))|Select-Object -Unique) -Force}
            if($owned){
                if($Remove){
                    if($entry.originalBackup){
                        $original=Read-RuleMaintenanceFile ([string]$entry.originalBackup);if(-not $original.Exists){throw '原快捷方式备份已缺失，保留现有入口；请先检查备份。'}
                        $restoredBytes=$original.Bytes
                        # Keep the original backup immutable. A previously confirmed repair also records
                        # its old program path, so removing the proxy need not restore a dead versioned launcher.
                        if(@(Get-ProgramIdentityValue $entry 'previousProgramPaths' @()).Count -and [IO.File]::Exists($SavedPath)){
                            $stage=Join-Path $Backup.Directory ([Guid]::NewGuid().ToString('N')+'.lnk');[IO.File]::WriteAllBytes($stage,$original.Bytes)
                            $restored=$shell.CreateShortcut($stage)
                            try{
                                $oldTarget=[string]$restored.TargetPath
                                if($oldTarget -in @(Get-ProgramIdentityValue $entry 'previousProgramPaths' @()) -and -not [IO.File]::Exists($oldTarget)){
                                    $restored.TargetPath=$SavedPath
                                    if($restored.WorkingDirectory -ieq [IO.Path]::GetDirectoryName($oldTarget)){$restored.WorkingDirectory=[IO.Path]::GetDirectoryName($SavedPath)}
                                    if($restored.IconLocation.StartsWith($oldTarget+',',[StringComparison]::OrdinalIgnoreCase)){$restored.IconLocation=$SavedPath+$restored.IconLocation.Substring($oldTarget.Length)}
                                    $restored.Save();$restoredBytes=[IO.File]::ReadAllBytes($stage);$restoredUpdated++
                                }
                            }finally{[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($restored)}
                        }
                        $changes+=@([pscustomobject]@{Before=$image;Bytes=$restoredBytes;Remove=$false})
                    }else{$changes+=@([pscustomobject]@{Before=$image;Bytes=[byte[]]@();Remove=$true})}
                }else{
                    $stage=Join-Path $Backup.Directory ([Guid]::NewGuid().ToString('N')+'.lnk');[IO.File]::WriteAllBytes($stage,$image.Bytes)
                    $link=$shell.CreateShortcut($stage)
                    try{
                        $next.managedTarget=Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe';$next.managedArguments=Get-RuleMaintenanceArguments $CurrentPath
                        $link.TargetPath=$next.managedTarget;$link.Arguments=$next.managedArguments;$link.WorkingDirectory=[IO.Path]::GetDirectoryName($CurrentPath)
                        if($link.IconLocation.StartsWith($SavedPath+',',[StringComparison]::OrdinalIgnoreCase)){$link.IconLocation=$CurrentPath+$link.IconLocation.Substring($SavedPath.Length)}
                        $link.Save()
                    }finally{[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($link)}
                    $changes+=@([pscustomobject]@{Before=$image;Bytes=[IO.File]::ReadAllBytes($stage);Remove=$false})
                }
            }elseif($image.Exists){$preserved++}
            if(-not $Remove){$records+=@($next)}
        }
    }finally{[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell)}
    [pscustomobject]@{Changes=$changes;Records=$records;Preserved=$preserved;RestoredUpdated=$restoredUpdated}
}
function Set-RuleMaintenanceFile($Before,[byte[]]$Bytes,[bool]$Remove=$false){[LocalProxySwitch.RuleFileExchange]::Apply($Before.Path,$Before.Hash,$Bytes,$Remove)}
function Assert-RuleMaintenanceEngine($Snapshot){
    $live=Invoke-AppRouter @{action='status'}
    if(-not $live.available -or -not (Get-ProgramIdentityValue $live 'rulesAvailable' $false) -or $live.mode -ne 'rule'){throw '分流引擎尚未运行或规则无法核对；请先启动已配置引擎。此次操作不会启动引擎或切换系统代理。'}
    if((Read-RuleMaintenanceFile $Snapshot.Files['app-rules.json'].Path).Hash -cne $Snapshot.Files['app-rules.json'].Hash){throw '引擎检查期间保存记录发生变化，请重新预览。'}
}
function Invoke-RuleMaintenanceChange($Snapshot,[string]$SavedPath,[string]$CurrentPath,$Identity,[switch]$Remove){
    # Invoke-AppRouter exports this object; bind it to exactly the previewed configuration bytes.
    $script:Profiles=Get-RuleMaintenanceProfiles $Snapshot
    $engineEntries=@($Snapshot.Engine.entries|Where-Object {$_.path -ieq $SavedPath});$launchEntries=@($Snapshot.Launch.entries|Where-Object {$_.path -ieq $SavedPath})
    if($engineEntries.Count){Assert-RuleMaintenanceEngine $Snapshot}
    $backup=New-RuleMaintenanceBackup $Snapshot $(if($Remove){'remove'}else{'repair'}) $SavedPath $CurrentPath
    $shortcutPlan=New-RuleMaintenanceShortcutChanges $Snapshot $SavedPath $CurrentPath $backup -Remove:$Remove
    $nextLaunch=$Snapshot.Launch|ConvertTo-Json -Depth 16|ConvertFrom-Json;$nextEngine=@()
    foreach($entry in @($Snapshot.Engine.entries)){
        if($entry.path -ine $SavedPath){$nextEngine+=@($entry);continue};if($Remove){continue}
        $next=$entry|ConvertTo-Json -Depth 16|ConvertFrom-Json;$next.path=$CurrentPath;$next|Add-Member NoteProperty identity $Identity -Force;$nextEngine+=@($next)
    }
    $nextLaunch.entries=@(foreach($entry in @($Snapshot.Launch.entries)){
        if($entry.path -ine $SavedPath){$entry;continue};if($Remove){continue}
        $next=$entry|ConvertTo-Json -Depth 16|ConvertFrom-Json;$next.path=$CurrentPath;$next|Add-Member NoteProperty identity $Identity -Force;$next
    })
    $changes=@($shortcutPlan.Changes)
    if(@($Snapshot.Shortcuts.entries|Where-Object {$_.program -ieq $SavedPath}).Count){
        $nextShortcuts=$Snapshot.Shortcuts|ConvertTo-Json -Depth 16|ConvertFrom-Json;$nextShortcuts.entries=@($shortcutPlan.Records)
        $changes+=@([pscustomobject]@{Before=$Snapshot.Files['program-shortcuts.json'];Bytes=(ConvertTo-RuleMaintenanceBytes $nextShortcuts);Remove=$false})
    }
    if($launchEntries.Count){$changes+=@([pscustomobject]@{Before=$Snapshot.Files['program-proxies.json'];Bytes=(ConvertTo-RuleMaintenanceBytes $nextLaunch);Remove=$false})}
    $written=@();$engineHash='';$rollbackProblems=@();$preserved=0
    try{
        if((Get-RuleMaintenanceSnapshot $SavedPath).Fingerprint -cne $Snapshot.Fingerprint){throw '记录或快捷方式在准备期间发生变化，请重新预览。'}
        if($engineEntries.Count){
            $response=Invoke-AppRouter @{action='replace';entries=$nextEngine;defaultRoute=$Snapshot.Engine.defaultRoute;expectedStateHash=$Snapshot.Files['app-rules.json'].TextHash;expectedSettingsHash=$Snapshot.Files['config.json'].TextHash}
            $engineHash=[string](Get-ProgramIdentityValue $response 'stateHash' '')
            if(-not $engineHash){throw '引擎未返回写入归属校验，已保留备份；请刷新核对，不继续改写启动入口。'}
        }
        foreach($change in $changes){
            Set-RuleMaintenanceFile $change.Before $change.Bytes $change.Remove
            $written+=@([pscustomobject]@{Before=$change.Before;AfterHash=$(if($change.Remove){'<missing>'}else{Get-RuleMaintenanceHash $change.Bytes})})
        }
        foreach($item in $written){if((Read-RuleMaintenanceFile $item.Before.Path).Hash -cne $item.AfterHash){throw '写入后发现外部更改，保留外部内容。'}}
    }catch{
        $message=$_.Exception.Message
        for($index=$written.Count-1;$index -ge 0;$index--){$item=$written[$index]
            try{
                $current=Read-RuleMaintenanceFile $item.Before.Path
                if($current.Hash -cne $item.AfterHash){$preserved++;continue}
                Set-RuleMaintenanceFile $current $item.Before.Bytes (-not $item.Before.Exists)
            }catch{$rollbackProblems+='本机记录或快捷方式'}
        }
        if($engineHash){
            try{
                $current=Read-RuleMaintenanceFile $Snapshot.Files['app-rules.json'].Path
                if($current.TextHash -ceq $engineHash){Invoke-AppRouter @{action='replace';entries=@($Snapshot.Engine.entries);defaultRoute=$Snapshot.Engine.defaultRoute;expectedStateHash=$engineHash;expectedSettingsHash=$Snapshot.Files['config.json'].TextHash}|Out-Null}else{$preserved++}
            }catch{$rollbackProblems+='引擎规则'}
        }
        $suffix='；已回滚仍归本次写入的内容。';if($preserved){$suffix+=' 已保留外部修改。'};if($rollbackProblems.Count){$suffix='；部分回滚未完成，请使用本机备份检查。'}
        throw ($message+$suffix+' 备份：'+$backup.Path)
    }
    $message=$(if($Remove){'已移除所选程序的保存记录，并恢复仍归本工具的原入口。'}else{'已修复程序路径，保留原目标线路与快捷方式备份。'})
    if($shortcutPlan.Preserved){$message+=' '+$shortcutPlan.Preserved+' 个快捷方式已由其他程序或用户修改，保持原样。'}
    if($shortcutPlan.RestoredUpdated){$message+=' 已将恢复的原入口指向此前确认的新版本；最初备份仍保留。'}
    if(-not $Remove -and $launchEntries.Count){$message+=' 当前运行会话未重启；请自行保存任务并完整退出后，使用修复后的代理入口重开。'}
    if(-not $Remove -and $engineEntries.Count){$message+=' 引擎规则已核对，新连接生效；已有连接未中断。'}
    [pscustomobject]@{Message=$message;Backup=$backup.Path;PreservedShortcuts=$shortcutPlan.Preserved;RepairedPath=$CurrentPath;Removed=[bool]$Remove;EngineChanged=($engineEntries.Count -gt 0);LaunchChanged=($launchEntries.Count -gt 0)}
}
function Repair-ProgramRule($Plan){
    Use-ChangeLock {
        $created=[DateTime]::MinValue
        if(-not $Plan -or $Plan.Version -ne 1 -or [string]$Plan.DataDirectory -ine [IO.Path]::GetFullPath($script:DataRoot) -or -not [DateTime]::TryParse([string]$Plan.CreatedAt,[ref]$created) -or [DateTime]::UtcNow.Subtract($created.ToUniversalTime()).TotalSeconds -gt 120 -or $created.ToUniversalTime() -gt [DateTime]::UtcNow.AddSeconds(5)){throw '修复预览已过期或来自其他配置目录，请重新预览后确认。'}
        $fresh=Get-ProgramRuleRepairPlan $Plan.SavedPath
        if($fresh.SnapshotFingerprint -cne $Plan.SnapshotFingerprint -or $fresh.IdentityFingerprint -cne $Plan.IdentityFingerprint -or $fresh.CurrentPath -ine $Plan.CurrentPath -or $fresh.Mode -ne $Plan.Mode){throw '程序身份、线路或快捷方式已经变化，请重新预览后确认。'}
        $snapshot=Get-RuleMaintenanceSnapshot $fresh.SavedPath
        if($snapshot.Fingerprint -cne $fresh.SnapshotFingerprint){throw '保存记录已变化，请重新预览后确认。'}
        Invoke-RuleMaintenanceChange $snapshot $fresh.SavedPath $fresh.CurrentPath $fresh.Identity
    }
}
function Remove-SavedProgramRule([string]$SavedPath){
    Use-ChangeLock {
        $path=ConvertTo-ProgramIdentityPath $SavedPath;if(-not $path -or $path -notmatch '(?i)\.exe$'){throw '请选择有效的已保存程序记录。'}
        $snapshot=Get-RuleMaintenanceSnapshot $path
        if(-not @(@($snapshot.Engine.entries)+@($snapshot.Launch.entries)|Where-Object {$_.path -ieq $path}).Count){throw '该程序没有可移除的保存记录。'}
        Invoke-RuleMaintenanceChange $snapshot $path '' $null -Remove
    }
}
