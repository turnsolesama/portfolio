# Codex Switcher 2.4.1 验证记录

日期：2026-09-09。Windows x64、Python 3.11、Tkinter。

`python -B -m unittest discover -q`：102 项通过，耗时 24.353 秒。

- 原有100项回归通过。新增正式头部不显示 LOCAL WORKSPACE、演示标记为普通次级文本的隔离测试；即使测试正式头部，也使用模块已绑定的临时演示目录并阻断密钥读取。
- 新图标源稿RGBA，alpha覆盖0..255；只做尺寸和格式转换，外缘真实透明。ICO七个BMP编码尺寸16/24/32/48/64/128/256通过结构检查；四档DPI头图36/45/54/72大小及透明角、实心中心检查通过。
- 根代理实际查看64px PNG，确认箭头轮廓清晰。完整窗口仍仅通过离屏Tk控件几何与样式验证，没有新增截图外观验收。
- 应用和所有弹窗继续通过Windows图标句柄检查、四档DPI/最小尺寸/固定按钮/长内容滚动/文字对比度回归。
- 没有读取真实Codex配置进行测试、应用服务或调用远端API。

以下保留历史记录。

# Codex Switcher 2.4.0 验证记录

日期：2026-09-09。Windows x64、Python 3.11、Tkinter。

`python -B -m unittest discover -q`：100 项通过，耗时 30.919 秒；包括原有 98 项以及 2 项新增视觉布局/状态测试。

- 100% / 125% / 150% / 200% 模拟 DPI 下，主窗口正常和最小尺寸、拖动分栏边界、四类弹窗、底部按钮和长内容独立滚动均通过。
- 分组详情的六个键值字段在四档缩放和最小宽度下自动换行，内容位于各自行内；状态徽标随官方账号/API 服务选择切换。
- 检查实际 ttk 样式解析出的按钮、菜单、下拉箭头、表头、复选框和状态徽标颜色，文字对比度不低于 4.5:1；禁用状态不会被悬停覆盖。
- 原有 cURL、Python、Node.js 静态解析、去重、导入不激活、不读取变量值、不保存默认密钥、配置语义保护等回归全部通过。
- 本轮自动测试全部使用临时演示配置；没有切换用户真实 Codex 或调用 API。
- 原生/浏览器界面查看工具本轮不可用，因此只完成离屏真实 Tk 控件几何与样式验证，未完成实际截图外观验收。没有通过其他屏幕捕获方式绕过该限制。

以下保留历史版本验证记录。

# Codex Switcher 2.3.0 验证记录

日期：2026-09-09。Windows x64、Python 3.11、Tkinter。

`python -B -m unittest discover -q`：98 项通过；包括原有 68 项、新增 28 项 SDK 解析测试、1 项 SDK 粘贴 / 文件导入 UI 测试及 1 项交互状态对比度回归测试。

- 读取 Tk 实际解析的样式颜色，检查普通/主按钮、菜单按钮、下拉框、表头、复选框在默认、悬停、按下+悬停、聚焦、禁用、禁用+悬停状态的文字对比度均不低于 4.5:1；下拉箭头亦通过此检查。非主操作背景始终保持深色，禁用颜色不会被悬停覆盖。

- Python / Node.js 示例导入结果一致，均保留 deepseek-v4-pro、high、DEEPSEEK_API_KEY 与 Responses 服务地址。
- 覆盖 Python 导入别名、异步客户端、常量、字典与 kwargs；Node.js ESM / CommonJS、简单函数与箭头函数包装、对象展开、字符串及注释。
- 覆盖变量引用不读取实际值、API Key 不进入导出、动态参数与重赋值拒绝、别名对象修改、同名导入覆盖、错误信息不包含输入密钥、未知 Chat 服务不猜测转换。
- 在隔离 Tk 窗口完成 Python 粘贴与 Node.js 文件导入；预览模型/推理强度正确，保存后原演示 Codex 配置逐字节不变。原有四档模拟 DPI 布局测试通过。
- 测试只解析示例，不执行 Python / JavaScript 代码、不加载 OpenAI SDK、不发送 API 请求、不更改真实 Codex 配置。

