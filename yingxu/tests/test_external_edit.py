import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from yingxu.external import ExternalPreviews
from yingxu.store import TEXT_LIMIT, UserError


class ExternalEditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='yingxu-external-edit-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.data = self.root / 'data'
        self.data.mkdir()
        self.external = ExternalPreviews(self.data)

    def document(self, raw=b'original\n', name='note.md'):
        path = self.root / name
        path.write_bytes(raw)
        entry = self.external.open({'paths': [str(path)]})['entries'][0]
        return path, entry['id'], self.external.detail(entry['id'])['content']['etag']

    def test_edit_original_with_private_backup_and_reusable_capability(self):
        before = '\u539f\u6587\n'.encode()
        path, iid, etag = self.document(before)
        result = self.external.save(iid, {'etag': etag, 'content': '\u65b0\u6587\n'})
        self.assertEqual(path.read_bytes(), '\u65b0\u6587\n'.encode())
        self.assertEqual(result['path'], str(path))
        self.assertTrue(result['content']['editable'])
        self.assertEqual(result['content']['etag'], hashlib.sha256(path.read_bytes()).hexdigest())
        backups = list((self.data / 'external-versions').glob('*/*.md'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), before)
        metadata = json.loads(backups[0].with_suffix('.metadata.json').read_text(encoding='utf-8'))
        self.assertEqual(metadata['path'], str(path))
        self.assertEqual(metadata['sha256'], etag)
        self.external.save(iid, {'etag': result['content']['etag'], 'content': 'third'})
        self.assertEqual(path.read_bytes(), b'third')
        self.assertFalse(list(self.root.glob('*.tmp')))
        self.assertFalse(list(self.data.glob('*.sqlite3')))

    def test_repeated_open_reuses_explicit_live_id(self):
        path, iid, etag = self.document()
        second = self.external.open({'paths': [str(path)]})['entries'][0]
        self.assertEqual(second['id'], iid)
        self.assertEqual(len(self.external.entries), 1)

    def test_json_backup_payload_does_not_collide_with_backup_metadata(self):
        path, iid, etag = self.document(b'{"old": true}', name='notes.json')
        self.external.save(iid, {'etag': etag, 'content': '{"new": true}'})
        self.assertEqual(path.read_bytes(), b'{"new": true}')
        self.assertEqual(len(list(self.data.glob('external-versions/*/*.metadata.json'))), 1)

    def test_bom_encoding_and_uniform_line_endings_preserved(self):
        cases = [
            (b'a\r\nb\r\n', 'c\nd\n', b'c\r\nd\r\n'),
            (b'\xef\xbb\xbfa\n', 'c\n', b'\xef\xbb\xbfc\n'),
            (b'a\rb\r', 'c\nd\n', b'c\rd\r'),
            (b'\xff\xfe' + 'a\r\n'.encode('utf-16-le'), 'c\n', b'\xff\xfe' + 'c\r\n'.encode('utf-16-le')),
            (b'\xfe\xff' + 'a\n'.encode('utf-16-be'), 'c\n', b'\xfe\xff' + 'c\n'.encode('utf-16-be')),
            ('\u539f\u6587\n'.encode('gb18030'), '\u65b0\u6587\n', '\u65b0\u6587\n'.encode('gb18030')),
            (b'a\r\nb\nc', 'c\r\nd\ne', b'c\r\nd\ne'),
        ]
        for index, (before, text, expected) in enumerate(cases):
            with self.subTest(index=index):
                path, iid, etag = self.document(before, str(index) + '.md')
                self.external.save(iid, {'etag': etag, 'content': text})
                self.assertEqual(path.read_bytes(), expected)

    def test_noop_does_not_replace_or_backup(self):
        path, iid, etag = self.document(b'a\r\n')
        before = path.stat()
        self.external.save(iid, {'etag': etag, 'content': 'a\n'})
        self.assertEqual((path.stat().st_ino, path.stat().st_mtime_ns), (before.st_ino, before.st_mtime_ns))
        self.assertEqual(list(self.data.iterdir()), [])

    def test_external_change_conflict_preserves_new_file(self):
        path, iid, etag = self.document()
        path.write_bytes(b'external change')
        with self.assertRaises(UserError) as caught:
            self.external.save(iid, {'etag': etag, 'content': 'draft'})
        self.assertEqual(caught.exception.status, 409)
        self.assertEqual(path.read_bytes(), b'external change')
        self.assertEqual(list(self.data.iterdir()), [])

    def test_replaced_identity_and_added_hardlink_refuse_save(self):
        path, iid, etag = self.document()
        replacement = self.root / 'replacement.md'
        replacement.write_bytes(path.read_bytes())
        os.replace(replacement, path)
        with self.assertRaises(UserError):
            self.external.save(iid, {'etag': etag, 'content': 'draft'})
        iid = self.external.open({'paths': [str(path)]})['entries'][0]['id']
        os.link(path, self.root / 'alias.md')
        with self.assertRaises(UserError):
            self.external.save(iid, {'etag': etag, 'content': 'draft'})
        self.assertEqual(path.read_bytes(), b'original\n')

    def test_late_change_rechecked_before_replace(self):
        path, iid, etag = self.document()
        original = self.external._read
        calls = 0
        def read(*args):
            nonlocal calls
            calls += 1
            if calls == 2:
                path.write_bytes(b'late external change')
            return original(*args)
        with patch.object(self.external, '_read', side_effect=read), self.assertRaises(UserError):
            self.external.save(iid, {'etag': etag, 'content': 'draft'})
        self.assertEqual(path.read_bytes(), b'late external change')
        self.assertEqual(list(self.root.glob('*.tmp')), [])

    def test_failed_replace_keeps_original_backup_and_cleans_temp(self):
        path, iid, etag = self.document()
        with patch('yingxu.external.os.replace', side_effect=PermissionError('busy')), self.assertRaises(UserError):
            self.external.save(iid, {'etag': etag, 'content': 'draft'})
        self.assertEqual(path.read_bytes(), b'original\n')
        self.assertEqual(len(list(self.data.glob('external-versions/*/*.md'))), 1)
        self.assertEqual(list(self.root.glob('*.tmp')), [])

    def test_failed_backup_never_replaces_original(self):
        path, iid, etag = self.document()
        original = Path.open
        def opened(target, *args, **kwargs):
            if 'external-versions' in target.parts and args and args[0] == 'xb':
                raise PermissionError('backup not writable')
            return original(target, *args, **kwargs)
        with patch.object(Path, 'open', opened), self.assertRaises(UserError):
            self.external.save(iid, {'etag': etag, 'content': 'draft'})
        self.assertEqual(path.read_bytes(), b'original\n')

    def test_unknown_expired_capability_and_extra_path_are_rejected(self):
        path, iid, etag = self.document()
        with self.assertRaises(UserError):
            self.external.save('a' * 32, {'etag': etag, 'content': 'draft'})
        with self.assertRaises(UserError):
            self.external.save(iid, {'etag': etag, 'content': 'draft', 'path': str(path)})
        self.external.entries[iid]['expires'] = 0
        with self.assertRaises(UserError):
            self.external.save(iid, {'etag': etag, 'content': 'draft'})
        self.assertEqual(path.read_bytes(), b'original\n')

    def test_oversized_draft_bad_content_and_invalid_etag_rejected(self):
        path, iid, etag = self.document()
        for body in ({'etag': etag, 'content': 'a' * (TEXT_LIMIT + 1)},
                     {'etag': etag, 'content': None}, {'etag': '', 'content': 'draft'},
                     {'etag': etag, 'content': '\ud800'}):
            with self.subTest(body_type=type(body.get('content'))), self.assertRaises(UserError):
                self.external.save(iid, body)
        self.assertEqual(path.read_bytes(), b'original\n')

    def test_readonly_file_does_not_advertise_editing_or_allow_save(self):
        path, iid, etag = self.document()
        path.chmod(0o444)
        self.addCleanup(path.chmod, 0o666)
        self.assertFalse(self.external.detail(iid)['content']['editable'])
        with self.assertRaises(UserError):
            self.external.save(iid, {'etag': etag, 'content': 'draft'})
        self.assertEqual(path.read_bytes(), b'original\n')

    def test_media_cannot_be_edited(self):
        path = self.root / 'movie.mp4'
        path.write_bytes(b'fake')
        iid = self.external.open({'paths': [str(path)]})['entries'][0]['id']
        with self.assertRaises(UserError):
            self.external.save(iid, {'etag': hashlib.sha256(b'fake').hexdigest(), 'content': 'draft'})
        self.assertEqual(path.read_bytes(), b'fake')

    def test_external_word_save_uses_captured_bytes_and_preserves_other_members(self):
        path = self.root / 'document.docx'
        with zipfile.ZipFile(path, 'w') as package:
            package.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
            package.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>original</w:t></w:r></w:p></w:body></w:document>')
            package.writestr('customXml/item1.xml', '<synthetic>untouched</synthetic>')
        before = path.read_bytes()
        iid = self.external.open({'paths': [str(path)]})['entries'][0]['id']
        detail = self.external.detail(iid)
        with patch('yingxu.docx_io._open_path', side_effect=AssertionError('must use captured bytes')):
            result = self.external.save(iid, {'etag': detail['content']['etag'],
                'paragraphs': [{'id': detail['content']['paragraphs'][0]['id'], 'text': 'new text'}]})
        self.assertEqual(result['content']['paragraphs'][0]['text'], 'new text')
        with zipfile.ZipFile(path) as package:
            self.assertEqual(package.read('customXml/item1.xml'), b'<synthetic>untouched</synthetic>')
        self.assertEqual(next(self.data.glob('external-versions/*/*.docx')).read_bytes(), before)

    def test_late_link_and_redirected_backup_refuse_write(self):
        path, iid, etag = self.document()
        original = self.external._read
        calls = 0
        def read(*args):
            nonlocal calls
            calls += 1
            if calls == 2:
                os.link(path, self.root / 'late-alias.md')
            return original(*args)
        with patch.object(self.external, '_read', side_effect=read), self.assertRaises(UserError):
            self.external.save(iid, {'etag': etag, 'content': 'draft'})
        self.assertEqual(path.read_bytes(), b'original\n')
        second, second_id, second_etag = self.document(name='second.md')
        with patch('yingxu.external.has_link', side_effect=lambda path: path == self.data), self.assertRaises(UserError):
            self.external.save(second_id, {'etag': second_etag, 'content': 'draft'})
        self.assertEqual(second.read_bytes(), b'original\n')


if __name__ == '__main__':
    unittest.main()
