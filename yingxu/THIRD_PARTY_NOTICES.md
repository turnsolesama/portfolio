# 随包组件与来源

完整包仅从 `tools/runtime-lock.json` 指定的上游发行档案组装，逐项校验大小与 SHA-256。不复制开发者安装目录、帐号、浏览记录或项目文件。

- **CPython 3.13.15**：Python Software Foundation License。保留 `runtime/LICENSE.txt`；[发行与源码](https://www.python.org/downloads/release/python-31315/)。嵌入版仅配置相对导入路径，解释器二进制未改动。
- **Pillow 12.3.0**：保留 wheel 中的许可证及其依赖说明，位于 `runtime/Lib/site-packages/pillow-12.3.0.dist-info/licenses/`。[发行档案与源码](https://pypi.org/project/pillow/12.3.0/#files)。原样使用官方 Windows wheel。
- **FFmpeg 9.0.1 essentials build（Gyan）**：独立命令行进程，保留 `runtime/ffmpeg/LICENSE` 和上游 README、文档。[构建发行、配置和库清单](https://www.gyan.dev/ffmpeg/builds/)，[FFmpeg 对应源码](https://ffmpeg.org/releases/ffmpeg-9.0.1.tar.xz)，[构建方发行记录](https://github.com/GyanD/codexffmpeg/releases/tag/9.0.1)。该构建使用 GPLv3；映序不修改二进制、不链接 FFmpeg 库，仅通过命令行调用。随包省略未调用的 ffplay、ffprobe。
- **Microsoft WebView2 Fixed Version Runtime 152.0.4191.62 x64**：保留原包许可证与第三方声明。[微软下载与分发说明](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution)。微软 WebView2 SDK 许可另见 `desktop/WebView2-LICENSE.txt`。完整包保留整个固定运行时，不裁剪解码器、语言或渲染组件。

系统已有相同或更新的 WebView2 时优先使用系统版本；否则使用随包版本。固定运行时不会自行更新，应随映序后续发布更新。Windows 10 所需的 AppContainer 读取/执行权限仅设置在随包 WebView2 文件夹，不涉及项目和应用数据。

## Markdown 编辑器本地组件（0.3.3）

实时预览编辑器基于 CodeMirror 6、Lezer 及相关 MIT 许可依赖。直接版本固定于 `tools/markdown-editor/package.json`：`@codemirror/state` 6.7.4、`@codemirror/view` 6.43.11、`@codemirror/commands` 6.11.0、`@codemirror/language` 6.12.4、`@codemirror/lang-markdown` 6.5.2、`@lezer/markdown` 1.7.2；构建工具为 esbuild 0.28.2。完整传递依赖、下载来源和完整性值由同目录 `package-lock.json` 锁定。

- `frontend/live-markdown.js` 是本地浏览器 bundle；运行时不访问 npm、CDN 或外部脚本，也不需要安装 Node.js。
- `frontend/live-markdown.manifest.json` 列出实际进入 bundle 的组件名称、锁定版本、许可证，以及 bundle 的字节数和 SHA-256。
- `frontend/live-markdown.LICENSE.txt` 保留实际随包组件的完整许可证和版权声明。生成工具从构建输入收集许可证，缺失时构建失败。
- `frontend/live-markdown-source.mjs` 与 `tools/markdown-editor/build.mjs` 为可重建入口。Node.js/npm 和 esbuild 仅用于开发构建，不作为终端用户运行环境安装或启动。

编辑器显示层改变排版和装饰，原始 Markdown 文本仍是唯一文稿模型。原始 HTML 不作为编辑器内容执行，格式操作不通过 HTML 回写文稿。


Excalidraw 0.18.1 与 React 18.3.1 用于本地画板；依赖锁定、许可证及字体许可证位于 frontend/canvas/，构建输入在 tools/canvas-editor/。
