# AI Hub 2.5.0

新增项目、运行与知识登记；模型分类分为所属范围、角色、用途和架构，人工标签在有效兼容入口间保持一致。工作流和运行按证据区分待验证、路径检查、历史通过与当前通过。已有模型库只提供统一整理预览，避免再生成一套实体入口。

应用、前端与发行包为 2.5.0；桌面外壳沿用 2.4.1，图标及桌面行为保持原有版本。

- [Windows x64 桌面包](https://raw.githubusercontent.com/turnsolesama/portfolio/main/ai-hub/releases/AI-Hub-v2.5.0-Windows-x64.zip) — 1086784 字节
- [完整源码包](https://raw.githubusercontent.com/turnsolesama/portfolio/main/ai-hub/releases/AI-Hub-v2.5.0-Source.zip) — 569690 字节
- [SHA-256 校验清单](AI-Hub-v2.5.0-SHA256.txt)
- [结构升级与回退说明](../docs/STRUCTURE_2.5.md)
- [项目及证据登记格式](../docs/REGISTRY.md)

验证：从发行源码包独立运行 169 项 Python 测试，其中 5 项因符号链接权限跳过；39 项 JavaScript 测试及 4 份脚本语法检查通过。补充验证了旧表/WAL 迁移、兼容入口被独立文件替换、纳秒时间戳跨前后端往返、登记回退及本地 HTTP 流程。两个包通过文件白名单、内外 SHA-256、ZIP CRC 和源码一致性检查。浏览器自动化连接不可用，页面目验尚未完成。

升级前等待后台空闲，保留整个 data/ 并使用 SQLite backup API 备份；具体步骤见结构升级说明。此次发布仅同步软件源码和发行包，不自动升级现有本机安装。

## 历史版本

### AI Hub 2.4.1

新增统一的叠层图标，覆盖桌面 EXE、窗口与网页入口。桌面外壳版本为 2.4.1，后台协议保持 2.3；资产与个人配置保留。

- [Windows x64 桌面包](https://raw.githubusercontent.com/turnsolesama/portfolio/main/ai-hub/releases/AI-Hub-v2.4.1-Windows-x64.zip) — 1031438 字节
- [完整源码包](https://raw.githubusercontent.com/turnsolesama/portfolio/main/ai-hub/releases/AI-Hub-v2.4.1-Source.zip) — 514341 字节
- [SHA-256 校验清单](AI-Hub-v2.4.1-SHA256.txt)
- [图标与验证说明](../docs/BRAND_2.4.1.md)

验证：桌面构建 30 项检查、打包 3 项检查通过；PNG、ICO 七种尺寸及 EXE 图标资源透明度检查通过。没有把自动检查等同于全部窗口的实际视觉验收。升级保留整个 data/，关闭旧桌面窗口后替换程序，再重新打开。


### AI Hub 2.4.0

视觉更新：紧凑导航、常用创作入口、用途分类和统计区，以及炭灰 / 冰蓝配色。保留模型介绍、图库删除与返回、安全区整理等现有行为。

- [Windows x64 桌面包](https://raw.githubusercontent.com/turnsolesama/portfolio/main/ai-hub/releases/AI-Hub-v2.4.0-Windows-x64.zip) — 457352 字节
- [完整源码包](https://raw.githubusercontent.com/turnsolesama/portfolio/main/ai-hub/releases/AI-Hub-v2.4.0-Source.zip) — 191748 字节
- [SHA-256 校验清单](AI-Hub-v2.4.0-SHA256.txt)
- [设计与验证记录](../docs/VISUAL_2.4.md)

本次仅更新前端，沿用已验证的桌面 EXE 与 2.3 后台协议。完整解压后双击 AI Hub.exe，需要本机 Python 3.9+、.NET Framework 4.8+ 与 WebView2 Runtime；升级保留整个 data/。已打开的页面需刷新或重新打开窗口。

验证：运行 120 项 Python 测试，其中 5 项按环境条件跳过；33 项前端测试及脚本语法检查通过。发行包通过白名单、摘要和 ZIP CRC 检查。浏览器自动化连接失败，尚未完成实际截图和逐尺寸视觉验收。

### 更早版本

### AI Hub 2.3.0

新增跨电脑安全区设置、可创建标准目录、分类预览、硬链接分类入口、批次记录与撤销、可选后台启动时自动整理。原件留在原处，既有工作流路径保留。硬链接共用文件内容，不是备份。

- [Windows x64 桌面包](https://raw.githubusercontent.com/turnsolesama/portfolio/main/ai-hub/releases/AI-Hub-v2.3.0-Windows-x64.zip) — 451683 字节
- [完整源码包](https://raw.githubusercontent.com/turnsolesama/portfolio/main/ai-hub/releases/AI-Hub-v2.3.0-Source.zip) — 186081 字节
- [SHA-256 校验清单](AI-Hub-v2.3.0-SHA256.txt)
- [安全区与自动整理说明](../docs/SAFE_ZONE.md)
- [验证记录](../docs/VALIDATION_2.3.md)

解压完整目录后双击 AI Hub.exe，保留本机 Python 3.9+、.NET Framework 4.8+ 与 WebView2 Runtime。全新安装先设置安全区，升级保留整个 data/。程序不预设作者的盘符，不包含用户配置、数据库、模型或图片。

验证：115 项 Python 测试通过，5 项因符号链接权限跳过；实际 NTFS 联接检查通过。33 项前端测试及3份脚本语法检查通过，浏览器预览/执行/撤销与干净解压启动通过。桌面外壳沿用已验证版本。

2.3.0 历史包保留在本目录；使用新版请下载页首的 2.5.0 文件。
