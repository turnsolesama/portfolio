"""Safe-zone orchestration; all writes are to managed entries and local journals."""
import copy
import json
import os
from pathlib import Path
import re
import threading

from . import config, jobs, organizer, classification, management

LOCK = threading.RLock()
ASSET_JOBS = ("scan", "organize-preview", "organize", "organize-undo")


def busy():
    return any(jobs.running(name) for name in ASSET_JOBS)


def storage():
    return Path(config.DATA_DIR) / "organizer"


def root_for(cfg):
    options = cfg.get("organizer") or {}
    if not options.get("enabled") or not options.get("root"):
        raise ValueError("请先设置并保存整理安全区")
    root = organizer.validate_root(options["root"])
    if os.path.normcase(root) != os.path.normcase(os.path.realpath(cfg.get("ai_root") or "")):
        raise ValueError("资产目录已改变，请重新保存整理安全区")
    return root


def plan_path(plan_id):
    if not isinstance(plan_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", plan_id):
        raise ValueError("整理计划编号无效")
    return storage() / "plans" / (plan_id + ".json")


def write_plan(plan):
    path = plan_path(plan["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)
    (storage() / "latest.txt").write_text(plan["id"], encoding="utf-8")


def read_plan(cfg, plan_id=None):
    root = root_for(cfg)
    if plan_id is None:
        latest = storage() / "latest.txt"
        if not latest.exists():
            return None
        plan_id = latest.read_text(encoding="utf-8").strip()
    path = plan_path(plan_id)
    if not path.is_file():
        raise ValueError("整理计划不存在，请重新预览")
    plan = json.loads(path.read_text(encoding="utf-8"))
    if os.path.normcase(plan.get("root", "")) != os.path.normcase(root):
        raise ValueError("此计划属于其他安全区，请重新预览")
    return plan


def model_context(db, cfg):
    if db is None:
        return classification.classification_context(catalog=management.catalog(cfg))
    return classification.classification_context(db.query("SELECT * FROM models"), management.catalog(cfg),
                                                 db.query("SELECT * FROM model_labels"))


def preview(cfg, db=None):
    snapshot = copy.deepcopy(cfg)
    root = root_for(snapshot)
    def target():
        jobs.progress("organize-preview", "正在识别安全区内可归类的资产…")
        plan = organizer.build_plan(root, config.APP_DIR, snapshot.get("ignore_dirs") or (), model_context=model_context(db, snapshot))
        write_plan(plan)
        jobs.progress("organize-preview", f"预览完成：{len(plan['items'])} 个分类入口待核对")
    return jobs.start("organize-preview", target)


def apply(db, cfg, plan_id):
    plan = read_plan(cfg, plan_id)
    if plan.get("apply_allowed") is False or not organizer.library_policy(plan["root"])["apply_allowed"]:
        raise ValueError("已有模型库仅支持统一虚拟预览，尚未批准实体目标策略")
    def target():
        with db.asset_lock:
            jobs.progress("organize", "正在建立分类入口，原文件位置保持不变…")
            result = organizer.apply_plan(plan, storage() / "runs", model_context=model_context(db, cfg))
            jobs.progress("organize", f"完成：建立 {result.get('created', 0)}，跳过 {result.get('skipped', 0)}；可在记录中撤销")
    return jobs.start("organize", target)


def undo(db, cfg, run_id):
    root = root_for(cfg)
    def target():
        with db.asset_lock:
            jobs.progress("organize-undo", "正在核对并撤销本次分类入口…")
            result = organizer.undo_run(run_id, storage() / "runs", root)
            jobs.progress("organize-undo", f"撤销完成：{result.get('removed', 0)} 个入口；原件保留")
    return jobs.start("organize-undo", target)


def startup(db, cfg):
    """An explicit per-workspace opt-in; runs once per backend startup."""
    options = cfg.get("organizer") or {}
    if not options.get("enabled") or not options.get("on_startup"):
        return False
    try:
        root = root_for(cfg)
        if not organizer.library_policy(root)["apply_allowed"]:
            return False
    except (ValueError, OSError):
        return False
    snapshot = copy.deepcopy(cfg)
    def target():
        with db.asset_lock:
            jobs.progress("organize", "按已保存的安全区设置自动分类…")
            context = model_context(db, snapshot)
            plan = organizer.build_plan(root, config.APP_DIR, snapshot.get("ignore_dirs") or (), model_context=context)
            write_plan(plan)
            result = organizer.apply_plan(plan, storage() / "runs", model_context=context)
            jobs.progress("organize", f"启动整理完成：建立 {result.get('created', 0)}，跳过 {result.get('skipped', 0)}")
        jobs.run_full_pipeline(db, snapshot)
    with LOCK:
        if busy():
            return False
        return bool(jobs.start("organize", target))
