"""Real loopback HTTP checks using only resolved temporary data and synthetic PNGs."""
import base64
import hashlib
import http.client
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

from server import Application, Server


PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j3ioAAAAASUVORK5CYII=')
ROOT = Path(__file__).resolve().parents[1]
CSC = Path(os.environ.get('WINDIR', '/missing')) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'


class CaptureHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='yingxu-capture-http-')
        self.root = Path(self.tmp.name).resolve()
        with patch('yingxu.skills.Path.home', return_value=self.root / 'empty-home'):
            self.app = Application(self.root / 'data', self.root / 'projects')
        self.server = Server(('127.0.0.1', 0), self.app)
        self.port = self.server.server_port
        self.assertNotIn(self.port, (8791, 8799))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.project = self.app.store.create_project('截图 HTTP 合成项目')
        self.note = self.app.store.create_item({'project_id': self.project['id'], 'category': 'scripts',
                                               'name': '保留原文', 'content': '占位'})
        self.original = b'\xef\xbb\xbf# ' + '中文原文\r\n\r\n末尾保留\r\n\r\n'.encode('utf-8')
        Path(self.note['path']).write_bytes(self.original)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.app.jobs.pool.shutdown(wait=True)
        self.app.thumbnails.pool.shutdown(wait=True)
        self.app.context.close()
        self.assertFalse(self.thread.is_alive())
        self.tmp.cleanup()

    def request(self, method, path, data=None, raw=None, headers=None):
        hdr = {'Origin': f'http://127.0.0.1:{self.port}', 'X-YingXu-Token': self.app.token}
        if data is not None:
            raw = json.dumps(data).encode('utf-8')
            hdr['Content-Type'] = 'application/json'
        hdr.update(headers or {})
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        try:
            connection.request(method, path, body=raw, headers=hdr)
            response = connection.getresponse()
            return response.status, response.read(), dict(response.getheaders())
        finally:
            connection.close()

    def json(self, method, path, data=None, status=200, headers=None):
        actual, raw, _ = self.request(method, path, data=data, headers=headers)
        self.assertEqual(actual, status, raw)
        return json.loads(raw)

    def upload(self, name='截图 空格[1].png'):
        query = urlencode({'project': self.project['id'], 'category': 'references', 'name': name})
        status, raw, _ = self.request('POST', '/api/upload?' + query, raw=PNG, headers={'Content-Type': 'image/png'})
        self.assertEqual(status, 201, raw)
        return json.loads(raw)

    def assert_original(self):
        self.assertEqual(Path(self.note['path']).read_bytes(), self.original)

    def test_markdown_link_image_range_and_boundaries_preserve_original(self):
        image = self.upload()
        query = urlencode({'note': self.note['id'], 'image': image['id']})
        link = self.json('GET', '/api/markdown-assets/link?' + query)
        self.assertIn('%20', link['relative_path'])
        self.assertNotIn(str(self.root), link['markdown'])
        status, raw, headers = self.request('GET', link['preview_url'])
        self.assertEqual((status, raw), (200, PNG))
        self.assertEqual(headers['Content-Type'], 'image/png')
        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
        status, raw, headers = self.request('GET', link['preview_url'], headers={'Range': 'bytes=0-7'})
        self.assertEqual((status, raw), (206, PNG[:8]))
        self.assertEqual(headers['Content-Range'], f'bytes 0-7/{len(PNG)}')
        self.assertEqual(self.request('HEAD', link['preview_url'])[:2], (200, b''))
        self.assertEqual(self.request('GET', link['preview_url'], headers={'Origin': 'https://untrusted.test'})[0], 403)
        self.assertEqual(self.request('GET', '/api/markdown-assets/link?' + query + '&path=private')[0], 400)
        for path in ['https://example.test/image.png', '//server/a.png', 'C:/private.png', '../../../outside.png']:
            url = '/api/markdown-assets/image?' + urlencode({'note': self.note['id'], 'path': path})
            self.assertNotEqual(self.request('GET', url)[0], 200)
        other = self.app.store.create_project('另外合成项目')
        other_note = self.app.store.create_item({'project_id': other['id'], 'name': '另一文稿'})
        cross = urlencode({'note': other_note['id'], 'image': image['id']})
        self.assertEqual(self.request('GET', '/api/markdown-assets/link?' + cross)[0], 403)
        self.assert_original()
        self.assertEqual(Path(image['path']).read_bytes(), PNG)

    def test_resource_group_crud_preserves_paths_and_exact_file_bytes(self):
        image = self.upload()
        extra = self.app.store.create_item({'project_id': self.project['id'], 'category': 'characters',
                                            'name': '第三份素材', 'content': '保留这一份'})
        originals = [self.note, image, extra]
        before = {entry['id']: (entry['path'], hashlib.sha256(Path(entry['path']).read_bytes()).hexdigest()) for entry in originals}
        group = self.json('POST', '/api/resource-groups', {'project_id': self.project['id'],
                          'item_ids': [self.note['id'], image['id']], 'name': '正文与截图'}, status=201)
        path = '/api/resource-groups/' + group['id']
        self.assertEqual(self.json('GET', path)['count'], 2)
        self.assertEqual(self.json('GET', '/api/resource-groups?project=' + self.project['id'])['total'], 1)
        group = self.json('PATCH', path, {'name': '改名后的合成组', 'revision': group['revision']})
        group = self.json('POST', path + '/members', {'item_ids': [extra['id']], 'revision': group['revision']})
        self.assertEqual(group['count'], 3)
        self.json('PATCH', path, {'name': '过期覆盖', 'revision': 1}, status=409)
        group = self.json('DELETE', path + '/members', {'item_ids': [image['id']], 'revision': group['revision']})
        self.assertEqual(group['count'], 2)
        self.assertTrue(self.json('DELETE', path, {'revision': group['revision']})['dissolved'])
        self.json('GET', path, status=404)
        self.assertEqual(self.json('GET', '/api/resource-groups?project=' + self.project['id'])['total'], 0)
        after = {}
        for entry in originals:
            current = self.app.store.get_item(entry['id'])
            after[entry['id']] = current['path'], hashlib.sha256(Path(current['path']).read_bytes()).hexdigest()
        self.assertEqual(before, after)
        self.assert_original()

    @unittest.skipUnless(os.name == 'nt' and CSC.is_file(), 'Windows .NET compiler required for desktop upload fixture')
    def test_native_capture_fixture_uploads_binary_png_to_same_temporary_server(self):
        executable = self.root / 'capture-tests.exe'
        command = [str(CSC), '/nologo', '/target:exe', '/platform:x64', f'/out:{executable}',
                   '/reference:System.dll', '/reference:System.Core.dll', '/reference:System.Web.Extensions.dll',
                   '/reference:System.Drawing.dll', '/reference:System.Windows.Forms.dll']
        command.extend(str(ROOT / 'desktop' / name) for name in ('Core.cs', 'Integration.cs', 'Capture.cs', 'CaptureTests.cs'))
        build = subprocess.run(command, capture_output=True, timeout=30)
        self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
        run = subprocess.run([str(executable), '--upload-fixture', f'http://127.0.0.1:{self.port}/', self.project['id']],
                             capture_output=True, timeout=45, encoding='utf-8')
        self.assertEqual(run.returncode, 0, run.stderr)
        image = json.loads(run.stdout)
        current = self.json('GET', '/api/items/' + image['id'])
        self.assertEqual((current['project_id'], current['category'], current['kind']),
                         (self.project['id'], 'references', 'image'))
        png = Path(current['path']).read_bytes()
        self.assertEqual(png[:8], b'\x89PNG\r\n\x1a\n')
        self.assertEqual(struct.unpack('>II', png[16:24]), (128, 64))
        link = self.json('GET', '/api/markdown-assets/link?' + urlencode({'note': self.note['id'], 'image': image['id']}))
        self.assertEqual(self.request('GET', link['preview_url'])[:2], (200, png))
        self.assertEqual(self.json('GET', '/api/items?project=' + self.project['id'] + '&category=references')['total'], 1)
        self.assert_original()


if __name__ == '__main__':
    unittest.main()
