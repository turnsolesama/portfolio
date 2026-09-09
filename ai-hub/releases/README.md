# AI Hub 2.3.0

新增跨电脑安全区设置、可创建标准目录、分类预览、硬链接分类入口、批次记录与撤销、可选后台启动时自动整理。原件留在原处，既有工作流路径保留。硬链接共用文件内容，不是备份。

- [Windows x64 桌面包](https://raw.githubusercontent.com/turnsolesama/portfolio/main/ai-hub/releases/AI-Hub-v2.3.0-Windows-x64.zip) — 451683 字节
- [完整源码包](https://raw.githubusercontent.com/turnsolesama/portfolio/main/ai-hub/releases/AI-Hub-v2.3.0-Source.zip) — 186081 字节
- [SHA-256 校验清单](AI-Hub-v2.3.0-SHA256.txt)
- [安全区与自动整理说明](../docs/SAFE_ZONE.md)
- [验证记录](../docs/VALIDATION_2.3.md)

解压完整目录后双击 AI Hub.exe，保留本机 Python 3.9+、.NET Framework 4.8+ 与 WebView2 Runtime。全新安装先设置安全区，升级保留整个 data/。程序不预设作者的盘符，不包含用户配置、数据库、模型或图片。

验证：115 项 Python 测试通过，5 项因符号链接权限跳过；实际 NTFS 联接检查通过。33 项前端测试及3份脚本语法检查通过，浏览器预览/执行/撤销与干净解压启动通过。桌面外壳沿用已验证版本。

旧版包保留在本目录，使用新版请下载上面的2.3.0文件。
