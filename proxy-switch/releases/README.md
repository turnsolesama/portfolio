# ProxySwitch 3.1.1 · Windows 源码运行包

[下载 ZIP · 约 281 KiB](ProxySwitch-v3.1.1-Windows-Source.zip?raw=true) · [SHA-256 校验](SHA256SUMS.txt) · [使用说明](../README.md) · [更新记录](../CHANGELOG.md)

完整解压 ZIP，打开 `proxy-switch` 文件夹，双击 `启动代理切换.cmd`。这是 PowerShell / WinForms 源码运行包，不捆绑 VPN、代理服务或运行依赖。

3.1.1 修复“管理器中已配置，但从桌面打开却提示未配置”的一种已确认原因：MSIX 应用启动的进程与普通桌面进程可能看到不同的 AppData 文件。默认本机数据改为 `%USERPROFILE%\.proxyswitch`，所有入口共享。界面与后台工作进程也会保留显式指定的配置目录。[Windows 文件重定向说明](https://learn.microsoft.com/en-us/windows/msix/desktop/desktop-to-uwp-behind-the-scenes)

首次迁移复制当前环境可见的旧默认目录数据与备份，原文件保留。完整复制后才启用新目录；已有新目录不会被旧文件覆盖。迁移不应用历史网络选择。已产生两套旧数据时，需要先核对并合并差异，自动迁移不会搜索其他应用的私有目录。旧桌面入口的默认 AppData 参数通过迁移记录兼容，其他自定义目录保持原样。

保留 3.1 的 Chromium/Electron 程序启动代理：支持的界面使用代理启动参数，支持代理变量的子进程继承所选 HTTP 入口。指定线路后先保存任务、完整退出程序，再从接入的桌面入口打开。不会自动结束程序，也不会仅凭保存目标就显示生效。

需要 Windows 10 / 11、Windows PowerShell 5.1、.NET Framework 4.8 与 `curl.exe`。HTTP / 直连系统切换和 Chromium/Electron 启动适配不要求 Node.js。引擎规则分流及 SOCKS5 统一切换需要 Node.js 22+ 和可选分流引擎。[运行要求](../README.md#运行要求)

压缩包为 **287,707 字节**，包含 42 个文件。公开截图均使用演示数据，不含本机代理配置、个人程序规则、启动记录或快捷方式备份。

SHA-256：

```text
5b979ae7933b657ecdc15dd4bc39268ba61b8772f36b470bdf69ddebf701738d
```

```powershell
Get-FileHash .\ProxySwitch-v3.1.1-Windows-Source.zip -Algorithm SHA256
```

验证：188 项断言，包括 13 项目录解析与迁移回归，以及真实临时父子程序的环境继承和入口备份恢复。另有 PowerShell / Node.js 语法检查、界面 SmokeTest 和四种隔离界面回归；配置目录测试验证显式目录从入口传到界面和后台。干净解压目录通过静态、单元与 SmokeTest 检查。这些检查不能替代用户实际桌面点击与目标软件功能验收。

本次修复针对桌面启动读取不到配置的问题。此前游戏登录错误 [4] 的具体根因与长期稳定性仍未确认。

历史版本：[3.1.0](ProxySwitch-v3.1.0-Windows-Source.zip?raw=true)、[3.0.3](ProxySwitch-v3.0.3-Windows-Source.zip?raw=true)、[3.0.2](ProxySwitch-v3.0.2-Windows-Source.zip?raw=true)、[3.0.1](ProxySwitch-v3.0.1-Windows-Source.zip?raw=true)、[3.0.0](ProxySwitch-v3.0.0-Windows-Source.zip?raw=true)。
