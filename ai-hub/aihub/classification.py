"""Functional browsing categories derived from recorded evidence and user labels.

This module does not inspect weights, execute models, move files or contact sources.
Architecture compatibility remains separate from a model's intended use.
"""
import collections
import json
import re

DOMAINS = {
    "image": {"label": "图片创作", "description": "绘图、图像编辑与配套模型", "icon": "image"},
    "video": {"label": "视频制作", "description": "视频生成、动作与画质处理", "icon": "video"},
    "language": {"label": "语言与对话", "description": "文本生成、对话与推理", "icon": "message"},
    "audio": {"label": "语音与音乐", "description": "配音、声音与音乐生成", "icon": "audio"},
    "vision": {"label": "视觉工具", "description": "识别、分割与图像分析", "icon": "scan"},
    "shared": {"label": "通用组件", "description": "用途未绑定的编码器等组件", "icon": "cpu"},
    "unknown": {"label": "用途待确认", "description": "现有证据不足，支持手动归类", "icon": "folder"},
}
PURPOSES = {
    "style": "风格画风", "character": "角色人物", "lighting": "光照氛围",
    "detail": "细节材质", "composition": "姿态构图", "outfit": "服饰造型",
    "scene": "场景物件", "motion": "动作运镜", "acceleration": "采样加速",
    "concept": "其他概念", "uncategorized": "用途待补充",
}
LOOSE_ROLES = {"Character_Identity": "character", "Acceleration": "acceleration"}

# These are purpose suggestions, not architecture or quality claims. Training-tag
# frequencies are deliberately excluded: a style dataset can contain many characters.
PURPOSE_RULES = {
    "acceleration": r"turbo|lightning|hyper[-_ ]?sd|(?:^|[^a-z])lcm(?:[^a-z]|$)|[248][- _]?step|采样加速|加速",
    "lighting": r"lighting|(?:^|[^a-z])light(?:[^a-z]|$)|backlight|rimlight|relight|光照|光源|光影|氛围感光|逆光|补光",
    "detail": r"detail|texture|skin|材质|质感|肌肤|皮肤|细节|细化",
    "style": r"style|artstyle|illustration|painting|watercolor|风格|画风|厚涂|水彩|油画|版画|水墨|半写实",
    "character": r"character|identity|faceid|肖像|人物|角色|身份",
    "composition": r"composition|(?:^|[^a-z])pose(?:[^a-z]|$)|(?:^|[^a-z])pov(?:[^a-z]|$)|构图|姿态|姿势|视角",
    "outfit": r"outfit|clothing|costume|fashion|服装|服饰|穿搭|造型",
    "scene": r"landscape|background|architecture|environment|场景|背景|建筑|风景|物件|道具",
    "motion": r"camera[-_ ]?motion|camera[-_ ]?move|(?:^|[^a-z])motion(?:[^a-z]|$)|运镜|镜头运动|动作控制",
}
FOLDER_RULES = {
    "style": r"^(?:风格(?:类)?(?:lora)?|sd1[._]?5风格|styles?|art_styles)$",
    "character": r"^(?:人物(?:类)?(?:lora)?|角色(?:类)?(?:lora)?|characters?|identity)$",
    "lighting": r"^(?:光影(?:lora)?|光源|光照|lighting)$",
    "detail": r"^(?:细节|材质|details?|textures?)$",
    "composition": r"^(?:姿势|姿态|构图|poses?|composition)$",
    "outfit": r"^(?:服装|服饰|clothing|outfits?)$",
    "scene": r"^(?:场景|背景|物件|scenes?|objects?)$",
    "motion": r"^(?:动作|运镜|motion)$",
    "acceleration": r"^(?:加速|acceleration)$",
}


def _object(value, fallback):
    if isinstance(value, type(fallback)):
        return value
    try:
        parsed = json.loads(value or "null")
        return parsed if isinstance(parsed, type(fallback)) else fallback
    except (TypeError, ValueError):
        return fallback


def family_domain(value):
    key = re.sub(r"[^a-z0-9]", "", str(value or "").casefold())
    if key.startswith(("qwenimage", "qwenimageanima")):
        return "image"
    if key.startswith(("minimaxmusic", "speech", "stableaudio", "audioldm", "bark", "whisper")):
        return "audio"
    if key.startswith(("hunyuanvideo", "wan2", "wanvideo", "minimaxh3", "ltxvideo", "ltx2", "cogvideo", "mochi", "hunyuanworld")) or key in {"wan", "ltx", "topaz"}:
        return "video"
    if key.startswith(("stablediffusion", "sdxl", "sd15", "sd3", "flux", "anima", "zimage", "krea2", "pixart", "hidream", "auraflow")):
        return "image"
    if key in {"vision", "sam", "sam2", "birefnet", "groundingdino", "insightface", "florence2"}:
        return "vision"
    if key == "upscaler":
        return "image"
    if key in {"language", "llama", "mistral", "gemma", "deepseek", "glm", "internlm"}:
        return "language"
    return None


