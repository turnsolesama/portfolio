"""Real loopback uploads/link resolution on resolved synthetic directories."""
import hashlib
import http.client
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlencode
import zipfile

from server import Application, Server
from yingxu.store import CATEGORIES


def synthetic_word():
    data=io.BytesIO()
    with zipfile.ZipFile(data,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml','<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        archive.writestr('word/document.xml','<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>合成 Word 原文：鹈鹕骑车</w:t></w:r></w:p></w:body></w:document>')
    return data.getvalue()


class MarkdownFileLinkHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='yingxu-file-link-http-')
        self.root=Path(self.temp.name).resolve()
        with patch('yingxu.skills.Path.home',return_value=self.root/'empty-home'):
            self.app=Application(self.root/'data',self.root/'projects')
        self.server=Server(('127.0.0.1',0),self.app)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.project=self.app.store.create_project('文件链接 HTTP 合成项目')
        self.note=self.app.store.create_item({'project_id':self.project['id'],'category':'scripts','name':'保留原稿','content':'初始正文'})
        self.original=b'\xef\xbb\xbf'+('# 原稿\r\n\r\n正文保持不变\r\n\r\n').encode('utf-8')
        Path(self.note['path']).write_bytes(self.original)
        self.sources={}

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=5)
        self.app.jobs.pool.shutdown(wait=True);self.app.thumbnails.pool.shutdown(wait=True);self.app.context.close()
        self.assertFalse(self.thread.is_alive());self.temp.cleanup()

    def request(self,method,path,data=None,raw=None,headers=None):
        hdr={'Origin':f'http://127.0.0.1:{self.server.server_port}','X-YingXu-Token':self.app.token}
        if data is not None:raw=json.dumps(data).encode('utf-8');hdr['Content-Type']='application/json'
        for key,value in (headers or {}).items():
            if value is None:hdr.pop(key,None)
            else:hdr[key]=value
        client=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=10)
        try:
            client.request(method,path,body=raw,headers=hdr)
            response=client.getresponse();return response.status,json.loads(response.read())
        finally:client.close()

    def ok(self,method,path,data=None,expected=200,**kwargs):
        status,result=self.request(method,path,data,**kwargs)
        self.assertEqual(status,expected,result);return result

    def upload(self,name,payload,project=None):
        source=self.root/('source-'+name);source.write_bytes(payload);self.sources[source]=payload
        pid=(project or self.project)['id']
        route='/api/upload?'+urlencode({'project':pid,'category':'references','name':name})
        item=self.ok('POST',route,raw=source.read_bytes(),headers={'Content-Type':'application/octet-stream'},expected=201)
        current=self.ok('GET','/api/items/'+item['id'])
        registered=Path(current['path'])
        expected_parent=Path((project or self.project)['root'])/CATEGORIES['references'][1]
        self.assertEqual(registered.parent,expected_parent)
        self.assertNotEqual(registered,source);self.assertEqual(registered.read_bytes(),payload)
        self.assertEqual(current['category'],'references');self.assertEqual(current['project_id'],pid)
        self.assertTrue(self.app.store.resolve_item_path(current).is_relative_to(Path((project or self.project)['root'])))
        return current

    def link(self,item):
        return self.ok('GET','/api/markdown-assets/file-link?'+urlencode({'note':self.note['id'],'item':item['id']}))

    def resolve(self,path,expected=200,headers=None,**extra):
        return self.ok('GET','/api/markdown-assets/resolve-file?'+urlencode({'note':self.note['id'],'path':path,**extra}),expected=expected,headers=headers)

    def assert_originals(self):
        self.assertEqual(Path(self.note['path']).read_bytes(),self.original)
        for path,content in self.sources.items():self.assertEqual(path.read_bytes(),content)

    def test_binary_word_and_text_upload_registered_then_relative_and_stable_links_roundtrip(self):
        for name,payload,kind in [('中文 Word [1]#%.docx',synthetic_word(),'docx'),('文本 [2]#%.txt',b'\xef\xbb\xbf'+ '文本\r\n未改'.encode(),'text')]:
            with self.subTest(kind=kind):
                item=self.upload(name,payload);self.assertEqual(item['kind'],kind)
                linked=self.link(item);self.assertIn('%20',linked['relative_path']);self.assertIn('%23',linked['relative_path']);self.assertIn('%25',linked['relative_path'])
                self.assertNotIn(str(self.root),linked['markdown']);self.assertIn(r'\[',linked['markdown'])
                for target in (linked['relative_path'],linked['relative_path']+'#yx-item='+item['id']):
                    resolved=self.resolve(target)
                    self.assertEqual(resolved,{'id':item['id'],'project_id':self.project['id'],'name':item['name'],'kind':kind})
                self.assertEqual(hashlib.sha256(Path(item['path']).read_bytes()).digest(),hashlib.sha256(payload).digest())
        self.assert_originals()

    def test_original_stable_link_survives_http_rename_and_move_but_plain_stale_path_does_not(self):
        item=self.upload('链接原名.txt','文件正文\r\n'.encode());linked=self.link(item)
        destination=linked['relative_path']+'#yx-item='+item['id'];original_path=Path(item['path'])
        self.ok('POST','/api/rename',{'id':item['id'],'name':'修改后名称'})
        folder=self.ok('POST','/api/folders',{'project_id':self.project['id'],'category':'references','name':'分类目录'},expected=201)
        self.ok('POST','/api/move',{'ids':[item['id']],'category':'references','folder_id':folder['id']})
        current=self.ok('GET','/api/items/'+item['id'])
        self.assertFalse(original_path.exists());self.assertEqual(current['folder_id'],folder['id'])
        self.assertEqual(Path(current['path']).name,'修改后名称.txt')
        self.assertEqual(Path(current['path']).parent,Path(folder['path']))
        self.assertEqual(Path(current['path']).read_bytes(),'文件正文\r\n'.encode())
        self.assertEqual(self.resolve(destination)['id'],item['id'])
        self.resolve(linked['relative_path'],expected=404)
        self.assert_originals()

    def test_removed_or_foreign_id_never_falls_back_to_an_existing_relative_path(self):
        text=self.upload('本项目文本.txt',b'text');word=self.upload('待删除文档.docx',synthetic_word())
        linked=self.link(text);destination=linked['relative_path']+'#yx-item='+word['id']
        self.ok('DELETE','/api/items/'+word['id'])
        self.resolve(destination,expected=404)
        self.ok('GET','/api/markdown-assets/file-link?'+urlencode({'note':self.note['id'],'item':word['id']}),expected=404)
        self.assertTrue(Path(word['path']).exists())
        other=self.app.store.create_project('隔离的第二项目');foreign=self.upload('其他项目.txt',b'foreign',other)
        self.resolve(linked['relative_path']+'#yx-item='+foreign['id'],expected=403)
        self.ok('GET','/api/markdown-assets/file-link?'+urlencode({'note':self.note['id'],'item':foreign['id']}),expected=403)
        self.resolve(linked['relative_path']+'#yx-item='+'f'*32,expected=404)
        self.resolve(linked['relative_path']+'#yx-item=invalid',expected=400)
        self.assert_originals()

    def test_origin_query_fields_and_path_boundaries_fail_without_uploading_or_modifying_sources(self):
        item=self.upload('验证文件.txt',b'kept');linked=self.link(item)
        route='/api/markdown-assets/file-link?'+urlencode({'note':self.note['id'],'item':item['id']})
        self.ok('GET',route,headers={'Origin':'https://foreign.invalid'},expected=403)
        self.ok('GET',route+'&unexpected=1',expected=400)
        self.resolve(linked['relative_path'],headers={'Origin':'https://foreign.invalid'},expected=403)
        self.resolve(linked['relative_path'],expected=400,unexpected='1')
        for path in ('https://foreign.invalid/file.txt','../../../outside.txt','file:///C:/file.txt'):
            self.resolve(path+'#yx-item='+item['id'],expected=403)
        upload='/api/upload?'+urlencode({'project':self.project['id'],'category':'references','name':'未授权上传.txt'})
        for headers in ({'Origin':'https://foreign.invalid'},{'X-YingXu-Token':None}):
            self.ok('POST',upload,raw=b'blocked',headers=headers,expected=403)
        self.assertFalse((Path(self.project['root'])/CATEGORIES['references'][1]/'未授权上传.txt').exists())
        self.assert_originals()


if __name__=='__main__':unittest.main()
