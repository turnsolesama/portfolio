using System;
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
[assembly: AssemblyVersion("0.2.2.0")]
[assembly: AssemblyFileVersion("0.2.2.0")]

namespace YingXu.Desktop
{
    internal static class Program
    {
        internal static EventWaitHandle ActivateEvent;
        internal static string LoaderFolder;

        [STAThread]
        private static int Main(string[] args)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            try
            {
                if (args.Length != 0 && !(args.Length == 2 && args[0] == "--root"))
                    throw new ArgumentException("支持的参数：YingXu.exe --root <映序程序目录>");
                Hub.Root = Hub.NormalizeRoot(args.Length == 2 ? args[1] : AppDomain.CurrentDomain.BaseDirectory);
                if (!Hub.IsAppRoot(Hub.Root))
                    throw new DirectoryNotFoundException("请把 YingXu.exe 放在映序程序文件夹内，与 server.py、launcher.pyw 和 frontend 同级。桌面请使用快捷方式。");
                Hub.Port = 8791;
                Hub.Url = "http://127.0.0.1:" + Hub.Port + "/";
                string id = Hub.Identity((Hub.Root + "|" + Hub.Data).ToUpperInvariant()).Substring(0, 24);
                // Keep the desktop profile with this installation. Packaged launchers
                // can virtualize LocalAppData, producing a different profile from Explorer.
                Hub.Cache = Path.Combine(Hub.Data, "desktop");
                Directory.CreateDirectory(Hub.Cache);
                using (var mutex = new Mutex(false, @"Local\YingXu-desktop-" + id))
                using (ActivateEvent = new EventWaitHandle(false, EventResetMode.AutoReset, @"Local\YingXu-desktop-show-" + id))
                {
                    bool owner;
                    try { owner = mutex.WaitOne(0); } catch (AbandonedMutexException) { owner = true; }
                    if (!owner) { ActivateEvent.Set(); Hub.Log("desktop_reused"); return 0; }
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

        internal StudioWindow()
        {
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
            loading = new Label { Dock = DockStyle.Fill, TextAlign = ContentAlignment.MiddleCenter,
                Text = "映序\n\n正在打开本地工作空间…", Font = new Font("Microsoft YaHei UI", 15F) };
            Controls.Add(loading);
            var bar = new StatusStrip { BackColor = Color.FromArgb(246, 247, 245), ForeColor = Color.FromArgb(104, 115, 108), SizingGrip = true };
            status = new ToolStripStatusLabel("本地工作台 · 关闭窗口后，后台服务与导入任务继续运行") { Spring = true, TextAlign = ContentAlignment.MiddleLeft };
            bar.Items.Add(status);
            Controls.Add(bar);
            RestoreWindow();
            activation = ThreadPool.RegisterWaitForSingleObject(Program.ActivateEvent, delegate
            {
                if (IsDisposed || !IsHandleCreated) return;
                try { BeginInvoke((Action)BringToUser); } catch (InvalidOperationException) { }
            }, null, Timeout.Infinite, false);
            Shown += async delegate { await InitializeAsync(); };
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
        }

        private void BringToUser()
        {
            if (WindowState == FormWindowState.Minimized) WindowState = FormWindowState.Normal;
            Show();
            Activate();
            SetForegroundWindow(Handle);
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
                var options = new CoreWebView2EnvironmentOptions();
                options.Language = "zh-CN";
                var environment = await CoreWebView2Environment.CreateAsync(null, Path.Combine(Hub.Cache, "WebView2"), options);
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
                core.NavigationStarting += delegate(object sender, CoreWebView2NavigationStartingEventArgs e)
                {
                    if (Hub.IsLocalPage(e.Uri, Hub.Url)) return;
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
            if (web != null) web.Visible = false;
            loading.Visible = true;
            loading.Text = "映序\n\n工作台未能打开\n\n请关闭窗口后重试。";
            loading.BringToFront();
            MessageBox.Show(this, message, "映序 · 启动提示", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }

        private async void ReceiveDragRequest(object sender, CoreWebView2WebMessageReceivedEventArgs e)
        {
            string itemId;
            if (draggingFile || closing.IsCancellationRequested || web == null ||
                !Hub.IsLocalPage(web.CoreWebView2.Source, Hub.Url) ||
                !Hub.TryReadDragMessage(e.Source, e.WebMessageAsJson, out itemId)) return;
            if ((Control.MouseButtons & MouseButtons.Left) == 0)
            {
                status.Text = "请按住素材的拖出手柄，再拖到资源管理器或剪辑软件。";
                return;
            }
            draggingFile = true;
            try
            {
                status.Text = "正在准备真实文件，请继续按住鼠标左键…";
                string path = await Task.Run(() => Hub.NativeFilePath(itemId));
                if (closing.IsCancellationRequested || web.IsDisposed) return;
                if ((Control.MouseButtons & MouseButtons.Left) == 0)
                {
                    status.Text = "已取消拖出；请按住手柄直到文件进入目标窗口。";
                    return;
                }
                // Recheck immediately before handing the file to Windows OLE.
                path = Hub.ValidateNativeFilePath(path);
                var data = new DataObject(DataFormats.FileDrop, new string[] { path });
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
            finally { draggingFile = false; }
        }

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
            closing.Cancel();
            activation.Unregister(null);
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
