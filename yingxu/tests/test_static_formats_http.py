import base64
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from server import Application, Server


class StaticFormatsHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='yingxu-static-formats-')
        self.root = Path(self.tmp.name).resolve()
        with patch('yingxu.skills.Path.home', return_value=self.root/'home'):
            self.app = Application(self.root/'data', self.root/'projects')
        self.server = Server(('127.0.0.1', 0), self.app)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        self.app.jobs.pool.shutdown(wait=True); self.app.thumbnails.pool.shutdown(wait=True)
        self.app.context.close(); self.tmp.cleanup()

    def request(self, path, data=None, method='GET', headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        hdr = {'X-YingXu-Token':self.app.token, **(headers or {})}
        raw = None
        if data is not None:
            hdr['Content-Type']='application/json'; raw=json.dumps(data).encode()
        conn.request(method,path,body=raw,headers=hdr)
        response=conn.getresponse(); body=response.read(); status=response.status
        result_headers=dict(response.getheaders()); conn.close()
        return status,body,result_headers

    def opened(self, name, raw):
        path=self.root/name; path.write_bytes(raw)
        status,body,_=self.request('/api/external-open',{'paths':[str(path)]},'POST')
        self.assertEqual(status,200,body)
        return path,json.loads(body)['entries'][0]

    def indexed(self, path):
        project=self.app.store.create_project('合成格式项目')
        source=self.app.store.register_source(project['id'],path,'references')
        self.app.store.index_files(source,[path])
        return self.app.store.list_items(project['id'])['items'][0]

    def test_svg_external_and_project_previews_are_sanitized_readonly_and_not_thumbnail_jobs(self):
        raw=b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 80"><rect width="50" height="40" fill="#456745"/></svg>'
        path,entry=self.opened('safe.SVG',raw)
        status,body,_=self.request(entry['content_url']); self.assertEqual(status,200,body)
        content=json.loads(body)['content']; self.assertFalse(content['editable'])
        safe=base64.b64decode(content['preview_url'].split(',',1)[1])
        status,body,headers=self.request(entry['media_url'],headers={'Range':'bytes=0-4'})
        self.assertEqual(status,200); self.assertEqual(body,safe)
        self.assertIn('image/svg+xml',headers['Content-Type'])
        self.assertIn('sandbox',headers['Content-Security-Policy'])
        self.assertEqual(headers['X-Content-Type-Options'],'nosniff')
        self.assertEqual(self.request(entry['content_url']+'/content',{'content':'changed'},'POST')[0],415)
        item=self.indexed(path); self.assertEqual(item['kind'],'svg')
        self.assertEqual(self.request('/api/media/'+item['id'])[1],safe)
        project_content=json.loads(self.request('/api/content/'+item['id'])[1])
        self.assertEqual(project_content['preview_url'],content['preview_url'])
        with patch.object(self.app.thumbnails.pool,'submit') as submit:
            self.assertEqual(self.request('/api/thumbnail/'+item['id'])[0],404)
            submit.assert_not_called()
        self.assertEqual(path.read_bytes(),raw)

    def test_active_or_oversized_svg_cannot_escape_via_any_media_route(self):
        for number,raw in enumerate([b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',b'X'*(1024*1024+1)]):
            path,entry=self.opened(str(number)+'.svg',raw)
            item=self.indexed(path)
            for endpoint in [entry['content_url'],entry['media_url'],'/api/content/'+item['id'],'/api/media/'+item['id']]:
                status,body,headers=self.request(endpoint)
                self.assertIn(status,(413,415),body)
                self.assertIn('application/json',headers['Content-Type'])
                self.assertNotIn(b'<script>',body)
            self.assertEqual(path.read_bytes(),raw)

    def test_html_source_is_preserved_preview_inert_and_raw_media_is_attachment(self):
        raw=b'<h1>Title</h1><table><tr><td>Cell</td></tr></table><script>window.BAD=1</script><img src="https://example.invalid/pixel"><a href="javascript:alert(1)">Link</a>'
        path,entry=self.opened('page.HTML',raw)
        status,body,_=self.request(entry['content_url']); self.assertEqual(status,200,body)
        content=json.loads(body)['content']
        self.assertFalse(content['editable']);self.assertEqual(content['content'],raw.decode())
        self.assertIn('<h1>',content['preview_html']);self.assertIn('<table>',content['preview_html'])
        for forbidden in ['<script','javascript:','https://','window.BAD']:
            self.assertNotIn(forbidden,content['preview_html'])
        item=self.indexed(path);self.assertEqual(item['kind'],'html')
        for endpoint in [entry['media_url'],'/api/media/'+item['id']]:
            status,body,headers=self.request(endpoint)
            self.assertEqual(status,200);self.assertEqual(body,raw)
            self.assertTrue(headers['Content-Type'].startswith('text/plain'))
            self.assertEqual(headers['Content-Disposition'],'attachment')
            self.assertEqual(headers['X-Content-Type-Options'],'nosniff')
        self.assertEqual(self.request(entry['content_url']+'/content',{'content':'changed'},'POST')[0],415)
        self.assertEqual(path.read_bytes(),raw)

    def test_external_static_content_still_rejects_cross_site_and_expired_capabilities(self):
        _,entry=self.opened('page.htm',b'<p>Hello</p>')
        for endpoint in [entry['media_url'],entry['content_url']]:
            self.assertEqual(self.request(endpoint,headers={'Sec-Fetch-Site':'cross-site'})[0],403)
        self.app.external.entries[entry['id']]['expires']=0
        self.assertEqual(self.request(entry['content_url'])[0],404)
        self.assertEqual(self.app.store.list_projects(),[])

    def test_complex_html_falls_back_to_readonly_source_with_explicit_notice(self):
        raw=b'<p>Too many nodes</p>'*1100
        path,entry=self.opened('complex.html',raw)
        status,body,_=self.request(entry['content_url']);self.assertEqual(status,200,body)
        content=json.loads(body)['content']
        self.assertEqual(content['content'],raw.decode())
        self.assertFalse(content['editable'])
        self.assertIn('查看源码',content['notice'])
        self.assertLess(len(content['preview_html']),500)
        self.assertEqual(path.read_bytes(),raw)


if __name__=='__main__':unittest.main()
