# -*- coding: utf-8 -*-
"""出图扫描：解析输出目录内图片的内嵌工作流，建立 图片 <-> 模型 引用关系，并计算使用统计。"""
import json
import os
import sqlite3
import time

from . import config as cfgmod, meta


def run_image_scan(db, cfg, progress_cb=None):
    with db.asset_lock:
        return _run_image_scan(db, cfg, progress_cb)


def _run_image_scan(db, cfg, progress_cb=None):
    """扫描所有输出目录。增量：path+mtime+size 未变则跳过。"""
    out_roots = cfg.get("output_roots") or []
    stats = {"scanned": 0, "with_meta": 0, "skipped": 0, "refs": 0, "ghost": 0}
    ghost_refs = {}

    def report(msg):
        if progress_cb:
            progress_cb(msg)

    prev = {}
    if db.get_meta("image_parser_version") == "2":
        for r in db.query("SELECT path, mtime, size FROM images"):
            prev[r["path"]] = (r["mtime"], r["size"])

    name_index = db.model_index_by_name()
    files_by_name = {}
    for r in db.query("SELECT path, name FROM files WHERE category='model'"):
        files_by_name.setdefault(r["name"].lower(), r["path"])

    img_rows, ref_rows = [], []

    def flush():
        if not img_rows and not ref_rows:
            return
        with db.lock:
            db.conn.executemany(
                "INSERT OR REPLACE INTO images(path,name,parent,size,mtime,width,height,has_meta,"
                "engine,checkpoint,loras,others,model_refs,sampler,steps,cfg,seed,prompt) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", img_rows)
            seen_paths = {r[0] for r in img_rows}
            for p in seen_paths:
                db.conn.execute("DELETE FROM img_refs WHERE image_path=?", (p,))
            db.conn.executemany("INSERT INTO img_refs(image_path,model_path,role,filename) "
                                "VALUES(?,?,?,?)", ref_rows)
            db.conn.commit()
        img_rows.clear()
        ref_rows.clear()

    img_total = 0
    visited = set()
    for root in out_roots:
        if not cfgmod.scan_root_allowed(root, cfg):
            continue
        root = os.path.realpath(root)
        if not os.path.isdir(root):
            continue
        for dp, _dns, fns in os.walk(root):
            _dns[:] = [name for name in _dns if not cfgmod.scan_excluded(os.path.join(dp, name), cfg)]
            for fn in fns:
                ext = os.path.splitext(fn)[1].lower()
                if ext not in meta.IMAGE_EXTS:
                    continue
                path = os.path.join(dp, fn)
                if cfgmod.scan_excluded(path, cfg):
                    continue
                if os.path.normcase(path) in visited:
                    continue
                visited.add(os.path.normcase(path))
                img_total += 1
                if img_total % 300 == 0:
                    report(f"出图分析：{img_total} 张…（已解析 {stats['scanned']}，"
                           f"引用 {stats['refs']}，未知 {stats['ghost']}）")
                try:
                    st = os.stat(path)
                except OSError:
                    continue
                if path in prev and abs(prev[path][0] - st.st_mtime) < 1 and prev[path][1] == st.st_size:
                    stats["skipped"] += 1
                    continue
                row, refs_out = analyze_image(path, fn, dp, st, name_index, files_by_name,
                                              ghost_refs, stats)
                if row:
                    img_rows.append(row)
                    stats["scanned"] += 1
                ref_rows.extend(refs_out)
                if len(img_rows) >= 800:
                    flush()
    flush()

    # 未知引用但文件存在于盘上 → 自动补录为模型行（覆盖"新下载模型"场景）
    auto_added = 0
    for info in ghost_refs.values():
        hit = files_by_name.get(info["filename"].lower())
        if not hit:
            continue
        try:
            st = os.stat(hit)
        except OSError:
            continue
        from .scan import _model_row_from_fs
        row = _model_row_from_fs(hit, {"paths": [hit], "size": st.st_size,
                                       "mtime": st.st_mtime,
                                       "ext": os.path.splitext(hit)[1].lower()}, [hit])
        db.upsert_model(row)
        auto_added += 1

    if auto_added:
        name_index = db.model_index_by_name()
        remap_unmatched(db, name_index)

    recompute_usage(db)
    db.set_meta("image_parser_version", "2")
    db.set_meta("image_scan_at", time.strftime("%Y-%m-%d %H:%M:%S"))
    refresh_ghost_refs(db)
    report(f"出图分析完成：解析 {stats['scanned']} 张（带元数据 {stats['with_meta']}，"
           f"增量跳过 {stats['skipped']}），模型引用 {stats['refs']}，未知引用 {stats['ghost']}，"
           f"自动补录模型 {auto_added}")
    return stats


