using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

[assembly: AssemblyTitle("映序")]
[assembly: AssemblyDescription("映序 本地视频创作项目工作台")]
[assembly: AssemblyProduct("映序桌面版")]
[assembly: AssemblyVersion("0.3.5.0")]
[assembly: AssemblyFileVersion("0.3.5.0")]

namespace YingXu.Desktop
{
    internal static class Program
    {
        internal static EventWaitHandle ActivateEvent;
        internal static string LoaderFolder;
        internal static string InstanceKey;
        internal static string[] InitialFiles;

        [STAThread]
        private static int Main(string[] args)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            try
            {
                var launch = LaunchOptions.Parse(args, AppDomain.CurrentDomain.BaseDirectory);
                Hub.Root = Hub.NormalizeRoot(launch.Root);
                if (!Hub.IsAppRoot(Hub.Root))
                    throw new DirectoryNotFoundException("请把 YingXu.exe 放在映序程序文件夹内，与 server.py、launcher.pyw 和 frontend 同级。桌面请使用快捷方式。");
                if (launch.Registration != null)
                {
                    MessageBox.Show(OpenWithRegistration.Change(launch.Registration == "--register-open-with"), "映序", MessageBoxButtons.OK, MessageBoxIcon.Information);
                    return 0;
                }
                InitialFiles = launch.Paths;
                Hub.Port = 8791;
                Hub.Url = "http://127.0.0.1:" + Hub.Port + "/";
                string id = Hub.Identity((Hub.Root + "|" + Hub.Data).ToUpperInvariant()).Substring(0, 24);
                InstanceKey = id;
                // Keep the desktop profile with this installation. Packaged launchers
                // can virtualize LocalAppData, producing a different profile from Explorer.
                Hub.Cache = Path.Combine(Hub.Data, "desktop");
                Directory.CreateDirectory(Hub.Cache);
                using (var mutex = new Mutex(false, @"Local\YingXu-desktop-" + id))
                using (ActivateEvent = new EventWaitHandle(false, EventResetMode.AutoReset, @"Local\YingXu-desktop-show-" + id))
                {
                    bool owner;
                    try { owner = mutex.WaitOne(0); } catch (AbandonedMutexException) { owner = true; }
                    if (!owner)
                    {
                        ActivateEvent.Set();
                        if (InitialFiles.Length != 0) OpenInbox.Send(id,InitialFiles);
                        Hub.Log("desktop_reused"); return 0;
                    }
                    try
                    {
                        SetCurrentProcessExplicitAppUserModelID("YingXu.Desktop");
                        PrepareLibraries();
                        Hub.Log("desktop_started pid=" + Process.GetCurrentProcess().Id);
                        RunWindow();
                        return 0;
                    }
                    finally { mutex.ReleaseMutex(); }
                }
            }
            catch (Exception e)
            {
                Hub.Log("desktop_error " + e.GetType().Name + ": " + e.Message);
                MessageBox.Show(e.Message, "映序 · 启动提示", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return 1;
            }
        }

        private static byte[] Resource(string name)
        {
            using (var source = Assembly.GetExecutingAssembly().GetManifestResourceStream(name))
            using (var memory = new MemoryStream())
            {
                if (source == null) throw new InvalidDataException("EXE 内缺少运行组件：" + name);
                source.CopyTo(memory);
                return memory.ToArray();
            }
        }

