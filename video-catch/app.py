from __future__ import annotations

import multiprocessing as mp
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from core import Store, start_bridge, safe_headers
from engine import download_worker
from pages import bili_page, video_page, observed_formats
from network import SYSTEM, DIRECT, proxy_value, discover_local_proxies

BG, PANEL, FG, MUTED, ACCENT = "#0f1722", "#192535", "#e7eef7", "#98abc0", "#79e3c5"
BUSY = {"排队中", "解析中", "下载中", "整理文件"}


def enable_dpi_awareness():
    if os.name == "nt":
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass


class App:
    def __init__(self, root, smoke=False):
        self.root = root
        self.smoke = smoke
        self.store = Store()
        self.bridge = start_bridge(self.store, 0 if smoke else 18796)
        self.jobs = {}
        self.pending = []
        self.closing = False
        self.folder = tk.StringVar(value=str(Path.home() / "Videos" / "VideoCatch"))
        self.notice = tk.StringVar(value="先连接扩展，选中页面后点「开始监听」，再回网页刷新并播放。")
        self.connection = tk.StringVar(value="等待浏览器连接")
        self.detail = tk.StringVar(value="选中视频可查看来源和保存状态。支持多选。")
        self.step = tk.StringVar(value="① 先连接浏览器扩展：复制配对码，在扩展弹窗中粘贴并连接。")
        self.proxy = tk.StringVar(value=SYSTEM)
        self.network_results = queue.Queue()
        self.build_ui()
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.tick()

    def build_ui(self):
        root = self.root
        asset_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "assets"
        if (asset_dir / "videocatch.ico").is_file():
            root.iconbitmap(str(asset_dir / "videocatch.ico"))
        root.title("拾影 VideoCatch · 视频原文件保存")
        scale = max(1, root.winfo_fpixels("1i") / 96)
        available_w, available_h = root.winfo_screenwidth() - 80, root.winfo_screenheight() - 100
        root.geometry(f"{min(round(1120 * scale), available_w)}x{min(round(760 * scale), available_h)}")
        root.minsize(min(round(980 * scale), available_w), min(round(680 * scale), available_h))
        root.configure(bg=BG)
        root.option_add("*Font", ("Microsoft YaHei UI", 10))
        s = ttk.Style()
        s.theme_use("clam")
        s.configure(".", font=("Microsoft YaHei UI", 10))
        s.configure("TFrame", background=BG)
        s.configure("TLabel", background=BG, foreground=FG)
        s.configure("Muted.TLabel", foreground=MUTED)
        s.configure("TButton", background="#29394d", foreground=FG, borderwidth=0, padding=(13, 9))
        s.map("TButton", background=[("active", "#3b526c"), ("disabled", "#1b2633")])
        s.configure("Accent.TButton", background=ACCENT, foreground="#102b26")
        s.map("Accent.TButton", background=[("active", "#a2f1da")])
        s.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=FG, rowheight=34, borderwidth=0)
        s.map("Treeview", background=[("selected", "#315772")], foreground=[("selected", "#ffffff")])
        s.configure("Treeview.Heading", background="#223247", foreground=MUTED, padding=9, relief="flat")
        s.configure("TEntry", fieldbackground=PANEL, foreground=FG, padding=8, insertcolor=FG)
        s.configure("TCombobox", fieldbackground=PANEL, foreground=FG, background="#29394d", arrowcolor=FG, padding=5)
        s.configure("TScrollbar", background="#34475d", troughcolor=BG, borderwidth=0, arrowcolor=MUTED)

        outer = ttk.Frame(root, padding=24)
        outer.pack(fill="both", expand=True)
        top = ttk.Frame(outer)
        top.pack(fill="x")
        ttk.Label(top, text="拾影", font=("Microsoft YaHei UI", 26, "bold")).pack(side="left")
        ttk.Label(top, text="VIDEOCATCH  /  0.3.0", style="Muted.TLabel").pack(side="left", padx=16, pady=(13, 0))
        ttk.Button(top, text="安装浏览器扩展", command=self.open_guide).pack(side="right")
        ttk.Button(top, text="复制配对码", command=self.copy_pairing).pack(side="right", padx=10)
        ttk.Label(outer, text="选定播放来源，发现视频，保存原始画质。", style="Muted.TLabel").pack(anchor="w", pady=(5, 17))
        ttk.Label(outer, textvariable=self.step, foreground=ACCENT, wraplength=1200).pack(anchor="w", pady=(0, 12))

        bar = ttk.Frame(outer)
        bar.pack(fill="x", pady=(0, 12))
        ttk.Label(bar, textvariable=self.connection, foreground=ACCENT).pack(side="left")
        self.pause_button = ttk.Button(bar, text="暂停发现", command=self.pause)
        self.pause_button.pack(side="right")
        ttk.Button(bar, text="取消全部监听", command=self.unwatch).pack(side="right", padx=8)

        split = ttk.Panedwindow(outer, orient="horizontal")
        split.pack(fill="both", expand=True)
        left, right = ttk.Frame(split), ttk.Frame(split)
        split.add(left, weight=1)
        split.add(right, weight=3)
        ttk.Label(left, text="01  选择监听的标签页", font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w", pady=(0, 10))
        self.tabs = self.tree(left, [("watch", "监听", 52), ("title", "页面", 190), ("browser", "浏览器", 105)])
        self.tabs.bind("<Button-1>", self.click_checkbox)
        self.tabs.bind("<Double-1>", lambda e: self.toggle_tabs() if self.tabs.identify_column(e.x) != "#1" else None)
        self.tabs.bind("<space>", lambda _: self.toggle_tabs())
        listening = ttk.Frame(left)
        listening.pack(fill="x", pady=(10, 4))
        ttk.Button(listening, text="开始监听", style="Accent.TButton", command=self.start_tabs).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ttk.Button(listening, text="停止监听", command=self.stop_tabs).pack(side="left", fill="x", expand=True)
        ttk.Button(left, text="直接添加所选页面", command=self.add_tab_pages).pack(fill="x", pady=(0, 4))
        hint = ttk.Label(left, text="单击选中一行，再点「开始监听」。\n回到对应网页刷新并播放，右侧会出现视频。", style="Muted.TLabel", wraplength=290)
        hint.pack(anchor="w", pady=6)
        left.bind("<Configure>", lambda e: hint.configure(wraplength=max(150, e.width - 15)))

        ttk.Label(right, text="02  发现的视频", font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w", pady=(0, 10))
        self.media = self.tree(right, [("title", "视频 / 页面", 220), ("kind", "类型", 115), ("host", "来源", 140), ("status", "状态", 85), ("progress", "进度", 155)])
        self.media.bind("<<TreeviewSelect>>", lambda _: self.show_detail())
        actions = ttk.Frame(right)
        actions.pack(fill="x", pady=(10, 0))
        ttk.Button(actions, text="保存所选视频", style="Accent.TButton", command=self.enqueue).pack(side="left")
        ttk.Button(actions, text="取消下载", command=self.cancel_selected).pack(side="left", padx=8)
        ttk.Button(actions, text="清除所选", command=self.clear_selected).pack(side="right")

        ttk.Label(outer, textvariable=self.detail, style="Muted.TLabel", wraplength=1010).pack(fill="x", pady=(14, 10))
        import_row = ttk.Frame(outer)
        import_row.pack(fill="x")
        ttk.Label(import_row, text="其他来源").pack(side="left", padx=(0, 10))
        self.url = ttk.Entry(import_row)
        self.url.pack(side="left", fill="x", expand=True)
        self.url.bind("<Return>", lambda _: self.import_url())
        ttk.Button(import_row, text="添加视频 / 分享链接", command=self.import_url).pack(side="left", padx=(10, 0))
        output = ttk.Frame(outer)
        output.pack(fill="x", pady=(12, 0))
        ttk.Label(output, text="保存位置").pack(side="left", padx=(0, 10))
        ttk.Entry(output, textvariable=self.folder).pack(side="left", fill="x", expand=True)
        ttk.Button(output, text="更改", command=self.choose_folder).pack(side="left", padx=10)
        ttk.Button(output, text="打开文件夹", command=self.open_folder).pack(side="left")
        net = ttk.Frame(outer)
        net.pack(fill="x", pady=(10, 0))
        ttk.Label(net, text="下载连接").pack(side="left", padx=(0, 10))
        self.proxy_box = ttk.Combobox(net, textvariable=self.proxy, values=(SYSTEM, DIRECT), width=31)
        self.proxy_box.pack(side="left", fill="x", expand=True)
        self.detect_button = ttk.Button(net, text="检测本机代理", command=self.detect_proxy)
        self.detect_button.pack(side="left", padx=(10, 0))
        ttk.Label(net, text="仅影响拾影；YouTube 超时可检测", style="Muted.TLabel").pack(side="left", padx=10)
        ttk.Label(outer, textvariable=self.notice, foreground=ACCENT, wraplength=1030).pack(anchor="w", pady=(13, 0))
        ttk.Label(outer, text="原文件直接下载 · 分段流合并不转码 · DRM 不支持 · 其他桌面软件通过链接导入", style="Muted.TLabel").pack(anchor="w", pady=(7, 0))

    def tree(self, parent, columns):
        box = ttk.Frame(parent)
        box.pack(fill="both", expand=True)
        tree = ttk.Treeview(box, columns=[c[0] for c in columns], show="headings", selectmode="extended", height=5)
        for key, title, width in columns:
            tree.heading(key, text=title)
            tree.column(key, width=width, minwidth=min(width, 65), stretch=True)
        scroll = ttk.Scrollbar(box, orient="vertical", command=tree.yview)
        hscroll = ttk.Scrollbar(box, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=scroll.set, xscrollcommand=hscroll.set)
        box.rowconfigure(0, weight=1)
        box.columnconfigure(0, weight=1)
        tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        hscroll.grid(row=1, column=0, sticky="ew")
        return tree

    def copy_pairing(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.bridge.token)
        self.notice.set("已复制本次配对码。打开浏览器扩展粘贴并连接；程序重启后需重新配对。")

    def open_guide(self):
        base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
        os.startfile(str(base / "使用指南.html"))
        import ctypes
        desktop = ctypes.create_unicode_buffer(260)
        ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, desktop)
        standalone = Path(desktop.value) / "拾影浏览器扩展"
        os.startfile(str(standalone if (standalone / "manifest.json").is_file() else base / "extension"))

    def pause(self):
        with self.store.lock:
            self.store.paused = not self.store.paused
        self.pause_button.configure(text="继续发现" if self.store.paused else "暂停发现")
        self.notice.set("已暂停发现新视频。已有下载继续。" if self.store.paused else "已继续发现视频。")

    def unwatch(self):
        with self.store.lock:
            self.store.watching.clear()

    def toggle_tabs(self):
        self.store.toggle(self.tabs.selection())
        self.notice.set("监听选择已更新。请播放或刷新对应页面，让浏览器重新请求视频。")

    def start_tabs(self):
        keys = self.tabs.selection()
        if not keys:
            self.notice.set("请先单击左侧的视频页面。列表为空时，先连接浏览器扩展。")
            return
        with self.store.lock:
            self.store.paused = False
            self.store.set_watching(keys, True)
        self.pause_button.configure(text="暂停发现")
        self.refresh()
        self.notice.set(f"已开始监听 {len(keys)} 个页面。请回到网页刷新并播放；B站等待「音画合并」，YouTube 可直接选条目保存。")

    def stop_tabs(self):
        self.store.set_watching(self.tabs.selection(), False)
        self.refresh()
        self.notice.set("已停止所选页面的监听。已经开始的下载继续运行。")

    def detect_proxy(self):
        self.detect_button.configure(state="disabled")
        self.notice.set("正在检测常见本机代理端口及 YouTube 连通性，约需 5 秒…")
        def detect():
            try:
                self.network_results.put(discover_local_proxies())
            except Exception:
                self.network_results.put([])
        threading.Thread(target=detect, daemon=True).start()

    def add_tab_pages(self):
        for key in self.tabs.selection():
            tab = self.store.tabs.get(key)
            if tab:
                self.store.add({"client": tab["client"], "tabId": tab["tabId"], "url": video_page(tab["url"]) or tab["url"], "title": tab["title"], "headers": {"Referer": tab["url"]}}, manual=True)
        self.refresh()
        self.notice.set("网页已加入列表。B 站建议先勾选监听并刷新，等待「B站音画合并」后保存。")

    def click_checkbox(self, event):
        row = self.tabs.identify_row(event.y)
        if row and self.tabs.identify_column(event.x) == "#1":
            self.store.toggle([row])
            self.refresh()
            return "break"

    def import_url(self):
        try:
            result = self.store.add({"url": self.url.get().strip()}, manual=True)
            if result.get("full"):
                self.notice.set("列表已达到 1000 条，请先清理。")
                return
            self.url.delete(0, "end")
            self.notice.set("链接已添加。选中后点击「保存所选视频」。")
            self.refresh()
            if result.get("id"):
                self.media.selection_set(result["id"])
                self.media.see(result["id"])
        except ValueError as error:
            messagebox.showerror("无法添加", str(error), parent=self.root)

    def choose_folder(self):
        folder = filedialog.askdirectory(parent=self.root, initialdir=str(Path.home()), title="选择视频保存目录")
        if folder:
            self.folder.set(folder)

    def open_folder(self):
        try:
            p = Path(self.folder.get()).expanduser().resolve()
            p.mkdir(parents=True, exist_ok=True)
            os.startfile(str(p))
        except OSError as error:
            messagebox.showerror("无法打开目录", str(error), parent=self.root)

    def enqueue(self):
        selected = self.media.selection()
        if not selected:
            self.notice.set("请先选中一个或多个视频。按 Ctrl / Shift 可以多选。")
            return
        try:
            proxy_value(self.proxy.get())
            if not self.folder.get().strip():
                raise ValueError("请选择保存目录")
            folder = Path(self.folder.get()).expanduser().resolve()
            folder.mkdir(parents=True, exist_ok=True)
        except (OSError, ValueError) as error:
            messagebox.showerror("无法开始下载", str(error), parent=self.root)
            return
        with self.store.lock:
            for ident in selected:
                item = self.store.items.get(ident)
                if item and item["status"] not in BUSY | {"已保存"}:
                    self.store.update(ident, status="排队中", progress="等待下载", error="")
                    self.pending.append((dict(item, proxy=self.proxy.get()), str(folder)))
        self.notice.set("已加入下载队列，最多同时下载 2 个视频。")

    def kill_job(self, ident):
        job = self.jobs.pop(ident, None)
        if job:
            process, events = job
            if process.is_alive():
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], creationflags=subprocess.CREATE_NO_WINDOW,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
                else:
                    process.terminate()
            process.join(timeout=2)
            if process.is_alive():
                process.kill()
                process.join(timeout=2)
            events.close()
        self.pending = [(item, folder) for item, folder in self.pending if item["id"] != ident]
        self.store.update(ident, status="已取消", progress="临时文件保留，可重试")

    def cancel_selected(self):
        for ident in self.media.selection():
            if self.store.items.get(ident, {}).get("status") in BUSY:
                self.kill_job(ident)

    def clear_selected(self):
        with self.store.lock:
            for ident in self.media.selection():
                if self.store.items.get(ident, {}).get("status") not in BUSY:
                    self.store.items.pop(ident, None)
        self.notice.set("已清除所选记录，磁盘上的视频保留。正在下载的记录请先取消。")

    def show_detail(self):
        selection = self.media.selection()
        item = self.store.items.get(selection[0]) if selection else None
        if item:
            self.detail.set((item["error"] or item["path"] or f"{item['source']} · {item['host']} · {item['kind']}；同页可能包含广告或不同清晰度，请核对后保存。")[:500])
        else:
            self.detail.set("选中视频可查看来源和保存状态。支持多选。")

    @staticmethod
    def reconcile(tree, rows):
        old = set(tree.get_children())
        for ident, values in rows:
            if ident in old:
                if tuple(str(v) for v in tree.item(ident, "values")) != tuple(str(v) for v in values):
                    tree.item(ident, values=values)
                old.remove(ident)
            else:
                tree.insert("", "end", iid=ident, values=values)
        for ident in old:
            tree.delete(ident)

    def refresh(self):
        tabs, items, count = self.store.snapshot()
        watching = sum(t["watching"] for t in tabs)
        self.connection.set(f"{'已暂停发现 · ' if self.store.paused else ''}{count} 个浏览器已连接  /  {watching} 个标签页监听中  /  {len(items)} 条视频")
        if self.store.paused:
            self.step.set("已暂停发现。点击「继续发现」，然后回网页播放；已有下载继续。")
        elif not count:
            self.step.set("① 连接浏览器：安装扩展 → 复制配对码 → 在扩展弹窗粘贴并连接。已有链接也可直接在下方添加。")
        elif not watching:
            self.step.set("② 单击左侧的视频页面，再点「开始监听」。可按 Ctrl 多选；不要只选中而未开始监听。")
        elif not items:
            self.step.set("③ 正在监听，等待视频。回到所选网页刷新并播放，视频出现后会列在右侧。")
        else:
            self.step.set("④ 单击右侧视频，再点「保存所选视频」。B站优先等待「音画合并」；YouTube 超时可检测本机代理。")
        self.reconcile(self.tabs, [(t["key"], ("☑" if t["watching"] else "☐", t["title"], t["browser"])) for t in tabs])
        self.reconcile(self.media, [(i["id"], tuple(i[k] for k in ("title", "kind", "host", "status", "progress"))) for i in items])
        self.show_detail()

    def tick(self):
        if self.closing:
            return
        try:
            proxies = self.network_results.get_nowait()
            self.detect_button.configure(state="normal")
            self.proxy_box.configure(values=(SYSTEM, DIRECT, *proxies))
            if proxies:
                self.proxy.set(proxies[0])
                self.notice.set(f"已选择可访问 YouTube 的本机代理 {proxies[0]}。现在可以重新保存失败的视频。")
            else:
                self.notice.set("没有找到可访问 YouTube 的常见本机代理。请启动你的代理客户端，或在「下载连接」中填写其 HTTP / SOCKS5 地址。")
        except queue.Empty:
            pass
        for ident, (process, events) in list(self.jobs.items()):
            def drain():
                try:
                    while True:
                        _ident, fields = events.get_nowait()
                        self.store.update(ident, **fields)
                except queue.Empty:
                    pass
            drain()
            if not process.is_alive():
                process.join(timeout=0)
                drain()
                if self.store.items.get(ident, {}).get("status") in BUSY:
                    self.store.update(ident, status="失败", progress="下载进程已退出", error="下载未完成，请检查网络后重试。")
                del self.jobs[ident]
                events.close()
        while self.pending and len(self.jobs) < 2:
            item, folder = self.pending.pop(0)
            events = mp.get_context("spawn").Queue()
            process = mp.get_context("spawn").Process(target=download_worker, args=(item, folder, events))
            try:
                process.start()
                self.jobs[item["id"]] = (process, events)
            except OSError as error:
                events.close()
                self.store.update(item["id"], status="失败", error=str(error), progress="无法启动下载进程")
        self.refresh()
        self.root.after(500, self.tick)

    def close(self):
        if self.jobs or self.pending:
            if not messagebox.askyesno("退出拾影", "还有视频正在下载或排队。退出将停止下载，是否退出？", parent=self.root):
                return
        self.closing = True
        for ident in list(self.jobs):
            self.kill_job(ident)
        self.pending.clear()
        self.bridge.shutdown()
        self.bridge.server_close()
        self.root.destroy()


