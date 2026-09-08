# ProxySwitch 3.0.0 · Windows 源码运行包

[下载 ZIP · 约 224 KiB](ProxySwitch-v3.0.0-Windows-Source.zip?raw=true) · [SHA-256 校验文件](SHA256SUMS.txt) · [使用说明](../README.md) · [更新记录](../CHANGELOG.md)

完整解压 ZIP，打开 `proxy-switch` 文件夹，双击 `启动代理切换.cmd`。这是 PowerShell / WinForms 源码运行包，未封装独立 EXE，也不捆绑 VPN、代理服务或运行依赖。

需要 Windows 10 / 11、Windows PowerShell 5.1、.NET Framework 4.8 与 `curl.exe`。普通 HTTP 系统代理和直连切换无需 Node.js；按程序分流与 SOCKS5 统一切换另需 Node.js 22+ 和已配置的 Clash Verge Rev / Mihomo 分流引擎，详见[运行要求](../README.md#运行要求)。

全新安装的代理列表为空，请在「代理管理」中添加自己的入口。切换影响新连接，已有连接可能需要刷新网页或重开对应程序。

压缩包为 **229,387 字节**，包含 29 个文件。公开截图使用演示数据；不包含本机代理配置、账号、订阅、个人程序规则或备份。

SHA-256：

```text
ccb68e03711aacf0f62503b4aa48fe09cfb21a0552101f5e63bc930f586081b1
```

下载后可用以下命令核对：

```powershell
Get-FileHash .\ProxySwitch-v3.0.0-Windows-Source.zip -Algorithm SHA256
```

发布前完成 95 项单元断言、PowerShell / Node.js 语法检查、界面检查，以及隔离引擎中的 4 种程序线路和 4 种统一线路验证。源码使用 MIT 许可证，第三方许可证随包保留。

