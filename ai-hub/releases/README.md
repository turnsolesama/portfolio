# AI Hub 2.4.0

视觉更新：紧凑导航、常用创作入口、用途分类和统计区，以及炭灰 / 冰蓝配色。保留模型介绍、图库删除与返回、安全区整理等现有行为。

- [Windows x64 桌面包](https://raw.githubusercontent.com/turnsolesama/portfolio/main/ai-hub/releases/AI-Hub-v2.4.0-Windows-x64.zip) — 457352 字节
- [完整源码包](https://raw.githubusercontent.com/turnsolesama/portfolio/main/ai-hub/releases/AI-Hub-v2.4.0-Source.zip) — 191748 字节
- [SHA-256 校验清单](AI-Hub-v2.4.0-SHA256.txt)
- [设计与验证记录](../docs/VISUAL_2.4.md)

本次仅更新前端，沿用已验证的桌面 EXE 与 2.3 后台协议。完整解压后双击 AI Hub.exe，需要本机 Python 3.9+、.NET Framework 4.8+ 与 WebView2 Runtime；升级保留整个 data/。已打开的页面需刷新或重新打开窗口。

验证：运行 120 项 Python 测试，其中 5 项按环境条件跳过；33 项前端测试及脚本语法检查通过。发行包通过白名单、摘要和 ZIP CRC 检查。浏览器自动化连接失败，尚未完成实际截图和逐尺寸视觉验收。

## 历史版本

### AI Hub 2.3.0

新增跨电脑安全区设置、可创建标准目录、分类预览、硬链接分类入口、批次记录与撤销、可选后台启动时自动整理。原件留在原处，既有工作流路径保留。硬链接共用文件内容，不是备份。

- [Windows x64 桌面包](https://raw.githubusercontent.com/turnsolesama/portfolio/main/ai-hub/releases/AI-Hub-v2.3.0-Windows-x64.zip) — 451683 字节
- [完整源码包](https://raw.githubusercontent.com/turnsolesama/portfolio/main/ai-hub/releases/AI-Hub-v2.3.0-Source.zip) — 186081 字节
- [SHA-256 校验清单](AI-Hub-v2.3.0-SHA256.txt)
- [安全区与自动整理说明](../docs/SAFE_ZONE.md)
- [验证记录](../docs/VALIDATION_2.3.md)

解压完整目录后双击 AI Hub.exe，保留本机 Python 3.9+、.NET Framework 4.8+ 与 WebView2 Runtime。全新安装先设置安全区，升级保留整个 data/。程序不预设作者的盘符，不包含用户配置、数据库、模型或图片。

验证：115 项 Python 测试通过，5 项因符号链接权限跳过；实际 NTFS 联接检查通过。33 项前端测试及3份脚本语法检查通过，浏览器预览/执行/撤销与干净解压启动通过。桌面外壳沿用已验证版本。

2.3.0 历史包保留在本目录；使用新版请下载页首的 2.4.0 文件。
