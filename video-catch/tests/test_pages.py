import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import Store
from pages import bili_page, observed_formats, downloader_formats


class PageTests(unittest.TestCase):
    URL = "https://www.bilibili.com/video/BV1WuYh6VEaS/"

    def setUp(self):
        self.store = Store()
        self.store.sync("browser-123", "Edge", [{"id": 1, "url": self.URL + "?spm_id_from=tracking", "title": "test"}])
        self.data = {"client": "browser-123", "tabId": 1, "url": self.URL}

    def test_watch_discovers_bili_without_file_requests(self):
        self.assertEqual(len(self.store.items), 0)
        self.store.toggle(["browser-123:1"])
        self.assertEqual(len(self.store.items), 1)
        self.assertEqual(next(iter(self.store.items.values()))["kind"], "B站页面解析")
        self.store.add_page(self.data)
        self.assertEqual(len(self.store.items), 1)

    def test_upgrade_preserves_headers_and_download_state(self):
        self.store.toggle(["browser-123:1"])
        formats = [{"url": "https://cdn.test/v.m4s", "role": "video"}, {"url": "https://cdn.test/a.m4s", "role": "audio"}]
        result = self.store.add_page(dict(self.data, formats=formats, headers={"User-Agent": "browser"}))
        item = self.store.items[result["id"]]
        self.assertEqual(item["kind"], "B站音画合并")
        self.store.update(result["id"], status="下载中")
        self.store.add_page(self.data)
        self.assertEqual(item["status"], "下载中")
        self.assertEqual(item["headers"]["User-Agent"], "browser")
        self.assertEqual(len(item["formats"]), 2)

    def test_ignore_unwatched_paused_and_stale_navigation(self):
        self.assertFalse(self.store.add_page(self.data)["added"])
        self.store.toggle(["browser-123:1"])
        self.assertFalse(self.store.add_page(dict(self.data, url=self.URL + "?p=2"))["added"])
        self.store.paused = True
        result = self.store.sync("browser-123", "Edge", [{"id": 1, "url": self.URL}])
        self.assertEqual(result["watching"], [])

    def test_parts_and_hosts_are_distinct(self):
        self.assertEqual(bili_page(self.URL + "?spm=x&p=2"), self.URL + "?p=2")
        self.assertIsNone(bili_page("https://bilibili.com.evil.test/video/BV123/"))
        self.assertIsNone(bili_page("https://www.bilibili.com/"))

    def test_cannot_forward_options_or_unsupported_protocols(self):
        self.assertEqual(observed_formats([{"url": "file:///secret", "role": "combined"}]), [])
        self.assertEqual(observed_formats([{"url": "https://x/v", "role": "video"}]), [])
        self.assertEqual(observed_formats([{"url": "https://x/v", "role": "combined", "drm": True}]), [])
        formats = downloader_formats([{"url": "https://x/v", "role": "combined", "postprocessors": [{"exec": "bad"}]}])
        self.assertNotIn("postprocessors", formats[0])


if __name__ == "__main__": unittest.main()
