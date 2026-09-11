# Read-only application identity. No rules, shortcuts, network settings or credentials are read/written here.
if(-not ('LocalProxySwitch.ProgramFileIdentity' -as [type])){
    Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using Microsoft.Win32.SafeHandles;
namespace LocalProxySwitch {
    public sealed class ProgramPackageRegistration {
        public readonly string InstallLocation, PackageFamilyName, PackageFullName;
        public readonly bool Verified=true;
        public ProgramPackageRegistration(string path,string family,string fullName) { InstallLocation=path;PackageFamilyName=family;PackageFullName=fullName; }
    }
    // A UI refresh uses a new runspace. Keep ONLY immutable OS registration metadata here,
    // scoped to this user's application process; running PID/file identities stay in the refresh context.
    public static class ProgramRegistrationCache {
        static readonly object Gate=new object();
        static ProgramPackageRegistration[] Packages;
        static DateTime Until=DateTime.MinValue;
        static HashSet<string> Known=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        static HashSet<string> Observed=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        public sealed class Lease : IDisposable {
            public readonly ProgramPackageRegistration[] Cached;
            readonly string[] observed;
            bool disposed;
            internal Lease(ProgramPackageRegistration[] cached,string[] active) {Cached=cached;observed=active;}
            public void Publish(ProgramPackageRegistration[] packages) {
                if(disposed)throw new ObjectDisposedException("Lease");
                Packages=packages==null?new ProgramPackageRegistration[0]:(ProgramPackageRegistration[])packages.Clone();
                Known=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                foreach(var value in Packages)Known.Add(value.PackageFullName);
                Observed=new HashSet<string>(observed,StringComparer.OrdinalIgnoreCase);
                Until=DateTime.UtcNow.AddMinutes(5);
            }
            public void Dispose(){if(!disposed){disposed=true;Monitor.Exit(Gate);}}
        }
        public static Lease Acquire(bool refresh,string[] observed) {
            // Serialize the OS query as well as publication, so concurrent runspaces do not fan it out.
            if(!Monitor.TryEnter(Gate,TimeSpan.FromSeconds(15)))throw new TimeoutException("Package identity cache is busy.");
            try {
                var active=observed??new string[0];bool reload=refresh||Packages==null||Until<=DateTime.UtcNow;
                if(!reload)foreach(var fullName in active)if(!String.IsNullOrEmpty(fullName)&&!Known.Contains(fullName)&&!Observed.Contains(fullName)){reload=true;break;}
                return new Lease(reload?null:(ProgramPackageRegistration[])Packages.Clone(),active);
            } catch {Monitor.Exit(Gate);throw;}
        }
    }
    public sealed class ProgramFileDescriptor {
        public string CanonicalPath="", FileId="", Status="Unavailable";
        public bool Exists;
    }
    public static class ProgramFileIdentity {
        [StructLayout(LayoutKind.Sequential)] struct FileTime { public uint Low,High; }
        [StructLayout(LayoutKind.Sequential)] struct FileInfo {
            public uint Attributes; public FileTime Created,Accessed,Written;
            public uint Volume,SizeHigh,SizeLow,Links,IndexHigh,IndexLow;
        }
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern SafeFileHandle CreateFileW(string path,uint access,uint share,IntPtr security,uint creation,uint flags,IntPtr template);
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern uint GetFinalPathNameByHandleW(SafeFileHandle file,StringBuilder path,uint length,uint flags);
        [DllImport("kernel32.dll", SetLastError=true)] static extern bool GetFileInformationByHandle(SafeFileHandle file,out FileInfo value);
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode)] static extern int PackageFamilyNameFromFullName(string fullName,ref uint length,StringBuilder family);
        public static string Normalize(string path) {
            if(String.IsNullOrWhiteSpace(path) || path.IndexOfAny(new char[]{'\r','\n','\0','"'})>=0)return "";
            if(path.StartsWith(@"\\?\UNC\",StringComparison.OrdinalIgnoreCase))path=@"\\"+path.Substring(8);
            else if(path.StartsWith(@"\\?\",StringComparison.OrdinalIgnoreCase))path=path.Substring(4);
            // Relative and device paths are not stable application identities.
            if(!(path.Length>=3 && Char.IsLetter(path[0]) && path[1]==':' && (path[2]=='\\'||path[2]=='/')) && !path.StartsWith(@"\\"))return "";
            if(path.StartsWith(@"\\.\") || path.StartsWith(@"\\?\"))return "";
            try{return Path.GetFullPath(path).TrimEnd('\\');}catch{return "";}
        }
        public static ProgramFileDescriptor Read(string path) {
            var value=new ProgramFileDescriptor();path=Normalize(path);if(path.Length==0){value.Status="InvalidPath";return value;}
            // A periodic local inventory must never initiate SMB/network IO.
            if(path.StartsWith(@"\\")){value.Status="NetworkPathUnverified";return value;}
            using(var file=CreateFileW(path,0,7,IntPtr.Zero,3,0x02000000,IntPtr.Zero)) {
                if(file.IsInvalid){int error=Marshal.GetLastWin32Error();value.Status=(error==2||error==3)?"Missing":error==5?"AccessDenied":"Unavailable";return value;}
                FileInfo info;if(!GetFileInformationByHandle(file,out info)){value.Status="Unavailable";return value;}
                if((info.Attributes&0x10)!=0){value.Status="NotFile";return value;}
                value.Exists=true;value.Status="Available";
                // Zero IDs are unsupported on some filesystems and must not match each other.
                if(info.IndexHigh!=0||info.IndexLow!=0)value.FileId=info.Volume.ToString("X8")+":"+info.IndexHigh.ToString("X8")+info.IndexLow.ToString("X8");
                var text=new StringBuilder(32768);uint count=GetFinalPathNameByHandleW(file,text,(uint)text.Capacity,0);
                if(count>0 && count<text.Capacity)value.CanonicalPath=Normalize(text.ToString());
                return value;
            }
        }
        public static string FamilyFromFullName(string fullName) {
            if(String.IsNullOrEmpty(fullName))return "";
            try{uint size=256;var text=new StringBuilder((int)size);return PackageFamilyNameFromFullName(fullName,ref size,text)==0?text.ToString():"";}
            catch(EntryPointNotFoundException){return "";}
        }
    }
}
'@
}

function Get-ProgramIdentityValue($Value,[string]$Name,$Default=$null) {
    if($Value -is [Collections.IDictionary] -and $Value.Contains($Name)){return $Value[$Name]}
    if($null -ne $Value -and $Value.PSObject.Properties[$Name]){return $Value.$Name}
    return $Default
}
function ConvertTo-ProgramIdentityPath([string]$Path) {[LocalProxySwitch.ProgramFileIdentity]::Normalize($Path)}
function Get-RegisteredProgramPackages([switch]$Refresh,$Processes=@()) {
    $observed=[string[]]@($Processes|ForEach-Object {Get-ProgramIdentityValue $_ 'PackageFullName' ''}|Where-Object {$_}|Sort-Object -Unique)
    $lease=$null
    try{
        $lease=[LocalProxySwitch.ProgramRegistrationCache]::Acquire([bool]$Refresh,$observed)
        if($null -ne $lease.Cached){return @($lease.Cached)}
        $packages=New-Object 'Collections.Generic.List[LocalProxySwitch.ProgramPackageRegistration]'
        try{
            # One current-user OS registration query per process/cache interval; no recursive scans or signatures.
            foreach($package in @(Get-AppxPackage -ErrorAction Stop)){
                if($package.IsDevelopmentMode -or [string]$package.SignatureKind -notin @('Store','System','Enterprise') -or [string]$package.Status -ne 'Ok'){continue}
                $root=ConvertTo-ProgramIdentityPath ([string]$package.InstallLocation)
                $family=[LocalProxySwitch.ProgramFileIdentity]::FamilyFromFullName([string]$package.PackageFullName)
                if(-not $root -or -not $family -or $family -ine [string]$package.PackageFamilyName){continue}
                $packages.Add((New-Object LocalProxySwitch.ProgramPackageRegistration($root,$family,[string]$package.PackageFullName)))
            }
        }catch{} # Missing Appx support or access denial means unknown, never a name-based fallback.
        $lease.Publish($packages.ToArray())
        @($packages.ToArray())
    }catch{@()}finally{if($null -ne $lease){$lease.Dispose()}}
}
function New-ProgramIdentityContext($Processes=@(),$Packages=$null,[switch]$RefreshPackages) {
    if($null -eq $Packages){$Packages=@(Get-RegisteredProgramPackages -Refresh:$RefreshPackages -Processes $Processes)}
    [pscustomobject]@{Processes=@($Processes);Packages=@($Packages);Files=@{};Created=[DateTime]::UtcNow}
}
function Get-ProgramIdentityDescriptor([string]$Path,$Context=$null) {
    if($null -eq $Context){$Context=New-ProgramIdentityContext}
    $normalized=ConvertTo-ProgramIdentityPath $Path
    if($normalized -and $Context.Files.ContainsKey($normalized)){return $Context.Files[$normalized]}
    $file=[LocalProxySwitch.ProgramFileIdentity]::Read($normalized)
    $result=[pscustomobject]@{Version=1;Kind='Path';Path=$normalized;CanonicalPath=$file.CanonicalPath;FileId=$file.FileId;Exists=$file.Exists;PathStatus=$file.Status;PackageFamilyName='';PackageFullName='';RelativeExecutable='';PackageVerified=$false}
    if($file.Exists){$result.Kind='File'}
    if($file.Exists -and $file.CanonicalPath -and $normalized -match '(?i)\.exe$'){
        $matches=@()
        foreach($package in $Context.Packages){
            if(-not (Get-ProgramIdentityValue $package 'Verified' $false)){continue}
            $root=ConvertTo-ProgramIdentityPath ([string]$package.InstallLocation)
            if(-not $root){continue}
            $prefix=$root+'\'
            # Match the final filesystem destination against a Windows-registered package root.
            # A user-controlled symlink into a different directory cannot impersonate the package.
            if(-not $file.CanonicalPath.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)){continue}
            $family=[LocalProxySwitch.ProgramFileIdentity]::FamilyFromFullName([string]$package.PackageFullName)
            if(-not $family -or $family -ine [string]$package.PackageFamilyName){continue}
            $matches+=@([pscustomobject]@{Package=$package;Relative=$file.CanonicalPath.Substring($prefix.Length)})
        }
        if($matches.Count -eq 1){
            $result.Kind='Package';$result.PackageFamilyName=[string]$matches[0].Package.PackageFamilyName
            $result.PackageFullName=[string]$matches[0].Package.PackageFullName;$result.RelativeExecutable=[string]$matches[0].Relative;$result.PackageVerified=$true
        }
    }
    if($normalized){$Context.Files[$normalized]=$result}
    $result
}
function Test-ProgramPathEquivalent([string]$Left,[string]$Right,$Context=$null) {
    $leftPath=ConvertTo-ProgramIdentityPath $Left;$rightPath=ConvertTo-ProgramIdentityPath $Right
    if(-not $leftPath -or -not $rightPath){return $false}
    if($leftPath -ieq $rightPath){return $true}
    if($null -eq $Context){$Context=New-ProgramIdentityContext -Packages @()}
    $a=Get-ProgramIdentityDescriptor $leftPath $Context;$b=Get-ProgramIdentityDescriptor $rightPath $Context
    if(-not $a.Exists -or -not $b.Exists){return $false}
    return [bool](($a.FileId -and $a.FileId -eq $b.FileId) -or ($a.CanonicalPath -and $a.CanonicalPath -ieq $b.CanonicalPath))
}
function Get-LegacyProgramPackageHint([string]$Path,$Context) {
    $normalized=ConvertTo-ProgramIdentityPath $Path;if(-not $normalized){return $null}
    $hints=@()
    foreach($package in $Context.Packages){
        if(-not (Get-ProgramIdentityValue $package 'Verified' $false)){continue}
        $root=ConvertTo-ProgramIdentityPath ([string]$package.InstallLocation)
        if(-not $root -or [IO.Path]::GetFileName($root) -ine [string]$package.PackageFullName){continue}
        $parent=[IO.Path]::GetDirectoryName($root)
        # Legacy rules lack saved package metadata. Only the OS package store layout supplies a candidate.
        if([IO.Path]::GetFileName($parent) -ine 'WindowsApps'){continue}
        $prefix=$parent+'\';if(-not $normalized.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)){continue}
        $tail=$normalized.Substring($prefix.Length);$separator=$tail.IndexOf('\');if($separator -le 0){continue}
        $oldFull=$tail.Substring(0,$separator);$relative=$tail.Substring($separator+1)
        $family=[LocalProxySwitch.ProgramFileIdentity]::FamilyFromFullName($oldFull)
        if(-not $family -or $family -ine [string]$package.PackageFamilyName -or $relative -notmatch '(?i)\.exe$'){continue}
        $hints+=@([pscustomobject]@{PackageFamilyName=$family;RelativeExecutable=$relative})
    }
    $unique=@($hints|Sort-Object PackageFamilyName,RelativeExecutable -Unique)
    if($unique.Count -eq 1){return $unique[0]}
    return $null
}
function Resolve-ProgramIdentity([string]$Path,$Processes=$null,$Context=$null,$SavedIdentity=$null) {
    if($null -eq $Context){if($null -eq $Processes){$Processes=@()};$Context=New-ProgramIdentityContext -Processes $Processes}
    if($null -eq $Processes){$Processes=$Context.Processes}
    $source=Get-ProgramIdentityDescriptor $Path $Context;$normalized=$source.Path
    $result=[pscustomobject]@{RequestedPath=$Path;CurrentPath=$normalized;Reason='NotRunning';Confidence='Unknown';RequiresRepair=$false;CanRepair=$false;CandidatePaths=@();PIDs=@();Identity=$source}
    if(-not $normalized){$result.Reason='PathUnavailable';$result.CurrentPath='';return $result}
    $live=@($Processes|Where-Object {[string](Get-ProgramIdentityValue $_ 'Path' '')})
    $exact=@($live|Where-Object {(ConvertTo-ProgramIdentityPath ([string]$_.Path)) -ieq $normalized})
    if($exact.Count){$result.Reason='ExactPath';$result.Confidence='Exact';$result.PIDs=@($exact|ForEach-Object Id);return $result}
    $aliases=@($live|Where-Object {Test-ProgramPathEquivalent $normalized ([string]$_.Path) $Context})
    if($aliases.Count){
        $paths=@($aliases|ForEach-Object Path|Sort-Object -Unique);$result.CurrentPath=[string]$paths[0];$result.Reason='SameFile';$result.Confidence='Verified'
        $result.CandidatePaths=$paths;$result.PIDs=@($aliases|ForEach-Object Id);$result.Identity=Get-ProgramIdentityDescriptor $result.CurrentPath $Context
        # Observing the same file does not prove the engine's literal PROCESS-PATH rule matches its image path.
        $result.RequiresRepair=$true;$result.CanRepair=$true;return $result
    }
    # An existing executable remains an unambiguous identity even if another version is also installed.
    if($source.Exists){return $result}
    # Access denied/unsupported storage is not proof that the saved installation disappeared.
    if($source.PathStatus -ne 'Missing'){$result.Reason='PathUnavailable';return $result}
    $basis=$null;$trusted=$false
    if($SavedIdentity -and (Get-ProgramIdentityValue $SavedIdentity 'Version' 0) -eq 1 -and (Get-ProgramIdentityValue $SavedIdentity 'Kind' '') -eq 'Package' -and (Get-ProgramIdentityValue $SavedIdentity 'PackageVerified' $false)){
        $savedPath=ConvertTo-ProgramIdentityPath ([string](Get-ProgramIdentityValue $SavedIdentity 'Path' ''))
        $savedFamily=[LocalProxySwitch.ProgramFileIdentity]::FamilyFromFullName([string](Get-ProgramIdentityValue $SavedIdentity 'PackageFullName' ''))
        $relative=[string](Get-ProgramIdentityValue $SavedIdentity 'RelativeExecutable' '')
        if($savedPath -ieq $normalized -and $savedFamily -and $savedFamily -ieq [string]$SavedIdentity.PackageFamilyName -and $relative -match '(?i)\.exe$' -and -not [IO.Path]::IsPathRooted($relative) -and $relative -notmatch '(^|[\\/])\.\.([\\/]|$)'){
            $basis=[pscustomobject]@{PackageFamilyName=$savedFamily;RelativeExecutable=$relative};$trusted=$true
        }
    }
    if(-not $basis){$basis=Get-LegacyProgramPackageHint $normalized $Context}
    if(-not $basis){$result.Reason=$(if($source.PathStatus -eq 'Missing'){'MissingPath'}else{'PathUnavailable'});return $result}
    $candidates=@{}
    foreach($package in $Context.Packages){
        if(-not (Get-ProgramIdentityValue $package 'Verified' $false) -or [string]$package.PackageFamilyName -ine $basis.PackageFamilyName){continue}
        $root=ConvertTo-ProgramIdentityPath ([string]$package.InstallLocation);if(-not $root){continue}
        $candidate=ConvertTo-ProgramIdentityPath (Join-Path $root $basis.RelativeExecutable)
        if(-not $candidate -or -not $candidate.StartsWith($root+'\',[StringComparison]::OrdinalIgnoreCase)){continue}
        $identity=Get-ProgramIdentityDescriptor $candidate $Context
        if(-not $identity.PackageVerified -or $identity.PackageFamilyName -ine $basis.PackageFamilyName -or $identity.RelativeExecutable -ine $basis.RelativeExecutable){continue}
        # If Windows exposes the running process package, cross-check it against registration.
        $processMatches=@($live|Where-Object {Test-ProgramPathEquivalent $candidate ([string]$_.Path) $Context})
        $contradictions=@($processMatches|Where-Object {([string](Get-ProgramIdentityValue $_ 'PackageFamilyName' '') -and [string]$_.PackageFamilyName -ine $identity.PackageFamilyName) -or ([string](Get-ProgramIdentityValue $_ 'PackageFullName' '') -and [string]$_.PackageFullName -ine $identity.PackageFullName)})
        if($contradictions.Count){continue}
        $key=$(if($identity.FileId){$identity.FileId}else{$candidate.ToLowerInvariant()})
        $candidates[$key]=[pscustomobject]@{Path=$candidate;Identity=$identity;Processes=$processMatches}
    }
    $values=@($candidates.Values);$result.CandidatePaths=@($values|ForEach-Object Path|Sort-Object)
    if($values.Count -gt 1){$result.CurrentPath='';$result.Reason='Ambiguous';$result.RequiresRepair=$true;return $result}
    if($values.Count -eq 0){$result.Reason='MissingPath';return $result}
    $value=$values[0];$result.CurrentPath=$value.Path;$result.Identity=$value.Identity;$result.PIDs=@($value.Processes|ForEach-Object Id)
    $result.RequiresRepair=$true;$result.CanRepair=$true;$result.Reason=$(if($trusted){'PackageIdentity'}else{'PackageUpgradeCandidate'});$result.Confidence=$(if($trusted){'Verified'}else{'Candidate'})
    $result
}
