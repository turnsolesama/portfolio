# 映序 0.3.4 · 运行与构建

这是一个自带运行环境的 Windows x64 完整包。完整解压后双击 `YingXu.exe`，不需要自行安装 Python、Pillow、FFmpeg 或 WebView2。

## 运行条件

面向 **Windows 10 22H2 / Windows 11 x64**。使用这些系统自带的 .NET Framework 4.8+；不支持 Windows 7、32 位 Windows，ARM64 未提供原生包。

随包提供 CPython 3.13.15、Pillow 12.3.0、FFmpeg 9.0.1 和 WebView2 固定运行时 152.0.4191.62。系统 WebView2 相同或更新时优先复用，否则使用随包版本。环境位于 `runtime/`，不写入系统 Python、不修改 PATH、不在每次启动时解压，也不会自动联网下载。

图片缩略图、图片尺寸和生成信息识别、视频缩略图、示例媒体、桌面原始文件拖拽、Shift 多选、文档编辑、索引与 AI 交接功能均保留。原始视频直接播放仍取决于 WebView2 解码器；完整包不会让所有专业格式都能内嵌播放。Word 仍仅编辑普通正文段落。

完整解压 ZIP，保留 `YingXu/` 下全部文件，双击 `YingXu.exe`。`start.vbs` 是备用入口。无需管理员权限，没有自动启动或自动更新。

## 数据与配置

| 内容 | 默认位置 |
|---|---|
| 数据库、版本备份、SKILL、缓存、日志 | `%LOCALAPPDATA%\YingXu` |
| 新建项目 | Windows“文档”目录下的 `YingXu\Projects` |
| WebView2 配置与窗口尺寸 | 应用数据下的 `desktop` |

系统“文档”若已重定向，默认项目目录跟随系统设置。应用不会扫描全盘；导入目录与扫描 SKILL 都在用户选择或现有 SKILL 约定目录范围内进行。

环境变量支持自定义路径，必须为绝对路径：

```powershell
$env:YINGXU_DATA_DIR = 'D:\YingXuData'
$env:YINGXU_PROJECTS_DIR = 'D:\VideoProjects'
$env:YINGXU_PYTHON = 'C:\Python311\python.exe'
.\YingXu.exe
```

Python 查找顺序：`YINGXU_PYTHON`（若设置只使用该项）、`runtime\python.exe`、Python 注册表安装记录、PATH 中的 `python.exe`。每个候选均须通过 3.11+ 版本检查。完整包自带 `runtime`，正常使用不需要设置这些环境变量。

不要同时对同一数据目录运行多个后台。端口 8791 上只有数据目录指纹一致的映序后台且版本一致才会被复用；旧版或不同数据目录服务占用端口时，新版显示提示并保留原服务。更换数据目录不会自动迁移原有内容。

关闭窗口后，后台和导入任务继续运行。需要彻底停止时，先保存编辑、等待导入完成，从托盘菜单退出映序窗口，再执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\Stop-YingXu.ps1
```

此脚本只停止命令行匹配本包 `server.py` 的 Python 进程，不删除文件。删除程序文件夹也不会删除上述项目与应用数据。

## 源码运行

以下命令均在应用根目录运行，`python` 应为已安装的 3.11+ 解释器。

```powershell
python -B launcher.pyw --no-browser --no-dialog
```

随后在浏览器打开 `http://127.0.0.1:8791/`。浏览器不提供桌面原生拖出功能。开发或隔离验证可直接启动：

```powershell
python -B server.py --port 18791 --data 'D:\YingXuTest\Data' --projects-root 'D:\YingXuTest\Projects'
```

## 检查与离线构建

```powershell
python -B -m unittest discover -s tests -v
node --check frontend/app.js
node tests/frontend_context_menu.cjs
node tests/frontend_drag_drop.cjs
node tests/frontend_selection.cjs
python desktop/build.py --sdk-package 'D:\Downloads\microsoft.web.webview2.1.0.4191.47.nupkg' --output YingXu.exe --test
python tools/prepare_runtime.py --cache 'D:\YingXuBuildCache' --download
python tools/package_release.py
python tools/verify_release.py releases/YingXu-v0.3.4-Windows-x64.zip
```

构建使用 Windows 自带 .NET Framework C# 编译器；SDK 必须事先自行下载。固定 WebView2 SDK 为 `1.0.4191.47`，9,259,926 字节，SHA-256 `f492bbf547d0da329553b6727435b677579b1e9f91cc9e4a1ad029366d5f23d0`。构建程序只读本地 SDK，不联网。微软 SDK 许可在 `desktop/WebView2-LICENSE.txt`，其运行组件嵌入 EXE。

打包脚本使用源码、前端、测试、桌面源码、公开文档与许可证白名单。仅允许组装锁定摘要的官方运行时档案；禁止纳入开发者安装环境、数据库、缓存、日志、真实项目、版本备份和私有配置。验证脚本在临时中文含空格路径解压，用独立数据目录和空白测试用户启动随机端口后台，结束时仅终止自身子进程并清理临时目录。

构建下载是开发者明确执行的步骤，普通用户启动时不联网安装依赖。下载来源、许可证和固定运行时更新责任见 [第三方组件说明](THIRD_PARTY_NOTICES.md)。使用指南会显示图片、视频缩略图和桌面拖出能力是否可用。