        private static void PrepareLibraries()
        {
            AppDomain.CurrentDomain.AssemblyResolve += delegate(object sender, ResolveEventArgs e)
            {
                string name = new AssemblyName(e.Name).Name;
                if (name != "Microsoft.Web.WebView2.Core" && name != "Microsoft.Web.WebView2.WinForms") return null;
                return Assembly.Load(Resource(name + ".dll"));
            };
            byte[] loader = Resource("WebView2Loader.dll");
            string digest;
            using (var sha = System.Security.Cryptography.SHA256.Create())
                digest = BitConverter.ToString(sha.ComputeHash(loader)).Replace("-", "");
            LoaderFolder = Path.Combine(Hub.Cache, "loader", digest);
            Directory.CreateDirectory(LoaderFolder);
            string target = Path.Combine(LoaderFolder, "WebView2Loader.dll");
            if (!File.Exists(target)) File.WriteAllBytes(target, loader);
            else
            {
                using (var sha = System.Security.Cryptography.SHA256.Create())
                    if (BitConverter.ToString(sha.ComputeHash(File.ReadAllBytes(target))).Replace("-", "") != digest)
                        File.WriteAllBytes(target, loader);
            }
        }

        // Resolve embedded WebView2 assemblies before the JIT sees the window type.
        [MethodImpl(MethodImplOptions.NoInlining)]
        private static void RunWindow()
        {
            CoreWebView2Environment.SetLoaderDllFolderPath(LoaderFolder);
            Application.Run(new StudioWindow());
        }

        [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
        private static extern int SetCurrentProcessExplicitAppUserModelID(string id);
    }

    internal sealed class WindowStateRecord
    {
        public int X { get; set; }
        public int Y { get; set; }
        public int Width { get; set; }
        public int Height { get; set; }
        public bool Maximized { get; set; }
    }

    internal sealed class StudioWindow : Form
    {
        private WebView2 web;
        private readonly Label loading;
        private readonly ToolStripStatusLabel status;
        private readonly RegisteredWaitHandle activation;
        private readonly CancellationTokenSource closing = new CancellationTokenSource();
        private bool loaded;
        private bool draggingFile;
        private bool nativeDragReleased;
        private string preparedDragKey;
        private Task<string[]> preparedDragPaths;
        private readonly NotifyIcon tray;
        private readonly OpenInbox inbox;
        private readonly Queue<string[]> pendingFiles = new Queue<string[]>();
        private bool pageReady;
        private bool closeToTray = true;
        private bool exitApproved;
        private bool settingsPending;
        private string exitRequest;
        private readonly System.Windows.Forms.Timer exitTimer;
        private bool openingFiles;
        private bool pageFailed;
        private bool exitUnresponsive;
        private readonly Func<bool> confirmUnavailableExit;
        private CaptureCoordinator capture;
        private CaptureHotkey captureHotkey;
        private bool captureEnabled;
        private string captureShortcut = CaptureHotkey.Default;
        private int settingsRevision;
        private bool showAfterCapture;

