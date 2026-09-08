# Codex Switcher

一个用于 Windows 的本地 Codex API 服务配置工作台。炭灰界面、服务搜索、当前模式、密钥状态、详情面板和独立 EXE 启动入口。

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
2. Codex `config.toml` 中的 `model_providers`，读取根级 model。
3. 含 `settingsConfig.config`（Codex TOML 字符串）与 `settingsConfig.env` 的导出项，支持外层 `codex.providers`。
4. `.env` 文本：`OPENAI_BASE_URL`、`OPENAI_API_KEY`、`OPENAI_MODEL`。只解析文本，不执行 shell、不展开变量。
5. 字段别名：`baseUrl` / `apiHost`、`apiKey`、`envKey`。

导入预览中 API Key 只显示“有/无”。只有勾选“同时保存附带的 API Key”后，才写入独立的新环境变量；不会覆盖已有服务的密钥。默认只导入服务描述。没有密钥时，编辑服务补充后再应用。

不导入 OAuth 会话、浏览器 Cookie、auth.json 或其他工具的登录缓存。未知格式、Chat Completions 协议和不合法地址会报错；需要自定义认证头、查询参数或特殊认证的服务应先人工核对，相关额外字段不会自动迁移。单次导入最多 2 MiB / 200 项。

示例文件见 [examples/provider.json](examples/provider.json)、[examples/codex.toml](examples/codex.toml)、[examples/provider.env](examples/provider.env)。示例只有虚构地址，不附带可用密钥。

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
