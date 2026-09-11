using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;

[assembly: AssemblyTitle("流向 · FlowSwitch")]
[assembly: AssemblyDescription("FlowSwitch Windows proxy manager")]
[assembly: AssemblyProduct("流向 · FlowSwitch")]

internal static class Launcher
{
    // Quote each argument for CreateProcess; never pass a command through cmd.exe.
    private static string Quote(string value)
    {
        var result = new StringBuilder("\"");
        int slashes = 0;
        foreach (char c in value)
        {
            if (c == '\\') { slashes++; continue; }
            if (c == '"') result.Append('\\', slashes * 2 + 1);
            else result.Append('\\', slashes);
            result.Append(c);
            slashes = 0;
        }
        result.Append('\\', slashes * 2);
        return result.Append('"').ToString();
    }

    private static void VerifyFiles(string app)
    {
        string[] required = {
            "ProxySwitch.ps1", "ProxyWindow.ps1", "ProxyBackend.ps1", "Preferences.ps1",
            "Storage.ps1", "RuntimeSupport.ps1", "DesktopBranding.cs", "FlowTheme.cs", "ProgramLaunch.ps1", "ProcessInventory.ps1", "ProxyDiscovery.ps1",
            "ProgramIdentity.ps1", "ProgramFamilyTracking.ps1", "ManagedRouting.ps1", "ApplicationObservation.ps1", "RuleMaintenance.ps1", "RoutePolicy.cjs", "GatewayPortOwnership.ps1",
            "AppRouting.ps1", "AppRouter.cjs", "IndependentRouter.cjs", "IndependentGateway.ps1", "GatewayWatchdog.ps1", "GatewayLock.ps1", "config.defaults.json", "Install-Shortcut.ps1",
            "assets/FlowSwitch.ico", "vendor/js-yaml/dist/js-yaml.cjs.js",
            "runtime/node.exe", "runtime/FlowSwitch.Core.exe", "runtime/FlowSwitch.Core.Compat.exe", "runtime/runtime-manifest.json"
        };
        foreach (string name in required)
            if (!File.Exists(Path.Combine(app, name)))
                throw new FileNotFoundException("程序文件不完整：" + name + "\r\n请完整解压程序包，保留 EXE 旁的 app 文件夹。");
    }

    [STAThread]
    private static int Main(string[] args)
    {
        string mode = "", dataDirectory = null;
        bool quiet = Array.Exists(args, a => a == "--quiet" || a == "--verify" || a == "--smoke-test" || a == "--status");
        try
        {
            for (int i = 0; i < args.Length; i++)
            {
                if (args[i] == "--quiet") continue;
                if (args[i] == "--data-directory" && i + 1 < args.Length)
                {
                    if (dataDirectory != null) throw new ArgumentException("配置目录只能指定一次。");
                    dataDirectory = Path.GetFullPath(args[++i]);
                }
                else if (args[i] == "--verify" || args[i] == "--smoke-test" || args[i] == "--status" || args[i] == "--install-shortcut")
                {
                    if (mode.Length != 0) throw new ArgumentException("一次只能选择一种启动操作。");
                    mode = args[i];
                }
                else throw new ArgumentException("不支持的启动参数：" + args[i]);
            }
            string root = AppDomain.CurrentDomain.BaseDirectory;
            string app = Path.Combine(root, "app");
            VerifyFiles(app);
            if (mode == "--verify") { Console.WriteLine("PASS: FlowSwitch " + Assembly.GetExecutingAssembly().GetName().Version.ToString(3) + " Windows package files are present."); return 0; }

            string shell = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows), "System32", "WindowsPowerShell", "v1.0", "powershell.exe");
            if (!File.Exists(shell)) throw new FileNotFoundException("找不到 Windows PowerShell 5.1。");
            var command = new List<string> { "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File" };
            if (mode == "--install-shortcut")
            {
                command.Add(Path.Combine(app, "Install-Shortcut.ps1"));
                command.Add("-LauncherPath"); command.Add(Path.Combine(root, "FlowSwitch.exe"));
            }
            else
            {
                command.Add(Path.Combine(app, "ProxySwitch.ps1"));
                if (mode == "--smoke-test") command.Add("-SmokeTest");
                if (mode == "--status") command.Add("-Status");
                if (dataDirectory != null) { command.Add("-DataDirectory"); command.Add(dataDirectory); }
            }
            var info = new ProcessStartInfo(shell, String.Join(" ", command.ConvertAll(Quote).ToArray()));
            info.WorkingDirectory = app;
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            info.WindowStyle = ProcessWindowStyle.Hidden;
            info.RedirectStandardOutput = true;
            info.RedirectStandardError = true;
            // Only the child process receives a custom data directory. No registry or user environment writes.
            if (mode == "--install-shortcut" && dataDirectory != null) info.EnvironmentVariables["PROXY_SWITCH_DATA_DIR"] = dataDirectory;
            using (var process = Process.Start(info))
            {
                if (process == null) throw new InvalidOperationException("无法启动代理管理器。");
                Task<string> output = process.StandardOutput.ReadToEndAsync();
                Task<string> errors = process.StandardError.ReadToEndAsync();
                process.WaitForExit(); Task.WaitAll(output, errors);
                Console.Write(output.Result); Console.Error.Write(errors.Result);
                if (process.ExitCode != 0)
                {
                    string detail = errors.Result.Length == 0 ? "请检查 app 文件夹是否完整。" : errors.Result;
                    if (detail.Length > 1600) detail = detail.Substring(0, 1600);
                    if (!quiet) MessageBox.Show("启动未完成。\r\n\r\n" + detail, "流向 · FlowSwitch", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                }
                else if (mode == "--install-shortcut" && !quiet) MessageBox.Show("桌面快捷方式已创建。", "流向 · FlowSwitch", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return process.ExitCode;
            }
        }
        catch (Exception error)
        {
            Console.Error.WriteLine(error.Message);
            if (!quiet) MessageBox.Show(error.Message, "流向 · FlowSwitch", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return 1;
        }
    }
}