        internal StudioWindow(bool initialize = true, Func<bool> failedExitConfirmation = null)
        {
            confirmUnavailableExit = failedExitConfirmation ?? (() => MessageBox.Show(this,
                "工作台页面已失去响应，无法完成页面保存。已落盘的草稿会保留，尚未保存的内容可能丢失。\n\n仍要退出映序吗？",
                "映序 · 确认退出",MessageBoxButtons.YesNo,MessageBoxIcon.Warning,MessageBoxDefaultButton.Button2) == DialogResult.Yes);
            Text = "映序 · 视频创作工作台";
            BackColor = Color.White;
            ForeColor = Color.FromArgb(40, 50, 45);
            Font = new Font("Microsoft YaHei UI", 10F);
            AutoScaleMode = AutoScaleMode.Dpi;
            MinimumSize = new Size(1120, 720);
            ClientSize = new Size(1440, 900);
            StartPosition = FormStartPosition.CenterScreen;
            using (var source = Assembly.GetExecutingAssembly().GetManifestResourceStream("brand.ico"))
                Icon = new Icon(source);
            var trayMenu = new ContextMenuStrip();
            trayMenu.Items.Add("打开映序",null,delegate { BringToUser(); });
            trayMenu.Items.Add("设置",null,delegate { BringToUser(); settingsPending = true; FlushSettings(); });
            trayMenu.Items.Add(new ToolStripSeparator());
            trayMenu.Items.Add("退出映序",null,delegate { RequestExit(); });
            tray = new NotifyIcon { Icon = Icon, Text = "映序 · 本地创作工作台", ContextMenuStrip = trayMenu, Visible = true };
            tray.DoubleClick += delegate { BringToUser(); };
            exitTimer = new System.Windows.Forms.Timer { Interval = 120000 };
            exitTimer.Tick += delegate { exitTimer.Stop(); exitRequest = null; exitUnresponsive = true; Notice("页面没有完成退出确认，窗口已保留。可再次选择退出，核对故障退出提示。",true); };
            loading = new Label { Dock = DockStyle.Fill, TextAlign = ContentAlignment.MiddleCenter,
                Text = "映序\n\n正在打开本地工作空间…", Font = new Font("Microsoft YaHei UI", 15F) };
            Controls.Add(loading);
            var bar = new StatusStrip { BackColor = Color.FromArgb(246, 247, 245), ForeColor = Color.FromArgb(104, 115, 108), SizingGrip = true };
            status = new ToolStripStatusLabel("本地工作台 · 关闭窗口默认保留在托盘，可从设置调整") { Spring = true, TextAlign = ContentAlignment.MiddleLeft };
            bar.Items.Add(status);
            Controls.Add(bar);
            RestoreWindow();
            if (Program.InitialFiles != null && Program.InitialFiles.Length != 0) pendingFiles.Enqueue(Program.InitialFiles);
            // Create the window handle before receiving requests from other instances.
            IntPtr initializedHandle = Handle;
            captureHotkey = new CaptureHotkey();
            capture = new CaptureCoordinator(PostCapture,CaptureNotice);
            inbox = new OpenInbox(Program.InstanceKey,delegate(string[] paths)
            {
                if (IsDisposed || closing.IsCancellationRequested) throw new IOException("映序正在退出，请重新打开。");
                BeginInvoke((Action)(() => { BringToUser(); if (paths.Length != 0) pendingFiles.Enqueue(paths); DrainFiles(); }));
            });
            activation = ThreadPool.RegisterWaitForSingleObject(Program.ActivateEvent, delegate
            {
                if (IsDisposed || !IsHandleCreated) return;
                try { BeginInvoke((Action)BringToUser); } catch (InvalidOperationException) { }
            }, null, Timeout.Infinite, false);
            if (initialize) Shown += async delegate { await InitializeAsync(); };
        }

        protected override void OnHandleCreated(EventArgs e)
        {
            base.OnHandleCreated(e);
            try
            {
                int dark = 0;
                DwmSetWindowAttribute(Handle, 20, ref dark, sizeof(int));
                int caption = 0x00ffffff;
                DwmSetWindowAttribute(Handle, 35, ref caption, sizeof(int));
            }
            catch (DllNotFoundException) { }
            if (captureHotkey != null) ApplyCaptureHotkey();
        }

        protected override void OnHandleDestroyed(EventArgs e)
        {
            if (captureHotkey != null) captureHotkey.Dispose();
            base.OnHandleDestroyed(e);
        }
        protected override void WndProc(ref Message message)
        {
            if (message.Msg == CaptureHotkey.Message && message.WParam.ToInt32() == CaptureHotkey.Id && captureHotkey != null && captureHotkey.Registered)
            { StartCapture(); return; }
            base.WndProc(ref message);
        }
        protected override void Dispose(bool disposing)
        {
            if (disposing) { if (capture != null) capture.Dispose(); if (captureHotkey != null) captureHotkey.Dispose(); }
            base.Dispose(disposing);
        }
        private bool PostCapture(object message)
        {
            if (!pageReady || web == null || web.IsDisposed || closing.IsCancellationRequested) return false;
            Post(message); return pageReady;
        }
        private void CaptureNotice(string message,bool error)
        {
            if (IsDisposed || closing.IsCancellationRequested) return;
            status.Text=message;
            if (Visible) { if(pageReady) Post(new {action="desktop-notice",message=message,error=error}); }
            else tray.ShowBalloonTip(3500,"映序 · 截图",message,error ? ToolTipIcon.Warning : ToolTipIcon.Info);
        }
        private void ApplyCaptureHotkey()
        {
            if (!IsHandleCreated || captureHotkey==null) return;
            string error=captureHotkey.Configure(Handle,captureEnabled,captureShortcut);
            if(error!=null) CaptureNotice(error,true);
        }
        private async void StartCapture()
        {
            if (capture==null || capture.Busy || closing.IsCancellationRequested || exitRequest!=null || exitApproved || draggingFile || openingFiles) return;
            try { await capture.StartAsync(); }
            finally
            {
                if (!IsDisposed && !closing.IsCancellationRequested)
                {
                    if (showAfterCapture) { showAfterCapture=false; BringToUser(); }
                    FlushSettings(); DrainFiles();
                }
            }
        }

