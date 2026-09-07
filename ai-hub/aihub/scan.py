# -*- coding: utf-8 -*-
"""文件系统扫描：目录/文件清单 + 模型识别 + codex 目录(00_Management/Catalogs)导入。"""
import csv
import json
import os
import re
import time

from . import meta

# codex 目录 category -> 内部 mtype
CATEGORY_MAP = {
    "Checkpoint": "Checkpoint", "LoRA": "LoRA", "LoRA-Training": "LoRA",
    "Diffusion": "Diffusion", "TextEncoder": "TextEncoder", "VAE": "VAE",
    "ControlNet": "ControlNet", "Embedding": "Embedding", "IPAdapter": "IPAdapter",
    "Vision": "Vision", "Upscaler": "Upscaler", "Speech": "TTS", "Language": "LLM",
    "Topaz": "VideoAI", "ModelPackage": "Package", "PrivateWeight": "Private",
}


# 训练过程状态文件（非资产）：排除出模型库
TRAINING_STATE_RE = re.compile(
    r"^(optimizer|scheduler|random_states|schedules|current_states|lora_weights|"
    r"optimizer_states|step_|snr_|train_state)", re.I)


def _strip_extended(p: str) -> str:
    if p.startswith("\\\\?\\UNC\\"):
        return "\\\\" + p[8:]
    if p.startswith("\\\\?\\"):
        return p[4:]
    return p


def _is_reparse_stat(st) -> bool:
    return bool(getattr(st, "st_file_attributes", 0) & 0x400)


def _pref(p):
    """同一文件多入口时选择主展示路径：Library > Runtime > 旧根 > 应用私有。"""
    low = p.lower()
    if "\\library\\" in low:
        return 0
    if "\\runtime\\" in low:
        return 1
    if "\\ai_models\\" in low:
        return 2
    if "\\ai_apps\\" in low:
        return 3
    return 4


def scan_all(db, cfg, progress_cb=None):
    with db.asset_lock:
        return _scan_all(db, cfg, progress_cb)


def _scan_all(db, cfg, progress_cb=None):
    """完整扫描：返回 {file_count, dir_count, model_groups}，并把 files/dirs 写入数据库。"""
    roots = cfg.get("scan_roots") or [cfg.get("ai_root")]
    ignore = set(cfg.get("ignore_dirs") or [])
    dirs_agg = {}          # path -> [size, file_count, dir_count]
    dirs_rows_ignored = [] # 被忽略目录的占位行
    files_rows = []
    groups = {}            # inode -> {paths,size,mtime,ext}
    count = [0]
    seen_inodes = {}       # (dev,ino) -> size，仅模型文件（DirEntry.stat 无 st_ino）
    model_path_bytes = [0]  # 模型文件按路径累加的体积（含硬链接重复）
    model_unique_bytes = [0]  # 模型文件按唯一 inode 的体积

    def report(msg):
        if progress_cb:
            progress_cb(msg)

    def visit(dirpath, depth):
        try:
            entries = list(os.scandir(dirpath))
        except OSError:
            dirs_agg[dirpath] = [0, 0, 0]
            return
        size_acc, f_acc, d_acc = 0, 0, 0
        parent_name = os.path.basename(dirpath)
        for e in entries:
            try:
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            if e.is_dir(follow_symlinks=False):
                if _is_reparse_stat(st):
                    d_acc += 1  # junction/链接：计入但不深入
                    continue
                if e.name.lower() in ignore:
                    sub = _strip_extended(e.path)
                    dirs_rows_ignored.append((sub, dirpath, e.name, depth + 1, 0, 0, 0, 1))
                    d_acc += 1
                    continue
                visit(e.path, depth + 1)
                s, f, d = dirs_agg.get(e.path, [0, 0, 0])
                size_acc += s
                f_acc += f
                d_acc += 1 + d
            else:
                path = _strip_extended(e.path)
                ext = os.path.splitext(e.name)[1].lower()
                category, mtype = meta.classify_file(ext, parent_name)
                if category == "model" and TRAINING_STATE_RE.match(e.name):
                    category = "training"  # 训练状态文件，不入模型库
                ino_key = ""
                if category == "model":
                    try:
                        fst = os.stat(e.path, follow_symlinks=False)  # 完整 stat 才有真实 st_ino
                        ino_key = f"{fst.st_dev}:{fst.st_ino}"
                        if (fst.st_dev, fst.st_ino) not in seen_inodes:
                            seen_inodes[(fst.st_dev, fst.st_ino)] = st.st_size
                            model_unique_bytes[0] += st.st_size
                        model_path_bytes[0] += st.st_size
                        g = groups.setdefault(ino_key, {"paths": [], "size": st.st_size,
                                                        "mtime": st.st_mtime, "ext": ext})
                        g["paths"].append(path)
                    except OSError:
                        pass
                files_rows.append((path, dirpath, e.name, ext, st.st_size, st.st_mtime,
                                   category, mtype, ino_key))
                size_acc += st.st_size
                f_acc += 1
                if category == "model":
                    ino = f"{st.st_dev}:{st.st_ino}"
                    g = groups.setdefault(ino, {"paths": [], "size": st.st_size,
                                                "mtime": st.st_mtime, "ext": ext})
                    g["paths"].append(path)
                count[0] += 1
                if count[0] % 20000 == 0:
                    report(f"已扫描 {count[0]} 个文件…")
        dirs_agg[dirpath] = [size_acc, f_acc, d_acc]

    report("开始扫描目录树…")
    t0 = time.time()
    for r in roots:
        if os.path.isdir(r):
            visit(os.path.realpath(r), 0)

    report(f"目录树完成：{count[0]} 文件 / {len(dirs_agg)} 目录（{time.time()-t0:.0f}s），写入数据库…")
    dirs_rows = []
    for p, (s, f, d) in dirs_agg.items():
        parent = os.path.dirname(p)
        depth = p.rstrip("\\").count("\\")
        dirs_rows.append((p, parent, os.path.basename(p) or p, depth, s, f, d, 0))
    dirs_rows.extend(dirs_rows_ignored)
    db.replace_scan_tables(dirs_rows, files_rows)
    root_paths = [os.path.realpath(r) for r in roots if os.path.isdir(r)]
    dirs_agg_total = sum(dirs_agg.get(rp, [0, 0, 0])[0] for rp in root_paths)
    unique_size = dirs_agg_total - (model_path_bytes[0] - model_unique_bytes[0])
    db.set_meta("unique_size", str(unique_size))
    report("文件清单已入库，构建模型库…")
    return {"file_count": count[0], "dir_count": len(dirs_agg),
            "unique_size": unique_size, "model_groups": groups}


