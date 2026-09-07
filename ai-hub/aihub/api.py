# -*- coding: utf-8 -*-
"""HTTP API 路由。所有 /api/* 由 dispatch() 处理。"""
import json
import collections
import mimetypes
import os
import re
import shutil
import time
import urllib.parse

from . import config as cfgmod
from . import jobs
from . import updater as upd
from . import management
from . import classification
from . import images as image_store, meta, recycle
from .db import jload

_started = time.time()


# ---------- 工具 ----------

def _json_bytes(obj, status=200):
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    return status, {"Content-Type": "application/json; charset=utf-8",
                    "Cache-Control": "no-store"}, body


def _err(msg, status=400):
    return _json_bytes({"error": msg}, status)


def _q(params, key, default=None):
    v = params.get(key, default)
    return v[0] if isinstance(v, list) else v


def _int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def human_size(n):
    if n is None:
        return "-"
    for u in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or u == "TB":
            return f"{n:.1f} {u}" if u != "B" else f"{int(n)} B"
        n /= 1024.0
    return f"{n:.1f} TB"


def _now():
    return time.time()


def value_fields(row: dict) -> dict:
    """使用价值评分与标签（公式透明可解释）。"""
    img = row.get("img_count") or 0
    days = min(row.get("days_used") or 0, 30) / 30.0
    lu = row.get("last_used")
    recency = max(0.0, 1.0 - (_now() - lu) / (180 * 86400)) if lu else 0.0
    rating = (row.get("rating") or 0) / 10.0
    score = 100 * (0.45 * min(img, 120) / 120 + 0.25 * recency + 0.15 * days + 0.15 * rating)
    age_days = (_now() - (row.get("mtime") or 0)) / 86400
    if img >= 50:
        tag = "高频核心"
    elif img >= 10:
        tag = "常用"
    elif img >= 1:
        tag = "低频"
    elif age_days > 14:
        tag = "暂无引用"
    else:
        tag = "新入库"
    return {"value_score": round(score, 1), "value_tag": tag,
            "age_days": round(age_days, 1) if row.get("mtime") else None}


def _row_json(row: dict) -> dict:
    d = dict(row)
    d["alt_paths"] = jload(d.get("alt_paths"), [])
    d["header_meta"] = jload(d.get("header_meta"), {})
    d["training_base"] = d.get("training_base") or d["header_meta"].get("ss_sd_model_name")
    d["lrank"] = d.get("lrank") or d["header_meta"].get("ss_network_dim")
    d["lalpha"] = d.get("lalpha") or d["header_meta"].get("ss_network_alpha")
    d.update(value_fields(d))
    d["size_h"] = human_size(d.get("size"))
    if d.get("last_used"):
        d["last_used_h"] = time.strftime("%Y-%m-%d", time.localtime(d["last_used"]))
    return d


def _whitelisted(path: str) -> bool:
    try:
        real = os.path.realpath(path)
    except Exception:
        return False
    real_l = real.lower().rstrip("\\")
    for root in _allowed_roots():
        r_l = os.path.realpath(root).lower().rstrip("\\")
        if real_l == r_l or real_l.startswith(r_l + os.sep):
            return True
    return False


def _allowed_roots():
    roots = [os.path.realpath(r) for r in (APP_CFG.get("scan_roots") or [])]
    roots += [os.path.realpath(r) for r in (APP_CFG.get("output_roots") or [])]
    ai_root = APP_CFG.get("ai_root")
    if ai_root:
        roots.append(os.path.realpath(ai_root))
    return roots


APP_DB = None
APP_CFG = {}


# ---------- 路由 ----------

