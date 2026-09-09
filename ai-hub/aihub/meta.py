# -*- coding: utf-8 -*-
"""文件元数据解析：safetensors 头部、PNG 内嵌工作流、分类规则。"""
import json
import re
import struct
import ntpath
import zlib

MODEL_EXTS = {".safetensors", ".sft", ".ckpt", ".pt", ".pth", ".gguf", ".onnx", ".bin"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv"}
AUDIO_EXTS = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}
DOC_EXTS = {".md", ".txt", ".pdf", ".docx", ".doc", ".html", ".htm", ".csv", ".xlsx"}
WORKFLOW_EXTS = {".json"}
ARCHIVE_EXTS = {".zip", ".7z", ".rar", ".tar", ".gz"}

# 目录名 -> 模型子类型（小写精确匹配最后一级目录名）
DIR_TYPE_MAP = {
    "checkpoints": "Checkpoint", "checkpoint": "Checkpoint",
    "loras": "LoRA", "lora": "LoRA",
    "vae": "VAE",
    "controlnet": "ControlNet", "control_net": "ControlNet",
    "unet": "Diffusion", "diffusion_models": "Diffusion", "diffusion": "Diffusion", "diffusers": "Diffusion",
    "text_encoders": "TextEncoder", "clip": "TextEncoder", "t5": "TextEncoder", "umt5": "TextEncoder",
    "clip_vision": "CLIPVision", "ipadapter": "IPAdapter", "ip_adapter": "IPAdapter",
    "embeddings": "Embedding", "embedding": "Embedding",
    "upscale_models": "Upscaler", "upscaler": "Upscaler", "latent_upscale_models": "Upscaler",
    "sam2": "Vision", "sams": "Vision", "insightface": "Vision", "birefnet": "Vision",
    "grounding-dino": "Vision", "florence2": "Vision",
    "detection": "Detection", "detectors": "Detection",
    "llm": "LLM", "llms": "LLM", "language": "LLM",
    "tts": "TTS", "speech": "TTS", "audio": "TTS",
    "video": "VideoAI",
}


def model_type(path):
    """Use directory roles only; file-name hints do not prove architecture."""
    for part in reversed(re.split(r"[\\/]", str(path))[:-1]):
        if part.casefold() in DIR_TYPE_MAP:
            return DIR_TYPE_MAP[part.casefold()]
    return None
# 输入参数键 -> 引用角色
KEY_ROLE_RULES = [
    (re.compile(r"lora", re.I), "LoRA"),
    (re.compile(r"ckpt|checkpoint", re.I), "Checkpoint"),
    (re.compile(r"unet|diffusion", re.I), "Diffusion"),
    (re.compile(r"vae", re.I), "VAE"),
    (re.compile(r"control_?net", re.I), "ControlNet"),
    (re.compile(r"ipadapter|ip_adapter", re.I), "IPAdapter"),
    (re.compile(r"clip_?vision", re.I), "CLIPVision"),
    (re.compile(r"clip|text_encoder|tokenizer", re.I), "TextEncoder"),
    (re.compile(r"upscale", re.I), "Upscaler"),
    (re.compile(r"sam|segment|mask|bbox|segs|grounding|florence|vision|face|insight", re.I), "Vision"),
    (re.compile(r"gguf|llm|glm|llava", re.I), "LLM"),
]
MODEL_FILE_RE = re.compile(r"\.(safetensors|sft|ckpt|pt|pth|gguf|onnx)$", re.I)
QUANT_RE = re.compile(r"\b(IQ[0-9]_[A-Z0-9]+|Q[0-9]_[A-Z0-9]+|Q[0-9]|F16|F32|BF16|fp16|fp32|int8)\b")
PARAMS_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*[bB]\b")
FAMILY_HINTS = [
    ("qwen", "Qwen"), ("glm", "GLM"), ("llama", "LLaMA"), ("mistral", "Mistral"), ("gemma", "Gemma"),
    ("deepseek", "DeepSeek"), ("phi", "Phi"), ("internlm", "InternLM"), ("yi-", "Yi"), ("minicpm", "MiniCPM"),
    ("flux", "Flux"), ("sd3", "SD3"), ("sdxl", "SDXL"), ("sd1", "SD15"), ("wan", "Wan"),
    ("hunyuan", "HunyuanVideo"), ("ltx", "LTX"),
]


