import json
import sys
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import Store, start_bridge, media_kind, http_url, safe_headers


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.store.sync("browser-123", "Edge", [{"id": 1, "url": "https://example.com", "title": "测试视频"}])
        self.data = {"client": "browser-123", "tabId": 1, "url": "https://cdn.example.com/movie.mp4?token=a"}

    def test_only_selected_tabs_and_pause(self):
        self.assertFalse(self.store.add(self.data)["added"])
        self.store.toggle(["browser-123:1"])
        self.store.paused = True
        self.assertFalse(self.store.add(self.data)["added"])
        self.store.paused = False
        self.assertTrue(self.store.add(self.data)["added"])
        self.assertFalse(self.store.add(self.data)["added"])
        self.assertEqual(len(self.store.items), 1)

    def test_tab_close_and_browser_isolation(self):
        self.store.toggle(["browser-123:1"])
        self.store.sync("browser-456", "Chrome", [{"id": 1, "url": "https://example.org"}])
        self.assertFalse(self.store.add(dict(self.data, client="browser-456"))["added"])
        self.store.sync("browser-123", "Edge", [])
        self.assertFalse(self.store.add(self.data)["added"])
        self.assertFalse(self.store.watching)

    def test_manifests_and_fragments(self):
        self.assertEqual(media_kind("https://x/v.m3u8?t=1"), "HLS 分段视频")
        self.assertEqual(media_kind("https://x/v", "application/dash+xml"), "DASH 分段视频")
        self.assertIsNone(media_kind("https://x/part.ts", "video/mp2t"))
        self.assertIsNone(media_kind("https://x/part.m4s", "video/mp4"))
        self.assertIsNone(media_kind("https://x/audio.m4a"))
        self.assertIsNone(media_kind("https://x/thing.js"))

    def test_headers_never_include_secrets(self):
        self.assertEqual(safe_headers({"Cookie": "secret", "Authorization": "secret", "Referer": "https://example.com", "Origin": "a\r\nb"}), {"Referer": "https://example.com"})

    def test_url_validation(self):
        for url in ["file:///secret", "ftp://x/v", "blob:https://x/test", "http://u:p@host/", "https://host:bad/", "not a link"]:
            with self.assertRaises(ValueError):
                http_url(url)


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.bridge = start_bridge(self.store, 0)
        self.url = f"http://127.0.0.1:{self.bridge.server_port}"

    def tearDown(self):
        self.bridge.shutdown()
        self.bridge.server_close()

    def post(self, data, token=None, origin=None, path="/sync"):
        headers = {"Content-Type": "application/json", "Authorization": "Bearer " + (token or self.bridge.token)}
        if origin:
            headers["Origin"] = origin
        req = Request(self.url + path, data=json.dumps(data).encode(), headers=headers)
        return urlopen(req, timeout=3)

    def test_authentication_and_web_origin(self):
        for token, origin, status in [("wrong", None, 401), (None, "https://example.com", 403), (None, "chrome-extension://bad", 403)]:
            with self.assertRaises(HTTPError) as error:
                self.post({}, token, origin)
            self.assertEqual(error.exception.code, status)

    def test_extension_sync_and_candidate_flow(self):
        with self.post({"client": "browser-123", "name": "Edge", "tabs": [{"id": 4, "url": "https://example.com"}]}, origin="chrome-extension://" + "a" * 32) as response:
            self.assertIsNone(response.headers.get("Access-Control-Allow-Origin"))
            self.assertTrue(json.load(response)["ok"])
        self.store.toggle(["browser-123:4"])
        with self.post({"client": "browser-123", "tabId": 4, "url": "https://x/v.mp4"}, path="/media") as response:
            self.assertTrue(json.load(response)["added"])

    def test_malformed_input_does_not_crash(self):
        with self.assertRaises(HTTPError) as error:
            self.post({"client": "browser-123", "tabs": "bad"})
        self.assertEqual(error.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
