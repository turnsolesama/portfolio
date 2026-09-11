"""A document title rename preserves original bytes and the draft's etag."""
import hashlib
import os
import sys
from pathlib import Path
import tempfile
import unittest

from yingxu.store import Store, UserError


@unittest.skipUnless(os.name == 'nt' or sys.platform == 'darwin', 'Requires non-overwriting native rename')
class TitleRenameTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='yingxu-title-rename-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.store = Store(self.root / 'data', self.root / 'projects')
        self.project = self.store.create_project('标题改名合成测试')
        self.item = self.store.create_item({'project_id': self.project['id'], 'category': 'scripts',
                                            'name': '原始标题', 'content': '占位'})
        self.path = Path(self.item['path'])
        self.original = b'\xef\xbb\xbf' + '# 原始正文\r\n\r\n中文内容\r\n\r\n'.encode('utf-8')
        self.path.write_bytes(self.original)
        self.opened = self.store.read_content(self.item['id'])

    def test_rename_preserves_bytes_id_etag_then_saves_unsaved_draft(self):
        draft = '# 尚未保存的正文\r\n\r\n追加修改\r\n\r\n'
        renamed = self.store.rename_file(self.item['id'], '修订标题 v1.2.md')
        target = Path(renamed['path'])
        self.assertEqual(renamed['id'], self.item['id'])
        self.assertEqual(target.name, '修订标题 v1.2.md')
        self.assertEqual(target.parent, self.path.parent)
        self.assertFalse(self.path.exists())
        self.assertEqual(target.read_bytes(), self.original)
        self.assertEqual(self.store.read_content(renamed['id'])['etag'], self.opened['etag'])
        self.assertEqual(self.opened['etag'], hashlib.sha256(self.original).hexdigest())
        saved = self.store.save_content(renamed['id'], {'etag': self.opened['etag'], 'content': draft})
        self.assertEqual(saved['content'], draft)
        self.assertEqual(target.read_bytes(), b'\xef\xbb\xbf' + draft.encode('utf-8'))
        self.assertFalse(self.path.exists())
        with self.store.connection() as db:
            versions = db.execute('SELECT path,sha256 FROM versions WHERE item_id=?', (renamed['id'],)).fetchall()
        self.assertEqual(len(versions), 1)
        self.assertEqual(Path(versions[0]['path']).read_bytes(), self.original)
        self.assertEqual(versions[0]['sha256'], self.opened['etag'])

    def test_external_change_then_rename_still_rejects_original_draft_etag(self):
        external = b'\xef\xbb\xbf' + '# 外部程序的新内容\r\n\r\n'.encode('utf-8')
        self.path.write_bytes(external)
        renamed = self.store.rename_file(self.item['id'], '外部改动后新标题')
        target = Path(renamed['path'])
        self.assertEqual(renamed['id'], self.item['id'])
        self.assertEqual(target.suffix, '.md')
        self.assertEqual(target.read_bytes(), external)
        with self.assertRaises(UserError) as error:
            self.store.save_content(renamed['id'], {'etag': self.opened['etag'], 'content': '不能覆盖外部的新内容'})
        self.assertEqual(error.exception.status, 409)
        self.assertEqual(target.read_bytes(), external)
        self.assertFalse(self.path.exists())
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM versions WHERE item_id=?', (renamed['id'],)).fetchone()[0], 0)

    def test_existing_title_is_not_overwritten_and_both_originals_survive(self):
        other = self.store.create_item({'project_id': self.project['id'], 'category': 'scripts',
                                       'name': '已有标题', 'content': '必须保留的另一份正文\n'})
        other_path = Path(other['path'])
        other_original = other_path.read_bytes()
        with self.assertRaises(UserError) as error:
            self.store.rename_file(self.item['id'], '已有标题.md')
        self.assertEqual(error.exception.status, 409)
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertEqual(other_path.read_bytes(), other_original)
        self.assertEqual(self.store.get_item(self.item['id'])['path'], str(self.path))
        self.assertEqual(self.store.get_item(other['id'])['path'], str(other_path))
        self.assertEqual(self.store.read_content(self.item['id'])['etag'], self.opened['etag'])


if __name__ == '__main__':
    unittest.main()
