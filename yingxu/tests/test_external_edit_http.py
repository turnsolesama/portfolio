import hashlib
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from server import Application, Server


class ExternalEditHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='yingxu-external-edit-http-')
        self.root = Path(self.tmp.name).resolve()
        with patch('yingxu.skills.Path.home', return_value=self.root / 'empty-home'):
            self.app = Application(self.root / 'data', self.root / 'projects')
        self.path = self.root / '外部文稿.md'
        self.path.write_bytes(b'original\r\n')
        self.server = Server(('127.0.0.1', 0), self.app)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        status, opened = self.request('/api/external-open', {'paths': [str(self.path)]})
        self.assertEqual(status, 200, opened)
        self.iid = opened['entries'][0]['id']
        self.endpoint = '/api/external/' + self.iid + '/content'
        status, detail = self.request('/api/external/' + self.iid, method='GET')
        self.assertEqual(status, 200, detail)
        self.etag = detail['content']['etag']

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        self.app.jobs.pool.shutdown(wait=True); self.app.thumbnails.pool.shutdown(wait=True)
        self.app.context.close(); self.tmp.cleanup()

    def request(self, path, fields=None, headers=None, method='POST'):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        hdr = {'Content-Type': 'application/json', 'X-YingXu-Token': self.app.token, **(headers or {})}
        raw = json.dumps(fields, ensure_ascii=False).encode() if fields is not None else None
        conn.request(method, path, body=raw, headers=hdr)
        response = conn.getresponse(); body = response.read(); status = response.status; conn.close()
        return status, json.loads(body)

    def test_same_origin_save_returns_updated_detail_backup_and_keeps_project_index_empty(self):
        origin = {'Origin': f'http://127.0.0.1:{self.server.server_port}'}
        with patch.object(self.app.context, 'request') as context:
            status, body = self.request(self.endpoint, {'etag': self.etag, 'content': '修改\n'}, origin)
            self.assertEqual(status, 200, body); context.assert_not_called()
        self.assertEqual(self.path.read_bytes(), '修改\r\n'.encode())
        self.assertEqual(body['id'], self.iid); self.assertTrue(body['editable'])
        self.assertEqual(body['content']['etag'], hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertTrue(body['backup_id'])
        self.assertEqual(self.app.store.list_projects(), [])
        self.assertEqual(next((self.root / 'data').glob('external-versions/*/*.md')).read_bytes(), b'original\r\n')

    def test_bad_token_cross_origin_host_and_fetch_site_cannot_mutate(self):
        body = {'etag': self.etag, 'content': 'rejected'}
        for headers in ({'X-YingXu-Token': ''}, {'X-YingXu-Token': 'invalid'},
                        {'Origin': 'https://evil.example'}, {'Host': 'evil.example'},
                        {'Sec-Fetch-Site': 'cross-site'}):
            with self.subTest(headers=headers):
                self.assertEqual(self.request(self.endpoint, body, headers)[0], 403)
        self.assertEqual(self.path.read_bytes(), b'original\r\n')
        self.assertFalse((self.root / 'data' / 'external-versions').exists())

    def test_unregistered_and_expired_capability_cannot_write(self):
        body = {'etag': self.etag, 'content': 'rejected'}
        self.assertEqual(self.request('/api/external/' + 'f' * 32 + '/content', body)[0], 404)
        self.app.external.entries[self.iid]['expires'] = 0
        self.assertEqual(self.request(self.endpoint, body)[0], 404)
        self.assertEqual(self.path.read_bytes(), b'original\r\n')

    def test_wrong_method_arbitrary_path_and_stale_etag_leave_file_intact(self):
        body = {'etag': self.etag, 'content': 'rejected'}
        self.assertEqual(self.request(self.endpoint, body, method='PUT')[0], 404)
        self.assertEqual(self.request(self.endpoint, {**body, 'path': str(self.root / 'another.md')})[0], 400)
        self.path.write_bytes(b'edited elsewhere')
        status, result = self.request(self.endpoint, body)
        self.assertEqual(status, 409, result)
        self.assertEqual(self.path.read_bytes(), b'edited elsewhere')

    def test_second_explicit_open_keeps_same_id_and_new_save_uses_new_etag(self):
        status, opened = self.request('/api/external-open', {'paths': [str(self.path)]})
        self.assertEqual(status, 200); self.assertEqual(opened['entries'][0]['id'], self.iid)
        status, saved = self.request(self.endpoint, {'etag': self.etag, 'content': 'one'})
        self.assertEqual(status, 200, saved)
        self.assertEqual(self.request(self.endpoint, {'etag': self.etag, 'content': 'stale'})[0], 409)
        status, saved = self.request(self.endpoint, {'etag': saved['content']['etag'], 'content': 'two'})
        self.assertEqual(status, 200, saved); self.assertEqual(self.path.read_bytes(), b'two')


if __name__ == '__main__':
    unittest.main()
