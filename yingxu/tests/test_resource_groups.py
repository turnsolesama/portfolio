import concurrent.futures
from contextlib import contextmanager
import http.client
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from yingxu.resource_groups import ResourceGroups
from yingxu.store import Store, UserError


class ResourceGroupsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='yingxu-groups-')
        self.root = Path(self.tmp.name).resolve()
        self.store = Store(self.root / 'data', self.root / 'projects')
        self.groups = ResourceGroups(self.store)
        self.project = self.store.create_project('临时分组项目')
        self.items = [self.store.create_item({'project_id': self.project['id'], 'name': f'素材{n}',
                                            'category': category, 'content': f'保留正文 {n}'})
                      for n, category in enumerate(['scripts', 'references', 'scripts', 'references'])]
        self.ids = [item['id'] for item in self.items]

    def tearDown(self):
        self.tmp.cleanup()

    def create(self, ids=None):
        return self.groups.create({'project_id': self.project['id'], 'item_ids': ids or self.ids[:2]})

    def files(self):
        return {str(p.relative_to(self.root)): p.read_bytes()
                for p in (self.root / 'projects').rglob('*') if p.is_file()}

    def test_cross_category_order_and_bounded_summary(self):
        group = self.create(self.ids[::-1])
        self.assertEqual(group['member_ids'], self.ids[::-1])
        self.assertEqual(group['categories'], ['references', 'scripts'])
        self.assertEqual(group['name'], '素材组')
        self.assertEqual(group['revision'], 1)
        summary = self.groups.list(self.project['id'])['groups'][0]
        self.assertNotIn('members', summary)
        self.assertEqual(len(summary['preview']), 4)
        self.assertNotIn('search_content', summary['preview'][0])

    def test_group_lifecycle_preserves_every_file_and_item_path(self):
        before = self.files()
        group = self.create()
        group = self.groups.rename(group['id'], {'name': ' 分镜与参考 ', 'revision': 1})
        self.assertEqual(group['name'], '分镜与参考')
        group = self.groups.add(group['id'], {'item_ids': self.ids[2:], 'revision': 2})
        group = self.groups.remove(group['id'], {'item_ids': self.ids[:3], 'revision': 3})
        self.assertEqual(group['count'], 1)
        group = self.groups.remove(group['id'], {'item_ids': self.ids[3:], 'revision': 4})
        self.assertEqual(group['count'], 0)
        self.groups.dissolve(group['id'], {'revision': 5})
        self.assertEqual(self.groups.list(self.project['id'])['total'], 0)
        self.assertEqual(before, self.files())
        for original in self.items:
            current = self.store.get_item(original['id'])
            self.assertEqual((original['path'], original['category'], original['folder_id']),
                             (current['path'], current['category'], current['folder_id']))

    def test_existing_database_and_restart_preserve_group(self):
        group = self.create()
        fresh = ResourceGroups(Store(self.root / 'data', self.root / 'projects'))
        self.assertEqual(fresh.get(group['id']), group)

    def test_cross_project_and_deleted_member_fail_atomically(self):
        other = self.store.create_project('另外项目')
        item = self.store.create_item({'project_id': other['id'], 'name': '别的文件'})
        for invalid in [item['id'], 'f' * 32]:
            with self.assertRaises(UserError):
                self.create([self.ids[0], invalid])
        with self.store.connection() as db:
            db.execute('UPDATE items SET removed=1 WHERE id=?', (self.ids[1],))
        with self.assertRaises(UserError):
            self.create()
        self.assertEqual(self.groups.list(self.project['id'])['total'], 0)

    def test_duplicate_and_invalid_parameters_rejected(self):
        for ids in [[], self.ids[:1], [self.ids[0]] * 2, [self.ids[0], '../../a'], self.ids * 51, 'bad']:
            with self.assertRaises(UserError):
                self.groups.create({'project_id': self.project['id'], 'item_ids': ids})
        for body in [{'name': 'ok', 'path': 'arbitrary'}, {'name': ''}, {'name': 'a\nb'}, {'name': 'a' * 81}]:
            with self.assertRaises(UserError):
                self.groups.create({'project_id': self.project['id'], 'item_ids': self.ids[:2], **body})
        self.assertEqual(self.groups.list(self.project['id'])['total'], 0)

    def test_unique_membership_and_idempotent_same_group_add(self):
        group = self.create()
        same = self.groups.add(group['id'], {'item_ids': self.ids[:2], 'revision': 1})
        self.assertEqual(same['revision'], 1)
        with self.assertRaises(UserError):
            self.create(self.ids[1:3])
        second = self.create(self.ids[2:])
        with self.assertRaises(UserError):
            self.groups.add(second['id'], {'item_ids': self.ids[:1], 'revision': 1})
        self.assertEqual(self.groups.get(group['id'])['member_ids'], self.ids[:2])

    def test_removed_resources_hidden_and_restored_membership_survives(self):
        group = self.create()
        with self.store.connection() as db:
            db.execute('UPDATE items SET removed=1 WHERE id=?', (self.ids[0],))
        self.assertEqual(self.groups.get(group['id'])['member_ids'], self.ids[1:2])
        with self.store.connection() as db:
            db.execute('UPDATE items SET removed=0 WHERE id=?', (self.ids[0],))
        self.assertEqual(self.groups.get(group['id'])['member_ids'], self.ids[:2])
        with self.store.connection() as db:
            db.execute('UPDATE projects SET removed=1 WHERE id=?', (self.project['id'],))
        for action in [lambda: self.groups.list(self.project['id']), lambda: self.groups.get(group['id']),
                       lambda: self.groups.dissolve(group['id'], {}), lambda: self.groups.add(group['id'], {'item_ids': self.ids[2:]})]:
            with self.assertRaises(UserError) as error:
                action()
            self.assertEqual(error.exception.status, 404)

    def test_revision_rejects_stale_and_invalid_mutations(self):
        group = self.create()
        renamed = self.groups.rename(group['id'], {'name': '新名称', 'revision': 1})
        for action in [lambda: self.groups.rename(group['id'], {'name': '旧名称', 'revision': 1}),
                       lambda: self.groups.add(group['id'], {'item_ids': self.ids[2:], 'revision': 1}),
                       lambda: self.groups.remove(group['id'], {'item_ids': self.ids[:1], 'revision': 1}),
                       lambda: self.groups.dissolve(group['id'], {'revision': 1})]:
            with self.assertRaises(UserError) as error:
                action()
            self.assertEqual(error.exception.status, 409)
        for revision in [True, None, '2', -1]:
            with self.assertRaises(UserError):
                self.groups.dissolve(group['id'], {'revision': revision})
        self.assertEqual(self.groups.get(group['id']), renamed)

    def test_remove_unknown_member_is_atomic_and_dissolve_releases_members(self):
        group = self.create()
        with self.assertRaises(UserError):
            self.groups.remove(group['id'], {'item_ids': self.ids[1:3]})
        self.assertEqual(self.groups.get(group['id'])['member_ids'], self.ids[:2])
        self.groups.dissolve(group['id'], {})
        self.assertEqual(self.create()['member_ids'], self.ids[:2])

    def test_two_connections_cannot_claim_same_item(self):
        other = ResourceGroups(Store(self.root / 'data', self.root / 'projects'))
        barrier = threading.Barrier(2)
        def attempt(groups, ids):
            barrier.wait(timeout=5)
            try:
                return groups.create({'project_id': self.project['id'], 'item_ids': ids})
            except UserError as error:
                return error.status
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(attempt, self.groups, self.ids[:2]), pool.submit(attempt, other, self.ids[1:3])]
            results = [future.result(timeout=10) for future in futures]
        self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
        self.assertIn(409, results)
        self.assertEqual(self.groups.list(self.project['id'])['total'], 1)

    def test_sql_failure_rolls_back_group_and_partial_members(self):
        with self.store.connection() as db:
            db.execute(f"CREATE TRIGGER reject_group_member BEFORE INSERT ON resource_group_members WHEN NEW.item_id='{self.ids[1]}' BEGIN SELECT RAISE(ABORT,'synthetic failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.create()
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM resource_groups').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM resource_group_members').fetchone()[0], 0)

    def test_limits_are_enforced_before_mutation(self):
        with patch('yingxu.resource_groups.MAX_GROUPS', 1):
            group = self.create()
            with self.assertRaises(UserError):
                self.create(self.ids[2:])
        with patch('yingxu.resource_groups.MAX_MEMBERS', 2):
            with self.assertRaises(UserError):
                self.groups.add(group['id'], {'item_ids': self.ids[2:3]})
        self.assertEqual(self.groups.get(group['id'])['count'], 2)

    def test_group_lookup_does_not_scan_unrelated_project_items(self):
        group = self.create()
        with self.store.connection() as db:
            db.executemany('INSERT INTO items(id,project_id,source_id,name,category,kind,ext,path,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?)',
                ((f'{n+100:032x}', self.project['id'], self.items[0]['source_id'], f'无关合成{n}', 'scripts',
                  'markdown', '.md', str(self.root / 'projects' / f'unread-{n}.md'), '2026', '2026') for n in range(4000)))
        connection = self.store.connection
        @contextmanager
        def bounded_connection():
            with connection() as db:
                steps = 0
                def budget():
                    nonlocal steps
                    steps += 100
                    return int(steps > 5000)
                db.set_progress_handler(budget, 100)
                yield db
        self.store.connection = bounded_connection
        try:
            self.assertEqual(self.groups.get(group['id'])['member_ids'], self.ids[:2])
        finally:
            self.store.connection = connection


