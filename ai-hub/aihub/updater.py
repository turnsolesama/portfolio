# -*- coding: utf-8 -*-
"""下载来源解析与更新检查：modelspec / sidecar / 手动登记 / Civitai & HuggingFace API。"""
import difflib
import json
import os
import re
import time
import urllib.parse
import urllib.request

from . import config as cfgmod
from . import meta
from .db import jload

CIVITAI_MODEL_RE = re.compile(r"civitai\.com/models/(\d+)", re.I)
CIVITAI_VER_RE = re.compile(r"modelVersionId=(\d+)|model[-.]version/(\d+)", re.I)
HF_RE = re.compile(r"huggingface\.co/([\w.\-]+/[\w.\-]+)", re.I)


class Checker:
    def __init__(self, db, cfg, progress_cb=None):
        self.db = db
        self.cfg = cfg
        self.net = cfg.get("network", {})
        self.progress_cb = progress_cb

    # ---------- 网络基础 ----------
    def _opener(self):
        proxy = self.net.get("proxy")
        handlers = []
        if proxy:
            handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
        return urllib.request.build_opener(*handlers)

    def _get_json(self, url: str, headers=None, timeout=20):
        req = urllib.request.Request(url, headers={
            "User-Agent": "AIHub/1.0 (local asset manager)",
            **(headers or {}),
        })
        token = self.net.get("civitai_token")
        if token and "civitai" in url:
            req.add_header("Authorization", f"Bearer {token}")
        with self._opener().open(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))

    # ---------- 来源解析 ----------
    def resolve_source(self, model: dict, allow_search=True) -> dict:
        """多策略解析下载来源。返回 {url, type, confidence, note}"""
        path, hdr = model["path"], jload(model.get("header_meta"), {})
        # 1. safetensors modelspec
        for k in ("modelspec.url", "modelspec.timestep_url"):
            v = hdr.get(k)
            if v and re.match(r"https?://", str(v)):
                t = "civitai" if "civitai" in str(v) else ("huggingface" if "huggingface" in str(v) else "web")
                return {"url": str(v), "type": t, "confidence": "header", "note": "模型内嵌 modelspec 元数据"}
        # 2. sidecar 文件
        for cand in _sidecar_paths(path):
            urls = _urls_in_file(cand)
            if urls:
                t = "civitai" if "civitai" in urls[0] else ("huggingface" if "huggingface" in urls[0] else "web")
                return {"url": urls[0], "type": t, "confidence": "sidecar", "note": f"伴随文件 {os.path.basename(cand)}"}
        # 3. 手动登记表
        reg = _load_registry()
        hit = reg.get(model.get("norm_name") or model["filename"].lower())
        if hit:
            return {"url": hit, "type": "manual", "confidence": "registry", "note": "手动登记"}
        # 4. Civitai 文件名搜索
        if allow_search and "civitai" in (self.net.get("civitai_base") or ""):
            hit = self._search_civitai(model)
            if hit:
                return {"url": hit["url"], "type": "civitai", "confidence": "search",
                        "note": f"文件名搜索命中：{hit['name']}（低置信，请人工确认）"}
        return {"url": None, "type": None, "confidence": "none", "note": "未找到来源"}

    def _search_civitai(self, model: dict):
        query = _clean_name(model["filename"])
        if not query:
            return None
        base = self.net.get("civitai_base")
        try:
            url = f"{base}/api/v1/models?query={urllib.parse.quote(query)}&limit=5" + \
                  ("&token=" + self.net["civitai_token"] if self.net.get("civitai_token") else "")
            data = self._get_json(url)
        except Exception:
            return None
        best, best_ratio = None, 0.0
        for item in data.get("items", []):
            ratio = difflib.SequenceMatcher(None, query.lower(),
                                            (item.get("name") or "").lower()).ratio()
            if ratio > best_ratio:
                best, best_ratio = item, ratio
        if best and best_ratio >= 0.62:
            return {"url": f"{base}/models/{best['id']}", "name": best.get("name")}
        return None

    # ---------- 更新检查 ----------
    def check_one(self, model: dict, resolve_if_missing=True) -> dict:
        """检查单个模型。返回 {state, message}。state: ok/available/maybe/error/unknown"""
        url = model.get("source_url")
        if not url:
            src = self.resolve_source(model)
            if src["url"]:
                model["source_url"], model["source_type"], model["source_conf"] = \
                    src["url"], src["type"], src["confidence"]
                self.db.upsert_model({"path": model["path"], "source_url": src["url"],
                                      "source_type": src["type"], "source_conf": src["confidence"]})
                url = src["url"]
            else:
                self._save_state(model, "unknown", "无来源信息，无法检查")
                return {"state": "unknown", "message": "无来源信息"}
        if "civitai" in url:
            return self._check_civitai(model, url)
        if "huggingface" in url:
            return self._check_hf(model, url)
        self._save_state(model, "unknown", "来源类型不支持自动检查，请人工核对")
        return {"state": "unknown", "message": "来源类型不支持"}

    def _check_civitai(self, model: dict, url: str) -> dict:
        base = self.net.get("civitai_base") or "https://civitai.com"
        m = CIVITAI_MODEL_RE.search(url)
        if not m:
            self._save_state(model, "unknown", "URL 中无模型 ID")
            return {"state": "unknown", "message": "URL 中无模型 ID"}
        mid = m.group(1)
        vm = CIVITAI_VER_RE.search(url)
        try:
            data = self._get_json(f"{base}/api/v1/models/{mid}")
        except Exception as e:
            msg = f"Civitai 请求失败：{e}"
            self._save_state(model, "error", msg)
            return {"state": "error", "message": msg}
        versions = data.get("modelVersions") or []
        if not versions:
            self._save_state(model, "unknown", "远端无版本信息")
            return {"state": "unknown", "message": "远端无版本信息"}
        latest = versions[0]
        latest_id, latest_name = str(latest.get("id")), latest.get("name")
        latest_date = (latest.get("updatedAt") or latest.get("createdAt") or "")
        preview_url = None
        imgs = latest.get("images") or []
        if imgs:
            preview_url = imgs[0].get("url")
        known_id = model.get("civitai_version_id") or (vm.group(1) or vm.group(2) if vm else None)
        known_id = str(known_id) if known_id else None
        if known_id and known_id == latest_id:
            state, msg = "ok", "已是最新版本"
        elif known_id:
            state, msg = "available", f"有新版本：{latest_name or latest_id}（{latest_date[:10]}）"
        else:
            # 未绑定版本：比较远端发布时间与本地文件 mtime
            mt = model.get("mtime") or 0
            try:
                remote_ts = time.mktime(time.strptime(latest_date[:19], "%Y-%m-%dT%H:%M:%S"))
            except Exception:
                remote_ts = 0
            if remote_ts and mt and remote_ts > mt + 86400:
                state = "maybe"
                msg = f"远端最新版本晚于本地文件（{latest_date[:10]}），疑似有更新"
            else:
                state = "ok"
                msg = "本地较新或一致（未绑定精确版本）"
        self.db.upsert_model({
            "path": model["path"],
            "civitai_model_id": mid,
            "civitai_version_id": known_id,
            "latest_version_id": latest_id,
            "latest_version_name": latest_name,
            "latest_version_date": latest_date,
            "latest_base_model": latest.get("baseModel"),
            "preview_url": preview_url,
            "update_state": state,
            "last_checked": time.strftime("%Y-%m-%d %H:%M:%S"),
            "check_error": None if state not in ("error",) else msg,
        })
        return {"state": state, "message": msg}

    def _check_hf(self, model: dict, url: str) -> dict:
        m = HF_RE.search(url)
        if not m:
            self._save_state(model, "unknown", "URL 中无仓库 ID")
            return {"state": "unknown", "message": "URL 中无仓库 ID"}
        repo = m.group(1).rstrip("/")
        base = self.net.get("hf_base") or "https://huggingface.co"
        try:
            data = self._get_json(f"{base}/api/models/{repo}")
        except Exception as e:
            msg = f"HuggingFace 请求失败：{e}"
            self._save_state(model, "error", msg)
            return {"state": "error", "message": msg}
        last_mod = data.get("lastModified") or ""
        mt = model.get("mtime") or 0
        try:
            remote_ts = time.mktime(time.strptime(last_mod[:19], "%Y-%m-%dT%H:%M:%S"))
        except Exception:
            remote_ts = 0
        if remote_ts and mt and remote_ts > mt + 86400:
            state = "maybe"
            msg = f"仓库有更新（lastModified {last_mod[:10]}）"
        else:
            state = "ok"
            msg = "本地与仓库一致或本地较新"
        self.db.upsert_model({
            "path": model["path"],
            "latest_version_date": last_mod,
            "update_state": state,
            "last_checked": time.strftime("%Y-%m-%d %H:%M:%S"),
            "check_error": None,
        })
        return {"state": state, "message": msg}

    def _save_state(self, model: dict, state: str, msg: str):
        self.db.upsert_model({
            "path": model["path"], "update_state": state,
            "last_checked": time.strftime("%Y-%m-%d %H:%M:%S"),
            "check_error": msg if state in ("error", "unknown") else None,
        })

    # ---------- 批量 ----------
    def check_many(self, rows, progress_every=1):
        total = len(rows)
        done = 0
        summary = {"ok": 0, "available": 0, "maybe": 0, "error": 0, "unknown": 0}
        for r in rows:
            try:
                res = self.check_one(dict(r))
            except Exception as e:
                res = {"state": "error", "message": str(e)}
            summary[res["state"]] = summary.get(res["state"], 0) + 1
            done += 1
            if done % progress_every == 0 and self.progress_cb:
                self.progress_cb(f"更新检查 {done}/{total}："
                                 f"最新 {summary['ok']} · 可更新 {summary['available'] + summary['maybe']} · "
                                 f"失败 {summary['error'] + summary['unknown']}")
            time.sleep(float(self.net.get("request_interval") or 1.0))
        return summary


