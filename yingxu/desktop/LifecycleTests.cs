using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace YingXu.Desktop
{
    internal static class LifecycleTests
    {
        private static int count;
        private static void Check(bool value,string name)
        {
            if (!value) throw new Exception("FAILED: " + name);
            count++; Console.WriteLine("PASS " + name);
        }
        private static object Field(object target,string name)
        {
            return target.GetType().GetField(name,BindingFlags.Instance|BindingFlags.NonPublic).GetValue(target);
        }
        private static void Field(object target,string name,object value)
        {
            target.GetType().GetField(name,BindingFlags.Instance|BindingFlags.NonPublic).SetValue(target,value);
        }
        private static object Call(object target,string name,params object[] args)
        {
            return target.GetType().GetMethod(name,BindingFlags.Instance|BindingFlags.NonPublic).Invoke(target,args);
        }
        [STAThread]
        private static int Main(string[] args)
        {
            string directory = Path.Combine(Path.GetTempPath(),"yingxu-lifecycle-"+Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(directory);
            try
            {
                Hub.Root = args[0]; Hub.Data = directory; Hub.Cache = directory;
                Hub.Port = 1; Hub.Url = "http://127.0.0.1:1/";
                Program.InitialFiles = new string[0]; Program.InstanceKey = Guid.NewGuid().ToString("N");
                Program.ActivateEvent = new EventWaitHandle(false,EventResetMode.AutoReset);
                typeof(Program).GetMethod("PrepareLibraries",BindingFlags.Static|BindingFlags.NonPublic).Invoke(null,null);
                Application.EnableVisualStyles();
                if(args.Length==3 && args[1]=="--zoom-integration") RunZoomIntegration(args[2]);
                else Run();
                Console.WriteLine("Desktop lifecycle tests passed: " + count);
                return 0;
            }
            finally
            {
                if (Program.ActivateEvent != null) Program.ActivateEvent.Dispose();
                string resolved = Path.GetFullPath(directory);
                if (!resolved.StartsWith(Path.GetFullPath(Path.GetTempPath()),StringComparison.OrdinalIgnoreCase) ||
                    !Path.GetFileName(resolved).StartsWith("yingxu-lifecycle-",StringComparison.Ordinal) ||
                    (File.GetAttributes(resolved)&FileAttributes.ReparsePoint)!=0) throw new IOException("Invalid fixture cleanup path");
                // Native WebView interop assemblies can remain mapped until this
                // process exits. The explicit integration runner cleans its own
                // printed fixture path only after observing process completion.
                if(args.Length==3 && args[1]=="--zoom-integration") Console.WriteLine("ZOOM_FIXTURE_CLEANUP_AFTER_EXIT="+resolved);
                else Directory.Delete(resolved,true);
            }
        }
        [MethodImpl(MethodImplOptions.NoInlining)]
        private static void RunZoomIntegration(string browserFolder)
        {
            // Explicit, offline integration mode. It never shows a window, connects
            // to the backend, registers a hotkey or accesses screen/clipboard data.
            CoreWebView2Environment.SetLoaderDllFolderPath(Program.LoaderFolder);
            using(var window=new StudioWindow(false))
            {
                ((NotifyIcon)Field(window,"tray")).Visible=false;
                try
                {
                    var work=CheckZoomReset(window,browserFolder);
                    DateTime deadline=DateTime.UtcNow.AddSeconds(15);
                    while(!work.IsCompleted && DateTime.UtcNow<deadline) { Application.DoEvents();Thread.Sleep(10); }
                    if(!work.IsCompleted) throw new TimeoutException("Offline WebView zoom integration timed out");
                    work.GetAwaiter().GetResult();
                }
                finally
                {
                    ((NotifyIcon)Field(window,"tray")).Dispose();
                    ((OpenInbox)Field(window,"inbox")).Dispose();
                    ((RegisteredWaitHandle)Field(window,"activation")).Unregister(null);
                    ((System.Windows.Forms.Timer)Field(window,"exitTimer")).Dispose();
                }
            }
        }
        private static async Task CheckZoomReset(StudioWindow window,string browserFolder)
        {
            var web=new WebView2 { Dock=DockStyle.Fill };window.Controls.Add(web);Field(window,"web",web);
            IntPtr initializedHandle=web.Handle;
            var environment=await CoreWebView2Environment.CreateAsync(browserFolder,Path.Combine(Hub.Cache,"zoom-profile"),
                new CoreWebView2EnvironmentOptions("--disable-background-networking --no-first-run"));
            var exited=new TaskCompletionSource<bool>();
            environment.BrowserProcessExited+=(sender,args)=>exited.TrySetResult(true);
            await web.EnsureCoreWebView2Async(environment);
            int events=0;
            web.ZoomFactorChanged+=(sender,args)=>{events++;Call(window,"UpdateZoomStatus");};
            var zoom=(ToolStripStatusLabel)Field(window,"zoomStatus");
            // Normal property assignment intentionally does not emit the SDK event.
            // An out-of-range assignment invokes the engine's real normalization event.
            web.ZoomFactor=100;
            for(int i=0;i<80 && events==0;i++) await Task.Delay(25);
            Check(events>0 && zoom.Text=="界面 "+Math.Round(web.ZoomFactor*100).ToString(System.Globalization.CultureInfo.InvariantCulture)+"%",
                "real WebView normalization event updates the product percentage callback");
            Check(Math.Abs(web.ZoomFactor-1)>0.01,"reset regression starts at a non-default engine zoom");
            zoom.PerformClick();
            Check(Math.Abs(web.ZoomFactor-1)<0.000001 && zoom.Text=="界面 100%",
                "real click resets engine and label synchronously without a setter event");
            var navigation=new TaskCompletionSource<bool>();
            web.CoreWebView2.NavigationCompleted+=(sender,args)=>navigation.TrySetResult(args.IsSuccess);
            web.NavigateToString("<!doctype html><meta charset='utf-8'><script>window.pauseMessageCount=0;window.chrome.webview.addEventListener('message',function(event){if(event.data.action==='pause-media')window.pauseMessageCount++;});</script>");
            for(int i=0;i<100 && !navigation.Task.IsCompleted;i++)await Task.Delay(25);
            Check(navigation.Task.IsCompleted && navigation.Task.Result,"isolated media lifecycle page loads inside real WebView");
            Field(window,"pageReady",true);
            var close=new FormClosingEventArgs(CloseReason.UserClosing,false);
            Call(window,"OnFormClosing",close);
            string pauseCount="0";
            for(int i=0;i<80 && pauseCount!="1";i++) {
                await Task.Delay(25);pauseCount=await web.CoreWebView2.ExecuteScriptAsync("window.pauseMessageCount");
            }
            Check(close.Cancel && !window.IsDisposed && !window.Visible && pauseCount=="1",
                "close to tray keeps window alive and posts exactly one pause-media message to real WebView");
            Check(!window.Visible,"offline zoom integration keeps the native window hidden");
            web.Dispose();
            for(int i=0;i<100 && !exited.Task.IsCompleted;i++) await Task.Delay(25);
            Check(exited.Task.IsCompleted,"isolated browser exits before temporary profile cleanup");
        }
        [MethodImpl(MethodImplOptions.NoInlining)]
        private static void Run()
        {
            using (var window = new StudioWindow(false))
            {
                window.Text = "映序桌面生命周期 · 合成测试";
                var tray = (NotifyIcon)Field(window,"tray");
                Check(tray.Visible && tray.ContextMenuStrip.Items.Count == 4,"tray icon and open/settings/exit menu exist");
                var zoom=(ToolStripStatusLabel)Field(window,"zoomStatus");
                Check(zoom.Text=="界面 100%"&&zoom.IsLink&&zoom.Owner==((ToolStripStatusLabel)Field(window,"status")).Owner,"independent zoom percentage keeps existing status messages in the same status bar");
                zoom.PerformClick();Check(zoom.Text=="界面 100%","zoom reset safely waits for WebView initialization");
                Call(window,"BringToUser"); Application.DoEvents();
                Check(window.Visible,"tray reopen restores visible window");
                window.Close(); Application.DoEvents();
                Check(!window.IsDisposed && !window.Visible,"default close hides window without disposing drafts");
                Call(window,"BringToUser"); Application.DoEvents();
                Check(window.Visible && !window.IsDisposed,"hidden window reopens with same instance");
                Field(window,"pageReady",true); Field(window,"loaded",true); Field(window,"closeToTray",false);
                window.Close(); Application.DoEvents();
                string request = (string)Field(window,"exitRequest");
                Check(!String.IsNullOrEmpty(request) && !window.IsDisposed,"close-to-tray off requests unsaved-draft approval before exit");
                var json = new JavaScriptSerializer();
                Call(window,"ReceiveDesktopRequest","https://example.com",json.Serialize(new {action="exit-response",requestId=request,allow=true}));
                Check((string)Field(window,"exitRequest")==request && !window.IsDisposed,"external exit response cannot close the editor");
                Call(window,"ReceiveDesktopRequest",Hub.Url,json.Serialize(new {action="exit-response",requestId="stale",allow=true}));
                Check((string)Field(window,"exitRequest")==request,"stale exit response is ignored");
                Call(window,"ReceiveDesktopRequest",Hub.Url,json.Serialize(new {action="exit-response",requestId=request,allow=false}));
                Check(Field(window,"exitRequest")==null && !window.IsDisposed,"cancelled draft approval preserves window");
                Call(window,"RequestExit"); request=(string)Field(window,"exitRequest");
                Call(window,"ReceiveDesktopRequest",Hub.Url,json.Serialize(new {action="exit-response",requestId=request,allow=true}));
                Application.DoEvents();
                Check(window.IsDisposed,"approved exit disposes the window");
                Check(!tray.Visible,"approved exit removes tray icon");
            }
            using (var capturing = new StudioWindow(false))
            {
                string contextRequest=null; int selections=0,registrations=0,unregisters=0;
                var fake=new CaptureCoordinator(message => {
                    var map=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(new JavaScriptSerializer().Serialize(message));
                    if((string)map["action"]=="capture-context-request")contextRequest=(string)map["requestId"];
                    return true;
                },(text,error)=>{},new CaptureServices {
                    ScreenBounds=()=>new Rectangle(-100,0,64,32),Select=bounds=>{selections++;return null;},
                    Copy=image=>{throw new Exception("Synthetic cancellation must never touch clipboard");},
                    Upload=(image,project)=>{throw new Exception("Synthetic cancellation must never upload");}
                });
                ((CaptureCoordinator)Field(capturing,"capture")).Dispose(); Field(capturing,"capture",fake);
                ((CaptureHotkey)Field(capturing,"captureHotkey")).Dispose();
                var keys=new CaptureHotkey((h,id,m,k)=>{registrations++;return true;},(h,id)=>unregisters++);
                Field(capturing,"captureHotkey",keys); Field(capturing,"captureEnabled",true);
                Call(capturing,"ApplyCaptureHotkey"); Call(capturing,"ApplyCaptureHotkey");
                Check(registrations==1,"window settings register one event hotkey without polling");
                Field(capturing,"captureEnabled",false); Call(capturing,"ApplyCaptureHotkey");
                Check(unregisters==1&&!keys.Registered,"turning background capture off unregisters global hotkey");
                var json=new JavaScriptSerializer();
                Check(!(bool)Call(capturing,"ReceiveDesktopRequest","https://example.com",json.Serialize(new{action="capture-request"})),"untrusted page cannot initiate capture");
                Call(capturing,"ReceiveDesktopRequest",Hub.Url,json.Serialize(new{action="capture-request"})); Application.DoEvents();
                Check(fake.Busy&&contextRequest!=null,"manual capture works while background hotkey is disabled");
                capturing.Close(); Application.DoEvents();
                Check(!capturing.IsDisposed&&fake.Busy,"titlebar close cannot dispose an active capture");
                Call(capturing,"RequestExit");
                Check(Field(capturing,"exitRequest")==null&&!capturing.IsDisposed,"exit during capture preserves editor and waits for completion");
                Call(capturing,"BringToUser");
                Check(!capturing.Visible&&(bool)Field(capturing,"showAfterCapture"),"explicit activation is deferred until capture completes");
                string response=json.Serialize(new{action="capture-context",requestId=contextRequest,projectId=(string)null,itemId=(string)null});
                Call(capturing,"ReceiveDesktopRequest","https://example.com",response);
                Check(selections==0&&fake.Busy,"untrusted context cannot complete the screenshot handshake");
                Call(capturing,"ReceiveDesktopRequest",Hub.Url,response); Application.DoEvents();
                Check(selections==1&&!fake.Busy&&capturing.Visible,"trusted cancellation releases busy state and honors deferred activation");
                Field(capturing,"exitApproved",true); capturing.Close(); Application.DoEvents();
            }
            bool approved = false;
            using (var failed = new StudioWindow(false,() => approved))
            {
                Field(failed,"loaded",true); Field(failed,"pageFailed",true); Field(failed,"pageReady",false);
                Call(failed,"RequestExit"); Application.DoEvents();
                Check(!failed.IsDisposed && Field(failed,"exitRequest")==null,"failed page exit cancellation preserves window without waiting on dead WebView");
                approved = true; Call(failed,"RequestExit"); Application.DoEvents();
                Check(failed.IsDisposed,"explicit native confirmation exits a failed page while leaving persisted draft files untouched");
            }
            approved = false;
            using (var failedClose = new StudioWindow(false,() => approved))
            {
                Field(failedClose,"loaded",true); Field(failedClose,"pageFailed",true);
                Call(failedClose,"BringToUser"); failedClose.Close(); Application.DoEvents();
                Check(failedClose.Visible && !failedClose.IsDisposed,"closing failed page asks for confirmation instead of hiding in tray");
                approved=true; failedClose.Close(); Application.DoEvents();
                Check(failedClose.IsDisposed,"failed page titlebar close exits after explicit confirmation");
            }
            using (var failedStartup = new StudioWindow(false,() => { throw new Exception("No editor draft exists"); }))
            {
                Field(failedStartup,"pageFailed",true);
                failedStartup.Close(); Application.DoEvents();
                Check(failedStartup.IsDisposed,"failed startup titlebar close exits directly when no editor ever loaded");
            }
            approved = false;
            using (var notReady = new StudioWindow(false,() => approved))
            {
                Field(notReady,"loaded",true); Field(notReady,"pageReady",false);
                Call(notReady,"RequestExit"); Application.DoEvents();
                Check(!notReady.IsDisposed,"loaded page without ready bridge preserves drafts when native exit is cancelled");
                approved = true; Call(notReady,"RequestExit"); Application.DoEvents();
                Check(notReady.IsDisposed,"loaded page without ready bridge can exit after explicit confirmation");
            }
            approved = false;
            using (var unresponsive = new StudioWindow(false,() => approved))
            {
                Field(unresponsive,"loaded",true); Field(unresponsive,"exitUnresponsive",true); Field(unresponsive,"pageReady",true);
                Call(unresponsive,"RequestExit"); Application.DoEvents();
                Check(!unresponsive.IsDisposed && Field(unresponsive,"exitRequest")==null,"timed-out exit requires native confirmation rather than another dead handshake");
                approved=true; Call(unresponsive,"RequestExit"); Application.DoEvents();
                Check(unresponsive.IsDisposed,"explicit native confirmation releases a timed-out page");
            }
        }
    }
}
