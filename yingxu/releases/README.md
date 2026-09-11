# 映序 Windows 发布包

当前完整版 **0.3.9**，面向 Windows 10 22H2 / Windows 11 x64。自带 Python、Pillow、FFmpeg 与 WebView2，完整解压后双击 `YingXu.exe`。从 [GitHub Releases 下载页面](https://github.com/turnsolesama/portfolio/releases) 获取完整包、SHA-256 和验收记录。较大的完整包使用 Release 附件分发，历史轻量包保留原路径。

组装方法见 [开发说明](../docs/开发说明.md)，来源与许可见 [第三方组件说明](../THIRD_PARTY_NOTICES.md)。所有检查只使用临时合成项目。


**[下载完整包](https://github.com/turnsolesama/portfolio/releases/download/yingxu-v0.3.9/YingXu-v0.3.9-Windows-x64.zip)** · [SHA-256](https://github.com/turnsolesama/portfolio/releases/download/yingxu-v0.3.9/YingXu-v0.3.9-SHA256.txt) · [包大小与摘要](https://github.com/turnsolesama/portfolio/releases/download/yingxu-v0.3.9/YingXu-v0.3.9-manifest.json) · [隔离验收记录](https://github.com/turnsolesama/portfolio/releases/download/yingxu-v0.3.9/YingXu-v0.3.9-verification.json)

0.3.7 截图默认进入标注后确认，支持画笔、箭头、矩形、颜色/粗细与撤销；设置中保留快速完成，取消不写剪贴板或项目。原生状态栏显示实际界面缩放百分比，点击恢复 100%；图片预览另显示图片自身的实际缩放比例。同时增加项目行与素材组成员长条行的拖动归类：拖到其他分类或同项目的组，拖出弹窗到明确空白区域则未分类或移出组，Esc 取消。全部为逻辑整理，磁盘原文件保持不变；修复素材选择框保持焦点时按 Delete 无响应，仍沿用映序回收站、确认开关与草稿保护。

[历史完整包 0.3.6](https://github.com/turnsolesama/portfolio/releases/tag/yingxu-v0.3.6) 的附件与验收记录保持不变。

本版还支持多选素材后批量追加标签、修改制作状态：工具栏和右键菜单均可进入，保留各素材原标签；整批验证与数据库更新失败时不留下部分修改，不改变原文件。没有新增翻译模型或模型下载要求。

0.3.6 增加标题改名与 Delete 快捷键：点击项目文件标题打开已有重命名弹窗，名称输入不含扩展名，确认时保留原扩展名和未保存正文。不是逐字自动重命名。资源区选中素材后按 Delete 可移入映序回收站，沿用普通删除确认设置；编辑标题、正文或其他输入框时只删除文字，不触发素材删除。0.3.5 的截图、框选、素材组与 Markdown 功能继续保留。

[历史完整包 0.3.5](https://github.com/turnsolesama/portfolio/releases/tag/yingxu-v0.3.5) 的附件与验收记录保持不变。

## 历史轻量版


历史轻量版 **0.2.3**，使用 MIT 许可证。桌面壳包含的微软 WebView2 SDK 组件遵循包内 `desktop/WebView2-LICENSE.txt`。

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

## 0.3.8：文件打开、文档预览与播放修复

- 完整 ZIP 包含灰绿色“界面 100%”桌面状态文字，悬停才显示下划线，点击恢复 100%。
- 项目库每个项目右侧有“重命名”，仅改项目名称，不移动目录；“未分类”是内置分组。
- 关闭最后一个视频/音频标签释放播放器；切换标签停止旧媒体，关闭窗口留在托盘也暂停播放，重新打开不会自动恢复旧播放。
- Windows 双击或“打开方式”打开的 Markdown/文本可直接编辑并按 Ctrl+S 保存原文件，不自动导入项目。原编码/BOM/统一换行保留，保存前备份，冲突不覆盖。重新明确打开同一路径时可恢复本地未保存草稿。
- Word 默认“文档预览”，显示标题、文字样式、表格与支持的内嵌光栅图片；“编辑文字”保留未改文字的 run 样式和其他 ZIP 资源。精确分页、页眉页脚、浮动排版及旧 .doc 不属于本次编辑范围。
- Word 图片按需读取：最多 32 张，单张 4 MiB、合计 8 MiB、每张 4000 万像素；预览图最长边 1600 像素，动画显示首帧，原图不改变；外链、不支持格式或超限内容显示提示。无图片常驻任务，索引只读纯文本。

## 0.3.9：拖动整理项目分类

- 在项目库左侧将一个自定义分类拖到另一个分类上，即可成为它的子分类。例如将“222”拖到“1111”，成为“1111 / 222”。分类里的项目和下级分类保持原有归属，磁盘目录不移动。
- 拖到“全部项目”可将分类移回项目库顶层。松手前显示目标，Esc 取消；不能拖入自身、自己的子分类或当前父级，同一层重名会提示并保持原状。
- 触屏可用分类握柄；也可以通过“编辑分类 → 上级分类”整理。项目行拖动归类继续保留。“未分类”仍为固定系统分组。
- 无新增依赖、模型或空闲轮询。完整包保留 0.3.8 的缩放配色、项目重命名、媒体暂停、外部 Markdown 编辑与 Word 结构预览修复。