def overview(db, cfg, params, body):
    parts = []
    roots = cfg.get("scan_roots") or []
    for r in roots:
        row = db.one("SELECT * FROM dirs WHERE path=?", (os.path.realpath(r),))
        name = os.path.basename(r.rstrip("\\"))
        aliases = [a for a, t in (cfg.get("aliases") or {}).items()
                   if os.path.realpath(a).lower() == r.lower()]
        parts.append({
            "name": name,
            "alias": aliases[0] if aliases else None,
            "path": r,
            "size": row["size"] if row else 0,
            "files": row["file_count"] if row else 0,
            "dirs": row["dir_count"] if row else 0,
            "size_h": human_size(row["size"] if row else 0),
        })
    total_size = sum(p["size"] for p in parts)
    total_files = sum(p["files"] for p in parts)

    mtype_counts = {r["mtype"] or "未分类": r["c"] for r in
                    db.query("SELECT mtype, COUNT(*) c FROM models GROUP BY mtype")}
    family_counts = [(r["family"] or "未知", r["c"]) for r in
                     db.query("SELECT family, COUNT(*) c FROM models WHERE mtype IN "
                              "('Checkpoint','LoRA','Diffusion','TextEncoder','VAE','ControlNet') "
                              "GROUP BY family ORDER BY c DESC LIMIT 12")]
    state_counts = {r["update_state"]: r["c"] for r in
                    db.query("SELECT update_state, COUNT(*) c FROM models GROUP BY update_state")}
    img_stats = db.one("SELECT COUNT(*) n, SUM(has_meta) m FROM images")
    ref_stats = db.one("SELECT COUNT(DISTINCT model_path) models, COUNT(*) refs "
                       "FROM img_refs WHERE model_path IS NOT NULL")
    ghost = jload(db.get_meta("ghost_refs"), [])
    disk_root = cfg.get("ai_root") or cfgmod.APP_DIR
    disk = shutil.disk_usage(disk_root if os.path.isdir(disk_root) else cfgmod.APP_DIR)
    top_used = [ _row_json(r) for r in db.query(
        "SELECT * FROM models WHERE img_count > 0 ORDER BY img_count DESC LIMIT 8")]
    recent = [_row_json(r) for r in db.query(
        "SELECT * FROM models WHERE missing=0 ORDER BY mtime DESC LIMIT 8")]
    pending = db.one("SELECT COUNT(*) c FROM models WHERE update_state IN ('available','maybe')")["c"]
    all_models = db.query("SELECT * FROM models")
    categories = classification.decorate(all_models, management.catalog(cfg), db.query("SELECT * FROM model_labels"))

    return _json_bytes({
        "ai_root": cfg.get("ai_root"),
        "disk": {"total": disk.total, "free": disk.free, "used_pct": round(100 * disk.used / disk.total, 1)},
        "parts": parts, "total_size": total_size, "total_size_h": human_size(total_size),
        "unique_size": int(db.get_meta("unique_size") or 0),
        "unique_size_h": human_size(int(db.get_meta("unique_size") or 0)),
        "total_files": total_files,
        "model_count": sum(mtype_counts.values()),
        "functional_categories": classification.facets(all_models, categories),
        "central_counts": {r["mtype"]: r["c"] for r in db.query("SELECT mtype,COUNT(*) c FROM models WHERE scope='central' GROUP BY mtype")},
        "mtype_counts": mtype_counts, "family_counts": family_counts,
        "state_counts": state_counts, "pending_updates": pending,
        "image_count": img_stats["n"] or 0, "image_with_meta": img_stats["m"] or 0,
        "used_models": ref_stats["models"] or 0, "ref_count": ref_stats["refs"] or 0,
        "ghost_refs": ghost[:12], "ghost_count": len(ghost),
        "scan_at": db.get_meta("scan_at"), "image_scan_at": db.get_meta("image_scan_at"),
        "update_check_at": db.get_meta("update_check_at"),
        "top_used": top_used, "recent_models": recent,
        "uptime_s": int(_now() - _started),
    })


