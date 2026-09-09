# ProxySwitch · 网络代理管家

[返回三个软件的目录](../)

## 下载 ProxySwitch

**[直接下载 Windows x64 程序包 · v3.1.2 · 96,145 字节](https://raw.githubusercontent.com/turnsolesama/portfolio/main/proxy-switch/releases/ProxySwitch-v3.1.2-Windows-x64.zip)**

完整解压后打开 `ProxySwitch` 文件夹，双击 **`ProxySwitch.exe`**。无需编译或安装开发工具；请保留同目录的 `app` 文件夹。需要 Windows 10 / 11 x64、Windows PowerShell 5.1、.NET Framework 4.8 和 `curl.exe`。

[单独下载源码包](https://raw.githubusercontent.com/turnsolesama/portfolio/main/proxy-switch/releases/ProxySwitch-v3.1.2-Windows-Source.zip) · [下载与 SHA-256 校验](releases/README.md) · [完整运行要求](#运行要求)

一个通用的 Windows 代理管理面板：添加自己的代理入口，统一切换系统网络，或为程序指定单独线路。**不预设任何 VPN 品牌，也不捆绑代理服务。**

![代理管理页面，演示数据](assets/proxy-management.png)

## 快速开始

1. 普通使用请下载 [Windows x64 程序包](https://raw.githubusercontent.com/turnsolesama/portfolio/main/proxy-switch/releases/ProxySwitch-v3.1.2-Windows-x64.zip)，完整解压后双击 **`ProxySwitch.exe`**。源码开发另有 [源码包](https://raw.githubusercontent.com/turnsolesama/portfolio/main/proxy-switch/releases/ProxySwitch-v3.1.2-Windows-Source.zip)，源码目录使用 `启动代理切换.cmd`。
2. 等待后台代理自动加入列表；可在 **代理管理 → 检测并添加后台代理** 手动重扫，或用「添加代理」填写自定义地址。
3. 在顶部选择直连或已添加的代理，点击 **统一切换**。
4. 为 Electron / Chromium 程序指定线路时，工具会备份并接入桌面启动入口。保存任务并完整退出该程序后，从桌面入口打开，再观察包含子进程的实际连接。需要撤回时点击 **撤回上次更改**。

默认模板不包含任何 VPN 品牌。启动时读取已有配置并自动识别本机代理；升级保留原来的名称、端口、路径与稳定标识。自动发现只补充列表，不自动选择线路。界面每次刷新同步配置与实读状态。

Windows 程序包无需编译或安装开发工具。EXE 是编译后的 Windows 启动入口，`app` 文件夹包含运行模块；请完整保留该目录，不能只复制 EXE。双击「创建桌面快捷方式.cmd」可创建或更新指向 EXE 的桌面入口。运行仍使用 Windows 自带 PowerShell 5.1 和 .NET Framework；可选分流功能的依赖见下文。源码包保留构建脚本和测试，程序包只包含运行所需文件。

## 统一切换会做什么

- 同步当前用户 Windows 系统代理、HTTP_PROXY、HTTPS_PROXY、ALL_PROXY。
- 撤销本工具保存的程序专用线路，使受系统代理或分流引擎管理的新连接使用所选目标。
- 如果使用分流引擎，写入优先匹配的统一规则，不让原来的程序例外继续分流。
- 切换前备份系统入口、变量和程序规则；修改与线路检查失败会尝试恢复。写入后重新读取系统入口与变量，确认成功才更新当前线路。
- 保留用户的本地绕过列表。已有连接和已经继承的环境变量可能仍需重开程序。

切换时会显示「检查入口 → 更新规则 → 同步变量 → 写入并核对」的实际阶段。三个连通性检查并行进行，任一通过即继续，单个检查最长 5 秒；引擎重载、Windows 写入和连接刷新另外计时，这不是整个切换固定耗时的承诺。用户操作会让后台自动发现提前让路。「诊断与工具」仍保留完整逐站检测。

**统一切换影响遵循系统代理或已接入分流引擎的新连接；已接入启动适配的程序在下次从托管入口打开时读取统一目标。** 独立代理、VPN 隧道及忽略系统代理的软件不能靠系统代理设置强制接管，本工具不自动开启 TUN，也不结束应用。

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

自动发现与连接监控都保留。自动发现仅向身份已识别的代理内核（或用户填写的内核完整路径）发送握手，每次发送前复核进程和端口归属；不向游戏、启动器或无关应用的通信端口发送协议请求。已成功识别的入口缓存 10 分钟，失败结果缓存 30 秒；代理重启、新端口出现时重新识别，每轮最多检查两个新入口。

对于未知代理客户端，工具可从当前系统代理与用户代理变量中读取已有的本地入口，确认有监听后补充列表，不主动猜测协议。该入口的协议来自设置，是否能访问目标网站仍需检测。也可手动添加入口，再点击「检测并添加后台代理」。远程入口不定时连接。

底部「自动发现代理」开关控制后台识别；「自动刷新」控制定时状态读取。关闭自动发现仍保留程序连接监控和手动检测。启动、刷新、退出不写系统代理、环境变量或程序规则，不重新应用上次选择。自动发现只保存代理列表元数据，实际网络切换由你点击确认。

通过 HTTP CONNECT 或 SOCKS5 握手识别协议，避免把普通网页、控制接口和需要认证的端口直接当成可用入口。HTTP 探测尝试建立到 www.microsoft.com:443 的连接，SOCKS5 探测只协商本地协议；不携带账号或读取订阅。探测有时间与数量限制，较慢或未识别的入口可手动添加。协议识别不代表所有目标网站均可访问，可再使用「检测选中项」。

验证通过后自动补充到本机代理列表，保存前备份；已有代理的名称、稳定标识、引擎选择与程序规则保持原样。同一端口只保存一次，混合端口优先使用 HTTP。删除过的本地入口会加入忽略列表，重扫不会自动加回；需要恢复时可手动添加。手动检测只补充代理列表，不更改系统代理、环境变量或程序路由。

正在被当前入口或程序规则使用的代理不能直接删除；先统一切换到其他目标。改变地址、端口后，需要重新统一切换或重载程序规则。

## 程序启动代理

Antigravity 等软件的主界面与联网子进程可能使用不同的网络库。主界面能连接系统代理，不代表语言服务也使用它；只改 Windows 系统代理或反复普通重开可能无法修复这种分裂。

3.1 对具有 Chromium/Electron 运行资源的程序提供启动适配。右键选择 HTTP 代理或直连后，工具为界面配置 Chromium 启动参数，并为支持代理变量的子进程提供独立环境块。当前版本这一路径支持 HTTP 入口；未知程序或其他协议仍需对应的分流方式，不能靠保存一个目标强制接管所有网络库。

原桌面快捷方式没有额外启动参数时，工具保留其图标与工作目录，备份原文件，再接入统一启动入口。有自定义参数时保留原文件，创建“程序名（指定代理）”入口。每次打开都会读取最新的程序目标和代理端口，不把旧端口写死在快捷方式中。

**保存线路后，需要完整退出一次，再从接入的桌面图标打开。** 已运行时再次点击只会明确提示尚未应用，不会自动结束程序。管理器本身可以关闭，桌面入口仍可读取保存的目标并启动软件。通过其他未接入的入口启动时，界面会显示需重开/待验证。

“统一切换”会把已配置程序改为跟随当前系统入口。每个程序仍需在下一次启动时获得新环境；“撤回”恢复备份中的目标，移除启动适配时恢复原桌面入口，保留用户后来更改过的目标/参数。

依据：[Electron 代理启动参数](https://www.electronjs.org/docs/latest/api/command-line-switches#--proxy-serveraddressport)、[Node.js 子进程环境](https://nodejs.org/api/child_process.html#child_processspawncommand-args-options)、[Go HTTP 代理变量](https://pkg.go.dev/net/http#ProxyFromEnvironment)。

## 可选的程序分流引擎

| 功能 | 是否需要分流引擎 |
| --- | --- |
| 直连、普通 HTTP 系统统一切换 | 不需要 |
| 检测 HTTP / SOCKS5 入口 | 不需要 |
| Chromium/Electron 程序的 HTTP / 直连启动代理 | 不需要 |
| 其他程序的引擎规则分流 | 需要；流量必须实际进入引擎 |
| SOCKS5 系统统一切换 | 需要，由引擎提供本地 HTTP 入口 |

目前程序分流适配 **Clash Verge Rev / Mihomo**。在对应代理编辑窗口，填写其本地 HTTP / 混合端口和内核 EXE，勾选「用作程序分流引擎」，让引擎保持规则模式。它使用 Verge 现有的本地命名管道与全局脚本，不开放新的 HTTP 控制端口。

统一切换到普通 HTTP 代理时直接使用它自己的端口，不因另一个引擎正在运行而借用其入口。指定引擎自身或 SOCKS5 作为统一目标时才经由引擎。引擎规则分流经由引擎转发到对应入口；程序启动适配直接使用指定的 HTTP 入口。原始规则和脚本保留在配置中，可撤回恢复。

实现依据：[Mihomo 路由规则](https://wiki.metacubex.one/config/rules/)、[HTTP 出站](https://wiki.metacubex.one/config/proxies/http/)、[SOCKS5 出站](https://wiki.metacubex.one/config/proxies/socks/)、[Verge 全局脚本](https://www.clashverge.dev/guide/script.html)。

## 为程序指定线路

右键程序选择线路。支持启动适配的程序使用自己的代理参数与子进程环境；其余程序使用已配置的引擎规则。选择「跟随统一线路」会撤销该程序的专用目标。支持 EXE、指向 EXE 的快捷方式、文件拖放、名称和路径搜索。

![动态代理右键菜单，演示数据](assets/program-menu.png)

引擎规则按 EXE 完整路径生效；启动适配随启动环境传给子进程。列表会汇总同一程序目录内的父子进程，并显示子进程绕过本地入口的连接失败。一个软件可能有多个独立联网进程；升级导致路径改变时，应移除旧路径并重新添加。程序路径使用 Windows 的有限查询权限接口获取，不枚举目标模块或读取进程内存；读取被拒绝时仍按 PID 显示，不能直接从缺少路径的行设置路径规则。已配置代理的 `SynSent` 会显示具体端口和「连接尚未建立」，不会算作成功出口。没有证据确认出口的连接会显示「入口外连接」或「出口待确认」，不将它冒认为直连。

## 运行要求

- Windows 10 / 11，Windows PowerShell 5.1、.NET Framework 4.8、`curl.exe`。
- Chromium/Electron 的 HTTP / 直连启动适配，以及 HTTP 系统代理与直连，不要求 Node.js。引擎规则分流与 SOCKS5 统一切换需要 Node.js 22+ 和受支持的分流引擎。
- 已在 Windows PowerShell 5.1、Node.js 24.18.0、Mihomo 1.19.29 上验证。

软件不自动下载依赖。桌面快捷方式可通过以下命令创建：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Install-Shortcut.ps1
```

## 本机数据与更新

3.1.1 起，本机数据默认位于 `%USERPROFILE%\.proxyswitch`，与发布源码分开保存。管理器、桌面启动入口和后台工作进程使用同一个目录，避免 MSIX 应用启动的进程与普通桌面进程看到不同的 AppData 文件。依据：[Windows 打包桌面应用的文件重定向](https://learn.microsoft.com/en-us/windows/msix/desktop/desktop-to-uwp-behind-the-scenes)。

首次使用新版默认目录时，会复制当前启动环境可见的 `%LOCALAPPDATA%\ProxySwitch` 数据及备份，保留原文件。复制完整后才启用新目录；已有新目录不会被旧配置覆盖。这个迁移只处理本机文件，不应用历史网络选择。若旧版已经产生两套配置，需要先核对并合并差异；自动迁移不会自行搜索或合并其他应用的私有目录。

完成迁移后，旧快捷方式中指向原默认 AppData 目录的 `-DataDirectory` 参数会按迁移记录转到共享目录。自行指定的其他目录和 `PROXY_SWITCH_DATA_DIR` 仍按原设置使用；测试继续使用独立目录。

| 文件 | 用途 |
| --- | --- |
| `config.json` | Version 3 的 Profiles、可选 Routing 引擎及 DiscoveryIgnored 本机端口忽略列表 |
| `selection.json` | 已应用的系统入口和目标线路 |
| `app-rules.json` | 分流引擎规则与统一默认路由 |
| `program-proxies.json` | 程序启动代理目标 |
| `program-shortcuts.json` / `program-launches.json` | 本机入口备份索引与启动会话核对 |
| `last-program-launch.json` | 最近一次启动结果、程序路径和实际配置目录，仅存本机 |
| `storage-layout.json` | 迁移来源与旧默认路径兼容记录 |
| `backups/` | 修改前系统、变量、规则和代理列表备份 |

含原 Clash 节点信息的配置备份留在 Clash 用户目录的 `proxy-switch-backups` 内，不进入发布包。更新时关闭本工具并替换程序文件，本机数据保持独立。

2.2 的固定代理设置可自动读入通用模型，保存代理管理设置后使用 Version 3 格式。2.1 及更早的目录内数据应先备份，再复制到上述本机目录，不覆盖已有新版设置。

移除工具前可以先统一切换到直连以撤回当前托管的路由设置，再关闭工具。删除程序文件本身不会修改网络或清理本机备份。已接入的程序桌面入口依赖工具文件；卸载前先撤回其启动代理适配并恢复原快捷方式。

## 诊断与恢复

「诊断与工具」提供所选代理的 HTTPS 探测、规则重载、匿名报告导出，以及打开该入口关联的代理程序。程序不再包含任何特定应用的启动按钮。

检测不携带账户凭据。HTTP 401 只说明接口可达但未认证；网页 403 可能要求验证或拒绝请求，不证明登录后可用。报告只含匿名线路标识、就绪状态、端口和数量，不包含代理名称、地址、账号、订阅、目标网站、程序名称或路径。

撤回前会检查备份中的系统入口和本地代理变量端口；端口未监听时不恢复任何设置。失败回滚仅恢复仍属于本次操作的值，保留其他客户端的新选择。界面的当前入口来自实读，历史选择不代表当前生效线路。

已运行程序保留启动时继承的环境变量；更改注册表中的用户代理变量不会直接改写其内存。若连接记录持续显示旧代理，可在保存任务后手动重开程序及其启动器；这是一种排查方法，不能仅凭旧端口就认定登录故障由缓存造成。不自动重启游戏、启动器、浏览器或代理客户端。依据：[Windows 进程环境变量](https://learn.microsoft.com/en-us/windows/win32/procthread/environment-variables)。

## 开发与验证

`Build-WindowsPackage.ps1` 使用本机 .NET Framework 的 C# 编译器生成 x64 WinExe，不下载编译依赖。只有构建者需要编译器，下载程序包的用户无需自行构建。启动器直接创建隐藏的 PowerShell 子进程，不经过 cmd 命令拼接。依据：[Microsoft 编译输出选项](https://learn.microsoft.com/en-us/dotnet/csharp/language-reference/compiler-options/output)、[ProcessStartInfo.UseShellExecute](https://learn.microsoft.com/en-us/dotnet/api/system.diagnostics.processstartinfo.useshellexecute)。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Test-All.ps1
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File .\ProxySwitch.ps1 -SmokeTest
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File .\Test-PassiveLifecycle.ps1
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File .\Test-DiscoveryUI.ps1
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File .\Test-AutomaticDiscoveryUI.ps1
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File .\Test-SwitchInteraction.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Test-ProgramLaunch.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Test-Storage.ps1
# 构建与测试可直接运行的 Windows 程序包
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Build-WindowsPackage.ps1 -Destination C:\Temp\ProxySwitch-Windows
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Test-WindowsPackage.ps1 -PackageDirectory C:\Temp\ProxySwitch-Windows\ProxySwitch
```

188 项断言覆盖代理模型、迁移、路由、事务回滚、并发改写保护、匿名报告、协议识别、自动发现缓存与有限进程查询。四种隔离界面回归覆盖自动发现、新端口识别、游戏行保留、连续 72 秒观察、外部选择、用户切换优先、阶段进度和设置实读。测试使用独立数据与模拟 Windows 写入，不切换用户正在使用的网络。临时父子程序真实验证启动环境继承、旧代理变量隔离、程序已运行时拒绝重复启动、快捷方式备份恢复及子进程绕过状态。13 项存储断言覆盖默认共享目录、显式目录优先级、迁移数据与原文件保留、快捷方式备份重定位、旧参数兼容及复制失败不发布半成品。

在一次现场只读预检中，当前可用 HTTP 代理 1.78 秒通过；无响应入口的并行检查 4.39 秒返回失败。这是预检耗时，不能当作完整切换时间，也不能保证其他网络同样快。

3.0.2 关闭自动发现后，现场仍出现游戏登录失败，随后也观察到管理器保持运行时一次登录成功。3.0.3 的改动修复已确认的实现问题，尚不能据此宣布游戏错误 [4] 的具体原因已找到。真实登录与长期稳定性需独立观察，单元测试不能代替。

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

Windows 程序包另做独立验收：文件哈希、移动到含中文/空格的路径、EXE 打开真实界面并正常退出、显式配置目录、文件缺失时报错，以及临时桌面快捷方式的目标和工作目录。验收只操作临时副本，不切换真实网络。

YAML 解析器的 CommonJS 构建已包含，无需 `npm install`。原创代码使用 [MIT](LICENSE)，第三方组件见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
