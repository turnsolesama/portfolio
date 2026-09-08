# ProxySwitch 3.0.1 · Windows 源码运行包

[下载 ZIP · 约 232 KiB](ProxySwitch-v3.0.1-Windows-Source.zip?raw=true) · [SHA-256 校验文件](SHA256SUMS.txt) · [使用说明](../README.md) · [更新记录](../CHANGELOG.md)

完整解压 ZIP，打开 `proxy-switch` 文件夹，双击 `启动代理切换.cmd`。这是 PowerShell / WinForms 源码运行包，未封装独立 EXE，也不捆绑 VPN、代理服务或运行依赖。

需要 Windows 10 / 11、Windows PowerShell 5.1、.NET Framework 4.8 与 `curl.exe`。普通 HTTP 系统代理和直连切换无需 Node.js；按程序分流与 SOCKS5 统一切换另需 Node.js 22+ 和已配置的 Clash Verge Rev / Mihomo 分流引擎，详见[运行要求](../README.md#运行要求)。

启动后自动发现后台 HTTP / SOCKS5 入口，验证后加入列表；也可手动重新检测或添加远程入口。3.0.1 同步刷新配置、下拉框和列表，避免后台代理未显示。检测不更改网络设置。切换影响新连接，已有连接可能需要刷新网页或重开对应程序。

压缩包为 **237,610 字节**，包含 31 个文件。公开截图使用演示数据；不包含本机代理配置、账号、订阅、个人程序规则或备份。

SHA-256：

```text
29a306d464cef0ee0ffb4113c11beec77ee078d4833b72b888bc8c5a9834300f
```

下载后可用以下命令核对：

```powershell
Get-FileHash .\ProxySwitch-v3.0.1-Windows-Source.zip -Algorithm SHA256
```

发布前完成 117 项单元断言、PowerShell / Node.js 语法检查、界面检查，以及隔离引擎中的 4 种程序线路和 4 种统一线路验证。源码使用 MIT 许可证，第三方许可证随包保留。


历史版本：[3.0.0 源码运行包](ProxySwitch-v3.0.0-Windows-Source.zip?raw=true)。
