"""Portable data-only workflow packages with explicit, typed input bindings."""

import copy
import hashlib
import json
import math
import re
import threading
import time
from collections import deque
from pathlib import Path

from .diagnostics import safe_relative
from .workflows import _check_json_limits, _expanded_inputs, _spec

FORMAT = "frameweave-workflow"
MAX_BYTES = 2 * 1024 * 1024
TYPES = {"text", "integer", "number", "boolean", "select", "image"}
ID = re.compile(r"[A-Za-z0-9_-]{1,80}\Z")
RESERVED = {"__proto__", "prototype", "constructor"}
MODEL_INPUTS = {"ckpt_name", "unet_name", "clip_name", "vae_name", "lora_name", "clip_name1", "clip_name2"}


def encoded(value):
    _check_json_limits(value)
    pending = [value]
    while pending:
        current = pending.pop()
        if type(current) is int and abs(current) > 9007199254740991:
            raise ValueError("JSON 整数超过浏览器的精确范围；请将随机种子等数值设为 0–9007199254740991")
        if isinstance(current, dict):
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)
    content = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(content) > MAX_BYTES:
        raise ValueError("工作流包最大为 2 MiB；请只包含工作流与参数，不嵌入媒体或模型")
    return content


def text(value, label, maximum, empty=False):
    if not isinstance(value, str) or len(value) > maximum or (not empty and not value.strip()):
        raise ValueError(f"{label}须为不超过 {maximum} 字符的文本")
    return value.strip()


def is_link(value):
    return isinstance(value, list) and len(value) == 2 and isinstance(value[0], str) and type(value[1]) is int


def normalize_prompt(prompt):
    encoded(prompt)
    if not isinstance(prompt, dict) or not 1 <= len(prompt) <= 1000:
        raise ValueError("请导入包含 1–1000 个节点的 ComfyUI API 工作流")
    if isinstance(prompt.get("nodes"), list):
        raise ValueError("这是 ComfyUI 画布格式；请在 ComfyUI 开启开发者模式并选择导出 API 格式")
    result = {}
    dependencies = {}
    for node_id, node in prompt.items():
        if (not isinstance(node_id, str) or not 1 <= len(node_id) <= 100 or node_id in RESERVED
                or not isinstance(node, dict) or not isinstance(node.get("inputs"), dict)):
            raise ValueError("API 节点需要有效 ID、class_type 和 inputs 对象")
        node_type = text(node.get("class_type"), "节点类型", 256)
        inputs = copy.deepcopy(node["inputs"])
        if any(key in RESERVED or not key or len(key) > 256 for key in inputs):
            raise ValueError("节点输入名称无效")
        result[node_id] = {"class_type": node_type, "inputs": inputs}
        dependencies[node_id] = set()
        for value in inputs.values():
            if is_link(value):
                if value[0] not in prompt or value[1] < 0:
                    raise ValueError("工作流连接到不存在的节点或无效输出插槽")
                dependencies[node_id].add(value[0])
    pending = deque((node_id, 1) for node_id, deps in dependencies.items() if not deps)
    levels, count = {}, 0
    downstream = {key: [] for key in result}
    for key, deps in dependencies.items():
        for parent in deps:
            downstream[parent].append(key)
    while pending:
        key, level = pending.popleft()
        if level > 256:
            raise ValueError("工作流依赖链不能超过 256 层")
        count += 1
        for child in downstream[key]:
            dependencies[child].remove(key)
            levels[child] = max(levels.get(child, 1), level + 1)
            if not dependencies[child]:
                pending.append((child, levels[child]))
    if count != len(result):
        raise ValueError("工作流包含循环连接")
    return result


def scalar(value):
    return (type(value) in (str, int, float, bool)
            and (type(value) is not int or abs(value) <= 9007199254740991)
            and (type(value) is not float or math.isfinite(value)))


def validate_value(field, value, *, template=False):
    kind, label = field["type"], field["label"]
    if kind in {"text", "image"}:
        if not isinstance(value, str) or len(value) > (1024 if kind == "image" else 64000):
            raise ValueError(f"{label} 的文本类型或长度无效")
        if not value.strip() and field.get("required") and not template:
            raise ValueError(f"请填写 {label}")
        if kind == "image" and value:
            safe_relative(value)
    elif kind == "boolean":
        if type(value) is not bool:
            raise ValueError(f"{label} 必须是布尔值")
    elif kind in {"integer", "number"}:
        if (type(value) not in ((int,) if kind == "integer" else (int, float))
                or (type(value) is float and not math.isfinite(value))):
            raise ValueError(f"{label} 的数值类型无效")
        if abs(value) > 9007199254740991:
            raise ValueError(f"{label} 超出浏览器可精确表示的数值范围")
        if ("min" in field and value < field["min"]) or ("max" in field and value > field["max"]):
            raise ValueError(f"{label} 超出工作流包允许的范围")
    elif kind == "select":
        if not any(type(value) is type(option) and value == option for option in field["options"]):
            raise ValueError(f"{label} 不在可选值中")
    return value


