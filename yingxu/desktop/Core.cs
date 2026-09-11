using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Security.Cryptography;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Web.Script.Serialization;
using Microsoft.Win32;
using Microsoft.Win32.SafeHandles;

namespace YingXu.Desktop
{
    internal static class Hub
    {
        internal static string Root;
        internal static string Cache;
        internal static string Data = DefaultData();
        internal static string Url;
        internal static int Port;

        internal static string DefaultData()
        {
            string configured = Environment.GetEnvironmentVariable("YINGXU_DATA_DIR");
            if (!String.IsNullOrEmpty(configured))
            {
                if (!Path.IsPathRooted(configured) || Path.GetPathRoot(configured).Length < 3)
                    throw new ArgumentException("YINGXU_DATA_DIR 必须是绝对路径。");
                return NormalizeRoot(configured);
            }
            return NormalizeRoot(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "YingXu"));
        }

        internal static string InstanceId()
        {
            return PathIdentity(NormalizeRoot(Data));
        }

        internal static string PathIdentity(string path)
        {
            // Match Python exactly: Unicode uppercasing is runtime-dependent.
            var normalized = new StringBuilder();
            foreach (char c in path.TrimEnd('\\', '/'))
                normalized.Append(c >= 'a' && c <= 'z' ? (char)(c - 32) : c);
            return Identity(normalized.ToString());
        }

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
                if (handle.IsInvalid) throw new IOException("无法读取 映序 程序目录。", new Win32Exception(Marshal.GetLastWin32Error()));
                var path = new StringBuilder(512);
                uint length = GetFinalPathNameByHandleW(handle, path, (uint)path.Capacity, 0);
                if (length >= path.Capacity)
                {
                    path.EnsureCapacity(checked((int)length + 1));
                    length = GetFinalPathNameByHandleW(handle, path, (uint)path.Capacity, 0);
                }
                if (length == 0 || length >= path.Capacity)
                    throw new IOException("无法解析 映序 程序目录。", new Win32Exception(Marshal.GetLastWin32Error()));
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

        internal static bool TryReadDragMessage(string source, string json, out string itemId)
        {
            itemId = null;
            if (!IsLocalPage(source, Url) || String.IsNullOrEmpty(json) || json.Length > 512) return false;
            try
            {
                var message = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(json);
                object action, id;
                if (message == null || message.Count != 2 || !message.TryGetValue("action", out action) ||
                    !message.TryGetValue("id", out id) || (action as string) != "drag-file") return false;
                string value = id as string;
                if (value == null || !Regex.IsMatch(value, "\\A[0-9a-fA-F]{32}\\z")) return false;
                itemId = value.ToLowerInvariant();
                return true;
            }
            catch { return false; }
        }

        internal static bool TryReadDragItemsMessage(string source, string json, out string[] itemIds)
        {
            return TryReadFileIdsMessage(source, json, "drag-files", out itemIds);
        }

        internal static bool TryReadFileIdsMessage(string source, string json, string expectedAction, out string[] itemIds)
        {
            itemIds = null;
            string legacyId;
            if (expectedAction == "drag-files" && TryReadDragMessage(source, json, out legacyId))
            {
                itemIds = new string[] { legacyId };
                return true;
            }
            if (!IsLocalPage(source, Url) || String.IsNullOrEmpty(json) || json.Length > 8192) return false;
            try
            {
                var message = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(json);
                object action, ids;
                if (message == null || message.Count != 2 || !message.TryGetValue("action", out action) ||
                    (action as string) != expectedAction || !message.TryGetValue("ids", out ids)) return false;
                var values = ids as System.Collections.ArrayList;
                if (values == null || values.Count == 0 || values.Count > 200) return false;
                var result = new List<string>();
                var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                foreach (object entry in values)
                {
                    string value = entry as string;
                    if (value == null || !Regex.IsMatch(value, "\\A[0-9a-fA-F]{32}\\z")) return false;
                    if (seen.Add(value)) result.Add(value.ToLowerInvariant());
                }
                itemIds = result.ToArray();
                return true;
            }
            catch { return false; }
        }

        private static readonly HashSet<string> DragExtensions = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
        {
            ".md", ".markdown", ".txt", ".json", ".csv", ".srt", ".vtt", ".yaml", ".yml",
            ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".avif",
            ".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v", ".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac",
            ".blend", ".fbx", ".obj", ".glb", ".gltf", ".stl", ".docx", ".pdf", ".doc", ".pptx", ".xlsx", ".rtf"
        };

