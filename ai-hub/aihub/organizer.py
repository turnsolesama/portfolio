"""Conservative, local asset organization through reversible hard-link entries.

Sources are never moved, rewritten, unpickled or removed. A hard link shares its
contents with the source; callers must communicate this before enabling it.
"""
import collections
import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import uuid

from . import classification, meta

LIBRARY_NAME = "00_AIHub_Library"
VERSION = 1
MAX_TRAVERSED_ENTRIES = 500000
_ID = re.compile(r"^[a-f0-9]{32}$")
_PRIVATE = re.compile(r"(?:^|[._\- ])(?:auth|credentials?|secrets?|tokens?|passwords?|api[_-]?keys?|private)(?:[._\- ]|$)|密钥|密码|凭据|隐私", re.I)
_SKIP_DIRS = {
    "apps", "ai_apps", "applications", "programs", "tools", "software", "应用", "软件",
    "venv", ".venv", "env", "envs", "node_modules", "site-packages", "python", "runtime",
    "python_embeded", "python_embedded", "lib", "scripts", "bin", "cache", "caches",
    "data", "backups", "backup", "备份", "releases", "build", "dist", "desktop",
    "projects", "project", "workspace", "workspaces", "repositories", "repos", "src", "项目", "工程",
    "training", "train", "ai_training", "datasets", "dataset", "training_data", "训练", "训练集", "训练数据",
    "library", "aihub_library", "models_library", "model_library", "分类库",
    "windows", "program files", "program files (x86)", "programdata", "appdata",
    "$recycle.bin", "system volume information", "recovery",
}
_PROJECT_MARKERS = {".git", "pyproject.toml", "package.json", "requirements.txt", "launch.py",
                    "webui-user.bat", "environment.yml", "cargo.toml", "go.mod", "model_index.json"}
_PRIVATE_FILES = {"auth.json", "profiles.json", "config.json", "settings.json", "manifest.json",
                  "package-lock.json", "cookies.txt", "login data", "local state"}
_SAFE_DOCS = {".md", ".txt", ".pdf", ".docx", ".doc", ".csv", ".xlsx"}
_MEDIA_CATS = {"image": "02_Images", "video": "03_Videos", "audio": "04_Audio",
               "workflow": "05_Workflows", "doc": "06_Documents"}