def normalize_fields(fields, prompt):
    if not isinstance(fields, list) or len(fields) > 64:
        raise ValueError("工作流包最多开放 64 个输入参数")
    result, ids, bindings = [], set(), set()
    for item in fields:
        if not isinstance(item, dict):
            raise ValueError("参数定义必须为对象")
        field_id = item.get("id")
        if not isinstance(field_id, str) or not ID.fullmatch(field_id) or field_id in RESERVED or field_id in ids:
            raise ValueError("参数 ID 无效或重复")
        node_id, name = item.get("node_id"), item.get("input")
        if not isinstance(node_id, str) or not isinstance(name, str) or node_id not in prompt or name not in prompt[node_id]["inputs"]:
            raise ValueError("参数绑定的节点输入不存在")
        if (node_id, name) in bindings or is_link(prompt[node_id]["inputs"][name]):
            raise ValueError("不能重复绑定输入或覆盖节点连线")
        kind = item.get("type")
        if not isinstance(kind, str) or kind not in TYPES:
            raise ValueError("工作流包不支持此参数类型")
        field = {"id": field_id, "label": text(item.get("label"), "参数名称", 120),
                 "node_id": node_id, "input": name, "type": kind,
                 "required": item.get("required", kind == "image") is True}
        if kind == "select":
            options = item.get("options")
            if not isinstance(options, list) or not 1 <= len(options) <= 512 or any(not scalar(v) or (isinstance(v, str) and len(v) > 2048) for v in options):
                raise ValueError("下拉选项须为 1–512 个基础值")
            field["options"] = copy.deepcopy(options)
        if kind in {"integer", "number"}:
            for bound in ("min", "max"):
                if bound in item:
                    value = item[bound]
                    if type(value) not in (int, float) or abs(value) > 9007199254740991 or not math.isfinite(value):
                        raise ValueError("数值边界须为有限数字")
                    field[bound] = value
            if field.get("min", -math.inf) > field.get("max", math.inf):
                raise ValueError("数值下限不能大于上限")
        default = item.get("default", prompt[node_id]["inputs"][name])
        if kind == "image":
            default, field["required"] = "", True
            prompt[node_id]["inputs"][name] = ""
        field["default"] = validate_value(field, default, template=True)
        result.append(field)
        ids.add(field_id)
        bindings.add((node_id, name))
    return result


def normalize_document(document):
    encoded(document)
    if not isinstance(document, dict):
        raise ValueError("工作流包须为 JSON 对象")
    if document.get("format", FORMAT) != FORMAT or document.get("version", 1) != 1:
        raise ValueError("工作流包格式或版本不支持")
    prompt = normalize_prompt(document.get("prompt"))
    fields = normalize_fields(document.get("fields", []), prompt)
    for node_id, node in prompt.items():
        if node["class_type"] in {"LoadImage", "LoadImageMask"} and "image" in node["inputs"]:
            if not any(field["node_id"] == node_id and field["input"] == "image" and field["type"] == "image" for field in fields):
                raise ValueError("参考图节点必须开放图片上传参数，才能在其他设备上使用工作流包")
    result = {"format": FORMAT, "version": 1, "name": text(document.get("name"), "工作流包名称", 120),
              "description": text(document.get("description", ""), "说明", 2000, empty=True),
              "prompt": prompt, "fields": fields}
    encoded(result)
    return result


