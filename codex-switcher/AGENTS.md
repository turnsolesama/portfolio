# Codex Switcher 开发约定

- Python 3.11+ 标准库、Tkinter；不添加在线前端依赖。Windows EXE 仅负责静默查找并启动 Python。
- 不把 profiles.json、用户环境变量、config.toml、登录数据、备份或日志提交到仓库。
- 切换前备份并验证 TOML 的语义差异；只允许修改根级模型选择及工具托管区域。配置变化需拒绝覆盖。
- 导入只在本地解析；默认不保存密钥。导入不等于激活。导出仅使用白名单字段。
- 用虚构配置运行 `python -B -m unittest discover -v`。不得复制真实 Codex 配置或依赖真实 API Key 来测试。
- 图形验证运行 `Codex Switcher.exe --demo`，与真实配置、环境变量完全隔离。不得在开发验证中应用真实切换或重启用户的 Codex。
- 界面原语位于 `switcher_ui.py`。主操作放在滚动区域外；布局改动运行 `test_switcher_ui.py`，覆盖 100% / 125% / 150% / 200% 缩放。测试窗口在屏幕外且使用临时演示数据。
- 发布使用 `python -B package_release.py`，白名单打包并检查摘要；保留用户现有修改。