def _automatic_domain(model, audit, metadata):
    kind = model.get("mtype") or audit.get("category")
    if kind in {"LLM", "Language"}:
        return "language", "record", "已记录为语言模型"
    if kind in {"TTS", "Speech", "Audio"}:
        return "audio", "record", "已记录为语音/音频模型"
    if kind in {"Vision", "CLIPVision"}:
        return "vision", "record", "已记录为视觉识别/分析组件"
    for value in (metadata.get("modelspec.architecture"), metadata.get("ss_base_model_version")):
        domain = family_domain(value)
        if domain:
            return domain, "metadata", "模型内嵌架构：" + str(value)
    family = audit.get("family") or model.get("family")
    domain = family_domain(family)
    if domain:
        confidence = audit.get("family_confidence") or model.get("family_conf")
        return domain, "architecture" if confidence == "confirmed" else "suggested", "架构记录：" + str(family) + ("（已有结构证据）" if confidence == "confirmed" else "（包含推断）")
    if kind == "VideoAI":
        return "video", "record", "已记录为视频处理模型"
    if kind in {"Upscaler", "IPAdapter", "ControlNet"}:
        return "image", "suggested", "按已记录组件类型建议；具体兼容架构仍需核对"
    paths = [audit.get("old_path", ""), *(_object(model.get("alt_paths"), []))]
    parts = [part.casefold() for path in paths for part in re.split(r"[\\/]", str(path))]
    if any(part in {"视频lora", "video_lora", "video_loras"} for part in parts):
        return "video", "folder", "沿用原目录中的视频 LoRA 分类，架构仍待核对"
    if any(part in {"图像lora", "风格lora", "人物lora", "sd1.5风格"} for part in parts):
        return "image", "folder", "沿用原目录中的图片 LoRA 分类，架构仍待核对"
    if kind in {"TextEncoder", "VAE", "Embedding"}:
        return "shared", "record", "配套组件；尚无足够证据绑定创作用途"
    return "unknown", "unknown", "现有类型和架构记录不足以确定用途"


def _automatic_purposes(model, audit, metadata):
    reasons = {}
    for key in ("aihub.purposes", "modelspec.purposes"):
        supplied = _object(metadata.get(key), [])
        for purpose in supplied:
            if isinstance(purpose, str) and purpose in PURPOSES and purpose != "uncategorized":
                reasons[purpose] = "模型内嵌用途字段"
    if reasons:
        return reasons, "metadata"
    text = " ".join(str(metadata.get(key, "")) for key in ("modelspec.title", "modelspec.description", "modelspec.tags"))
    name = str(model.get("filename", ""))
    for purpose, pattern in PURPOSE_RULES.items():
        if re.search(pattern, text, re.I):
            reasons[purpose] = "根据内嵌标题、描述或标签建议"
        elif re.search(pattern, name, re.I):
            reasons[purpose] = "根据文件名称建议，尚未验证实际效果"
    if reasons:
        return reasons, "suggested"
    # Only explicit original categories are useful. The generated Library/Style_Other
    # catch-all is not evidence that an unknown concept is a style LoRA.
    paths = [audit.get("old_path", ""), *(_object(model.get("alt_paths"), [])), model.get("path", "")]
    parts = [part.casefold() for path in paths for part in re.split(r"[\\/]", str(path))]
    for purpose, pattern in FOLDER_RULES.items():
        if any(re.search(pattern, part) for part in parts):
            reasons[purpose] = "沿用原目录的明确用途分类"
    if reasons:
        return reasons, "folder"
    role = LOOSE_ROLES.get(audit.get("role"))
    if role:
        return {role: "沿用台账用途记录，支持进一步调整"}, "suggested"
    return {"uncategorized": "尚无明确用途；旧的风格/其他、细节/光照混合分组未当作确定结论"}, "unknown"


def classify(model, audit=None, manual=None):
    audit, manual = audit or {}, manual or {}
    metadata = {**_object(model.get("header_meta"), {}), **_object(audit.get("metadata"), {})}
    domain, domain_source, domain_evidence = _automatic_domain(model, audit, metadata)
    if isinstance(manual.get("domain"), str) and manual["domain"] in DOMAINS:
        domain, domain_source, domain_evidence = manual["domain"], "manual", "用户指定的用途分类"
    is_lora = (model.get("mtype") or audit.get("category")) in {"LoRA", "LoRA-Training"}
    reasons, purpose_source = _automatic_purposes(model, audit, metadata) if is_lora else ({}, "none")
    if is_lora and manual.get("purposes") is not None:
        purposes = _object(manual["purposes"], [])
        reasons = {p: "用户指定的 LoRA 用途" for p in purposes if isinstance(p, str) and p in PURPOSES}
        if not reasons:
            reasons = {"uncategorized": "用户保留为待补充"}
        purpose_source = "manual"
    return {"domain": domain, "domain_label": DOMAINS[domain]["label"],
            "domain_source": domain_source, "domain_evidence": domain_evidence,
            "purposes": [p for p in PURPOSES if p in reasons],
            "purpose_labels": [PURPOSES[p] for p in PURPOSES if p in reasons],
            "purpose_source": purpose_source, "purpose_evidence": reasons,
            "manual_domain": manual.get("domain"),
            "manual_purposes": _object(manual.get("purposes"), []) if manual.get("purposes") is not None else None}


def decorate(rows, catalog, labels):
    audit_index = {item.get("id"): item for item in catalog.get("models", []) if item.get("id")}
    manual_index = {row["model_path"]: dict(row) for row in labels}
    return {row["rowid_pk"]: classify(dict(row), audit_index.get(row["legacy_uid"]), manual_index.get(row["path"])) for row in rows}


def facets(rows, classifications):
    counts = collections.Counter(classifications[row["rowid_pk"]]["domain"] for row in rows)
    return [{"id": key, **value, "count": counts[key]} for key, value in DOMAINS.items()]
