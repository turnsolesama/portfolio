# 构建与发布

源码运行：Python 3.11+，标准库即可。前端是原生 ES modules，无 npm 安装步骤。Node 22+ 仅用于运行前端核心测试。

## Windows x64 便携包

构建环境使用 Python 3.11 x64、PyInstaller 6.22.2。先在临时目录创建隔离 venv，再安装打包依赖；不要修改用户已有推理环境。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install pyinstaller==6.22.2
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --name FrameWeave --add-data "web;web" launch.py
```

将生成的 EXE 与 README、LICENSE、THIRD_PARTY、PYTHON-LICENSE.txt 和 docs 放在同一个 `FrameWeave-0.1.0/` 根目录下打包。源码包只包含明确允许的项目文件，不包含 venv、缓存、测试数据、模型、配置、日志或输入媒体。

官方构建选项：[PyInstaller 使用文档](https://pyinstaller.org/en/stable/usage.html)。PyInstaller 的许可包含允许发布构建产物的例外；独立二进制仍需附带其所含 Python 运行库的许可说明。

## 发布检查

1. 完成 Python / Node 测试与语法检查。
2. 真实连接一个 ComfyUI 后端，确认模式能力、诊断和至少一个生成结果；分别记录未实测模式。
3. 启动打包后的 EXE，核实 HTTP 服务、静态前端、结果回传和退出。
4. 检查 ZIP CRC、根目录、解压体积、SHA-256 以及公开文件允许清单。
5. GitHub 上传后重新读取源文件/下载包核对哈希。

源码可跨平台运行；当前便携二进制只构建 Windows x64。没有证据时不可宣称其他平台或 GPU 已经验证。