def inspect_document(document, info=None):
    encoded(document)
    if not isinstance(document, dict):
        raise ValueError("请导入 JSON 工作流对象")
    if "format" in document or "fields" in document:
        result = normalize_document(document)
        return {**result, "fields": [{**field, "recommended": True} for field in result["fields"]]}
    source = document.get("prompt", document)
    prompt = normalize_prompt(source)
    fields, info = [], info or {}
    labels = {"text": "提示词", "prompt": "画面提示词", "positive": "正向提示词", "negative": "负向提示词", "seed": "随机种子",
              "noise_seed": "随机种子", "steps": "采样步数", "cfg": "提示词引导", "width": "宽度",
              "height": "高度", "image": "参考图片", "denoise": "重绘强度", "batch_size": "生成数量", "length": "帧数"}
    polarity = {}
    for node in prompt.values():
        for key in ("positive", "negative"):
            link = node["inputs"].get(key)
            if is_link(link):
                polarity[link[0]] = labels[key]
    for node_id, node in prompt.items():
        schema = info.get(node["class_type"], {})
        specs, _ = _expanded_inputs(schema, node["inputs"]) if isinstance(schema, dict) else ({}, set())
        for name, value in node["inputs"].items():
            if not scalar(value) or len(fields) >= 64 or (type(value) is int and abs(value) > 9007199254740991):
                continue
            kind = "boolean" if type(value) is bool else "integer" if type(value) is int else "number" if type(value) is float else "text"
            spec, meta = _spec(specs[name]) if name in specs else (None, {})
            options = spec if isinstance(spec, list) else meta.get("options") if spec == "COMBO" else None
            if isinstance(options, list) and 1 <= len(options) <= 512 and all(scalar(v) for v in options):
                kind = "select"
            if node["class_type"] in {"LoadImage", "LoadImageMask"} and name == "image":
                kind, value = "image", ""
                prompt[node_id]["inputs"][name] = ""
            label = polarity.get(node_id, labels.get(name, name)) if name == "text" else labels.get(name, name)
            field = {"id": "f_" + hashlib.sha256((node_id + "\0" + name).encode()).hexdigest()[:16],
                     "label": f"{label} · {node_id}", "node_id": node_id, "input": name,
                     "type": kind, "default": value, "required": kind == "image",
                     "recommended": name in labels and name not in MODEL_INPUTS}
            if kind == "select":
                field["options"] = options
                if value not in options:
                    field["options"] = [value, *options][:512]
            if kind in {"integer", "number"}:
                for bound in ("min", "max"):
                    if type(meta.get(bound)) in (int, float):
                        clamped = max(-9007199254740991, min(9007199254740991, meta[bound]))
                        if math.isfinite(clamped):
                            field[bound] = clamped
            fields.append(field)
    return {"name": "我的生成工作流", "description": "", "prompt": prompt, "fields": fields,
            "requirements": {"nodes": sorted({node["class_type"] for node in prompt.values()})}}


def apply_values(document, values):
    normalized = normalize_document(document)
    encoded(values)
    if not isinstance(values, dict) or set(values) - {field["id"] for field in normalized["fields"]}:
        raise ValueError("输入包含工作流包没有定义的参数")
    prompt = copy.deepcopy(normalized["prompt"])
    for field in normalized["fields"]:
        value = validate_value(field, values.get(field["id"], field["default"]))
        prompt[field["node_id"]]["inputs"][field["input"]] = value
    return prompt


class PackageStore:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.lock = threading.RLock()

    def _path(self, package_id):
        if not isinstance(package_id, str) or not re.fullmatch(r"p-[0-9a-f]{24}", package_id):
            raise ValueError("工作流包 ID 无效")
        return self.directory / (package_id + ".json")

    def save(self, document):
        normalized = normalize_document(document)
        package_id = "p-" + hashlib.sha256(encoded(normalized)).hexdigest()[:24]
        with self.lock:
            self.directory.mkdir(exist_ok=True, parents=True)
            path = self._path(package_id)
            if path.is_file():
                return self.get(package_id)
            if sum(1 for _ in self.directory.glob("p-*.json")) >= 200:
                raise ValueError("当前工作流包库最多保存 200 个包")
            temp = path.with_suffix(".tmp")
            temp.write_bytes(encoded(normalized))
            temp.replace(path)
            return self.get(package_id)

    def get(self, package_id):
        path = self._path(package_id)
        with self.lock:
            try:
                with path.open("rb") as stream:
                    data = stream.read(MAX_BYTES + 1)
                if len(data) > MAX_BYTES:
                    raise ValueError("工作流包文件超过大小上限")
                try:
                    document = normalize_document(json.loads(data))
                except RecursionError:
                    raise ValueError("工作流包 JSON 嵌套过深") from None
            except FileNotFoundError:
                raise ValueError("工作流包未在本机安装，请先导入对应工作流包") from None
            if "p-" + hashlib.sha256(encoded(document)).hexdigest()[:24] != package_id:
                raise ValueError("工作流包内容已变化，请重新导入")
            return {**document, "id": package_id, "created_at": path.stat().st_mtime,
                    "updated_at": path.stat().st_mtime,
                    "requirements": {"nodes": sorted({node["class_type"] for node in document["prompt"].values()})}}

    def list(self):
        packages = []
        for path in list(self.directory.glob("p-*.json"))[:200]:
            try:
                package = self.get(path.stem)
                package.pop("prompt")
                packages.append(package)
            except (ValueError, OSError):
                continue
        return sorted(packages, key=lambda item: item["updated_at"], reverse=True)

    def export(self, package_id):
        return normalize_document(self.get(package_id))