        private void BringToUser()
        {
            if (capture != null && capture.Busy) { showAfterCapture=true; return; }
            if (WindowState == FormWindowState.Minimized) WindowState = FormWindowState.Normal;
            Show();
            Activate();
            SetForegroundWindow(Handle);
        }

        private void Post(object message)
        {
            if (!pageReady || web == null || web.IsDisposed || closing.IsCancellationRequested) return;
            try { web.CoreWebView2.PostWebMessageAsJson(new JavaScriptSerializer().Serialize(message)); }
            catch (InvalidOperationException) { pageFailed = true; pageReady = false; }
            catch (COMException) { pageFailed = true; pageReady = false; }
        }

        private void Notice(string message, bool error = false)
        {
            status.Text = message;
            if (pageReady) Post(new { action = "desktop-notice", message = message, error = error });
            else MessageBox.Show(this,message,"映序",MessageBoxButtons.OK,error ? MessageBoxIcon.Warning : MessageBoxIcon.Information);
        }

        private async void ReloadSettings()
        {
            int revision=++settingsRevision;
            try
            {
                var settings=await Task.Run(() => DesktopApi.Request("/api/settings"));
                if(revision!=settingsRevision || IsDisposed || closing.IsCancellationRequested) return;
                object value;
                closeToTray=!settings.TryGetValue("close_to_tray",out value) || !(value is bool) || (bool)value;
                captureEnabled=!settings.TryGetValue("capture_enabled",out value) || !(value is bool) || (bool)value;
                captureShortcut=settings.TryGetValue("capture_hotkey",out value) && value is string ? (string)value : CaptureHotkey.Default;
                ApplyCaptureHotkey();
            }
            catch (Exception error) { Hub.Log("desktop_settings_error " + error.GetType().Name); }
        }

        private void FlushSettings()
        {
            if (pageReady && settingsPending && (capture==null || !capture.Busy)) { settingsPending = false; Post(new { action = "open-settings" }); }
        }

        private async void DrainFiles()
        {
            if (!pageReady || openingFiles || closing.IsCancellationRequested || (capture!=null && capture.Busy)) return;
            openingFiles = true;
            try
            {
                while (pendingFiles.Count != 0 && !closing.IsCancellationRequested)
                {
                    string[] paths = pendingFiles.Dequeue();
                    try
                    {
                        object entries = await Task.Run(() => DesktopApi.OpenFiles(paths));
                        if (!pageReady) { pendingFiles.Enqueue(paths); break; }
                        Post(new { action = "external-open", entries = entries });
                    }
                    catch (Exception error) { Notice("文件未能打开：" + error.Message,true); }
                }
            }
            finally { openingFiles = false; }
        }

        private void ChooseFiles()
        {
            using (var dialog = new OpenFileDialog { Title = "用映序只读打开文件", Multiselect = true,
                Filter = "可预览文件|*.md;*.markdown;*.txt;*.json;*.csv;*.srt;*.vtt;*.docx;*.pdf;*.png;*.jpg;*.jpeg;*.webp;*.gif;*.bmp;*.mp4;*.mov;*.webm;*.mkv;*.avi;*.m4v;*.mp3;*.wav;*.ogg;*.flac;*.m4a;*.aac|所有文件|*.*" })
                if (dialog.ShowDialog(this) == DialogResult.OK)
                {
                    if (dialog.FileNames.Length > 32) { Notice("一次最多打开 32 个文件。",true); return; }
                    pendingFiles.Enqueue(dialog.FileNames); DrainFiles();
                }
        }

