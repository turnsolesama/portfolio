# portfolio
My personal website and AI portfolio.

## AI Hub · 本地 AI 资产管理

按图片、视频、语言、音频等功能管理模型，支持 LoRA 多用途分类、批量整理、图库和独立 Windows 桌面窗口。2.3 新增跨电脑安全区设置、自动分类入口、可选启动整理和批次撤销。

- [项目源码与使用说明](ai-hub/README.md)
- [下载 Windows x64 桌面包 · v2.3.0](ai-hub/releases/AI-Hub-v2.3.0-Windows-x64.zip?raw=true)
- [完整源码包](ai-hub/releases/AI-Hub-v2.3.0-Source.zip?raw=true)
- [版本说明与校验清单](ai-hub/releases/README.md)

运行需本机 Python 3.9+、.NET Framework 4.8+ 和 WebView2 Runtime。发行包不包含个人数据库、图片、配置、凭据或模型权重。

## Codex Switcher · 服务配置工作台

紧凑双栏界面、可调分栏、固定操作区，以及文件/粘贴导入、去重预览、服务搜索、配置备份恢复。v2.1 修复高缩放与小窗口下的按钮裁切，并保留可修复的旧版服务记录。

- [项目源码与使用说明](codex-switcher/README.md)
- [下载 Windows x64 程序包 · v2.1.1](codex-switcher/releases/Codex-Switcher-v2.1.1-Windows-x64.zip?raw=true)
- [测试记录](codex-switcher/TEST_REPORT.md) · [文件校验清单](codex-switcher/releases/manifest.json)

解压整个目录后双击 EXE。需要 Python 3.11+（含 Tkinter）与 .NET Framework 4.x；EXE 不内置 Python。发布包不包含个人服务列表、密钥、登录信息或备份。

## ProxySwitch · 网络代理管家

添加自定义 HTTP / SOCKS5 代理入口，统一切换系统代理，支持可选引擎下的程序分流与实际连接检查。3.0 移除固定 VPN 品牌选项，新增代理管理和统一切换。

- [源码、运行要求与使用说明](proxy-switch/README.md)
- [下载 Windows 源码运行包 · v3.0.0](proxy-switch/releases/ProxySwitch-v3.0.0-Windows-Source.zip?raw=true)
- [版本记录](proxy-switch/CHANGELOG.md)
- [下载与校验说明](proxy-switch/releases/README.md)

解压完整目录后双击「启动代理切换.cmd」。基础 HTTP / 直连切换无需 Node.js；程序分流与 SOCKS5 统一切换需要可选引擎。软件不捆绑 VPN 或代理服务。