# ---------- 工具 ----------

def _sidecar_paths(model_path: str):
    base, _ = os.path.splitext(model_path)
    parent = os.path.dirname(model_path)
    cands = [base + ext for ext in (".json", ".txt", ".md", ".civitai", ".url")]
    cands.append(os.path.join(parent, "metadata", os.path.basename(base) + ".json"))
    return [c for c in cands if os.path.isfile(c)]


def _urls_in_file(path: str):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read(256 * 1024)
    except OSError:
        return []
    urls = re.findall(r"https?://[^\s\"'<>\\]+", text)
    priority = [u for u in urls if "civitai.com/models" in u or "huggingface.co" in u]
    return priority + [u for u in urls if u not in priority][:3]


def _load_registry() -> dict:
    try:
        with open(cfgmod.SOURCES_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_registry(reg: dict):
    os.makedirs(cfgmod.DATA_DIR, exist_ok=True)
    with open(cfgmod.SOURCES_PATH, "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)


def _clean_name(filename: str) -> str:
    stem = os.path.splitext(filename)[0]
    stem = re.sub(r"[\(\[\{].*?[\)\]\}]", " ", stem)          # 去括号段
    stem = re.sub(r"[-_. ]?\d{4,}([-_.]\d+)*$", " ", stem)     # 去尾部步数
    stem = re.sub(r"\b(v\d+|final|fixed|pruned|fp16|fp8|f16|e?epoch\d+|s\d+|comfyui)\b", " ", stem, flags=re.I)
    stem = re.sub(r"[\\/]+", " ", stem)
    stem = re.sub(r"[_\-.]+", " ", stem)
    return re.sub(r"\s+", " ", stem).strip()