class ResourceGroupsHttpTests(unittest.TestCase):
    def test_routes_and_origin_token_protection(self):
        from server import Application, Server
        with tempfile.TemporaryDirectory(prefix='yingxu-groups-http-') as temporary:
            root = Path(temporary).resolve()
            with patch('yingxu.skills.Path.home', return_value=root / 'empty-home'):
                app = Application(root / 'data', root / 'projects')
            server = Server(('127.0.0.1', 0), app)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            def request(method, path, data=None, headers=None):
                conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=10)
                hdr = {'X-YingXu-Token': app.token, 'Content-Type': 'application/json', **(headers or {})}
                conn.request(method, path, None if data is None else json.dumps(data), hdr)
                result = conn.getresponse()
                payload = json.loads(result.read())
                conn.close()
                return result.status, payload
            try:
                project = app.store.create_project('路由合成')
                ids = [app.store.create_item({'project_id': project['id'], 'name': str(n)})['id'] for n in range(3)]
                body = {'project_id': project['id'], 'item_ids': ids[:2]}
                self.assertTrue(app.bootstrap()['capabilities']['resource_groups'])
                self.assertEqual(request('POST', '/api/resource-groups', body, {'X-YingXu-Token': ''})[0], 403)
                status, group = request('POST', '/api/resource-groups', body)
                self.assertEqual(status, 201)
                path = '/api/resource-groups/' + group['id']
                self.assertEqual(request('GET', path)[1]['member_ids'], ids[:2])
                self.assertEqual(request('GET', '/api/resource-groups?project=' + project['id'])[1]['total'], 1)
                self.assertEqual(request('GET', path + '?path=C:/private')[0], 400)
                self.assertEqual(request('GET', path, headers={'Origin': 'https://evil.example'})[0], 403)
                self.assertEqual(request('PATCH', path, {'name': '新组', 'revision': 1})[0], 200)
                self.assertEqual(request('POST', path + '/members', {'item_ids': ids[2:], 'revision': 2})[1]['count'], 3)
                self.assertEqual(request('DELETE', path + '/members', {'item_ids': ids[2:], 'revision': 3})[1]['count'], 2)
                self.assertEqual(request('DELETE', path, {'revision': 4})[1]['dissolved'], True)
                self.assertEqual(request('GET', path)[0], 404)
                self.assertTrue(all(Path(app.store.get_item(iid)['path']).exists() for iid in ids))
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
                app.jobs.pool.shutdown(wait=True)
                app.thumbnails.pool.shutdown(wait=True)
                app.context.close()


if __name__ == '__main__':
    unittest.main()
