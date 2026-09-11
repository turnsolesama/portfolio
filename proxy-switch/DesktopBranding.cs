using System;
using System.Runtime.InteropServices;

// Give the PowerShell-hosted window its own taskbar identity and a usable pin target.
public static class FlowSwitchDesktop
{
    public const string AppId = "FlowSwitch.Desktop";
    private static readonly Guid PropertyFormat = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3");

    [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
    private static extern int SetCurrentProcessExplicitAppUserModelID(string appId);
    [DllImport("shell32.dll")]
    private static extern int SHGetPropertyStoreForWindow(IntPtr window, ref Guid iid, out IPropertyStore store);
    [DllImport("ole32.dll")]
    private static extern int PropVariantClear(ref PropVariant value);

    [StructLayout(LayoutKind.Sequential)]
    private struct PropertyKey { public Guid Format; public uint Id; }
    [StructLayout(LayoutKind.Explicit, Size = 24)]
    private struct PropVariant
    {
        [FieldOffset(0)] public ushort Type;
        [FieldOffset(8)] public IntPtr Value;
    }
    [ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IPropertyStore
    {
        [PreserveSig] int GetCount(out uint count);
        [PreserveSig] int GetAt(uint index, out PropertyKey key);
        [PreserveSig] int GetValue(ref PropertyKey key, out PropVariant value);
        [PreserveSig] int SetValue(ref PropertyKey key, ref PropVariant value);
        [PreserveSig] int Commit();
    }
    private static IPropertyStore Open(IntPtr window)
    {
        Guid iid = typeof(IPropertyStore).GUID;
        IPropertyStore store;
        Marshal.ThrowExceptionForHR(SHGetPropertyStoreForWindow(window, ref iid, out store));
        return store;
    }
    private static void Set(IPropertyStore store, uint id, string text)
    {
        var key = new PropertyKey { Format = PropertyFormat, Id = id };
        var value = new PropVariant { Type = 31, Value = Marshal.StringToCoTaskMemUni(text) };
        try { Marshal.ThrowExceptionForHR(store.SetValue(ref key, ref value)); }
        finally { PropVariantClear(ref value); }
    }
    public static void Initialize()
    {
        Marshal.ThrowExceptionForHR(SetCurrentProcessExplicitAppUserModelID(AppId));
    }
    public static bool ConfigureWindow(IntPtr window, string command, string icon)
    {
        var store = Open(window);
        try
        {
            // Relaunch properties must precede the ID. Keep arguments and selected data directory.
            bool relaunchReady = true;
            try
            {
                Set(store, 2, command);
                Set(store, 3, icon + ",0");
                Set(store, 4, "流向 · FlowSwitch");
            }
            catch (COMException error)
            {
                if (error.ErrorCode != unchecked((int)0x8007007A)) throw;
                // Some Shell builds limit relaunch properties to MAX_PATH. Never truncate
                // the command or lose its data directory. Keep the window icon and ID,
                // but do not offer a broken pin/relaunch action for this long source path.
                var key = new PropertyKey { Format = PropertyFormat, Id = 9 };
                var value = new PropVariant { Type = 11, Value = new IntPtr(-1) };
                Marshal.ThrowExceptionForHR(store.SetValue(ref key, ref value));
                relaunchReady = false;
            }
            Set(store, 5, AppId);
            Marshal.ThrowExceptionForHR(store.Commit());
            return relaunchReady;
        }
        finally { Marshal.ReleaseComObject(store); }
    }
    public static string ReadWindowProperty(IntPtr window, uint id)
    {
        var store = Open(window);
        try
        {
            var key = new PropertyKey { Format = PropertyFormat, Id = id };
            PropVariant value;
            Marshal.ThrowExceptionForHR(store.GetValue(ref key, out value));
            try { return value.Type == 31 ? Marshal.PtrToStringUni(value.Value) : null; }
            finally { PropVariantClear(ref value); }
        }
        finally { Marshal.ReleaseComObject(store); }
    }
}


// One visible/tray UI per shared data directory. A second launch wakes the first.
public sealed class FlowSwitchWindowLease : System.IDisposable {
    private System.Threading.Mutex mutex;
    private System.Threading.EventWaitHandle wake;
    private readonly string launchPipeName;
    private readonly System.Collections.Generic.Queue<LaunchRequest> launches=new System.Collections.Generic.Queue<LaunchRequest>();
    private readonly object pipeLock=new object();
    private System.IO.Pipes.NamedPipeServerStream activePipe;
    private System.Threading.Thread launchThread;
    private volatile bool disposed;
    private int expiredLaunches;
    private sealed class LaunchRequest { public string Path; public long Expires; }
    public bool IsPrimary { get; private set; }
    public FlowSwitchWindowLease(string directory) {
        string id;
        using(var hash=System.Security.Cryptography.SHA256.Create())
            id=System.BitConverter.ToString(hash.ComputeHash(System.Text.Encoding.UTF8.GetBytes(System.IO.Path.GetFullPath(directory).TrimEnd('\\').ToLowerInvariant()))).Replace("-","");
        mutex=new System.Threading.Mutex(false,@"Local\FlowSwitch.UI."+id);
        try { IsPrimary=mutex.WaitOne(0); } catch(System.Threading.AbandonedMutexException) { IsPrimary=true; }
        wake=new System.Threading.EventWaitHandle(false,System.Threading.EventResetMode.AutoReset,@"Local\FlowSwitch.Wake."+id);
        launchPipeName="FlowSwitch.Launch."+id;
        if(IsPrimary){launchThread=new System.Threading.Thread(ServeLaunches);launchThread.IsBackground=true;launchThread.Start();}
        if(!IsPrimary)wake.Set();
    }
    public bool ConsumeWake() { return wake.WaitOne(0); }
    private static bool ValidPath(string value) {
        return !System.String.IsNullOrWhiteSpace(value) && value.Length<=2048 && value.IndexOfAny(new char[]{'\r','\n','\0'})<0 && System.IO.Path.IsPathRooted(value) && System.String.Equals(System.IO.Path.GetExtension(value),".exe",System.StringComparison.OrdinalIgnoreCase);
    }
    private bool EnqueueLaunch(string value,long created) {
        long now=System.DateTime.UtcNow.Ticks;
        if(!ValidPath(value) || created>now+System.TimeSpan.FromSeconds(5).Ticks || created<now-System.TimeSpan.FromSeconds(30).Ticks)return false;
        lock(launches){
            while(launches.Count>0 && launches.Peek().Expires<now){launches.Dequeue();expiredLaunches++;}
            foreach(var item in launches)if(System.String.Equals(item.Path,value,System.StringComparison.OrdinalIgnoreCase))return true;
            if(launches.Count>=4)return false;
            launches.Enqueue(new LaunchRequest{Path=value,Expires=created+System.TimeSpan.FromSeconds(30).Ticks});return true;
        }
    }
    private static byte[] ReadBounded(System.IO.Stream stream,int count) {
        byte[] data=new byte[count];int offset=0;long deadline=System.DateTime.UtcNow.AddMilliseconds(1500).Ticks;
        while(offset<count){
            int remaining=(int)System.Math.Ceiling(System.TimeSpan.FromTicks(deadline-System.DateTime.UtcNow.Ticks).TotalMilliseconds);
            if(remaining<=0)throw new System.IO.IOException("Launch request timed out.");
            var read=stream.BeginRead(data,offset,count-offset,null,null);
            try{if(!read.AsyncWaitHandle.WaitOne(remaining))throw new System.IO.IOException("Launch request timed out.");int received=stream.EndRead(read);if(received<=0)throw new System.IO.EndOfStreamException();offset+=received;}
            finally{read.AsyncWaitHandle.Close();}
        }
        return data;
    }
    private void ServeLaunches() {
        while(!disposed){
            System.IO.Pipes.NamedPipeServerStream pipe=null;
            try{
                var security=new System.IO.Pipes.PipeSecurity();security.SetAccessRuleProtection(true,false);
                security.AddAccessRule(new System.IO.Pipes.PipeAccessRule(System.Security.Principal.WindowsIdentity.GetCurrent().User,System.IO.Pipes.PipeAccessRights.FullControl,System.Security.AccessControl.AccessControlType.Allow));
                pipe=new System.IO.Pipes.NamedPipeServerStream(launchPipeName,System.IO.Pipes.PipeDirection.InOut,1,System.IO.Pipes.PipeTransmissionMode.Byte,System.IO.Pipes.PipeOptions.Asynchronous,4096,4096,security);
                lock(pipeLock){if(disposed){pipe.Dispose();return;}activePipe=pipe;}
                var connection=pipe.BeginWaitForConnection(null,null);
                try{while(!disposed && !connection.AsyncWaitHandle.WaitOne(200)){}if(disposed)return;pipe.EndWaitForConnection(connection);}finally{connection.AsyncWaitHandle.Close();}
                byte[] header=ReadBounded(pipe,16);
                int version=System.BitConverter.ToInt32(header,0),size=System.BitConverter.ToInt32(header,12);
                if(version!=1 || size<1 || size>8192)throw new System.IO.IOException("Invalid launch request.");
                string path=new System.Text.UTF8Encoding(false,true).GetString(ReadBounded(pipe,size));
                bool accepted=EnqueueLaunch(path,System.BitConverter.ToInt64(header,4));
                pipe.WriteByte(accepted?(byte)1:(byte)0);pipe.Flush();if(accepted)wake.Set();
            }catch(System.Exception){if(!disposed)System.Threading.Thread.Sleep(50);}
            finally{lock(pipeLock){if(activePipe==pipe)activePipe=null;}if(pipe!=null)pipe.Dispose();}
        }
    }
    public bool RequestLaunch(string executable) {
        if(disposed || !ValidPath(executable))return false;
        long created=System.DateTime.UtcNow.Ticks;
        if(IsPrimary)return EnqueueLaunch(executable,created);
        using(var client=new System.IO.Pipes.NamedPipeClientStream(".",launchPipeName,System.IO.Pipes.PipeDirection.InOut,System.IO.Pipes.PipeOptions.Asynchronous)){
            client.Connect(3000);byte[] path=System.Text.Encoding.UTF8.GetBytes(executable);
            using(var data=new System.IO.MemoryStream()){
                byte[] version=System.BitConverter.GetBytes(1),time=System.BitConverter.GetBytes(created),size=System.BitConverter.GetBytes(path.Length);
                data.Write(version,0,version.Length);data.Write(time,0,time.Length);data.Write(size,0,size.Length);data.Write(path,0,path.Length);
                byte[] message=data.ToArray();client.Write(message,0,message.Length);client.Flush();
            }
            return ReadBounded(client,1)[0]==1;
        }
    }
    public string ConsumeLaunch() {
        if(!IsPrimary)return null;long now=System.DateTime.UtcNow.Ticks;
        lock(launches){while(launches.Count>0){var next=launches.Dequeue();if(next.Expires>=now)return next.Path;expiredLaunches++;}}return null;
    }
    public int ConsumeExpiredLaunchCount() {
        long now=System.DateTime.UtcNow.Ticks;
        lock(launches){while(launches.Count>0 && launches.Peek().Expires<now){launches.Dequeue();expiredLaunches++;}int count=expiredLaunches;expiredLaunches=0;return count;}
    }
    public void Dispose() {
        if(disposed)return;disposed=true;
        lock(pipeLock){if(activePipe!=null)activePipe.Dispose();}
        if(launchThread!=null)launchThread.Join(500);
        if(IsPrimary){mutex.ReleaseMutex();IsPrimary=false;}wake.Dispose();mutex.Dispose();
    }
}