以下保留 v2.2.0 的验证记录。

日期：2026-09-09。环境：Windows x64、Python 3.11、Tkinter。

运行 `python -B -m unittest discover -q`：68 项通过（33 项原核心、23 项 cURL / 推理强度、12 项界面测试）。

- 用户提供的 DeepSeek 官方 cURL 及带 Markdown 链接、转义下划线的版本，均保留模型 deepseek-v4-pro、环境变量 DEEPSEEK_API_KEY 和 high 推理强度；映射到官方 Responses 基址。
- 覆盖 Bash / CMD / PowerShell 续行，curl.exe、常用 data / header 参数、代码块、环境变量写法、通用 Responses 地址、未知 Chat 服务拒绝转换、畸形 JSON 与参数、安全错误信息、禁止执行命令及读取文件引用。
- 推理强度经过 JSON / TOML / 本地服务列表导入导出往返，应用只变更指定根级字段，嵌套项目设置保持原值；去重不覆盖旧配置。
- 界面测试覆盖完整粘贴 → 预览 → 导入 → 编辑 → 重复导入；变量占位符不保存为密钥，真实配置不被应用。解析失败保留输入文字。
- 100% / 125% / 150% / 200% 模拟缩放下，主窗口及四类弹窗的正常/最小尺寸、按钮边界、滚动区域检查通过。修复预览提示与弹窗页脚控件名称冲突。
- 通过新编译的 EXE --demo 实际点击粘贴与导入，看到 DeepSeek / deepseek-v4-pro / Responses / high / DEEPSEEK_API_KEY，导入后列表新增服务，顶部仍为演示原配置。

依据：[DeepSeek 官方首次调用示例](https://api-docs.deepseek.com/zh-cn/)、[DeepSeek Responses 兼容说明](https://api-docs.deepseek.com/zh-cn/guides/responses_api/)、[Codex 配置参考](https://developers.openai.com/codex/config-reference)。文档确认兼容与本地测试不等于使用实际 Key 发起远端调用；本次未调用 DeepSeek API、未切换用户真实 Codex 配置。

以下保留 v2.1.1 的验证记录。

日期：2026-09-08。环境：Windows x64、Python 3.11、Tkinter。

## 自动验证

运行 `python -B -m unittest discover -v`：43 项通过。

- 33 项核心测试：配置语义保留、切换备份与恢复、并发修改保护、导入格式、去重、敏感字段过滤、地址和变量校验，以及旧版不兼容记录的保留和修正。
- 10 项 UI 测试：100% / 125% / 150% / 200% 缩放下的正常与最小窗口尺寸；四类弹窗底部按钮边界；分栏拖动边界；长名称/地址滚动；搜索与选择；唯一副本；粘贴导入不切换配置、不默认保存密钥；空列表的禁用状态；旧版不兼容条目的显示与修复；Windows 原生应用标识及主窗口大小图标、弹窗图标。

任务栏修复通过 `GetCurrentProcessExplicitAppUserModelID` 读取实际进程标识，并通过 `WM_GETICON` 验证原生窗口图标句柄。实现依据：[Microsoft 应用标识说明](https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nf-shobjidl_core-setcurrentprocessexplicitappusermodelid)。
- 导入布局使用 80 条虚构配置与额外字段提示；长字段使用最长接近 500 字符的虚构地址和名称。

## 图形验证

通过 EXE 的 `--demo` 入口打开隔离演示。实际检查了主界面、编辑弹窗和拖动分栏：右侧三个次要操作完整可见，编辑窗口的取消和保存按钮固定在底部。

## 验证范围

所有测试使用临时演示目录与虚构服务，未应用真实 Codex 配置，未读取真实密钥，也未发起第三方 API 请求。自动测试模拟 Tk 的四档缩放；未在四种真实显示器设置上分别操作，也未验证运行中跨显示器切换 DPI。

EXE 是无控制台启动器，发布包需要系统 Python 3.11+（含 Tkinter），或另行提供 `runtime/pythonw.exe`。发布使用程序文件白名单，不包含用户 profiles.json、Codex 配置或备份。
