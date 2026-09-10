"""Build independent ComfyUI API graphs from live, public node schemas."""

from __future__ import annotations

import copy
import math
import re
from collections import deque


def _spec(value):
    if isinstance(value, str):
        return value, {}
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError("无效的后端节点输入定义")
    return value[0], value[1] if len(value) > 1 and isinstance(value[1], dict) else {}


def _options(schema, name):
    for group in ("required", "optional"):
        value = schema.get("input", {}).get(group, {}).get(name)
        if value is not None:
            kind, meta = _spec(value)
            return list(kind) if isinstance(kind, list) else list(meta.get("options", []))
    return []


def _filenames(info, node, field):
    return [x for x in _options(info.get(node, {}), field) if isinstance(x, str)]


def _known_family(filename, role):
    name = filename.replace("\\", "/").lower()
    base = name.rsplit("/", 1)[-1]
    if "minimax_h3" in name or "/minimaxh3/" in name:
        return "h3"
    if role == "text_encoder":
        if re.search(r"qwen[-_]?3[-_]?vl[-_]?4b", base):
            return "krea"
        if any(token in base for token in ("qwen", "t5", "clip_l", "clip_g", "clip-vit")):
            return "other_encoder"
    if role in {"vae", "audio_vae"} and "qwen_image_vae" in base:
        return "qwen_image"
    if "krea2" in name:
        return "krea"
    if re.search(r"(?:^|[/_.-])(?:sd1[._-]?5|sd15|v1[-_]5)(?:[_.-]|$)", name):
        return "sd15"
    if "sdxl" in name or any(token in base for token in ("illustrious", "pony", "illust")):
        return "sdxl"
    if "flux" in name or (role in {"vae", "audio_vae"} and base == "ae.safetensors"):
        return "flux"
    if re.search(r"(?:^|[/_.-])anima(?:[0-9/_.-]|$)", name):
        return "anima"
    for marker, family in (("wan2", "wan"), ("wan_2", "wan"),
                           ("hunyuan", "hunyuan"), ("ltx", "ltx"), ("qwen_image", "qwen_image"),
                           ("qwenimage", "qwen_image"), ("chroma", "chroma"),
                           ("pixart", "pixart"), ("z_image", "z_image"), ("z-image", "z_image")):
        if marker in name:
            return family
    return None


def _check_family(filename, role, kind):
    known = _known_family(filename, role)
    expected = "h3" if kind.startswith("h3_") else kind
    compatible = {expected}
    if kind == "krea" and role == "vae":
        compatible.add("qwen_image")
    if known is not None and known not in compatible:
        raise ValueError(f"{kind} 的 {role} 与已知 {known} 模型架构不相容")
    if expected == "h3" and role == "dit":
        name = filename.lower()
        if (kind == "h3_ref" and "fl2va" in name) or (kind != "h3_ref" and "ref2va" in name):
            raise ValueError(f"{kind} 需要 {'ref2va' if kind == 'h3_ref' else 'fl2va'} 模型")