def classify_file(ext: str, parent_name: str):
    """返回 (category, mtype)。"""
    e = ext.lower()
    if e in MODEL_EXTS:
        t = DIR_TYPE_MAP.get(parent_name.lower())
        return "model", t or None
    if e in IMAGE_EXTS:
        return "image", None
    if e in VIDEO_EXTS:
        return "video", None
    if e in AUDIO_EXTS:
        return "audio", None
    if e in WORKFLOW_EXTS:
        return "workflow", None
    if e in ARCHIVE_EXTS:
        return "archive", None
    if e in DOC_EXTS:
        return "doc", None
    if e in {".py", ".js", ".ts", ".bat", ".sh", ".ps1", ".yaml", ".yml", ".toml", ".c", ".cpp", ".h", ".rs"}:
        return "code", None
    return "other", None


def read_safetensors_header(path: str, max_header: int = 8 * 1024 * 1024):
    """只读 safetensors 头部，返回 (metadata_dict, tensor_count) 或 (None, 0)。"""
    try:
        with open(path, "rb") as f:
            n = struct.unpack("<Q", f.read(8))[0]
            if n <= 0 or n > max_header:
                return None, 0
            raw = f.read(min(n, max_header))
        header = json.loads(raw.decode("utf-8", "ignore"))
        meta = header.pop("__metadata__", None) or {}
        return meta, max(0, len(header))
    except Exception:
        return None, 0


def header_summary(meta: dict) -> dict:
    """从 safetensors __metadata__ 提取关键字段（modelspec / kohya）。"""
    if not meta:
        return {}
    out = {}
    keys = ["modelspec.sai_model_spec", "modelspec.architecture", "modelspec.title", "modelspec.author",
            "modelspec.description", "modelspec.url", "modelspec.license", "modelspec.tags",
            "modelspec.timesteps", "modelspec.trigger_prompt",
            "ss_base_model_version", "ss_sd_model_name", "ss_output_name", "ss_steps", "ss_num_train_images", "ss_epoch",
            "ss_network_dim", "ss_network_alpha", "ss_network_module", "ss_dataset_dirs",
            "ss_resolution", "ss_sha256", "training_method"]
    for k in keys:
        if k in meta and meta[k]:
            out[k] = str(meta[k])[:500]
    return out


def extract_trigger_words(meta: dict) -> str:
    for k in ("modelspec.trigger_prompt", "ss_trigger_word", "trigger_word"):
        v = meta.get(k)
        if v:
            return str(v)[:300]
    tags = meta.get("modelspec.tags")
    return str(tags)[:300] if tags else ""


def parse_png_metadata(path: str) -> dict:
    """流式读取 PNG 元数据 chunk（在读到 IDAT 前停止），返回 {key: value}。"""
    out = {}
    try:
        with open(path, "rb") as f:
            sig = f.read(8)
            if sig != b"\x89PNG\r\n\x1a\n":
                return out
            while True:
                head = f.read(8)
                if len(head) < 8:
                    break
                ln, typ = struct.unpack(">I4s", head)
                typ = typ.decode("latin1")
                if typ == "IEND":
                    break
                if typ in ("tEXt", "iTXt", "zTXt"):
                    limit = 64 * 1024 * 1024
                    if ln > limit:
                        f.seek(ln + 4, 1)
                        continue
                    data = f.read(ln)
                    if len(data) != ln:
                        break
                    f.seek(4, 1)  # Skip this text chunk's CRC before reading the next header.
                    try:
                        k, rest = data.split(b"\x00", 1)
                        compressed = False
                        if typ == "tEXt":
                            value = rest
                        elif typ == "iTXt":
                            if rest[0] not in (0, 1) or rest[1] != 0:
                                continue
                            compressed = rest[0] == 1
                            value = rest[2:].split(b"\x00", 2)[2]  # language, translated keyword, text
                        else:
                            if rest[0] != 0:
                                continue
                            compressed, value = True, rest[1:]
                        if compressed:
                            decoder = zlib.decompressobj()
                            value = decoder.decompress(value, limit + 1)
                            if len(value) > limit or not decoder.eof:
                                continue
                        out[k.decode("latin1")] = value.decode("utf-8", "replace")
                    except Exception:
                        pass
                else:
                    if typ == "IDAT":
                        break
                    f.seek(ln + 4, 1)
    except Exception:
        return out
    return out


