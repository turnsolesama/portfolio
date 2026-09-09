# 流向 FlowSwitch 3.2.1 · 下载与校验

普通使用下载 **Windows x64 程序包**，完整解压后双击 `FlowSwitch/FlowSwitch.exe`。请保留 EXE 旁的 `app` 文件夹。源码包用于开发与重新构建。

| 下载 | 大小 | 文件数 |
| --- | --- | --- |
| [Windows x64 程序包](https://raw.githubusercontent.com/turnsolesama/portfolio/main/proxy-switch/releases/FlowSwitch-v3.2.1-Windows-x64.zip) | 356,653 字节 | 23 |
| [源码包](https://raw.githubusercontent.com/turnsolesama/portfolio/main/proxy-switch/releases/FlowSwitch-v3.2.1-Windows-Source.zip) | 1,660,375 字节 | 50 |

[使用说明](../README.md) · [运行要求](../README.md#运行要求) · [更新记录](../CHANGELOG.md) · [SHA256SUMS.txt](SHA256SUMS.txt)

3.2.1 将原 ProxySwitch 更名为「流向 · 网络代理管家 / FlowSwitch」，更新桌面、窗口和任务栏图标，包含固定入口模式、程序分流和确认后重连。原数据目录 `%USERPROFILE%\.proxyswitch` 保持兼容；升级不会自动切换代理。

运行要求：Windows 10 / 11 x64、Windows PowerShell 5.1、.NET Framework 4.8 和 curl.exe。可选引擎功能需要 Node.js 22+ 与已安装的受支持分流引擎。程序不捆绑 VPN 或代理节点。固定入口只管理已接入引擎的连接，不自动开启 TUN。

验证：207 项静态与基础断言、17 项真实隔离网关检查、12 项 Windows 程序包检查，以及隔离的切换交互检查。包检查覆盖中文与空格路径、真实 UI 启动、所选配置目录、桌面入口、任务栏标识与长命令边界。任务栏重开信息超过 Windows 支持长度时保留窗口图标，禁用该实例的固定操作，不截断路径。

包内使用显式文件清单与 SHA-256 校验，不含个人配置、代理规则、凭据、启动记录或实机截图；公开截图为演示数据。

```text
80f005d6ce6264384831b3317cd4bcefb5e7a0b8928e89d73512a380d9d11b08  FlowSwitch-v3.2.1-Windows-x64.zip
a8781de2e48f0aae403983e503c0f747a6b0be9e08f08a979bda7d77e9cdaeae  FlowSwitch-v3.2.1-Windows-Source.zip
```


## 本版功能与使用条件

| 功能 | 行为与条件 |
| --- | --- |
| 代理发现与管理 | 识别后台代理，可手动添加 HTTP / SOCKS5 入口；不捆绑 VPN、不要求安装 Upnet，发现不会自动切换线路 |
| 统一切换 | 同步系统入口和代理变量，并撤销本工具的程序专用目标；用户点击后才应用 |
| 固定入口 | 保持本地入口，通过已配置的 Clash Verge Rev / mihomo 切换 HTTP、SOCKS5 或直连出口；引擎需要保持运行 |
| 按程序分流 | 右键按 EXE 完整路径设置直连、指定代理或跟随统一线路；只对实际进入引擎的连接生效，不新建代理启动图标 |
| 旧连接重连 | 先预览，再经用户确认逐条关闭仍匹配的旧连接，由应用自行重连；不退出程序、不关闭其他程序连接 |
| 实际状态 | 分开显示保存目标、规则载入和已观察到的出口，提示连接尚未建立、入口外及旧线路连接 |
| 备份与撤回 | 切换前备份，失败尝试回滚；撤回时检查失效端口和外部更改，保留其他客户端的新选择 |
| 桌面与任务栏 | 使用「流向 FlowSwitch」入口、新图标和独立任务栏标识；已有配置目录继续兼容 |

固定入口和当前普通程序分流需要 Node.js 22+ 及受支持的分流引擎；普通 HTTP / 直连系统切换不要求 Node.js。管理器不强制拦截全机流量，也不自动开启 TUN、修改 DNS 或退出软件。本地端口通、规则载入与外部网站登录成功需要分别验证。

历史版本：[3.1.2 程序包](https://raw.githubusercontent.com/turnsolesama/portfolio/main/proxy-switch/releases/ProxySwitch-v3.1.2-Windows-x64.zip)、[3.1.2 源码](https://raw.githubusercontent.com/turnsolesama/portfolio/main/proxy-switch/releases/ProxySwitch-v3.1.2-Windows-Source.zip)、[3.1.1 源码](https://raw.githubusercontent.com/turnsolesama/portfolio/main/proxy-switch/releases/ProxySwitch-v3.1.1-Windows-Source.zip)、[3.1.0 源码](https://raw.githubusercontent.com/turnsolesama/portfolio/main/proxy-switch/releases/ProxySwitch-v3.1.0-Windows-Source.zip)、[3.0.3 源码](https://raw.githubusercontent.com/turnsolesama/portfolio/main/proxy-switch/releases/ProxySwitch-v3.0.3-Windows-Source.zip)、[3.0.2 源码](https://raw.githubusercontent.com/turnsolesama/portfolio/main/proxy-switch/releases/ProxySwitch-v3.0.2-Windows-Source.zip)、[3.0.1 源码](https://raw.githubusercontent.com/turnsolesama/portfolio/main/proxy-switch/releases/ProxySwitch-v3.0.1-Windows-Source.zip)、[3.0.0 源码](https://raw.githubusercontent.com/turnsolesama/portfolio/main/proxy-switch/releases/ProxySwitch-v3.0.0-Windows-Source.zip)。
