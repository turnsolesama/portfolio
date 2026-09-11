using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Pipes;
using System.Net;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using Microsoft.Win32;

namespace YingXu.Desktop
{
    internal sealed class LaunchOptions
    {
        internal string Root;
        internal string[] Paths;
        internal string Registration;
        internal static LaunchOptions Parse(string[] args, string defaultRoot)
        {
            var result = new LaunchOptions { Root = defaultRoot };
            var files = new List<string>();
            for (int index = 0; index < args.Length; index++)
            {
                string value = args[index];
                if (value == "--root")
                {
                    if (++index == args.Length) throw new ArgumentException("--root 缺少程序目录。");
                    result.Root = args[index];
                }
                else if (value == "--open")
                {
                    if (++index == args.Length) throw new ArgumentException("--open 缺少文件路径。");
                    files.Add(Hub.ValidateNativeFilePath(args[index]));
                }
                else if (value == "--register-open-with" || value == "--unregister-open-with") result.Registration = value;
                else if (value.StartsWith("--", StringComparison.Ordinal)) throw new ArgumentException("不支持的映序启动参数。");
                else files.Add(Hub.ValidateNativeFilePath(value));
            }
            if (files.Count > 32) throw new ArgumentException("一次最多打开 32 个文件。");
            if (result.Registration != null && files.Count != 0) throw new ArgumentException("注册操作不能同时打开文件。");
            result.Paths = files.ToArray();
            return result;
        }
    }

    internal static class DesktopApi
    {
        private static Dictionary<string,object> ReadResponse(WebResponse response)
        {
            using (response)
            using (var reader = new StreamReader(response.GetResponseStream(),Encoding.UTF8))
            {
                var chars=new char[2097153]; int count=reader.ReadBlock(chars,0,chars.Length);
                if (count==chars.Length) throw new InvalidDataException("本地服务返回的数据过大。");
                var result=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(new string(chars,0,count));
                if (result==null) throw new InvalidDataException("本地服务返回的数据无效。");
                return result;
            }
        }
        internal static Dictionary<string, object> Request(string path, object payload = null, string token = null)
        {
            var request = (HttpWebRequest)WebRequest.Create(Hub.Url.TrimEnd('/') + path);
            request.Proxy = null; request.AllowAutoRedirect = false;
            request.Timeout = 15000; request.ReadWriteTimeout = 15000;
            request.Headers["Origin"] = Hub.Url.TrimEnd('/');
            if (payload != null)
            {
                request.Method = "POST"; request.ContentType = "application/json";
                request.Headers["X-YingXu-Token"] = token;
                byte[] bytes = Encoding.UTF8.GetBytes(new JavaScriptSerializer().Serialize(payload));
                request.ContentLength = bytes.Length;
                using (var stream = request.GetRequestStream()) stream.Write(bytes, 0, bytes.Length);
            }
            return ReadResponse(request.GetResponse());
        }
        internal static object UploadCapture(byte[] png,string projectId)
        {
            if (projectId==null || !Regex.IsMatch(projectId,"\\A[a-f0-9]{32}\\z")) throw new InvalidDataException("截图目标项目无效。");
            byte[] signature={137,80,78,71,13,10,26,10};
            if (png==null || png.Length<signature.Length || png.Length>160*1024*1024) throw new InvalidDataException("截图图片大小无效。");
            for(int i=0;i<signature.Length;i++) if(png[i]!=signature[i]) throw new InvalidDataException("截图图片格式无效。");
            var bootstrap=Request("/api/bootstrap"); object token;
            if(!bootstrap.TryGetValue("token",out token) || !(token is string)) throw new InvalidDataException("后台未提供截图保存令牌。");
            string name="截图_"+DateTime.Now.ToString("yyyyMMdd_HHmmss_fff")+"_"+Guid.NewGuid().ToString("N").Substring(0,6)+".png";
            var request=(HttpWebRequest)WebRequest.Create(Hub.Url.TrimEnd('/')+"/api/upload?project="+projectId+"&category=references&name="+Uri.EscapeDataString(name));
            request.Proxy=null; request.AllowAutoRedirect=false; request.Timeout=30000; request.ReadWriteTimeout=30000;
            request.Method="POST"; request.ContentType="image/png"; request.ContentLength=png.Length;
            request.Headers["Origin"]=Hub.Url.TrimEnd('/'); request.Headers["X-YingXu-Token"]=(string)token;
            using(var output=request.GetRequestStream()) output.Write(png,0,png.Length);
            var result=ReadResponse(request.GetResponse()); object id,project,kind;
            if(!result.TryGetValue("id",out id) || !(id is string) || !Regex.IsMatch((string)id,"\\A[a-f0-9]{32}\\z") ||
                !result.TryGetValue("project_id",out project) || (project as string)!=projectId ||
                !result.TryGetValue("kind",out kind) || (kind as string)!="image")
                throw new InvalidDataException("截图保存响应不完整，请在项目参考资料中核对。");
            return result;
        }
        internal static object OpenFiles(string[] paths)
        {
            var bootstrap = Request("/api/bootstrap");
            object token;
            if (!bootstrap.TryGetValue("token", out token) || !(token is string)) throw new InvalidDataException("后台未提供本地打开令牌。");
            var response = Request("/api/external-open", new { paths = paths }, (string)token);
            object entries;
            if (!response.TryGetValue("entries", out entries)) throw new InvalidDataException("后台未返回文件预览。");
            return entries;
        }
        internal static bool CloseToTray()
        {
            var settings = Request("/api/settings"); object value;
            if (settings.TryGetValue("settings", out value) && value is Dictionary<string,object>) settings = (Dictionary<string,object>)value;
            return !settings.TryGetValue("close_to_tray", out value) || !(value is bool) || (bool)value;
        }
    }