def models_list(db, cfg, params, body):
    domain, purpose = _q(params, "domain"), _q(params, "purpose")
    if domain and domain not in classification.DOMAINS:
        return _err("未知的功能分类")
    if purpose and purpose not in classification.PURPOSES:
        return _err("未知的 LoRA 用途")
    conds, args = [], []
    if _q(params, "kind") == "core":
        conds.append("mtype IN ('Checkpoint','Diffusion','LoRA')")
    elif _q(params, "kind") == "base":
        conds.append("mtype IN ('Checkpoint','Diffusion','LLM','TTS','Package')")
    elif _q(params, "kind") == "components":
        conds.append("mtype NOT IN ('Checkpoint','Diffusion','LLM','TTS','Package','LoRA')")
    if _q(params, "ids") is not None:
        ids = [int(value) for value in str(_q(params, "ids")).split(",") if value.isdigit()][:500]
        conds.append("rowid_pk IN (" + ",".join("?" for _ in ids) + ")" if ids else "0=1")
        args += ids
    if _q(params, "type"):
        conds.append("mtype=?"); args.append(_q(params, "type"))
    if _q(params, "family"):
        conds.append("family=? COLLATE NOCASE"); args.append(_q(params, "family"))
    if _q(params, "scope"):
        conds.append("scope=?"); args.append(_q(params, "scope"))
    st = _q(params, "state")
    if st == "pending":
        conds.append("update_state IN ('available','maybe')")
    elif st == "unchecked":
        conds.append("update_state='unchecked'")
    elif st:
        conds.append("update_state=?"); args.append(st)
    if _q(params, "usage") == "unused":
        conds.append("(img_count IS NULL OR img_count=0)")
    elif _q(params, "usage") == "used":
        conds.append("img_count>0")
    q = _q(params, "q")
    if q:
        conds.append("(filename LIKE ? OR IFNULL(trigger_words,'') LIKE ? OR IFNULL(source_url,'') LIKE ? OR COALESCE(training_base,header_meta,'') LIKE ? OR IFNULL(family,'') LIKE ?)")
        args += [f"%{q}%"] * 5
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    sort_map = {
        "mtime": "mtime DESC", "size": "size DESC", "name": "filename COLLATE NOCASE ASC",
        "usage": "img_count DESC", "score": "img_count DESC", "family": "family, filename",
    }
    order = sort_map.get(_q(params, "sort") or "", "mtime DESC")
    page = max(1, _int(_q(params, "page"), 1))
    size = min(200, max(10, _int(_q(params, "size"), 50)))
    all_rows = db.query("SELECT * FROM models")
    categories = classification.decorate(all_rows, management.catalog(cfg), db.query("SELECT * FROM model_labels"))
    rows = db.query(f"SELECT * FROM models {where} ORDER BY {order}, rowid_pk", args)
    if domain:
        rows = [r for r in rows if categories[r["rowid_pk"]]["domain"] == domain]
    purpose_counts = collections.Counter(p for r in rows for p in categories[r["rowid_pk"]]["purposes"])
    if purpose:
        rows = [r for r in rows if purpose in categories[r["rowid_pk"]]["purposes"]]
    total = len(rows)
    page = min(page, max(1, (total + size - 1) // size))
    items = [_row_json(r) for r in rows[(page - 1) * size:page * size]]
    for it in items:
        it["partition"] = _partition_of(cfg, it["path"])
        it["classification"] = categories[it["rowid_pk"]]
    scope_rows = [r for r in all_rows if not _q(params, "scope") or r["scope"] == _q(params, "scope")]
    facet_rows = [r for r in scope_rows if not domain or categories[r["rowid_pk"]]["domain"] == domain]
    facets = {
        "types": sorted({r["mtype"] for r in facet_rows if r["mtype"]}),
        "families": sorted({r["family"] for r in facet_rows if r["family"] and r["family"] != 'Unknown'}, key=str.casefold),
        "domains": classification.facets(scope_rows, categories),
        "purposes": [{"id": key, "label": value, "count": purpose_counts[key]} for key, value in classification.PURPOSES.items()],
        "options": {"domains": classification.DOMAINS, "purposes": classification.PURPOSES},
    }
    return _json_bytes({"total": total, "page": page, "size": size,
                        "items": items, "facets": facets})


def _find_preview(path: str):
    """模型同名预览图约定：stem.preview.png / stem.png / stem.jpg / stem.webp。"""
    base, _ = os.path.splitext(path)
    for cand in (base + ".preview.png", base + ".png", base + ".jpg", base + ".jpeg", base + ".webp"):
        if os.path.isfile(cand):
            return cand
    return None


def model_detail(db, cfg, params, body):
    mid = _int(params.get("id"))
    row = db.one("SELECT * FROM models WHERE rowid_pk=?", (mid,))
    if not row:
        return _err("model not found", 404)
    d = _row_json(row)
    d["preview_path"] = _find_preview(d["path"])
    # 相关图片
    d["images"] = [{"path": r["image_path"], "role": r["role"]} for r in db.query(
        "SELECT image_path, role FROM img_refs WHERE model_path=? ORDER BY 1 DESC LIMIT 24", (row["path"],))]
    d["image_total"] = db.one("SELECT COUNT(*) c FROM img_refs WHERE model_path=?", (row["path"],))["c"]
    # 重复/多入口
    dups = []
    if d.get("size"):
        for r in db.query("SELECT path, filename, mtype, scope FROM models WHERE size=? AND path!=? LIMIT 10",
                          (d["size"], d["path"])):
            dups.append({"path": r["path"], "filename": r["filename"], "same_name": r["filename"] == d["filename"]})
    d["duplicates"] = dups
    # 面包屑（分区归属）
    d["partition"] = _partition_of(cfg, d["path"])
    d["audit"] = management.audit_for_model(cfg, d)
    labels = db.one("SELECT * FROM model_labels WHERE model_path=?", (d["path"],))
    d["classification"] = classification.classify(d, d["audit"], dict(labels) if labels else None)
    d["classification_options"] = {"domains": classification.DOMAINS, "purposes": classification.PURPOSES}
    return _json_bytes(d)


def models_classify(db, cfg, params, body):
    if not isinstance(body, dict) or not isinstance(body.get("ids"), list):
        return _err("请选择需要分类的模型")
    ids = body["ids"]
    if not ids or len(ids) > 200 or any(type(i) is not int or i < 1 for i in ids):
        return _err("每次请选择 1 至 200 个有效模型")
    ids = list(dict.fromkeys(ids))
    if set(body) - {"ids", "domain", "purposes", "reset"}:
        return _err("不支持的分类字段")
    if "reset" in body and type(body["reset"]) is not bool:
        return _err("恢复自动分类参数无效")
    if not any(key in body for key in ("domain", "purposes")) and not body.get("reset"):
        return _err("请选择要调整的分类")
    domain = body.get("domain")
    if domain is not None and (not isinstance(domain, str) or domain not in classification.DOMAINS):
        return _err("未知的功能分类")
    purposes = body.get("purposes")
    if purposes is not None and (not isinstance(purposes, list) or len(purposes) > len(classification.PURPOSES)
                                or any(not isinstance(p, str) or p not in classification.PURPOSES for p in purposes)):
        return _err("未知的 LoRA 用途")
    if purposes and "uncategorized" in purposes and len(set(purposes)) > 1:
        return _err("待补充不能与其他用途同时选择")
    with db.lock:
        rows = db.query("SELECT path,mtype FROM models WHERE rowid_pk IN (" + ",".join("?" for _ in ids) + ")", ids)
        if len(rows) != len(ids):
            return _err("部分模型已不在索引中，请刷新后重试", 404)
        with db.conn:
            for row in rows:
                if body.get("reset"):
                    db.conn.execute("DELETE FROM model_labels WHERE model_path=?", (row["path"],))
                    continue
                previous = db.one("SELECT * FROM model_labels WHERE model_path=?", (row["path"],))
                value = dict(previous) if previous else {"domain": None, "purposes": None}
                if "domain" in body:
                    value["domain"] = domain
                if "purposes" in body and row["mtype"] == "LoRA":
                    value["purposes"] = json.dumps(list(dict.fromkeys(purposes)), ensure_ascii=False) if purposes is not None else None
                db.conn.execute("INSERT INTO model_labels(model_path,domain,purposes,updated_at) VALUES(?,?,?,?) "
                                "ON CONFLICT(model_path) DO UPDATE SET domain=excluded.domain,purposes=excluded.purposes,updated_at=excluded.updated_at",
                                (row["path"], value["domain"], value["purposes"], time.strftime("%Y-%m-%d %H:%M:%S")))
    return _json_bytes({"ok": True, "updated": len(rows)})


def _partition_of(cfg, path):
    path_l = (path or "").lower()
    for r in cfg.get("scan_roots") or []:
        if path_l.startswith(os.path.realpath(r).lower() + os.sep):
            return os.path.basename(r.rstrip("\\"))
    return None


def model_set_source(db, cfg, params, body):
    mid = _int(params.get("id"))
    row = db.one("SELECT * FROM models WHERE rowid_pk=?", (mid,))
    if not row:
        return _err("model not found", 404)
    url = (body or {}).get("url", "").strip()
    if url:
        # 顺手登记
        reg = upd._load_registry()
        reg[(row["filename"] or "").lower()] = url
        upd.save_registry(reg)
        db.upsert_model({"path": row["path"], "source_url": url,
                         "source_type": "manual", "source_conf": "manual",
                         "update_state": "unchecked", "check_error": None})
    else:
        db.upsert_model({"path": row["path"], "source_url": None,
                         "source_type": None, "source_conf": None, "update_state": "unchecked"})
    return _json_bytes({"ok": True})


def model_check(db, cfg, params, body):
    mid = _int(params.get("id"))
    row = db.one("SELECT * FROM models WHERE rowid_pk=?", (mid,))
    if not row:
        return _err("model not found", 404)
    ck = upd.Checker(db, cfg)
    res = ck.check_one(dict(row))
    fresh = db.one("SELECT * FROM models WHERE rowid_pk=?", (mid,))
    return _json_bytes({"result": res, "model": _row_json(fresh)})


def model_edit(db, cfg, params, body):
    mid = _int(params.get("id"))
    row = db.one("SELECT * FROM models WHERE rowid_pk=?", (mid,))
    if not row:
        return _err("model not found", 404)
    upd_model = {"path": row["path"]}
    if body and "rating" in body:
        upd_model["rating"] = max(0, min(10, _int(body["rating"], 0)))
    if body and "notes" in body:
        upd_model["notes"] = str(body["notes"])[:2000]
    db.upsert_model(upd_model)
    return _json_bytes({"ok": True})


def check_updates_start(db, cfg, params, body):
    if jobs.running("check-updates"):
        return _err("更新检查已在运行", 409)
    b = body or {}
    jobs.run_update_check(db, cfg, scope=b.get("scope", "all"), limit=_int(b.get("limit"), 0))
    return _json_bytes({"ok": True})


def images_list(db, cfg, params, body):
    conds, args = [], []
    q = _q(params, "q")
    if q:
        conds.append("(i.name LIKE ? OR IFNULL(i.prompt,'') LIKE ?)")
        args += [f"%{q}%"] * 2
    model_path = _q(params, "model")
    if model_path:
        conds.append("EXISTS (SELECT 1 FROM img_refs r JOIN models m ON m.path=r.model_path WHERE r.image_path=i.path AND (r.model_path=? OR m.filename LIKE ?))")
        args += [model_path, "%" + model_path + "%"]
    d = _q(params, "dir")
    if d:
        conds.append("(i.parent=? OR substr(i.parent,1,?)=?)")
        directory = d.rstrip("\\/")
        prefix = directory + os.sep
        args += [directory, len(prefix), prefix]
    if _q(params, "only_meta") == "1":
        conds.append("i.has_meta=1")
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    page = max(1, _int(_q(params, "page"), 1))
    size = min(120, max(12, _int(_q(params, "size"), 48)))
    total = db.one(f"SELECT COUNT(*) c FROM images i {where}", args)["c"]
    order = "ASC" if _q(params, "sort") == "oldest" else "DESC"
    rows = db.query(f"SELECT * FROM images i {where} ORDER BY i.mtime {order},i.path LIMIT ? OFFSET ?",
                    args + [size, (page - 1) * size])
    items = []
    for r in rows:
        item = dict(r)
        item["loras"] = jload(item.get("loras"), [])
        item["others"] = jload(item.get("others"), [])
        item["model_refs"] = jload(item.get("model_refs"), [])
        items.append(item)
    dirs = [r["parent"] for r in db.query("SELECT DISTINCT parent FROM images LIMIT 400")]
    return _json_bytes({"total": total, "page": page, "size": size, "items": items, "dirs": dirs})


def image_delete(db, cfg, params, body):
    body = body if isinstance(body, dict) else {}
    path = body.get("path")
    if not isinstance(path, str) or not path or not os.path.isabs(path):
        return _err("请选择图库中的图片。")
    real = os.path.realpath(path)
    roots = [os.path.normcase(os.path.realpath(root)) for root in cfg.get("output_roots", [])]
    normalized = os.path.normcase(real)
    if not any(normalized.startswith(root.rstrip("\\/") + os.sep) for root in roots):
        return _err("仅可删除已配置出图目录中的图库图片。", 403)
    if os.path.splitext(real)[1].lower() not in meta.IMAGE_EXTS or os.path.islink(path):
        return _err("仅可删除普通图片文件。", 403)
    if jobs.running("scan") or not db.asset_lock.acquire(blocking=False):
        return _err("正在刷新索引，请扫描完成后再删除。", 409)
    try:
        row = db.one("SELECT * FROM images WHERE path=?", (path,))
        if not row:
            return _err("该图片已不在图库中，请刷新页面。", 404)
        try:
            current = os.stat(real)
        except OSError:
            return _err("图片已移动或不存在，请刷新索引。", 404)
        if not os.path.isfile(real):
            return _err("该路径不是普通图片文件。", 403)
        if (body.get("size") != row["size"] or body.get("mtime") != row["mtime"] or
                current.st_size != row["size"] or abs(current.st_mtime - row["mtime"]) > 0.000001):
            return _err("图片在页面打开后已变化，请刷新索引后重新选择。", 409)
        try:
            recycle.recycle_file(real)
        except OSError as error:
            return _err(str(error), 409)
        with db.lock:
            db.conn.execute("DELETE FROM img_refs WHERE image_path=?", (path,))
            db.conn.execute("DELETE FROM images WHERE path=?", (path,))
            file_row = db.one("SELECT path,parent,size FROM files WHERE path=?", (real,))
            if file_row:
                db.conn.execute("DELETE FROM files WHERE path=?", (real,))
                parent = file_row["parent"]
                while parent:
                    db.conn.execute("UPDATE dirs SET size=MAX(0,size-?),file_count=MAX(0,file_count-1) WHERE path=?", (file_row["size"], parent))
                    ancestor = os.path.dirname(parent)
                    if ancestor == parent:
                        break
                    parent = ancestor
                size = max(0, int(db.get_meta("unique_size") or 0) - file_row["size"])
                db.set_meta("unique_size", str(size))
            image_store.recompute_usage(db)
            image_store.refresh_ghost_refs(db)
            db.commit()
        return _json_bytes({"ok": True, "path": path, "destination": "windows_recycle_bin"})
    finally:
        db.asset_lock.release()


def usage_ranking(db, cfg, params, body):
    mtype = _q(params, "type") or "LoRA"
    limit = min(100, max(5, _int(_q(params, "limit"), 30)))
    rows = db.query("SELECT * FROM models WHERE mtype=? AND missing=0 ORDER BY img_count DESC LIMIT ?",
                    (mtype, limit))
    unused = [_row_json(r) for r in db.query(
        "SELECT * FROM models WHERE mtype=? AND missing=0 AND (img_count=0 OR img_count IS NULL) "
        "ORDER BY mtime DESC LIMIT 20", (mtype,))]
    return _json_bytes({"type": mtype, "ranking": [_row_json(r) for r in rows],
                        "unused": [_row_json(r) for r in unused]})


def llm_list(db, cfg, params, body):
    rows = db.query("SELECT * FROM models WHERE mtype IN ('LLM','TTS','Package') AND missing=0 "
                    "ORDER BY mtype, family, size DESC")
    items = [_row_json(r) for r in rows]
    for it in items:
        import aihub.meta as meta
        info = meta.llm_info(it["filename"])
        it["quant"] = info["quant"]
        it["params"] = info["params"]
    return _json_bytes({"items": items})


def tree(db, cfg, params, body):
    path = _q(params, "path") or cfg.get("ai_root")
    real = os.path.realpath(path)
    if not _whitelisted(real):
        return _err("path not allowed", 403)
    drow = db.one("SELECT * FROM dirs WHERE path=?", (real,))
    subdirs = [dict(r) for r in db.query(
        "SELECT path, name, size, file_count, dir_count, ignored FROM dirs WHERE parent=? ORDER BY name",
        (real,))]
    for d in subdirs:
        d["size_h"] = human_size(d["size"])
    files = [dict(r) for r in db.query(
        "SELECT path, name, ext, size, mtime, category, mtype FROM files WHERE parent=? "
        "ORDER BY category, name LIMIT 1000", (real,))]
    for f in files:
        f["size_h"] = human_size(f["size"])
    crumb = []
    acc = ""
    for seg in re.split(r"[\\/]+", real):
        if not seg:
            continue
        acc = (acc + "\\" + seg) if acc else seg
        crumb.append({"name": seg, "path": acc})
    return _json_bytes({"path": real, "dir": dict(drow) if drow else None,
                        "subdirs": subdirs, "files": files, "crumb": crumb})


def files_search(db, cfg, params, body):
    q = _q(params, "q") or ""
    if len(q) < 2:
        return _json_bytes({"items": []})
    cat = _q(params, "category")
    conds, args = ["name LIKE ?"], [f"%{q}%"]
    if cat:
        conds.append("category=?"); args.append(cat)
    rows = db.query(f"SELECT path, name, size, mtime, category, mtype FROM files WHERE {' AND '.join(conds)} "
                    "ORDER BY size DESC LIMIT 200", args)
    items = [dict(r) for r in rows]
    for it in items:
        it["size_h"] = human_size(it["size"])
    return _json_bytes({"items": items})


def duplicates(db, cfg, params, body):
    rows = db.query(
        "SELECT size, COUNT(*) c, MIN(filename) fname FROM models WHERE size > 100000000 AND missing=0 "
        "GROUP BY size HAVING c > 1 ORDER BY size*c DESC LIMIT 60")
    items = []
    for r in rows:
        files = db.query("SELECT path, filename, mtype, family, scope FROM models WHERE size=? AND missing=0",
                         (r["size"],))
        items.append({"size": r["size"], "size_h": human_size(r["size"]),
                      "files": [dict(f) for f in files],
                      "same_name": len({f["filename"] for f in files}) == 1})
    return _json_bytes({"items": items})


def scan_start(db, cfg, params, body):
    if jobs.running("scan"):
        return _err("扫描已在运行", 409)
    jobs.run_full_pipeline(db, cfg)
    return _json_bytes({"ok": True})


def jobs_status(db, cfg, params, body):
    return _json_bytes({"jobs": jobs.get_jobs()})


def settings_detect(db, cfg, params, body):
    requested = body.get("ai_root") if isinstance(body, dict) else None
    if not isinstance(requested, str) or not os.path.isabs(requested) or not os.path.isdir(requested):
        return _err("请填写已经存在的资产文件夹绝对路径")
    ai_root = os.path.realpath(requested)
    layout = cfgmod.detect_layout(ai_root)
    with os.scandir(ai_root) as entries:
        has_weights = any(entry.is_file(follow_symlinks=False) and os.path.splitext(entry.name)[1].lower() in meta.MODEL_EXTS for entry in entries)
    if has_weights:
        layout["scan_roots"] = [ai_root]
    return _json_bytes({"ai_root": ai_root, "scan_roots": layout["scan_roots"] or [ai_root],
                        "aliases": layout["aliases"], "output_roots": cfgmod.detect_output_roots(layout["scan_roots"] or [ai_root]),
                        "catalog_dir": os.path.join(ai_root, "00_Management", "Catalogs")})


def settings_get(db, cfg, params, body):
    c = json.loads(json.dumps(cfg))  # deep copy
    tok = (c.get("network") or {}).get("civitai_token")
    if tok:
        c["network"]["civitai_token"] = tok[:4] + "****" if len(tok) > 4 else "****"
    return _json_bytes(c)


def settings_post(db, cfg, params, body):
    if not isinstance(body, dict):
        return _err("invalid body")
    tok = (body.get("network") or {}).get("civitai_token") or ""
    if "****" in tok:  # 未修改
        body["network"]["civitai_token"] = cfg.get("network", {}).get("civitai_token", "")
    for key in ("ai_root", "scan_roots", "output_roots", "aliases", "catalog_dir",
                "ignore_dirs", "server", "network"):
        if key in body:
            cfg[key] = body[key]
    cfgmod.save_config(cfg)
    if APP_CFG is not cfg:
        APP_CFG.clear()
        APP_CFG.update(cfg)
    return _json_bytes({"ok": True})


def report_generate(db, cfg, params, body):
    """生成当前盘点 Markdown 报告到 data/reports。"""
    ov = json.loads(overview(db, cfg, {}, body)[2].decode("utf-8"))
    now = time.strftime("%Y-%m-%d %H:%M")
    lines = [f"# AI Hub 盘点报告 · {now}", "",
             f"- AI 根目录：`{ov['ai_root']}`（逻辑 {ov['total_size_h']}，去重 {ov['unique_size_h']}，"
             f"文件 {ov['total_files']:,}）",
             f"- 模型 {ov['model_count']} 个 · 出图 {ov['image_count']} 张（带元数据 {ov['image_with_meta']}）"
             f"· 被引用模型 {ov['used_models']} 个",
             f"- 待处理更新 {ov['pending_updates']} · 上次扫描 {ov['scan_at']}", "",
             "## 分区分布", "",
             "| 分区 | 体积 | 文件数 |", "|------|------|--------|"]
    for p in ov["parts"]:
        lines.append(f"| {p['alias'] or p['name']} | {p['size_h']} | {p['files']:,} |")
    lines += ["", "## 使用参考排行（LoRA Top 15）", "",
              "仅统计已扫描图片的引用记录，不能据此判断模型质量或认定可删除。", "",
              "| 模型 | 出图引用 | 最近记录 | 参考分 | 标签 |", "|------|------|----------|--------|------|"]
    usage = json.loads(usage_ranking(db, cfg, {"type": "LoRA", "limit": "15"}, body)[2].decode("utf-8"))
    for m in usage["ranking"]:
        lines.append(f"| {m['filename']} | {m['img_count'] or 0} | {m.get('last_used_h') or '暂无记录'} "
                     f"| {m['value_score']} | {m['value_tag']} |")
    lines += ["", "## 当前无引用记录的 LoRA（前 20）", ""]
    for m in usage["unused"][:20]:
        d_str = time.strftime("%Y-%m-%d", time.localtime(m["mtime"])) if m.get("mtime") else "-"
        lines.append(f"- `{m['filename']}`（{m['family'] or '未知'}，{m['size_h']}，文件修改 {d_str}）")
    if ov["ghost_count"]:
        lines += ["", f"## 未匹配引用 {ov['ghost_count']} 种（当前模型索引未能对应，原因尚未确认）", ""]
        for g in ov["ghost_refs"]:
            lines.append(f"- `{g['filename']}`（{g['role']}，被引用 {g['count']} 次）")
    lines += ["", "## 更新状态分布", ""]
    for k, v in ov["state_counts"].items():
        lines.append(f"- {k}: {v}")
    name = f"盘点报告_{time.strftime('%Y%m%d_%H%M')}.md"
    path = os.path.join(cfgmod.REPORTS_DIR, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return _json_bytes({"ok": True, "name": name, "path": path})


def reports_list(db, cfg, params, body):
    items = management.reports(cfg, cfgmod.REPORTS_DIR)
    return _json_bytes({"items": sorted(items, key=lambda x: -x["mtime"])})


def report_content(db, cfg, params, body):
    path = _q(params, "path") or ""
    if not management.is_report(cfg, cfgmod.REPORTS_DIR, path):
        return _err("path not allowed", 403)
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return _json_bytes({"name": os.path.basename(path), "content": f.read(400 * 1024)})
    except OSError as e:
        return _err(str(e), 404)


def serve_file(db, cfg, params, body):
    """返回文件内容（图片预览/报告下载），白名单限定在 AI 根目录内。"""
    path = _q(params, "path") or ""
    if not (_whitelisted(path) or management.is_report(cfg, cfgmod.REPORTS_DIR, path)) or not os.path.isfile(path):
        return _err("path not allowed", 403)
    ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
    with open(path, "rb") as f:
        data = f.read()
    return 200, {"Content-Type": ctype, "Content-Length": str(len(data)),
                 "Cache-Control": "max-age=3600"}, data


def thumb(db, cfg, params, body):
    """缩略图：有 Pillow 则生成，否则回退原图。"""
    path = _q(params, "path") or ""
    if not _whitelisted(path) or not os.path.isfile(path):
        return _err("path not allowed", 403)
    try:
        from PIL import Image  # noqa
        import io
        img = Image.open(path)
        img.thumbnail((320, 320))
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "JPEG", quality=80)
        return 200, {"Content-Type": "image/jpeg", "Cache-Control": "max-age=86400"}, buf.getvalue()
    except Exception:
        return serve_file(db, cfg, params, body)


def model_reveal(db, cfg, params, body):
    """在 Windows 资源管理器中定位模型文件。"""
    mid = _int(params.get("id"))
    row = db.one("SELECT * FROM models WHERE rowid_pk=?", (mid,))
    if not row:
        return _err("model not found", 404)
    path = row["path"]
    if not _whitelisted(path):
        return _err("path not allowed", 403)
    import subprocess
    if os.path.isfile(path):
        subprocess.Popen(["explorer", "/select,", path])
    else:
        subprocess.Popen(["explorer", os.path.dirname(path) or cfg.get("ai_root") or cfgmod.APP_DIR])
    return _json_bytes({"ok": True})


def resolve_source_api(db, cfg, params, body):
    mid = _int(params.get("id"))
    row = db.one("SELECT * FROM models WHERE rowid_pk=?", (mid,))
    if not row:
        return _err("model not found", 404)
    ck = upd.Checker(db, cfg)
    res = ck.resolve_source(dict(row), allow_search=True)
    return _json_bytes(res)


def management_summary(db, cfg, params, body):
    return _json_bytes(management.overview(cfg))


def workflow_summary(db, cfg, params, body):
    return _json_bytes(management.workflows(cfg))


ROUTES = [
    ("GET", r"^/api/health$", lambda db, cfg, params, body: _json_bytes({"app": "ai-hub", "version": "2.2", "jobs_running": any(j["status"] == "running" for j in jobs.get_jobs())})),
    ("GET", r"^/api/management$", management_summary),
    ("GET", r"^/api/workflows$", workflow_summary),
    ("GET", r"^/api/overview$", overview),
    ("GET", r"^/api/models$", models_list),
    ("POST", r"^/api/models/classify$", models_classify),
    ("GET", r"^/api/model/(?P<id>\d+)$", model_detail),
    ("POST", r"^/api/model/(?P<id>\d+)/source$", model_set_source),
    ("POST", r"^/api/model/(?P<id>\d+)/check$", model_check),
    ("POST", r"^/api/model/(?P<id>\d+)/resolve-source$", resolve_source_api),
    ("POST", r"^/api/model/(?P<id>\d+)/edit$", model_edit),
    ("POST", r"^/api/model/(?P<id>\d+)/reveal$", model_reveal),
    ("POST", r"^/api/models/check-updates$", check_updates_start),
    ("GET", r"^/api/images$", images_list),
    ("POST", r"^/api/image/delete$", image_delete),
    ("GET", r"^/api/usage/ranking$", usage_ranking),
    ("GET", r"^/api/llm$", llm_list),
    ("GET", r"^/api/tree$", tree),
    ("GET", r"^/api/files/search$", files_search),
    ("GET", r"^/api/duplicates$", duplicates),
    ("POST", r"^/api/scan/start$", scan_start),
    ("GET", r"^/api/jobs$", jobs_status),
    ("GET", r"^/api/settings$", settings_get),
    ("POST", r"^/api/settings$", settings_post),
    ("POST", r"^/api/settings/detect$", settings_detect),
    ("GET", r"^/api/reports$", reports_list),
    ("POST", r"^/api/report/generate$", report_generate),
    ("GET", r"^/api/report/content$", report_content),
    ("GET", r"^/api/file$", serve_file),
    ("GET", r"^/api/thumb$", thumb),
]


def dispatch(db, cfg, method, path, params, body):
    for m, rx, fn in ROUTES:
        match = re.match(rx, path)
        if match and m == method:
            params = dict(params)
            params.update({k: v for k, v in match.groupdict().items() if v is not None})
            try:
                return fn(db, cfg, params, body)
            except Exception as e:
                import traceback
                return _json_bytes({"error": str(e), "trace": traceback.format_exc(limit=4)}, 500)
    return _err("not found", 404)
