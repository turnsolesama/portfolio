# -*- coding: utf-8 -*-
"""AI Hub configuration. A fresh installation waits for an explicit asset root."""
import json
import os
import stat

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(APP_DIR, "data")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
DB_PATH = os.path.join(DATA_DIR, "aihub.db")
SOURCES_PATH = os.path.join(DATA_DIR, "sources.json")
REPORTS_DIR = os.path.join(DATA_DIR, "reports")

FILE_ATTRIBUTE_REPARSE_POINT = 0x400

DEFAULT_IGNORE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv",
                       ".pnpm-store", ".cache", "$RECYCLE.BIN", "System Volume Information"}


def _is_reparse(entry_stat) -> bool:
    fa = getattr(entry_stat, "st_file_attributes", 0)
    return bool(fa & FILE_ATTRIBUTE_REPARSE_POINT)


def detect_layout(ai_root: str) -> dict:
    """探测 ai_root 顶层物理目录（跳过 junction/symlink 防止环路），返回扫描根与别名映射。"""
    scan_roots, aliases = [], {}
    if not os.path.isdir(ai_root):
        return {"scan_roots": scan_roots, "aliases": aliases}
    with os.scandir(ai_root) as it:
        for entry in it:
            try:
                st = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            if not entry.is_dir(follow_symlinks=False) or _is_reparse(st):
                continue
            real = os.path.realpath(entry.path)
            scan_roots.append(real)
            if real.lower() != entry.path.lower():
                aliases[entry.path] = real
    scan_roots.sort()
    return {"scan_roots": scan_roots, "aliases": aliases}


def detect_output_roots(roots) -> list:
    """在顶层分区 + ComfyUI 安装内自动找输出目录。"""
    found = []
    for root in list(roots):
        # 顶层分区名含 Output / 输出
        base = os.path.basename(root.rstrip("\\")).lower()
        if "output" in base or "输出" in base:
            found.append(root)
    # ComfyUI 便携版 output
    for apps_dir in roots:
        for suffix in (("ComfyUI_Main", "ComfyUI", "output"), ("ComfyUI", "output")):
            comfy_output = os.path.join(apps_dir, *suffix)
            if os.path.isdir(comfy_output):
                found.append(os.path.realpath(comfy_output))
        if "comfy" in os.path.basename(apps_dir).casefold() and os.path.isdir(os.path.join(apps_dir, "output")):
            found.append(os.path.realpath(os.path.join(apps_dir, "output")))
    # 去重
    seen, uniq = set(), []
    for p in found:
        rl = os.path.realpath(p).lower()
        if rl not in seen:
            seen.add(rl)
            uniq.append(os.path.realpath(p))
    return uniq


def default_config() -> dict:
    requested = os.environ.get("AI_HUB_ROOT", "").strip()
    ai_root = os.path.abspath(requested) if requested and os.path.isdir(requested) else ""
    layout = detect_layout(ai_root)
    return {
        "ai_root": ai_root,
        "scan_roots": layout["scan_roots"],
        "aliases": layout["aliases"],
        "output_roots": detect_output_roots(layout["scan_roots"]),
        "catalog_dir": os.path.join(ai_root, "00_Management", "Catalogs") if ai_root else "",
        "ignore_dirs": sorted(DEFAULT_IGNORE_DIRS),
        "server": {"host": "127.0.0.1", "port": 8765},
        "network": {
            "civitai_base": "https://civitai.com",
            "hf_base": "https://huggingface.co",
            "civitai_token": "",
            "proxy": "",
            "request_interval": 1.2,
        },
    }


def load_config() -> dict:
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(REPORTS_DIR, exist_ok=True)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
        default = default_config()
        for k, v in default.items():
            cfg.setdefault(k, v)
        return cfg
    cfg = default_config()
    save_config(cfg)
    return cfg


def save_config(cfg: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    c = default_config()
    print(json.dumps(c, ensure_ascii=False, indent=2)[:2000])
