import unittest
from core import Store
from pages import youtube_page
from network import proxy_value, SYSTEM, DIRECT


class YouTubeTests(unittest.TestCase):
    def test_single_video_identity(self):
        canonical = 'https://www.youtube.com/watch?v=F8zqVO8UqTM'
        for url in [canonical + '&list=RDF8zqVO8UqTM&start_radio=1',
                    'https://youtu.be/F8zqVO8UqTM?t=10',
                    'https://www.youtube.com/shorts/F8zqVO8UqTM']:
            self.assertEqual(youtube_page(url), canonical)
        self.assertIsNone(youtube_page('https://youtube.com.evil.test/watch?v=F8zqVO8UqTM'))
        self.assertIsNone(youtube_page('https://youtube.com/playlist?list=x'))

    def test_idempotent_monitoring_and_fragment_deduplication(self):
        store = Store()
        url = 'https://www.youtube.com/watch?v=F8zqVO8UqTM&list=RDtest'
        store.sync('browser-123', 'Edge', [{'id': 1, 'url': url}])
        key = 'browser-123:1'
        store.set_watching([key], True)
        store.set_watching([key], True)
        self.assertIn(key, store.watching)
        store.add({'client': 'browser-123', 'tabId': 1,
                   'url': 'https://rr1.googlevideo.com/videoplayback?range=0-999', 'contentType': 'video/mp4'})
        self.assertEqual(len(store.items), 1)
        item = next(iter(store.items.values()))
        self.assertEqual(item['kind'], 'YouTube 解析')
        self.assertNotIn('list=', item['url'])
        store.set_watching([key], False)
        store.set_watching([key], False)
        self.assertFalse(store.watching)
        self.assertFalse(store.add_page({'client': 'browser-123', 'tabId': 1, 'url': url})['added'])


class NetworkTests(unittest.TestCase):
    def test_preferences(self):
        self.assertIsNone(proxy_value(SYSTEM))
        self.assertEqual(proxy_value(DIRECT), '')
        self.assertEqual(proxy_value('127.0.0.1:7890'), 'http://127.0.0.1:7890')
        self.assertEqual(proxy_value('socks5://127.0.0.1:1080/'), 'socks5://127.0.0.1:1080')
        for value in ['file:///tmp/test', 'http://localhost:bad', 'http://localhost:0',
                      'http://localhost:90000', 'http://localhost:7890/path', 'http://localhost:7890?x=y']:
            with self.assertRaises(ValueError):
                proxy_value(value)
