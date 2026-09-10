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
    public bool IsPrimary { get; private set; }
    public FlowSwitchWindowLease(string directory) {
        string id;
        using(var hash=System.Security.Cryptography.SHA256.Create())
            id=System.BitConverter.ToString(hash.ComputeHash(System.Text.Encoding.UTF8.GetBytes(System.IO.Path.GetFullPath(directory).TrimEnd('\\').ToLowerInvariant()))).Replace("-","");
        mutex=new System.Threading.Mutex(false,@"Local\FlowSwitch.UI."+id);
        try { IsPrimary=mutex.WaitOne(0); } catch(System.Threading.AbandonedMutexException) { IsPrimary=true; }
        wake=new System.Threading.EventWaitHandle(false,System.Threading.EventResetMode.AutoReset,@"Local\FlowSwitch.Wake."+id);
        if(!IsPrimary)wake.Set();
    }
    public bool ConsumeWake() { return wake.WaitOne(0); }
    public void Dispose() { if(IsPrimary){mutex.ReleaseMutex();IsPrimary=false;}wake.Dispose();mutex.Dispose(); }
}
