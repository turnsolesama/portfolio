# -*- coding: utf-8 -*-
"""AI Hub —— AI 资产管理终端（零依赖，Python 3.9+）

用法:
  python server.py serve [--port 8765] [--open]   启动本地服务（默认，自动初始化扫描）
  python server.py scan                            终端内执行一次完整扫描
  python server.py check-updates [--limit 50]      终端内执行更新检查
  python server.py stats                           打印概览
"""
import argparse
import json
import os
import sys
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from aihub import api, config as cfgmod, jobs  # noqa: E402
from aihub.db import DB  # noqa: E402

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")

DB_OBJ = None
CFG = {}


class Handler(BaseHTTPRequestHandler):
    server_version = "AIHub/2.2"

    def log_message(self, fmt, *args):
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    # ---------- 响应 ----------
    def _send(self, status, headers, body):
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _send_file(self, rel):
        path = os.path.realpath(os.path.join(FRONTEND_DIR, urllib.parse.unquote(rel)))
        try:
            allowed = os.path.commonpath([path, os.path.realpath(FRONTEND_DIR)]) == os.path.realpath(FRONTEND_DIR)
        except ValueError:
            allowed = False
        if not allowed or not os.path.isfile(path):
            self._send(404, {"Content-Type": "text/plain"}, b"not found")
            return
        ctype = {"html": "text/html; charset=utf-8", "js": "text/javascript; charset=utf-8",
                 "css": "text/css; charset=utf-8", "svg": "image/svg+xml"}.get(
                     os.path.splitext(path)[1][1:], "application/octet-stream")
        with open(path, "rb") as f:
            self._send(200, {"Content-Type": ctype, "Cache-Control": "no-cache"}, f.read())

    # ---------- 请求 ----------
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith("/api/"):
            params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
            status, headers, body = api.dispatch(DB_OBJ, CFG, "GET", parsed.path, params, None)
            self._send(status, headers, body)
            return
        rel = parsed.path.lstrip("/") or "index.html"
        self._send_file(rel)

    def do_POST(self):
        origin = self.headers.get("Origin")
        if origin and urllib.parse.urlparse(origin).netloc != self.headers.get("Host"):
            self._send(403, {"Content-Type": "application/json"}, b'{"error":"origin not allowed"}')
            return
        parsed = urllib.parse.urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            self._send(404, {"Content-Type": "text/plain"}, b"not found")
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            body = json.loads(raw.decode("utf-8")) if raw else None
        except Exception:
            body = None
        params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        status, headers, body_out = api.dispatch(DB_OBJ, CFG, "POST", parsed.path, params, body)
        self._send(status, headers, body_out)


# ---------- 命令 ----------

def cmd_serve(args):
    global DB_OBJ, CFG
    CFG = cfgmod.load_config()
    if args.port:
        CFG["server"]["port"] = args.port
    DB_OBJ = DB()
    api.APP_DB, api.APP_CFG = DB_OBJ, CFG

    # 首次无数据则自动扫描
    n = DB_OBJ.one("SELECT COUNT(*) c FROM models")["c"]
    if CFG.get("scan_roots") and not getattr(args, "no_initial_scan", False) and (n == 0 or not DB_OBJ.get_meta("scan_at")):
        print("[AI Hub] 首次运行，开始后台初始化扫描…")
        jobs.run_full_pipeline(DB_OBJ, CFG)

    port = CFG.get("server", {}).get("port", 8765)
    url = f"http://127.0.0.1:{port}"
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"[AI Hub] 服务已启动: {url}  (Ctrl+C 退出)")
    if args.open:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[AI Hub] 已退出")


def cmd_scan(args):
    global DB_OBJ, CFG
    CFG = cfgmod.load_config()
    DB_OBJ = DB()
    api.APP_DB, api.APP_CFG = DB_OBJ, CFG

    def cb(msg):
        print("  " + msg)

    result = __import__("aihub.scan", fromlist=["scan"]).scan_all(DB_OBJ, CFG, progress_cb=cb)
    stats = __import__("aihub.scan", fromlist=["scan"]).build_models(DB_OBJ, CFG, result, progress_cb=cb)
    DB_OBJ.set_meta("scan_at", __import__("time").strftime("%Y-%m-%d %H:%M:%S"))
    if not args.skip_images:
        __import__("aihub.images", fromlist=["images"]).run_image_scan(DB_OBJ, CFG, progress_cb=cb)
    print(f"[AI Hub] 扫描完成：文件 {result['file_count']}，目录 {result['dir_count']}，"
          f"模型目录 {stats['catalog']}+现场 {stats['filesystem']}（缺失 {stats['missing']}）")


def cmd_check_updates(args):
    global DB_OBJ, CFG
    CFG = cfgmod.load_config()
    DB_OBJ = DB()
    api.APP_DB, api.APP_CFG = DB_OBJ, CFG
    from aihub import updater
    cond = "mtype IN ('Checkpoint','LoRA','Diffusion','VAE','ControlNet','Embedding','IPAdapter','TextEncoder') AND missing=0"
    if args.limit:
        cond += f" LIMIT {args.limit}"
    rows = DB_OBJ.query(f"SELECT * FROM models WHERE {cond}")
    print(f"[AI Hub] 待检查 {len(rows)} 个模型（间隔 {CFG['network'].get('request_interval')}s）")
    ck = updater.Checker(DB_OBJ, CFG, progress_cb=lambda m: print("  " + m))
    summary = ck.check_many(rows)
    print(f"[AI Hub] 完成：{summary}")


def cmd_stats(args):
    global DB_OBJ, CFG
    CFG = cfgmod.load_config()
    DB_OBJ = DB()
    api.APP_DB, api.APP_CFG = DB_OBJ, CFG
    ov = api.overview(DB_OBJ, CFG, {}, None)[2]
    d = json.loads(ov.decode("utf-8"))
    print(f"AI 根目录 : {d['ai_root']}  磁盘可用 {d['disk']['free']/2**30:.0f} GiB")
    print(f"总大小    : {d['total_size_h']}  文件 {d['total_files']}")
    print(f"模型总数  : {d['model_count']}  分类: {d['mtype_counts']}")
    print(f"图片      : {d['image_count']}（带元数据 {d['image_with_meta']}） 被引用模型 {d['used_models']}")
    print(f"待更新    : {d['pending_updates']}  上次扫描: {d['scan_at']}")


def main():
    ap = argparse.ArgumentParser(description="AI Hub - AI 资产管理终端")
    sub = ap.add_subparsers(dest="cmd")
    p_serve = sub.add_parser("serve", help="启动本地服务")
    p_serve.add_argument("--port", type=int, default=None)
    p_serve.add_argument("--open", action="store_true", help="自动打开浏览器")
    p_serve.add_argument("--no-initial-scan", action="store_true", help="启动时不自动扫描")
    p_scan = sub.add_parser("scan", help="执行完整扫描")
    p_scan.add_argument("--skip-images", action="store_true")
    p_ck = sub.add_parser("check-updates", help="执行更新检查")
    p_ck.add_argument("--limit", type=int, default=0)
    sub.add_parser("stats", help="打印概览")
    args = ap.parse_args()
    if args.cmd is None:
        args = ap.parse_args(["serve"])
    {"serve": cmd_serve, "scan": cmd_scan,
     "check-updates": cmd_check_updates, "stats": cmd_stats}.get(args.cmd or "serve")(args)


if __name__ == "__main__":
    main()
