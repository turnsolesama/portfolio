# 流向 FlowSwitch 3.6.0 · 下载与校验

关闭窗口默认驻留右下角系统托盘，保持固定入口；内核异常退出有限恢复。使用托盘菜单「停止代理服务并退出」完全退出。

| 文件 | 大小 | SHA-256 |
| --- | --- | --- |
| [FlowSwitch-v3.6.0-Windows-x64.zip](https://raw.githubusercontent.com/turnsolesama/portfolio/main/proxy-switch/releases/FlowSwitch-v3.6.0-Windows-x64.zip) | 71,449,036 字节 | `bb9063753c3c48bbbc3cf6ef143409a825e603533d5d90ec0686c40ca3017886` |
| [FlowSwitch-v3.6.0-Windows-Source.zip](https://raw.githubusercontent.com/turnsolesama/portfolio/main/proxy-switch/releases/FlowSwitch-v3.6.0-Windows-Source.zip) | 1,763,660 字节 | `91e1d162dc4dd7c912a7983536526cb64cc9fbab1530491ae8b2c9f4b2d70055` |

Windows 包 35 个文件，源码包 72 个文件，均为单应用根目录；已核验 ZIP CRC、大小与 SHA-256。源码包 README 是随包说明，仓库 README 另有下载导航。

[使用与升级说明](../README.md) · [验收范围与另一台电脑复测步骤](../TEST_REPORT.md) · [更新记录](../CHANGELOG.md) · [SHA256SUMS.txt](SHA256SUMS.txt)

以下保留历史版本说明，其行为与运行要求仅适用于相应版本。

## 流向 FlowSwitch 3.5.1 · 下载与校验

普通使用下载 Windows x64 程序包，完整解压后双击 `FlowSwitch/FlowSwitch.exe`，保留 `app` 文件夹。自带 Node.js 和独立分流内核，无需另装 Clash；仍需自己的可用代理入口。

| 文件 | 大小 | SHA-256 |
| --- | --- | --- |
| [FlowSwitch-v3.5.1-Windows-x64.zip](https://raw.githubusercontent.com/turnsolesama/portfolio/main/proxy-switch/releases/FlowSwitch-v3.5.1-Windows-x64.zip) | 71,442,535 字节 | `f814cc1bddca70a138b1fe397e0c3e3fabe47047881e205d036f24cda6df664c` |
| [FlowSwitch-v3.5.1-Windows-Source.zip](https://raw.githubusercontent.com/turnsolesama/portfolio/main/proxy-switch/releases/FlowSwitch-v3.5.1-Windows-Source.zip) | 1,753,693 字节 | `499bd0213ad698512d138ba14cff454941e1a0e5ff9510e09f2991f46464bceb` |

[使用说明与运行要求](../README.md) · [更新记录](../CHANGELOG.md) · [SHA256SUMS.txt](SHA256SUMS.txt)

Windows 包含 35 个文件，源码包含 67 个文件，均为单应用根目录；已核验 ZIP CRC、大小与 SHA-256。包内无个人配置、代理规则、节点、账户或凭据。运行要求与验证范围见使用说明。

## 历史版本资料

以下为 3.3.2 及更早版本的原始说明，其运行条件和升级行为仅适用于对应历史版本。

### 流向 FlowSwitch 3.3.2 · 下载与校验

普通使用下载 **Windows x64 程序包**，完整解压后双击 `FlowSwitch/FlowSwitch.exe`。请保留 EXE 旁的 `app` 文件夹。源码包用于开发与重新构建。

| 下载 | 大小 | 文件数 |
| --- | --- | --- |
| [Windows x64 程序包](https://raw.githubusercontent.com/turnsolesama/portfolio/main/proxy-switch/releases/FlowSwitch-v3.3.2-Windows-x64.zip) | 362,929 字节 | 24 |
| [源码包](https://raw.githubusercontent.com/turnsolesama/portfolio/main/proxy-switch/releases/FlowSwitch-v3.3.2-Windows-Source.zip) | 1,708,158 字节 | 53 |

[使用说明](../README.md) · [运行要求](../README.md#运行要求) · [更新记录](../CHANGELOG.md) · [SHA256SUMS.txt](SHA256SUMS.txt)

3.3.2 包含深色侧边导航、灰蓝主题与细滚动条，修复拖动及缩放时下方原生横向白条闪现，并修复圆角卡片边缘残影。保留代理发现、固定入口模式、程序分流和确认后重连。原数据目录 `%USERPROFILE%\.proxyswitch` 保持兼容；升级不会自动切换代理。

运行要求：Windows 10 / 11 x64、Windows PowerShell 5.1、.NET Framework 4.8 和 curl.exe。可选引擎功能需要 Node.js 22+ 与已安装的受支持分流引擎。程序不捆绑 VPN 或代理节点。固定入口只管理已接入引擎的连接，不自动开启 TUN。

验证：207 项静态与基础断言、12 项 Windows 程序包检查及隔离切换交互检查通过。新增视觉回归先在旧版本复现原生横条，再在三种控件布局缩放下检查共 240 帧调整尺寸和滚动；覆盖滑块、滚轮、Home / End、日志滚动及内容未裁切。布局缩放模拟不修改系统 DPI。包检查覆盖中文与空格路径、真实 UI 启动、所选配置目录、桌面入口、任务栏标识与长命令边界。任务栏重开信息超过 Windows 支持长度时保留窗口图标，禁用该实例的固定操作，不截断路径。

包内使用显式文件清单与 SHA-256 校验，不含个人配置、代理规则、凭据、启动记录或实机截图；公开截图为演示数据。

```text
96528fa0764069311ca9d093d8a23a5f25cd93003ef0eb2e71276618bea6c2f8  FlowSwitch-v3.3.2-Windows-x64.zip
0229e2f6c1df30eb957a38f23b048a4aaf2bdb28fe351cd230da7e0b65d97475  FlowSwitch-v3.3.2-Windows-Source.zip
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

历史版本：[3.2.1 程序包](https://raw.githubusercontent.com/turnsolesama/portfolio/main/proxy-switch/releases/FlowSwitch-v3.2.1-Windows-x64.zip)、[3.2.1 源码](https://raw.githubusercontent.com/turnsolesama/portfolio/main/proxy-switch/releases/FlowSwitch-v3.2.1-Windows-Source.zip)、[3.1.2 程序包](https://raw.githubusercontent.com/turnsolesama/portfolio/main/proxy-switch/releases/ProxySwitch-v3.1.2-Windows-x64.zip)、[3.1.2 源码](https://raw.githubusercontent.com/turnsolesama/portfolio/main/proxy-switch/releases/ProxySwitch-v3.1.2-Windows-Source.zip)、[3.1.1 源码](https://raw.githubusercontent.com/turnsolesama/portfolio/main/proxy-switch/releases/ProxySwitch-v3.1.1-Windows-Source.zip)、[3.1.0 源码](https://raw.githubusercontent.com/turnsolesama/portfolio/main/proxy-switch/releases/ProxySwitch-v3.1.0-Windows-Source.zip)、[3.0.3 源码](https://raw.githubusercontent.com/turnsolesama/portfolio/main/proxy-switch/releases/ProxySwitch-v3.0.3-Windows-Source.zip)、[3.0.2 源码](https://raw.githubusercontent.com/turnsolesama/portfolio/main/proxy-switch/releases/ProxySwitch-v3.0.2-Windows-Source.zip)、[3.0.1 源码](https://raw.githubusercontent.com/turnsolesama/portfolio/main/proxy-switch/releases/ProxySwitch-v3.0.1-Windows-Source.zip)、[3.0.0 源码](https://raw.githubusercontent.com/turnsolesama/portfolio/main/proxy-switch/releases/ProxySwitch-v3.0.0-Windows-Source.zip)。

