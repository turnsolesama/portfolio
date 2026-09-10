"""Bounded read-only model checks. A header check is never a checksum claim."""

import json
import math
import struct
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from .workflows import (_check_family, _check_json_limits, _expanded_inputs, _model,
                        _number, _options, _reference_names, _reference_roles,
                        _spec, compile_workflow, validate_prompt)


def safe_relative(name):
    if not isinstance(name, str) or not name or len(name) > 1024:
        raise ValueError("文件名无效")
    name = name.replace("\\", "/")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in ("..", ".") for part in name.split("/")) or ":" in name or "\x00" in name:
        raise ValueError("不可使用绝对路径或越界路径")
    return str(path)


def inspect_safetensors(path):
    path = Path(path)
    size = path.stat().st_size
    if size < 10:
        return "error", "文件为空或截断", size
    with path.open("rb") as stream:
        header_length = struct.unpack("<Q", stream.read(8))[0]
        if not 2 <= header_length <= min(16 * 1024 * 1024, size - 8):
            return "error", "safetensors 头长度无效，可能下载不完整", size
        try:
            header = json.loads(stream.read(header_length))
        except (ValueError, UnicodeError):
            return "error", "safetensors 头不是有效 JSON", size
    if not isinstance(header, dict):
        return "error", "safetensors 头类型无效", size
    ranges = []
    tensor_count = 0
    unknown_types = set()
    widths = {"BOOL": 1, "U8": 1, "I8": 1, "F8_E4M3": 1, "F8_E5M2": 1, "F8_E8M0": 1,
              "I16": 2, "U16": 2, "F16": 2, "BF16": 2, "I32": 4, "U32": 4, "F32": 4,
              "I64": 8, "U64": 8, "F64": 8, "F8_E4M3FN": 1, "F8_E5M2FNUZ": 1}
    for key, tensor in header.items():
        if key == "__metadata__":
            continue
        if not isinstance(tensor, dict):
            return "error", "张量描述无效", size
        offsets, shape = tensor.get("data_offsets"), tensor.get("shape")
        if (not isinstance(offsets, list) or len(offsets) != 2
                or any(type(v) is not int for v in offsets)
                or not 0 <= offsets[0] <= offsets[1] <= size - header_length - 8
                or not isinstance(shape, list) or any(type(v) is not int or v < 0 for v in shape)):
            return "error", "张量数据越界，文件可能截断", size
        dtype = tensor.get("dtype")
        if not isinstance(dtype, str) or not dtype:
            return "error", "张量 dtype 类型无效", size
        width = widths.get(dtype)
        if width is None:
            unknown_types.add(dtype)
        if width and math.prod(shape) * width != offsets[1] - offsets[0]:
            return "error", "张量形状与数据长度不一致", size
        ranges.append(tuple(offsets))
        tensor_count += 1
    if not tensor_count:
        return "error", "文件没有张量数据", size
    cursor = 0
    for start, end in sorted(ranges):
        if start != cursor:
            return "error", "张量数据重叠或存在空洞", size
        cursor = end
    if cursor != size - header_length - 8:
        return "error", "文件长度与张量目录不一致", size
    if unknown_types:
        return "warning", "数据边界检查通过，但存在未支持的 dtype；不能确认完整张量结构，未做 SHA-256 校验", size
    return "ok", f"结构与长度检查通过，{tensor_count} 个张量；未进行全文件 SHA-256 校验", size


def resolve_model(roots, name, role):
    name = safe_relative(name)
    role_dirs = {"checkpoint": ["checkpoints"], "dit": ["diffusion_models", "unet"],
                 "text_encoder": ["text_encoders", "clip"], "vae": ["vae"],
                 "audio_vae": ["vae"], "lora": ["loras"]}.get(role, [])
    for base in roots:
        root = Path(base).expanduser().resolve()
        for rel in [name] + [f"{folder}/{name}" for folder in role_dirs]:
            candidate = (root / rel).resolve()
            # Deliberate user-selected model roots may contain compatibility junctions.
            # Only an enumerated backend filename is checked; no directory walking.
            if candidate.is_file():
                return candidate
    return None


