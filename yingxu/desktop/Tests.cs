using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading.Tasks;

namespace YingXu.Desktop
{
    internal static class Tests
    {
        private static int passed;
        private static void Check(bool ok, string name)
        {
            if (!ok) throw new Exception("FAILED: " + name);
            passed++;
            Console.WriteLine("PASS " + name);
        }

        private static void QuoteRoundTrip(string value)
        {
            int count;
            IntPtr arguments = CommandLineToArgvW("test.exe " + Hub.Quote(value), out count);
            try { Check(count == 2 && Marshal.PtrToStringUni(Marshal.ReadIntPtr(arguments, IntPtr.Size)) == value, "Windows argument round-trip"); }
            finally { LocalFree(arguments); }
        }

        private static void HealthResponse(string body, bool expected)
        {
            var listener = new TcpListener(IPAddress.Loopback, 0);
            listener.Start();
            int port = ((IPEndPoint)listener.LocalEndpoint).Port;
            var respond = Task.Run(() =>
            {
                using (var client = listener.AcceptTcpClient())
                using (var stream = client.GetStream())
                {
                    var buffer = new byte[4096];
                    stream.Read(buffer, 0, buffer.Length);
                    var bytes = Encoding.UTF8.GetBytes(body);
                    var header = Encoding.ASCII.GetBytes("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: " + bytes.Length + "\r\nConnection: close\r\n\r\n");
                    stream.Write(header, 0, header.Length);
                    stream.Write(bytes, 0, bytes.Length);
                }
            });
            try { Check(Hub.Healthy(port) == expected, "identify health service " + body); respond.Wait(); }
            finally { listener.Stop(); }
        }

        private static void ColdStart(string folder, string sourceRoot)
        {
            Hub.Root = folder;
            Hub.Data = Path.Combine(folder, "logs");
            Directory.CreateDirectory(Hub.Data);
            Hub.Cache = Hub.Data;
            var probe = new TcpListener(IPAddress.Loopback, 0);
            probe.Start();
            Hub.Port = ((IPEndPoint)probe.LocalEndpoint).Port;
            probe.Stop();
            Hub.Url = "http://127.0.0.1:" + Hub.Port + "/";
            File.Copy(Path.Combine(sourceRoot, "launcher.pyw"), Path.Combine(folder, "launcher.pyw"), true);
            Directory.CreateDirectory(Path.Combine(folder, "yingxu"));
            File.Copy(Path.Combine(sourceRoot, "yingxu", "__init__.py"), Path.Combine(folder, "yingxu", "__init__.py"), true);
            File.Copy(Path.Combine(sourceRoot, "yingxu", "paths.py"), Path.Combine(folder, "yingxu", "paths.py"), true);
            File.WriteAllText(Path.Combine(folder, "server.py"),
                "import ctypes,json,sys,threading\nfrom http.server import BaseHTTPRequestHandler,HTTPServer\n" +
                "from pathlib import Path\nfrom yingxu.paths import instance_id,default_data_root\n" +
                "Path('logs/console.txt').write_text(str(ctypes.windll.kernel32.GetConsoleWindow()))\n" +
                "class Handler(BaseHTTPRequestHandler):\n" +
                " def do_GET(self):\n" +
                "  body=json.dumps(dict(app='yingxu',ok=True,version='0.4.2',instance_id=instance_id(default_data_root()))).encode()\n" +
                "  self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)\n" +
                " def log_message(self,*args): pass\n" +
                "server=HTTPServer(('127.0.0.1',int(sys.argv[sys.argv.index('--port')+1])),Handler)\n" +
                "threading.Timer(4,server.shutdown).start()\nserver.serve_forever()\nserver.server_close()\n");
            Check(Hub.EnsureService() == "started", "cold startup in isolated Unicode path");
            string pidRecord = Path.Combine(Hub.Data, "server.pid.json");
            string before = File.ReadAllText(pidRecord);
            Check(Hub.EnsureService() == "reused" && File.ReadAllText(pidRecord) == before, "existing service reused with same PID");
            Check(File.ReadAllText(Path.Combine(Hub.Data, "console.txt")) == "0", "background Python has no console window");
            var record = new System.Web.Script.Serialization.JavaScriptSerializer().Deserialize<System.Collections.Generic.Dictionary<string, object>>(before);
            using (var process = Process.GetProcessById((int)record["pid"]))
                Check(process.WaitForExit(10000), "owned fixture stops itself cleanly");
        }

