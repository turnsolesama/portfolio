# AI Hub 开发约定

- 用中文沟通，先检查当前文件和用户改动。不要覆盖 `data/`。
- Python 标准库和原生 HTML/JS/CSS；无需 npm/pip 安装。桌面入口为 C# WinForms + WebView2。
- 后台只监听 127.0.0.1。模型权重只读；图库删除仅通过现有回收站接口处理。
- 功能与用途归类由 `aihub/classification.py` 维护。用户覆盖位于独立 `model_labels` 表，扫描不得清除。
- 导航统一经过 `frontend/navigation.js`；页面加载返回 Promise，恢复筛选、分页、滚动和详情，防止旧请求覆盖新页面。
- 更新现有 SQLite 使用 backup API 备份。不要忽略 WAL 直接复制 `.db`。
- 检查：`python -B -m unittest discover -s tests -v`、`node --check frontend/app.js`、`node --check frontend/navigation.js`、`node --test tests/*.test.js`。
- 桌面代码变化还需运行 `desktop/build.py --sdk-package <已核对摘要的SDK> --output <临时路径>/AIHub.exe --test`。
- 使用 `tools/package_release.py` 打包；不把数据、模型、图片、凭据、备份或浏览器配置提交到 GitHub。
