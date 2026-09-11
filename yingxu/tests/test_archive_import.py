import io
import json
from pathlib import Path
import stat
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.request
import urllib.error
import zipfile

from server import Application, Server
from yingxu.archive_import import import_zip
from yingxu.store import UserError


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='yingxu-zip-test-');self.root=Path(self.tmp.name).resolve()
        with patch('yingxu.skills.Path.home',return_value=self.root/'home'):
            self.app=Application(self.root/'data',self.root/'projects')
        self.pid=self.app.store.create_project('压缩包合成项目')['id']

    def tearDown(self):
        self.app.jobs.pool.shutdown(wait=True);self.app.thumbnails.pool.shutdown(wait=True);self.app.context.close();self.tmp.cleanup()

    def make_zip(self,entries,name='中文素材.zip',compression=zipfile.ZIP_DEFLATED):
        path=self.root/name
        with zipfile.ZipFile(path,'w',compression=compression) as z:
            for key,value in entries:z.writestr(key,value)
        return path

    def counts(self):
        with self.app.store.connection() as db:
            return tuple(db.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in ('items','folders'))

    def wait(self,result):
        for _ in range(200):
            job=self.app.jobs.get(result['job_id'])
            if job['state'] in ('done','error'):return job
            time.sleep(.01)
        self.fail('ZIP job timed out')

    def test_tree_target_empty_folders_duplicates_and_source_preserved(self):
        folder=self.app.organize.create_folder(self.pid,'scripts','选中目录')
        path=self.make_zip([('第一集/原稿.md','中文原稿'),('第一集/空目录/',''),('参考.png',b'image'),('工具.exe',b'not executed'),('__MACOSX/._note.md','metadata')])
        before=path.read_bytes()
        first=import_zip(self.app.store,path,self.pid,'scripts',folder['id'])
        second=import_zip(self.app.store,path,self.pid,'scripts',folder['id'])
        self.assertEqual((first['done'],first['skipped']),(2,2))
        a=Path(self.app.organize.get_folder(first['folder_id'])['path']);b=Path(self.app.organize.get_folder(second['folder_id'])['path'])
        self.assertEqual(a.parent,Path(folder['path']));self.assertNotEqual(a,b)
        self.assertTrue((a/'第一集/空目录').is_dir());self.assertEqual((a/'第一集/原稿.md').read_text(encoding='utf-8'),'中文原稿')
        self.assertFalse((a/'工具.exe').exists());self.assertEqual(path.read_bytes(),before)
        with self.app.store.connection() as db:
            row=db.execute('SELECT category,folder_id FROM items WHERE path=?',(str(a/'第一集/原稿.md'),)).fetchone()
        self.assertEqual(row['category'],'scripts');self.assertEqual(Path(self.app.organize.get_folder(row['folder_id'])['path']),a/'第一集')

    def test_legacy_chinese_names_are_decoded(self):
        class LegacyInfo(zipfile.ZipInfo):
            def _encodeFilenameFlags(self):
                return self.filename.encode('gb18030'), self.flag_bits & ~0x800
        path=self.make_zip([(LegacyInfo('第一集/中文.md'),'legacy')])
        result=import_zip(self.app.store,path,self.pid,'scripts')
        destination=Path(self.app.organize.get_folder(result['folder_id'])['path'])
        self.assertEqual((destination/'第一集/中文.md').read_text(),'legacy')

    def test_unsafe_paths_and_portable_collisions_publish_nothing(self):
        for names in [['../escape.md'],['/escape.md'],['C:/escape.md'],['a/../../x.md'],['safe.md','SAFE.md'],['a','a/x.md'],['A/x.md','a/y.md'],['dir./x.md'],['CON.md']]:
            with self.subTest(names=names):
                before=self.counts();path=self.make_zip([(name,'x') for name in names])
                with self.assertRaises(UserError):import_zip(self.app.store,path,self.pid,'scripts')
                self.assertEqual(before,self.counts())
        self.assertFalse((self.root/'escape.md').exists())

    def test_links_encrypted_and_unsupported_compression_rejected(self):
        link=zipfile.ZipInfo('link.md');link.create_system=3;link.external_attr=(stat.S_IFLNK|0o777)<<16
        path=self.make_zip([(link,'target')])
        with self.assertRaises(UserError):import_zip(self.app.store,path,self.pid,'scripts')
        path=self.make_zip([('note.md','hi')],compression=zipfile.ZIP_BZIP2)
        with self.assertRaises(UserError):import_zip(self.app.store,path,self.pid,'scripts')
        path=self.make_zip([('note.md','hi')]);data=bytearray(path.read_bytes())
        # Traditional encryption flag in both headers; no password is ever requested/read.
        data[6]|=1;central=data.index(b'PK\x01\x02');data[central+8]|=1;path.write_bytes(data)
        with self.assertRaises(UserError):import_zip(self.app.store,path,self.pid,'scripts')
        self.assertEqual(self.counts(),(0,0))

    def test_corrupt_crc_and_limits_leave_no_partial_files(self):
        path=self.make_zip([('note.md',b'UNIQUE_PAYLOAD')],compression=zipfile.ZIP_STORED)
        data=path.read_bytes().replace(b'UNIQUE_PAYLOAD',b'BROKEN_PAYLOAD');path.write_bytes(data)
        with self.assertRaises(UserError):import_zip(self.app.store,path,self.pid,'scripts')
        path=self.make_zip([('a.md','a'),('b.md','b')])
        with patch('yingxu.archive_import.MAX_ENTRIES',1),self.assertRaises(UserError):import_zip(self.app.store,path,self.pid,'scripts')
        with patch('yingxu.archive_import.MAX_EXPANDED',1),self.assertRaises(UserError):import_zip(self.app.store,path,self.pid,'scripts')
        self.assertEqual(self.counts(),(0,0))
        self.assertFalse(list(Path(self.app.store.get_project(self.pid)['root']).rglob('.yingxu-archive-*')))

    def test_changed_destination_and_missing_archive_do_not_publish(self):
        path=self.make_zip([('a.md','one')]);folder=self.app.organize.create_folder(self.pid,'scripts','目标')
        def change(_):
            if Path(folder['path']).exists():self.app.organize.rename_folder(folder['id'],'已改名')
        with self.assertRaises(UserError):import_zip(self.app.store,path,self.pid,'scripts',folder['id'],progress=change)
        self.assertEqual(self.counts()[0],0)
        self.assertFalse(list(Path(self.app.store.get_project(self.pid)['root']).rglob('.yingxu-archive-*')))
        with self.assertRaises(UserError):self.app.jobs.submit_archive(self.pid,'scripts',self.root/'missing.zip')

    def test_local_selection_and_clipboard_import_zip_without_registering_archive(self):
        path=self.make_zip([('nested/note.md','text')])
        job=self.wait(self.app.jobs.submit(self.pid,'unclassified',[str(path)],None))
        self.assertEqual(job['done'],1);self.assertEqual(job['errors'],[])
        with patch('yingxu.clipboard_files.read_files',return_value=[str(path)]):result=self.app.paste_clipboard({'project_id':self.pid,'category':'scripts'})
        self.assertEqual(result['items'],[]);self.assertEqual(len(result['job_ids']),1)
        self.assertEqual(self.wait({'job_id':result['job_ids'][0]})['done'],1)
        self.assertFalse(any(s['path']==str(path) for s in self.app.store.sources(self.pid)))

    def test_upload_job_cleans_owned_zip_and_preserves_target(self):
        path=self.make_zip([('nested/note.md','text')]);body=path.read_bytes()
        from types import SimpleNamespace
        result=self.app.receive_upload(SimpleNamespace(headers={'Content-Length':str(len(body))},rfile=io.BytesIO(body)),{'project':self.pid,'category':'scripts','name':'上传.zip'})
        self.assertEqual(self.wait(result)['done'],1)
        self.assertEqual(list((self.app.store.data_root/'archive-uploads').glob('*.zip')),[])
        self.assertEqual(path.read_bytes(),body)

    def test_http_upload_requires_same_origin_token_and_imports_zip(self):
        service=Server(('127.0.0.1',0),self.app);thread=threading.Thread(target=service.serve_forever,daemon=True);thread.start()
        origin=f'http://127.0.0.1:{service.server_port}'
        path=self.make_zip([('note.md','http')]);body=path.read_bytes()
        url=origin+'/api/upload?project='+self.pid+'&category=scripts&name=test.zip'
        try:
            for headers in [{},{'Origin':'https://example.com','X-YingXu-Token':self.app.token}]:
                with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(urllib.request.Request(url,data=body,headers=headers))
            self.assertEqual(self.counts(),(0,0))
            result=json.load(urllib.request.urlopen(urllib.request.Request(url,data=body,headers={'Origin':origin,'X-YingXu-Token':self.app.token})))
            self.assertEqual(self.wait(result)['done'],1)
        finally:service.shutdown();service.server_close();thread.join()
