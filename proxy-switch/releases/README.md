# ProxySwitch 3.0.2 · Windows 源码运行包

[下载 ZIP · 约 243 KiB](ProxySwitch-v3.0.2-Windows-Source.zip?raw=true) · [SHA-256 校验文件](SHA256SUMS.txt) · [使用说明](../README.md) · [更新记录](../CHANGELOG.md)

完整解压 ZIP，打开 `proxy-switch` 文件夹，双击 `启动代理切换.cmd`。这是 PowerShell / WinForms 源码运行包，不捆绑 VPN、代理服务或运行依赖。

3.0.2 的启动、自动刷新和退出均被动读取状态。代理发现改为手动触发，排除游戏和无关程序的通信端口；普通 HTTP 切换直接使用所选端口，撤回前拒绝失效的本地代理变量端口，回滚保留其他客户端的新选择。

需要 Windows 10 / 11、Windows PowerShell 5.1、.NET Framework 4.8 与 `curl.exe`。基础 HTTP / 直连无需 Node.js；程序分流与 SOCKS5 统一切换另需 Node.js 22+ 和可选的 Clash Verge Rev / Mihomo 引擎。[运行要求](../README.md#运行要求)

切换影响新连接。已有程序及其启动器可能保留启动时的环境变量，需要用户自行重开。本工具不自动结束游戏或代理客户端。

压缩包为 **248,941 字节**，包含 34 个文件。截图均为演示数据，不含本机代理配置、账号、订阅、个人程序规则或备份。

SHA-256：

```text
ba53ce74e7412055421752e93fde3de3a535c6a2e5df0b4bf67be00bc673aff4
```

```powershell
Get-FileHash .\ProxySwitch-v3.0.2-Windows-Source.zip -Algorithm SHA256
```

验证：136 项断言、PowerShell / Node.js 语法检查、界面 SmokeTest、手动发现和 72 秒被动刷新及退出测试。对应游戏版本的实际登录仍需现场复测，以上检查不代表已确认游戏错误 [4] 的唯一原因。源码和第三方许可证随包保留。

历史版本：[3.0.1](ProxySwitch-v3.0.1-Windows-Source.zip?raw=true)、[3.0.0](ProxySwitch-v3.0.0-Windows-Source.zip?raw=true)。
