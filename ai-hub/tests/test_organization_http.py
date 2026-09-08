"""Real loopback HTTP regression tests; all assets and state are temporary."""
import http.client
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest import mock

import server
from aihub import api, config, db as dbmod, jobs, organizer


class OrganizationHTTP(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='aihub-http-')
        self.base = Path(self.tmp.name)
        self.root = self.base / 'Assets on another disk'
        self.root.mkdir()
        self.app = self.base / 'Programs' / 'Hub'
        self.app.mkdir(parents=True)
        self.data = self.app / 'data'
        self.data.mkdir()
        self.patches = []
        for key, value in [('APP_DIR', self.app), ('DATA_DIR', self.data),
                           ('CONFIG_PATH', self.data / 'config.json'),
                           ('REPORTS_DIR', self.data / 'reports'),
                           ('DB_PATH', self.data / 'hub.sqlite')]:
            self.patch(config, key, str(value))
        self.cfg = config.default_config(use_environment=False)
        self.db = dbmod.DB()
        self.patch(server, 'CFG', self.cfg)
        self.patch(server, 'DB_OBJ', self.db)
        self.patch(api, 'APP_CFG', self.cfg)
        self.patch(api, 'APP_DB', self.db)
        self.patch(jobs, '_jobs', {})
        self.release_preview = threading.Event()
        self.initial_threads = set(threading.enumerate())
        class QuietHandler(server.Handler):
            def log_message(self, *args):
                pass
        self.httpd = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, name='fixture-http-server', daemon=True)
        self.thread.start()

    def patch(self, obj, key, value):
        patch = mock.patch.object(obj, key, value)
        patch.start()
        self.patches.append(patch)

    def tearDown(self):
        self.release_preview.set()
        self.httpd.shutdown()
        self.thread.join(timeout=5)
        self.httpd.server_close()
        owned = [thread for thread in threading.enumerate() if thread not in self.initial_threads
                 and thread.name in {'organize-preview', 'organize', 'organize-undo'}]
        for thread in owned:
            thread.join(timeout=5)
        try:
            self.assertFalse(any(thread.is_alive() for thread in owned), 'Fixture background jobs leaked')
        finally:
            self.db.conn.close()
            for patch in reversed(self.patches):
                patch.stop()
            self.tmp.cleanup()

    def request(self, method, path, body=None, headers=None, raw=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        request_headers = {'Content-Type': 'application/json'}
        request_headers.update(headers or {})
        payload = raw if raw is not None else (json.dumps(body).encode('utf-8') if body is not None else None)
        try:
            connection.request(method, path, body=payload, headers=request_headers)
            response = connection.getresponse()
            data = response.read()
            try:
                decoded = json.loads(data)
            except ValueError:
                decoded = data.decode('utf-8', errors='replace')
            return response.status, decoded
        finally:
            connection.close()

    def ok(self, method, path, body=None):
        status, data = self.request(method, path, body)
        self.assertEqual(status, 200, data)
        return data

    def wait_job(self, name):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            entries = self.ok('GET', '/api/jobs')['jobs']
            entry = next((job for job in entries if job['name'] == name), None)
            if entry and entry['status'] != 'running':
                self.assertEqual(entry['status'], 'done', entry)
                return entry
            time.sleep(0.02)
        self.fail('Fixture background job did not complete: ' + name)

    def test_http_preview_apply_undo_runs_asynchronously_and_preserves_original(self):
        original = self.root / 'fixture.png'
        payload = b'SYNTHETIC IMAGE FIXTURE - NEVER DISPLAYED'
        original.write_bytes(payload)
        original_stat = original.stat()
        self.ok('POST', '/api/workspace/setup', {'root': str(self.root), 'on_startup': False})
        self.assertFalse((self.root / '00_AIHub_Library').exists())
        entered = threading.Event()
        actual_build_plan = organizer.build_plan
        def controlled_preview(*args, **kwargs):
            entered.set()
            if not self.release_preview.wait(5):
                raise RuntimeError('Fixture preview release timed out')
            return actual_build_plan(*args, **kwargs)
        with mock.patch.object(organizer, 'build_plan', side_effect=controlled_preview):
            started = self.ok('POST', '/api/organizer/preview', {})
            self.assertEqual(started['job']['name'], 'organize-preview')
            self.assertTrue(entered.wait(2))
            status = self.ok('GET', '/api/organizer/status')
            self.assertTrue(status['busy'])
            rejected, _ = self.request('POST', '/api/workspace/setup', {'root': str(self.root)})
            self.assertEqual(rejected, 409)
            self.release_preview.set()
            self.wait_job('organize-preview')
        plan = self.ok('GET', '/api/organizer/plan')
        self.assertEqual(len(plan['items']), 1)
        target = Path(plan['items'][0]['target'])
        self.assertFalse(target.exists())
        self.ok('POST', '/api/organizer/apply', {'plan_id': plan['id']})
        self.wait_job('organize')
        self.assertTrue(os.path.samefile(original, target))
        self.assertEqual(target.read_bytes(), payload)
        runs = self.ok('GET', '/api/organizer/status')['runs']
        self.assertEqual(len(runs), 1)
        self.ok('POST', '/api/organizer/undo', {'run_id': runs[0]['id']})
        self.wait_job('organize-undo')
        self.assertFalse(target.exists())
        self.assertEqual(original.read_bytes(), payload)
        self.assertEqual(original.stat().st_ino, original_stat.st_ino)
        self.assertEqual(original.stat().st_mtime_ns, original_stat.st_mtime_ns)
        self.assertFalse(self.ok('GET', '/api/organizer/status')['busy'])

    def test_post_rejects_foreign_host_before_mutation(self):
        for host in ('attacker.example', '127.0.0.1:1', 'localhost', f'localhost.attacker.example:{self.port}'):
            with self.subTest(host=host):
                status, _ = self.request('POST', '/api/workspace/setup', {'root': str(self.root)}, {'Host': host})
                self.assertEqual(status, 403)
        self.assertEqual(self.cfg['ai_root'], '')
        self.assertFalse(Path(config.CONFIG_PATH).exists())

    def test_get_rejects_foreign_host_before_revealing_local_state(self):
        for path in ('/api/settings', '/api/organizer/status', '/'):
            with self.subTest(path=path):
                status, _ = self.request('GET', path, headers={'Host': f'attacker.example:{self.port}'})
                self.assertEqual(status, 403)

    def test_post_origin_must_match_local_server(self):
        origins = ('https://attacker.example', 'null', 'http://127.0.0.1:1')
        for origin in origins:
            with self.subTest(origin=origin):
                status, _ = self.request('POST', '/api/workspace/setup', {'root': str(self.root)}, {'Origin': origin})
                self.assertEqual(status, 403)
        origin = f'http://127.0.0.1:{self.port}'
        status, data = self.request('POST', '/api/settings/detect', {'ai_root': str(self.root)}, {'Origin': origin})
        self.assertEqual(status, 200, data)
        self.assertFalse(Path(config.CONFIG_PATH).exists())

    def test_request_size_limit_rejects_oversize_before_reading_body(self):
        for length in (str(2 * 1024 * 1024 + 1), '-1'):
            with self.subTest(length=length):
                status, _ = self.request('POST', '/api/workspace/setup', headers={'Content-Length': length}, raw=b'{}')
                self.assertEqual(status, 413)
        self.assertEqual(self.cfg['ai_root'], '')
        self.assertFalse(Path(config.CONFIG_PATH).exists())

    def test_exact_two_mib_request_reaches_validated_endpoint(self):
        # A syntactically valid but incomplete request distinguishes the size gate
        # (413) from endpoint validation (400), without causing a data mutation.
        limit = 2 * 1024 * 1024
        raw = b'{"padding":"' + b'x' * (limit - len(b'{"padding":""}')) + b'"}'
        self.assertEqual(len(raw), limit)
        status, _ = self.request('POST', '/api/workspace/setup', raw=raw)
        self.assertEqual(status, 400)
        self.assertFalse(Path(config.CONFIG_PATH).exists())

    def test_root_change_only_discards_previous_scan_and_output_scope(self):
        old_output = self.root / '70_Output'
        old_output.mkdir()
        self.ok('POST', '/api/workspace/setup', {'root': str(self.root), 'on_startup': True})
        self.assertEqual(self.cfg['output_roots'], [str(old_output)])
        self.cfg['aliases'] = {'old-alias': str(self.root)}
        replacement = self.base / 'Replacement Assets'
        new_output = replacement / '70_Output'
        new_output.mkdir(parents=True)
        self.ok('POST', '/api/settings', {'ai_root': str(replacement)})
        self.assertEqual(self.cfg['ai_root'], str(replacement))
        self.assertEqual(self.cfg['scan_roots'], [str(replacement)])
        self.assertEqual(self.cfg['output_roots'], [str(new_output)])
        self.assertEqual(self.cfg['aliases'], {})
        self.assertEqual(self.cfg['catalog_dir'], str(replacement / '00_Management' / 'Catalogs'))
        self.assertEqual(self.cfg['organizer'], {'enabled': False, 'root': '', 'on_startup': False})
        self.assertNotIn(str(self.root / '00_AIHub_Library'), self.cfg['scan_exclude_paths'])

    def test_explicit_scan_and_output_roots_outside_safe_zone_are_rejected(self):
        self.ok('POST', '/api/workspace/setup', {'root': str(self.root)})
        outside = self.base / 'Outside Assets'
        outside.mkdir()
        before = json.dumps(self.cfg, sort_keys=True)
        saved = Path(config.CONFIG_PATH).read_bytes()
        for field in ('scan_roots', 'output_roots'):
            with self.subTest(field=field):
                status, _ = self.request('POST', '/api/settings', {field: [str(outside)]})
                self.assertEqual(status, 400)
                self.assertEqual(json.dumps(self.cfg, sort_keys=True), before)
                self.assertEqual(Path(config.CONFIG_PATH).read_bytes(), saved)


if __name__ == '__main__':
    unittest.main()
