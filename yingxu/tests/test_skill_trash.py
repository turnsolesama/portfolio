import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from yingxu.skills import SkillLibrary
from yingxu.store import Store, UserError


class SkillTrashTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve()
        self.patch = patch('yingxu.skills.Path.home', return_value=root / 'home')
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.store = Store(root / 'data', root / 'projects')
        self.project = self.store.create_project('技能回收测试')
        self.library = SkillLibrary(self.store)

    def test_delete_refresh_restore_preserves_file_and_project_binding(self):
        skill = self.library.create({'name': '连续性审查', 'content': '# 检查角色'})
        path = Path(skill['path'])
        original = path.read_bytes()
        self.library.bind(self.project['id'], skill['id'], True)
        result = self.library.remove(skill['id'])
        self.assertEqual(result['batch_id'], skill['id'])
        self.library.refresh()
        self.assertEqual(self.library.list()['total'], 0)
        self.assertEqual(self.library.bound_skills(self.project['id']), [])
        self.assertEqual(self.library.trash()['total'], 1)
        with self.assertRaises(UserError):
            self.library.get(skill['id'])
        self.library.restore(skill['id'])
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(self.library.trash()['total'], 0)
        self.assertEqual(self.library.bound_skills(self.project['id'])[0]['id'], skill['id'])

    def test_external_skill_is_hidden_without_uninstall_and_survives_restart(self):
        path = self.library.sources['codex'] / 'external' / 'SKILL.md'
        path.parent.mkdir(parents=True)
        path.write_text('# 外部能力', encoding='utf-8')
        self.library.refresh()
        skill = self.library.list()['skills'][0]
        self.library.remove(skill['id'])
        again = SkillLibrary(self.store)
        self.assertTrue(path.exists())
        self.assertEqual(again.list()['total'], 0)
        self.assertEqual(again.trash()['entries'][0]['source'], 'codex')
        again.restore(skill['id'])
        self.assertEqual(again.list()['total'], 1)


if __name__ == '__main__':
    unittest.main()