def refresh_ghost_refs(db):
    db.set_meta("ghost_refs", json.dumps([dict(row) for row in db.query(
        "SELECT filename, role, COUNT(DISTINCT image_path) count FROM img_refs WHERE model_path IS NULL "
        "GROUP BY filename, role ORDER BY count DESC LIMIT 200")], ensure_ascii=False))


def remap_unmatched(db, name_index):
    """补录模型后，把 img_refs 中未匹配的引用重新匹配。"""
    with db.lock:
        rows = db.conn.execute(
            "SELECT DISTINCT filename, role FROM img_refs WHERE model_path IS NULL").fetchall()
        for r in rows:
            hit = name_index.get((r["filename"] or "").lower())
            if hit:
                db.conn.execute("UPDATE img_refs SET model_path=? WHERE filename=? AND model_path IS NULL",
                                (hit, r["filename"]))
        db.conn.commit()


def analyze_image(path, fn, dp, st, name_index, files_by_name, ghost_refs, stats):
    """解析单张图片。返回 (images行元组, [(image_path, model_path|None, role, filename)])。"""
    ext = os.path.splitext(fn)[1].lower()
    engine = "none"
    refs, sampler, steps, cfg_v, seed, prompt = [], None, None, None, None, ""
    checkpoint, loras, others = None, [], []
    w = h = None

    if ext == ".png":
        md = meta.parse_png_metadata(path)
        if "prompt" in md:
            try:
                graph = json.loads(md["prompt"])
                engine = "comfyui"
                refs = meta.extract_refs_from_graph(graph)
                sm = meta.extract_sampler_from_graph(graph)
                sampler, steps, cfg_v, seed = (sm.get("sampler"), sm.get("steps"),
                                               sm.get("cfg"), sm.get("seed"))
                prompt = meta.extract_prompts_from_graph(graph)
            except Exception:
                pass
        if engine != "comfyui" and "workflow" in md:
            try:
                graph = json.loads(md["workflow"])
                engine = "comfyui"
                refs = meta.extract_refs_from_graph(graph)
            except Exception:
                pass
        if engine == "none" and "parameters" in md:
            p = meta.parse_a1111_parameters(md.get("parameters"))
            engine = "a1111"
            prompt = p.get("prompt", "")
            checkpoint = p.get("checkpoint")
            steps, cfg_v, seed, sampler = p.get("steps"), p.get("cfg"), p.get("seed"), p.get("sampler")
            refs = p.get("refs", [])
        w, h = _png_dimensions(path)

    has_meta = 1 if engine != "none" else 0
    if has_meta:
        stats["with_meta"] += 1

    matched = []
    refs_out = []
    for ref in refs:
        fn_ref = ref["filename"]
        hit = name_index.get(ref.get("reference", fn_ref).replace("/", "\\").lower()) or name_index.get(fn_ref.lower())
        if not hit:
            key = fn_ref.lower()
            g = ghost_refs.setdefault(key, {"filename": fn_ref, "role": ref["role"], "count": 0})
            g["count"] += 1
            stats["ghost"] += 1
            refs_out.append((path, None, ref["role"], fn_ref))
            continue
        stats["refs"] += 1
        matched.append(hit)
        refs_out.append((path, hit, ref["role"], fn_ref))
        if ref["role"] == "Checkpoint" and not checkpoint:
            checkpoint = fn_ref
        elif ref["role"] == "LoRA" and fn_ref not in loras:
            loras.append(fn_ref)
        elif ref["role"] not in ("Checkpoint", "LoRA"):
            others.append(f'{ref["role"]}:{fn_ref}')

    row = (path, fn, dp, st.st_size, st.st_mtime, w, h, has_meta, engine,
           checkpoint, json.dumps(loras, ensure_ascii=False), json.dumps(others, ensure_ascii=False),
           json.dumps(matched, ensure_ascii=False), sampler, steps, cfg_v, seed, prompt)
    return row, refs_out


def _png_dimensions(path):
    try:
        with open(path, "rb") as f:
            head = f.read(33)
        return meta.png_size(head)
    except OSError:
        return None, None


def recompute_usage(db):
    """从 img_refs 聚合每模型使用量，写回 models。"""
    with db.lock:
        db.conn.execute("""
            UPDATE models SET
              img_count = (SELECT COUNT(DISTINCT image_path) FROM img_refs r WHERE r.model_path = models.path),
              days_used = (SELECT COUNT(DISTINCT CAST(i.mtime/86400 AS INTEGER)) FROM img_refs r
                           JOIN images i ON i.path = r.image_path WHERE r.model_path = models.path),
              last_used = (SELECT MAX(i.mtime) FROM img_refs r JOIN images i ON i.path = r.image_path
                           WHERE r.model_path = models.path),
              first_used = (SELECT MIN(i.mtime) FROM img_refs r JOIN images i ON i.path = r.image_path
                            WHERE r.model_path = models.path)
        """)
        db.conn.commit()