        private void RequestExit()
        {
            if (capture!=null && capture.Busy) { CaptureNotice("截图正在处理，请先完成选区或按 Esc 取消，再退出映序。",true); return; }
            if (exitRequest != null || exitApproved) return;
            BringToUser();
            if (pageFailed || exitUnresponsive)
            {
                if (!loaded || confirmUnavailableExit()) { exitApproved = true; Close(); }
                return;
            }
            if (!pageReady)
            {
                // No loaded editor exists, so there cannot be an unsaved browser draft.
                if (loaded)
                {
                    if (confirmUnavailableExit()) { exitApproved = true; Close(); }
                    return;
                }
                exitApproved = true; Close(); return;
            }
            exitRequest = Guid.NewGuid().ToString("N"); exitTimer.Start();
            Post(new { action = "prepare-exit", requestId = exitRequest });
        }

        private bool ReceiveDesktopRequest(string source, string json)
        {
            if (!Hub.IsLocalPage(source,Hub.Url) || String.IsNullOrEmpty(json) || json.Length > 4096) return false;
            Dictionary<string,object> message;
            try { message = new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(json); }
            catch { return false; }
            object value; if (message == null || !message.TryGetValue("action",out value) || !(value is string)) return false;
            string action = (string)value;
            if (action == "desktop-ready") { pageReady = true; pageFailed = false; exitUnresponsive = false; ReloadSettings(); if(capture!=null)capture.Flush(); FlushSettings(); DrainFiles(); return true; }
            if (action == "capture-request" && message.Count==1) { BeginInvoke((Action)StartCapture); return true; }
            if (action == "capture-context") { if(capture!=null)capture.Receive(message); return true; }
            if (action == "settings-changed") { ReloadSettings(); return true; }
            if (action == "choose-external-files") { BeginInvoke((Action)ChooseFiles); return true; }
            if (action == "register-open-with" || action == "unregister-open-with")
            {
                try { Notice(OpenWithRegistration.Change(action == "register-open-with")); }
                catch (Exception error) { Notice(error.Message,true); }
                return true;
            }
            if (action == "exit-response")
            {
                object request, allow;
                if (message.TryGetValue("requestId",out request) && (request as string) == exitRequest && exitRequest != null &&
                    message.TryGetValue("allow",out allow) && allow is bool)
                {
                    exitTimer.Stop(); exitRequest = null;
                    if ((bool)allow) { exitApproved = true; BeginInvoke((Action)Close); }
                }
                return true;
            }
            return false;
        }

