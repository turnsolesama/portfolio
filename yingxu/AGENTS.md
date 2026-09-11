# 映序公开版开发约定

- 中文本地视频创作项目工作台；独立目录 `yingxu/`。公开版不包含任何个人素材、数据库、缓存、日志或帐号配置。
- Python 3.11+ 标准库 HTTP + SQLite，原生 HTML/CSS/JS；源码运行可使用 Pillow 与 PATH 中的 FFmpeg；公开完整包必须自带锁定来源的运行环境。无 CDN、遥测或启动时自动下载。开发构建可以显式下载锁定的上游档案。
- 默认应用数据 `%LOCALAPPDATA%\YingXu`，项目在 Windows“文档”目录的 `YingXu\Projects`。`YINGXU_DATA_DIR` 和 `YINGXU_PROJECTS_DIR` 只接受绝对路径；测试必须覆盖到临时目录，禁止在真实用户数据上测试。
- 桌面仅监听 127.0.0.1:8791，开发后台可用 `--port`。写接口要求同源和会话令牌；保留版本备份、原子替换、冲突检查和有界后台工作队列。
- 界面用白色内容区、淡灰侧栏、墨色文字、少量绿色强调。删除是可恢复的应用回收站，不永久删除素材。
- 回收站清理默认预览后确认（用户可在设置关闭弹窗，仍必须取得后台预览令牌）：项目内原文件移入 Windows 回收站，外部引用与外部 SKILL 保留源文件。严禁永久删除降级；共享、状态变化、未知目录内容和失败必须保留记录并解释。相关测试仅使用临时合成文件，禁止操作真实回收条目。
- 验证：`python -B -m unittest discover -s tests -v`、`node --check frontend/app.js`、`node tests/frontend_context_menu.cjs`、`node tests/frontend_drag_drop.cjs`、`node tests/frontend_selection.cjs`。
- Markdown 编辑器构建：在 `tools/markdown-editor` 执行 `npm ci --ignore-scripts --no-audit --no-fund`，然后 `npm run build`；每步成功后再运行前端测试。版本与完整性由 `package-lock.json` 锁定，输出本地 bundle、依赖清单和许可证，禁止从 CDN 加载。Node.js/npm 只在开发构建与测试时使用，完整包运行不需要 Node.js。
- Markdown 文本是唯一保存模型，不将排版后的 HTML 回写文稿。超过 500000 字符或混合换行降级源码；中文 composition 期间禁止重建/关闭编辑器，保存草稿需与当前文本一致，并保留原文件 BOM 和换行方式。
- Windows 桌面离线构建：`python desktop/build.py --sdk-package <已下载官方SDK.nupkg> --output YingXu.exe --test`。构建脚本校验固定 SDK 摘要，不下载依赖。
- 发布：`python tools/package_release.py`，仅白名单打包；`python tools/verify_release.py releases/YingXu-v0.4.4-Windows-x64.zip` 使用隔离临时目录验证。
- 不提交构建日志、本机配置、个人目录、素材和数据库；打包文件不能包含个人绝对路径。

- 完整包先运行 `python tools/prepare_runtime.py --cache <构建缓存> --download`；运行时清单逐项校验，只能来自 `tools/runtime-lock.json`，禁止复制本机安装环境。大体积 ZIP 放 GitHub Release，不提交 Git 历史。

- 新增定向回归：`node tests/frontend_marquee.cjs`、`node tests/frontend_capture.cjs`、`node tests/frontend_resource_groups.cjs`、`node tests/frontend_live_markdown.cjs`、`node tests/frontend_markdown_integration.cjs`；后端 `python -B -m unittest discover -s tests -p test_markdown_assets.py -v`、`python -B -m unittest discover -s tests -p test_resource_groups.py -v`。完整前端测试应逐个运行 `tests/frontend_*.cjs` 并检查退出码。
- 所有合成测试根目录使用 `Path(temporary).resolve()` 后再构建来源路径，避免 Windows TEMP 短路径或大小写不同导致索引漏项。
- 截图仅在用户按快捷键或点击截图时触发，无持续屏幕/剪贴板轮询；一次只截请求时鼠标所在的屏幕，最大 40000000 像素。原生 `desktop/build.py --test` 包含 CaptureTests，使用合成位图、模拟剪贴板和临时 HTTP 服务；不得把通过合成测试写成已验收真实屏幕、多显示器或真实剪贴板。
- 文件名标题置于正文 contenteditable 外，既有 Markdown 第一行不删除；新建普通笔记显式空正文。截图保存到项目参考资料后，仅在原笔记仍处于可编辑模式、项目/文稿/输入法状态未改变时插入草稿。
- 素材组是本项目内的逻辑集合，不搬动文件或改变其分类；成员与修订号需由后台验证。Markdown 图片仅预览已登记的项目内独立光栅文件，拒绝外部 URL、越界路径与链接；无 imageResolver 不加载图片。

- 框选只从资源滚动区空白启动；默认本页 48 项，排除隐藏组成员/控件/正文。缓存卡片几何、合并帧更新，空闲不得持续 RAF 或轮询；Ctrl 切换、Shift 追加、Esc/取消恢复，减少动态效果设置下不自动滚动。
- 独立文稿标题仅显示名称、不含扩展名，真实文件路径与正文不得因显示标题改变。截图插入只在选区末尾追加，不替换已选正文；异步结果处理结束前保持忙碌，防止退出漏掉新草稿。
- 0.3.7 点击项目文件标题复用确认式重命名弹窗；名称输入不含原扩展名，确认时保留扩展名和未保存正文，不逐字自动重命名文件。不可改名来源维持原权限边界。

- 0.4.0 Word 编辑只挂载最多 40 段，跨页草稿必须保留；不要重引入全量 textarea 与逐项布局读写。检查 `node tests/frontend_docx_editor.cjs`。
- 0.4.4 Word 预览同样按 40 段挂载；文内查找须覆盖当前草稿和跨页定位。画板 iframe 必须固定宿主保留撤销，隐藏时停用，关闭时销毁；本地字体构建不得放宽 CSP。画板构建在 `tools/canvas-editor` 执行 `pnpm install --frozen-lockfile --ignore-scripts` 后 `node build.mjs`，开发依赖不打入运行环境。容量清理只允许预览 token 中的受控缓存/旧版本，选项变更必须使确认失效。
- SVG/HTML 是独立只读类型，无缩略图任务。SVG 只能净化后作为图片提供，所有媒体直链必须经过同一净化器；HTML 静态片段必须在无 allow-* 的 sandbox iframe 与限制性 CSP 中，原始媒体响应为文本附件。检查 `python -B -m unittest discover -s tests -p test_static_formats_http.py -v` 和 `node tests/frontend_static_formats.cjs`。