        private static void RejectNativePath(string path, string name)
        {
            bool rejected = false;
            try { Hub.ValidateNativeFilePath(path); }
            catch { rejected = true; }
            Check(rejected, name);
        }

        private static void NativeResponse(string body, string expected)
        {
            var listener = new TcpListener(IPAddress.Loopback, 0);
            listener.Start();
            Hub.Port = ((IPEndPoint)listener.LocalEndpoint).Port;
            var respond = Task.Run(() =>
            {
                using (var client = listener.AcceptTcpClient())
                using (var stream = client.GetStream())
                {
                    var buffer = new byte[4096];
                    stream.Read(buffer, 0, buffer.Length);
                    var bytes = Encoding.UTF8.GetBytes(body);
                    var header = Encoding.ASCII.GetBytes("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: " + bytes.Length + "\r\nConnection: close\r\n\r\n");
                    stream.Write(header, 0, header.Length);
                    stream.Write(bytes, 0, bytes.Length);
                }
            });
            string result = null;
            try
            {
                try { result = Hub.NativeFilePath("0123456789abcdef0123456789abcdef"); }
                catch { if (expected != null) throw; }
                Check(result == expected, expected == null ? "reject invalid native file response" : "resolve authorized native file ID");
                respond.Wait();
            }
            finally { listener.Stop(); }
        }

        private static void NativeDrag(string folder, string[] args)
        {
            Hub.Url = "http://127.0.0.1:8791/";
            const string id = "0123456789abcdef0123456789abcdef";
            string parsed;
            string valid = "{\"action\":\"drag-file\",\"id\":\"" + id + "\"}";
            Check(Hub.TryReadDragMessage(Hub.Url, valid, out parsed) && parsed == id, "native drag accepts exact trusted ID message");
            Check(!Hub.TryReadDragMessage("https://example.com", valid, out parsed), "native drag rejects external source");
            Check(!Hub.TryReadDragMessage("http://127.0.0.1:8765", valid, out parsed), "native drag rejects other local app");
            Check(!Hub.TryReadDragMessage(Hub.Url, valid.Replace("drag-file", "run-command"), out parsed), "native drag rejects arbitrary action");
            Check(!Hub.TryReadDragMessage(Hub.Url, valid.Replace(id, "../secret"), out parsed), "native drag rejects path as ID");
            Check(!Hub.TryReadDragMessage(Hub.Url, valid.Replace(id, id + "\\n"), out parsed), "native drag rejects trailing newline ID");
            Check(!Hub.TryReadDragMessage(Hub.Url, valid.Replace("}", ",\"path\":\"C:/private.md\"}"), out parsed), "native drag rejects extra path field");
            Check(!Hub.TryReadDragMessage(Hub.Url, "null", out parsed) && !Hub.TryReadDragMessage(Hub.Url, "[]", out parsed), "native drag rejects non-object messages");
            Check(!Hub.TryReadDragMessage(Hub.Url, new string('x', 513), out parsed), "native drag rejects oversized message");
            string[] parsedIds;
            string multi = "{\"action\":\"drag-files\",\"ids\":[\"" + id + "\",\"" + new string('a', 32) + "\"]}";
            Check(Hub.TryReadDragItemsMessage(Hub.Url, multi, out parsedIds) && parsedIds.Length == 2 && parsedIds[0] == id, "native multi-drag accepts resource IDs");
            Check(Hub.TryReadDragItemsMessage(Hub.Url, valid, out parsedIds) && parsedIds.Length == 1, "native multi-drag accepts legacy handle");
            Check(!Hub.TryReadDragItemsMessage("https://example.com", multi, out parsedIds), "native multi-drag rejects external source");
            Check(!Hub.TryReadDragItemsMessage(Hub.Url, multi.Replace(id, "C:/secret.png"), out parsedIds), "native multi-drag rejects caller paths");
            Check(!Hub.TryReadDragItemsMessage(Hub.Url, "{\"action\":\"drag-files\",\"ids\":[]}", out parsedIds), "native multi-drag rejects empty selection");
            Check(!Hub.TryReadDragItemsMessage(Hub.Url, multi.Replace("}", ",\"path\":\"secret\"}"), out parsedIds), "native multi-drag rejects extra fields");
            string tooMany = "{\"action\":\"drag-files\",\"ids\":[" + String.Join(",", new System.Collections.Generic.List<string>(System.Linq.Enumerable.Repeat("\"" + id + "\"", 201)).ToArray()) + "]}";
            Check(!Hub.TryReadDragItemsMessage(Hub.Url, tooMany, out parsedIds), "native multi-drag bounds selection at 200");
            string file = Path.Combine(folder, "合成素材.md");
            File.WriteAllText(file, "Synthetic drag fixture; never user content");
            Check(Hub.ValidateNativeFilePath(file) == file, "native drag accepts ordinary safe file");
            string svgFile = Path.Combine(folder, "合成矢量.SVG");
            File.WriteAllText(svgFile, "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 10 10'><path d='M0 0L10 10'/></svg>");
            Check(Hub.ValidateNativeFilePath(svgFile) == svgFile, "native path accepts case-insensitive SVG extension without interpreting content");
            Check(LaunchOptions.Parse(new [] {"--open",svgFile},folder).Paths[0] == svgFile, "OpenWith SVG command reaches the existing validated file queue");
            foreach (string extension in new [] {".html", ".HTM"}) {
                string htmlFile = Path.Combine(folder, "静态页面"+extension);
                File.WriteAllText(htmlFile, "<!doctype html><h1>Synthetic page</h1>");
                Check(LaunchOptions.Parse(new [] {"--open",htmlFile},folder).Paths[0] == htmlFile,"HTML command reaches validated read-only preview queue: "+extension);
            }
            RejectNativePath("relative.md", "native drag rejects relative path");
            RejectNativePath(@"C:relative.md", "native drag rejects drive-relative path");
            RejectNativePath(@"\\server\share\file.md", "native drag rejects network path");
            RejectNativePath(@"\\?\C:\file.md", "native drag rejects device path");
            RejectNativePath(file + ":secret", "native drag rejects alternate stream");
            RejectNativePath(Path.Combine(folder, "missing.md"), "native drag rejects missing file");
            string unsafeFile = Path.Combine(folder, "unsafe.cmd");
            File.WriteAllText(unsafeFile, "not executable test bytes");
            RejectNativePath(unsafeFile, "native drag rejects executable extension");
            string directory = Path.Combine(folder, "directory.md");
            Directory.CreateDirectory(directory);
            RejectNativePath(directory, "native drag rejects directory");
            if (args.Length > 1)
                RejectNativePath(Path.Combine(args[1], "README_DESKTOP.md"), "native drag rejects reparse-point ancestor");
            var json = new System.Web.Script.Serialization.JavaScriptSerializer();
            NativeResponse(json.Serialize(new { path = file }), file);
            NativeResponse(json.Serialize(new { path = unsafeFile }), null);
            NativeResponse("{\"path\":5}", null);
            NativeResponse("{\"error\":\"not indexed\"}", null);
        }