# ---------------- 模型库构建 ----------------

def build_models(db, cfg, scan_result, progress_cb=None):
    """导入 codex Catalogs + 现场扫描补充未编目模型。"""
    stats = {"catalog": 0, "filesystem": 0, "missing": 0}
    groups = scan_result["model_groups"]
    known_paths = set()

    def report(msg):
        if progress_cb:
            progress_cb(msg)

    def norm_path(p):
        if not p:
            return None
        try:
            return os.path.realpath(p)
        except Exception:
            return p

    # ---- 1. Catalogs: models.json + loras.csv + base_models.csv ----
    cat_dir = cfg.get("catalog_dir")
    entries = []
    csv_extra = {}
    if cat_dir and os.path.isfile(os.path.join(cat_dir, "models.json")):
        try:
            with open(os.path.join(cat_dir, "models.json"), encoding="utf-8") as f:
                data = json.load(f)
            entries = data.get("models") or []
            report(f"读取目录清单 models.json：{len(entries)} 条")
        except Exception as e:
            report(f"models.json 解析失败：{e}")
        for csv_name in ("loras.csv", "base_models.csv"):
            p = os.path.join(cat_dir, csv_name)
            if os.path.exists(p):
                try:
                    with open(p, encoding="utf-8-sig") as f:
                        for row in csv.DictReader(f):
                            csv_extra[row.get("id")] = row
                except Exception:
                    pass

    for ent in entries:
        canon = norm_path(ent.get("canonical_path") or ent.get("old_path"))
        if not canon:
            continue
        mtype = CATEGORY_MAP.get(ent.get("category"), ent.get("category") or None)
        extra = csv_extra.get(ent.get("id"), {})
        md = ent.get("metadata")
        meta_hdr = {k: str(v) for k, v in list(md.items())[:40]} if isinstance(md, dict) and md else {}
        exists = os.path.exists(canon)
        if not exists:
            stats["missing"] += 1
        filename = ent.get("filename") or os.path.basename(canon)
        alts = []
        for p in [norm_path(ent.get("runtime_path")), norm_path(ent.get("old_path"))]:
            if p and p != canon and p not in alts:
                alts.append(p)
        row = {
            "path": canon,
            "filename": filename,
            "norm_name": filename.lower(),
            "ext": os.path.splitext(canon)[1].lower(),
            "mtype": mtype or "Private",
            "family": ent.get("family") or None,
            "family_conf": ent.get("family_confidence") or None,
            "scope": ent.get("scope") or "central",
            "size": ent.get("bytes"),
            "mtime": (ent.get("mtime_ns") or 0) / 1e9 or None,
            "inode": str(ent.get("inode") or ""),
            "alt_paths": json.dumps(alts, ensure_ascii=False),
            "legacy_uid": ent.get("id"),
            "header_meta": json.dumps(meta_hdr, ensure_ascii=False) if meta_hdr else None,
            "trigger_words": _join_trigger(ent.get("trigger_candidates"))
                             or meta.extract_trigger_words(meta_hdr) or None,
            "training_base": extra.get("training_base") or meta_hdr.get("ss_sd_model_name") or None,
            "lrank": _f(extra.get("rank") or meta_hdr.get("ss_network_dim")),
            "lalpha": _f(extra.get("alpha") or meta_hdr.get("ss_network_alpha")),
            "method": extra.get("method") or ent.get("method") or None,
            "missing": 0 if exists else 1,
            "update_state": "unchecked",
        }
        db.upsert_model(row)
        known_paths.add(canon.lower())
        stats["catalog"] += 1
    report(f"目录清单导入完成：{stats['catalog']} 条（文件缺失 {stats['missing']}）")

    # ---- 2. 现场扫描补充（未编目的模型文件，如新下载）----
    for _ino, g in groups.items():
        paths = g["paths"]
        primary = sorted(paths, key=_pref)[0]
        if primary.lower() in known_paths:
            continue
        known_paths.add(primary.lower())
        db.upsert_model(_model_row_from_fs(primary, g, paths))
        stats["filesystem"] += 1
    report(f"现场补充新模型：{stats['filesystem']} 个")

    # ---- 3. 清理：非编目（现场发现）但已不在盘上的旧行 ----
    with db.lock:
        cur = db.conn.execute(
            "DELETE FROM models WHERE legacy_uid IS NULL AND path NOT IN "
            "(SELECT path FROM files WHERE category='model')")
        stats["pruned"] = cur.rowcount
        db.conn.commit()
    if stats["pruned"]:
        report(f"清理失效模型行：{stats['pruned']} 个")
    db.commit()
    return stats


