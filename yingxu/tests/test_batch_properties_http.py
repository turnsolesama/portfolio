import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from server import Application, Server

class BatchPropertiesHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='yingxu-batch-http-'); self.root = Path(self.tmp.name).resolve()
        with patch('yingxu.skills.Path.home',return_value=self.root/'empty-home'): self.app = Application(self.root/'data',self.root/'projects')
        self.pid = self.app.store.create_project('HTTP临时项目')['id']
        self.item = self.app.store.create_item({'project_id':self.pid,'name':'临时正文','content':'不改变文件'})
        self.server = Server(('127.0.0.1',0),self.app)
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start()
    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        self.app.jobs.pool.shutdown(wait=True); self.app.thumbnails.pool.shutdown(wait=True); self.app.context.close(); self.tmp.cleanup()
    def request(self,fields,headers=None,method='POST'):
        conn = http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=10)
        hdr = {'Content-Type':'application/json','X-YingXu-Token':self.app.token,**(headers or {})}
        conn.request(method,'/api/items/batch-properties',body=json.dumps(fields).encode(),headers=hdr)
        response = conn.getresponse(); raw = response.read(); status = response.status; conn.close()
        return status,json.loads(raw)
    def test_auth_origin_and_wrong_method_do_not_mutate(self):
        fields = {'project_id':self.pid,'ids':[self.item['id']],'status':'已完成'}
        for headers in [{'X-YingXu-Token':''},{'Origin':'https://evil.example'},{'Host':'evil.example'},{'Sec-Fetch-Site':'cross-site'}]:
            self.assertEqual(self.request(fields,headers)[0],403)
        self.assertEqual(self.request(fields,method='PATCH')[0],404)
        self.assertEqual(self.app.store.get_item(self.item['id'])['status'],'待开始')
    def test_success_requests_context_once_invalid_body_does_not(self):
        fields = {'project_id':self.pid,'ids':[self.item['id']],'tags_add':['追加'],'status':'已完成'}
        path = Path(self.item['path']); before = path.read_bytes(); origin = {'Origin':f'http://127.0.0.1:{self.server.server_port}'}
        with patch.object(self.app.context,'request') as request:
            status,body = self.request(fields,origin); self.assertEqual(status,200,body); request.assert_called_once_with(self.pid)
            request.reset_mock(); self.assertEqual(self.request({**fields,'unexpected':True},origin)[0],400); request.assert_not_called()
        self.assertEqual(body['items'][0]['tags'],['追加']); self.assertEqual(body['items'][0]['status'],'已完成'); self.assertEqual(path.read_bytes(),before)

if __name__ == '__main__': unittest.main()
