# 网络代理切换器

- Windows PowerShell 5.1 / WinForms。程序分流使用已安装的 Node.js 与本目录 vendor/js-yaml 5.4.1（保留 MIT 许可证）。不自动更新依赖。
- `ProxySwitch.ps1` 是唯一入口；`ProxyBackend.ps1` 提供状态、诊断、事务切换和恢复。
- `Preferences.ps1` 提供本机设置、快捷方式解析、汇总诊断；数据统一保存到 `%LOCALAPPDATA%\ProxySwitch`，代码目录仅保留 `config.defaults.json` 默认模板。测试可用 `PROXY_SWITCH_DATA_DIR` 指定隔离目录。
- `Build-Release.ps1 -Destination <新目录>` 通过显式文件清单打包；不得把本机 config.json、selection.json、app-rules.json、备份或实机截图加入清单。
- `assets` 中的截图使用 `-Demo` 演示数据生成；不要用用户真实进程列表作为公开截图。
- PowerShell 中文源文件保存为 UTF-8 BOM，兼容 Windows PowerShell 5.1。
- 全局切换管理当前用户 WinINet 系统代理及 HTTP_PROXY、HTTPS_PROXY、ALL_PROXY；NO_PROXY 仅追加本地绕过，直连时保留。
- 用户要求的程序分流使用 Clash PROCESS-PATH 规则；仅管理 PSW-App-* 命名的代理和规则及带标记的全局脚本扩展，保留其他设置。
- 修改 Clash 前验证候选配置、备份，并通过已有本地命名管道重载和核对规则；失败回滚。含节点凭据的备份只存在 Clash 用户配置目录中，不写入 outputs。
- 不输出 API 密钥、订阅地址、节点凭据或账户认证；不改账号切换器、DNS、路由、WinHTTP。不自动开启 TUN 或网络控制端口。
- 不自动结束 Codex、浏览器或其他客户端进程；显示当前连接和重启提示。
- 不后台抢回代理。切换带跨进程互斥、持久化备份、失败回滚、实读校验。
- 验证：`powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Test-ProxySwitch.ps1`（内存模拟写入，不改真实网络）。
- 只读实机检查：`powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\ProxySwitch.ps1 -Status` 和 `-Check <代理标识>`。
- 界面预览：`powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File .\ProxySwitch.ps1 -PreviewPath <绝对PNG路径>`。
- 分流单元测试：`node .\Test-AppRouter.cjs`。实机分流只使用工作目录中专门编译的校验程序，完成后移除测试规则。
- 完整静态与单元验证：`powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Test-All.ps1`。界面检查：`powershell.exe -NoProfile -STA -File .\ProxySwitch.ps1 -SmokeTest`。
- Windows PowerShell 5.1 调用 .NET 需要空字符串指针时使用 `[NullString]::Value`；不要将 `$null` 传入 `File.Replace` 的 backupFileName 参数。

- 3.0 的代理模型是 Version=3 / Profiles[] / Routing；全新默认 Profiles 为空，品牌名称只允许出现在旧配置迁移、候选端口识别或特定引擎适配中，不能作为固定 UI 选项。
- 「统一切换」必须一起处理系统代理、用户变量和程序例外，保存可恢复快照。启用引擎时使用托管默认 MATCH 规则；不要将“只改系统入口”声称为统一出口。
- 原生设置尚未开始写入时，失败不能覆盖其他程序的并发系统设置更改。应用路由后需验证实际线路。
- HTTP 与直连的基础统一切换不依赖 Node.js 或任何 VPN 品牌；SOCKS5 统一切换和按程序分流需要可选引擎。
- 独立集成测试可设置 PROXY_SWITCH_TEST_ENGINE_DIR 和 PROXY_SWITCH_TEST_PIPE；后者必须以 \\.\pipe\ProxySwitch-Test- 开头。使用专门的回环端口、独立状态目录和测试进程，退出时结束自己启动的引擎，不修改用户实例。

- 3.0.3 保留启动与定时自动发现，提供独立的自动发现开关。启动、刷新、退出不写系统代理、环境变量或程序规则，不重新应用历史选择。自动发现可以补充本机代理列表；主动握手仅针对已识别的代理内核或用户配置的内核完整路径，发送前复核 PID、启动时间、路径与监听归属。不扫描游戏或无关程序端口。未知客户端可以从当前系统代理/用户代理变量被动识别，或由用户明确添加入口后手动检测。
- 保留用户已有标识、名称、Routing 和 DiscoveryIgnored。探测后须在互斥锁内重新读取配置，去重后再保存；删除本地入口时记入忽略列表。
- 后台状态响应需携带同一配置目录的 Settings，UI 同步下拉框与列表；SmokeTest 不运行自动发现，断言配置数量与列表数量一致。
- 新增验证：powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Test-ProxyDiscovery.ps1（真实回环应答与隔离配置，不写真实网络）。

- HTTP 统一选择直接使用所选入口；只有引擎自身或 SOCKS5 需要托管默认 MATCH。回滚前检查设置仍属于本次操作，保留外部更改。撤回必须检查本地代理环境变量端口。
- `Test-Compatibility.ps1` 验证被动状态、游戏端口排除、并发回滚、失效备份和 SynSent；不得读取游戏进程内存或自动重启游戏来测试。
- 界面回归：`Test-PassiveLifecycle.ps1`（关闭自动发现后的 72 秒观察模式）、`Test-DiscoveryUI.ps1`（手动发现、外部配置刷新、删除与重扫）、`Test-AutomaticDiscoveryUI.ps1`（自动发现、缓存、新端口与程序监控）和 `Test-SwitchInteraction.ps1`（用户切换优先、进度与设置实读）。均使用隔离配置和模拟 Windows 写入。
- 进程路径通过 `ProcessInventory.ps1` 的 QueryFullProcessImageNameW 和 PROCESS_QUERY_LIMITED_INFORMATION 获取。不得回退到 Windows PowerShell 5.1 的 Get-Process.Path / MainModule；它们可能请求 VM_READ 并枚举目标模块。拒绝访问时仅显示可取得的 PID/名称，不提权。
- 切换使用 Test-ProxyRoute -Fast，并行预检、任一可用即继续；完整逐站诊断保留独立入口。后台发现须响应用户操作的取消请求，不能强行中断网络事务或回滚。
- 单元/隔离验证不能代替真实游戏登录，不能把偶发成功或有限查询接口变更表述为已确认游戏错误的根因。
