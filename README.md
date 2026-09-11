![本地创作工具集](docs/assets/portfolio.svg)



# 本地创作系统与工具



项目按本地化 AI 系统、资产管理系统、工具类组织。每个软件保留独立的功能说明与下载包，可按需要单独使用。分类用于导航，现有源码目录、历史版本和下载地址继续保留。



**[帧织：AI 生成画布](frameweave/)** · **[映序：视频项目](yingxu/)** · **[AI Hub：模型资产](ai-hub/)** · **[Codex Switcher：服务配置](codex-switcher/)** · **[FlowSwitch：网络线路](proxy-switch/)** · **[拾影：视频保存](video-catch/)**



## 项目分类



| 分类 | 项目 | 主要用途 |

| --- | --- | --- |

| **本地化 AI 系统** | **[FrameWeave 帧织](frameweave/)** | 专业画布、H3 视频与图片生成控制、本地环境缺失检查 |

| **资产管理系统** | **[映序 YingXu](yingxu/)**、**[AI Hub](ai-hub/)** | 作品项目、文档、素材、分镜与本地模型资产管理 |

| **工具类** | **[Codex Switcher](codex-switcher/)**、**[流向 FlowSwitch](proxy-switch/)**、**[拾影 VideoCatch](video-catch/)** | Codex 服务配置、程序网络分流、网页视频发现与保存 |



## 选择你的工作台



| 你现在想做什么 | 对应项目 | 当前版本 | 下载 Windows 程序包 |

| --- | --- | --- | --- |

