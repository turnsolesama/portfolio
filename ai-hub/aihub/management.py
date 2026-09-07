"""Read the maintained asset catalog and project evidence without changing assets."""
import collections
import json
import os
from pathlib import Path
import threading
from . import config

_cache = {}
_lock = threading.RLock()


def read_json(path, default=None):
    path = Path(path)
    try:
        stamp = (path.stat().st_mtime_ns, path.stat().st_size)
        with _lock:
            saved = _cache.get(str(path))
            if saved and saved[0] == stamp:
                return saved[1]
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        with _lock:
            _cache[str(path)] = (stamp, value)
        return value
    except (OSError, ValueError):
        return default


def root(cfg):
    return Path(cfg.get("ai_root") or config.DATA_DIR) / "00_Management"


def catalog(cfg):
    return read_json(Path(cfg.get("catalog_dir") or root(cfg) / "Catalogs") / "models.json", {})


def audit_for_model(cfg, model):
    for record in catalog(cfg).get("models", []):
        if model.get("legacy_uid") == record.get("id"):
            return record
    return None


def overview(cfg):
    base = root(cfg)
    data = catalog(cfg)
    models = data.get("models", [])
    central = [m for m in models if m.get("scope") == "central"]
    migrations = base / "Migrations"
    checks = sorted(migrations.glob("*/final_library_check.json")) if migrations.is_dir() else []
    check = read_json(checks[-1], {}) if checks else {}
    duplicates = read_json(base / "Catalogs/duplicate_candidates.json", [])
    reviewed = read_json(base / "Catalogs/workflow_path_review.json", {})
    live = read_json(base / "Catalogs/live_inventory.json", {})
    return {"available": bool(models), "updated_at": data.get("updated_at"),
            "catalog_records": len(models), "central_records": len(central),
            "base_count": sum(m.get("category") in ("Checkpoint", "Diffusion") for m in central),
            "lora_count": sum(m.get("category") == "LoRA" for m in central),
            "family_counts": collections.Counter(m.get("family", "Unknown") for m in central if m.get("category") in ("LoRA", "Checkpoint", "Diffusion")),
            "check": {key: check.get(key) for key in ("checked_at", "status", "hardlinks_verified", "directory_pairs_verified", "models_checked")},
            "workflow_reviewed": len(reviewed.get("copies", [])), "workflow_pending": len(reviewed.get("needs_review", [])),
            "duplicate_groups": len(duplicates),
            "duplicate_candidate_bytes": sum(d.get("bytes_each", 0) * max(0, len(d.get("files", [])) - 1) for d in duplicates),
            "live_updated_at": live.get("updated_at"), "live_diff": {k: len(v) for k, v in live.get("diff", {}).items()},
            "entry_report": str(base / "START_HERE.md"),
            "verification_report": str(base / "验证与待办.md"),
            "next_steps_report": str(base / "模型选型与下一步.md")}


def projects(cfg):
    ai_root = root(cfg).parent
    training = ai_root / "50_Training/Projects"
    records = catalog(cfg).get("models", [])
    items = []
    for project in sorted(training.iterdir()) if training.is_dir() else []:
        if not project.is_dir() or project.is_symlink():
            continue
        name = project.name
        needle = "/projects/" + name.casefold() + "/"
        weights = [m for m in records if needle in m.get("canonical_path", "").replace("\\", "/").casefold()
                   or (name.casefold() in m.get("filename", "").casefold() and m.get("scope") == "central" and m.get("category") == "LoRA")]
        datasets = [str(p) for p in (project / "Datasets").iterdir() if p.is_dir()] if (project / "Datasets").is_dir() else []
        runs = [str(p) for p in (project / "Runs").iterdir() if p.is_dir()] if (project / "Runs").is_dir() else []
        report = project / "README_训练项目.md"
        specialist = list((root(cfg) / "Projects" / name).glob("*.md"))
        items.append({"name": name, "path": str(project), "datasets": datasets, "runs": runs,
                      "report": str(specialist[0] if specialist else report) if specialist or report.is_file() else None,
                      "families": sorted({m.get("family", "Unknown") for m in weights}),
                      "weights": [{k: m.get(k) for k in ("id", "filename", "category", "scope", "family", "canonical_path", "metadata", "variant_note", "training_note")} for m in weights],
                      "status": "待对照验证", "weight_count": len(weights)})
    items.sort(key=lambda p: p["name"].casefold())
    return {"items": items, "coverage": "50_Training/Projects 与当前模型台账；状态不代表新生成测试"}


def workflows(cfg):
    base = root(cfg) / "Catalogs"
    original = read_json(base / "workflows.json", [])
    review = read_json(base / "workflow_path_review.json", {})
    fixed = {row["source"]: row for row in review.get("copies", [])}
    pending = {row["source"]: row for row in review.get("needs_review", [])}
    items = []
    for workflow in original:
        path = workflow["path"]
        item = {"name": Path(path).name, "path": path, "exists": Path(path).is_file(),
                "dependencies": workflow.get("model_dependencies", []), "missing": workflow.get("missing_models", []),
                "unavailable_nodes": workflow.get("unavailable_node_types", []), "status": "path_checked",
                "copy": None, "changes": [], "generation_status": "not_run"}
        if path in fixed:
            match = fixed[path]
            item.update(status="reviewed_copy", copy=match["reviewed_copy"], changes=match["changes"])
            item["copy_exists"] = Path(match["reviewed_copy"]).is_file()
        elif path in pending:
            item.update(status="needs_review", missing=pending[path].get("unresolved", item["missing"]))
        elif item["missing"] or item["unavailable_nodes"] or workflow.get("error"):
            item["status"] = "needs_review"
        items.append(item)
    return {"items": items, "counts": dict(collections.Counter(item["status"] for item in items)),
            "coverage": "静态记录覆盖常见加载器；路径修正版并未执行生成测试"}


def reports(cfg, generated_dir):
    base = root(cfg)
    locations = [(base, "工作入口"), (base / "Reports", "模型与 LoRA"), (Path(generated_dir), "终端生成报告")]
    locations += [(p, "项目 · " + p.name) for p in (base / "Projects").iterdir() if p.is_dir()] if (base / "Projects").is_dir() else []
    items = []
    for folder, group in locations:
        for path in folder.iterdir() if folder.is_dir() else []:
            if path.is_file() and path.suffix.lower() in (".md", ".html"):
                st = path.stat()
                items.append({"name": path.name, "path": str(path), "group": group, "kind": path.suffix[1:],
                              "mtime": st.st_mtime, "size": st.st_size})
    for project in projects(cfg)["items"]:
        if project["report"] and all(r["path"] != project["report"] for r in items):
            path = Path(project["report"])
            st = path.stat()
            items.append({"name": project["name"] + " · 训练记录", "path": str(path), "group": "训练项目", "kind": "md", "mtime": st.st_mtime, "size": st.st_size})
    return items


def is_report(cfg, generated_dir, path):
    real = os.path.normcase(os.path.realpath(path))
    return any(real == os.path.normcase(os.path.realpath(item["path"])) for item in reports(cfg, generated_dir))
