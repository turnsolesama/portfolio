# ProxySwitch 3.1.2 · 下载与校验

普通使用请选择 **Windows x64 程序包**，完整解压后双击 `ProxySwitch.exe`，无需编译或安装开发工具。请保留 EXE 旁的 `app` 文件夹。双击「创建桌面快捷方式.cmd」可创建或更新桌面入口。

| 下载 | 大小 | 用途 |
| --- | --- | --- |
| **[Windows x64 程序包](https://raw.githubusercontent.com/turnsolesama/portfolio/main/proxy-switch/releases/ProxySwitch-v3.1.2-Windows-x64.zip)** | 96,145 字节 · 22 个文件 | 直接打开 EXE，包含运行模块 |
| [源码包](https://raw.githubusercontent.com/turnsolesama/portfolio/main/proxy-switch/releases/ProxySwitch-v3.1.2-Windows-Source.zip) | 297,388 字节 · 46 个文件 | 修改源码、运行测试或重新构建 |

[使用说明](../README.md) · [运行要求](../README.md#运行要求) · [更新记录](../CHANGELOG.md) · [SHA256SUMS.txt](SHA256SUMS.txt)

运行需要 Windows 10 / 11 x64、Windows PowerShell 5.1、.NET Framework 4.8 和 curl.exe。EXE 是编译后的 Windows 启动入口，运行模块仍使用 Windows 自带 PowerShell。基础 HTTP / 直连及支持的程序启动代理不要求 Node.js；可选引擎规则分流与 SOCKS5 统一切换需要 Node.js 22+ 和受支持的分流引擎。程序不捆绑 VPN、代理服务或节点。

3.1.2 新增 EXE 发行包，保留 3.1.1 的共享数据目录 `%USERPROFILE%\.proxyswitch`，已有代理和程序规则继续读取。升级不会自动应用历史选择，旧连接和已运行软件仍需按需重开。

验证：188 项基础断言和 10 项 Windows 程序包检查。实际编译为 x64 Windows GUI EXE，移动到含中文与空格的目录后打开真实界面并正常退出；验证显式配置目录、目录末尾分隔符、缺失文件处理、隔离桌面快捷方式及其启动参数。干净解压源码包通过静态与单元检查。测试不切换真实网络。

两个包均使用文件清单与 SHA-256 校验，只包含本软件的源码或运行文件，不含用户代理、启动记录、账号、迁移数据或快捷方式备份。此前游戏错误 [4] 的具体原因不由本次发行包验收推定。

SHA-256：

```text
357c5d3328a9db96c71cb7858b03faa1515f428c869fde5fda510f7ea0575e9b  ProxySwitch-v3.1.2-Windows-x64.zip
55325b0e4f3f811b420b4bc099030a7760d8f9fe23a3e32e13a3a59525fa7eed  ProxySwitch-v3.1.2-Windows-Source.zip
```

历史源码包：[3.1.1](https://raw.githubusercontent.com/turnsolesama/portfolio/main/proxy-switch/releases/ProxySwitch-v3.1.1-Windows-Source.zip)、[3.1.0](https://raw.githubusercontent.com/turnsolesama/portfolio/main/proxy-switch/releases/ProxySwitch-v3.1.0-Windows-Source.zip)、[3.0.3](https://raw.githubusercontent.com/turnsolesama/portfolio/main/proxy-switch/releases/ProxySwitch-v3.0.3-Windows-Source.zip)、[3.0.2](https://raw.githubusercontent.com/turnsolesama/portfolio/main/proxy-switch/releases/ProxySwitch-v3.0.2-Windows-Source.zip)、[3.0.1](https://raw.githubusercontent.com/turnsolesama/portfolio/main/proxy-switch/releases/ProxySwitch-v3.0.1-Windows-Source.zip)、[3.0.0](https://raw.githubusercontent.com/turnsolesama/portfolio/main/proxy-switch/releases/ProxySwitch-v3.0.0-Windows-Source.zip)。
