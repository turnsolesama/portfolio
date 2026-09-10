# 映序公开版开发约定

- 中文本地视频创作项目工作台；独立目录 `yingxu/`。公开版不包含任何个人素材、数据库、缓存、日志或帐号配置。
- Python 3.11+ 标准库 HTTP + SQLite，原生 HTML/CSS/JS；Pillow 与 PATH 中的 FFmpeg 为可选缩略图依赖。无 CDN、遥测或自动下载。
- 默认应用数据 `%LOCALAPPDATA%\YingXu`，项目在 Windows“文档”目录的 `YingXu\Projects`。`YINGXU_DATA_DIR` 和 `YINGXU_PROJECTS_DIR` 只接受绝对路径；测试必须覆盖到临时目录，禁止在真实用户数据上测试。
- 桌面仅监听 127.0.0.1:8791，开发后台可用 `--port`。写接口要求同源和会话令牌；保留版本备份、原子替换、冲突检查和有界后台工作队列。
- 界面用白色内容区、淡灰侧栏、墨色文字、少量绿色强调。删除是可恢复的应用回收站，不永久删除素材。
- 验证：`python -B -m unittest discover -s tests -v`、`node --check frontend/app.js`、`node tests/frontend_context_menu.cjs`、`node tests/frontend_drag_drop.cjs`。
- Windows 桌面离线构建：`python desktop/build.py --sdk-package <已下载官方SDK.nupkg> --output YingXu.exe --test`。构建脚本校验固定 SDK 摘要，不下载依赖。
- 发布：`python tools/package_release.py`，仅白名单打包；`python tools/verify_release.py releases/YingXu-v0.2.2-Windows-x64.zip` 使用隔离临时目录验证。
- 不提交构建日志、本机配置、个人目录、素材和数据库；打包文件不能包含个人绝对路径。