        private async Task InitializeAsync()
        {
            try
            {
                string serviceStatus = await Task.Run(() => Hub.EnsureService());
                if (closing.IsCancellationRequested) return;
                Hub.Log("service_" + serviceStatus + " port=" + Hub.Port);
                loading.Text = "映序\n\n正在加载工作台…";
                web = new WebView2 { Dock = DockStyle.Fill, DefaultBackgroundColor = BackColor };
                Controls.Add(web);
                web.QueryContinueDrag += delegate(object sender, QueryContinueDragEventArgs e)
                {
                    nativeDragReleased = !e.EscapePressed && (e.KeyState & 1) == 0;
                };
                var options = new CoreWebView2EnvironmentOptions();
                options.Language = "zh-CN";
                string bundledBrowser = Hub.BundledBrowserFolder();
                string browserFolder = bundledBrowser;
                if (Environment.GetEnvironmentVariable("YINGXU_WEBVIEW2_MODE") != "bundled")
                {
                    try
                    {
                        string installed = CoreWebView2Environment.GetAvailableBrowserVersionString();
                        if (bundledBrowser == null || CoreWebView2Environment.CompareBrowserVersions(installed,
                            CoreWebView2Environment.GetAvailableBrowserVersionString(bundledBrowser)) >= 0) browserFolder = null;
                    }
                    catch (WebView2RuntimeNotFoundException) { }
                }
                if (browserFolder != null) await Task.Run(() => Hub.PrepareBrowserFolder(browserFolder));
                Hub.Log("browser_source=" + (browserFolder == null ? "system" : "bundled"));
                var environment = await CoreWebView2Environment.CreateAsync(browserFolder, Path.Combine(Hub.Cache, "WebView2"), options);
                if (closing.IsCancellationRequested) return;
                await web.EnsureCoreWebView2Async(environment);
                if (closing.IsCancellationRequested) return;
                var core = web.CoreWebView2;
                core.Profile.PreferredColorScheme = CoreWebView2PreferredColorScheme.Light;
                core.Settings.IsStatusBarEnabled = false;
                core.Settings.AreDefaultContextMenusEnabled = false;
                core.Settings.AreBrowserAcceleratorKeysEnabled = false;
                core.Settings.AreDevToolsEnabled = false;
                core.Settings.AreHostObjectsAllowed = false;
                core.Settings.IsWebMessageEnabled = true;
                core.Settings.IsPasswordAutosaveEnabled = false;
                core.Settings.IsGeneralAutofillEnabled = false;
                core.WebMessageReceived += ReceiveDragRequest;
                await core.AddScriptToExecuteOnDocumentCreatedAsync("window.yingxuDesktopDrag = true;");
                core.NavigationStarting += delegate(object sender, CoreWebView2NavigationStartingEventArgs e)
                {
                    if (Hub.IsLocalPage(e.Uri, Hub.Url)) { pageReady = false; return; }
                    e.Cancel = true;
                    status.Text = "已阻止打开外部地址；映序只显示本地创作工作台。";
                };
                core.NewWindowRequested += delegate(object sender, CoreWebView2NewWindowRequestedEventArgs e)
                {
                    e.Handled = true;
                    status.Text = "已阻止打开外部地址；映序只显示本地创作工作台。";
                };
                core.PermissionRequested += delegate(object sender, CoreWebView2PermissionRequestedEventArgs e)
                {
                    // Copying model paths works with the ordinary user-gesture clipboard API.
                    // This app does not require camera, mic, location or clipboard-read access.
                    e.State = CoreWebView2PermissionState.Deny;
                };
                core.DownloadStarting += delegate(object sender, CoreWebView2DownloadStartingEventArgs e)
                {
                    e.Cancel = true;
                    MessageBox.Show(this, "此工作台不提供网页下载。请使用导入功能引用已有素材。", "映序", MessageBoxButtons.OK, MessageBoxIcon.Information);
                };
                core.ProcessFailed += delegate
                {
                    if (!closing.IsCancellationRequested) ShowFailure("页面运行环境意外退出。请关闭窗口后重新打开 映序。");
                };
                core.NavigationCompleted += delegate(object sender, CoreWebView2NavigationCompletedEventArgs e)
                {
                    if (closing.IsCancellationRequested) return;
                    if (!e.IsSuccess)
                    {
                        if (e.WebErrorStatus != CoreWebView2WebErrorStatus.OperationCanceled)
                            ShowFailure("工作台页面加载失败，请重新打开 映序。错误：" + e.WebErrorStatus);
                        return;
                    }
                    loading.Visible = false;
                    web.BringToFront();
                    if (!loaded)
                    {
                        loaded = true;
                        Hub.Log("window_ready runtime=" + environment.BrowserVersionString + " console=" + (GetConsoleWindow() != IntPtr.Zero));
                        web.Focus();
                    }
                };
                core.Navigate(Hub.Url);
            }
            catch (Exception e)
            {
                if (closing.IsCancellationRequested) return;
                Hub.Log("window_error " + e.GetType().Name + ": " + e.Message);
                ShowFailure(e is WebView2RuntimeNotFoundException ?
                    "未找到 Microsoft Edge WebView2 运行环境。请安装微软官方 WebView2 Runtime 后再打开。" : e.Message);
            }
        }

