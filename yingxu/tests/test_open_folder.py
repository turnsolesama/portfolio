"""Folder shortcuts must resolve catalogue IDs, never arbitrary client paths."""
import os
from pathlib import Path
from unittest.mock import patch
import unittest

from test_http import HttpTests


@unittest.skipUnless(os.name == 'nt', 'Windows Explorer integration')
class OpenFolderTests(unittest.TestCase):
    setUp = HttpTests.setUp
    tearDown = HttpTests.tearDown
    request = HttpTests.request

    def test_open_project_category_and_nested_folder(self):
        project = self.app.store.create_project('右键菜单')
        folder = self.app.organize.create_folder(project['id'], 'characters', '第 1 集')
        nested = self.app.organize.create_folder(project['id'], 'characters', '主角', folder['id'])
        cases = [
            ({'project_id': project['id']}, Path(project['root'])),
            ({'project_id': project['id'], 'category': 'characters'}, Path(project['root']) / '20_Assets/角色'),
            ({'project_id': project['id'], 'folder_id': nested['id']}, Path(nested['path'])),
        ]
        with patch('server.subprocess.Popen') as launch:
            for payload, expected in cases:
                status, body, _ = self.request('POST', '/api/open-folder', payload)
                self.assertEqual(status, 200, body)
                arguments = launch.call_args.args[0]
                self.assertEqual(Path(arguments[0]).name.lower(), 'explorer.exe')
                self.assertEqual(Path(arguments[1]), expected)
                self.assertEqual(len(arguments), 2)

    def test_deleted_cross_project_and_arbitrary_paths_never_launch(self):
        project = self.app.store.create_project('当前项目')
        other = self.app.store.create_project('其他项目')
        folder = self.app.organize.create_folder(project['id'], 'characters', '角色')
        with patch('server.subprocess.Popen') as launch:
            self.assertEqual(self.request('POST', '/api/open-folder', {'project_id': other['id'], 'folder_id': folder['id']})[0], 403)
            self.assertEqual(self.request('POST', '/api/open-folder', {'project_id': project['id'], 'path': str(self.root)})[0], 400)
            self.assertEqual(self.request('POST', '/api/open-folder', {'project_id': project['id'], 'category': '../../'})[0], 400)
            self.assertEqual(self.request('POST', '/api/open-folder', {'project_id': project['id']}, headers={'X-YingXu-Token': ''})[0], 403)
            self.app.organize.delete_folder(folder['id'])
            self.assertEqual(self.request('POST', '/api/open-folder', {'project_id': project['id'], 'folder_id': folder['id']})[0], 404)
            self.app.organize.delete_project(project['id'])
            self.assertEqual(self.request('POST', '/api/open-folder', {'project_id': project['id']})[0], 404)
            launch.assert_not_called()

    def test_missing_directory_and_reparse_replacement_never_launch(self):
        project = self.app.store.create_project('路径变化')
        folder = self.app.organize.create_folder(project['id'], 'characters', '后来移走')
        path = Path(folder['path'])
        with patch('server.subprocess.Popen') as launch:
            path.rmdir()
            self.assertEqual(self.request('POST', '/api/open-folder', {'project_id': project['id'], 'folder_id': folder['id']})[0], 404)
            path.mkdir()
            from yingxu.store import has_link
            with patch('yingxu.store.has_link', side_effect=lambda p: Path(p) == path or has_link(p)):
                self.assertEqual(self.request('POST', '/api/open-folder', {'project_id': project['id'], 'folder_id': folder['id']})[0], 400)
            launch.assert_not_called()

    def test_file_shortcut_uses_clicked_file_id_and_selects_file(self):
        project = self.app.store.create_project('文件菜单')
        item = self.app.store.create_item({'project_id': project['id'], 'name': '选择这个文件'})
        with patch('server.subprocess.Popen') as launch:
            status, body, _ = self.request('POST', '/api/open', {'id': item['id'], 'action': 'reveal'})
            self.assertEqual(status, 200, body)
            self.assertEqual(launch.call_args.args[0][1:], ['/select,', item['path']])

    def test_skill_shortcut_opens_registered_local_and_external_parent_without_reading_content(self):
        local=self.app.skills.create({'name':'本地合成技能','content':'# 本地正文'})
        external_path=self.app.skills.sources['codex']/'外部合成技能'/'SKILL.md'
        external_path.parent.mkdir(parents=True); external_path.write_text('# 外部合成正文',encoding='utf-8')
        self.app.skills.refresh()
        external=next(skill for skill in self.app.skills.list()['skills'] if skill['source']=='codex')
        with patch('server.subprocess.Popen') as launch, patch('yingxu.skills._read',side_effect=AssertionError('location must not read content')), patch.object(self.app.skills,'_upsert',side_effect=AssertionError('location must not update catalogue')):
            for skill in (local,external):
                status,body,_=self.request('POST','/api/open-folder',{'skill_id':skill['id']})
                self.assertEqual(status,200,body)
                arguments=launch.call_args.args[0]
                self.assertEqual(Path(arguments[0]).name.lower(),'explorer.exe')
                self.assertEqual(arguments[1:],[str(Path(skill['path']).parent)])

    def test_skill_shortcut_rejects_mixed_arbitrary_missing_removed_and_unauthorized_targets(self):
        skill=self.app.skills.create({'name':'仅登记目标'})
        with patch('server.subprocess.Popen') as launch:
            for extra in ({'project_id':None},{'category':'all'},{'folder_id':'root'},{'path':str(self.root)}):
                self.assertEqual(self.request('POST','/api/open-folder',{'skill_id':skill['id'],**extra})[0],400)
            for invalid in (None,[], '../SKILL.md'):
                self.assertEqual(self.request('POST','/api/open-folder',{'skill_id':invalid})[0],400)
            self.assertEqual(self.request('POST','/api/open-folder',{'skill_id':'0'*32})[0],404)
            self.assertEqual(self.request('POST','/api/open-folder',{'skill_id':skill['id']},headers={'X-YingXu-Token':''})[0],403)
            self.app.skills.remove(skill['id'])
            self.assertEqual(self.request('POST','/api/open-folder',{'skill_id':skill['id']})[0],404)
            self.app.skills.restore(skill['id']); Path(skill['path']).unlink()
            self.assertEqual(self.request('POST','/api/open-folder',{'skill_id':skill['id']})[0],404)
            launch.assert_not_called()

    def test_skill_shortcut_revalidates_source_boundary_and_reparse_parents(self):
        skill=self.app.skills.create({'name':'路径保护'})
        parent=Path(skill['path']).parent
        from yingxu.store import has_link
        with patch('server.subprocess.Popen') as launch:
            with patch('yingxu.skills.has_link',side_effect=lambda path: Path(path)==parent or has_link(path)):
                self.assertEqual(self.request('POST','/api/open-folder',{'skill_id':skill['id']})[0],400)
            outside=self.root/'not-registered'/'SKILL.md'; outside.parent.mkdir(); outside.write_text('# synthetic',encoding='utf-8')
            with self.app.store.connection() as db: db.execute('UPDATE yx_skills SET path=? WHERE id=?',(str(outside),skill['id']))
            self.assertEqual(self.request('POST','/api/open-folder',{'skill_id':skill['id']})[0],400)
            launch.assert_not_called()


# Do not expose the imported fixture class to unittest discovery twice.
del HttpTests


if __name__ == '__main__':
    unittest.main()
