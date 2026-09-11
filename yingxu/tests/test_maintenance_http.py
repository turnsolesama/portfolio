"""Maintenance HTTP authorization and preview binding on temporary data only."""
import hashlib
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from server import Application, Server


class MaintenanceHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='yingxu-maintenance-http-')
        self.root=Path(self.temp.name).resolve()
        with patch('yingxu.skills.Path.home',return_value=self.root/'empty-home'):
            self.app=Application(self.root/'data',self.root/'projects')
        self.server=Server(('127.0.0.1',0),self.app)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.project=self.app.store.create_project('容量维护合成项目')
        self.note=self.app.store.create_item({'project_id':self.project['id'],'category':'scripts','name':'原稿','content':'原稿正文'})
        self.original=Path(self.note['path']).read_bytes()
        self.cache=self.app.store.data_root/'thumbnails'/('a'*64+'.jpg')
        self.cache.write_bytes(b'synthetic cached preview')
        self.unknown=self.cache.with_name('unrecognized.jpg');self.unknown.write_bytes(b'keep unknown')

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=5)
        self.app.jobs.pool.shutdown(wait=True);self.app.thumbnails.pool.shutdown(wait=True);self.app.context.close()
        self.assertFalse(self.thread.is_alive())
        self.temp.cleanup()

    def request(self,route,data=None,method='POST',headers=None):
        hdr={'Origin':f'http://127.0.0.1:{self.server.server_port}','X-YingXu-Token':self.app.token,
             'Content-Type':'application/json'}
        for key,value in (headers or {}).items():
            if value is None:hdr.pop(key,None)
            else:hdr[key]=value
        client=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=10)
        try:
            body=None if method in ('GET','HEAD') else json.dumps(data or {}).encode()
            client.request(method,'/api/maintenance/'+route,body=body,headers=hdr)
            response=client.getresponse();return response.status,json.loads(response.read())
        finally:client.close()

    def assert_original(self):
        self.assertEqual(Path(self.note['path']).read_bytes(),self.original)
        self.assertEqual(self.unknown.read_bytes(),b'keep unknown')
        self.assertTrue(self.app.store.db_path.exists())
        self.assertEqual(self.app.store.get_item(self.note['id'])['name'],'原稿')

    def test_foreign_origin_token_host_and_cross_site_reject_before_preview_or_cleanup(self):
        for route in ('preview','cleanup'):
            for headers in ({'Origin':'https://foreign.invalid'},{'X-YingXu-Token':'wrong'},
                            {'X-YingXu-Token':None},{'Host':'localhost'}, {'Sec-Fetch-Site':'cross-site'}):
                with self.subTest(route=route,headers=headers):
                    self.assertEqual(self.request(route,{},headers=headers)[0],403)
                    self.assertTrue(self.cache.exists());self.assert_original()
        self.assertEqual(len(self.app.maintenance.tokens),0)

    def test_contract_preview_does_not_delete_and_cleanup_is_bound_one_time(self):
        status,preview=self.request('preview',{})
        self.assertEqual(status,200,preview);self.assertTrue(self.cache.exists())
        for field in ('token','expires_in','groups','total_bytes','reclaimable_bytes','reclaimable_files','truncated','warnings'):
            self.assertIn(field,preview)
        self.assertIsInstance(preview['groups'],list)
        self.assertTrue(all({'key','label','bytes','files','reclaimable_bytes','reclaimable_files'}<=set(g) for g in preview['groups']))
        self.assertNotIn(str(self.root),json.dumps(preview))
        self.assertEqual(preview['reclaimable_files'],1)
        # Wrong session token must not consume the separately bound preview.
        body={'token':preview['token']}
        self.assertEqual(self.request('cleanup',body,headers={'X-YingXu-Token':'wrong'})[0],403)
        status,cleaned=self.request('cleanup',body)
        self.assertEqual(status,200,cleaned)
        self.assertEqual(cleaned['removed_files'],1)
        self.assertEqual(cleaned['removed_bytes'],len(b'synthetic cached preview'))
        self.assertEqual(cleaned['skipped_files'],0);self.assertEqual(cleaned['warnings'],[])
        self.assertFalse(self.cache.exists());self.assert_original()
        self.assertEqual(self.request('cleanup',body)[0],409)

    def test_history_opt_in_preserves_original_and_latest_recovery_point(self):
        for text in ('第一次编辑','第二次编辑'):
            current=self.app.store.read_content(self.note['id'])
            self.app.store.save_content(self.note['id'],{'content':text,'etag':current['etag']})
        self.original=Path(self.note['path']).read_bytes()
        version_dir=self.app.store.data_root/'versions'/self.note['id']
        snapshots=sorted(version_dir.iterdir(),key=lambda p:p.stat().st_mtime_ns)
        self.assertEqual(len(snapshots),2)
        latest=snapshots[-1];digest=hashlib.sha256(latest.read_bytes()).hexdigest()
        self.assertEqual(self.request('preview',{})[1]['groups'][1]['reclaimable_files'],0)
        status,preview=self.request('preview',{'include_cache':False,'include_versions':True,'keep_versions':1,'older_than_days':0})
        self.assertEqual(status,200,preview);self.assertEqual(preview['reclaimable_files'],1)
        status,result=self.request('cleanup',{'token':preview['token']})
        self.assertEqual(status,200,result);self.assertEqual(result['removed_files'],1)
        self.assertEqual(hashlib.sha256(latest.read_bytes()).hexdigest(),digest)
        self.assertEqual(list(version_dir.iterdir()),[latest]);self.assertTrue(self.cache.exists());self.assert_original()
        self.assertEqual(len(self.app.store.get_item(self.note['id'],detail=True)['versions']),1)

    def test_wrong_methods_paths_expired_and_incomplete_preview_fail_closed(self):
        for route in ('preview','cleanup'):
            for method in ('GET','DELETE','PATCH','PUT'):
                self.assertEqual(self.request(route,method=method)[0],404)
        self.assertEqual(self.request('preview',{'path':str(self.root)})[0],400)
        self.assertEqual(self.request('cleanup',{'token':'invented','path':str(self.cache)})[0],400)
        self.assertEqual(self.request('cleanup',{'token':'invented'})[0],409)
        status,preview=self.request('preview',{})
        self.app.maintenance.tokens[preview['token']]['expires']=0
        self.assertEqual(self.request('cleanup',{'token':preview['token']})[0],409)
        with patch('yingxu.maintenance.MAX_ENTRIES',0):status,preview=self.request('preview',{})
        self.assertEqual(status,200);self.assertTrue(preview['truncated'])
        self.assertEqual(preview['reclaimable_files'],0)
        self.assertEqual(self.request('cleanup',{'token':preview['token']})[0],409)
        self.assertTrue(self.cache.exists());self.assert_original()

    def test_replaced_file_and_delete_failure_are_reported_without_touching_original(self):
        _,preview=self.request('preview',{})
        self.cache.write_bytes(b'changed since preview')
        status,result=self.request('cleanup',{'token':preview['token']})
        self.assertEqual(status,200);self.assertEqual(result['removed_files'],0);self.assertEqual(result['skipped_files'],1)
        _,preview=self.request('preview',{})
        with patch('yingxu.maintenance._unlink_verified',side_effect=PermissionError('synthetic failure')):
            status,result=self.request('cleanup',{'token':preview['token']})
        self.assertEqual(status,200);self.assertEqual(result['removed_files'],0);self.assertEqual(result['skipped_files'],1)
        self.assertTrue(result['warnings']);self.assertEqual(self.cache.read_bytes(),b'changed since preview');self.assert_original()


if __name__=='__main__':unittest.main()