def main():
    enable_dpi_awareness()
    root = tk.Tk()
    try:
        captured_check = "--verify-capture-json" in sys.argv
        verification = "--verify-download" in sys.argv or captured_check
        app = App(root, smoke="--smoke-test" in sys.argv or verification)
        if "--smoke-test" in sys.argv:
            root.after(1200, app.close)
        if verification:
            # Developer integration check; uses the same UI queue and frozen worker path.
            url, folder, report = sys.argv[2:5]
            captured = json.loads(Path(url).read_text(encoding="utf-8")) if captured_check else None
            if captured:
                url = captured["url"]
            root.withdraw()
            app.folder.set(folder)
            result = app.store.add({"url": url}, manual=True)
            ident = result["id"]
            if captured:
                app.store.update(ident, formats=observed_formats(captured.get("formats", [])),
                                 title=str(captured.get("title", "test"))[:300],
                                 headers=safe_headers(captured.get("headers", {})))
                app.proxy.set(captured.get("proxy", SYSTEM))
            app.refresh()
            app.media.selection_set(ident)
            app.enqueue()
            attempts = [0]
            def check():
                attempts[0] += 1
                item = app.store.items[ident]
                if (item["status"] in {"失败", "已保存"} and not app.jobs) or attempts[0] > 120:
                    Path(report).write_text(json.dumps({k: item[k] for k in ["status", "path", "error"]}, ensure_ascii=False), encoding="utf-8")
                    for key in list(app.jobs):
                        app.kill_job(key)
                    app.pending.clear()
                    app.close()
                else:
                    root.after(500, check)
            root.after(500, check)
    except OSError as error:
        messagebox.showerror("拾影无法启动", f"本机连接端口不可用。请检查是否已经打开拾影。\n{error}", parent=root)
        root.destroy()
        raise SystemExit(1)
    root.mainloop()


if __name__ == "__main__":
    mp.freeze_support()
    main()
