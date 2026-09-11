// Isolated fixed-runtime smoke test. Never opens the user's workbench or data.
using System;
using System.IO;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace YingXu.Desktop
{
    internal static class RuntimeCheck
    {
        [STAThread]
        private static int Main(string[] args)
        {
            Application.EnableVisualStyles();
            Hub.Root = args[0];
            string temporary = Path.Combine(Path.GetTempPath(), "yingxu-webview-test-" + Guid.NewGuid().ToString("N"));
            Hub.Data = temporary;
            Hub.Cache = temporary;
            Directory.CreateDirectory(temporary);
            string result = "not completed";
            using (var form = new Form { ShowInTaskbar = false, Opacity = 0, Width = 640, Height = 480 })
            using (var web = new WebView2 { Dock = DockStyle.Fill })
            using (var timeout = new Timer { Interval = 45000 })
            {
                form.Controls.Add(web);
                timeout.Tick += delegate { result = "timeout"; form.Close(); };
                form.Shown += async delegate
                {
                    timeout.Start();
                    try
                    {
                        string folder = Hub.BundledBrowserFolder();
                        if (folder == null) throw new Exception("Bundled browser missing");
                        Hub.PrepareBrowserFolder(folder);
                        var environment = await CoreWebView2Environment.CreateAsync(folder, temporary);
                        await web.EnsureCoreWebView2Async(environment);
                        // Prove the fixed browser started; installed Evergreen cannot satisfy this check.
                        if (environment.BrowserVersionString != "152.0.4191.62") throw new Exception("Unexpected runtime version");
                        web.CoreWebView2.NavigationCompleted += async delegate(object sender, CoreWebView2NavigationCompletedEventArgs e)
                        {
                            try
                            {
                                if (!e.IsSuccess) throw new Exception("Navigation failed");
                                string value = await web.CoreWebView2.ExecuteScriptAsync("document.getElementById('fixture').textContent + ':' + !!document.createElement('canvas').getContext('2d')");
                                if (value != "\"YingXu:true\"") throw new Exception("Rendering/JavaScript check failed: " + value);
                                result = "PASS bundled WebView2 navigation, JavaScript and Canvas, no system browser";
                            }
                            catch (Exception error) { result = error.ToString(); }
                            form.Close();
                        };
                        web.CoreWebView2.NavigateToString("<!doctype html><meta charset=utf-8><p id=fixture>YingXu</p>");
                    }
                    catch (Exception error) { result = error.ToString(); form.Close(); }
                };
                Application.Run(form);
            }
            // Browser children can finish releasing their profile after controller disposal.
            for (int attempt = 0; attempt < 20; attempt++)
            {
                try { Directory.Delete(temporary, true); break; }
                catch (IOException) { System.Threading.Thread.Sleep(100); }
                catch (UnauthorizedAccessException) { System.Threading.Thread.Sleep(100); }
            }
            Console.WriteLine(result);
            return result.StartsWith("PASS ") ? 0 : 1;
        }
    }
}
