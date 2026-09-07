using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Security.Cryptography;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using Microsoft.Win32;
using Microsoft.Win32.SafeHandles;

namespace AIHub.Desktop
{
    internal static class Hub
    {
        internal static string Root;
        internal static string Cache;
        internal static string Url;
        internal static int Port;

        internal static string Identity(string value)
        {
            using (var sha = SHA256.Create())
                return BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(value))).Replace("-", "").ToLowerInvariant();
        }

        internal static string NormalizeRoot(string root)
        {
            string full = Path.GetFullPath(root);
            if (!Directory.Exists(full)) return full;
            // Resolve directory junctions before deriving the mutex and browser profile.
            // All compatibility entries must open the same physical app and same window.
            using (var handle = CreateFileW(full, 0, 7, IntPtr.Zero, 3, 0x02000000, IntPtr.Zero))
            {
                if (handle.IsInvalid) throw new IOException("无法读取 AI Hub 程序目录。", new Win32Exception(Marshal.GetLastWin32Error()));
                var path = new StringBuilder(512);
                uint length = GetFinalPathNameByHandleW(handle, path, (uint)path.Capacity, 0);
                if (length >= path.Capacity)
                {
                    path.EnsureCapacity(checked((int)length + 1));
                    length = GetFinalPathNameByHandleW(handle, path, (uint)path.Capacity, 0);
                }
                if (length == 0 || length >= path.Capacity)
                    throw new IOException("无法解析 AI Hub 程序目录。", new Win32Exception(Marshal.GetLastWin32Error()));
                full = path.ToString();
                if (full.StartsWith(@"\\?\UNC\", StringComparison.OrdinalIgnoreCase)) full = @"\\" + full.Substring(8);
                else if (full.StartsWith(@"\\?\", StringComparison.Ordinal)) full = full.Substring(4);
            }
            return full.Length > Path.GetPathRoot(full).Length ? full.TrimEnd('\\', '/') : full;
        }

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern SafeFileHandle CreateFileW(string name, uint access, uint share, IntPtr security, uint creation, uint flags, IntPtr template);
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern uint GetFinalPathNameByHandleW(SafeFileHandle handle, StringBuilder path, uint capacity, uint flags);

        internal static bool IsAppRoot(string root)
        {
            return File.Exists(Path.Combine(root, "server.py")) &&
                   File.Exists(Path.Combine(root, "launcher.pyw")) &&
                   File.Exists(Path.Combine(root, "frontend", "index.html"));
        }

        internal static int ReadPort(string path)
        {
            if (!File.Exists(path)) return 8765;
            Dictionary<string, object> config;
            try { config = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(File.ReadAllText(path, Encoding.UTF8)); }
            catch { throw new InvalidDataException("data/config.json 格式有误，请修复配置后再打开 AI Hub。"); }
            if (config == null) throw new InvalidDataException("data/config.json 必须是配置对象。");
            object server, port;
            if (!config.TryGetValue("server", out server)) return 8765;
            var settings = server as Dictionary<string, object>;
            if (settings == null) throw new InvalidDataException("server 配置必须是对象。");
            if (!settings.TryGetValue("port", out port)) return 8765;
            if (!(port is int) || (int)port < 1024 || (int)port > 65535)
                throw new InvalidDataException("AI Hub 端口必须是 1024 至 65535 之间的整数。");
            return (int)port;
        }

        internal static bool IsLocalPage(string address, string origin)
        {
            Uri uri, baseUri;
            return Uri.TryCreate(address, UriKind.Absolute, out uri) &&
                   Uri.TryCreate(origin, UriKind.Absolute, out baseUri) &&
                   uri.Scheme == "http" && uri.Host == "127.0.0.1" &&
                   uri.Port == baseUri.Port && uri.UserInfo.Length == 0;
        }

        internal static bool IsWebLink(string address)
        {
            Uri uri;
            return Uri.TryCreate(address, UriKind.Absolute, out uri) &&
                   (uri.Scheme == "http" || uri.Scheme == "https") &&
                   uri.UserInfo.Length == 0 && !String.IsNullOrEmpty(uri.Host);
        }

        // Windows command-line quoting, including trailing backslashes and quotes.
        internal static string Quote(string value)
        {
            var result = new StringBuilder("\"");
            int slashes = 0;
            foreach (char c in value)
            {
                if (c == '\\') { slashes++; continue; }
                result.Append('\\', slashes * (c == '"' ? 2 : 1));
                if (c == '"') result.Append('\\');
                result.Append(c);
                slashes = 0;
            }
            return result.Append('\\', slashes * 2).Append('"').ToString();
        }

        internal static bool Healthy(int port)
        {
            try
            {
                var request = (HttpWebRequest)WebRequest.Create("http://127.0.0.1:" + port + "/api/health");
                request.Proxy = null;
                request.AllowAutoRedirect = false;
                request.Timeout = 1200;
                request.ReadWriteTimeout = 1200;
                using (var response = request.GetResponse())
                using (var reader = new StreamReader(response.GetResponseStream()))
                {
                    var health = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(reader.ReadToEnd());
                    object name;
                    return health != null && health.TryGetValue("app", out name) && (name as string) == "ai-hub";
                }
            }
            catch { return false; }
        }

        private static IEnumerable<string> PythonCandidates()
        {
            yield return Path.Combine(Root, "runtime", "python.exe");
            var installs = new List<KeyValuePair<Version, string>>();
            foreach (RegistryHive hive in new[] { RegistryHive.CurrentUser, RegistryHive.LocalMachine })
            foreach (RegistryView view in new[] { RegistryView.Registry64, RegistryView.Registry32 })
            {
                using (var root = RegistryKey.OpenBaseKey(hive, view))
                using (var core = root.OpenSubKey(@"Software\Python\PythonCore"))
                {
                    if (core == null) continue;
                    foreach (string tag in core.GetSubKeyNames())
                    {
                        Version version;
                        if (!Version.TryParse(tag.Split('-')[0], out version) || version.Major != 3 || version.Minor < 9) continue;
                        using (var install = core.OpenSubKey(tag + @"\InstallPath"))
                        {
                            if (install == null) continue;
                            string path = install.GetValue("ExecutablePath") as string;
                            string directory = install.GetValue("") as string;
                            if (String.IsNullOrEmpty(path) && !String.IsNullOrEmpty(directory)) path = Path.Combine(directory, "python.exe");
                            if (!String.IsNullOrEmpty(path)) installs.Add(new KeyValuePair<Version, string>(version, path));
                        }
                    }
                }
            }
            installs.Sort((a, b) => b.Key.CompareTo(a.Key));
            foreach (var entry in installs) yield return entry.Value;
        }

        internal static string FindPython()
        {
            foreach (string path in PythonCandidates()) if (File.Exists(path)) return Path.GetFullPath(path);
            throw new FileNotFoundException("未找到 Python 3.9 或更新版本。请保留原 Python 安装，或把运行环境放到 AI Hub 的 runtime 文件夹。");
        }

        internal static string EnsureService()
        {
            if (Healthy(Port)) return "reused";
            string python = FindPython();
            var start = new ProcessStartInfo(python,
                "-B " + Quote(Path.Combine(Root, "launcher.pyw")) + " --no-browser --no-dialog --port " + Port);
            start.UseShellExecute = false;
            start.CreateNoWindow = true;
            start.WindowStyle = ProcessWindowStyle.Hidden;
            start.WorkingDirectory = Root;
            start.RedirectStandardOutput = true;
            start.RedirectStandardError = true;
            start.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
            using (var process = Process.Start(start))
            {
                // Drain pipes concurrently so a diagnostic message cannot block startup.
                var output = process.StandardOutput.ReadToEndAsync();
                var error = process.StandardError.ReadToEndAsync();
                if (!process.WaitForExit(30000))
                    throw new TimeoutException("后台启动超时，请查看 data/launcher.log 和 data/server.log。稍后重新打开会复用已启动服务。");
                if (process.ExitCode != 0 || !Healthy(Port))
                    throw new InvalidOperationException("后台服务未能启动。端口可能已被占用，详细原因请查看 data/launcher.log 和 data/server.log。");
                string text = output.GetAwaiter().GetResult();
                error.GetAwaiter().GetResult();
                return text.Contains("\"started\"") ? "started" : "reused";
            }
        }

        internal static void Log(string message)
        {
            try
            {
                string directory = Path.Combine(Root, "data");
                Directory.CreateDirectory(directory);
                File.AppendAllText(Path.Combine(directory, "desktop.log"), DateTime.Now.ToString("s") + " " + message + Environment.NewLine, Encoding.UTF8);
            }
            catch { }
        }
    }
}
