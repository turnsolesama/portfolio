import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from server import Application
from yingxu.store import UserError


class ClipboardCanvasTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='yingxu-canvas-test-')
        self.root=Path(self.tmp.name).resolve()
        with patch('yingxu.skills.Path.home',return_value=self.root/'home'):
            self.app=Application(self.root/'data',self.root/'projects')
        self.project=self.app.store.create_project('合成画板项目')
        self.pid=self.project['id']

    def tearDown(self):
        self.app.jobs.pool.shutdown(wait=True);self.app.thumbnails.pool.shutdown(wait=True);self.app.context.close()
        self.tmp.cleanup()

    def test_paste_copies_to_clicked_folder_and_never_overwrites(self):
        source=self.root/'原稿.md';source.write_bytes(b'original\r\n')
        folder=self.app.organize.create_folder(self.pid,'scripts','第 1 集')
        target={'project_id':self.pid,'category':'scripts','folder_id':folder['id']}
        with patch('yingxu.clipboard_files.read_files',return_value=[str(source)]):
            first=self.app.paste_clipboard(target)['items'][0]
            second=self.app.paste_clipboard(target)['items'][0]
        self.assertNotEqual(first['path'],second['path'])
        for item in [first,second]:
            self.assertEqual(item['folder_id'],folder['id']);self.assertEqual(Path(item['path']).read_bytes(),source.read_bytes())
        self.assertEqual(source.read_bytes(),b'original\r\n')

    def test_old_project_gets_unclassified_on_demand_without_reclassifying(self):
        root=Path(self.project['root'])/'05_Unclassified';root.rmdir()
        original=self.app.store.create_item({'project_id':self.pid,'category':'references','name':'参考'})
        canvas=self.app.store.create_item({'project_id':self.pid,'category':'unclassified','name':'画板','format':'excalidraw'})
        self.assertEqual(canvas['category'],'unclassified');self.assertTrue(root.is_dir())
        self.assertEqual(self.app.store.get_item(original['id'])['category'],'references')

    def test_canvas_round_trip_backup_conflict_and_invalid_scene(self):
        item=self.app.store.create_item({'project_id':self.pid,'category':'scripts','name':'画板','format':'excalidraw'})
        self.assertTrue(item['path'].endswith('.excalidraw'))
        content=self.app.store.read_content(item['id']);before=Path(item['path']).read_bytes()
        scene=json.loads(content['content']);scene['appState']['viewBackgroundColor']='#eeeeee'
        saved=self.app.store.save_content(item['id'],{'etag':content['etag'],'content':json.dumps(scene)})
        self.assertNotEqual(content['etag'],saved['etag'])
        self.assertTrue(any(p.read_bytes()==before for p in (self.root/'data/versions').rglob('*.excalidraw')))
        with self.assertRaises(UserError):self.app.store.save_content(item['id'],{'etag':content['etag'],'content':content['content']})
        for value in ['{}','not json',json.dumps({**scene,'files':{'remote':{'dataURL':'https://example.org/image.png'}}})]:
            with self.assertRaises(UserError):self.app.store.save_content(item['id'],{'etag':saved['etag'],'content':value})

    def test_clipboard_rejects_folders_and_bad_target_before_copy(self):
        with patch('yingxu.clipboard_files.read_files',return_value=[str(self.root)]):
            with self.assertRaises(UserError):self.app.paste_clipboard({'project_id':self.pid,'category':'scripts'})
        with patch('yingxu.clipboard_files.read_files') as reader:
            with self.assertRaises(UserError):self.app.paste_clipboard({'project_id':self.pid,'category':'missing'})
            reader.assert_not_called()

    def test_external_canvas_preserves_original_and_conflict_protection(self):
        from yingxu.canvas import EMPTY
        source=self.root/'外部画板.excalidraw'
        original=EMPTY
        source.write_text(original,encoding='utf-8')
        item=self.app.external.open({'paths':[str(source)]})['entries'][0]
        content=self.app.external.detail(item['id'])['content']
        self.assertTrue(content['editable'])
        scene=json.loads(content['content']);scene['appState']['viewBackgroundColor']='#eeeeee'
        self.app.external.save(item['id'],{'etag':content['etag'],'content':json.dumps(scene)})
        self.assertEqual(json.loads(source.read_text())['appState']['viewBackgroundColor'],'#eeeeee')
        with self.assertRaises(UserError):
            self.app.external.save(item['id'],{'etag':content['etag'],'content':original})
