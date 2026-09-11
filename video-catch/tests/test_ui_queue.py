import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
import threading
import time
import tkinter as tk
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import App, enable_dpi_awareness


class QueueTests(unittest.TestCase):
    def test_cancel_stops_worker_and_retry_can_finish(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            # yt-dlp direct transfer needs only a media suffix, and must preserve arbitrary bytes.
            payload = b"fixture" * 100_000
            (folder / "slow.mp4").write_bytes(payload)
            fast = threading.Event()
            class Handler(SimpleHTTPRequestHandler):
                def log_message(self, *_): pass
                def copyfile(self, source, destination):
                    try:
                        while data := source.read(4096):
                            destination.write(data)
                            if not fast.is_set(): time.sleep(.08)
                    except (ConnectionError, OSError):
                        pass
            server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=directory))
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            enable_dpi_awareness()
            root = tk.Tk()
            root.withdraw()
            app = App(root, smoke=True)
            def wait_until(predicate, timeout=20):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    root.update()
                    if predicate(): return
                    time.sleep(.03)
                self.fail("UI queue did not reach expected state")
            try:
                ident = app.store.add({"url": f"http://127.0.0.1:{server.server_port}/slow.mp4"}, manual=True)["id"]
                app.folder.set(str(folder / "output"))
                app.refresh()
                app.media.selection_set(ident)
                app.enqueue()
                wait_until(lambda: app.store.items[ident]["status"] == "下载中")
                process = app.jobs[ident][0]
                app.cancel_selected()
                self.assertFalse(process.is_alive())
                self.assertEqual(app.store.items[ident]["status"], "已取消")
                fast.set()
                app.enqueue()
                wait_until(lambda: app.store.items[ident]["status"] in {"已保存", "失败"} and not app.jobs)
                item = app.store.items[ident]
                self.assertEqual(item["status"], "已保存", item)
                self.assertEqual(Path(item["path"]).read_bytes(), payload)
            finally:
                fast.set()
                for ident in list(app.jobs): app.kill_job(ident)
                app.pending.clear()
                app.close()
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
