# AI Hub 桌面入口

`AI Hub.exe` 是 Windows x64 图形应用，使用深色 WinForms 窗口承载现有 WebView2 工作台。后台仍是现有 Python 标准库服务，页面和数据与浏览器入口共用。

## 日常运行

双击解压目录中的 AI Hub.exe，也可以为它创建桌面快捷方式。EXE 必须与 `server.py`、`launcher.pyw`、`frontend` 同级；移动整个项目目录后重新建立快捷方式即可。开发测试可以指定 `--root "程序目录"`。程序不申请管理员权限，不配置开机启动。

重复运行会激活同一程序目录的已有窗口。关闭窗口释放页面进程，保留共享后台服务及扫描任务。后台端口沿用 `data/config.json`，只连接 `127.0.0.1`。网页来源链接交给默认浏览器；桌面窗口只加载本地工作台。

主机需要 Python 3.9+、.NET Framework 4.8+、Microsoft Edge WebView2 Runtime。EXE 包含 WebView2 Core、WinForms 与 x64 Loader 三个 SDK 组件，首次启动在程序的 data/desktop 目录释放经摘要校验的 Loader。它不包含 Python、本机模型和资产数据库；请保留整个程序目录与 Python 安装。

`data/desktop.log` 记录窗口与服务启动结果。窗口尺寸、收藏、WebView2 配置和嵌入 Loader 统一存放在项目 `data/desktop`。这样从资源管理器或打包的开发工具启动时也使用同一配置，避免 LocalAppData 虚拟化形成两份状态。评分、备注、来源仍在项目 `data`；外部普通浏览器收藏不自动迁入。

启动器通过目录句柄解析联接的物理路径，再生成单实例标识。多个目录联接入口共用同一窗口和 data。

## 可复现构建

不安装 pip、npm 或 Visual Studio。使用 Windows 自带的 .NET Framework C# 编译器。先手动取得微软官方 SDK 归档，构建脚本只读取本地包并验证摘要，不联网下载。

```powershell
python -B desktop/build.py --sdk-package "下载目录/microsoft.web.webview2.1.0.4191.47.nupkg" --output "临时目录/AI Hub.exe" --test
```

SDK 版本：`1.0.4191.47`。官方 nupkg：9,259,926 字节（8.83 MiB）。SHA-256：`f492bbf547d0da329553b6727435b677579b1e9f91cc9e4a1ad029366d5f23d0`。

构建参数为 `target:winexe`、`platform:x64`，包含图标与 asInvoker / PerMonitorV2 清单。测试覆盖配置、端口边界、URL 来源、Windows 参数转义、服务身份、真实 Python 冷启动与无控制台进程。冷启动只使用独立临时夹与自退测试服务，不重启用户服务。

安装新版 EXE 前关闭 AI Hub 桌面窗口，备份旧 EXE、快捷方式和源码；无需停止 Python 服务。只复制程序文件，不覆盖 `data`。主服务/前端测试仍按项目 AGENTS.md 执行。

组件来源与实现参考：

- [Microsoft 官方 SDK 包](https://www.nuget.org/packages/Microsoft.Web.WebView2/1.0.4191.47)
- [WebView2 WinForms 指南](https://learn.microsoft.com/en-us/microsoft-edge/webview2/get-started/winforms)
- [WebView2 分发说明](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution)
- [WebView2 安全实践](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/security)

SDK 许可全文见 `WebView2-LICENSE.txt`，同时嵌入 EXE。

开发机如已缓存 SDK，可以直接传给 `--sdk-package`。公开源码包不包含 SDK 缓存；Windows 桌面包中的 EXE 已包含运行所需的三个 SDK 组件。
