"""In-memory browser discovery and authenticated loopback bridge."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from pages import bili_page, youtube_page, video_page, observed_formats

PORT = 18796
MAX_ITEMS = 1000


def http_url(value):
    if not isinstance(value, str) or len(value) > 16000:
        raise ValueError("请输入有效的 HTTP 或 HTTPS 视频/网页链接")
    try:
        parts = urlsplit(value.strip())
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
            raise ValueError()
        _ = parts.port
    except ValueError:
        raise ValueError("请输入有效的 HTTP 或 HTTPS 视频/网页链接") from None
    return value.strip()


def media_kind(url, content_type=""):
    path = urlsplit(url).path.lower()
    mime = content_type.lower().split(";")[0].strip()
    if path.endswith(".m3u8") or mime in ("application/vnd.apple.mpegurl", "application/x-mpegurl", "audio/mpegurl", "audio/x-mpegurl"):
        return "HLS 分段视频"
    if path.endswith(".mpd") or mime == "application/dash+xml":
        return "DASH 分段视频"
    # Fragments must never be presented as complete videos.
    if path.endswith((".ts", ".m4s", ".cmfv", ".cmfa", ".m4a", ".aac")) or mime in ("video/mp2t", "audio/mp4"):
        return None
    if path.endswith((".mp4", ".webm", ".mov", ".mkv", ".flv", ".avi", ".m4v")) or mime.startswith("video/"):
        return "视频文件"
    return None


def safe_headers(headers):
    allowed = {"referer": "Referer", "user-agent": "User-Agent", "origin": "Origin"}
    return {allowed[str(k).lower()]: v for k, v in headers.items()
            if str(k).lower() in allowed and isinstance(v, str) and len(v) < 16000 and "\r" not in v and "\n" not in v}


def display_host(url):
    return urlsplit(url).hostname or "未知来源"


class Store:
    def __init__(self):
        self.lock = threading.RLock()
        self.clients = {}
        self.tabs = {}
        self.watching = set()
        self.items = {}
        self.paused = False

    def sync(self, client, name, tabs):
        if not re.fullmatch(r"[a-zA-Z0-9_-]{8,80}", client):
            raise ValueError("无效的浏览器标识")
        if not isinstance(tabs, list) or len(tabs) > 1000:
            raise ValueError("标签页列表过大")
        current = {}
        for tab in tabs:
            if not isinstance(tab, dict) or not isinstance(tab.get("id"), int):
                continue
            try:
                url = http_url(tab.get("url", ""))
            except ValueError:
                continue
            key = f"{client}:{tab['id']}"
            current[key] = {"key": key, "client": client, "tabId": tab["id"], "title": str(tab.get("title", "未命名页面"))[:300], "url": url, "browser": str(name)[:50]}
        with self.lock:
            old = {k for k, t in self.tabs.items() if t["client"] == client}
            for key in old - current.keys():
                self.tabs.pop(key, None)
                self.watching.discard(key)
            self.tabs.update(current)
            self.clients[client] = time.monotonic()
            for key in current:
                if key in self.watching and not self.paused and video_page(current[key]["url"]):
                    self.add_page({"client": client, "tabId": current[key]["tabId"], "url": current[key]["url"]})
            watching = [] if self.paused else [t["tabId"] for k, t in current.items() if k in self.watching]
        return {"ok": True, "watching": watching, "protocol": 3}

    def snapshot(self):
        with self.lock:
            expired = {c for c, last in self.clients.items() if time.monotonic() - last > 95}
            for c in expired:
                del self.clients[c]
            for key in list(self.tabs):
                if self.tabs[key]["client"] in expired:
                    del self.tabs[key]
                    self.watching.discard(key)
            return ([dict(t, watching=k in self.watching) for k, t in self.tabs.items()],
                    [dict(v) for v in self.items.values()], len(self.clients))

    def toggle(self, keys):
        with self.lock:
            for key in keys:
                if key in self.tabs:
                    self.watching.symmetric_difference_update({key})
                    tab = self.tabs[key]
                    if key in self.watching and not self.paused and video_page(tab["url"]):
                        self.add_page({"client": tab["client"], "tabId": tab["tabId"], "url": tab["url"]})

    def set_watching(self, keys, enabled):
        with self.lock:
            changed = [k for k in keys if k in self.tabs and (k in self.watching) != enabled]
            self.toggle(changed)

    def add_page(self, data):
        with self.lock:
            key = f"{data.get('client', '')}:{data.get('tabId', -1)}"
            tab = self.tabs.get(key)
            if not tab or key not in self.watching or self.paused:
                return {"ok": True, "added": False}
            page = http_url(data.get("url", ""))
            current = video_page(tab["url"]) or tab["url"].split("#")[0]
            page = video_page(page) or page.split("#")[0]
            if page != current:
                return {"ok": True, "added": False}  # Ignore callbacks from previous navigation.
            result = self.add({"url": page, "client": tab["client"], "tabId": tab["tabId"],
                               "title": tab["title"], "headers": {"Referer": tab["url"]}}, manual=True)
            if "id" not in result:
                return result
            item = self.items[result["id"]]
            item["title"] = tab["title"]
            item["kind"] = item.get("kind") if item.get("formats") else ("B站页面解析" if bili_page(page) else "YouTube 解析" if youtube_page(page) else "网页视频解析")
            formats = observed_formats(data.get("formats", [])) if bili_page(page) else []
            if formats:
                item["formats"] = formats
                item["kind"] = "B站音画合并"
                item["headers"].update(safe_headers(data.get("headers", {})))
            return result

    def add(self, data, manual=False):
        url = http_url(data.get("url", ""))
        if manual:
            url = video_page(url) or url
        else:
            with self.lock:
                tab = self.tabs.get(f"{data.get('client', '')}:{data.get('tabId', -1)}", {})
                if youtube_page(tab.get("url", "")) and (urlsplit(url).hostname or "").endswith(".googlevideo.com"):
                    # A range or single track is not a complete video.
                    return self.add_page(dict(data, url=tab["url"]))
        kind = "链接解析" if manual else media_kind(url, str(data.get("contentType", "")))
        if not kind:
            return {"ok": True, "added": False}
        with self.lock:
            key = f"{data.get('client', '')}:{data.get('tabId', -1)}"
            if not manual and (self.paused or key not in self.watching or key not in self.tabs):
                return {"ok": True, "added": False}
            ident = hashlib.sha256((key + "\n" + url).encode()).hexdigest()[:20]
            if ident in self.items:
                self.items[ident]["headers"].update(safe_headers(data.get("headers", {})))
                return {"ok": True, "added": False, "id": ident}
            if len(self.items) >= MAX_ITEMS:
                return {"ok": True, "added": False, "full": True}
            tab = self.tabs.get(key, {})
            self.items[ident] = {"id": ident, "url": url, "title": str(data.get("title") or tab.get("title") or display_host(url))[:300],
                                 "source": tab.get("browser", "手动导入"), "host": display_host(url), "kind": kind,
                                 "headers": safe_headers(data.get("headers", {})), "size": str(data.get("size", ""))[:30],
                                 "status": "待保存", "progress": "", "path": "", "error": ""}
            return {"ok": True, "added": True, "id": ident}

    def update(self, ident, **fields):
        with self.lock:
            if ident in self.items:
                self.items[ident].update(fields)


class Bridge(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, store, port=PORT, token=None):
        self.store = store
        self.token = token or secrets.token_urlsafe(24)
        super().__init__(("127.0.0.1", port), Handler)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def reply(self, status, data):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        # Extension host permissions permit its requests. Websites receive no CORS grant.
        origin = self.headers.get("Origin", "")
        if origin and not re.fullmatch(r"chrome-extension://[a-p]{32}", origin):
            self.reply(403, {"error": "禁止网页访问"})
            return
        expected_host = f"127.0.0.1:{self.server.server_port}"
        supplied = self.headers.get("Authorization", "")
        if self.headers.get("Host") != expected_host or not hmac.compare_digest(supplied, f"Bearer {self.server.token}"):
            self.reply(401, {"error": "请在扩展中重新填写本次配对码"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 1_000_000:
                self.reply(413, {"error": "请求大小无效"})
                return
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError("无效请求")
            if self.path == "/sync":
                result = self.server.store.sync(str(data.get("client", "")), data.get("name", "浏览器"), data.get("tabs", []))
            elif self.path == "/media":
                if not isinstance(data.get("headers", {}), dict):
                    raise ValueError("无效请求头")
                result = self.server.store.add(data)
            elif self.path == "/page":
                if not isinstance(data.get("headers", {}), dict):
                    raise ValueError("无效请求头")
                result = self.server.store.add_page(data)
            else:
                self.reply(404, {"error": "不存在"})
                return
            self.reply(200, result)
        except (ValueError, TypeError, KeyError):
            self.reply(400, {"error": "无效请求"})


def start_bridge(store, port=PORT):
    bridge = Bridge(store, port)
    threading.Thread(target=bridge.serve_forever, daemon=True).start()
    return bridge
