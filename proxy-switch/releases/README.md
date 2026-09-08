# ProxySwitch 3.1.0 · Windows 源码运行包

[下载 ZIP · 约 276 KiB](ProxySwitch-v3.1.0-Windows-Source.zip?raw=true) · [SHA-256 校验](SHA256SUMS.txt) · [使用说明](../README.md) · [更新记录](../CHANGELOG.md)

完整解压 ZIP，打开 `proxy-switch` 文件夹，双击 `启动代理切换.cmd`。这是 PowerShell / WinForms 源码运行包，不捆绑 VPN、代理服务或运行依赖。

3.1.0 新增 Chromium/Electron 程序启动代理。界面使用代理启动参数，支持 HTTP 代理环境变量的子进程继承同一入口，无需额外代理客户端充当中转。工具备份并接入桌面原图标，每次启动读取当前选择和端口。已有自定义启动参数的图标会保留，另外创建代理入口。

指定线路后先保存任务、完整退出程序，再从接入后的桌面入口打开。仅保存目标不能改变已运行的进程。工具不自动结束应用，列表区分“等待重开”“已启动待验证”和“已观察到目标代理连接”，并汇总联网子进程。统一切换会撤销专用目标，已接入的启动入口在下次启动时跟随统一线路。

需要 Windows 10 / 11、Windows PowerShell 5.1、.NET Framework 4.8 与 `curl.exe`。HTTP / 直连系统切换和 Chromium/Electron 启动适配不需要 Node.js。其他程序的引擎规则分流及 SOCKS5 统一切换需要 Node.js 22+ 和可选的 Clash Verge Rev / Mihomo 引擎。忽略系统代理、启动参数和代理环境变量的软件，不会因此被强制接管。[运行要求](../README.md#运行要求)

压缩包为 **283,098 字节**，包含 40 个文件。截图均使用演示数据，不含本机代理、账号、订阅、个人程序规则、启动记录或快捷方式备份。

SHA-256：

```text
c63c85824fb422b0efe6445305a83eeccd928e95d2a2448b92d710d99457682c
```

```powershell
Get-FileHash .\ProxySwitch-v3.1.0-Windows-Source.zip -Algorithm SHA256
```

验证：175 项断言，包括真实临时父子程序的环境继承、旧变量隔离、桌面入口备份恢复、重复启动拒绝和统一回滚。另有 PowerShell / Node.js 语法、界面 SmokeTest，以及四种隔离界面回归。干净解压目录再次通过静态、单元与 SmokeTest 检查。

程序启动适配不等于所有程序的流量拦截。此前游戏登录错误 [4] 的具体根因与长期稳定性尚未确认，不以本次程序代理修复替代游戏验收。

历史版本：[3.0.3](ProxySwitch-v3.0.3-Windows-Source.zip?raw=true)、[3.0.2](ProxySwitch-v3.0.2-Windows-Source.zip?raw=true)、[3.0.1](ProxySwitch-v3.0.1-Windows-Source.zip?raw=true)、[3.0.0](ProxySwitch-v3.0.0-Windows-Source.zip?raw=true)。
