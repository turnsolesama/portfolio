using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Windows.Forms;
using Microsoft.Win32;
[assembly: AssemblyTitle("Codex Switcher")]
[assembly: AssemblyVersion("2.1.1.0")]
[assembly: AssemblyFileVersion("2.1.1.0")]
class Launcher {
    static string FindPython(string root) {
        string bundled=Path.Combine(root,"runtime","pythonw.exe");
        if(File.Exists(bundled)) return bundled;
        foreach(RegistryKey hive in new[]{Registry.CurrentUser,Registry.LocalMachine}) {
            using(RegistryKey versions=hive.OpenSubKey(@"SOFTWARE\Python\PythonCore")) {
                if(versions==null) continue;
                foreach(string name in versions.GetSubKeyNames().OrderByDescending(x=>x)) {
                    Version version;
                    if(!Version.TryParse(name.Split('-')[0],out version) || version<new Version(3,11))continue;
                    using(RegistryKey key=versions.OpenSubKey(name+@"\InstallPath")) {
                        string folder=key==null?null:key.GetValue(null) as string;
                        if(folder!=null && File.Exists(Path.Combine(folder,"pythonw.exe")))return Path.Combine(folder,"pythonw.exe");
                    }
                }
            }
        }
        return null;
    }
    [STAThread] static int Main(string[] args) {
        try {
            string root=AppDomain.CurrentDomain.BaseDirectory;
            string script=Path.Combine(root,"codex_switcher.pyw");
            if(!File.Exists(script)||!File.Exists(Path.Combine(root,"switcher_core.py"))||!File.Exists(Path.Combine(root,"switcher_ui.py")))throw new Exception("请保留完整解压目录，程序文件不完整。");
            string python=FindPython(root);
            if(python==null)throw new Exception("未找到 Python 3.11 或更新版本。请安装包含 Tkinter 的官方 Windows Python，或将运行环境放到 runtime 目录。");
            if(Array.IndexOf(args,"--check")>=0)return 0;
            var info=new ProcessStartInfo(python,"-B \""+script+"\""+(Array.IndexOf(args,"--demo")>=0?" --demo":""));
            info.WorkingDirectory=root;info.UseShellExecute=false;info.CreateNoWindow=true;
            Process.Start(info);return 0;
        }catch(Exception error){MessageBox.Show(error.Message,"Codex Switcher · 启动提示",MessageBoxButtons.OK,MessageBoxIcon.Information);return 1;}
    }
}
