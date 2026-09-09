"""Deterministic, temporary-fixture regressions for deletion/import races."""
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from server import Application
from yingxu.context import ContextExporter
from yingxu.jobs import Jobs
from yingxu.organize import Organize
from yingxu.store import Store,UserError


class IntegrationReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        self.store=Store(self.base/'data',self.base/'projects')
        self.project=self.store.create_project('上传导入竞态测试')
        self.org=Organize(self.store)
        self.folder=self.org.create_folder(self.project['id'],'scripts','第01集')
        self.app=SimpleNamespace(store=self.store,organize=self.org,context=SimpleNamespace(request=lambda pid:None))

    def upload(self,on_read):
        class Stream(BytesIO):
            def read(self,n=-1):
                result=super().read(n)
                if result:on_read()
                return result
        handler=SimpleNamespace(headers={'Content-Length':'4'},rfile=Stream(b'test'))
        return Application.receive_upload(self.app,handler,{'project':self.project['id'],'category':'scripts',
            'folder_id':self.folder['id'],'name':'upload.md'})

    def assert_upload_absent(self):
        files=[p for p in Path(self.project['root']).rglob('*') if p.is_file()]
        self.assertFalse(any(p.name=='upload.md' or p.name.startswith('.yingxu-upload-') for p in files),files)
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM items WHERE name=?',('upload',)).fetchone()[0],0)

    def test_folder_deleted_during_upload_prevents_publication(self):
        with self.assertRaises(UserError):self.upload(lambda:self.org.delete_folder(self.folder['id']))
        self.assert_upload_absent()

    def test_project_deleted_during_upload_prevents_publication(self):
        with self.assertRaises(UserError):self.upload(lambda:self.org.delete_project(self.project['id']))
        self.assert_upload_absent()

    def test_closed_upload_temp_also_blocks_directory_rename(self):
        # Closed temporary file models the small interval before final publication.
        temporary=Path(self.folder['path'])/'.yingxu-upload-synthetic.tmp'
        temporary.write_bytes(b'synthetic uncommitted upload')
        with self.assertRaises(UserError) as error:self.org.rename_folder(self.folder['id'],'改名')
        self.assertEqual(error.exception.status,409)
        self.assertEqual(temporary.read_bytes(),b'synthetic uncommitted upload')
        self.assertTrue(Path(self.folder['path']).is_dir())

    def test_midstream_rename_is_a_clear_conflict_and_upload_can_finish(self):
        conflicts=[]
        def rename_attempt():
            try:self.org.rename_folder(self.folder['id'],'稍后改名')
            except UserError as error:conflicts.append(error.status)
        uploaded=self.upload(rename_attempt)
        self.assertEqual(conflicts,[409])
        self.assertEqual(Path(uploaded['path']).read_bytes(),b'test')
        renamed=self.org.rename_folder(self.folder['id'],'稍后改名')
        self.assertEqual(Path(self.store.get_item(uploaded['id'])['path']).parent,Path(renamed['path']))

    def jobs(self):
        jobs=Jobs(self.store);self.addCleanup(jobs.pool.shutdown,wait=True);return jobs

    def finish(self,jobs,result):
        jobs.pool.submit(lambda:None).result(timeout=10)
        return jobs.get(result['job_id'])

    def test_deleted_external_import_destination_does_not_leak_items_into_root(self):
        external=self.base/'reference.md';external.write_text('外部原文',encoding='utf-8')
        original=self.store.inspect_file
        def delete_after_parse(path):
            parsed=original(path);self.org.delete_folder(self.folder['id']);return parsed
        jobs=self.jobs()
        with patch.object(self.store,'inspect_file',side_effect=delete_after_parse):
            result=self.finish(jobs,jobs.submit(self.project['id'],'scripts',[str(external)],self.folder['id']))
        self.assertEqual(result['done'],0)
        self.assertTrue(result['errors'])
        self.assertEqual(self.store.list_items(self.project['id'])['total'],0)
        self.assertEqual(external.read_text(encoding='utf-8'),'外部原文')

    def test_unchanged_reference_assignment_is_atomic_without_reparsing_and_rescan_keeps_it(self):
        external=self.base/'unchanged.md';external.write_text('保持原位的雨夜剧本。',encoding='utf-8')
        source=self.store.register_source(self.project['id'],external,'references');self.store.index_files(source,[external])
        original_path=str(external);jobs=self.jobs()
        with patch.object(self.store,'inspect_file',side_effect=AssertionError('Unchanged files must not be reparsed')):
            state=self.finish(jobs,jobs.submit(self.project['id'],'scripts',[str(external)],self.folder['id']))
            self.assertFalse(state['errors'])
        first=self.store.list_items(self.project['id'],folder=self.folder['id'])['items'][0]
        self.assertEqual(first['path'],original_path);self.assertEqual(first['category'],'scripts')
        state=self.finish(jobs,jobs.submit(self.project['id']));self.assertFalse(state['errors'])
        self.assertEqual(self.store.get_item(first['id'])['folder_id'],self.folder['id'])
        with patch.object(self.store,'inspect_file',side_effect=AssertionError('Explicit root assignment needs no parse')):
            state=self.finish(jobs,jobs.submit(self.project['id'],'scripts',[str(external)],None))
            self.assertFalse(state['errors'])
        current=self.store.get_item(first['id']);self.assertIsNone(current['folder_id'])
        self.assertEqual(current['path'],original_path)
        self.assertEqual(self.store.list_items(self.project['id'],q='雨夜')['total'],1)

    def test_delayed_archive_after_restore_keeps_active_snapshot_and_dirty_marker(self):
        with patch('yingxu.context.DEBOUNCE_SECONDS',3600),patch('yingxu.context.MAX_DEBOUNCE_SECONDS',3600):
            context=ContextExporter(self.store)
            try:
                context.export(self.project['id'])
                batch=self.org.delete_project(self.project['id'])
                self.org.restore(batch['id']);context.request(self.project['id'])
                # The original delete HTTP request resumes after an immediate undo.
                context.archive(self.project)
                progress=json.loads((Path(self.project['root'])/'.yingxu'/'progress.json').read_text(encoding='utf-8'))
                self.assertFalse(progress.get('archived',False))
                with self.store.connection() as db:
                    row=db.execute('SELECT revision,exported_revision FROM context_exports WHERE project_id=?',(self.project['id'],)).fetchone()
                self.assertIsNotNone(row,'A delayed archive must not erase the restore export request.')
                self.assertGreater(row['revision'],row['exported_revision'])
            finally:context.close()


if __name__=='__main__':unittest.main()