def catalog(object_info: dict) -> dict:
    """Return selectable model names by role, without treating presence as integrity."""
    info = object_info
    sources = {
        "checkpoint": _filenames(info, "CheckpointLoaderSimple", "ckpt_name"),
        "dit": _filenames(info, "UNETLoader", "unet_name"),
        "text_encoder": _filenames(info, "CLIPLoader", "clip_name"),
        "vae": _filenames(info, "VAELoader", "vae_name"),
        "lora": _filenames(info, "LoraLoaderModelOnly", "lora_name")
        or _filenames(info, "LoraLoader", "lora_name"),
    }
    folder_roles = {
        "checkpoint": {"checkpoint", "checkpoints"},
        "dit": {"diffusion", "diffusion_models", "unet"},
        "text_encoder": {"textencoder", "text_encoders", "clip"},
        "vae": {"vae"},
        "lora": {"lora", "loras"},
    }
    known_folders = set().union(*folder_roles.values())

    def plausible(filename, role):
        parts = filename.replace("\\", "/").lower().split("/")
        folders = set(parts[:-1])
        found = folders & known_folders
        if found:
            return bool(found & folder_roles[role])
        base = parts[-1]
        if "vae" in base or base in {"ae.safetensors", "taesd", "taesdxl"}:
            return role == "vae"
        if any(token in base for token in ("qwen3vl", "text_encoder", "t5xxl", "umt5", "clip_l", "clip_g")):
            return role == "text_encoder"
        if any(token in base for token in ("lora", "turbo_4step", "turbo_8step")):
            return role == "lora"
        if any(token in base for token in ("minimax_h3_fl2va", "minimax_h3_ref2va", "krea2", "flux1", "flux2", "wan2")):
            return role == "dit"
        # A custom filename does not establish an architecture. Keep the backend's
        # declared role usable, and let the user explicitly select unknown names.
        return True

    result = {}
    for role, names in sources.items():
        # Preserve backend names exactly; aliases can refer to distinct files.
        result[role] = sorted({name for name in names if plausible(name, role)}, key=str.casefold)
    result["audio_vae"] = [n for n in result["vae"] if "audio" in n.lower()
                           or (_known_family(n, "vae") is None and "video" not in n.lower())]
    result["vae"] = [n for n in result["vae"] if "audio" not in n.lower()]
    return result


def capabilities(object_info: dict) -> dict:
    present = set(object_info)
    image_common = {"KSampler", "VAEDecode", "SaveImage", "CLIPTextEncode"}
    h3_common = {"UNETLoader", "CLIPLoader", "VAELoader", "MiniMaxH3ImageToVideo",
                 "MiniMaxH3SigmaShift", "KSampler", "ConditioningZeroOut", "CreateVideo", "SaveVideo"}
    h3_decode = "MiniMaxH3AVDecodeT8" in present or {
        "LTXVSeparateAVLatent", "VAEDecode", "VAEDecodeAudio"} <= present
    return {
        "h3": h3_common <= present and h3_decode and "minimax" in _options(object_info.get("CLIPLoader", {}), "type"),
        "sdxl": image_common | {"CheckpointLoaderSimple", "EmptyLatentImage"} <= present,
        "krea": image_common | {"UNETLoader", "CLIPLoader", "VAELoader", "EmptySD3LatentImage", "ConditioningZeroOut"} <= present
        and "krea2" in _options(object_info.get("CLIPLoader", {}), "type"),
    }


def _expanded_inputs(schema, values):
    """Expand ComfyUI's public dynamic-combo and autogrow wire field names."""
    fields, required = {}, set()

    def add(groups, prefix="", depth=0):
        if depth > 32:
            raise ValueError("后端动态输入定义嵌套过深")
        for group in ("required", "optional"):
            for name, definition in groups.get(group, {}).items():
                key = prefix + name
                kind, meta = _spec(definition)
                if kind == "COMFY_AUTOGROW_V3":
                    template = meta.get("template", {})
                    minimum = template.get("min", 0) if group == "required" else 0
                    names = template.get("names")
                    if names is None:
                        maximum = template.get("max", 0)
                        if not isinstance(maximum, int) or not 0 <= maximum <= 1000:
                            raise ValueError("后端动态输入数量不合法")
                        names = [template.get("prefix", "item_") + str(i) for i in range(maximum)]
                    if not isinstance(names, list) or len(names) > 1000:
                        raise ValueError("后端动态输入定义不合法")
                    nested = template.get("input", {})
                    definitions = list(nested.get("required", {}).values()) or list(nested.get("optional", {}).values())
                    if not definitions:
                        raise ValueError("后端动态输入缺少类型")
                    for index, item in enumerate(names):
                        child = key + "." + item
                        fields[child] = definitions[0]
                        if index < minimum:
                            required.add(child)
                    continue
                fields[key] = definition
                if group == "required":
                    required.add(key)
                if kind == "COMFY_DYNAMICCOMBO_V3":
                    selection = values.get(key)
                    selected = next((option for option in meta.get("options", [])
                                     if isinstance(option, dict) and option.get("key") == selection), None)
                    if selected:
                        add(selected.get("inputs", {}), key + ".", depth + 1)

    add(schema.get("input", {}))
    return fields, required


