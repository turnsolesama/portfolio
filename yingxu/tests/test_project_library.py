import tempfile
import unittest
from pathlib import Path

from yingxu.project_library import ProjectLibrary
from yingxu.store import Store, UserError


class ProjectLibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='yingxu-library-test-')
        self.root = Path(self.tmp.name)
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


if __name__ == '__main__':
    unittest.main()
