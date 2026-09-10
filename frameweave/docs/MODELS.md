# 模型、后端与生成控制

FrameWeave 是「本地化 AI 系统」类别中的轻量画布客户端。它连接用户已有的本机 ComfyUI，用画布组织提示词、参考素材、生成任务和结果。模型权重、Python 推理环境和 CUDA 不包含在客户端中。

本文官方资料核查于 2026-09-11。模型能力不等于本客户端已完成全部适配；实际可运行范围取决于已安装后端版本、节点、模型及验证结果。

## 可选模型

| 模型 | 适合的工作 | 初始选择 | 许可证 |
|---|---|---|---|
| MiniMax H3 FL2VA | 文生音视频、首帧或首尾帧控制 | 20 步，短片先验证 | [H3 Community License](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/LICENSE) |
| MiniMax H3 Ref2VA | 多模态参考，控制身份、风格、运动、镜头或声音 | 使用专属 Ref2VA 模型和匹配工作流 | [H3 Community License](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/LICENSE) |
| Krea 2 Turbo | 快速图像生成与风格探索 | 8 步，约 1MP，单张 | [Krea 2 Community License](https://www.krea.ai/krea-2-licensing) |
| SDXL Base 1.0 | 通用图像生成，复用已有 checkpoint 与生态工作流 | 基础模型可独立使用；先跑已有稳定工作流 | [CreativeML Open RAIL++-M](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/blob/main/LICENSE.md) |

FrameWeave 的代码许可与模型许可独立。开放权重不代表所有地区、用途和规模均无条件获准。H3 许可正文包含地域、分发和商业使用条款；Krea 2 许可正文包含商业收入阈值及分发条款；SDXL 也有用途限制。使用者应阅读所选版本的原文。本客户端不提供法律判断，界面保留模型名称和官方许可入口。

## MiniMax H3

MiniMax 官方已发布 H3-Base 的 FL2VA 和 Ref2VA 权重，并提供 ComfyUI 集成入口。基础模型原生输出视频和 32kHz 立体声。官方完整系统还包含 Context-IR 和 Regenerate-2K；它们没有包含在已开放的本地基础模型中，因此不能把基础本地生成称作已复现官方完整 2K 流程。

Comfy 官方文档要求 ComfyUI 0.30.0 或更高。客户端使用后端实际注册的节点和参数检查能力；仅有版本号或模型文件不代表工作流可运行。

### 模型配套

| 角色 | 当前 Comfy 官方示例文件 |
|---|---|
| FL2VA 主模型 | `minimax_h3_fl2va_pruned_int8_convrot.safetensors` |
| Ref2VA 主模型 | `minimax_h3_ref2va_pruned_int8_convrot.safetensors` |
| 文本编码器 | `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` |
| 视频 VAE | `minimax_h3_video_vae_fp16.safetensors` |
| 音频 VAE | `minimax_h3_audio_vae_fp32.safetensors` |

已有的非 pruned INT8、其他官方量化格式可以继续由兼容后端使用，不应只为名称变化覆盖原模型。FL2VA 与 Ref2VA 使用不同主模型；不使用的模式无需下载另一套主模型。

精确大小可从 [Comfy H3 官方模型仓库](https://huggingface.co/Comfy-Org/MiniMax-H3/tree/main) 查看。核查时，pruned INT8 单主模型为 20,970,379,616 字节，NVFP4 文本编码器为 15,687,142,551 字节，视频 VAE 为 5,207,808,496 字节，音频 VAE 为 605,254,808 字节。客户端安装包大小与这些外置模型大小分别计算。

### 分辨率、时间与参考控制

- 原生 16:9 可设置为 1344×768，尺寸按 32 对齐。低清预演可先用更小的对齐尺寸；这只是工程预设，不保证与原生分辨率同质。
- 输出以 24fps 运行，Comfy 原生节点采用 `17k+5` 帧数网格，默认 124 帧约 5.17 秒。以提交后的真实帧数和成片时长为准。
- 首尾帧用于约束开头与结尾。Ref2VA 则通过明确的参考角色和提示词关系，影响人物、风格、镜头或声音；二者不能互换。
- 官方 Ref2VA 总体规范包括最多 9 张图片、3 段视频、3 段音频，混合输入最多 12 个文件，并对参考时长有限制。客户端某一版本支持的输入数可能更少，不应把模型上限当作界面承诺。
- 高阶的多时刻 Guide、控制视频、局部重绘与延长需要相应节点和工作流。初版可通过 Comfy API 格式工作流扩展；没有适配和真实验证的控制项不宣称已验收。

### 步数与 Turbo

Comfy 官方基本流程默认 20 步；25 步可作为更重视运动质量的比较选项。Turbo 会改变质量与速度的取舍，必须使用对应模型和 LoRA：

| 模式 | 配套 LoRA | Turbo 步数 |
|---|---|---|
| FL2VA | `minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors` | 8 |
| Ref2VA | `minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors` | 4 |

降低普通模型的步数不等于启用 Turbo。初版若没有专门的 Turbo 配置控件，应导入已验证且配套完整的 API 工作流。官方文档提示 Turbo 的声音和运动质量可能略有下降；不要把少步数设为所有任务的质量优选。

来源：[MiniMax 官方仓库](https://github.com/MiniMax-AI/MiniMax-H3)、[Comfy H3 概览](https://docs.comfy.org/tutorials/video/minimax/minimax-h3)、[Comfy H3 原生工作流与 Turbo](https://docs.comfy.org/tutorials/video/minimax/minimax-h3-native)。

## Krea 2 与 SDXL

Krea 2 RAW 是未蒸馏基础模型，官方建议用于训练和 LoRA；Turbo 是 8 步推理模型。官方直接推理示例采用 CFG 0.0、mu 1.15，这些参数应按具体后端节点的语义匹配，不能机械套用任意通用采样器。Krea 2 Turbo 建议先生成单张 1024×1024 图像，然后再增加面积；2MP 也不等于 2048×2048。

Comfy 官方 Krea 2 通用建议采用 `krea2_turbo_fp8_scaled.safetensors`、`qwen3vl_4b_fp8_scaled.safetensors` 与 `qwen_image_vae.safetensors`。NVFP4、INT8 等格式是否更合适，取决于 GPU 和推理软件栈。风格参考还需要匹配的参考条件与专属 LoRA；单纯上传图片不表示此控制已生效。

SDXL Base 官方模型可以独立运行，Refiner 是可选组合。客户端提供基础 checkpoint 流程或 API 工作流接入；社区 checkpoint、LoRA 和扩展各有自己的来源与许可，不由 SDXL Base 的许可统一覆盖。

来源：[Krea 官方仓库](https://github.com/krea-ai/krea-2)、[Comfy Krea 2 指南](https://docs.comfy.org/tutorials/image/krea/krea-2)、[SDXL 官方模型卡](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0)。

## 速度、质量和可控性

客户端负责减少重复操作、检查依赖、保存参数及追踪任务。推理速度和生成质量主要由模型、量化、推理内核、显存/内存、分辨率、帧数和采样流程决定。界面流畅不能作为模型加速证据。

对于 16GB 级显卡，H3 单主模型文件本身就可能超过显存，需要后端进行 CPU offload 等内存管理；文件大小也不等于运行峰值显存。先以单任务、短片、固定种子验证，再增加长度和画面面积。Sage Attention、NVFP4 或 Turbo 只在软件版本兼容且已有 A/B 结果时作为明确优化；客户端不自动改动现有生产环境。

建议对同一镜头记录：后台版本、工作流、模型与量化、种子、真实分辨率/帧数/步数、加载耗时、生成耗时、总耗时、峰值显存、缓存状态和结果。对同一组镜头检查人物一致性、动作完成度、声音同步及文本可读性。速度预演、平衡出片、质量优先应为可比较的预设，不能给所有用户一个固定性能数字。

## 依赖检查和初版边界

- 缺失检查按当前模式实际使用的节点和模型进行。后端可达、节点已注册、文件存在、safetensors 结构通过、SHA-256 匹配和真实生成完成是不同验证层级。
- 初版文件检查为有界的 safetensors 头、张量范围与文件长度检查，**没有完成全文件 SHA-256 校验**。同名和正确结构不能证明官方来源、完整权重内容或推理成功。
- 修复提示词可复制，用于向 AI 说明缺失依赖与验证要求。AI 的建议不自动执行；下载前核查官方来源和精确大小，超过 50MiB 先确认，超过 100MiB 优先断点续传。
- 初版后端连接限于本机回环地址，不包含远程云服务凭据或托管。客户端不附模型，也不自动安装或替换 ComfyUI。
- 导入的 Comfy 工作流必须是 `/prompt` 所用的 **API 格式**。普通画布 JSON 的 `nodes/links` 结构不能原样作为执行图提交。
- 协议测试和模拟后端只证明软件行为。真实 GPU 图片生成、音视频生成与播放须单独验证；发行说明应明确列出已经完成与尚未完成的实测。

来源：[Comfy HTTP API](https://docs.comfy.org/development/comfyui-server/comms_routes)、[Comfy 消息协议](https://docs.comfy.org/development/comfyui-server/comms_messages)。