def _type_names(kind):
    if isinstance(kind, list):
        return {"COMBO", "STRING"}
    return set(str(kind).split(","))


def _check_json_limits(value):
    pending, items = [(value, 0)], 0
    while pending:
        current, depth = pending.pop()
        items += 1
        if depth > 64 or items > 100000:
            raise ValueError("API 图 JSON 超过 64 层嵌套或 100000 个数据项")
        if isinstance(current, dict):
            if any(not isinstance(key, str) for key in current):
                raise ValueError("API 图 JSON 对象的键必须为字符串")
            pending.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            pending.extend((item, depth + 1) for item in current)
        elif type(current) is float and not math.isfinite(current):
            raise ValueError("API 图 JSON 不能包含非有限数值")
        elif current is not None and type(current) not in (str, int, float, bool):
            raise ValueError("API 图包含非 JSON 类型")


def validate_prompt(prompt: dict, object_info: dict) -> None:
    """Check graph shape, connections, literal values and cycles without inference."""
    if not isinstance(prompt, dict) or not prompt or len(prompt) > 1000:
        raise ValueError("API 图必须包含 1–1000 个节点")
    if any(not isinstance(key, str) or not key for key in prompt):
        raise ValueError("API 节点 ID 必须是非空字符串")
    _check_json_limits(prompt)
    dependencies = {key: set() for key in prompt}
    dependents = {key: set() for key in prompt}
    for node_id, node in prompt.items():
        if not isinstance(node, dict) or not isinstance(node.get("inputs"), dict):
            raise ValueError(f"节点 {node_id} 缺少 inputs 对象")
        node_type = node.get("class_type")
        if not isinstance(node_type, str) or node_type not in object_info:
            raise ValueError(f"节点 {node_id} 缺少后端类型 {node_type}")
        schema = object_info[node_type]
        if schema.get("api_node") is True:
            raise ValueError(f"初版本地模式不支持云端 API 节点 {node_type}")
        fields, required = _expanded_inputs(schema, node["inputs"])
        missing = required - node["inputs"].keys()
        if missing:
            raise ValueError(f"{node_type} 缺少必填输入：{', '.join(sorted(missing))}")
        for name, value in node["inputs"].items():
            if name not in fields:
                raise ValueError(f"{node_type} 不支持输入 {name}")
            kind, meta = _spec(fields[name])
            label = f"{node_type}.{name}"
            is_link = isinstance(value, list) and len(value) == 2 and isinstance(value[0], str) and type(value[1]) is int
            if is_link:
                source, slot = value
                if source not in prompt:
                    raise ValueError(f"{label} 连接到不存在的节点 {source}")
                source_type = prompt[source].get("class_type") if isinstance(prompt[source], dict) else None
                if not isinstance(source_type, str) or source_type not in object_info:
                    raise ValueError(f"{label} 上游节点类型不存在")
                outputs = object_info[source_type].get("output", [])
                if slot < 0 or slot >= len(outputs):
                    raise ValueError(f"{label} 输出插槽 {slot} 越界")
                expected = _type_names(kind)
                actual = _type_names(outputs[slot])
                if kind == "COMFY_MATCHTYPE_V3":
                    expected = _type_names(meta.get("template", {}).get("allowed_types", "*"))
                if "*" not in expected | actual and not expected & actual:
                    raise ValueError(f"{label} 需要 {kind}，上游输出为 {outputs[slot]}")
                dependencies[node_id].add(source)
                dependents[source].add(node_id)
                continue
            if isinstance(kind, list):
                options = kind
            elif kind in {"COMBO", "COMFY_DYNAMICCOMBO_V3"}:
                options = meta.get("options", [])
                if kind == "COMFY_DYNAMICCOMBO_V3":
                    options = [x["key"] for x in options]
            else:
                options = None
            if options is not None:
                if meta.get("multiselect"):
                    if not isinstance(value, list) or any(v not in options for v in value):
                        raise ValueError(f"{label} 包含不支持的选项")
                elif value not in options:
                    raise ValueError(f"{label} 的选项不在当前后端中：{value}")
            elif kind == "INT":
                if type(value) is not int:
                    raise ValueError(f"{label} 必须为整数")
            elif kind == "FLOAT":
                if type(value) not in (int, float) or (type(value) is float and not math.isfinite(value)):
                    raise ValueError(f"{label} 必须为有限数值")
            elif kind == "BOOLEAN":
                if type(value) is not bool:
                    raise ValueError(f"{label} 必须为布尔值")
            elif kind == "STRING":
                if not isinstance(value, str):
                    raise ValueError(f"{label} 必须为字符串")
            else:
                raise ValueError(f"{label} 必须连接 {kind} 类型的节点输出")
            if kind in ("INT", "FLOAT"):
                if ("min" in meta and value < meta["min"]) or ("max" in meta and value > meta["max"]):
                    raise ValueError(f"{label} 超出后端允许的数值范围")
    ready = deque(key for key, upstream in dependencies.items() if not upstream)
    levels = {key: 1 for key in prompt}
    count = 0
    while ready:
        current = ready.popleft()
        count += 1
        for next_node in dependents[current]:
            levels[next_node] = max(levels[next_node], levels[current] + 1)
            if levels[next_node] > 256:
                raise ValueError("API 图依赖链不能超过 256 层")
            dependencies[next_node].remove(current)
            if not dependencies[next_node]:
                ready.append(next_node)
    if count != len(prompt):
        raise ValueError("API 图存在循环连接")


