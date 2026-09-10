import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

from server import Application,Server


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='yingxu-http-')
        self.root=Path(self.tmp.name).resolve()
        # Use empty external skill roots, never inspect real skill contents in tests.
        from unittest.mock import patch
        with patch('yingxu.skills.Path.home',return_value=self.root/'home'):
            self.app=Application(self.root/'data',self.root/'projects')
        self.server=Server(('127.0.0.1',0),self.app)
        self.port=self.server.server_port
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        self.app.jobs.pool.shutdown(wait=True);self.app.thumbnails.pool.shutdown(wait=True);self.app.context.close()
        self.tmp.cleanup()

    def request(self,method,path,data=None,headers=None,raw=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=10)
        hdr={'X-YingXu-Token':self.app.token}
        if data is not None:hdr['Content-Type']='application/json';raw=json.dumps(data).encode()
        hdr.update(headers or {})
        conn.request(method,path,body=raw,headers=hdr)
        result=conn.getresponse();body=result.read();status=result.status;rh=dict(result.getheaders());conn.close()
        return status,body,rh

    def test_origin_host_and_mutation_token_protect_local_files(self):
        status,body,_=self.request('GET','/api/health');self.assertEqual(status,200)
        for headers in ({'Origin':'https://evil.example'},{'Host':'evil.example'},{'Sec-Fetch-Site':'cross-site'}):
            self.assertEqual(self.request('GET','/api/bootstrap',headers=headers)[0],403)
        self.assertEqual(self.request('POST','/api/projects',{'name':'blocked'},headers={'X-YingXu-Token':''})[0],403)
        self.assertEqual(self.app.store.list_projects(),[])

    def test_settings_routes_validate_and_external_preview_ranges_never_create_project(self):
        self.assertTrue(json.loads(self.request('GET','/api/settings')[1])['close_to_tray'])
        self.assertEqual(self.request('PATCH','/api/settings',{'close_to_tray':False},headers={'X-YingXu-Token':''})[0],403)
        status,raw,_=self.request('PATCH','/api/settings',{'close_to_tray':False,'confirm_delete':False})
        self.assertEqual(status,200,raw); self.assertFalse(json.loads(raw)['close_to_tray'])
        self.assertFalse(json.loads(self.request('GET','/api/bootstrap')[1])['settings']['confirm_delete'])
        self.assertEqual(self.request('PATCH','/api/settings',{'unknown':1})[0],400)
        path=self.root/'outside.mp4'; path.write_bytes(b'0123456789')
        self.assertEqual(self.request('POST','/api/external-open',{'paths':[str(path)]},headers={'X-YingXu-Token':''})[0],403)
        status,raw,_=self.request('POST','/api/external-open',{'paths':[str(path)]})
        self.assertEqual(status,200,raw); entry=json.loads(raw)['entries'][0]
        status,raw,headers=self.request('GET',entry['media_url'],headers={'Range':'bytes=2-5'})
        self.assertEqual((status,raw),(206,b'2345')); self.assertEqual(headers['Content-Range'],'bytes 2-5/10')
        self.assertEqual(self.request('GET',entry['media_url'],headers={'Range':'bytes=50-'})[0],416)
        self.assertEqual(self.request('GET',entry['content_url']+'?path='+str(path))[0],400)
        self.assertFalse(json.loads(self.request('GET',entry['content_url'])[1])['content']['editable'])
        self.assertEqual(self.request('PUT',entry['content_url'],{'content':'write'})[0],404)
        self.assertEqual(path.read_bytes(),b'0123456789'); self.assertEqual(self.app.store.list_projects(),[])

    def test_project_library_routes_only_change_logical_organisation(self):
        project=self.app.store.create_project('归类合成项目'); root=Path(project['root'])
        before=sorted(str(path.relative_to(root)) for path in root.rglob('*'))
        self.assertTrue(self.app.bootstrap()['capabilities']['project_library'])
        self.assertEqual(self.request('POST','/api/project-folders',{'name':'分类'},headers={'X-YingXu-Token':''})[0],403)
        status,raw,_=self.request('POST','/api/project-folders',{'name':'分类'})
        self.assertEqual(status,201,raw); folder=json.loads(raw)
        status,raw,_=self.request('PATCH','/api/project-folders/'+folder['id'],{'name':'新分类'})
        self.assertEqual(status,200,raw); self.assertEqual(json.loads(raw)['name'],'新分类')
        self.assertEqual(self.request('PATCH','/api/project-library/'+project['id'],{'folder_id':folder['id']})[0],200)
        self.assertEqual(self.request('POST','/api/project-library/'+project['id']+'/visit',{})[0],200)
        snapshot=json.loads(self.request('GET','/api/project-library')[1])
        self.assertEqual(snapshot['projects'][0]['folder_id'],folder['id']); self.assertEqual(snapshot['recent_ids'],[project['id']])
        self.assertEqual(self.request('DELETE','/api/project-folders/'+folder['id'],{})[0],409)
        self.assertEqual(self.request('PATCH','/api/project-library/'+project['id'],{'folder_id':None})[0],200)
        self.assertEqual(self.request('DELETE','/api/project-folders/'+folder['id'],{})[0],200)
        self.assertEqual(sorted(str(path.relative_to(root)) for path in root.rglob('*')),before)

    def test_trash_delete_requires_preview_token_and_exposes_recycle_capability(self):
        from unittest.mock import patch
        project=self.app.store.create_project('HTTP回收合成项目')
        item=self.app.store.create_item({'project_id':project['id'],'name':'合成正文','content':'test'})
        batch=self.app.organize.delete_items([item['id']])
        self.assertTrue(self.app.bootstrap()['capabilities']['trash_delete'])
        body={'entries':[{'id':batch['id'],'kind':'items'}]}
        self.assertEqual(self.request('POST','/api/trash/delete-preview',body,headers={'X-YingXu-Token':''})[0],403)
        self.assertEqual(self.request('POST','/api/trash/delete',{'token':'invalid'})[0],409)
        status,raw,_=self.request('POST','/api/trash/delete-preview',body)
        self.assertEqual(status,200,raw); preview=json.loads(raw)
        self.assertEqual(preview['paths'],[item['path']])
        target=self.root/'mock-recycled.md'
        with patch('yingxu.trash.recycle_path',side_effect=lambda path: Path(path).rename(target)):
            status,raw,_=self.request('POST','/api/trash/delete',{'token':preview['token']})
        self.assertEqual(status,200,raw); self.assertEqual(json.loads(raw)['deleted'],1)
        self.assertTrue(target.exists()); self.assertEqual(json.loads(self.request('GET','/api/trash')[1])['total'],0)
        self.assertEqual(self.request('POST','/api/trash/'+batch['id']+'/restore',{})[0],409)

    def test_upload_range_read_and_rename_keep_file_bytes(self):
        project=json.loads(self.request('POST','/api/projects',{'name':'HTTP项目'})[1]);pid=project['id']
        payload=b'0123456789'*1000
        status,body,_=self.request('POST',f'/api/upload?project={pid}&category=generated&name=sample.mp4',headers={'Content-Type':'application/octet-stream'},raw=payload)
        self.assertEqual(status,201,body)
        item=json.loads(body);iid=item['id'];self.assertEqual(Path(item['path']).read_bytes(),payload)
        status,body,headers=self.request('GET','/api/media/'+iid,headers={'Range':'bytes=10-19'})
        self.assertEqual((status,body),(206,b'0123456789'));self.assertEqual(headers['Content-Range'],'bytes 10-19/10000')
        self.assertEqual(self.request('GET','/api/media/'+iid,headers={'Range':'bytes=99999-'})[0],416)
        self.assertEqual(self.request('GET','/api/media/'+iid,headers={'Range':'bytes=-10'})[1],b'0123456789')
        status,body,_=self.request('POST','/api/rename',{'id':iid,'name':'new-file'})
        self.assertEqual(status,200,body);new=json.loads(body)
        self.assertEqual(Path(new['path']).read_bytes(),payload)
        self.assertEqual(json.loads(self.request('GET','/api/native-file/'+iid)[1])['path'],new['path'])

    def test_reject_upload_executable_and_path_escape(self):
        pid=self.app.store.create_project('边界')['id']
        self.assertEqual(self.request('POST',f'/api/upload?project={pid}&name=bad.exe',raw=b'x')[0],400)
        self.assertEqual(self.request('GET','/../server.py')[0],404)
        self.assertFalse(any(Path(self.app.store.get_project(pid)['root']).rglob('*.exe')))

    def test_folder_upload_move_delete_restore_and_context(self):
        project=self.app.store.create_project('分集制作');pid=project['id']
        status,body,_=self.request('POST','/api/folders',{'project_id':pid,'category':'characters','name':'第01集'})
        self.assertEqual(status,201,body);folder=json.loads(body)
        status,body,_=self.request('POST',f'/api/upload?project={pid}&category=characters&folder_id={folder["id"]}&name=role.md',raw='角色正文'.encode())
        self.assertEqual(status,201,body);item=json.loads(body)
        original=Path(item['path']);self.assertEqual(item['folder_id'],folder['id'])
        status,body,_=self.request('GET',f'/api/items?project={pid}&category=characters&folder={folder["id"]}')
        self.assertEqual(status,200,body);self.assertEqual(json.loads(body)['total'],1)
        status,body,_=self.request('POST','/api/move',{'ids':[item['id']],'category':'scenes','folder_id':None})
        self.assertEqual(status,200,body);moved=self.app.store.get_item(item['id'])
        self.assertFalse(original.exists());self.assertEqual(Path(moved['path']).read_text(encoding='utf-8'),'角色正文')
        self.assertEqual(moved['category'],'scenes');self.assertFalse(moved['folder_id'])
        status,body,_=self.request('DELETE','/api/items/'+item['id']);self.assertEqual(status,200,body)
        removed=json.loads(body);self.assertTrue(Path(moved['path']).exists())
        self.assertEqual(self.request('GET','/api/items/'+item['id'])[0],404)
        status,body,_=self.request('POST','/api/trash/'+removed['batch_id']+'/restore',{})
        self.assertEqual(status,200,body)
        status,body,_=self.request('POST','/api/context/refresh',{'project_id':pid})
        self.assertEqual(status,200,body)
        progress=json.loads(Path(json.loads(body)['json_path']).read_text(encoding='utf-8'))
        self.assertEqual(progress['folders'][0]['id'],folder['id'])
        self.assertIn('folder_id',json.loads(Path(json.loads(body)['index_path']).read_text(encoding='utf-8').splitlines()[0]))

    def test_project_and_skill_trash_routes_preserve_files(self):
        project=self.app.store.create_project('可以恢复');pid=project['id']
        self.app.store.create_item({'project_id':pid,'category':'scripts','name':'正文','content':'故事'})
        self.app.context.export(pid)
        status,body,_=self.request('PATCH','/api/projects/'+pid,{'name':'新项目名'})
        self.assertEqual(status,200,body);self.assertEqual(self.app.store.get_project(pid)['root'],project['root'])
        status,body,_=self.request('DELETE','/api/projects/'+pid);self.assertEqual(status,200,body);batch=json.loads(body)
        self.assertEqual(json.loads(self.request('GET','/api/projects')[1])['projects'],[])
        progress=json.loads((Path(project['root'])/'.yingxu/progress.json').read_text(encoding='utf-8'))
        self.assertTrue(progress['archived'])
        status,body,_=self.request('POST','/api/trash/'+batch['batch_id']+'/restore',{})
        self.assertEqual(status,200,body);self.assertEqual(self.app.store.list_items(pid)['total'],1)
        skill=self.app.skills.create({'name':'技能回收','content':'# 可恢复'})
        status,body,_=self.request('DELETE','/api/skills/'+skill['id']);self.assertEqual(status,200,body)
        entries=json.loads(self.request('GET','/api/trash')[1])['entries']
        self.assertTrue(any(entry['kind']=='skill' and entry['id']==skill['id'] for entry in entries))
        self.assertEqual(self.request('POST','/api/trash/'+skill['id']+'/restore',{'kind':'skill'})[0],200)
        self.assertTrue(Path(skill['path']).exists())

    def test_reference_import_assigns_folder_across_index_batches(self):
        project=self.app.store.create_project('批量引用');pid=project['id']
        folder=self.app.organize.create_folder(pid,'characters','共用角色')
        source_dir=self.root/'external';source_dir.mkdir()
        for number in range(66):(source_dir/f'actor-{number}.md').write_text('共同角色',encoding='utf-8')
        status,body,_=self.request('POST','/api/import',{'project_id':pid,'category':'characters','folder_id':folder['id'],'paths':[str(source_dir)]})
        self.assertEqual(status,202,body);jid=json.loads(body)['job_id']
        import time
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            job=self.app.jobs.get(jid)
            if job['state'] in ('done','error'):break
            time.sleep(.03)
        self.assertEqual(job['state'],'done',job);self.assertEqual(job['errors'],[])
        self.assertEqual(self.app.store.list_items(pid,folder=folder['id'])['total'],66)
        self.assertEqual(len(list(source_dir.glob('*.md'))),66)
        self.assertEqual(len(list(Path(folder['path']).glob('*.md'))),0)

    def test_trash_pagination_combines_skill_and_project_items_without_duplicates(self):
        pid=self.app.store.create_project('分页回收')['id']
        for n in range(3):
            item=self.app.store.create_item({'project_id':pid,'name':f'回收{n}'})
            self.app.organize.delete_items([item['id']])
        for n in range(2):
            skill=self.app.skills.create({'name':f'规范{n}'})
            self.app.skills.remove(skill['id'])
        pages=[]
        for offset in (0,2,4):
            status,body,_=self.request('GET',f'/api/trash?project={pid}&limit=2&offset={offset}')
            self.assertEqual(status,200,body);page=json.loads(body)
            self.assertEqual(page['total'],5);self.assertLessEqual(len(page['entries']),2)
            pages.extend(page['entries'])
        self.assertEqual(len({entry['id'] for entry in pages}),5)
        self.assertEqual(sum(entry['kind']=='skill' for entry in pages),2)


if __name__=='__main__':unittest.main()
