# ProxySwitch · 网络代理管家

一个通用的 Windows 代理管理面板：添加自己的代理入口，统一切换系统网络，或为程序指定单独线路。**不预设任何 VPN 品牌，也不捆绑代理服务。**

![代理管理页面，演示数据](assets/proxy-management.png)

## 快速开始

1. 解压完整文件夹，双击 `启动代理切换.cmd`。
2. 等待后台代理自动检测，已验证的本机入口会加入列表。也可打开 **代理管理 → 重新检测后台代理**；远程入口仍可用「添加代理」填写。
3. 在顶部选择直连或已添加的代理，点击 **统一切换**。
4. 刷新网页或重开目标程序，再查看实际连接。需要撤回时点击 **撤回上次更改**。

默认模板不包含任何 VPN 品牌。启动后从这台电脑的实际监听端口识别代理；升级保留原来的名称、端口、路径与稳定标识。界面每次刷新都会同步配置文件，避免下拉框与后台状态不一致。

## 统一切换会做什么

- 同步当前用户 Windows 系统代理、HTTP_PROXY、HTTPS_PROXY、ALL_PROXY。
- 撤销已保存的程序专用线路，将新连接统一到所选目标。
- 如果使用分流引擎，写入优先匹配的统一规则，不让原来的程序例外继续分流。
- 切换前备份系统入口、变量和程序规则；修改与实际线路检查失败会尝试恢复。
- 保留用户的本地绕过列表。已有连接和已经继承的环境变量可能仍需重开程序。

**统一切换影响遵循系统代理或已接入分流引擎的新连接。** 独立代理、VPN 隧道及忽略系统代理的软件不能靠系统代理设置强制接管，本工具不自动开启 TUN，也不结束应用。

![程序分流与统一切换，演示数据](assets/screenshot.png)

## 代理管理

每个入口具有独立标识，名称可以自由修改；改名不会丢失程序规则。

| 字段 | 内容 |
| --- | --- |
| 名称 | 方便识别的名称，如办公网络、备用线路 |
| 协议 | HTTP 或 SOCKS5 |
| 地址 | IPv4、IPv6 或域名；不含协议前缀、账号或路径 |
| 端口 | 1–65535 |
| 关联程序 | 可选的客户端 EXE，便于从工具打开 |
| 分流内核 | 启用程序分流引擎时填写 |

当前版本不保存代理账号密码。VPN 客户端需要提供 HTTP / SOCKS5 端口才能作为入口添加；仅提供系统隧道的 VPN 仍需在其客户端管理。

启动后自动检测本机监听端口；「自动刷新」开启时每分钟重扫，也可手动重新检测。已知代理客户端优先，同时尝试识别其他用户程序的本地端口，不要求进程名称必须在固定名单中。读取进程路径失败时仍可检测。

通过 HTTP CONNECT 或 SOCKS5 握手识别协议，避免把普通网页、控制接口和需要认证的端口直接当成可用入口。HTTP 探测尝试建立到 www.microsoft.com:443 的连接，SOCKS5 探测只协商本地协议；不携带账号或读取订阅。探测有时间与数量限制，较慢或未识别的入口可手动添加。协议识别不代表所有目标网站均可访问，可再使用「检测选中项」。

验证通过后自动补充到本机代理列表，保存前备份；已有代理的名称、稳定标识、引擎选择与程序规则保持原样。同一端口只保存一次，混合端口优先使用 HTTP。删除过的本地入口会加入忽略列表，重扫不会自动加回；需要恢复时可手动添加。自动发现只补充代理列表，不更改系统代理、环境变量或程序路由。

正在被当前入口或程序规则使用的代理不能直接删除；先统一切换到其他目标。改变地址、端口后，需要重新统一切换或重载程序规则。

## 可选的程序分流引擎

| 功能 | 是否需要分流引擎 |
| --- | --- |
| 直连、普通 HTTP 系统统一切换 | 不需要 |
| 检测 HTTP / SOCKS5 入口 | 不需要 |
| 按程序选择不同线路 | 需要 |
| SOCKS5 系统统一切换 | 需要，由引擎提供本地 HTTP 入口 |

目前程序分流适配 **Clash Verge Rev / Mihomo**。在对应代理编辑窗口，填写其本地 HTTP / 混合端口和内核 EXE，勾选「用作程序分流引擎」，让引擎保持规则模式。它使用 Verge 现有的本地命名管道与全局脚本，不开放新的 HTTP 控制端口。

指定引擎自身作为目标时，使用原主节点组；指定其他代理时，转发到配置的 HTTP 或 SOCKS5 入口；指定直连时退出代理。原始规则和脚本保留在配置中，可撤回恢复。

