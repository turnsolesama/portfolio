# AI Hub

在一个本地工作台里管理模型、LoRA、工作流、出图和资料。

AI Hub 采用炭灰界面，提供独立 Windows 桌面窗口。按图片、视频、语言、音频等用途找模型；按风格、角色、光照、细节等用途整理 LoRA。模型保留原文件位置，评分、备注与分类保存在本机。

## 获取与启动

Windows 桌面包包含 `AI Hub.exe`、完整程序源码和使用说明。解压到一个可写目录后，双击 **AI Hub.exe**。请保留整个解压目录；桌面可以另建快捷方式。

运行条件：Windows x64、.NET Framework 4.8+、本机 Python 3.9+、Microsoft Edge WebView2 Runtime。桌面包不捆绑 Python 和 WebView2 Runtime，也不包含模型权重。程序会查找已安装的 Python；也支持将可用解释器放到 `runtime/python.exe`。

- [Python 官方 Windows 下载](https://www.python.org/downloads/windows/)
- [Microsoft WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/)
- `start.vbs` 为备用浏览器入口；`debug.bat` 用于需要控制台输出的诊断。

首次使用：进入 **终端设置**，填写资产根目录，点击 **探测目录**，检查并保存扫描范围，再点击 **刷新索引**。新安装没有预设他人的磁盘目录，不会直接扫描整台电脑。

## 常用功能

| 功能 | 使用方式 |
| --- | --- |
| 按功能查模型 | 图片创作、视频制作、语言与对话、语音与音乐、视觉工具、通用组件、用途待确认 |
| LoRA 用途 | 风格、角色、光照、细节、姿态构图、服饰、场景、动作运镜、加速等多选分类 |
| 手动与批量分类 | 详情中的“调整分类”，或勾选列表后“批量分类”；可恢复自动建议 |
| 模型资料 | 兼容架构、训练底模、触发词候选、训练参数、路径、来源、评分和备注 |
| 图库 | 搜索、模型引用筛选、大图查看、密度切换、移到 Windows 回收站 |
| 返回来路 | 顶部返回按钮恢复筛选、页码、滚动和模型详情；Alt+← / Alt+→ 后退与前进 |
| 资料与工作流 | 阅读已登记资料、查看工作流依赖和路径记录 |

Ctrl+K 聚焦全局模型搜索。返回记录保留在当前页面会话内，刷新页面会重新开始。引用次数来自已扫描图片的元数据，不代表模型质量或全部使用历史。

分类规则、证据优先级与手动覆盖：[分类说明](docs/CLASSIFICATION.md)。功能分类不替代架构兼容检查，也不代表已验证生成效果。

## 数据与更新

本地服务仅监听 `127.0.0.1`，默认端口 8765。关闭桌面窗口会保留后台服务和正在运行的任务。网络来源识别和版本检查由用户手动触发；不会自动下载或替换模型。

`data/` 包含索引、配置、评分、备注、来源登记、分类和桌面浏览器配置。升级时保留整个 `data/`，然后替换程序文件；任务运行时请先等任务完成。运行中的 SQLite 请使用 backup API 备份，不能忽略 WAL 只复制数据库文件。

更新前关闭 AI Hub 窗口；后台代码更新后还需重新启动后台服务。只关闭窗口会保留服务，因此不会让旧服务自动加载新版 Python 文件。请只停止属于该应用目录的服务进程。

图库删除使用 Windows 回收站，只有索引与实际文件仍一致、且位于已配置出图目录的普通图片才可处理；回收失败时保留文件和索引。

可选的目录台账放在所选资产根目录的 `00_Management/Catalogs`；没有台账时仍可使用现场扫描、模型列表、图库与手动分类。

## 开发和构建

后台使用 Python 标准库，前端为原生 HTML、CSS 和 JavaScript，无需 npm/pip 安装。若本机已有 Pillow，图库可以使用缩略图优化；没有时读取原图。

```powershell
python -B -m unittest discover -s tests -v
node --check frontend/app.js
node --check frontend/navigation.js
node --test tests/*.test.js
```

桌面构建使用本机 .NET Framework 编译器与固定版本 WebView2 SDK，见 [桌面构建说明](desktop/README.md)。

```powershell
python -B tools/package_release.py --exe "AI Hub.exe" --output releases
```

打包采用文件白名单，生成 Windows 包、源码包和 SHA-256 清单；不会纳入运行数据、模型、图片、备份、浏览器配置、凭据或本机快捷方式。

第三方组件说明：[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。本项目尚未指定额外的开源许可证，WebView2 组件按随附的微软许可分发。