        private void ShowFailure(string message)
        {
            pageFailed = true; pageReady = false;
            exitTimer.Stop(); exitRequest = null;
            if (web != null) web.Visible = false;
            loading.Visible = true;
            loading.Text = "映序\n\n工作台未能打开\n\n请关闭窗口后重试。";
            loading.BringToFront();
            MessageBox.Show(this, message, "映序 · 启动提示", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }

        private async void ReceiveDragRequest(object sender, CoreWebView2WebMessageReceivedEventArgs e)
        {
            if (ReceiveDesktopRequest(e.Source,e.WebMessageAsJson)) return;
            string[] itemIds;
            if (draggingFile || closing.IsCancellationRequested || web == null ||
                !Hub.IsLocalPage(web.CoreWebView2.Source, Hub.Url)) return;
            if (Hub.TryReadFileIdsMessage(e.Source, e.WebMessageAsJson, "prepare-drag-files", out itemIds))
            {
                try { await PrepareNativeDrag(itemIds); } catch { /* The actual drag reports preparation errors. */ }
                return;
            }
            if (!Hub.TryReadDragItemsMessage(e.Source, e.WebMessageAsJson, out itemIds)) return;
            if ((GetAsyncKeyState(1) & 0x8000) == 0)
            {
                status.Text = "请按住素材，再拖到目标位置。";
                FinishNativeDrag();
                return;
            }
            draggingFile = true;
            nativeDragReleased = false;
            try
            {
                status.Text = "正在准备真实文件，请继续按住鼠标左键…";
                // Yield out of the WebView2 callback before starting the Windows OLE loop.
                string[] paths = await PrepareNativeDrag(itemIds);
                // Even a cached lookup must leave the WebView2 event before the OLE loop.
                await Task.Yield();
                if (closing.IsCancellationRequested || web.IsDisposed) return;
                if ((GetAsyncKeyState(1) & 0x8000) == 0)
                {
                    status.Text = "已取消拖拽；请按住素材直到文件进入目标位置。";
                    return;
                }
                // Recheck immediately before handing the file to Windows OLE.
                paths = Array.ConvertAll(paths, Hub.ValidateNativeFilePath);
                var data = new DataObject(DataFormats.FileDrop, paths);
                DragDropEffects effect = web.DoDragDrop(data, DragDropEffects.Copy);
                status.Text = effect == DragDropEffects.Copy ?
                    "已将文件交给目标应用；原素材保留在原位置。" : "拖出已结束；原素材保留在原位置。";
                Hub.Log(effect == DragDropEffects.Copy ? "native_drag_copy" : "native_drag_ended");
            }
            catch (Exception error)
            {
                if (!closing.IsCancellationRequested)
                    status.Text = error is WebException ? "素材暂时无法拖出，请确认后台服务正常并重新打开素材。" : error.Message;
                Hub.Log("native_drag_error " + error.GetType().Name);
            }
            finally { draggingFile = false; preparedDragPaths = null; preparedDragKey = null; FinishNativeDrag(nativeDragReleased); }
        }

        private Task<string[]> PrepareNativeDrag(string[] ids)
        {
            string key = String.Join(",", ids);
            if (preparedDragPaths == null || preparedDragKey != key || preparedDragPaths.IsFaulted)
            {
                preparedDragKey = key;
                preparedDragPaths = Task.Run(() => {
                    var paths = new string[ids.Length];
                    Parallel.For(0, ids.Length, new ParallelOptions { MaxDegreeOfParallelism = 4 }, index => paths[index] = Hub.NativeFilePath(ids[index]));
                    return paths;
                });
            }
            return preparedDragPaths;
        }

        [DllImport("user32.dll")]
        private static extern short GetAsyncKeyState(int key);

        private void FinishNativeDrag(bool released = false)
        {
            if (closing.IsCancellationRequested || web == null || web.IsDisposed) return;
            try
            {
                Point screen = Cursor.Position;
                Point local = web.PointToClient(screen);
                IntPtr target = WindowFromPoint(screen);
                bool inside = web.ClientRectangle.Contains(local) && (target == web.Handle || IsChild(web.Handle, target));
                web.CoreWebView2.PostWebMessageAsJson(new JavaScriptSerializer().Serialize(new {
                    action = "native-drag-ended", released = released, inside = inside,
                    x = local.X, y = local.Y, width = web.ClientSize.Width, height = web.ClientSize.Height
                }));
            }
            catch (InvalidOperationException) { }
        }

        [DllImport("user32.dll")]
        private static extern IntPtr WindowFromPoint(Point point);
        [DllImport("user32.dll")]
        private static extern bool IsChild(IntPtr parent, IntPtr child);

        private void RestoreWindow()
        {
            try
            {
                string file = Path.Combine(Hub.Cache, "window.json");
                if (!File.Exists(file)) return;
                var state = new JavaScriptSerializer().Deserialize<WindowStateRecord>(File.ReadAllText(file));
                var rectangle = new Rectangle(state.X, state.Y, Math.Max(1120, state.Width), Math.Max(720, state.Height));
                foreach (Screen screen in Screen.AllScreens)
                {
                    Rectangle visible = Rectangle.Intersect(screen.WorkingArea, rectangle);
                    if (visible.Width < 160 || visible.Height < 100) continue;
                    StartPosition = FormStartPosition.Manual;
                    Bounds = new Rectangle(
                        Math.Max(screen.WorkingArea.Left, Math.Min(rectangle.X, screen.WorkingArea.Right - 160)),
                        Math.Max(screen.WorkingArea.Top, Math.Min(rectangle.Y, screen.WorkingArea.Bottom - 100)),
                        Math.Min(rectangle.Width, screen.WorkingArea.Width), Math.Min(rectangle.Height, screen.WorkingArea.Height));
                    if (state.Maximized) WindowState = FormWindowState.Maximized;
                    return;
                }
            }
            catch { }
        }

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            base.OnFormClosing(e);
            if (e.Cancel) return;
            if (capture!=null && capture.Busy) { e.Cancel=true; CaptureNotice("截图正在处理，请先完成或取消截图。",true); return; }
            if (!exitApproved)
            {
                e.Cancel = true;
                if (e.CloseReason == CloseReason.UserClosing && closeToTray && !pageFailed && !exitUnresponsive) { Hide(); return; }
                RequestExit(); return;
            }
            closing.Cancel();
            activation.Unregister(null);
            inbox.Dispose(); exitTimer.Stop(); exitTimer.Dispose();
            tray.Visible = false; tray.ContextMenuStrip.Dispose(); tray.Dispose();
            try
            {
                Rectangle bounds = WindowState == FormWindowState.Normal ? Bounds : RestoreBounds;
                var state = new WindowStateRecord { X = bounds.X, Y = bounds.Y, Width = bounds.Width, Height = bounds.Height,
                    Maximized = WindowState == FormWindowState.Maximized };
                File.WriteAllText(Path.Combine(Hub.Cache, "window.json"), new JavaScriptSerializer().Serialize(state), Encoding.UTF8);
            }
            catch { }
            // The shared backend can be doing a scan. Window lifetime must not terminate it.
            if (web != null) web.Dispose();
            Hub.Log("window_closed service_preserved");
        }

        [DllImport("dwmapi.dll")]
        private static extern int DwmSetWindowAttribute(IntPtr hwnd, int attribute, ref int value, int size);
        [DllImport("user32.dll")]
        private static extern bool SetForegroundWindow(IntPtr hwnd);
        [DllImport("kernel32.dll")]
        private static extern IntPtr GetConsoleWindow();
    }
}