_KINDS = set(classification.MODEL_ROLES)
_DOMAINS = set(classification.DOMAINS)
_PURPOSES = set(classification.PURPOSES) | {"multiple"}


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _is_reparse(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _normal(path):
    if not isinstance(path, (str, os.PathLike)) or not os.fspath(path):
        raise ValueError("请选择有效的绝对目录")
    raw = os.fspath(path)
    if not os.path.isabs(raw) or raw.startswith(("\\\\", "//")) or "\x00" in raw:
        raise ValueError("仅支持本机磁盘上的绝对路径，不支持网络或设备路径")
    result = Path(os.path.abspath(raw))
    if os.name == "nt" and any(":" in part for part in result.parts[1:]):
        raise ValueError("路径不能包含备用数据流")
    return result


def _inside(path, root):
    try:
        return os.path.normcase(os.path.commonpath((str(path), str(root)))) == os.path.normcase(str(root))
    except ValueError:
        return False


def _chain(path, missing=False):
    """Check every ancestor before using a path; never resolve through junctions."""
    path = _normal(path)
    unseen = False
    info = None
    for entry in reversed((path, *path.parents)):
        try:
            info = os.lstat(entry)
        except FileNotFoundError:
            if not missing:
                raise ValueError("路径不存在") from None
            unseen = True
            continue
        if unseen or _is_reparse(info):
            raise ValueError("不允许符号链接、目录联接或其他重解析路径")
        if entry != path and not stat.S_ISDIR(info.st_mode):
            raise ValueError("路径祖先不是普通目录")
    return None if unseen else info


def _identity(info):
    return {"dev": info.st_dev, "ino": info.st_ino}


def _stamp(info):
    return {**_identity(info), "size": info.st_size, "mtime_ns": info.st_mtime_ns}


def _matches(info, expected):
    return not _is_reparse(info) and stat.S_ISREG(info.st_mode) and all(
        getattr(info, "st_" + key) == expected.get(key) for key in ("dev", "ino", "size", "mtime_ns"))


def validate_root(root):
    """Return a canonical ordinary local asset directory, or raise ValueError."""
    path = _normal(root)
    if os.name == "nt":
        import ctypes
        drive_type = ctypes.windll.kernel32.GetDriveTypeW
        drive_type.argtypes = [ctypes.c_wchar_p]
        drive_type.restype = ctypes.c_uint
        if drive_type(path.anchor) not in {2, 3, 6}:
            raise ValueError("安全区必须位于本地磁盘，不能使用映射网络盘")
    info = _chain(path)
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError("安全区必须是已经存在的普通目录")
    home = Path(os.path.abspath(os.path.expanduser("~")))
    if path == Path(path.anchor) or path in {home, home.parent}:
        raise ValueError("安全区不能是整个磁盘、用户根或所有用户目录")
    if _excluded_name(path.name) and path.name.casefold() not in {"library", "runtime", "packages"}:
        raise ValueError("程序、训练、隐私和已有分类目录不能设置为安全区")
    blocked = [os.environ.get(key) for key in ("WINDIR", "SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramData")]
    if any(value and _inside(path, Path(os.path.abspath(value))) for value in blocked):
        raise ValueError("系统和程序目录不能设置为安全区")
    if any(part.casefold() == LIBRARY_NAME.casefold() for part in path.parts):
        raise ValueError("分类库本身不能再次作为安全区")
    return str(path)


def _excluded_name(name):
    low = name.casefold()
    bare = re.sub(r"^\d+[_\- ]*", "", low)
    return low.startswith(".") or low == LIBRARY_NAME.casefold() or bare in _SKIP_DIRS or bool(_PRIVATE.search(low))


def _pack(entries):
    names = {entry.name.casefold() for entry in entries}
    if names & _PROJECT_MARKERS:
        return True
    if "config.json" in names and (names & {"tokenizer.json", "tokenizer_config.json", "pytorch_model.bin"}
                                    or any(name.endswith(".safetensors") for name in names)):
        return True
    # Caption/image pairs usually form a training set. Keep the package together.
    image_stems = {Path(name).stem for name in names if Path(name).suffix in meta.IMAGE_EXTS}
    return any(stem + ".txt" in names or stem + ".caption" in names for stem in image_stems)


def _workflow(path, size):
    if size > 2 * 1024 * 1024:
        return False
    try:
        with open(path, encoding="utf-8-sig") as handle:
            obj = json.load(handle)
        if not isinstance(obj, dict):
            return False
        nodes = obj.get("nodes")
        if isinstance(nodes, list) and isinstance(obj.get("links"), list):
            return bool(nodes) and all(isinstance(n, dict) and isinstance(n.get("type"), str) and "id" in n for n in nodes)
        return bool(obj) and all(str(k).isdigit() and isinstance(n, dict) and isinstance(n.get("class_type"), str)
                                 and isinstance(n.get("inputs"), dict) for k, n in obj.items())
    except (OSError, ValueError, RecursionError):
        return False


def _classify(path, info, root, model_context=None):
    ext = path.suffix.casefold()
    if path.name.casefold() in _PRIVATE_FILES or path.name.startswith(".") or _PRIVATE.search(path.name):
        return None
    if ext in meta.MODEL_EXTS - {".bin"}:
        kind = "Unknown"
        for part in reversed(path.parent.relative_to(root).parts):
            kind = meta.DIR_TYPE_MAP.get(part.casefold(), "Unknown")
            if kind != "Unknown":
                break
        header = {}
        if ext in {".safetensors", ".sft"}:
            header, _ = meta.read_safetensors_header(str(path))
            header = header if isinstance(header, dict) else {}
            if header.get("ss_network_module") or "lora" in str(header.get("modelspec.architecture", "")).lower():
                kind = "LoRA"
        inputs = classification.context_for(model_context, path, {"filename": path.name, "path": str(path),
                                             "alt_paths": [str(path)], "mtype": kind, "header_meta": header})
        result = classification.classify(**inputs)
        kind = result["model_role"]
        architecture = result["architecture"]
        purposes = result["purposes"]
        purpose = purposes[0] if len(purposes) == 1 else "multiple" if purposes else "uncategorized"
        category = "/".join(("01_Models", result["domain"], kind))
        if kind == "LoRA":
            category += "/" + purpose
        reason = result["domain_evidence"]
        if kind == "LoRA":
            reason += "；" + "、".join(result["purpose_labels"])
        return category, reason, {**result, "architecture": architecture, "evidence": result["domain_source"],
                                  "classification_input": inputs}
    category, _ = meta.classify_file(ext, path.parent.name)
    if category == "doc" and ext not in _SAFE_DOCS:
        return None
    if category == "workflow" and not _workflow(path, info.st_size):
        return None
    if category in _MEDIA_CATS:
        return _MEDIA_CATS[category], "按文件类型分类" if category != "workflow" else "已识别 ComfyUI 工作流结构", {}
    return None


def _category_valid(category):
    if category in _MEDIA_CATS.values():
        return True
    parts = str(category).split("/")
    return (len(parts) in {3, 4} and parts[0] == "01_Models" and parts[1] in _DOMAINS and parts[2] in _KINDS
            and ((parts[2] == "LoRA" and len(parts) == 4 and parts[3] in _PURPOSES)
                 or (parts[2] != "LoRA" and len(parts) == 3)))


def _target(root, source, category):
    if not _category_valid(category):
        raise ValueError("整理类别无效")
    rel = str(source.relative_to(root)).replace("\\", "/")
    suffix = hashlib.sha256(rel.casefold().encode("utf-8")).hexdigest()[:12]
    filename = source.stem[:100] + "__" + suffix + source.suffix
    return root / LIBRARY_NAME / Path(category) / filename


def library_policy(root):
    """An existing model library is a read-only virtual view, not another tree."""
    path = _normal(root)
    names = {"20_models", "library", "runtime", "packages"}
    found = []
    if path.name.casefold() in names:
        found.append(str(path))
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                if entry.name.casefold() in names and entry.is_dir(follow_symlinks=False):
                    found.append(entry.path)
    except OSError:
        pass
    existing = bool(found)
    return {"strategy": "existing_library_view" if existing else "portable_hardlinks",
            "apply_allowed": not existing, "existing_libraries": sorted(found),
            "policy_reason": "检测到已有模型库；仅提供统一分类视图，需单独审查实体目标策略" if existing else "便携安全区：预览后可建立可撤销硬链接入口"}


def build_plan(root, app_dir, ignore_dirs=(), max_files=50000, model_context=None):
    """Read only: budget new candidates separately from bounded traversal.

    Existing entries do not consume max_files, so subsequent runs can advance.
    A directory is eligible only after its complete contents were inspected for
    package markers; reaching the traversal cap never promotes a partial list.
    """
    root = Path(validate_root(root))
    policy = library_policy(root)
    virtual = not policy["apply_allowed"]
    if isinstance(max_files, bool) or not isinstance(max_files, int) or not 1 <= max_files <= 50000:
        raise ValueError("单次新增整理数量必须为 1 至 50000")
    ignore = [_normal(app_dir)] if app_dir else []
    for value in ignore_dirs:
        value = Path(value)
        ignore.append(_normal(value if value.is_absolute() else root / value))
    summary = {"scanned": 0, "planned": 0, "already_linked": 0, "excluded": 0, "unknown": 0,
               "logical_bytes": 0, "categories": {}, "traversed": 0,
               "candidate_limited": False, "traversal_limited": False, "compatibility_entries": 0,
               "indexed": 0, "registered": 0, "classification_pending": 0}
    plan = {"version": VERSION, "id": uuid.uuid4().hex, "root": str(root), "library": None if virtual else str(root / LIBRARY_NAME),
            **policy,
            "created_at": _now(), "root_identity": _identity(_chain(root)), "items": [], "summary": summary,
            "warnings": [], "app_dir": str(ignore[0]) if app_dir else "", "ignore_dirs": [str(p) for p in ignore]}
    queue = [root]
    counts = collections.Counter()
    examined = 0
    seen = {}
    def excluded(name):
        return _excluded_name(name) and not (virtual and name.casefold() in {"library", "runtime", "packages"})
    while queue:
        folder = queue.pop()
        try:
            _chain(folder)
            if any(_inside(folder, path) for path in ignore) or (folder != root and excluded(folder.name)):
                summary["excluded"] += 1
                continue
            with os.scandir(folder) as iterator:
                # Never classify a partially enumerated directory: a training
                # or application marker may be the first item beyond the cap.
                entries = []
                complete = True
                for entry in iterator:
                    examined += 1
                    if examined > MAX_TRAVERSED_ENTRIES:
                        complete = False
                        summary["traversal_limited"] = True
                        plan["warnings"].insert(0, f"已达到 {MAX_TRAVERSED_ENTRIES} 个目录项的遍历上限；当前目录未完整检查，已整体跳过。请缩小安全区或按子目录分别整理，重复本轮扫描不能保证覆盖剩余目录")
                        queue.clear()
                        break
                    entries.append(entry)
            if not complete:
                summary["excluded"] += len(entries) + 1
                continue
            if _pack(entries):
                summary["excluded"] += len(entries)
                continue
            for entry in sorted(entries, key=lambda x: x.name.casefold()):
                path = Path(entry.path)
                try:
                    info = entry.stat(follow_symlinks=False)
                    if _is_reparse(info) or excluded(entry.name):
                        summary["excluded"] += 1
                    elif stat.S_ISDIR(info.st_mode):
                        queue.append(path)
                    elif stat.S_ISREG(info.st_mode):
                        if virtual and any(p.casefold() in {"library", "runtime", "packages"} for p in path.parent.relative_to(root).parts) and path.suffix.casefold() not in meta.MODEL_EXTS - {".bin"}:
                            summary["excluded"] += 1
                            continue
                        summary["scanned"] += 1
                        # Windows DirEntry.stat() can report zero inode/device;
                        # use an explicit lstat for durable file identity.
                        info = _chain(path)
                        classified = _classify(path, info, root, model_context)
                        if not classified:
                            summary["unknown"] += 1
                            continue
                        category, reason, details = classified
                        identity = (info.st_dev, info.st_ino) if info.st_ino else str(path)
                        if identity in seen:
                            prior = seen[identity]
                            if str(path) not in prior["compatibility_paths"]:
                                prior["compatibility_paths"].append(str(path))
                            summary["compatibility_entries"] += 1
                            continue
                        target = None if virtual else _target(root, path, category)
                        current = _chain(target, missing=True) if target else None
                        if current is not None:
                            if _matches(current, _stamp(info)):
                                summary["already_linked"] += 1
                                seen[identity] = {"compatibility_paths": [str(path)]}
                            else:
                                summary["excluded"] += 1
                                plan["warnings"].append("分类入口冲突，已跳过：" + str(target.relative_to(root)))
                            continue
                        if len(plan["items"]) >= max_files:
                            summary["candidate_limited"] = True
                            plan["warnings"].insert(0, f"本轮已列出 {max_files} 个新增入口；执行本轮后再次预览，将跳过已建立的入口并继续后续候选")
                            queue.clear()
                            break
                        item = {"source": str(path), "target": str(target) if target else None, "category": category,
                                "reason": reason, **_stamp(info), **details}
                        item.setdefault("compatibility_paths", [])
                        item["compatibility_paths"] = [p for p in item["compatibility_paths"] if classification.path_key(p) != classification.path_key(path)]
                        plan["items"].append(item)
                        seen[identity] = item
                        for key in ("indexed", "registered", "classification_pending"):
                            summary[key] += bool(item.get(key))
                        summary["logical_bytes"] += info.st_size
                        counts[category] += 1
                except (OSError, ValueError) as exc:
                    summary["excluded"] += 1
                    plan["warnings"].append("跳过无法安全检查的项目：" + str(path.relative_to(root)) + "（" + type(exc).__name__ + "）")
        except (OSError, ValueError) as exc:
            summary["excluded"] += 1
            plan["warnings"].append("目录检查失败：" + str(folder.relative_to(root)) + "（" + type(exc).__name__ + "）")
    summary["planned"] = len(plan["items"])
    if virtual:
        # Existing package directories are deliberately not traversed. Indexed
        # weights inside them still appear through the same read-only identity
        # context used by the browser, without parsing package configuration.
        unique_inputs = {id(value): value for value in (model_context or {}).get("paths", {}).values()}
        for inputs in unique_inputs.values():
            model = inputs["model"]
            candidates = [model.get("path"), *classification._object(model.get("alt_paths"), [])]
            for candidate in candidates:
                if not candidate:
                    continue
                try:
                    source = _normal(candidate)
                    if not _inside(source, root) or any(_inside(source, p) for p in ignore):
                        continue
                    info = _chain(source)
                    if not stat.S_ISREG(info.st_mode) or not info.st_ino:
                        continue
                    identity = (info.st_dev, info.st_ino)
                    if identity in seen:
                        break
                    if len(plan["items"]) >= max_files:
                        summary["candidate_limited"] = True
                        break
                    result = classification.classify(**inputs)
                    category = "/".join(("01_Models", result["domain"], result["model_role"]))
                    if result["model_role"] == "LoRA":
                        purposes = result["purposes"]
                        category += "/" + (purposes[0] if len(purposes) == 1 else "multiple" if purposes else "uncategorized")
                    item = {"source": str(source), "target": None, "category": category,
                            "reason": result["domain_evidence"], **_stamp(info), **result,
                            "classification_input": inputs, "evidence": result["domain_source"]}
                    plan["items"].append(item)
                    seen[identity] = item
                    summary["logical_bytes"] += info.st_size
                    for key in ("indexed", "registered", "classification_pending"):
                        summary[key] += bool(result.get(key))
                    counts[category] += 1
                    break
                except (OSError, ValueError):
                    continue
    summary["planned"] = len(plan["items"])
    summary["traversed"] = min(examined, MAX_TRAVERSED_ENTRIES)
    summary["categories"] = dict(counts)
    plan["warnings"] = plan["warnings"][:200]
    return plan


def _mkdir(path):
    path = _normal(path)
    _chain(path, missing=True)
    for entry in reversed((path, *path.parents)):
        if _chain(entry, missing=True) is None:
            try:
                os.mkdir(entry)
            except FileExistsError:
                pass
        info = _chain(entry)
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError("目标父路径不是普通目录")


@contextlib.contextmanager
def _lock(journal_dir):
    folder = _normal(journal_dir)
    _mkdir(folder)
    path = folder / ".organizer.lock"
    info = _chain(path, missing=True)
    if info is not None and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
        raise ValueError("整理锁文件无效")
    with open(path, "a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError):
            raise ValueError("已有整理或撤销正在执行，请稍后重试") from None
        try:
            yield folder
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _append(handle, event):
    handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
    handle.flush()
    os.fsync(handle.fileno())


def _check_item(item, root, ignore=(), pack_cache=None, model_context=None):
    if not isinstance(item, dict):
        raise ValueError("计划项目格式无效")
    source, target = _normal(item.get("source")), _normal(item.get("target"))
    if not _inside(source, root) or source == root or _inside(source, root / LIBRARY_NAME):
        raise ValueError("源文件不在安全区内")
    if any(_inside(source, _normal(p)) for p in ignore):
        raise ValueError("源文件位于排除目录")
    if any(_excluded_name(part) for part in source.relative_to(root).parts):
        raise ValueError("源文件位于受保护目录或属于隐私配置")
    if target != _target(root, source, item.get("category")):
        raise ValueError("分类目标与计划规则不一致")
    info = _chain(source)
    if not _matches(info, item):
        raise ValueError("源文件在预览后发生变化，已跳过")
    if model_context is None and item.get("classification_input"):
        model_context = {"paths": {classification.path_key(source): item["classification_input"]}}
    classified = _classify(source, info, root, model_context)
    if not classified or classified[0] != item.get("category"):
        raise ValueError("源文件分类与计划不一致，请重新预览")
    if item.get("classification_input") and any(classified[2].get(key) != item.get(key)
                                                for key in ("scope", "model_role", "domain", "purposes", "architecture")):
        raise ValueError("分类维度在预览后发生变化，请重新预览")
    _chain(target, missing=True)
    # Directory packages may have gained markers after the preview.
    for folder in (source.parent, *source.parent.parents):
        if not _inside(folder, root):
            break
        folder_info = _chain(folder)
        cache_key = (str(folder), folder_info.st_ino, folder_info.st_mtime_ns)
        packed = pack_cache.get(cache_key) if pack_cache is not None else None
        if packed is None:
            with os.scandir(folder) as it:
                entries = []
                for index, entry in enumerate(it):
                    if index >= MAX_TRAVERSED_ENTRIES:
                        raise ValueError("父目录过大，无法安全复核")
                    entries.append(entry)
            packed = _pack(entries)
            if pack_cache is not None:
                pack_cache[cache_key] = packed
        if packed:
            raise ValueError("源文件属于程序、模型包或训练包，已跳过")
        if folder == root:
            break
    return source, target


def apply_plan(plan, journal_dir, model_context=None):
    """Create entries from a reviewed plan, without overwrites or source changes."""
    if not isinstance(plan, dict) or plan.get("version") != VERSION or not _ID.fullmatch(str(plan.get("id", ""))):
        raise ValueError("整理计划格式无效")
    root = Path(validate_root(plan.get("root")))
    if plan.get("strategy") == "existing_library_view" or plan.get("apply_allowed") is False or not library_policy(root)["apply_allowed"]:
        raise ValueError("已有模型库当前仅供虚拟预览，尚未批准实体目标策略，不能执行整理")
    if _identity(_chain(root)) != plan.get("root_identity"):
        raise ValueError("安全区已被替换，请重新预览")
    items = plan.get("items")
    if not isinstance(items, list) or len(items) > 50000:
        raise ValueError("整理计划项目数量无效")
    with _lock(journal_dir) as folder:
        run_id = uuid.uuid4().hex
        path = folder / (run_id + ".jsonl")
        result = {"id": run_id, "run_id": run_id, "created": 0, "skipped": 0, "errors": [], "root": str(root)}
        pack_cache = {}
        ignore = [*plan.get("ignore_dirs", []), *([plan["app_dir"]] if plan.get("app_dir") else [])]
        with open(path, "x", encoding="utf-8", newline="\n") as handle:
            _append(handle, {"event": "start", "version": VERSION, "id": run_id, "plan_id": plan["id"],
                             "root": str(root), "root_identity": plan["root_identity"], "created_at": _now()})
            for index, item in enumerate(items):
                try:
                    if _identity(_chain(root)) != plan["root_identity"]:
                        raise ValueError("安全区身份已改变")
                    source, target = _check_item(item, root, ignore, pack_cache, model_context)
                    if os.path.lexists(target):
                        result["skipped"] += 1
                        continue
                    _mkdir(target.parent)
                    source, target = _check_item(item, root, ignore, pack_cache, model_context)
                    if _chain(target.parent).st_dev != item["dev"]:
                        raise ValueError("硬链接只支持同一磁盘卷")
                    _append(handle, {"event": "intent", "index": index, "item": item})
                    try:
                        os.link(source, target, follow_symlinks=False)
                    except OSError:
                        # A competing creator may have won after the existence
                        # check. Its entry must never become ours during undo.
                        _append(handle, {"event": "link_failed", "index": index})
                        raise
                    if not _matches(_chain(target), item) or not _matches(_chain(source), item):
                        raise ValueError("创建后复核失败，保留入口并记录以供检查")
                    _append(handle, {"event": "created", "index": index})
                    result["created"] += 1
                except (OSError, ValueError, TypeError, KeyError) as exc:
                    result["skipped"] += 1
                    error = {"index": index, "source": item.get("source", "") if isinstance(item, dict) else "",
                             "message": str(exc) if isinstance(exc, ValueError) else type(exc).__name__}
                    result["errors"].append(error)
                    _append(handle, {"event": "error", **error})
            _append(handle, {"event": "complete", "created_at": _now(), **result})
        return result


def _read_run(folder, run_id):
    if not isinstance(run_id, str) or not _ID.fullmatch(run_id):
        raise ValueError("批次编号无效")
    path = folder / (run_id + ".jsonl")
    info = _chain(path)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 128 * 1024 * 1024:
        raise ValueError("批次记录无效")
    events, valid_size = [], 0
    with open(path, "rb") as handle:
        for line in handle:
            try:
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise ValueError("批次事件无效")
                events.append(event)
                valid_size += len(line)
            except (ValueError, RecursionError):
                # Only a truncated final append is recoverable.
                if handle.read():
                    raise ValueError("批次记录损坏") from None
                break
    if not events or events[0].get("event") != "start" or events[0].get("id") != run_id or events[0].get("version") != VERSION:
        raise ValueError("批次记录无效")
    return path, events, valid_size


def list_runs(journal_dir, root):
    """Return summaries for this exact safety root, including interrupted runs."""
    root = validate_root(root)
    folder = _normal(journal_dir)
    if _chain(folder, missing=True) is None:
        return []
    rows = []
    for path in folder.glob("*.jsonl"):
        try:
            _, events, _ = _read_run(folder, path.stem)
            start = events[0]
            if start.get("root") != root:
                continue
            complete = next((e for e in reversed(events) if e.get("event") == "complete"), {})
            latest = next((e for e in reversed(events) if e.get("event") in {"complete", "undo_complete"}), {})
            errors = latest.get("errors", [])
            undone = {e.get("index") for e in events if e.get("event") == "undone"}
            failed = {e.get("index") for e in events if e.get("event") == "link_failed"}
            intents = {e.get("index") for e in events if e.get("event") == "intent"} - failed
            rows.append({"id": path.stem, "run_id": path.stem, "created_at": start.get("created_at"), "root": root,
                         "created": complete.get("created", sum(e.get("event") == "created" for e in events)),
                         "skipped": complete.get("skipped", 0), "pending": len(intents - undone),
                         "undone": len(undone), "errors": len(errors),
                         "error_messages": [e.get("message", "操作失败") for e in errors[:10]],
                         "status": "partial" if errors else "undone" if intents and not intents - undone else "complete" if complete else "interrupted"})
        except (OSError, ValueError):
            continue
    return sorted(rows, key=lambda row: row.get("created_at") or "", reverse=True)[:100]


def undo_run(run_id, journal_dir, root):
    """Remove only unchanged hard-link entries recorded by this run."""
    root = Path(validate_root(root))
    with _lock(journal_dir) as folder:
        path, events, valid_size = _read_run(folder, run_id)
        start = events[0]
        if start.get("root") != str(root) or start.get("root_identity") != _identity(_chain(root)):
            raise ValueError("批次不属于当前安全区或安全区已被替换")
        done = {event.get("index") for event in events if event.get("event") == "undone"}
        failed = {event.get("index") for event in events if event.get("event") == "link_failed"}
        intents = {event.get("index"): event.get("item") for event in events
                   if event.get("event") == "intent" and event.get("index") not in failed}
        result = {"id": run_id, "run_id": run_id, "removed": 0, "skipped": 0, "errors": []}
        pack_cache = {}
        # Remove only an incomplete final append from this validated journal;
        # otherwise recovery events would be concatenated onto corrupt JSON.
        if path.stat().st_size != valid_size:
            with open(path, "r+b") as repair:
                repair.truncate(valid_size)
                repair.flush()
                os.fsync(repair.fileno())
        with open(path, "a", encoding="utf-8", newline="\n") as handle:
            for index, item in intents.items():
                if index in done:
                    continue
                try:
                    source, target = _check_item(item, root, pack_cache=pack_cache)
                    info = _chain(target, missing=True)
                    if info is None:
                        _append(handle, {"event": "undone", "index": index, "absent": True})
                        result["skipped"] += 1
                        continue
                    if not _matches(info, item) or info.st_nlink < 2 or not _matches(_chain(source), item):
                        raise ValueError("入口或原文件已变化，保留并跳过")
                    _append(handle, {"event": "undo_intent", "index": index})
                    # Recheck immediately before unlink. No recursive deletion is used.
                    if not _matches(_chain(target), item) or not _matches(_chain(source), item):
                        raise ValueError("入口或原文件已变化，保留并跳过")
                    os.unlink(target)
                    _append(handle, {"event": "undone", "index": index})
                    result["removed"] += 1
                except (OSError, ValueError, TypeError, KeyError) as exc:
                    result["skipped"] += 1
                    result["errors"].append({"index": index, "message": str(exc) if isinstance(exc, ValueError) else type(exc).__name__})
            _append(handle, {"event": "undo_complete", "created_at": _now(), **result})
        return result
