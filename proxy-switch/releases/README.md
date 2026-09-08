# ProxySwitch 3.0.3 · Windows 源码运行包

[下载 ZIP · 约 259 KiB](ProxySwitch-v3.0.3-Windows-Source.zip?raw=true) · [SHA-256 校验文件](SHA256SUMS.txt) · [使用说明](../README.md) · [更新记录](../CHANGELOG.md)

完整解压 ZIP，打开 `proxy-switch` 文件夹，双击 `启动代理切换.cmd`。这是 PowerShell / WinForms 源码运行包，不捆绑 VPN、代理服务或运行依赖。

3.0.3 恢复启动与定时自动发现，并提供独立开关。后台识别核实代理进程与端口归属，缓存结果，不扫描游戏通信端口；未知客户端可从当前系统代理与变量设置被动识别。程序连接监控、右键分流与统一切换保留。

进程路径查询改用有限权限接口，避免旧版路径查询隐式请求目标内存读取权限。统一切换预检并行进行，任一可用即继续，单项最多 5 秒；显示阶段进度，用户操作优先于后台发现。引擎重载与系统写入另外计时，已有连接不会被强制断开。

需要 Windows 10 / 11、Windows PowerShell 5.1、.NET Framework 4.8 与 `curl.exe`。基础 HTTP / 直连无需 Node.js；程序分流与 SOCKS5 统一切换另需 Node.js 22+ 和可选的 Clash Verge Rev / Mihomo 引擎。[运行要求](../README.md#运行要求)

切换影响遵循系统代理或已接入分流引擎的新连接。已有程序可能仍使用启动时的环境变量或自己的代理设置。本工具不自动结束游戏、启动器或代理客户端。

压缩包为 **265,306 字节**，包含 38 个文件。截图均为演示数据，不含本机代理配置、账号、订阅、个人程序规则或备份。

SHA-256：

```text
76be6c69e39545e05728a681301bb6490c4f484d8d220a797f4c37ea0934dd20
```

```powershell
Get-FileHash .\ProxySwitch-v3.0.3-Windows-Source.zip -Algorithm SHA256
```

验证：152 项断言、PowerShell / Node.js 语法、界面 SmokeTest、手动发现、自动发现与缓存、切换进度与实读、72 秒观察与退出测试。隔离界面使用独立配置、模拟 Windows 写入及专属测试锁。干净解压目录通过同一套静态与单元检查。

3.0.2 关闭自动发现后，现场仍出现登录失败，之后也有管理器保持运行时一次登录成功。3.0.3 修复的是已确认的实现问题；目前不能宣称游戏错误 [4] 的根因已找到或长期稳定性已经验收。

历史版本：[3.0.2](ProxySwitch-v3.0.2-Windows-Source.zip?raw=true)、[3.0.1](ProxySwitch-v3.0.1-Windows-Source.zip?raw=true)、[3.0.0](ProxySwitch-v3.0.0-Windows-Source.zip?raw=true)。
