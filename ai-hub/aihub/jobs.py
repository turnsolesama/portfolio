# -*- coding: utf-8 -*-
"""后台任务管理：扫描 / 出图分析 / 更新检查。任务状态保存在内存。"""
import threading
import json
import time
import traceback

from . import config as cfgmod
from . import images, scan, updater

_jobs = {}
_lock = threading.Lock()


def _new_job(name):
    return {"name": name, "status": "running", "progress": "", "started": time.time(),
            "finished": None, "error": None}


def get_jobs():
    with _lock:
        return sorted(_jobs.values(), key=lambda j: j["started"], reverse=True)


def running(name):
    with _lock:
        j = _jobs.get(name)
        return j and j["status"] == "running"


def start(name, target, *args):
    with _lock:
        j = _jobs.get(name)
        if j and j["status"] == "running":
            return None
        job = _new_job(name)
        _jobs[name] = job

    def run():
        try:
            target(*args)
            job["status"] = "done"
        except Exception as e:
            job["status"] = "error"
            job["error"] = f"{e}\n{traceback.format_exc(limit=3)}"
        finally:
            job["finished"] = time.time()

    t = threading.Thread(target=run, daemon=True, name=name)
    t.start()
    return job


def progress(name, msg):
    with _lock:
        j = _jobs.get(name)
        if j:
            j["progress"] = msg


# ---------- 任务定义 ----------

def run_full_pipeline(db, cfg, do_images=True):
    """完整流水线：文件扫描 -> 模型库构建 -> 出图分析（单任务，进度统一走 scan）。"""

    def target():
        def cb(m):
            progress("scan", m)
        result = scan.scan_all(db, cfg, progress_cb=cb)
        stats = scan.build_models(db, cfg, result, progress_cb=cb)
        db.set_meta("scan_at", time.strftime("%Y-%m-%d %H:%M:%S"))
        db.set_meta("scan_file_count", str(result["file_count"]))
        if do_images:
            cb("出图分析中…")
            images.run_image_scan(db, cfg, progress_cb=cb)
        cb(f"完成：文件 {result['file_count']}，模型目录 {stats['catalog']}+{stats['filesystem']}")

    start("scan", target)


def run_update_check(db, cfg, scope="all", limit=0):
    """批量更新检查。scope: all | unchecked | pending"""

    def target():
        def cb(m):
            progress("check-updates", m)
        if scope == "all":
            cond = "mtype IN ('Checkpoint','LoRA','Diffusion','VAE','ControlNet','Embedding','IPAdapter','TextEncoder')"
        elif scope == "unchecked":
            cond = "update_state='unchecked'"
        else:
            cond = "update_state IN ('unchecked','error','unknown','maybe')"
        sql = f"SELECT * FROM models WHERE {cond} AND missing=0 ORDER BY mtype, size DESC"
        if limit:
            sql += f" LIMIT {int(limit)}"
        rows = db.query(sql)
        cb(f"待检查 {len(rows)} 个模型…")
        if not rows:
            progress("check-updates", "没有需要检查的模型")
            return
        ck = updater.Checker(db, cfg, progress_cb=cb)
        summary = ck.check_many(rows)
        db.set_meta("update_check_at", time.strftime("%Y-%m-%d %H:%M:%S"))
        progress("check-updates", f"完成：{json.dumps(summary, ensure_ascii=False)}")

    start("check-updates", target)