def _f(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _join_trigger(cands) -> str:
    """trigger_candidates 元素可能是 str / dict（如 {'word':..,'score':..}）。"""
    out = []
    for c in cands or []:
        if isinstance(c, dict):
            c = c.get("word") or c.get("name") or c.get("text") or json.dumps(c, ensure_ascii=False)
        if c:
            out.append(str(c))
    return ", ".join(out)[:300]


def _model_row_from_fs(primary, g, all_paths):
    filename = os.path.basename(primary)
    ext = os.path.splitext(filename)[1].lower()
    parent = os.path.basename(os.path.dirname(primary))
    _category, mtype = meta.classify_file(ext, parent)
    hdr_meta, _tensor_count = (None, 0)
    raw_meta = None
    if ext == ".safetensors":
        raw_meta, _tensor_count = meta.read_safetensors_header(primary)
        hdr_meta = meta.header_summary(raw_meta or {})
        if not mtype:
            arch = (raw_meta or {}).get("modelspec.architecture", "")
            if arch:
                mtype = "LoRA" if "lora" in arch.lower() else "Checkpoint"
    family = (hdr_meta or {}).get("ss_base_model_version")
    if mtype == "LLM":
        family = meta.llm_family(filename)
    return {
        "path": primary,
        "filename": filename,
        "norm_name": filename.lower(),
        "ext": ext,
        "mtype": mtype or "Private",
        "family": family,
        "scope": "app-private" if "\\ai_apps\\" in primary.lower() else "central",
        "size": g["size"],
        "mtime": g["mtime"],
        "inode": None,
        "alt_paths": json.dumps([p for p in all_paths if p != primary], ensure_ascii=False),
        "header_meta": json.dumps(hdr_meta, ensure_ascii=False) if hdr_meta else None,
        "trigger_words": meta.extract_trigger_words(raw_meta or {}),
        "training_base": (hdr_meta or {}).get("ss_base_model_version"),
        "method": (hdr_meta or {}).get("ss_network_module"),
        "missing": 0,
        "update_state": "unchecked",
    }
