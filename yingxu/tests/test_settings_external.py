import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from yingxu.settings import DEFAULTS, Settings
from yingxu.external import ExternalPreviews
from yingxu.store import UserError


class SettingsExternalTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='yingxu-preferences-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name).resolve(); self.data=self.root/'data'; self.data.mkdir()
        self.settings=Settings(self.data); self.external=ExternalPreviews(self.data)

    def file(self,name='test.md',content=b'synthetic text'):
        path=self.root/name; path.write_bytes(content); return path

    def test_defaults_do_not_write_and_settings_persist_with_strict_types(self):
        self.assertEqual(self.settings.get(),DEFAULTS); self.assertEqual(list(self.data.iterdir()),[])
        values=self.settings.update({'close_to_tray':False,'default_view':'board','default_sort':'order','autoplay_media':True})
        self.assertEqual(Settings(self.data).get(),values)
        original=self.settings.path.read_bytes()
        for value in ({'confirm_delete':1},{'default_view':'bad'},{'default_sort':None},{'unknown':True}):
            with self.assertRaises(UserError): self.settings.update(value)
        self.assertEqual(self.settings.path.read_bytes(),original)

    def test_failed_atomic_replace_preserves_existing_settings(self):
        self.settings.update({'confirm_delete':False}); original=self.settings.path.read_bytes()
        with patch('yingxu.settings.os.replace',side_effect=OSError('synthetic error')):
            with self.assertRaises(OSError): self.settings.update({'close_to_tray':False})
        self.assertEqual(self.settings.path.read_bytes(),original)
        self.assertEqual(list(self.data.glob('*.tmp')),[])

    def test_capture_mode_defaults_to_annotate_and_persists_only_known_modes(self):
        self.assertEqual(self.settings.get()['capture_mode'],'annotate')
        self.settings.update({'capture_mode':'quick'})
        self.assertEqual(Settings(self.data).get()['capture_mode'],'quick')
        self.settings.update({'capture_mode':'annotate'})
        self.assertEqual(Settings(self.data).get()['capture_mode'],'annotate')
        before=self.settings.path.read_bytes()
        for invalid in ('', 'silent', None, True, 1, ['quick']):
            with self.subTest(mode=invalid),self.assertRaises(UserError):self.settings.update({'capture_mode':invalid})
        self.assertEqual(self.settings.path.read_bytes(),before)

    def test_corrupt_or_shared_settings_are_not_overwritten(self):
        self.settings.path.write_text('{broken',encoding='utf-8')
        with self.assertRaises(UserError): self.settings.update({'close_to_tray':False})
        self.assertEqual(self.settings.path.read_text(),'{broken')
        self.settings.path.write_text('{}',encoding='utf-8'); os.link(self.settings.path,self.root/'linked-settings.json')
        with self.assertRaises(UserError): self.settings.get()

    def test_external_text_is_editable_and_opening_has_no_persistence_or_copies(self):
        path=self.file('外部正文.md','测试原文'.encode()); original=path.read_bytes()
        entry=self.external.open({'paths':[str(path),str(path)]})['entries'][0]
        detail=self.external.detail(entry['id'])
        self.assertEqual(detail['content']['content'],'测试原文')
        self.assertTrue(detail['content']['editable']); self.assertTrue(detail['external'])
        self.assertTrue(detail['editable']); self.assertEqual(len(detail['content']['etag']),64)
        self.assertEqual(path.read_bytes(),original); self.assertEqual(list(self.data.iterdir()),[])
        with self.assertRaises(UserError): ExternalPreviews(self.data).detail(entry['id'])

    def test_batch_validation_rejects_unknown_directory_and_app_data_without_partial_registration(self):
        valid=self.file(); unsupported=self.file('script.exe',b'not executable')
        for other in (unsupported,self.root,self.data/'settings.json'):
            if other==self.data/'settings.json': other.write_text('{}',encoding='utf-8')
            with self.assertRaises(UserError): self.external.open({'paths':[str(valid),str(other)]})
            self.assertEqual(self.external.entries,{})
        for body in ({'paths':['relative.md']},{'paths':[]},{'paths':[str(valid)],'unexpected':True}):
            with self.assertRaises(UserError): self.external.open(body)

    def test_replaced_file_identity_is_rejected_without_serving_new_bytes(self):
        path=self.file(); entry=self.external.open({'paths':[str(path)]})['entries'][0]
        replacement=self.file('replacement.md',b'different file'); os.replace(replacement,path)
        with self.assertRaises(UserError): self.external.detail(entry['id'])
        with self.assertRaises(UserError):
            with self.external.open_media(entry['id']): self.fail('must not serve replacement')

    def test_late_reparse_replacement_is_rejected(self):
        path=self.file(); entry=self.external.open({'paths':[str(path)]})['entries'][0]
        with patch('yingxu.store.has_link',side_effect=lambda value: Path(value)==path):
            with self.assertRaises(UserError): self.external.resolve(entry['id'])

    def test_data_hardlink_outside_data_root_cannot_bypass_preview_boundary(self):
        private=self.data/'settings.json'; private.write_text('{"synthetic":"private"}',encoding='utf-8')
        link=self.root/'apparently-external.json'; os.link(private,link)
        with self.assertRaises(UserError): self.external.open({'paths':[str(link)]})
        self.assertEqual(self.external.entries,{})

    def test_hardlink_created_between_path_check_and_open_is_rejected_by_handle(self):
        path=self.file(); entry=self.external.open({'paths':[str(path)]})['entries'][0]
        original=Path.open; alias=self.root/'late-shared.md'
        def race(target,*args,**kwargs):
            if target==path and not alias.exists(): os.link(path,alias)
            return original(target,*args,**kwargs)
        with patch.object(Path,'open',race),self.assertRaises(UserError):
            with self.external.open_media(entry['id']): self.fail('shared file must not be served')

    def test_docx_simple_paragraphs_are_editable_with_etag(self):
        path=self.root/'test.docx'
        with zipfile.ZipFile(path,'w') as package:
            package.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
            package.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Synthetic Word</w:t></w:r></w:p></w:body></w:document>')
        entry=self.external.open({'paths':[str(path)]})['entries'][0]
        with patch('yingxu.docx_io._open_path',side_effect=AssertionError('must use verified open handle')):
            detail=self.external.detail(entry['id'])
        self.assertIn('Synthetic Word',detail['content']['content'])
        self.assertTrue(detail['content']['editable'])
        self.assertTrue(all(paragraph['editable'] for paragraph in detail['content']['paragraphs']))
        self.assertEqual(len(detail['content']['etag']),64)

    def test_large_text_is_bounded_and_binary_media_does_not_read_body_for_metadata(self):
        path=self.file('huge.txt',b'x'*(2*1024*1024+1)); entry=self.external.open({'paths':[str(path)]})['entries'][0]
        with self.assertRaises(UserError): self.external.detail(entry['id'])
        media=self.file('video.mp4',b'0123456789'); entry=self.external.open({'paths':[str(media)]})['entries'][0]
        with patch.object(Path,'read_bytes',side_effect=AssertionError('no metadata content read')):
            self.assertEqual(self.external.detail(entry['id'])['kind'],'video')
        with self.external.open_media(entry['id']) as handle:
            handle.seek(3); self.assertEqual(handle.read(3),b'345')


if __name__=='__main__': unittest.main()