COMFY_DOCS = "https://docs.comfy.org/installation/system_requirements"
H3_DOCS = "https://docs.comfy.org/tutorials/video/minimax/minimax-h3-native"
KREA_DOCS = "https://docs.comfy.org/tutorials/image/krea/krea-2"
STATES = ("ok", "missing", "error", "warning", "unknown")
ROLES = ("checkpoint", "dit", "text_encoder", "vae", "audio_vae", "lora")
MODEL_FIELDS = {"ckpt_name": "checkpoint", "unet_name": "dit", "clip_name": "text_encoder",
                "vae_name": "vae", "lora_name": "lora", "model_name": "model"}
MODEL_SUFFIXES = (".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".gguf")


def _request(request):
    if not isinstance(request, dict):
        raise ValueError("检测请求必须是对象")
    _check_json_limits(request)
    kind = request.get("kind", "h3_t2v")
    if not isinstance(kind, str) or kind not in {"h3_t2v", "h3_i2v", "h3_ref", "krea", "sdxl", "api"}:
        raise ValueError("不支持的检测模式")
    models = request.get("models", {})
    if not isinstance(models, dict) or any(key not in ROLES for key in models):
        raise ValueError("models 必须是支持的模型角色对象")
    if any(value is not None and (not isinstance(value, str) or len(value) > 1024) for value in models.values()):
        raise ValueError("模型名称必须是 0–1024 字符的文本")
    for key in ("positive", "negative", "sampler", "scheduler", "lora"):
        if key in request and (not isinstance(request[key], str) or len(request[key]) > (100000 if key in {"positive", "negative"} else 1024)):
            raise ValueError("提示词、采样选项和 LoRA 名称必须是长度受限的文本")
    refs = _reference_names(request)
    if len(refs) > 9 or any(len(ref) > 1024 for ref in refs):
        raise ValueError("参考图最多 9 张，每个相对名称不超过 1024 字符")
    _reference_roles(request, kind, refs)
    _number(request, "denoise", 1, 0, 1)
    for key, minimum, maximum, integer in (("width", 32, 8192, True), ("height", 32, 8192, True),
            ("steps", 1, 1000, True), ("seed", 0, 2**64 - 1, True), ("cfg", 0, 100, False),
            ("seconds", 5 / 24, 150, False), ("fps", 1, 120, False),
            ("shift_video", .01, 100, False), ("shift_audio", .01, 100, False), ("lora_strength", -10, 10, False)):
        if key in request:
            _number(request, key, minimum, minimum, maximum, integer)
    if kind != "api":
        return kind, models, refs, None
    prompt = request.get("prompt", request.get("workflow", {}))
    if isinstance(prompt, dict) and isinstance(prompt.get("prompt"), dict) and "class_type" not in prompt["prompt"]:
        prompt = prompt["prompt"]
    if not isinstance(prompt, dict) or len(prompt) > 1000:
        raise ValueError("API 图必须是最多 1000 个节点的对象")
    for key, node in prompt.items():
        if not isinstance(key, str) or not key or len(key) > 200 or not isinstance(node, dict):
            raise ValueError("API 节点 ID 或节点对象无效")
        if not isinstance(node.get("inputs"), dict):
            raise ValueError("API 节点必须包含 inputs 对象")
        if not isinstance(node.get("class_type"), str) or not 1 <= len(node["class_type"]) <= 200:
            raise ValueError("API 节点类型必须是 1–200 字符的文本")
    return kind, models, refs, prompt


def _selections(kind, models, request, model_catalog):
    """Use the compiler's model chooser, including its preferred quantization."""
    available = {role: [name for name in model_catalog.get(role, []) if isinstance(name, str)] for role in ROLES}
    h3 = kind.startswith("h3_")
    lora = request.get("lora") or models.get("lora")
    if kind == "api":
        return []
    choices = [("checkpoint", ("sdxl", "_xl", "xl_", "xl.", "pony", "illustrious", "illust"), ())] if kind == "sdxl" else [
        ("dit", ("ref2va",) if kind == "h3_ref" else ("fl2va",) if h3 else ("krea2",), ("pruned",) if h3 and not lora else ()),
        ("text_encoder", ("minimax_h3",) if h3 else ("qwen3vl_4b",), ("nvfp4",) if h3 else ()),
        ("vae", ("minimax_h3_video_vae",) if h3 else ("qwen_image_vae",), ())]
    if h3:
        choices.append(("audio_vae", ("minimax_h3_audio_vae",), ()))
    elif kind == "sdxl" and models.get("vae"):
        choices.append(("vae", (), ()))
    selected = []
    for role, tokens, preferred in choices:
        try:
            name = _model(models, role, available, tokens, preferred)
        except ValueError:
            name = models.get(role)
        selected.append((role, name, available[role]))
    if lora:
        selected.append(("lora", lora, available["lora"]))
    return selected


def _dependencies(kind, request, refs, selections, info):
    """Mirror compile_workflow branches; never infer image dependencies for API graphs."""
    if kind == "api":
        return []
    h3 = kind.startswith("h3_")
    needed = {"CheckpointLoaderSimple"} if kind == "sdxl" else {"UNETLoader", "CLIPLoader", "VAELoader"}
    models = dict((role, name) for role, name, _ in selections)
    if kind == "sdxl" and models.get("vae"):
        needed.add("VAELoader")
    if models.get("lora"):
        if kind == "sdxl":
            needed.add("LoraLoader")
        else:
            quantized = any(token in (models.get("dit") or "").lower() for token in ("int8", "fp8", "nvfp4", "gguf"))
            needed.add("LoraLoaderBypassModelOnly" if quantized and "LoraLoaderBypassModelOnly" in info else "LoraLoaderModelOnly")
    if refs:
        needed.add("LoadImage")
    negative = request.get("negative", "").strip()
    if h3:
        needed |= {"MiniMaxH3ReferenceToVideo" if kind == "h3_ref" else "MiniMaxH3ImageToVideo", "CreateVideo", "SaveVideo"}
        if request.get("sampler") == "dual_clock_euler":
            needed |= {"MiniMaxH3DualClockSamplerT8", "RandomNoise", "BasicGuider", "SamplerCustomAdvanced"}
        else:
            needed |= {"MiniMaxH3SigmaShift", "KSampler", "CLIPTextEncode" if negative else "ConditioningZeroOut"}
        decode = {"LTXVSeparateAVLatent", "VAEDecode", "VAEDecodeAudio"}
        needed |= decode if decode <= info.keys() else {"MiniMaxH3AVDecodeT8"}
    else:
        needed |= {"KSampler", "VAEDecode", "SaveImage"}
        needed |= {"Krea2OstrisEditModelPatch", "TextEncodeKrea2OstrisEdit"} if kind == "krea" and refs else {"CLIPTextEncode"}
        needed.add("ConditioningZeroOut" if kind == "krea" and not negative else "CLIPTextEncode")
        if refs and (kind == "sdxl" or request.get("denoise", 1) < 1):
            needed |= {"ImageScale", "VAEEncode"}
        else:
            needed.add("EmptySD3LatentImage" if kind == "krea" else "EmptyLatentImage")
    return sorted(needed)


def _api_models(prompt, info):
    """Inspect actual loader enum fields, retaining no prompt/media fields."""
    result = []
    for node in prompt.values():
        schema = info.get(node["class_type"], {})
        fields, _ = _expanded_inputs(schema, node["inputs"])
        for field, value in node["inputs"].items():
            if not isinstance(value, str) or field not in fields:
                continue
            kind, meta = _spec(fields[field])
            options = kind if isinstance(kind, list) else meta.get("options", []) if kind == "COMBO" else []
            if not isinstance(options, list):
                continue
            # Generic custom loaders are recognized from declared model-file choices.
            role = MODEL_FIELDS.get(field)
            if role is None and any(isinstance(option, str) and option.lower().endswith(MODEL_SUFFIXES) for option in options):
                role = "model"
            if role and (isinstance(kind, list) or kind == "COMBO"):
                result.append((role, value, options))
    return result


def diagnose(settings, object_info, status, request, model_catalog, environment=None):
    """Readiness evidence, not a GPU execution, installation or quality guarantee."""
    if not all(isinstance(value, dict) for value in (settings, object_info, status, model_catalog)):
        raise ValueError("设置、节点能力和状态必须是对象")
    if environment is not None and not isinstance(environment, dict):
        raise ValueError("环境快照必须是对象")
    kind, models, refs, prompt = _request(request)
    roots = settings.get("model_roots", [])
    if not isinstance(roots, list) or len(roots) > 32 or any(not isinstance(root, str) or len(root) > 4096 for root in roots):
        raise ValueError("模型目录应为最多 32 个路径的列表")
    online = status.get("online") is True
    info = object_info if online else {}
    checks, repair_rows = [], []
    docs = H3_DOCS if kind.startswith("h3_") else KREA_DOCS if kind == "krea" else COMFY_DOCS

    def add(key, category, name, state, detail, steps=(), url=None, repair=None):
        action = {"label": "查看修复步骤" if state != "ok" else "查看检查说明", "steps": list(steps)}
        if url:
            action["url"] = url
        checks.append({"id": key, "category": category, "name": name, "status": state,
                       "detail": detail, "action": action})
        if state != "ok":
            # Only fixed, application-owned strings enter the clipboard. Never copy
            # request values, schema filenames, environment text or exception text.
            repair_rows.append(f"- {category} [{state}]：{repair or detail}")

    add("backend.connection", "backend", "推理后端", "ok" if online else "unknown",
        "ComfyUI HTTP 服务已响应" if online else "服务尚未连接；不能据此断言节点、PyTorch 或模型未安装",
        ("检查自动发现的本机服务候选，确认它是目标 ComfyUI。", "若服务已安装但未运行，使用原有启动方式启动，再重新检查。"), COMFY_DOCS)

    env_checks = environment.get("checks", []) if environment else []
    if not isinstance(env_checks, list) or len(env_checks) > 256:
        raise ValueError("环境检查列表无效")
    for index, item in enumerate(env_checks):
        if not isinstance(item, dict) or item.get("status") not in STATES:
            continue
        # Presentation may show locally discovered evidence. Exported advice is
        # independent of all snapshot strings, including filenames/arguments.
        fallback = "自动发现已取得证据；查看环境发现面板了解本机详情。" if item["status"] == "ok" else "自动发现存在未满足或未确认的环境条件；查看环境发现详情。"
        title = item.get("name") if isinstance(item.get("name"), str) else "自动发现检查 " + str(index + 1)
        detail = item.get("detail") if isinstance(item.get("detail"), str) else fallback
        add(f"environment.{index}", "environment", title[:200], item["status"], detail[:2000],
            ("确认自动发现对应的是当前选中的推理环境。", "结合后端 system_stats 和官方安装说明核对；不迁移现有资产。"), COMFY_DOCS, repair=fallback)

    system = status.get("system", {}) if online else {}
    system = system if isinstance(system, dict) else {}
    torch_known = isinstance(system.get("pytorch_version"), str) and bool(system["pytorch_version"].strip())
    devices = status.get("devices", []) if online else []
    devices = devices if isinstance(devices, list) else []
    cuda = any(isinstance(device, dict) and device.get("type") == "cuda" for device in devices)
    add("runtime.pytorch", "runtime", "PyTorch 推理运行时", "ok" if torch_known else "unknown",
        "当前后端报告了 PyTorch 版本" if torch_known else "当前后端未提供 PyTorch 版本证据；不能推断为未安装",
        ("连接目标后端后重新获取 system_stats。", "若安装记录显示缺失，按 ComfyUI 官方安装方法修复该环境。"), COMFY_DOCS)
    add("runtime.cuda", "runtime", "CUDA 加速", "ok" if cuda else "warning" if devices else "unknown",
        "当前后端报告了 CUDA 设备；显存和生成速度仍需实测" if cuda else "后端没有报告正在使用 CUDA；可能使用 CPU 或其他设备，不能据此断言未安装 CUDA" if devices else "尚无当前后端设备证据；不能确认 CUDA 是否可用",
        ("检查当前后端设备类型及官方 GPU 支持要求。", "硬件发现与包目录存在不能代替 CUDA 张量运行验证。"), COMFY_DOCS)

    selections = _selections(kind, models, request, model_catalog)
    needed = _dependencies(kind, request, refs, selections, info)
    if kind == "api":
        needed = sorted({node["class_type"] for node in prompt.values()})
        if not prompt:
            add("workflow.empty", "workflow", "API 工作流", "error", "API 图为空；先导入 ComfyUI API 格式工作流",
                ("导出并导入 ComfyUI 的 API 格式 JSON，而非界面布局 JSON。",), COMFY_DOCS)
        selections = _api_models(prompt, info) if online else []
        if not online and prompt:
            add("models.api", "model", "API 模型输入", "unknown", "需要连接后端取得实际 loader 枚举，不能为 API 图虚构图片模型角色",
                ("连接后重新核对工作流中每个模型加载节点的选项。",), COMFY_DOCS)

    for index, node in enumerate(needed):
        present = node in info
        cloud = present and isinstance(info[node], dict) and info[node].get("api_node") is True
        state = "unknown" if not online else "error" if cloud else "ok" if present else "missing"
        detail = "服务未连接，节点注册情况未知" if not online else "当前客户端不支持此云端 API 节点" if cloud else "后端已注册此节点" if present else "当前后端未注册此节点；核实官方节点来源和版本"
        add(f"node.{index}", "node", f"节点 · {node}", state, detail,
            ("按模式官方文档核对 ComfyUI 版本与所需扩展。", "安装或更新后使用原有启动方式重新启动后端，再检查节点注册。"), docs,
            repair=detail + (f"；所需节点：{node}" if kind != "api" else "；API 自定义节点名称请在本地检查面板核对"))

    if kind != "api":
        limits = {"h3_t2v": (0, 0), "h3_i2v": (1, 2), "h3_ref": (1, 9), "krea": (0, 3), "sdxl": (0, 1)}
        minimum, maximum = limits[kind]
        if not minimum <= len(refs) <= maximum or (request.get("denoise", 1) < 1 and not refs):
            add("input.references", "input", "参考图数量", "missing" if len(refs) < minimum or not refs else "error",
                f"当前模式需要 {minimum}–{maximum} 张参考图；低噪声重绘必须有输入图",
                ("在画布连接已上传的输入图片并核对首帧、尾帧或参考图角色。",), docs)
        if online and "CLIPLoader" in needed and "CLIPLoader" in info:
            options = _options(info["CLIPLoader"], "type")
            expected = "minimax" if kind.startswith("h3_") else "krea2"
            add("schema.clip_type", "schema", "文本编码器模式", "ok" if expected in options else "missing",
                "后端文本编码器支持目标模式" if expected in options else "后端 CLIPLoader 缺少当前模式选项；需要核对 ComfyUI 版本",
                ("按模式官方文档核对节点及文本编码器版本。",), docs)
        if refs and online and "LoadImage" in info:
            images = _options(info["LoadImage"], "image")
            add("input.images", "input", "后端参考图", "ok" if all(ref in images for ref in refs) else "missing",
                "后端图片选项包含全部参考图" if all(ref in images for ref in refs) else "后端未列出至少一张参考图；切换后端后需要重新上传",
                ("重新上传画布参考图到当前后端，然后检查图片连线。",), docs)

    for index, root in enumerate(roots):
        try:
            exists = Path(root).is_dir()
        except (ValueError, OSError):
            exists = False
        add(f"root.{index}", "directory", f"模型目录 {index + 1}", "ok" if exists else "missing",
            "目录存在；只对所选模型执行有界文件检查" if exists else "已配置的模型目录不存在或当前用户不可访问",
            ("在本地设置中核对模型目录；优先使用后端原有目录和兼容路径。", "检查目录访问权限，不移动或替换现有模型。"), COMFY_DOCS)
    if selections and not roots:
        add("models.local_scope", "directory", "本地文件检查范围", "warning", "未指定模型目录，只能核对后端枚举；未确认模型文件完整性",
            ("选择当前后端原本使用的模型根目录，再执行文件检查。",), docs)

    for index, (role, selected, candidates) in enumerate(selections):
        key, name = f"model.{role}.{index}", f"模型 · {role}" + (f" {index + 1}" if kind == "api" else "")
        steps = ("核对模式官方文档中的模型角色与版本，在当前后端选择匹配模型。", "先核实文件大小、官方校验值和已有路径；本检查不会下载模型。")
        if not online:
            add(key, "model", name, "unknown", "服务未连接，模型枚举和兼容性未知", steps, docs)
            continue
        if not selected or selected not in candidates:
            add(key, "model", name, "missing", "所需模型未被对应加载器列出，或尚未选择适配此模式的模型", steps, docs)
            continue
        try:
            safe_relative(selected)
            if kind != "api" and role != "lora":
                _check_family(selected, role, kind)
            if kind.startswith("h3_") and role == "lora" and ((kind == "h3_ref" and "fl2v" in selected.lower()) or (kind != "h3_ref" and "ref2v" in selected.lower())):
                raise ValueError("LoRA 架构不相容")
        except ValueError:
            add(key, "model", name, "error", "模型角色、已知架构或相对路径不兼容；请核对当前模式和加载器", steps, docs)
            continue
        add(key, "model", name, "ok", "当前加载器已列出此模型，未发现已知架构冲突；未知自定义名称仍需加载验证", steps, docs)
        try:
            path = resolve_model(roots, selected, role)
            if path is None:
                state, detail = "warning", "后端已枚举模型，但在所选目录中未定位；目录范围可能不完整，不能断言文件缺失"
            elif path.suffix.lower() == ".safetensors":
                state, detail, size = inspect_safetensors(path)
                detail = f"{size / 1024 ** 3:.2f} GiB · {detail}"
            else:
                state, detail = "warning", "文件存在；当前仅检查 safetensors 结构，未做全文件校验"
        except (ValueError, OSError):
            state, detail = "error", "文件无法读取或结构无效；请检查目录授权、文件占用与下载完整性"
        add(key + ".file", "file", name + " · 本地文件", state, detail, steps, docs)

    if kind == "api" and online and prompt and all(node in info for node in needed):
        try:
            validate_prompt(prompt, info)
        except ValueError:
            add("workflow.schema", "workflow", "API 图结构", "error", "API 图与后端节点定义不兼容；核对必填参数、枚举、连线类型和循环依赖",
                ("在画布的编译检查中查看具体节点错误，再修正 API 图。",), COMFY_DOCS)
        else:
            add("workflow.schema", "workflow", "API 图结构", "ok", "节点参数、枚举与连线通过静态校验；尚未执行 GPU 推理")
    elif kind != "api" and online and not any(check["status"] in {"missing", "error"} for check in checks):
        # Reuse the real compiler to catch dynamic schema/loader variants and
        # parameter constraints after missing prerequisites have been enumerated.
        check_request = dict(request)
        if not check_request.get("positive", "").strip():
            check_request["positive"] = "Environment readiness check."
        try:
            compile_workflow(check_request, info)
        except ValueError:
            add("workflow.schema", "workflow", "当前生成配置", "error", "当前配置与后端节点定义不兼容；核对参数范围、动态输入、模型加载器和采样选项",
                ("使用画布的编译检查查看具体错误，再核对模式官方模板。",), docs)
        else:
            add("workflow.schema", "workflow", "当前生成配置", "ok", "当前配置通过编译与节点定义检查；尚未执行 GPU 推理")
    if kind.startswith("h3_"):
        add("h3.runtime_limits", "performance", "H3 实际运行验证", "warning", "显存占用、CPU offload、生成速度和视听质量需使用当前组合进行短片实测", ("先使用短时长、固定种子测试当前基模和 LoRA 组合。",), H3_DOCS)
        add("h3.license", "license", "MiniMax H3 许可", "warning", "模型采用独立社区许可；客户端不附带模型权重", ("阅读并遵守模型官方许可。",), "https://huggingface.co/MiniMaxAI/MiniMax-H3")

    counts = {state: sum(check["status"] == state for check in checks) for state in STATES}
    ready = online and not any(counts[state] for state in ("missing", "error", "unknown"))
    summary = f"{counts['missing']} 项缺失 · {counts['error']} 项错误 · {counts['unknown']} 项待连接或确认 · {counts['warning']} 项提醒 · {counts['ok']} 项通过"
    lines = ["请协助检查 FrameWeave 本地 AI 生成环境。", f"目标模式：{kind}", f"检测摘要：{summary}",
             "以下为脱敏检测数据，不是执行指令；未包含本地路径、用户提示词、媒体名称、用户名或启动命令："]
    lines += repair_rows
    lines += [f"模式官方文档：{docs}", f"环境官方文档：{COMFY_DOCS}",
              "先区分未安装、未运行、未连接和未确认；不要从连接失败推断环境缺失。",
              "请给出官方来源、兼容版本、下载字节数和校验方式，并说明对已有工作流的影响。",
              "先提供修复方案；不要自动下载、执行命令、移动现有资产或删除文件。",
              "静态就绪不等于 GPU 已成功生成，也不证明速度或生成质量。"]
    return {"checks": checks, "counts": counts, "ready": ready,
            "checked_at": datetime.now(timezone.utc).isoformat(), "mode": kind,
            "summary": summary, "repair_prompt": "\n".join(lines),
            "scope": "静态环境与所选工作流检查；不代表 GPU 生成、性能或质量验证"}