实现依据：[Mihomo 路由规则](https://wiki.metacubex.one/config/rules/)、[HTTP 出站](https://wiki.metacubex.one/config/proxies/http/)、[SOCKS5 出站](https://wiki.metacubex.one/config/proxies/socks/)、[Verge 全局脚本](https://www.clashverge.dev/guide/script.html)。

## 为程序指定线路

右键程序，选择直连或任意已添加的代理。选择「跟随统一线路」会删除该程序的专用规则。支持 EXE、指向 EXE 的快捷方式、文件拖放、名称和路径搜索。

![动态代理右键菜单，演示数据](assets/program-menu.png)

规则按 EXE 完整路径生效。一个软件可能有多个独立联网进程；升级导致路径改变时，应移除旧路径并重新添加。没有证据确认出口的连接会显示「入口外连接」或「出口待确认」，不将它冒认为直连。

## 运行要求

- Windows 10 / 11，Windows PowerShell 5.1、.NET Framework 4.8、`curl.exe`。
- 按程序分流需要 Node.js 22+ 和受支持的分流引擎；单独使用 HTTP 系统代理与直连不要求 Node.js。
- 已在 Windows PowerShell 5.1、Node.js 24.18.0、Mihomo 1.19.29 上验证。

软件不自动下载依赖。桌面快捷方式可通过以下命令创建：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Install-Shortcut.ps1
```

## 本机数据与更新

本机数据位于 `%LOCALAPPDATA%\ProxySwitch`，与发布源码分开保存：

| 文件 | 用途 |
| --- | --- |
| `config.json` | Version 3 的 Profiles、可选 Routing 引擎及 DiscoveryIgnored 本机端口忽略列表 |
| `selection.json` | 已应用的系统入口和目标线路 |
| `app-rules.json` | 程序专用规则与统一默认路由 |
| `backups/` | 修改前系统、变量、规则和代理列表备份 |

含原 Clash 节点信息的配置备份留在 Clash 用户目录的 `proxy-switch-backups` 内，不进入发布包。更新时关闭本工具并替换程序文件，本机数据保持独立。

2.2 的固定代理设置可自动读入通用模型，保存代理管理设置后使用 Version 3 格式。2.1 及更早的目录内数据应先备份，再复制到上述本机目录，不覆盖已有新版设置。

移除工具前可以先统一切换到直连以撤回当前托管的路由设置，再关闭工具。删除程序文件本身不会修改网络或清理本机备份。

## 诊断与恢复

「诊断与工具」提供所选代理的 HTTPS 探测、规则重载、匿名报告导出，以及打开该入口关联的代理程序。程序不再包含任何特定应用的启动按钮。

检测不携带账户凭据。HTTP 401 只说明接口可达但未认证；网页 403 可能要求验证或拒绝请求，不证明登录后可用。报告只含匿名线路标识、就绪状态、端口和数量，不包含代理名称、地址、账号、订阅、目标网站、程序名称或路径。

## 开发与验证

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Test-All.ps1
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File .\ProxySwitch.ps1 -SmokeTest
```

117 项单元断言覆盖通用代理模型、旧配置迁移、规则优先级、统一切换、失败整体回滚、并发改写保护、Unicode 快捷方式和匿名报告。新增发现测试覆盖真实回环 HTTP / SOCKS5 应答、分片、超时、控制端口排除、去重、忽略列表与隔离保存。界面检查读取实际状态、搜索和筛选，不修改网络；另在隔离设置中验证自动发现、下拉框更新、外部配置刷新、删除与重扫。

发布前还使用隔离的 Mihomo 实例验证了 4 种程序线路和 4 种统一线路的实际规则命中与 HTTPS 连接；测试实例恢复原配置，用户实例没有被改动。

```powershell
# 查看状态
.\ProxySwitch.ps1 -Status
.\ProxySwitch.ps1 -AppStatus
# 检测并补充本机代理列表（不切换网络）
.\ProxySwitch.ps1 -Discover
# 指定已存在的代理标识，或 Direct，执行统一切换
.\ProxySwitch.ps1 -Switch <代理标识>
# 生成公开演示图
.\ProxySwitch.ps1 -Demo -PreviewView Proxies -PreviewPath C:\Temp\proxies.png
# 按显式清单创建发布包，目标目录须尚未存在
.\Build-Release.ps1 -Destination C:\Temp\ProxySwitch-release
```

测试可用 `PROXY_SWITCH_DATA_DIR` 隔离本机数据。路由集成测试同时设置 `PROXY_SWITCH_TEST_ENGINE_DIR` 与以 `\\.\pipe\ProxySwitch-Test-` 开头的 `PROXY_SWITCH_TEST_PIPE`，以测试专用实例替代用户实例。

YAML 解析器的 CommonJS 构建已包含，无需 `npm install`。原创代码使用 [MIT](LICENSE)，第三方组件见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
