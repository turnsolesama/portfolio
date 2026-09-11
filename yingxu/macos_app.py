"""映序 macOS preview: private local server with a Cocoa/WebKit window."""
from pathlib import Path
import argparse
import json
import logging
import os
import secrets
import sys
import threading
import time

from server import Application, Server
from yingxu.paths import default_data_root, default_project_root

PREVIEW = '0.4.3-mac.1'


class CloseGuard:
    def __init__(self):
        self.request_id = None
        self.deadline = 0
        self.allowed = False
        self.lock = threading.Lock()

    def begin(self):
        with self.lock:
            if self.request_id and time.monotonic() < self.deadline:
                return None
            self.request_id = secrets.token_hex(16)
            self.deadline = time.monotonic() + 120
            return self.request_id

    def respond(self, request_id, allow):
        with self.lock:
            if request_id != self.request_id or not self.request_id or time.monotonic() > self.deadline:
                return False
            self.request_id = None
            self.allowed = allow is True
            return self.allowed


class Desktop:
    def __init__(self, app, origin):
        self.app = app
        self.origin = origin
        self.window = None
        self.ready = False
        self.guard = CloseGuard()

    def post_message(self, data, token):
        # No arbitrary filesystem methods are exposed to the browser bridge.
        if not isinstance(token, str) or not secrets.compare_digest(token, self.app.token):
            return False
        if not isinstance(data, dict) or self.window.get_current_url() != self.origin + '/?desktop=macos':
            return False
        if data.get('action') == 'desktop-ready':
            self.ready = True
        elif data.get('action') == 'exit-response':
            if self.guard.respond(data.get('requestId'), data.get('allow')):
                self.window.destroy()
        return True

    def closing(self):
        if self.guard.allowed:
            return True
        request_id = self.guard.begin()
        if request_id:
            # Never evaluate JavaScript while blocking Cocoa's closing callback.
            threading.Thread(target=self._ask_close, args=(request_id,), daemon=True).start()
        return False

    def _ask_close(self, request_id):
        try:
            if not self.ready:
                if self.window.create_confirmation_dialog('退出映序', '页面尚未就绪。退出并保留本地数据？'):
                    if self.guard.respond(request_id, True): self.window.destroy()
                else: self.guard.respond(request_id, False)
                return
            message = json.dumps({'action':'prepare-exit','requestId':request_id})
            self.window.run_js('window.yingxuMacReceive(' + message + ')')
        except Exception:
            logging.exception('Close preparation failed')
            self.guard.respond(request_id, False)
            # Native confirmation also provides an exit path if the web process fails.
            if self.window.create_confirmation_dialog('页面响应失败', '无法检查当前文稿。强制退出可能丢失尚未保存的输入，仍要退出吗？'):
                self.guard.allowed = True
                self.window.destroy()


def stop_server(server, app):
    server.shutdown()
    server.server_close()
    app.jobs.pool.shutdown(wait=True, cancel_futures=False)
    app.thumbnails.pool.shutdown(wait=True, cancel_futures=False)
    app.context.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--smoke-test', action='store_true')
    parser.add_argument('--ui-smoke-test', action='store_true')
    args = parser.parse_args()
    if sys.platform != 'darwin': raise SystemExit('此入口仅用于 macOS。')
    if args.smoke_test:
        from macos_smoke import run
        run()
        return
    if args.ui_smoke_test:
        from macos_ui_smoke import run
        run()
        return
    import fcntl
    import webview
    data, projects = default_data_root(), default_project_root()
    data.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=data/'macos.log', level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    lock_path = data/'macos.lock'
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    lock = os.fdopen(descriptor, 'a+')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        from AppKit import NSAlert
        alert = NSAlert.alloc().init(); alert.setMessageText_('映序已经运行，请从 Dock 打开现有窗口。'); alert.runModal()
        lock.close(); return
    app = Application(data, projects)
    try:
        server = Server(('127.0.0.1', 8791), app)
    except OSError:
        app.context.close()
        from AppKit import NSAlert
        alert = NSAlert.alloc().init(); alert.setMessageText_('本地端口 8791 已被占用，请退出原有映序后重试。'); alert.runModal()
        lock.close(); return
    origin = 'http://127.0.0.1:8791'
    desktop = Desktop(app, origin)
    window = webview.create_window('映序 · macOS 试用版', origin+'/?desktop=macos',
        width=1380, height=900, min_size=(980,650),
        background_color='#f7f8f6', text_select=True, zoomable=True)
    desktop.window = window
    app.desktop_message = desktop.post_message
    app.native_picker = lambda kind: window.create_file_dialog(
        webview.FileDialog.FOLDER if kind == 'folder' else webview.FileDialog.OPEN,
        allow_multiple=kind == 'files')
    window.events.closing += desktop.closing
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    webview.settings['ALLOW_FILE_URLS'] = False
    webview.settings['ALLOW_DOWNLOADS'] = False
    try:
        webview.start(private_mode=False, storage_path=str(data/'desktop-macos'),
            localization={'global.quit':'退出','global.cancel':'取消'})
    finally:
        stop_server(server, app)
        lock.close()


if __name__ == '__main__':
    main()