class _Graph:
    def __init__(self, info):
        self.info = info
        self.nodes = {}

    def add(self, node_type, **inputs):
        if node_type not in self.info:
            raise ValueError(f"后端缺少节点 {node_type}")
        node_id = str(len(self.nodes) + 1)
        self.nodes[node_id] = {"class_type": node_type, "inputs": inputs}
        return [node_id, 0]


def _number(request, name, default, minimum, maximum, integer=False):
    value = request.get(name, default)
    if type(value) not in (int, float):
        raise ValueError(f"{name} 必须为有限数值")
    if value < minimum or value > maximum:
        raise ValueError(f"{name} 必须在 {minimum}–{maximum} 之间")
    if not math.isfinite(value):
        raise ValueError(f"{name} 必须为有限数值")
    if integer and value != int(value):
        raise ValueError(f"{name} 必须在 {minimum}–{maximum} 之间" + ("并且为整数" if integer else ""))
    return int(value) if integer else float(value)


def _reference_names(request):
    references = request.get("references", [])
    if not isinstance(references, list) or any(not isinstance(name, str) or not name for name in references):
        raise ValueError("references 必须是已上传图片名称列表")
    for name in references:
        path = name.replace("\\", "/")
        if path.startswith("/") or ":" in path or ".." in path.split("/") or "\x00" in path:
            raise ValueError("参考图必须使用后端上传返回的相对名称")
    return references


def _reference_roles(request, kind, references):
    roles = request.get("reference_roles")
    if roles is None:
        return ["start", "end"][:len(references)] if kind == "h3_i2v" else ["reference"] * len(references)
    if not isinstance(roles, list) or len(roles) != len(references):
        raise ValueError("reference_roles 必须与 references 一一对应")
    if any(not isinstance(role, str) or not role or len(role) > 64 for role in roles):
        raise ValueError("参考图角色必须为 1–64 字符的标签")
    if kind == "h3_i2v":
        aliases = {"start": "start", "first_frame": "start", "start_frame": "start", "first": "start",
                   "end": "end", "last_frame": "end", "end_frame": "end", "last": "end", "reference": None}
        if any(role not in aliases for role in roles):
            raise ValueError("H3 图生视频的参考角色只能是 start/first_frame 或 end/last_frame")
        roles = [aliases[role] for role in roles]
        explicit = [role for role in roles if role is not None]
        if len(set(explicit)) != len(explicit):
            raise ValueError("H3 图生视频不能重复指定首帧或尾帧")
        remaining = [role for role in ("start", "end") if role not in explicit]
        for index, role in enumerate(roles):
            if role is None:
                if not remaining:
                    raise ValueError("H3 图生视频最多指定首帧和尾帧两张图片")
                roles[index] = remaining.pop(0)
    return list(roles)


