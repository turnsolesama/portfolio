# 映序 Windows 发布包

当前版本为 **0.2.3**，使用 MIT 许可证。桌面壳包含的微软 WebView2 SDK 组件遵循包内 `desktop/WebView2-LICENSE.txt`。

下载 [YingXu-v0.2.3-Windows-x64.zip](https://raw.githubusercontent.com/turnsolesama/portfolio/main/yingxu/releases/YingXu-v0.2.3-Windows-x64.zip)，完整解压后双击 `YingXu.exe`。**ZIP 包含应用与源码，不包含 Python 运行环境。** 需要 Windows 10/11 x64、Python 3.11+、.NET Framework 4.8+ 与 WebView2 Runtime；Pillow 和 FFmpeg 为缩略图可选依赖。

[SHA-256 清单](YingXu-v0.2.3-SHA256.txt) · [包大小与摘要](YingXu-v0.2.3-manifest.json) · [发布验证记录](YingXu-v0.2.3-verification.json) · [运行条件与配置](../RUNNING.md) · [功能介绍](../README.md)

每个包只有 `YingXu/` 一个根文件夹。`RELEASE_MANIFEST.json` 列出所有包内文件的大小与 SHA-256。白名单只收录程序、原创示例生成代码、前端、测试、桌面源码、公开文档和许可证；不包含素材、项目、数据库、缓存、日志、帐号配置或用户自建 SKILL。

在应用源码目录重新生成并检查：

```powershell
python tools/package_release.py
python tools/verify_release.py releases/YingXu-v0.2.3-Windows-x64.zip
```

0.2.3 增加直接从图片、卡片和列表行发起 Windows 原始文件拖拽，以及 Shift 首尾连续多选。选中后可批量拖出，也可在映序内移动分类或文件夹。修复快速拖动准备延迟，并兼容 WebView2 拖回自身窗口缺少放下事件的情况。

[历史版本 0.2.2](https://raw.githubusercontent.com/turnsolesama/portfolio/main/yingxu/releases/YingXu-v0.2.2-Windows-x64.zip) 保持原包与校验记录不变。

0.2.2 修复从图片或视频缩略图拖动素材时，被误识别为外部文件导入的问题。卡片和列表行支持拖到分类、文件夹和根目录；多选移动保留，外部文件导入与桌面拖出手柄仍可使用。

[历史版本 0.2.1](https://raw.githubusercontent.com/turnsolesama/portfolio/main/yingxu/releases/YingXu-v0.2.1-Windows-x64.zip) 保持原包与校验记录不变。

0.2.1 提供右键操作列表和打开本地文件夹，并为公开分发增加个人数据目录、可配置 Python 查找和后台数据目录身份检查。现有项目管理、文件夹、拖放移动、文档编辑、SKILL、AI 交接与应用回收站功能一并保留。

该 EXE 未进行商业代码签名；Windows 下载提示取决于系统策略。发布检查覆盖编译、后台、源码与包完整性；真实桌面拖出到不同剪辑软件的接收行为仍由目标软件决定。
