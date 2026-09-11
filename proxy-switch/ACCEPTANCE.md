# FlowSwitch 3.7.1 功能与验收约定

本次重点是程序身份、连接证据、规则维护与入口生命周期的一致性。保留现有代理选择和用户数据；不把一次探测成功写成全功能验收通过。

| 功能 | 必须保持的行为 | 验证入口 |
| --- | --- | --- |
| 自定义 HTTP / SOCKS5 | 任意已登记入口；发现不抢回系统代理，基础 HTTP 不依赖引擎 | Test-ProxySwitch、Preferences、ProxyDiscovery、AutomaticDiscovery |
| 统一切换与撤回 | 系统代理、用户环境和专用规则一起处理；持久化备份，失败回滚，保留外部后续修改 | Test-ProxySwitch、Compatibility、GatewayControl、SwitchInteraction |
| 按程序分流 | 仅处理进入入口的连接；不自动 TUN、不关闭用户程序；旧启动代理继续兼容 | Test-ProgramLaunch、AppRouter、GatewayIntegration、IndependentIntegration |
| 程序身份 | 精确路径和真实文件别名；商店应用同包同相对 EXE 的唯一升级候选；路径不可读与歧义分别报告 | Test-ProgramIdentity |
| 旧规则维护 | 自动关联只用于显示；用户核对后修复记录；保留线路和自有快捷方式备份；外部修改与过期计划拒绝覆盖 | Test-RuleMaintenance、ObservationUI |
| 连接观察 | 区分未运行、路径失效、空闲、正在建立、已观察到、读取失败；规则载入与实际线路分开 | Test-ApplicationObservation、StatusSnapshot、Compatibility、ObservationUI |
| 自动接替 | 保留有效备用；全失败暂停，直连需明确允许；检测工具失败为未知 | Test-IndependentRouter、IndependentIntegration、FailoverDisplay |
| 托盘与独立入口 | X 隐藏且入口持续；明确停止后先恢复设置再停止自有内核；同一配置单窗口 | Test-TrayLifecycle、WindowInstance |
| 有限恢复 | 五分钟三次、1/2/4 秒退避与就绪校验；重启与停止竞争不误用旧 PID；看门狗不恢复新会话 | Test-Lifecycle、SupervisorRecovery、ExitRecovery、Watchdog |
| 私密数据与诊断 | 不读令牌或进程内存；日志固定事件码且限额；报告匿名汇总，不含程序路径与凭据 | Test-Preferences、LifecycleProtection |
| 安装与升级 | 新目录构建、自带锁定组件；保留旧包和 .proxyswitch；打包文件及移动后启动检查 | Test-WindowsPackage、RuntimeBundle |

## “未观察到连接”的含义

当前界面主要观察 Windows TCP Established / SynSent 与引擎连接快照。程序空闲、短时请求已结束、UDP / QUIC、独立隧道，以及无权限取得路径时都有可见范围限制。未观察到不等于断网；SynSent 不等于永久故障；TCP 或 HTTPS 成功不等于登录成功。

程序可能有独立联网子进程。父进程的一条成功连接不能证明子进程都在目标线路；独立 EXE 的引擎规则仍按路径匹配。软件升级时，原路径规则不能直接被声称已对新路径生效。

## 另一台电脑的真实验收

1. 保留旧版和本机数据，停止旧 FlowSwitch 后运行新包；配置该电脑自己的上游。
2. 开启独立模式并等待入口就绪，验证日常应用；X 收至托盘后继续发送请求，再从托盘恢复界面。
3. 完整重开目标应用及需要的启动器；执行真实 Google 登录，由使用者确认账号进入应用。无凭据诊断不能代替此步。
4. 确认已升级应用对应一条当前记录；若提示待修复，核对旧、新路径再执行修复，观察新连接。保留旧连接的程序可先预览重连。
5. 停止服务后确认设置按归属恢复；如果应用仍报旧入口，保存工作后完整重开，不自动结束程序。

杀内核、占用端口及故障注入仅在测试脚本的隔离环境进行。生产电脑的登录和长时间运行验收结果应单独记录，不能用测试断言数量替代。

3.7.1 补充：损坏锁恢复须核对活跃文件句柄与进程身份；Test-GatewayLock 覆盖真实并发，Test-Lifecycle 覆盖空锁下自动接替和重开。