| 编排提示词与参考图，控制 H3 视频和图片生成，检查本地缺失项 | **[FrameWeave 帧织](frameweave/)** | 0.2.0 | **[下载帧织 · 9.12 MiB](https://raw.githubusercontent.com/turnsolesama/portfolio/main/frameweave/releases/FrameWeave-v0.2.0-Windows-x64.zip)** |

| 写剧本、管分镜，按集数整理角色、场景和生成结果 | **[映序 YingXu](yingxu/)** | 0.3.8 | **[下载映序](https://github.com/turnsolesama/portfolio/releases/download/yingxu-v0.3.8/YingXu-v0.3.8-Windows-x64.zip)** |

| 查模型与 LoRA，用分类、图库和路径记录整理 AI 资产 | **[AI Hub](ai-hub/)** | 2.5.0 | **[下载 AI Hub · 1.04 MiB](https://raw.githubusercontent.com/turnsolesama/portfolio/main/ai-hub/releases/AI-Hub-v2.5.0-Windows-x64.zip)** |

| 导入 API 示例，管理服务、密钥变量和 Codex 配置切换 | **[Codex Switcher](codex-switcher/)** | 2.4.1 | **[下载切换器 · 327 KiB](https://raw.githubusercontent.com/turnsolesama/portfolio/main/codex-switcher/releases/Codex-Switcher-v2.4.1-Windows-x64.zip)** |

| 管理已有代理、统一出口，给程序设置专用线路 | **[流向 FlowSwitch](proxy-switch/)** | 3.7.1 | **[下载 FlowSwitch · 68.1 MiB](https://raw.githubusercontent.com/turnsolesama/portfolio/main/proxy-switch/releases/FlowSwitch-v3.7.1-Windows-x64.zip)** |

| 选择浏览器视频页面，发现媒体并保存到本地 | **[拾影 VideoCatch](video-catch/)** | 0.3.0 | **[下载程序 · 96.3 MiB](https://github.com/turnsolesama/portfolio/releases/download/videocatch-v0.3.0/VideoCatch-v0.3.0-Windows-x64.zip)** · **[独立浏览器扩展 · 20.6 KiB](https://github.com/turnsolesama/portfolio/releases/download/videocatch-v0.3.0/VideoCatch-Extension-v0.3.0.zip)** |



每个 ZIP 只包含对应软件。下载链接直接取得压缩包；完整解压后再运行，保留包内文件夹。各项目页面提供源码说明、校验值和版本记录；映序的程序包已包含源码。



## 本地化 AI 系统



### FrameWeave 帧织



**把提示词、参考图、视频生成和结果，放进一张可控制的专业画布。**



- 无限画布、框选与连线、撤销重做、JSON 导入导出、提示词一键复制。

- 工作流包：导入 ComfyUI API 图或封装当前生成节点，开放提示词、尺寸、种子和参考图，填表即可生成图片或视频。

- 自动发现本机后端、安装目录与显卡，按完整工作流识别节点和模型缺失，区分“缺失”与“暂不可检查”，复制脱敏修复说明。

- H3 视频与 Krea 2 / SDXL 图片控制，支持队列、结果大图和视频预览；原创深墨蓝与青绿界面，无广告。

- Windows 程序约 9.04 MiB，复用系统浏览器及已有本地 ComfyUI，不捆绑模型、CUDA 或 PyTorch。



0.2.0 通过 109 项 Python、16 项 Node、源码与 EXE 各 17 项界面检查，以及打包版 5 项真实表单与媒体检查；已实际生成 Krea 图片、H3 文生视频和首帧图生视频。生成仍需要已有本地 ComfyUI，未实现自动安装、独立推理引擎或完整剪辑时间线。



[进入帧织 →](frameweave/) · [工作流包](frameweave/docs/WORKFLOW_PACKAGES.md) · [环境检查](frameweave/docs/ENVIRONMENT.md) · [模型与参数](frameweave/docs/MODELS.md) · [验证记录](frameweave/docs/VALIDATION.md) · [开发记录](frameweave/docs/DEVELOPMENT_LOG.md)



## 资产管理系统



### 映序 YingXu



**把一部作品的剧本、素材和制作进度放在同一个项目里。**



- **长期项目库**：用多层分类文件夹归类项目，侧栏仅保留当前与最近项目。逻辑分类不会搬动磁盘素材。

- **设置与桌面**：删除确认、托盘与播放偏好可配置；托盘双击唤回，从 Windows“打开方式”直接打开本地文件，支持的文稿可编辑保存。

- **项目与分类**：剧本、分镜、角色、场景、道具、参考、白模预演、生成素材和交付。支持多层文件夹，用“跨集共用 / 第 1 集 / 第 2 集”整理系列作品。

- **文件工作区**：多标签打开、Markdown/文本编辑、Word 普通段落编辑、图片与音视频预览。支持拖入、移动、多选、改名，以及右键打开所在文件夹。

- **拖动归类**：项目库项目行可拖到其他分类，素材组成员行可拖到同项目其他组；拖出弹窗到空白区域用于未分类或移出组，Esc 取消，磁盘原文件保持不变。

- **标题改名与删除**：点击项目文件标题打开确认改名弹窗，输入仅名称，保留扩展名与未保存正文；选中素材后按 Delete 移入映序回收站，素材选择框保持焦点时也可使用，沿用删除确认设置。编辑标题、正文或其他输入框时只删除文字。

- **全局搜索**：Ctrl+K 或顶栏入口跨项目查找项目、文件与已注册 SKILL，显示来源、摘要和分页；Ctrl+F 继续搜索当前页面。

- **截图与素材组**：按需截取鼠标所在屏幕区域，复制图片并保存项目附件；逻辑素材组跨分类整理文件，保留原位置。资源区空白拖框选择本页可见卡片，文稿独立标题仅显示名称、不含扩展名。

- **Markdown 实时预览**：可编辑文稿与自建 SKILL 默认边写边看排版，当前段落显示源码；源码、双栏与只读预览继续保留。

- **制作管理**：镜号、时长、提示词、标签、待审核等状态，连接角色与对应镜头；删除确认、回收站和恢复保护整理过程。

- **SKILL 与 AI 协作**：集中查看与编写技能，给项目绑定规范；生成普通 Markdown/JSON 交接文件，便于 Codex 等工具读取当前进度。



浅色中文界面，MIT 许可。专注项目管理、文档编辑与素材组织；剪辑时间线、完整 Word 排版和内嵌 3D 编辑暂未提供。



[进入映序 →](yingxu/) · [详细功能](yingxu/docs/功能指南.md) · [安装与运行](yingxu/docs/安装与运行.md)



### AI Hub



**围绕“用什么模型、素材在哪里”建立本地资产目录。**



- 按图片、视频、语言、音频等用途找模型；LoRA 支持风格、角色、光照、细节等多选分类。

- 查看模型架构、训练底模、触发词候选、评分、备注和来源；支持手动与批量调整分类。

- 图库提供搜索、模型引用筛选、大图查看和密度切换；资料与工作流可记录路径、依赖与说明。

- 统一分类视图与人工覆盖，区分所属范围、模型角色、创作用途和兼容架构；已有模型库只预览，散落资产区可按确认建立硬链接入口。

- 2.5 新增项目、运行和知识登记，记录当前说明与交付位置；工作流区分路径检查、历史通过与当前复验，证据变化后降低有效状态。



[进入 AI Hub →](ai-hub/) · [分类规则](ai-hub/docs/CLASSIFICATION.md) · [项目与证据登记](ai-hub/docs/REGISTRY.md) · [安全区整理](ai-hub/docs/SAFE_ZONE.md)



## 工具类



### Codex Switcher



**把多组 API 服务配置整理好，再手动应用到 Codex。**



- 新增、编辑、复制、搜索和移除服务；区分当前使用、未应用和需要修正的配置。

- 本地解析 JSON、TOML、env、cURL，以及受支持的 Python/Node.js SDK 示例，先预览再导入。

- 在官方登录模式与第三方 Responses API 配置间切换；应用前检查并备份，支持恢复。

- 密钥使用 Windows 用户环境变量，导出始终不含密钥；示例导入不执行代码，也不调用 API。



这是独立配置工具。导入或保存配置不会自动激活服务，应用后需要重新打开 Codex；服务商是否支持对应协议仍需确认。



[进入 Codex Switcher →](codex-switcher/) · [支持的导入格式](codex-switcher/#第三方导入格式) · [验证记录](codex-switcher/TEST_REPORT.md)



### 流向 FlowSwitch



**整理已有代理入口，观察软件的连接实际走向。**



- 添加 HTTP / SOCKS5 入口、发现后台代理、检测入口并保存可恢复的设置。

- 统一切换系统代理与相关用户环境变量，撤销本工具管理的程序专用线路。

- 自带独立分流内核，使用固定本地入口并按 EXE 路径选择线路；上游失效时按备用顺序接替。

- 关闭窗口驻留系统托盘，异常内核有限重启；保留有效备用出口，停止服务时先恢复仍归属本会话的网络设置。

- Google 登录诊断分开显示本地入口、代理握手和 HTTPS 响应，提示旧代理缓存与重开步骤。

- 分开显示规则载入、进程身份和 TCP 观察结果；软件升级后可核对并修复旧路径，保留有效备用线路。
- 读取失败显示为未知，主程序与有独立规则的子程序分别核对；先预览再确认重连所选程序的旧连接。



软件不提供 VPN、订阅或节点。完整包自带运行组件；按程序分流要求流量实际进入独立入口，不会自动开启 TUN 或退出其他应用。



[进入 FlowSwitch →](proxy-switch/) · [快速开始](proxy-switch/#快速开始) · [运行要求](proxy-switch/#运行要求)



### 拾影 VideoCatch



**选定正在播放的网页，把可获取的视频保存到本地。**



- Chrome / Edge 扩展连接桌面程序，可选择前台或后台标签页，使用「开始监听」「停止监听」控制来源。

- 普通文件直接下载；B站成对音视频轨道、HLS/DASH 分段无转码合并；YouTube 自带 JavaScript 解析组件。

- 顶部提示当前操作步骤，支持直接粘贴网页分享链接；浏览器能播放但下载超时时，可检测已有本机代理。

- 自带 Python、yt-dlp、FFmpeg 与 Deno。新版图标，程序包和浏览器扩展包独立下载。



**扩展需单独放在固定目录，导入浏览器后不要移动或删除。** 桌面程序与扩展配对后：选中页面 → 开始监听 → 回网页刷新播放 → 选中右侧视频保存。扩展不能独立下载；网站验证和访问限制仍可能导致失败。



[进入拾影 →](video-catch/) · [独立扩展与程序下载](video-catch/releases/) · [验证记录](video-catch/TEST-REPORT.md)



## 下载以后



| 软件 | 双击入口 | 主要运行要求 |

| --- | --- | --- |

| 映序 | `YingXu.exe` | Windows 10 22H2 / Windows 11 x64；完整包自带 Python、图片与视频处理组件和 WebView2 |

| AI Hub | `AI Hub.exe` | Windows x64、Python 3.9+、.NET Framework 4.8+、WebView2 Runtime |

| Codex Switcher | `Codex Switcher.exe` | Windows x64、Python 3.11+（含 Tkinter）、.NET Framework 4.x |

| FlowSwitch | `FlowSwitch.exe` | Windows 10 1809+ / 11 x64、PowerShell 5.1、.NET Framework 4.x、curl；自带 Node.js 和独立内核 |

| 拾影 VideoCatch | `VideoCatch.exe` | Windows 10 / 11 x64；自带运行组件，监听网页需 Chrome / Edge 120+ 扩展 |



这些 EXE 是桌面启动入口，需要保留完整程序包，并满足各自的运行条件。映序 0.3.8 与 FlowSwitch 3.7.1 完整包已自带主要运行组件；各软件请按自己的说明配置。各包不包含模型权重或代理服务。



如果 GitHub 页面显示 **Error loading page**，可直接使用上表的下载链接；已经下载但不能启动时，请查看对应项目的运行要求。版本升级、数据保留和诊断步骤都放在各软件的独立说明中。



## 源码与许可



仓库按项目发布源码、程序包、图标和公开演示资源，不包含个人图集、模型权重、密钥、本机数据库或私人配置。各工具可独立下载，本仓库不设置订阅付费入口。



- **映序、FlowSwitch** 的原创代码使用各自随附的 MIT 许可，第三方组件遵循各自声明。

- **AI Hub、Codex Switcher、拾影 VideoCatch** 当前公开源码，但尚未指定额外开源许可证；请以项目内的许可说明为准。



各款软件的用途和运行条件相互独立，可以根据工作需要组合使用。



