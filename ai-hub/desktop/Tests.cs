using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading.Tasks;

namespace AIHub.Desktop
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

        private static void InvalidPort(string file, string json)
        {
            File.WriteAllText(file, json);
            bool rejected = false;
            try { Hub.ReadPort(file); } catch (InvalidDataException) { rejected = true; }
            Check(rejected, "reject invalid config " + json);
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
            Hub.Cache = folder;
            var probe = new TcpListener(IPAddress.Loopback, 0);
            probe.Start();
            Hub.Port = ((IPEndPoint)probe.LocalEndpoint).Port;
            probe.Stop();
            Hub.Url = "http://127.0.0.1:" + Hub.Port + "/";
            File.Copy(Path.Combine(sourceRoot, "launcher.pyw"), Path.Combine(folder, "launcher.pyw"), true);
            File.WriteAllText(Path.Combine(folder, "server.py"),
                "import ctypes,json,sys,threading\nfrom http.server import BaseHTTPRequestHandler,HTTPServer\n" +
                "from pathlib import Path\n" +
                "Path('data/console.txt').write_text(str(ctypes.windll.kernel32.GetConsoleWindow()))\n" +
                "class Handler(BaseHTTPRequestHandler):\n" +
                " def do_GET(self):\n" +
                "  body=b'{\"app\":\"ai-hub\"}'\n" +
                "  self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)\n" +
                " def log_message(self,*args): pass\n" +
                "server=HTTPServer(('127.0.0.1',int(sys.argv[sys.argv.index('--port')+1])),Handler)\n" +
                "threading.Timer(4,server.shutdown).start()\nserver.serve_forever()\nserver.server_close()\n");
            Check(Hub.EnsureService() == "started", "cold startup in isolated Unicode path");
            string pidRecord = Path.Combine(folder, "data", "server.pid.json");
            string before = File.ReadAllText(pidRecord);
            Check(Hub.EnsureService() == "reused" && File.ReadAllText(pidRecord) == before, "cold-started service reused without replacing PID");
            Check(File.ReadAllText(Path.Combine(folder, "data", "console.txt")) == "0", "background Python has no console window");
            var record = new System.Web.Script.Serialization.JavaScriptSerializer().Deserialize<System.Collections.Generic.Dictionary<string, object>>(before);
            using (var process = Process.GetProcessById((int)record["pid"]))
                Check(process.WaitForExit(10000), "owned fixture stops itself cleanly");
        }

        private static int Main(string[] args)
        {
            string folder = Path.Combine(Path.GetTempPath(), "aihub-桌面测试 空间-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(folder);
            try
            {
                Check(Hub.NormalizeRoot(args[0]) == Hub.NormalizeRoot(Path.Combine(args[0], ".")), "app root normalization retains physical directory");
                if (args.Length > 1)
                {
                    string physical = Hub.NormalizeRoot(args[0]);
                    string alias = Hub.NormalizeRoot(args[1]);
                    Check(physical == alias, "junction and physical app roots resolve equally");
                    Check(Hub.Identity(physical.ToUpperInvariant()) == Hub.Identity(alias.ToUpperInvariant()), "junction uses same mutex and browser profile identity");
                }
                string file = Path.Combine(folder, "config.json");
                Check(Hub.ReadPort(file) == 8765, "default port without config");
                File.WriteAllText(file, "{\"server\":{\"port\":8999}}", new UTF8Encoding(true));
                Check(Hub.ReadPort(file) == 8999, "custom port and BOM");
                foreach (string json in new[] { "{", "null", "{\"server\":null}", "{\"server\":{\"port\":true}}", "{\"server\":{\"port\":\"8765\"}}", "{\"server\":{\"port\":80}}", "{\"server\":{\"port\":65536}}" }) InvalidPort(file, json);
                string origin = "http://127.0.0.1:8765/";
                Check(Hub.IsLocalPage(origin + "#/models", origin), "local routes retained");
                Check(!Hub.IsLocalPage("http://127.0.0.1:8766/", origin), "different port blocked");
                Check(!Hub.IsLocalPage("http://127.0.0.1.evil.example:8765/", origin), "hostname suffix blocked");
                Check(!Hub.IsLocalPage("http://user@127.0.0.1:8765/", origin), "userinfo blocked");
                Check(!Hub.IsWebLink("file:///C:/Windows/System32/cmd.exe") && !Hub.IsWebLink("javascript:alert(1)") && !Hub.IsWebLink("ms-settings:about"), "non-web schemes blocked");
                Check(Hub.IsWebLink("https://huggingface.co/models"), "external source page allowed");
                foreach (string value in new[] { "", @"C:\资料 空间\AI Hub\", "quote\"embedded", @"C:\AI Hub\launcher.pyw", "abc\\\"def\\" }) QuoteRoundTrip(value);
                Check(!Hub.IsAppRoot(folder), "incomplete installation rejected");
                File.WriteAllText(Path.Combine(folder, "server.py"), "");
                File.WriteAllText(Path.Combine(folder, "launcher.pyw"), "");
                Directory.CreateDirectory(Path.Combine(folder, "frontend"));
                File.WriteAllText(Path.Combine(folder, "frontend", "index.html"), "");
                Check(Hub.IsAppRoot(folder), "app folder recognized");
                HealthResponse("{\"app\":\"ai-hub\"}", true);
                HealthResponse("{\"app\":\"other\"}", false);
                HealthResponse("not-json", false);
                ColdStart(folder, args[0]);
                Console.WriteLine("Desktop tests passed: " + passed);
                return 0;
            }
            finally
            {
                // Only the GUID-named fixture created in this test is removed.
                Directory.Delete(folder, true);
            }
        }

        [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
        private static extern IntPtr CommandLineToArgvW(string command, out int count);
        [DllImport("kernel32.dll")]
        private static extern IntPtr LocalFree(IntPtr pointer);
    }
}