    internal sealed class OpenInbox : IDisposable
    {
        private readonly string name;
        private readonly Action<string[]> receive;
        private volatile bool stopping;
        private NamedPipeServerStream active;
        private readonly object sync = new object();
        internal OpenInbox(string identity, Action<string[]> callback)
        {
            name = "YingXu-open-" + identity; receive = callback;
            Task.Run((Action)Listen);
        }
        internal static byte[] Encode(string[] paths)
        {
            if (paths == null || paths.Length > 32) throw new InvalidDataException("文件数量超过限制。");
            byte[] bytes = Encoding.UTF8.GetBytes(new JavaScriptSerializer().Serialize(paths));
            if (bytes.Length > 1048576) throw new InvalidDataException("打开请求过大。");
            return bytes;
        }
        internal static string[] Decode(byte[] bytes)
        {
            if (bytes.Length > 1048576) throw new InvalidDataException("打开请求过大。");
            var paths = new JavaScriptSerializer().Deserialize<string[]>(Encoding.UTF8.GetString(bytes));
            if (paths == null || paths.Length > 32) throw new InvalidDataException("文件数量超过限制。");
            return Array.ConvertAll(paths, Hub.ValidateNativeFilePath);
        }
        private static byte[] Read(Stream stream, int size)
        {
            var bytes = new byte[size]; int offset = 0;
            while (offset < size)
            {
                var pending = stream.ReadAsync(bytes, offset, size-offset);
                if (!pending.Wait(5000)) throw new IOException("打开请求读取超时。");
                int count = pending.Result;
                if (count == 0) throw new EndOfStreamException();
                offset += count;
            }
            return bytes;
        }
        internal static void Send(string identity, string[] paths)
        {
            using (var pipe = new NamedPipeClientStream(".", "YingXu-open-" + identity, PipeDirection.InOut, PipeOptions.Asynchronous))
            {
                pipe.Connect(5000); byte[] bytes = Encode(paths); byte[] size = BitConverter.GetBytes(bytes.Length);
                pipe.Write(size,0,size.Length); pipe.Write(bytes,0,bytes.Length); pipe.Flush();
                if (Read(pipe,1)[0] != 1) throw new IOException("已有窗口未接收文件，请更新并重新打开映序。");
            }
        }
        private void Listen()
        {
            while (!stopping)
            {
                try
                {
                    var security = new PipeSecurity();
                    security.SetAccessRuleProtection(true,false);
                    security.AddAccessRule(new PipeAccessRule(WindowsIdentity.GetCurrent().User,PipeAccessRights.FullControl,AccessControlType.Allow));
                    using (var pipe = new NamedPipeServerStream(name,PipeDirection.InOut,1,PipeTransmissionMode.Byte,
                        PipeOptions.Asynchronous,4096,4096,security))
                    {
                        lock (sync) { if (stopping) return; active = pipe; }
                        pipe.WaitForConnection();
                        int size = BitConverter.ToInt32(Read(pipe,4),0);
                        if (size < 2 || size > 1048576) throw new InvalidDataException("打开请求长度无效。");
                        receive(Decode(Read(pipe,size))); pipe.WriteByte(1); pipe.Flush();
                    }
                }
                catch (Exception error) { if (!stopping) Hub.Log("open_inbox_error " + error.GetType().Name); }
                finally { lock (sync) active = null; }
            }
        }
        public void Dispose() { stopping = true; lock (sync) { if (active != null) active.Dispose(); } }
    }

