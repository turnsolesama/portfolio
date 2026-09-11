import functools
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import download_worker, ffmpeg_path
from core import Store


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_): pass


class DownloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.ffmpeg = ffmpeg_path()
        subprocess.run([cls.ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=160x90:rate=15", "-f", "lavfi", "-i", "sine=frequency=440", "-t", "3", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(cls.root / "sample.mp4")], check=True, capture_output=True)
        subprocess.run([cls.ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(cls.root / "sample.mp4"), "-c", "copy", "-hls_time", "1", "-hls_list_size", "0", str(cls.root / "sample.m3u8")], check=True, capture_output=True)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(cls.root)))
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def run_download(self, filename, ident):
        events = queue.Queue()
        download_worker({"id": ident, "url": f"http://127.0.0.1:{self.server.server_port}/{filename}", "headers": {}}, str(self.root / "output"), events)
        values = []
        while not events.empty():
            values.append(events.get()[1])
        return values[-1]

    def test_direct_download_is_byte_identical(self):
        result = self.run_download("sample.mp4", "direct")
        self.assertEqual(result["status"], "已保存", result)
        original = (self.root / "sample.mp4").read_bytes()
        saved = Path(result["path"]).read_bytes()
        self.assertEqual(hashlib.sha256(original).digest(), hashlib.sha256(saved).digest())

    def test_hls_merges_and_decodes_audio_and_video(self):
        result = self.run_download("sample.m3u8", "hls")
        self.assertEqual(result["status"], "已保存", result)
        decoded = subprocess.run([self.ffmpeg, "-hide_banner", "-loglevel", "error", "-i", result["path"], "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-"], capture_output=True)
        self.assertEqual(decoded.returncode, 0, decoded.stderr.decode(errors="replace"))

    def test_failed_download_never_reports_success(self):
        result = self.run_download("missing.mp4?secret=do-not-log", "missing")
        self.assertEqual(result["status"], "失败")
        self.assertNotIn("do-not-log", result["error"])

    def test_bili_separate_m4s_tracks_capture_download_and_merge(self):
        for name, mapping in [("video", "0:v:0"), ("audio", "0:a:0")]:
            subprocess.run([self.ffmpeg, "-v", "error", "-y", "-i", str(self.root / "sample.mp4"),
                            "-map", mapping, "-c", "copy", "-f", "mp4", str(self.root / (name + ".m4s"))], check=True, capture_output=True)
        store = Store()
        url = "https://www.bilibili.com/video/BV1WuYh6VEaS/"
        store.sync("browser-123", "Edge", [{"id": 1, "url": url}])
        store.toggle(["browser-123:1"])
        result = store.add_page({"client": "browser-123", "tabId": 1, "url": url,
            "formats": [{"url": f"http://127.0.0.1:{self.server.server_port}/{role}.m4s", "role": role} for role in ["video", "audio"]]})
        events = queue.Queue()
        download_worker(store.items[result["id"]], str(self.root / "paired"), events)
        while not events.empty():
            fields = events.get()[1]
        self.assertEqual(fields["status"], "已保存", fields)
        check = subprocess.run([self.ffmpeg, "-v", "error", "-i", fields["path"], "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-"], capture_output=True)
        self.assertEqual(check.returncode, 0, check.stderr)


if __name__ == "__main__":
    unittest.main()
