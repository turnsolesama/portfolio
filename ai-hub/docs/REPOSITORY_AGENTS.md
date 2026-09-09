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

- 安全区整理仅在明确配置的本地目录中建立硬链接，不移动原件、不覆盖目标、不跟随重解析点。修改需验证预览陈旧、路径逃逸、冲突、撤销、启动默认关闭及跨电脑路径失效。
- 测试使用临时夹具；不得用真实用户模型或图库执行整理/撤销。分类库排除出扫描，避免重复统计。

- 2.5 分类四维由 classification.py 共用；登记/证据协议见 docs/REGISTRY.md。修改登记须预览、备份、并发校验，工作流界面使用 verification_state，运行使用 effective_validation_status。数据迁移使用 SQLite backup API 且可回退；不得通过推断状态宣称当前执行通过。
- 同文件别名只能按有效文件身份合并；历史路径已指向其他文件时不得传播人工标签。已有模型库采用只读统一预览，不创建第二棵实体入口树。