    internal static class OpenWithRegistration
    {
        private const string ProgId = "YingXu.LocalPreview";
        private static readonly string[] Extensions = { ".md", ".markdown", ".txt", ".json", ".csv", ".srt", ".vtt", ".html", ".htm", ".docx", ".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg", ".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v", ".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac" };
        internal static string Change(RegistryKey classes, string executable, bool register)
        {
            string command = Hub.Quote(Path.GetFullPath(executable)) + " --open \"%1\"";
            using (var owner = classes.OpenSubKey(ProgId))
            {
                if (owner == null && !register) return "映序打开方式候选尚未注册。";
                if (owner != null && !Object.Equals(owner.GetValue("YingXuOwned"),1))
                    throw new IOException("此打开方式注册不属于映序，未改动现有设置。");
            }
            using (var existing = classes.OpenSubKey(ProgId + @"\shell\open\command"))
                if (existing != null && (string)existing.GetValue("") != command)
                    throw new IOException("已存在另一个映序安装的打开方式；请先从原安装撤销注册。");
            if (register)
            {
                using (var root = classes.CreateSubKey(ProgId))
                {
                    root.SetValue("", "映序 · 只读文件预览");
                    root.SetValue("FriendlyTypeName", "映序 · 只读文件预览");
                    root.SetValue("YingXuOwned",1,RegistryValueKind.DWord);
                }
                using (var icon = classes.CreateSubKey(ProgId + @"\DefaultIcon")) icon.SetValue("", Hub.Quote(executable) + ",0");
                using (var open = classes.CreateSubKey(ProgId + @"\shell\open\command")) open.SetValue("",command);
                foreach (string extension in Extensions)
                    using (var key = classes.CreateSubKey(extension + @"\OpenWithProgids")) key.SetValue(ProgId,"",RegistryValueKind.String);
                return "已添加映序到 Windows“打开方式”候选，默认应用保持不变。";
            }
            foreach (string extension in Extensions)
                using (var key = classes.OpenSubKey(extension + @"\OpenWithProgids",true))
                    if (key != null) key.DeleteValue(ProgId,false);
            classes.DeleteSubKeyTree(ProgId,false);
            return "已撤销映序的打开方式候选，默认应用保持不变。";
        }
        internal static string Change(bool register)
        {
            using (var classes = Registry.CurrentUser.CreateSubKey(@"Software\Classes"))
            {
                string result = Change(classes,Path.Combine(Hub.Root,"YingXu.exe"),register);
                SHChangeNotify(0x08000000,0,IntPtr.Zero,IntPtr.Zero);
                return result;
            }
        }
        [DllImport("shell32.dll")]
        private static extern void SHChangeNotify(uint eventId,uint flags,IntPtr item1,IntPtr item2);
    }
}
