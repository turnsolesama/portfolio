import base64
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import quote

from yingxu.markdown_assets import MarkdownAssets
from yingxu.organize import Organize
from yingxu.settings import Settings
from yingxu.store import Store, UserError

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j3ioAAAAASUVORK5CYII=')


class MarkdownAssetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='yingxu-markdown-assets-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.store = Store(self.root/'data', self.root/'projects')
        self.project = self.store.create_project('合成图片项目')
        self.note = self.store.create_item({'project_id':self.project['id'], 'name':'合成正文', 'content':'保持正文'})
        self.assets = MarkdownAssets(self.store)
        self.image = self.make_image(self.project)

    def make_image(self, project, name='截图 空格[1].png'):
        path = Path(project['root']) / name
        path.write_bytes(PNG)
        source = next(s for s in self.store.sources(project['id']) if s['path'] == project['root'])
        self.store.index_files(source, [path])
        with self.store.connection() as db:
            image_id = db.execute('SELECT id FROM items WHERE path=?', (str(path),)).fetchone()[0]
        return self.store.get_item(image_id)

    def test_portable_link_opens_registered_image_without_changing_note(self):
        before = Path(self.note['path']).read_bytes()
        link = self.assets.link(self.note['id'], self.image['id'])
        self.assertIn('../', link['relative_path'])
        self.assertIn('%20', link['relative_path'])
        self.assertNotIn('C:', link['markdown'])
        with self.assets.open_image(self.note['id'], link['relative_path']) as handle:
            self.assertEqual(handle.read(), PNG)
        self.assertEqual(Path(self.note['path']).read_bytes(), before)

    def test_cross_project_and_unregistered_images_cannot_be_embedded(self):
        other = self.make_image(self.store.create_project('其他项目'))
        with self.assertRaises(UserError): self.assets.link(self.note['id'], other['id'])
        path = Path(self.project['root'])/'未登记.png'; path.write_bytes(PNG)
        with self.assertRaises(UserError):
            with self.assets.open_image(self.note['id'], '../'+quote(path.name)): pass

    def test_traversal_protocols_unc_and_private_data_are_rejected(self):
        outside = self.root/'outside.png'; outside.write_bytes(PNG)
        relative = Path(os.path.relpath(outside, Path(self.note['path']).parent)).as_posix()
        for value in [relative, 'https://example.test/a.png', '//server/a.png', r'C:\a.png',
                      'data:image/png,x', '%2Fetc/a.png', r'..\outside.png', 'a\x00.png']:
            with self.subTest(value=value), self.assertRaises(UserError):
                with self.assets.open_image(self.note['id'], value): pass

    def test_recycled_and_shared_images_are_not_served(self):
        link = self.assets.link(self.note['id'], self.image['id'])
        Organize(self.store).delete_items([self.image['id']])
        with self.assertRaises(UserError):
            with self.assets.open_image(self.note['id'], link['relative_path']): pass
        second = self.make_image(self.project, '第二张.png')
        os.link(second['path'], self.root/'alias.png')
        with self.assertRaises(UserError): self.assets.link(self.note['id'], second['id'])

    def test_open_handle_checks_late_hardlink_and_size_budget(self):
        link = self.assets.link(self.note['id'], self.image['id'])
        original = Path.open
        def racing(path, *args, **kwargs):
            if path == Path(self.image['path']): os.link(path, self.root/'late.png')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'open', racing), self.assertRaises(UserError):
            with self.assets.open_image(self.note['id'], link['relative_path']): pass
        second = self.make_image(self.project, '大小测试.png')
        with patch('yingxu.markdown_assets.MAX_IMAGE_BYTES', 1), self.assertRaises(UserError) as caught:
            self.assets.link(self.note['id'], second['id'])
        self.assertEqual(caught.exception.status, 413)

    def test_capture_settings_persist_and_reject_reserved_or_ambiguous_shortcuts(self):
        settings = Settings(self.store.data_root)
        self.assertEqual(settings.get()['capture_hotkey'], 'Ctrl+Alt+Shift+S')
        settings.update({'capture_enabled':False,'capture_hotkey':'Ctrl+Shift+F8'})
        self.assertEqual(Settings(self.store.data_root).get()['capture_hotkey'], 'Ctrl+Shift+F8')
        for value in ['', None, 'Ctrl+S', 'Win+Shift+S', 'Ctrl+Alt+F12', 'Ctrl+Ctrl+A', 'Ctrl+Alt+F25', 'Ctrl+Alt+s']:
            with self.subTest(value=value), self.assertRaises(UserError): settings.update({'capture_hotkey':value})


if __name__ == '__main__': unittest.main()