def _walk_strings(obj, key_ctx=""):
    """深度遍历 JSON，产出 (key, string_value)。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk_strings(v, str(k))
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_strings(v, key_ctx)
    elif isinstance(obj, str):
        yield key_ctx, obj


def role_for_key(key: str, filename: str) -> str:
    for rx, role in KEY_ROLE_RULES:
        if rx.search(key or ""):
            return role
    if MODEL_FILE_RE.search(filename or ""):
        return "Other"
    return ""


def output_ancestors(graph):
    """Trace known image outputs; unknown output types remain graph references."""
    if not isinstance(graph, dict):
        return {}
    nodes = {str(k): v for k, v in graph.items() if isinstance(v, dict) and v.get("mode", 0) not in (2, 4)}
    roots = [key for key, node in nodes.items() if str(node.get("class_type", "")).lower() in
             ("saveimage", "previewimage", "saveanimatedwebp", "saveanimatedpng")]
    if not roots:
        return nodes
    visited, pending = set(), list(roots)
    while pending:
        key = pending.pop()
        if key in visited or key not in nodes:
            continue
        visited.add(key)
        inputs = nodes[key].get("inputs") or {}
        if not isinstance(inputs, dict):
            continue
        for value in inputs.values():
            if isinstance(value, list) and len(value) == 2 and isinstance(value[1], int) and str(value[0]) in nodes:
                pending.append(str(value[0]))
    return {key: node for key, node in nodes.items() if key in visited}


def extract_refs_from_graph(graph: dict) -> list:
    """从 ComfyUI prompt(API) 图中提取模型引用 [(filename, role)]。"""
    refs, seen = [], set()
    for _nid, node in output_ancestors(graph).items():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs") or {}
        if not isinstance(inputs, dict):
            continue
        for ik, iv in inputs.items():
            if isinstance(iv, str) and MODEL_FILE_RE.search(iv):
                role = role_for_key(ik, iv)
                key = (iv.lower(), role)
                if key not in seen:
                    seen.add(key)
                    refs.append({"filename": ntpath.basename(iv), "reference": iv.replace("/", "\\"), "role": role or "Other"})
    return refs


def extract_sampler_from_graph(graph: dict) -> dict:
    out = {}
    for _nid, node in output_ancestors(graph).items():
        if not isinstance(node, dict):
            continue
        ct = str(node.get("class_type") or "")
        if "sampler" in ct.lower() and not out.get("sampler"):
            inp = node.get("inputs") or {}
            if not isinstance(inp, dict):
                continue
            out["sampler"] = inp.get("sampler_name")
            out["steps"] = inp.get("steps")
            out["cfg"] = inp.get("cfg")
            out["seed"] = inp.get("seed", inp.get("noise_seed"))
    return out


def extract_prompts_from_graph(graph: dict) -> str:
    texts = []
    for _nid, node in output_ancestors(graph).items():
        if isinstance(node, dict) and str(node.get("class_type", "")).lower().find("textencode") >= 0:
            inp = node.get("inputs") or {}
            t = inp.get("text") if isinstance(inp, dict) else None
            if isinstance(t, str) and len(t.strip()) > 1:
                texts.append(t.strip())
    return " | ".join(texts)[:1000]


def parse_a1111_parameters(text: str) -> dict:
    """A1111 'parameters' 文本解析。"""
    out = {"engine": "a1111", "prompt": ""}
    if not text:
        return out
    parts = text.split("\nSteps:")
    out["prompt"] = (parts[0] or "")[:1000]
    tail = "Steps:" + (parts[1] if len(parts) > 1 else "")
    m = re.search(r"Model:\s*([^,]+)", tail)
    if m:
        out["checkpoint"] = m.group(1).strip()
    m = re.search(r"Steps:\s*(\d+)", tail)
    if m:
        out["steps"] = int(m.group(1))
    m = re.search(r"CFG scale:\s*([\d.]+)", tail)
    if m:
        out["cfg"] = float(m.group(1))
    m = re.search(r"Seed:\s*(\d+)", tail)
    if m:
        out["seed"] = m.group(1)
    m = re.search(r"Sampler:\s*([^,]+)", tail)
    if m:
        out["sampler"] = m.group(1).strip()
    refs = []
    m = re.search(r"Lora hashes:\s*\"([^\"]+)\"", tail)
    if m:
        for seg in m.group(1).split(","):
            if ":" in seg:
                name = seg.split(":")[0].strip().strip('"')
                refs.append({"filename": name, "role": "LoRA"})
    out["refs"] = refs
    return out


def png_size(data8: bytes):
    try:
        w, h = struct.unpack(">II", data8[16:24])
        return w, h
    except Exception:
        return None, None


def llm_family(filename: str) -> str:
    low = filename.lower()
    for hint, fam in FAMILY_HINTS:
        if hint in low:
            return fam
    return "其他"


def llm_info(filename: str) -> dict:
    """从文件名提取量化/参数量。"""
    out = {"quant": None, "params": None}
    m = QUANT_RE.search(filename)
    if m:
        out["quant"] = m.group(1)
    m = PARAMS_RE.search(filename)
    if m:
        out["params"] = m.group(1) + "B"
    return out