        internal static string ValidateNativeFilePath(string value)
        {
            if (String.IsNullOrEmpty(value) || value.Length > 32700 || value.Length < 3 ||
                !Char.IsLetter(value[0]) || value[1] != ':' || (value[2] != '\\' && value[2] != '/'))
                throw new InvalidDataException("拖出文件必须位于本机磁盘的绝对路径。");
            string full = Path.GetFullPath(value);
            if (!DragExtensions.Contains(Path.GetExtension(full)))
                throw new InvalidDataException("此文件类型不支持拖出。");
            FileAttributes attributes = File.GetAttributes(full);
            if ((attributes & (FileAttributes.Directory | FileAttributes.ReparsePoint)) != 0)
                throw new InvalidDataException("拖出对象必须是普通文件，不能是目录、联接或符号链接。");
            for (DirectoryInfo parent = Directory.GetParent(full); parent != null; parent = parent.Parent)
                if ((File.GetAttributes(parent.FullName) & FileAttributes.ReparsePoint) != 0)
                    throw new InvalidDataException("拖出路径包含联接或符号链接，请从实际素材目录重新导入。");
            return full;
        }

        internal static string NativeFilePath(string itemId)
        {
            if (String.IsNullOrEmpty(itemId) || !Regex.IsMatch(itemId, "\\A[0-9a-f]{32}\\z"))
                throw new InvalidDataException("素材标识不正确。");
            var request = (HttpWebRequest)WebRequest.Create("http://127.0.0.1:" + Port + "/api/native-file/" + itemId);
            request.Proxy = null;
            request.AllowAutoRedirect = false;
            request.Timeout = 1500;
            request.ReadWriteTimeout = 1500;
            using (var response = (HttpWebResponse)request.GetResponse())
            using (var reader = new StreamReader(response.GetResponseStream()))
            {
                if (response.StatusCode != HttpStatusCode.OK)
                    throw new InvalidDataException("素材路径暂不可用，请刷新后重试。");
                var buffer = new char[65537];
                int count = reader.ReadBlock(buffer, 0, buffer.Length);
                if (count > 65536) throw new InvalidDataException("素材路径响应异常。");
                var record = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(new string(buffer, 0, count));
                object path;
                if (record == null || !record.TryGetValue("path", out path) || !(path is string))
                    throw new InvalidDataException("素材路径响应不完整。");
                return ValidateNativeFilePath((string)path);
            }
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
                    var buffer = new char[65537];
                    int count = reader.ReadBlock(buffer, 0, buffer.Length);
                    if (count > 65536) return false;
                    var health = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(new string(buffer, 0, count));
                    object name;
                    object ok, identity, version;
                    return health != null && health.TryGetValue("app", out name) && (name as string) == "yingxu" &&
                           health.TryGetValue("ok", out ok) && ok is bool && (bool)ok &&
                           health.TryGetValue("instance_id", out identity) && (identity as string) == InstanceId() &&
                           health.TryGetValue("version", out version) && (version as string) == "0.3.8";
                }
            }
            catch { return false; }
        }

        private static IEnumerable<string> PythonCandidates()
        {
            string configured = Environment.GetEnvironmentVariable("YINGXU_PYTHON");
            if (!String.IsNullOrEmpty(configured))
            {
                if (!Path.IsPathRooted(configured) || Path.GetPathRoot(configured).Length < 3)
                    throw new ArgumentException("YINGXU_PYTHON 必须是 Python 可执行文件的绝对路径。");
                yield return configured;
                yield break;
            }
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
                        if (!Version.TryParse(tag.Split('-')[0], out version) || version.Major != 3 || version.Minor < 11) continue;
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
            foreach (string directory in (Environment.GetEnvironmentVariable("PATH") ?? "").Split(Path.PathSeparator))
            {
                string clean = directory.Trim().Trim('"');
                if (clean.Length > 0 && Path.IsPathRooted(clean))
                    yield return Path.Combine(clean, "python.exe");
            }
        }

        private static bool CompatiblePython(string path)
        {
            if (!File.Exists(path)) return false;
            try
            {
                var start = new ProcessStartInfo(path, "-I -S -c " + Quote("import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)"));
                start.UseShellExecute = false;
                start.CreateNoWindow = true;
                start.WindowStyle = ProcessWindowStyle.Hidden;
                using (var process = Process.Start(start))
                {
                    if (!process.WaitForExit(3000)) { process.Kill(); return false; }
                    return process.ExitCode == 0;
                }
            }
            catch { return false; }
        }

        internal static string BundledBrowserFolder()
        {
            string folder = Path.Combine(Root, "runtime", "webview2");
            return File.Exists(Path.Combine(folder, "msedgewebview2.exe")) ? folder : null;
        }

        internal static void PrepareBrowserFolder(string folder)
        {
            // Fixed WebView2 >=120 requires AppContainer read/execute access on Windows 10.
            if (Environment.OSVersion.Version.Build >= 22000) return;
            var directory = new DirectoryInfo(folder);
            var security = directory.GetAccessControl();
            bool changed = false;
            foreach (string value in new[] { "S-1-15-2-1", "S-1-15-2-2" })
            {
                var sid = new System.Security.Principal.SecurityIdentifier(value);
                bool granted = false;
                foreach (System.Security.AccessControl.FileSystemAccessRule rule in security.GetAccessRules(true, true, typeof(System.Security.Principal.SecurityIdentifier)))
                    if (rule.IdentityReference.Equals(sid) && rule.AccessControlType == System.Security.AccessControl.AccessControlType.Allow &&
                        (rule.FileSystemRights & System.Security.AccessControl.FileSystemRights.ReadAndExecute) == System.Security.AccessControl.FileSystemRights.ReadAndExecute &&
                        (rule.InheritanceFlags & (System.Security.AccessControl.InheritanceFlags.ContainerInherit | System.Security.AccessControl.InheritanceFlags.ObjectInherit)) ==
                        (System.Security.AccessControl.InheritanceFlags.ContainerInherit | System.Security.AccessControl.InheritanceFlags.ObjectInherit)) granted = true;
                if (granted) continue;
                security.AddAccessRule(new System.Security.AccessControl.FileSystemAccessRule(sid,
                    System.Security.AccessControl.FileSystemRights.ReadAndExecute,
                    System.Security.AccessControl.InheritanceFlags.ContainerInherit | System.Security.AccessControl.InheritanceFlags.ObjectInherit,
                    System.Security.AccessControl.PropagationFlags.None, System.Security.AccessControl.AccessControlType.Allow));
                changed = true;
            }
            if (changed) directory.SetAccessControl(security);
        }

        internal static string FindPython()
        {
            foreach (string path in PythonCandidates()) if (CompatiblePython(path)) return Path.GetFullPath(path);
            throw new FileNotFoundException("未找到 Python 3.11 或更新版本。请安装 Python 3.11+，或用 YINGXU_PYTHON 指定完整的 python.exe 路径。程序不会自动下载。");
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
            start.EnvironmentVariables["PYTHONUTF8"] = "1";
            start.EnvironmentVariables["YINGXU_DATA_DIR"] = Data;
            using (var process = Process.Start(start))
            {
                // Drain pipes concurrently so a diagnostic message cannot block startup.
                var output = process.StandardOutput.ReadToEndAsync();
                var error = process.StandardError.ReadToEndAsync();
                if (!process.WaitForExit(30000))
                    throw new TimeoutException("后台启动超时，请查看 应用数据目录中的 launcher.log 和 server.log。稍后重新打开会复用已启动服务。");
                if (process.ExitCode != 0 || !Healthy(Port))
                    throw new InvalidOperationException("后台服务未能启动。如果刚更新过程序，请保存编辑、等待导入完成，关闭窗口并运行 Stop-YingXu.ps1 后重试。详细原因请查看应用数据目录中的 launcher.log 和 server.log。");
                string text = output.GetAwaiter().GetResult();
                error.GetAwaiter().GetResult();
                return text.Contains("\"started\"") ? "started" : "reused";
            }
        }

        internal static void Log(string message)
        {
            try
            {
                string directory = Data;
                Directory.CreateDirectory(directory);
                File.AppendAllText(Path.Combine(directory, "desktop.log"), DateTime.Now.ToString("s") + " " + message + Environment.NewLine, Encoding.UTF8);
            }
            catch { }
        }
    }
}
