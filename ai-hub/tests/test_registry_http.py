"""Representative page/API integration on a temporary loopback server."""
import json
from pathlib import Path
import unittest
import urllib.parse
import test_organization_http as fixtures


class RegistryHTTP(unittest.TestCase):
    setUp=fixtures.OrganizationHTTP.setUp
    tearDown=fixtures.OrganizationHTTP.tearDown
    patch=fixtures.OrganizationHTTP.patch
    request=fixtures.OrganizationHTTP.request
    ok=fixtures.OrganizationHTTP.ok

    def test_project_knowledge_evidence_and_history_endpoints(self):
        self.cfg['ai_root']=str(self.root)
        project=self.root/'40_Projects/Film';project.mkdir(parents=True)
        doc=project/'README.md';doc.write_text('# Fixture project',encoding='utf-8')
        knowledge=self.root/'80_Knowledge/Guides';knowledge.mkdir(parents=True)
        tutorial=knowledge/'tutorial.md';tutorial.write_text('# Tutorial',encoding='utf-8')
        wf=self.root/'60_Workflows/workflow.json';wf.parent.mkdir();wf.write_text('{}')
        model=self.root/'20_Models/Runtime/sample.safetensors';model.parent.mkdir(parents=True);model.write_bytes(b'fixture')
        output=project/'run/result.bin';output.parent.mkdir();output.write_bytes(b'result')
        items=self.ok('GET','/api/projects')['items'];self.assertEqual(items[0]['name'],'Film')
        self.assertEqual(items[0]['status'],'未登记')
        reports=self.ok('GET','/api/reports')['items'];self.assertIn(str(tutorial),[r['path'] for r in reports])
        text=self.ok('GET','/api/report/content?path='+urllib.parse.quote(str(doc)))
        self.assertEqual(text['content'],'# Fixture project')
        record={'id':'film','name':'Film','type':'creative','root':str(project),'current_doc':str(doc),'delivery':str(project/'Delivery')}
        preview=self.ok('POST','/api/registry/preview',{'kind':'project','record':record})
        self.assertFalse((self.data/'registry.json').exists())
        self.ok('POST','/api/registry/save',{'token':preview['token']})
        self.assertFalse((project/'Delivery').exists())
        evidence=self.ok('POST','/api/registry/evidence',{'workflow_path':str(wf),'dependencies':[str(model)],'outputs':[str(output)]})
        self.assertEqual(len(evidence['workflow_sha256']),64)
        self.assertIsInstance(evidence['outputs'][0]['mtime_ns'],str)
        self.assertNotIn('state',evidence)
        record['description']='Revised'
        preview=self.ok('POST','/api/registry/preview',{'kind':'project','record':record})
        self.ok('POST','/api/registry/save',{'token':preview['token']})
        backups=self.ok('GET','/api/registry/backups')['items'];self.assertIsInstance(backups,list);self.assertEqual(len(backups),1)
        restore=self.ok('POST','/api/registry/restore-preview',{'backup_id':backups[0]['id']})
        self.ok('POST','/api/registry/save',{'token':restore['token']})
        self.assertNotEqual(self.ok('GET','/api/registry')['projects'][0]['description'],'Revised')
        self.assertEqual(self.request('POST','/api/registry/save',{'token':restore['token']})[0],400)

    def test_new_assets_and_routes_render_without_real_asset_requests(self):
        for url,marker in [('/','data-page="projects"'),('/registry.js','effective_validation_status'),('/app.js','verificationBadge'),('/atelier.css','project-grid')]:
            self.assertIn(marker,self.ok('GET',url))
        health=self.ok('GET','/api/health');self.assertEqual(health['version'],'2.5.0')
        self.assertEqual(health['desktop_shell_version'],'2.4.1')
        self.assertFalse(health['jobs_running'])


if __name__=='__main__':unittest.main()