        private static int Main(string[] args)
        {
            string folder = Path.Combine(Path.GetTempPath(), "yingxu-桌面测试 空间-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(folder);
            try
            {
                Check(Hub.NormalizeRoot(args[0]) == Hub.NormalizeRoot(Path.Combine(args[0], ".")), "app root resolves physical directory");
                if (args.Length > 1)
                {
                    string physical = Hub.NormalizeRoot(args[0]);
                    string alias = Hub.NormalizeRoot(args[1]);
                    Check(physical == alias, "junction and physical root resolve equally");
                    Check(Hub.Identity(physical.ToUpperInvariant()) == Hub.Identity(alias.ToUpperInvariant()), "junction yields same desktop mutex");
                }
                Check(Hub.PathIdentity(@"C:\Audit\Straße") == "e867a867e545e833f16113aa42f03485c55457b9eefeda1bc6755beeb3b4319c", "shared Python/.NET ASCII-fold identity: Straße");
                Check(Hub.PathIdentity(@"C:\Audit\ﬀ") == "db96b67fe990fd289531cf9868b44c592012ee30ee34b81d57f30207cab285ba", "shared Python/.NET ASCII-fold identity: ﬀ");
                Check(Hub.PathIdentity(@"C:\Audit\ς") == "2329b08c2f584d907890e9344d3bc88a25c41286f3d146e1499c8b3790455426", "shared Python/.NET ASCII-fold identity: ς");
                Check(Hub.PathIdentity(@"C:\Audit\中文") == "0b7e51da5b463088158bf0e2d52f464f63c60e6d0d406ee419a1720fe1f32287", "shared Python/.NET ASCII-fold identity: 中文");
                Check(Hub.PathIdentity(@"C:\Audit\Ascii") == "80679416497de0e0f8011ceb2c7c87bd239168db413ad2f163257af0df458711", "shared Python/.NET ASCII-fold identity: Ascii");
                Check(Hub.PathIdentity(@"C:\Audit\ascii") == "80679416497de0e0f8011ceb2c7c87bd239168db413ad2f163257af0df458711", "shared Python/.NET ASCII-fold identity: ascii");
                string origin = "http://127.0.0.1:8791/";
                Check(Hub.IsLocalPage(origin + "?project=1#files", origin), "local pages retained");
                Check(!Hub.IsLocalPage("http://127.0.0.1:8765/", origin), "different app port blocked");
                Check(!Hub.IsLocalPage("http://127.0.0.1.evil.example:8791/", origin), "hostname suffix blocked");
                Check(!Hub.IsLocalPage("http://user@127.0.0.1:8791/", origin), "userinfo blocked");
                Check(!Hub.IsLocalPage("https://127.0.0.1:8791/", origin), "different scheme blocked");
                Check(!Hub.IsLocalPage("file:///C:/Windows/System32/cmd.exe", origin), "file navigation blocked");
                Check(!Hub.IsLocalPage("javascript:alert(1)", origin), "script navigation blocked");
                foreach (string value in new[] { "", @"F:\资料 空间\映序\", "quote\"embedded", @"F:\映序\launcher.pyw", "abc\\\"def\\" }) QuoteRoundTrip(value);
                Check(!Hub.IsAppRoot(folder), "incomplete installation rejected");
                File.WriteAllText(Path.Combine(folder, "server.py"), "");
                File.WriteAllText(Path.Combine(folder, "launcher.pyw"), "");
                Directory.CreateDirectory(Path.Combine(folder, "frontend"));
                File.WriteAllText(Path.Combine(folder, "frontend", "index.html"), "");
                Check(Hub.IsAppRoot(folder), "complete app folder recognized");
                HealthResponse("{\"app\":\"yingxu\",\"ok\":true,\"version\":\"0.4.2\",\"instance_id\":\"" + Hub.InstanceId() + "\"}", true);
                HealthResponse("{\"app\":\"yingxu\",\"ok\":true,\"version\":\"0.3.2\",\"instance_id\":\"" + Hub.InstanceId() + "\"}", false);
                HealthResponse("{\"app\":\"yingxu\",\"ok\":true,\"version\":\"0.2.1\",\"instance_id\":\"" + Hub.InstanceId() + "\"}", false);
                HealthResponse("{\"app\":\"yingxu\",\"ok\":true}", false);
                HealthResponse("{\"app\":\"yingxu\",\"ok\":true,\"instance_id\":\"other\"}", false);
                HealthResponse("{\"app\":\"ai-hub\",\"ok\":true}", false);
                HealthResponse("{\"app\":\"yingxu\",\"ok\":false}", false);
                HealthResponse("{\"app\":\"yingxu\"}", false);
                HealthResponse("not-json", false);
                NativeDrag(folder, args);
                DesktopIntegration(folder);
                ColdStart(folder, args[0]);
                Console.WriteLine("Desktop tests passed: " + passed);
                return 0;
            }
            finally
            {
                string safe = Path.GetFullPath(folder);
                if (!safe.StartsWith(Path.GetFullPath(Path.GetTempPath()), StringComparison.OrdinalIgnoreCase) ||
                    !Path.GetFileName(safe).StartsWith("yingxu-桌面测试 空间-", StringComparison.Ordinal) ||
                    (File.GetAttributes(safe) & FileAttributes.ReparsePoint) != 0)
                    throw new IOException("拒绝删除范围不符的测试目录。");
                Directory.Delete(safe, true);
            }
        }

        private static void DesktopIntegration(string folder)
        {
            string file = Path.Combine(folder,"只读预览 空格.txt"); File.WriteAllText(file,"synthetic");
            var launch = LaunchOptions.Parse(new[] { "--root",folder,"--open",file },folder);
            Check(launch.Root == folder && launch.Paths.Length == 1 && launch.Paths[0] == file,"CLI --root and --open preserve Unicode file path");
            Check(LaunchOptions.Parse(new[] { file },folder).Paths[0] == file,"CLI bare quoted path opens actual file");
            bool rejected = false;
            try { LaunchOptions.Parse(new[] { "--open" },folder); } catch (ArgumentException) { rejected = true; }
            Check(rejected,"CLI rejects missing file argument");
            Check(OpenInbox.Decode(OpenInbox.Encode(new[] { file }))[0] == file,"IPC Unicode JSON frame round trip");
            rejected = false;
            try { OpenInbox.Decode(Encoding.UTF8.GetBytes("[\"relative.txt\"]")); } catch { rejected = true; }
            Check(rejected,"IPC rejects relative file paths");
            var arrived = new System.Threading.ManualResetEventSlim(false); string[] received = null;
            string identity = Guid.NewGuid().ToString("N");
            using (var inbox = new OpenInbox(identity,paths => { received = paths; arrived.Set(); }))
            {
                OpenInbox.Send(identity,new[] { file });
                Check(arrived.Wait(2000) && received[0] == file,"same-user named pipe delivers actual Unicode open request");
                OpenInbox.Send(identity,new string[0]);
                Check(received.Length == 0,"single-instance inbox accepts activation without files");
            }
            string testKey = @"Software\YingXu-DesktopTests-" + Guid.NewGuid().ToString("N");
            try
            {
                using (var root = Microsoft.Win32.Registry.CurrentUser.CreateSubKey(testKey))
                {
                    using (var ext = root.CreateSubKey(".txt")) ext.SetValue("","Other.Default");
                    using (var ext = root.CreateSubKey(".svg")) ext.SetValue("","Other.Vector");
                    using (var ext = root.CreateSubKey(@".txt\OpenWithProgids")) ext.SetValue("Other.Preview", "keep");
                    OpenWithRegistration.Change(root,Path.Combine(folder,"YingXu.exe"),true);
                    using (var ext = root.OpenSubKey(".txt")) Check((string)ext.GetValue("") == "Other.Default","OpenWith preserves existing default application");
                    using (var ext = root.OpenSubKey(@".txt\OpenWithProgids")) Check(ext.GetValue("YingXu.LocalPreview") != null && (string)ext.GetValue("Other.Preview") == "keep","OpenWith adds its candidate and preserves unrelated candidates");
                    using (var ext = root.OpenSubKey(@".svg\OpenWithProgids")) Check(ext != null && ext.GetValue("YingXu.LocalPreview") != null,"OpenWith registers an SVG candidate");
                    using (var ext = root.OpenSubKey(".svg")) Check((string)ext.GetValue("") == "Other.Vector","SVG registration preserves the existing default application");
                    foreach (string extension in new [] {".html", ".htm"})
                        using (var ext = root.OpenSubKey(extension+@"\OpenWithProgids")) Check(ext != null && ext.GetValue("YingXu.LocalPreview") != null,"OpenWith registers HTML candidate: "+extension);
                    OpenWithRegistration.Change(root,Path.Combine(folder,"YingXu.exe"),false);
                    Check(root.OpenSubKey("YingXu.LocalPreview") == null,"OpenWith unregister removes its own ProgID");
                    using (var ext = root.OpenSubKey(@".txt\OpenWithProgids")) Check(ext.GetValue("YingXu.LocalPreview") == null && (string)ext.GetValue("Other.Preview") == "keep","OpenWith unregister preserves unrelated values");
                    using (var ext = root.OpenSubKey(@".svg\OpenWithProgids")) Check(ext == null || ext.GetValue("YingXu.LocalPreview") == null,"SVG unregister removes only its candidate");
                    foreach (string extension in new [] {".html", ".htm"})
                        using (var ext = root.OpenSubKey(extension+@"\OpenWithProgids")) Check(ext == null || ext.GetValue("YingXu.LocalPreview") == null,"HTML unregister removes only its candidate: "+extension);
                    using (var existing = root.CreateSubKey("YingXu.LocalPreview")) existing.SetValue("","unowned");
                    rejected = false;
                    try { OpenWithRegistration.Change(root,Path.Combine(folder,"YingXu.exe"),true); } catch (IOException) { rejected = true; }
                    Check(rejected,"OpenWith refuses unowned preexisting registration");
                }
            }
            finally { Microsoft.Win32.Registry.CurrentUser.DeleteSubKeyTree(testKey,false); }
        }

        [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
        private static extern IntPtr CommandLineToArgvW(string command, out int count);
        [DllImport("kernel32.dll")]
        private static extern IntPtr LocalFree(IntPtr pointer);
    }
}
