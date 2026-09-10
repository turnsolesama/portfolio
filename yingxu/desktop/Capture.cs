using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Runtime.InteropServices;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace YingXu.Desktop
{
    internal sealed class CaptureHotkey : IDisposable
    {
        internal const int Message = 0x0312;
        internal const int Id = 0x5943;
        internal const string Default = "Ctrl+Alt+Shift+S";
        private readonly Func<IntPtr,int,uint,uint,bool> register;
        private readonly Action<IntPtr,int> unregister;
        private IntPtr window;
        private string current;
        internal bool Registered { get; private set; }
        internal CaptureHotkey(Func<IntPtr,int,uint,uint,bool> add = null, Action<IntPtr,int> remove = null)
        {
            register = add ?? RegisterHotKey;
            unregister = remove ?? ((handle,id) => { UnregisterHotKey(handle,id); });
        }
        internal static bool TryParse(string value, out uint modifiers, out uint key)
        {
            modifiers = 0; key = 0;
            if (String.IsNullOrWhiteSpace(value) || value.Length > 64) return false;
            string[] parts = value.Split('+');
            if (parts.Length < 3 || parts.Length > 4) return false;
            for (int i=0;i<parts.Length-1;i++)
            {
                string part = parts[i].Trim().ToUpperInvariant();
                uint flag = part == "CTRL" ? 2u : part == "ALT" ? 1u : part == "SHIFT" ? 4u : 0u;
                if (flag == 0 || (modifiers & flag) != 0) return false;
                modifiers |= flag;
            }
            string last = parts[parts.Length-1].Trim().ToUpperInvariant();
            if (last.Length == 1 && ((last[0] >= 'A' && last[0] <= 'Z') || (last[0] >= '0' && last[0] <= '9'))) key = last[0];
            else if (last.StartsWith("F",StringComparison.Ordinal))
            {
                int number;
                if (!Int32.TryParse(last.Substring(1),out number) || last != "F"+number || number < 1 || number > 24 || number == 12) return false;
                key = (uint)(0x70+number-1);
            }
            if (key == 0) return false;
            modifiers |= 0x4000; // MOD_NOREPEAT: no repeated capture while held.
            return true;
        }
        internal string Configure(IntPtr handle, bool enabled, string value)
        {
            if (enabled && Registered && window == handle && current == value) return null;
            Dispose();
            if (!enabled) return null;
            uint modifiers,key;
            if (!TryParse(value,out modifiers,out key)) return "截图快捷键格式无效，请重新设置。";
            if (!register(handle,Id,modifiers,key)) return "截图快捷键已被占用或不可用；可更换组合，或点击工作台的截图按钮。";
            window = handle; current = value; Registered = true;
            return null;
        }
        public void Dispose()
        {
            if (Registered) unregister(window,Id);
            Registered = false; window = IntPtr.Zero; current = null;
        }
        [DllImport("user32.dll",SetLastError=true)]
        private static extern bool RegisterHotKey(IntPtr handle,int id,uint modifiers,uint key);
        [DllImport("user32.dll",SetLastError=true)]
        private static extern bool UnregisterHotKey(IntPtr handle,int id);
    }

    internal sealed class CaptureContext
    {
        internal string ProjectId;
        internal string ItemId;
        private static bool IdOrEmpty(object value)
        {
            return value == null || (value is string && ((string)value == "" || Regex.IsMatch((string)value,"\\A[a-f0-9]{32}\\z")));
        }
        internal static bool TryRead(Dictionary<string,object> message,string requestId,out CaptureContext result)
        {
            result = null; object action,request,project,item;
            if (message == null || message.Count != 4 || requestId == null ||
                !message.TryGetValue("action",out action) || (action as string) != "capture-context" ||
                !message.TryGetValue("requestId",out request) || (request as string) != requestId ||
                !message.TryGetValue("projectId",out project) || !message.TryGetValue("itemId",out item) || !IdOrEmpty(project) || !IdOrEmpty(item)) return false;
            result = new CaptureContext { ProjectId = String.IsNullOrEmpty(project as string) ? null : (string)project };
            result.ItemId = result.ProjectId == null || String.IsNullOrEmpty(item as string) ? null : (string)item;
            return true;
        }
    }
    internal sealed class CaptureResult
    {
        public string action = "capture-result";
        public string requestId;
        public object item;
        public bool clipboardCopied;
        public bool cancelled;
        public string error;
        public string clipboardError;
        public string saveError;
    }
    internal sealed class CaptureServices
    {
        internal Func<Rectangle> ScreenBounds = () => Screen.FromPoint(Cursor.Position).Bounds;
        internal Func<Rectangle,Bitmap> Select = CapturePlatform.Select;
        internal Action<Bitmap> Copy = CapturePlatform.Copy;
        internal Func<Bitmap,string,object> Upload = (image,project) => DesktopApi.UploadCapture(CapturePlatform.Encode(image),project);
    }

    // Allocates no image and starts no timer until an explicit capture request.
    internal sealed class CaptureCoordinator : IDisposable
    {
        private readonly Func<object,bool> send;
        private readonly Action<string,bool> notice;
        private readonly CaptureServices services;
        private readonly Queue<CaptureResult> completed = new Queue<CaptureResult>();
        private TaskCompletionSource<CaptureContext> context;
        private string requestId;
        private bool disposed;
        internal int ContextTimeoutMs = 5000;
        internal bool Busy { get; private set; }
        internal CaptureCoordinator(Func<object,bool> post,Action<string,bool> notify,CaptureServices implementation = null)
        {
            send = post; notice = notify; services = implementation ?? new CaptureServices();
        }
        internal bool Receive(Dictionary<string,object> message)
        {
            CaptureContext value;
            return Busy && context != null && CaptureContext.TryRead(message,requestId,out value) && context.TrySetResult(value);
        }
        internal void Flush()
        {
            while (!disposed && completed.Count != 0 && send(completed.Peek())) completed.Dequeue();
        }
        internal async Task StartAsync()
        {
            if (disposed || Busy) return;
            if (completed.Count >= 8) { notice("工作台尚未接收之前的截图结果，请先重新打开工作台。",true); return; }
            Busy = true; requestId = Guid.NewGuid().ToString("N");
            var result = new CaptureResult { requestId = requestId };
            try
            {
                Rectangle screen = services.ScreenBounds();
                context = new TaskCompletionSource<CaptureContext>();
                CaptureContext target = null;
                if (send(new { action = "capture-context-request", requestId = requestId }))
                {
                    using (var delay = new CancellationTokenSource())
                    {
                        var timeout = Task.Delay(ContextTimeoutMs,delay.Token);
                        if (await Task.WhenAny(context.Task,timeout) == context.Task) target = await context.Task;
                        delay.Cancel();
                    }
                }
                context = null;
                if (disposed) return;
                using (Bitmap image = services.Select(screen))
                {
                    if (image == null) { result.cancelled = true; return; }
                    try { services.Copy(image); result.clipboardCopied = true; }
                    catch (Exception error) { result.clipboardError = "剪贴板写入失败："+error.Message; }
                    if (target != null && target.ProjectId != null)
                    {
                        try { result.item = await Task.Run(() => services.Upload(image,target.ProjectId)); }
                        catch (Exception error) { result.saveError = "项目附件保存失败："+error.Message; }
                    }
                    else result.saveError = target == null ? "未及时取得工作台项目，截图未存入项目。" : "未选择项目，截图未存入项目。";
                }
                result.error = String.Join("\n",new[] { result.clipboardError,result.saveError }).Trim();
                notice(result.item != null ? (result.clipboardCopied ? "截图已复制，并保存到项目的参考资料。" : "截图已保存到项目，但未能写入剪贴板。") : result.clipboardCopied ? "截图已复制到剪贴板；"+result.saveError : result.error,
                    !result.clipboardCopied || (target != null && target.ProjectId != null && result.item == null));
            }
            catch (Exception error) { result.error = "截图未完成："+error.Message; notice(result.error,true); }
            finally
            {
                context = null; requestId = null; Busy = false;
                if (!disposed) { completed.Enqueue(result); Flush(); }
            }
        }
        public void Dispose() { disposed = true; if (context != null) context.TrySetResult(null); completed.Clear(); }
    }

    internal static class CapturePlatform
    {
        internal const long MaxPixels = 40000000;
        internal static byte[] Encode(Bitmap image)
        {
            using (var output = new MemoryStream()) { image.Save(output,ImageFormat.Png); return output.ToArray(); }
        }
        internal static void Copy(Bitmap image)
        {
            var data = new DataObject(); data.SetData(DataFormats.Bitmap,true,image);
            Clipboard.SetDataObject(data,true,3,40);
        }
        internal static Rectangle Selection(Point first,Point last,Size size)
        {
            int x1=Math.Max(0,Math.Min(size.Width,first.X)),y1=Math.Max(0,Math.Min(size.Height,first.Y));
            int x2=Math.Max(0,Math.Min(size.Width,last.X)),y2=Math.Max(0,Math.Min(size.Height,last.Y));
            return Rectangle.FromLTRB(Math.Min(x1,x2),Math.Min(y1,y2),Math.Max(x1,x2),Math.Max(y1,y2));
        }
        internal static Bitmap Crop(Bitmap image,Rectangle area)
        {
            if (area.Width < 2 || area.Height < 2 || !new Rectangle(Point.Empty,image.Size).Contains(area)) return null;
            return image.Clone(area,PixelFormat.Format32bppRgb);
        }
        internal static Bitmap Select(Rectangle bounds)
        {
            if (bounds.Width <= 0 || bounds.Height <= 0 || (long)bounds.Width*bounds.Height > MaxPixels) throw new InvalidOperationException("当前屏幕尺寸超过截图上限。");
            IntPtr foreground = GetForegroundWindow();
            try
            {
                using (var screen = new Bitmap(bounds.Width,bounds.Height,PixelFormat.Format32bppRgb))
                {
                    using (var graphics = Graphics.FromImage(screen)) graphics.CopyFromScreen(bounds.Location,Point.Empty,bounds.Size,CopyPixelOperation.SourceCopy);
                    using (var selector = new CaptureSelector(screen,bounds))
                        return selector.ShowDialog() == DialogResult.OK ? Crop(screen,selector.Area) : null;
                }
            }
            finally { if (foreground != IntPtr.Zero && IsWindow(foreground)) SetForegroundWindow(foreground); }
        }
        [DllImport("user32.dll")] private static extern IntPtr GetForegroundWindow();
        [DllImport("user32.dll")] private static extern bool IsWindow(IntPtr handle);
        [DllImport("user32.dll")] private static extern bool SetForegroundWindow(IntPtr handle);
    }
    internal sealed class CaptureSelector : Form
    {
        private readonly Bitmap screen;
        private Point first;
        private bool selecting;
        internal Rectangle Area { get; private set; }
        internal CaptureSelector(Bitmap image,Rectangle bounds)
        {
            screen=image; AutoScaleMode=AutoScaleMode.None; FormBorderStyle=FormBorderStyle.None;
            StartPosition=FormStartPosition.Manual; Bounds=bounds; TopMost=true; ShowInTaskbar=false;
            DoubleBuffered=true; KeyPreview=true; Cursor=Cursors.Cross; Text="映序截图 · 拖动选择区域，Esc 取消";
        }
        protected override void OnPaint(PaintEventArgs e)
        {
            e.Graphics.DrawImageUnscaled(screen,0,0);
            using (var shade=new SolidBrush(Color.FromArgb(100,0,0,0)))
            using (var outside=new Region(ClientRectangle))
            {
                if (Area.Width>0 && Area.Height>0) outside.Exclude(Area);
                e.Graphics.FillRegion(shade,outside);
            }
            if (Area.Width>0 && Area.Height>0)
                using (var pen=new Pen(Color.FromArgb(135,208,154),2)) e.Graphics.DrawRectangle(pen,Area.X,Area.Y,Math.Max(0,Area.Width-1),Math.Max(0,Area.Height-1));
            TextRenderer.DrawText(e.Graphics,"拖动选择当前屏幕区域 · Esc / 右键取消",Font,new Point(18,18),Color.White,Color.FromArgb(35,45,38));
        }
        protected override void OnMouseDown(MouseEventArgs e)
        {
            if (e.Button==MouseButtons.Right) { DialogResult=DialogResult.Cancel; Close(); return; }
            if (e.Button!=MouseButtons.Left) return;
            first=e.Location; selecting=true; Capture=true; Area=Rectangle.Empty; Invalidate();
        }
        protected override void OnMouseMove(MouseEventArgs e)
        {
            if (!selecting) return; Area=CapturePlatform.Selection(first,e.Location,screen.Size); Invalidate();
        }
        protected override void OnMouseUp(MouseEventArgs e)
        {
            if (!selecting || e.Button!=MouseButtons.Left) return;
            Area=CapturePlatform.Selection(first,e.Location,screen.Size); selecting=false; Capture=false;
            if (Area.Width<2 || Area.Height<2) { Area=Rectangle.Empty; Invalidate(); return; }
            DialogResult=DialogResult.OK; Close();
        }
        protected override void OnKeyDown(KeyEventArgs e)
        {
            if (e.KeyCode==Keys.Escape) { e.Handled=true; DialogResult=DialogResult.Cancel; Close(); }
            base.OnKeyDown(e);
        }
    }
}
