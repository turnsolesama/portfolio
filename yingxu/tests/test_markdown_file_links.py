import os
from pathlib import Path
import tempfile
import unittest
from urllib.parse import quote, unquote

from yingxu.markdown_assets import MarkdownAssets
from yingxu.organize import Organize
from yingxu.store import Store, UserError


class MarkdownFileLinkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='yingxu-file-links-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.store = Store(self.root/'data', self.root/'projects')
        self.project = self.store.create_project('链接合成项目')
        self.note = self.store.create_item({'project_id': self.project['id'], 'name': '文稿', 'content': '原始正文'})
        self.assets = MarkdownAssets(self.store)
        self.org = Organize(self.store)
        self.target = self.register(Path(self.project['root'])/'文件 空格[1]#百分%.txt')

    def register(self, path, project=None, external=False):
        project = project or self.project
        path.write_text('合成文件', encoding='utf-8')
        source = self.store.register_source(project['id'], path, 'references') if external else next(s for s in self.store.sources(project['id']) if s['path'] == project['root'])
        self.store.index_files(source, [path])
        with self.store.connection() as db:
            iid = db.execute('SELECT id FROM items WHERE path=?', (str(path),)).fetchone()[0]
        return self.store.get_item(iid)

    def destination(self, item=None):
        linked = self.assets.file_link(self.note['id'], (item or self.target)['id'])
        return linked['relative_path'] + '#yx-item=' + linked['item_id']

    def test_relative_markdown_encodes_filename_and_does_not_modify_note_or_target(self):
        before = {i['id']: Path(i['path']).read_bytes() for i in (self.note, self.target)}
        linked = self.assets.file_link(self.note['id'], self.target['id'])
        self.assertIn('%20', linked['relative_path'])
        self.assertIn('%23', linked['relative_path'])
        self.assertIn('%25', linked['relative_path'])
        self.assertIn(r'\[1\]', linked['markdown'])
        self.assertNotIn('C:', linked['markdown'])
        actual = self.assets.resolve_file(self.note['id'], self.destination())
        self.assertEqual(actual['id'], self.target['id'])
        self.assertEqual(set(actual), {'id', 'project_id', 'name', 'kind'})
        self.assertEqual(before, {i['id']: Path(i['path']).read_bytes() for i in (self.note, self.target)})

    def test_plain_relative_path_resolves_only_registered_file(self):
        linked = self.assets.file_link(self.note['id'], self.target['id'])
        self.assertEqual(self.assets.resolve_file(self.note['id'], linked['relative_path'])['id'], self.target['id'])
        loose = Path(self.project['root'])/'unregistered.txt'; loose.write_text('x')
        with self.assertRaises(UserError): self.assets.resolve_file(self.note['id'], '../unregistered.txt')

    def test_stable_id_survives_target_move_and_rename(self):
        destination = self.destination()
        folder = self.org.create_folder(self.project['id'], 'references', '新目录')
        self.org.move_items([self.target['id']], 'references', folder['id'])
        if os.name == 'nt': self.store.rename_file(self.target['id'], '改名后')
        actual = self.assets.resolve_file(self.note['id'], destination)
        self.assertEqual(actual['id'], self.target['id'])
        with self.assertRaises(UserError): self.assets.resolve_file(self.note['id'], destination.split('#')[0])

    def test_other_project_target_is_rejected_even_with_valid_relative_path(self):
        other = self.store.create_project('另一个项目')
        target = self.register(Path(other['root'])/'other.txt', other)
        with self.assertRaises(UserError): self.assets.file_link(self.note['id'], target['id'])
        with self.assertRaises(UserError): self.assets.resolve_file(self.note['id'], 'legitimate.txt#yx-item='+target['id'])

    def test_external_target_and_external_note_are_rejected(self):
        target = self.register(self.root/'external.txt', external=True)
        with self.assertRaises(UserError): self.assets.file_link(self.note['id'], target['id'])
        with self.assertRaises(UserError): self.assets.resolve_file(self.note['id'], 'safe.txt#yx-item='+target['id'])
        note = self.register(self.root/'external.md', external=True)
        with self.assertRaises(UserError): self.assets.file_link(note['id'], self.target['id'])

    def test_recycled_target_and_note_are_rejected(self):
        destination = self.destination(); self.org.delete_items([self.target['id']])
        with self.assertRaises(UserError): self.assets.resolve_file(self.note['id'], destination)
        with self.assertRaises(UserError): self.assets.file_link(self.note['id'], self.target['id'])
        self.org.delete_items([self.note['id']])
        with self.assertRaises(UserError): self.assets.resolve_file(self.note['id'], destination)

    def test_hardlinks_are_checked_on_every_resolution(self):
        destination = self.destination(); os.link(self.target['path'], self.root/'alias.txt')
        with self.assertRaises(UserError): self.assets.resolve_file(self.note['id'], destination)
        with self.assertRaises(UserError): self.assets.file_link(self.note['id'], self.target['id'])

    def test_hardlinked_note_cannot_authorize_file_links(self):
        os.link(self.note['path'], self.root/'note-alias.md')
        with self.assertRaises(UserError): self.assets.file_link(self.note['id'], self.target['id'])

    def test_invalid_or_removed_fragment_never_falls_back_to_real_relative_target(self):
        path = self.destination().split('#')[0]
        for fragment in ['bad', 'yx-item='+'f'*32, 'yx-item='+self.target['id']+'&extra=1', 'yx-item='+self.target['id'].upper()]:
            with self.subTest(fragment=fragment), self.assertRaises(UserError): self.assets.resolve_file(self.note['id'], path+'#'+fragment)

    def test_protocols_traversal_queries_encoding_and_directories_rejected(self):
        suffix = '#yx-item='+self.target['id']
        for path in ['https://evil.test/x','//server/x','/absolute','C:/x',r'..\x','javascript:alert(1)',
                     '../../../outside.txt','%2fabsolute','%5cserver','x%00.txt','x\n.txt','x?query=1','%GG','%ff']:
            with self.subTest(path=path), self.assertRaises(UserError): self.assets.resolve_file(self.note['id'], path+suffix)
        with self.assertRaises(UserError): self.assets.resolve_file(self.note['id'], '../')


if __name__ == '__main__': unittest.main()
