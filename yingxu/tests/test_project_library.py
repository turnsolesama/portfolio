import tempfile
import unittest
from pathlib import Path

from yingxu.project_library import ProjectLibrary
from yingxu.store import Store, UserError


class ProjectLibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='yingxu-library-test-')
        self.root = Path(self.tmp.name).resolve()
        self.store = Store(self.root / 'data', self.root / 'projects')
        self.project = self.store.create_project('原有项目')
        self.library = ProjectLibrary(self.store)

    def tearDown(self):
        self.tmp.cleanup()

    def test_existing_projects_unclassified_and_metadata_retained(self):
        result = self.library.snapshot()
        self.assertEqual(result['total'], 1)
        project = result['projects'][0]
        self.assertIsNone(project['folder_id'])
        self.assertIsNone(project['last_opened'])
        self.assertEqual(project['root'], self.project['root'])
        self.assertIn('counts', project)

    def test_assign_and_rename_do_not_move_files_and_survive_restart(self):
        before = {str(p.relative_to(self.root / 'projects')): p.read_bytes() for p in (self.root / 'projects').rglob('*') if p.is_file()}
        folder = self.library.create_folder({'name': '长篇'})
        self.library.assign_project(self.project['id'], {'folder_id': folder['id']})
        self.library.update_folder(folder['id'], {'name': ' 长期创作 '})
        self.library.visit(self.project['id'])
        result = ProjectLibrary(self.store).snapshot()
        self.assertEqual(result['folders'][0]['name'], '长期创作')
        self.assertEqual(result['projects'][0]['folder_id'], folder['id'])
        self.assertEqual(result['recent_ids'], [self.project['id']])
        after = {str(p.relative_to(self.root / 'projects')): p.read_bytes() for p in (self.root / 'projects').rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_visit_and_assignment_preserve_each_other(self):
        folder = self.library.create_folder({'name': '分类'})
        self.library.visit(self.project['id'])
        visit = self.library.assign_project(self.project['id'], {'folder_id': folder['id']})['last_opened']
        self.assertIsNotNone(visit)
        self.assertEqual(self.library.visit(self.project['id'])['folder_id'], folder['id'])
        self.library.assign_project(self.project['id'], {'folder_id': None})
        self.assertIsNone(self.library.snapshot()['projects'][0]['folder_id'])

    def test_cycle_rejected_without_changing_tree(self):
        root = self.library.create_folder({'name': '父'})
        child = self.library.create_folder({'name': '子', 'parent_id': root['id']})
        leaf = self.library.create_folder({'name': '孙', 'parent_id': child['id']})
        before = self.library.snapshot()['folders']
        for parent in [root['id'], child['id'], leaf['id']]:
            with self.assertRaises(UserError) as error:
                self.library.update_folder(root['id'], {'parent_id': parent})
            self.assertEqual(error.exception.status, 409)
        self.assertEqual(self.library.snapshot()['folders'], before)
        self.library.update_folder(leaf['id'], {'parent_id': None})
        self.assertIsNone(next(f for f in self.library.snapshot()['folders'] if f['id'] == leaf['id'])['parent_id'])

    def test_duplicate_siblings_rejected_but_other_parent_allowed(self):
        root = self.library.create_folder({'name': 'Films'})
        for name in ['Films', ' films ']:
            with self.assertRaises(UserError):
                self.library.create_folder({'name': name})
        other = self.library.create_folder({'name': 'Films', 'parent_id': root['id']})
        with self.assertRaises(UserError):
            self.library.update_folder(other['id'], {'parent_id': None})

    def test_nonempty_folder_refused_then_empty_delete(self):
        root = self.library.create_folder({'name': '父'})
        child = self.library.create_folder({'name': '子', 'parent_id': root['id']})
        with self.assertRaises(UserError):
            self.library.delete_folder(root['id'])
        self.library.assign_project(self.project['id'], {'folder_id': child['id']})
        with self.assertRaises(UserError):
            self.library.delete_folder(child['id'])
        self.library.assign_project(self.project['id'], {'folder_id': None})
        self.assertTrue(self.library.delete_folder(child['id'])['deleted'])
        self.assertTrue(self.library.delete_folder(root['id'])['deleted'])
        self.assertTrue(Path(self.project['root']).exists())

    def test_removed_projects_hidden_and_detached_when_empty_folder_deleted(self):
        folder = self.library.create_folder({'name': '旧分类'})
        self.library.assign_project(self.project['id'], {'folder_id': folder['id']})
        self.library.visit(self.project['id'])
        with self.store.connection() as db:
            db.execute('UPDATE projects SET removed=1 WHERE id=?', (self.project['id'],))
        self.assertEqual(self.library.snapshot()['projects'], [])
        self.assertEqual(self.library.snapshot()['recent_ids'], [])
        self.library.delete_folder(folder['id'])
        with self.store.connection() as db:
            db.execute('UPDATE projects SET removed=0 WHERE id=?', (self.project['id'],))
        self.assertIsNone(self.library.snapshot()['projects'][0]['folder_id'])

    def test_invalid_input_and_missing_entities_do_not_write(self):
        for body in [{}, {'name': ''}, {'name': 3}, {'name': 'x'*81}, {'name': 'x\n'}, {'name': 'x', 'extra': 1}, {'name': 'x', 'parent_id': 'missing'}]:
            with self.assertRaises(UserError): self.library.create_folder(body)
        for body in [{}, {'folder_id': []}, {'folder_id': 'missing'}, {'folder_id': None, 'extra': 1}]:
            with self.assertRaises(UserError): self.library.assign_project(self.project['id'], body)
        with self.assertRaises(UserError): self.library.visit('missing')
        with self.assertRaises(UserError): self.library.assign_project('missing', {'folder_id': None})
        self.assertEqual(self.library.snapshot()['folders'], [])

    def disk_snapshot(self):
        return {str(path.relative_to(self.root / 'projects')):
                (path.is_dir(), path.stat().st_mtime_ns,
                 path.read_bytes() if path.is_file() else None)
                for path in (self.root / 'projects').rglob('*')}

    def project_rows(self):
        with self.store.connection() as db:
            return {table: [tuple(row) for row in db.execute('SELECT * FROM ' + table + ' ORDER BY rowid')]
                    for table in ('projects', 'items', 'sources', 'project_library_entries')}

    def test_move_populated_subtree_and_return_to_top_keeps_every_project_and_file(self):
        source = self.library.create_folder({'name': '222'})
        destination = self.library.create_folder({'name': '1111'})
        child = self.library.create_folder({'name': '子分类', 'parent_id': source['id']})
        grandchild = self.library.create_folder({'name': '孙分类', 'parent_id': child['id']})
        projects = [self.project] + [self.store.create_project('合成项目' + str(index)) for index in range(3)]
        for index, (project, folder) in enumerate(zip(projects, (source, child, grandchild, destination))):
            self.store.create_item({'project_id': project['id'], 'name': '合成文稿' + str(index),
                                    'content': '原始内容\r\n😀\n'})
            self.library.assign_project(project['id'], {'folder_id': folder['id']})
            self.library.visit(project['id'])
        before = self.library.snapshot()
        files, rows = self.disk_snapshot(), self.project_rows()
        for parent_id in (destination['id'], None):
            with self.subTest(parent=parent_id):
                moved = self.library.update_folder(source['id'], {'parent_id': parent_id})
                self.assertEqual(moved, {**source, 'parent_id': parent_id})
                # Reload models to prove hierarchy persistence, not just return values.
                after = ProjectLibrary(self.store).snapshot()
                expected = [{**folder, 'parent_id': parent_id} if folder['id'] == source['id'] else folder
                            for folder in before['folders']]
                self.assertEqual(after['folders'], expected)
                self.assertEqual(after['projects'], before['projects'])
                self.assertEqual(after['recent_ids'], before['recent_ids'])
                self.assertEqual(self.project_rows(), rows)
                self.assertEqual(self.disk_snapshot(), files)

    def test_rejected_subtree_moves_do_not_partially_rename_or_reassign(self):
        source = self.library.create_folder({'name': '222'})
        child = self.library.create_folder({'name': '子分类', 'parent_id': source['id']})
        leaf = self.library.create_folder({'name': '孙分类', 'parent_id': child['id']})
        self.library.assign_project(self.project['id'], {'folder_id': leaf['id']})
        self.library.visit(self.project['id'])
        before, rows, files = self.library.snapshot(), self.project_rows(), self.disk_snapshot()
        for parent in (source['id'], child['id'], leaf['id'], 'missing', [], 123):
            with self.subTest(parent=parent):
                with self.assertRaises(UserError):
                    self.library.update_folder(source['id'], {'parent_id': parent, 'name': '不可局部生效的新名'})
                self.assertEqual(self.library.snapshot(), before)
                self.assertEqual(self.project_rows(), rows)
                self.assertEqual(self.disk_snapshot(), files)

    def test_sibling_collision_on_move_and_top_level_return_is_atomic(self):
        destination = self.library.create_folder({'name': '1111'})
        source = self.library.create_folder({'name': '222'})
        nested = self.library.create_folder({'name': '222', 'parent_id': destination['id']})
        self.library.create_folder({'name': 'Films', 'parent_id': destination['id']})
        self.library.assign_project(self.project['id'], {'folder_id': source['id']})
        self.library.visit(self.project['id'])
        before, rows, files = self.library.snapshot(), self.project_rows(), self.disk_snapshot()
        for folder_id, body in (
                (source['id'], {'parent_id': destination['id']}),
                (source['id'], {'parent_id': destination['id'], 'name': ' films '}),
                (nested['id'], {'parent_id': None})):
            with self.subTest(folder_id=folder_id, body=body):
                with self.assertRaises(UserError) as error:
                    self.library.update_folder(folder_id, body)
                self.assertEqual(error.exception.status, 409)
                self.assertEqual(self.library.snapshot(), before)
                self.assertEqual(self.project_rows(), rows)
                self.assertEqual(self.disk_snapshot(), files)


if __name__ == '__main__':
    unittest.main()
