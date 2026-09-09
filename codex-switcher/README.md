# Codex Switcher

[返回三个软件的目录](../)

## 下载 Codex Switcher

**[直接下载 Windows 程序包 · v2.4.0](https://raw.githubusercontent.com/turnsolesama/portfolio/main/codex-switcher/releases/Codex-Switcher-v2.4.0-Windows-x64.zip)**

完整解压后双击 `Codex Switcher.exe`。包内包含本软件源码，EXE 需要 Python 3.11+（含 Tkinter）与 .NET Framework 4.x。

[下载与 SHA-256 校验](releases/README.md) · [程序源码](codex_switcher.pyw)

一个用于 Windows 的本地 Codex API 服务配置工作台。炭灰界面、服务搜索、当前模式、密钥状态、详情面板和独立 EXE 启动入口。

## v2.4 视觉更新

- 中性炭灰、柔和冰蓝和细分隔线；品牌顶栏与当前配置条分工清晰，保留更多服务管理空间。
- 服务详情按连接、模型、认证分组，紧凑键值布局自动换行；长内容独立滚动，应用与维护按钮保持可见。
- 当前使用、未应用、需要修正使用独立状态徽标。列表中官方模式也明确标记当前状态。
- 新增、导入等日常操作使用低强调配色，主强调色集中在“应用所选配置”；悬停、按下、禁用状态保持清晰对比。
- 继续支持 JSON / TOML / env / cURL / Python / Node.js 的本地静态导入。

更新后关闭旧切换器窗口，再从桌面快捷方式或 EXE 打开。未强制结束已有窗口。
设计参考与维护说明见 [DESIGN.md](DESIGN.md)。

## v2.3 Python / Node.js 导入

同时修复深色界面的控件状态：导入/更多菜单按钮悬停时保持炭灰底色和浅色文字，箭头同步变色；统一普通按钮、下拉选择框、表头、复选框的悬停/按下/禁用配色。禁用状态优先，不会被鼠标悬停覆盖。

- 粘贴完整 OpenAI SDK 示例，或选择 `.py` / `.js` / `.mjs` / `.cjs` 文件。无需安装 OpenAI SDK 或 Node.js 来执行导入。
- Python：支持 `OpenAI` / `AsyncOpenAI`、导入别名、字面量配置字典、常量引用、`**kwargs`，以及 `os.getenv` / `os.environ.get` / `os.environ[...]` 密钥变量。
- Node.js：支持 ESM `import`、CommonJS `require('openai')`、对象配置、常量引用、对象展开、简单 async 函数/箭头函数包装，以及 `process.env.KEY` / `process.env['KEY']`。
- 从 `responses.create` 或 DeepSeek 官方 `chat.completions.create` 读取模型和推理强度；Python `extra_body.thinking` 也可识别。其他未确认兼容的 Chat 服务不会被自动转换。
- 地址、模型和认证需能静态确定。动态计算、重赋值、复杂表达式、配置对象修改或自定义认证会提示需要简化示例。只支持上述 SDK 示例结构，不是通用 Python/JavaScript 执行器；fetch、axios、requests 和 TypeScript 代码暂不作为导入格式。
- 同样提供新增预览、重复跳过、密钥默认不保存。解析不执行示例、不加载第三方模块、不读取实际环境变量或调用 API。

示例：[Python](examples/deepseek.py) · [Node.js](examples/deepseek.mjs)。两个示例均使用占位密钥变量，模型为 `deepseek-v4-pro`、推理强度为 `high`。

## v2.2 cURL 导入

- 直接粘贴 DeepSeek 官方 cURL 示例，保留 `deepseek-v4-pro` 和 `reasoning_effort: high`。预览展示地址、模型、Responses 协议、推理强度与密钥变量。
- 将 DeepSeek 官方 Chat Completions 示例转换为 `base_url=https://api.deepseek.com`、`wire_api=responses`；其他未知 Chat Completions 服务不猜测兼容性。
- 识别 Markdown 代码块、网址链接、复制时的下划线转义，以及 Bash / PowerShell / CMD 换行续行。支持 `curl.exe`、`-H`、`-d`、`--json`、`--data-raw` 等常用写法。
- `${DEEPSEEK_API_KEY}`、`$NAME`、`%NAME%` 和 `$env:NAME` 只作为变量引用；解析不读取其值，不保存占位符。仅含变量的导入禁用“保存附带 API Key”；导入后编辑服务填写实际 Key。
- 推理强度可编辑，应用时映射到 Codex 根级 `model_reasoning_effort`；为空时沿用当前值。切回官方模式时模型和推理强度保持当前值，需要时自行调整。
- 不会发送示例对话、执行命令、读取 `@文件` 或调用 API。`messages`、`stream` 和其他单次请求参数由 Codex 管理。自定义请求头或不能完整转换的思考模式会说明原因并拒绝导入。

使用：关闭旧切换器窗口，通过 EXE 打开 → 导入配置 → 粘贴导入 → 粘贴完整 cURL → 解析并预览 → 导入所选。保存后补充 API Key，最后手动应用。

[DeepSeek cURL 示例](examples/deepseek.curl) · [DeepSeek 官方 Responses 文档](https://api-docs.deepseek.com/zh-cn/guides/responses_api/) · [首次调用文档](https://api-docs.deepseek.com/zh-cn/)

v2.1.1 修复 Windows 任务栏显示 Python 图标的问题：在创建窗口前设置独立应用标识，并为主窗口与弹窗使用同一套图标。演示环境使用独立分组。更新后关闭旧切换器窗口，再通过 EXE 打开。

## v2.1 界面更新

- 将大幅标题和状态卡收为紧凑的顶部栏，主要空间用于服务列表与详情。
- 左右分栏可拖动调节，并限制最窄宽度；详情独立滚动，应用、编辑、创建副本、移除始终固定在底部。
- “导入配置”集中提供文件导入与粘贴导入；导出和备份恢复位于“更多”。搜索支持 `Ctrl+F`，右侧 × 清空搜索。
- 编辑表单采用双列布局；粘贴、导入预览和备份恢复窗口可调整大小，底部按钮始终可见。`Esc` 取消当前弹窗。
- 字体、间距和控件按 Windows DPI 缩放。主窗口最小尺寸为 900 × 570 逻辑像素；在屏幕空间较小时限制到可用区域。
- 创建副本会生成唯一 ID，保留原记录；副本的密钥变量单独生成，需要自行填写 API Key。
- 旧列表中的不兼容配置保留并标为“需修正”，不会阻断其他服务的加载与编辑。修正前禁用应用，不会自动将旧协议转换为 Responses。

测试记录见 [TEST_REPORT.md](TEST_REPORT.md)。

## 启动

解压整个目录，双击 **Codex Switcher.exe**。需要 Windows x64、.NET Framework 4.x、Python 3.11+（包含 Tkinter）。EXE 不包含 Python；可使用系统安装的 Python，或把可用运行环境放在 `runtime/pythonw.exe`。

也可以直接运行 `python codex_switcher.pyw`。`Codex Switcher.exe --demo` 打开隔离演示，不读取或更改真实 Codex 配置和用户密钥。

## 常用功能

- 新增、编辑、复制、搜索和移除服务配置。
- 在官方账号登录与第三方 Responses API 配置之间切换；应用前检查并备份。
- 文件或粘贴导入，预览新增条目，按 Ctrl 多选，重复的地址与模型组合自动跳过，ID 冲突另行命名。
- API Key 输入隐藏，使用 Windows 用户环境变量；不将 Key 放入进程命令行或 profiles.json。环境变量是本机存储，并非加密保险库。
- 导出可再次导入的配置 JSON，默认且始终不含密钥。
- 查看并恢复由新版创建的 Codex 配置备份；恢复前再次备份当前文件。

切换只修改 `CODEX_HOME/config.toml`，未指定 CODEX_HOME 时使用用户目录下的 `.codex/config.toml`。不会自动结束或重启当前任务；应用后自行关闭并重新打开 Codex。环境变量更改在新进程中生效，必要时退出所有 Codex 进程后从桌面重开。

## 第三方导入格式

支持以下**结构**，不保证所有同名工具的每个版本都兼容：

1. 本工具导出的 JSON；普通配置数组，以及 `profiles` / `providers` 下的数组或字典。
2. Codex `config.toml` 中的 `model_providers`，读取根级 model 和 model_reasoning_effort。
3. 含 `settingsConfig.config`（Codex TOML 字符串）与 `settingsConfig.env` 的导出项，支持外层 `codex.providers`。
4. `.env` 文本：`OPENAI_BASE_URL`、`OPENAI_API_KEY`、`OPENAI_MODEL`。只解析文本，不执行 shell、不展开变量。
5. 单条内联 JSON cURL 请求：通用 `/responses` 示例，以及 DeepSeek 官方 `/chat/completions` 示例。
6. 字段别名：`baseUrl` / `apiHost`、`apiKey`、`envKey`。

导入预览中 API Key 只显示“有/无”。只有勾选“同时保存附带的 API Key”后，才写入独立的新环境变量；不会覆盖已有服务的密钥。默认只导入服务描述。没有密钥时，编辑服务补充后再应用。

不导入 OAuth 会话、浏览器 Cookie、auth.json 或其他工具的登录缓存。未知格式、未经确认的 Chat Completions 协议和不合法地址会报错；需要自定义认证头、查询参数或特殊认证的服务应先人工核对，相关额外字段不会自动迁移。单次导入最多 2 MiB / 200 项。

示例文件见 [examples/provider.json](examples/provider.json)、[examples/codex.toml](examples/codex.toml)、[examples/provider.env](examples/provider.env)。普通示例使用虚构地址；DeepSeek 示例使用其官方地址。所有示例均不附带可用密钥。

## 数据与维护

服务列表保存在程序旁的 `profiles.json`；配置写入前的备份保存在对应文件旁的 `switcher-backups/`。更新时保留 profiles.json、备份和已设置的环境变量。新版不预置任何商业中转服务，也不自动请求第三方网络。

旧记录若包含不合法的密钥变量名或旧接口协议，先在“编辑服务”中修正后再应用或导出。保存其他有效服务时，这些旧记录会原样保留。接口协议修改前需要自行确认服务支持 Responses。

工具用 `switcher_` 前缀管理自己的 provider 表，保留用户其他 provider、工作区与嵌套模型配置。遇到无法安全处理的 TOML 布局会拒绝写入。根级模型名切回官方模式时保留，不会猜测替换模型。

```powershell
python -B -m unittest discover -v
python -B build.py
python -B package_release.py
```

配置字段参考：[OpenAI 官方配置说明](https://developers.openai.com/codex/config-reference)、[高级配置](https://developers.openai.com/codex/config-advanced)。分类为 Responses 配置不代表已通过远端服务的真实请求验证。使用前请确认服务商支持的模型与协议。

本项目为独立工具，不是 OpenAI 官方客户端。当前未指定额外开源许可证。