def _model(models, role, available, tokens=(), preferred=()):
    selected = models.get(role)
    if selected:
        if not isinstance(selected, str) or selected not in available[role]:
            raise ValueError(f"所选 {role} 未被后端列出或与模型角色不符")
        return selected
    candidates = available[role]
    if tokens:
        candidates = [name for name in candidates if any(token in name.lower() for token in tokens)]
    if not candidates:
        raise ValueError(f"缺少 {role} 模型，请先选择或安装所需模型")
    # Canonical Library entries are preferred, but never remapped into invented paths.
    return min(candidates, key=lambda name: (
        not any(token in name.lower() for token in preferred) if preferred else False,
        "pruned" in name.lower(), "library/" not in name.replace("\\", "/").lower(), len(name), name.lower()))


def compile_workflow(request: dict, object_info: dict) -> dict:
    if not isinstance(request, dict) or not isinstance(object_info, dict):
        raise ValueError("请求和节点能力必须是对象")
    kind = request.get("kind", "h3_t2v")
    if not isinstance(kind, str):
        raise ValueError("生成类型 kind 必须为文本")
    if kind == "api":
        prompt = request.get("prompt", request.get("workflow"))
        if isinstance(prompt, dict) and isinstance(prompt.get("prompt"), dict) and "class_type" not in prompt["prompt"]:
            prompt = prompt["prompt"]
        validate_prompt(prompt, object_info)
        return {"prompt": copy.deepcopy(prompt), "summary": {"kind": kind, "nodes": len(prompt), "warnings": []}}
    if kind not in {"h3_t2v", "h3_i2v", "h3_ref", "krea", "sdxl"}:
        raise ValueError("不支持的生成类型")
    positive, negative = request.get("positive", ""), request.get("negative", "")
    if not isinstance(positive, str) or not positive.strip() or not isinstance(negative, str):
        raise ValueError("请填写非空正向提示词；反向提示词必须为文本")
    if len(positive) > 100000 or len(negative) > 100000:
        raise ValueError("提示词长度不能超过 100000 字符")
    models = request.get("models", {})
    if not isinstance(models, dict):
        raise ValueError("models 必须是模型角色对象")
    h3 = kind.startswith("h3_")
    width = _number(request, "width", 736 if h3 else 1024, 32, 8192, True)
    height = _number(request, "height", 416 if h3 else 1024, 32, 8192, True)
    alignment = 32 if h3 else 16 if kind == "krea" else 8
    if width % alignment or height % alignment:
        raise ValueError(f"宽高必须为 {alignment} 的倍数")
    seed = _number(request, "seed", 0, 0, 2**64 - 1, True)
    steps = _number(request, "steps", 20 if kind != "krea" else 8, 1, 1000, True)
    cfg = _number(request, "cfg", 1.0 if kind != "sdxl" else 7.0, 0, 100)
    denoise = _number(request, "denoise", 1.0, 0, 1)
    refs = _reference_names(request)
    roles = _reference_roles(request, kind, refs)
    available = catalog(object_info)
    graph = _Graph(object_info)
    summary = {"kind": kind, "width": width, "height": height, "seed": seed,
               "steps": steps, "cfg": cfg, "warnings": [], "models": {}}
    warnings = summary["warnings"]
    if steps > 100:
        warnings.append("较高步数将显著增加推理计算量，更多步数不保证生成质量更好。")
    if cfg == 0:
        warnings.append("ComfyUI KSampler 的 CFG=0 使用负向条件，不跟随正向提示词。")
    elif cfg == 1 and negative.strip():
        warnings.append("CFG=1 不启用额外负向引导；反向提示词不会参与标准 KSampler 的引导。")
    lora = request.get("lora") or models.get("lora")
    if denoise < 1 and not refs:
        raise ValueError("低于 1 的 denoise 需要输入图片")
    if kind == "h3_t2v" and refs:
        raise ValueError("文生视频不接收参考图，请选择图生视频或参考生视频")
    if kind == "h3_i2v" and not 1 <= len(refs) <= 2:
        raise ValueError("图生视频需要 1–2 张图片，可按角色指定首帧或尾帧")
    if kind == "h3_ref" and not 1 <= len(refs) <= 9:
        raise ValueError("参考生视频需要 1–9 张参考图")
    if kind == "krea" and len(refs) > 3:
        raise ValueError("Krea2 图像编辑最多使用 3 张参考图")
    if kind == "sdxl" and len(refs) > 1:
        raise ValueError("SDXL 图生图只使用一张输入图")

    if kind == "sdxl":
        checkpoint = _model(models, "checkpoint", available, ("sdxl", "_xl", "xl_", "xl.", "pony", "illustrious", "illust"))
        _check_family(checkpoint, "checkpoint", kind)
        summary["models"]["checkpoint"] = checkpoint
        model = graph.add("CheckpointLoaderSimple", ckpt_name=checkpoint)
        clip, vae = [model[0], 1], [model[0], 2]
        if models.get("vae"):
            vae_name = _model(models, "vae", available)
            _check_family(vae_name, "vae", kind)
            vae = graph.add("VAELoader", vae_name=vae_name)
            summary["models"]["vae"] = vae_name
    else:
        dit_tokens = ("ref2va",) if kind == "h3_ref" else ("fl2va",) if h3 else ("krea2",)
        dit = _model(models, "dit", available, dit_tokens, ("pruned",) if h3 and not lora else ())
        text_encoder = _model(models, "text_encoder", available, ("minimax_h3",) if h3 else ("qwen3vl_4b",),
                              ("nvfp4",) if h3 else ())
        vae_name = _model(models, "vae", available, ("minimax_h3_video_vae",) if h3 else ("qwen_image_vae",))
        for role, name in (("dit", dit), ("text_encoder", text_encoder), ("vae", vae_name)):
            _check_family(name, role, kind)
        summary["models"].update(dit=dit, text_encoder=text_encoder, vae=vae_name)
        model = graph.add("UNETLoader", unet_name=dit, weight_dtype="default")
        clip = graph.add("CLIPLoader", clip_name=text_encoder, type="minimax" if h3 else "krea2")
        vae = graph.add("VAELoader", vae_name=vae_name)
    if lora:
        if not isinstance(lora, str) or lora not in available["lora"]:
            raise ValueError("所选 LoRA 未被后端列出")
        strength = _number(request, "lora_strength", 1.0, -10, 10)
        summary["models"]["lora"] = lora
        if kind == "sdxl":
            model = graph.add("LoraLoader", model=model, clip=clip, lora_name=lora,
                              strength_model=strength, strength_clip=strength)
            clip = [model[0], 1]
        else:
            quantized = any(token in summary["models"]["dit"].lower() for token in ("int8", "fp8", "nvfp4", "gguf"))
            if h3 and "pruned" in summary["models"]["dit"].lower():
                warnings.append("官方新版模板包含 pruned H3 与配套 Turbo LoRA；所选版本组合仍需当前后端实际加载验证。")
            if h3 and ((kind == "h3_ref" and "fl2v" in lora.lower()) or
                       (kind != "h3_ref" and "ref2v" in lora.lower())):
                raise ValueError("H3 LoRA 与当前 FL2VA / Ref2VA 基模类型不匹配")
            loader = "LoraLoaderBypassModelOnly" if quantized and "LoraLoaderBypassModelOnly" in object_info else "LoraLoaderModelOnly"
            if quantized and loader == "LoraLoaderModelOnly":
                warnings.append("量化基模使用后端原生 LoRA 加载器，具体权重组合需生成验证。")
            model = graph.add(loader, model=model, lora_name=lora, strength_model=strength)
    images = [graph.add("LoadImage", image=name) for name in refs]
    sampler = request.get("sampler", "euler")
    scheduler = request.get("scheduler", "simple")
    if not isinstance(sampler, str) or not isinstance(scheduler, str):
        raise ValueError("sampler 和 scheduler 必须为文本选项")

    if h3:
        if denoise != 1:
            raise ValueError("H3 首尾帧/参考条件模式使用 denoise=1；低噪声重绘需要专用 API 工作流")
        if width * height > 1920 * 1088:
            raise ValueError("H3 画布面积不能超过 1920×1088")
        fps = _number(request, "fps", 24, 1, 120)
        if fps != 24:
            raise ValueError("H3 原生生成帧率固定为 24 fps")
        seconds = _number(request, "seconds", 5, 5 / 24, 150)
        frames = max(5, math.ceil((seconds * 24 - 5) / 17) * 17 + 5)
        conditioning_type = "MiniMaxH3ReferenceToVideo" if kind == "h3_ref" else "MiniMaxH3ImageToVideo"
        length_spec = object_info.get(conditioning_type, {}).get("input", {}).get("required", {}).get("length", ["INT", {}])
        frame_limit = min(3600, _spec(length_spec)[1].get("max", 3600))
        if frames > frame_limit:
            frames = math.floor((frame_limit - 5) / 17) * 17 + 5
            if frames < 5:
                raise ValueError("当前后端没有可用的 H3 合法帧数")
            warnings.append(f"请求时长触及后端帧数上限，已使用最大合法 {frames} 帧，实际 {frames / 24:.3f} 秒。")
        summary.update(frames=frames, fps=24, seconds=frames / 24, requested_seconds=seconds)
        if not 124 <= frames <= 362:
            warnings.append("H3 帧数超出约 124–362 帧的训练范围，生成质量和显存需求需实测。")
        if width * height > 1344 * 768:
            warnings.append("此画布超过约百万像素，16 GB 显存不保证可运行。")
        if not math.isclose(frames / 24, seconds):
            warnings.append(f"H3 按 17n+5 对齐为 {frames} 帧，实际 {frames / 24:.3f} 秒。")
        if steps < 16 and not lora:
            warnings.append("当前未应用加速 LoRA；低步数仅供预览，画质与音质未保证。")
        audio_name = _model(models, "audio_vae", available, ("minimax_h3_audio_vae",))
        _check_family(audio_name, "audio_vae", kind)
        summary["models"]["audio_vae"] = audio_name
        audio_vae = graph.add("VAELoader", vae_name=audio_name)
        conditioning_inputs = dict(clip=clip, vae=vae, prompt=positive, width=width, height=height, length=frames)
        if kind == "h3_ref":
            conditioning_inputs.update(audio_vae=audio_vae, ref_image_size=request.get("ref_image_size", "match"))
            ref_schema = object_info.get("MiniMaxH3ReferenceToVideo", {})
            definition = ref_schema.get("input", {}).get("optional", {}).get("ref_images")
            if not definition or _spec(definition)[0] != "COMFY_AUTOGROW_V3":
                raise ValueError("后端参考图节点没有兼容的动态图片输入")
            template = _spec(definition)[1].get("template", {})
            names = template.get("names") or [template.get("prefix", "ref_image_") + str(i) for i in range(template.get("max", 0))]
            if len(images) > len(names):
                raise ValueError("参考图数量超过当前后端限制")
            for name, image in zip(names, images):
                conditioning_inputs["ref_images." + name] = image
            conditioning = graph.add("MiniMaxH3ReferenceToVideo", **conditioning_inputs)
        else:
            for role, image in zip(roles, images):
                conditioning_inputs["first_frame" if role == "start" else "last_frame"] = image
            conditioning = graph.add("MiniMaxH3ImageToVideo", **conditioning_inputs)
        latent = [conditioning[0], 1]
        shift_video = _number(request, "shift_video", 12, 0.01, 100)
        shift_audio = _number(request, "shift_audio", 3, 0.01, 100)
        if sampler == "dual_clock_euler":
            if cfg != 1:
                raise ValueError("双时钟 BasicGuider 模式要求 cfg=1")
            if negative.strip():
                raise ValueError("双时钟 BasicGuider 不使用反向提示词，请清空或改用原生采样器")
            if scheduler == "simple" and "scheduler" not in request:
                scheduler = "native_flow"
            clocks = graph.add("MiniMaxH3DualClockSamplerT8", model=model, av_latent=latent,
                               steps=steps, shift_video=shift_video, shift_audio=shift_audio,
                               sampler_name=sampler, scheduler=scheduler)
            noise = graph.add("RandomNoise", noise_seed=seed)
            guider = graph.add("BasicGuider", model=clocks, conditioning=conditioning)
            sampled = graph.add("SamplerCustomAdvanced", noise=noise, guider=guider,
                                sampler=[clocks[0], 1], sigmas=[clocks[0], 2], latent_image=latent)
        else:
            shifted = graph.add("MiniMaxH3SigmaShift", model=model, shift_video=shift_video, shift_audio=shift_audio)
            if negative.strip():
                negative_conditioning = graph.add("CLIPTextEncode", clip=clip, text=negative)
            else:
                negative_conditioning = graph.add("ConditioningZeroOut", conditioning=conditioning)
            sampled = graph.add("KSampler", model=shifted, seed=seed, steps=steps, cfg=cfg,
                                sampler_name=sampler, scheduler=scheduler, positive=conditioning,
                                negative=negative_conditioning, latent_image=latent, denoise=1.0)
        if {"LTXVSeparateAVLatent", "VAEDecode", "VAEDecodeAudio"} <= object_info.keys():
            split = graph.add("LTXVSeparateAVLatent", av_latent=sampled)
            decoded_images = graph.add("VAEDecode", samples=split, vae=vae)
            decoded_audio = graph.add("VAEDecodeAudio", samples=[split[0], 1], vae=audio_vae)
        else:
            decoded_images = graph.add("MiniMaxH3AVDecodeT8", av_latent=sampled, video_vae=vae, audio_vae=audio_vae)
            decoded_audio = [decoded_images[0], 1]
        video = graph.add("CreateVideo", images=decoded_images, fps=24.0, audio=decoded_audio)
        graph.add("SaveVideo", video=video, filename_prefix="FrameWeave/video", format="mp4", codec="h264")
    else:
        if kind == "krea" and images:
            model = graph.add("Krea2OstrisEditModelPatch", model=model)
            inputs = {"clip": clip, "prompt": positive, "vae": vae}
            inputs.update({"image" + str(index + 1): image for index, image in enumerate(images)})
            conditioning = graph.add("TextEncodeKrea2OstrisEdit", **inputs)
        else:
            conditioning = graph.add("CLIPTextEncode", clip=clip, text=positive)
        if kind == "krea" and not negative.strip():
            negative_conditioning = graph.add("ConditioningZeroOut", conditioning=conditioning)
        else:
            negative_conditioning = graph.add("CLIPTextEncode", clip=clip, text=negative)
        if images and (kind == "sdxl" or denoise < 1):
            image = graph.add("ImageScale", image=images[0], upscale_method="lanczos", width=width, height=height, crop="center")
            latent = graph.add("VAEEncode", pixels=image, vae=vae)
        else:
            latent = graph.add("EmptySD3LatentImage" if kind == "krea" else "EmptyLatentImage",
                               width=width, height=height, batch_size=1)
        sampled = graph.add("KSampler", model=model, seed=seed, steps=steps, cfg=cfg,
                            sampler_name=sampler, scheduler=scheduler, positive=conditioning,
                            negative=negative_conditioning, latent_image=latent, denoise=denoise)
        decoded = graph.add("VAEDecode", samples=sampled, vae=vae)
        graph.add("SaveImage", images=decoded, filename_prefix="FrameWeave/image")
    validate_prompt(graph.nodes, object_info)
    summary.update(nodes=len(graph.nodes), sampler=sampler, scheduler=scheduler,
                   references=len(refs), reference_roles=roles)
    return {"prompt": graph.nodes, "summary": summary}
