# Windows PowerShell's Process.Path getter enumerates MainModule with VM_READ.
# Keep monitoring and routing paths using the documented limited-query API instead.
if(-not ('LocalProxySwitch.ProcessCatalog' -as [type])){
    Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
namespace LocalProxySwitch {
    public sealed class ProcessEntry {
        public int Id;
        public int ParentId;
        public string ProcessName;
        public string Path = "";
        public string PathStatus = "Unavailable";
        public int QueryError;
        public string PackageFamilyName = "";
        public string PackageFullName = "";
        public DateTime StartTime = DateTime.MinValue;
        public IntPtr MainWindowHandle;
    }
    public static class ProcessCatalog {
        public const uint QueryAccess = 0x1000; // PROCESS_QUERY_LIMITED_INFORMATION only.
        [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)]
        struct Entry {
            public uint Size, Usage, Id;
            public UIntPtr Heap;
            public uint Module, Threads, Parent;
            public int Priority;
            public uint Flags;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst=260)] public string Name;
        }
        [StructLayout(LayoutKind.Sequential)]
        struct Time { public uint Low, High; }
        [DllImport("kernel32.dll", SetLastError=true)] static extern IntPtr CreateToolhelp32Snapshot(uint flags, uint pid);
        [DllImport("kernel32.dll", EntryPoint="Process32FirstW", CharSet=CharSet.Unicode, SetLastError=true)] static extern bool First(IntPtr snapshot, ref Entry value);
        [DllImport("kernel32.dll", EntryPoint="Process32NextW", CharSet=CharSet.Unicode, SetLastError=true)] static extern bool Next(IntPtr snapshot, ref Entry value);
        [DllImport("kernel32.dll", SetLastError=true)] static extern IntPtr OpenProcess(uint access, bool inherit, uint pid);
        [DllImport("kernel32.dll", SetLastError=true)] static extern bool CloseHandle(IntPtr handle);
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern bool QueryFullProcessImageNameW(IntPtr handle, uint flags, StringBuilder text, ref uint size);
        [DllImport("kernel32.dll", SetLastError=true)] static extern bool GetProcessTimes(IntPtr handle, out Time created, out Time exited, out Time kernel, out Time user);
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode)] static extern int GetPackageFamilyName(IntPtr process, ref uint length, StringBuilder value);
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode)] static extern int GetPackageFullName(IntPtr process, ref uint length, StringBuilder value);
        delegate bool WindowCallback(IntPtr window, IntPtr parameter);
        [DllImport("user32.dll")] static extern bool EnumWindows(WindowCallback callback, IntPtr parameter);
        [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr window, out uint pid);
        [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr window);
        [DllImport("user32.dll")] static extern IntPtr GetWindow(IntPtr window, uint command);
        static readonly Dictionary<string,DateTime> Denied = new Dictionary<string,DateTime>();
        static readonly object Gate = new object();
        public static ProcessEntry[] Read(int requestedId) {
            var entries = new Dictionary<int,ProcessEntry>();
            IntPtr snapshot = CreateToolhelp32Snapshot(2,0); // Processes only, never modules or heaps.
            if(snapshot == new IntPtr(-1)) throw new Win32Exception(Marshal.GetLastWin32Error());
            try {
                var item = new Entry(); item.Size=(uint)Marshal.SizeOf(typeof(Entry));
                if(!First(snapshot,ref item)) throw new Win32Exception(Marshal.GetLastWin32Error());
                do {
                    if(requestedId!=0 && requestedId!=(int)item.Id) continue;
                    var row=new ProcessEntry();row.Id=(int)item.Id;row.ParentId=(int)item.Parent;
                    row.ProcessName=System.IO.Path.GetFileNameWithoutExtension(item.Name ?? "");
                    entries[row.Id]=row;
                } while(Next(snapshot,ref item));
            } finally {CloseHandle(snapshot);}
            foreach(var row in entries.Values) {
                if(row.Id<=4) continue;
                string identity=row.Id+"|"+row.ParentId+"|"+row.ProcessName;
                lock(Gate) {DateTime until;if(Denied.TryGetValue(identity,out until)&&until>DateTime.UtcNow) {row.PathStatus="AccessDenied";row.QueryError=5;continue;}}
                IntPtr handle=OpenProcess(QueryAccess,false,(uint)row.Id);
                if(handle==IntPtr.Zero) {row.QueryError=Marshal.GetLastWin32Error();row.PathStatus=row.QueryError==5?"AccessDenied":"Unavailable";if(row.QueryError==5){lock(Gate){if(Denied.Count>4096)Denied.Clear();Denied[identity]=DateTime.UtcNow.AddMinutes(1);}}continue;}
                try {
                    uint length=32768;var text=new StringBuilder((int)length);
                    if(QueryFullProcessImageNameW(handle,0,text,ref length)) {row.Path=text.ToString();row.PathStatus="Available";}
                    else {row.QueryError=Marshal.GetLastWin32Error();row.PathStatus=row.QueryError==5?"AccessDenied":"Unavailable";}
                    Time created,exited,kernel,user;
                    if(GetProcessTimes(handle,out created,out exited,out kernel,out user))row.StartTime=DateTime.FromFileTimeUtc(((long)created.High<<32)|created.Low);
                    // Package identity comes from Windows on the same limited-query handle.
                    // A blank value means unpackaged/unavailable, never a filename guess.
                    try {
                        uint familyLength=256;var family=new StringBuilder((int)familyLength);
                        if(GetPackageFamilyName(handle,ref familyLength,family)==0)row.PackageFamilyName=family.ToString();
                        uint fullLength=1024;var full=new StringBuilder((int)fullLength);
                        if(GetPackageFullName(handle,ref fullLength,full)==0)row.PackageFullName=full.ToString();
                    } catch(EntryPointNotFoundException) {} // Older Windows: preserve PID/path observation.
                } finally {CloseHandle(handle);}
            }
            WindowCallback callback=delegate(IntPtr window,IntPtr parameter){
                uint id;GetWindowThreadProcessId(window,out id);ProcessEntry row;
                if(entries.TryGetValue((int)id,out row)&&row.MainWindowHandle==IntPtr.Zero&&IsWindowVisible(window)&&GetWindow(window,4)==IntPtr.Zero)row.MainWindowHandle=window;
                return true;
            };
            EnumWindows(callback,IntPtr.Zero);GC.KeepAlive(callback);
            var result=new ProcessEntry[entries.Count];entries.Values.CopyTo(result,0);return result;
        }
    }
}
'@
}
function Get-ProcessInventory([int]$Id=0) {[LocalProxySwitch.ProcessCatalog]::Read($Id)}
