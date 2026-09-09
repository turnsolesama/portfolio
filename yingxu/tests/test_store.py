import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import unittest

from yingxu.store import Store,UserError
from yingxu.jobs import Jobs
from server import parse_range


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='yingxu-test-')
        self.root=Path(self.tmp.name)
        self.store=Store(self.root/'data',self.root/'projects')
        self.project=self.store.create_project('合成测试项目','测试，不是真实创作资产')
        self.pid=self.project['id']

    def tearDown(self):self.tmp.cleanup()

    def item(self,name='剧本',**kw):
        return self.store.create_item({'project_id':self.pid,'name':name,'category':'scripts','content':'# 雨夜\n\n港口角色重逢。',**kw})

    def test_edit_creates_exact_backup_and_rejects_external_conflict(self):
        item=self.item();path=Path(item['path']);before=path.read_bytes()
        opened=self.store.read_content(item['id'])
        saved=self.store.save_content(item['id'],{'etag':opened['etag'],'content':'# 黎明\n下一场'})
        self.assertEqual(saved['content'],'# 黎明\n下一场')
        with self.store.connection() as db:version=db.execute('SELECT * FROM versions WHERE item_id=?',(item['id'],)).fetchone()
        self.assertEqual(Path(version['path']).read_bytes(),before)
        self.assertEqual(version['sha256'],hashlib.sha256(before).hexdigest())
        path.write_text('外部最新文字',encoding='utf-8')
        with self.assertRaises(UserError) as exc:self.store.save_content(item['id'],{'etag':saved['etag'],'content':'不能覆盖'})
        self.assertEqual(exc.exception.status,409)
        self.assertEqual(path.read_text(encoding='utf-8'),'外部最新文字')

    def test_chinese_phrase_search_and_advanced_filters(self):
        a=self.item('雨夜镜头',tags=['夜景'],status='已完成')
        self.item('雨后的夜晚',content='另外一个场景',tags=['外景'])
        result=self.store.list_items(self.pid,q='雨夜 tag:夜景 status:已完成')
        self.assertEqual([x['id'] for x in result['items']],[a['id']])
        self.assertEqual(self.store.list_items(self.pid,q='雨夜')['total'],1)
        self.assertEqual(self.store.list_items(self.pid,q='type:video')['total'],0)
        self.assertNotIn('search_content',result['items'][0])

    def test_pagination_has_bound_and_does_not_send_large_metadata(self):
        for i in range(73):self.item(f'{i:03d}',metadata={'prompt':'文'*10000,'shot_number':str(i)})
        first=self.store.list_items(self.pid,limit=999,sort='name');second=self.store.list_items(self.pid,offset=60,sort='name')
        self.assertEqual(len(first['items']),60);self.assertEqual(len(second['items']),13)
        self.assertFalse({x['id'] for x in first['items']} & {x['id'] for x in second['items']})
        self.assertLess(len(json.dumps(first,ensure_ascii=False)),100000)
        self.assertEqual(len(self.store.get_item(first['items'][0]['id'])['metadata']['prompt']),10000)

    def test_import_is_reference_and_rescan_preserves_user_labels(self):
        folder=self.root/'external';folder.mkdir();p=folder/'参考.txt';p.write_text('原始文件',encoding='utf-8')
        source=self.store.register_source(self.pid,str(folder),'references')
        self.assertEqual(self.store.index_files(source,[p]),(1,0))
        item=self.store.list_items(self.pid)['items'][0]
        self.assertEqual(item['path'],str(p));self.assertTrue(p.exists())
        self.store.update_item(item['id'],{'name':'我的名字','category':'scenes','tags':['保留'],'status':'已完成'})
        p.write_text('外部已更新的资料',encoding='utf-8')
        self.store.index_files(source,[p]);updated=self.store.get_item(item['id'])
        self.assertEqual((updated['name'],updated['category'],updated['tags'],updated['status']),('我的名字','scenes',['保留'],'已完成'))
        self.assertEqual(self.store.index_files(source,[p]),(0,1))

    def test_removal_only_hides_index_and_does_not_resurrect(self):
        item=self.item();path=Path(item['path']);self.store.remove_item(item['id'])
        self.assertTrue(path.exists());self.assertEqual(self.store.list_items(self.pid)['total'],0)
        source=next(s for s in self.store.sources(self.pid) if s['id']==item['source_id'])
        self.store.index_files(source,[path]);self.assertEqual(self.store.list_items(self.pid)['total'],0)

    def test_relations_bidirectional_same_project_only(self):
        a=self.item('分镜',category='shots');b=self.item('角色',category='characters')
        relation=self.store.add_relation(a['id'],b['id'],'角色')
        self.assertEqual(self.store.get_item(b['id'],True)['relations'][0]['item']['id'],a['id'])
        other=self.store.create_project('其他项目');c=self.store.create_item({'project_id':other['id'],'name':'其他'})
        with self.assertRaises(UserError):self.store.add_relation(a['id'],c['id'],'角色')
        self.store.remove_relation(relation['id']);self.assertEqual(self.store.get_item(a['id'],True)['relations'],[])

    @unittest.skipUnless(os.name=='nt','Windows rename semantics')
    def test_real_rename_updates_paths_but_keeps_ids_and_relations(self):
        a=self.item('旧文件');b=self.item('关联镜头');self.store.add_relation(b['id'],a['id'],'剧本')
        old=Path(a['path']);renamed=self.store.rename_file(a['id'],'新的中文名.md')
        self.assertFalse(old.exists());self.assertTrue(Path(renamed['path']).exists())
        self.assertEqual(renamed['id'],a['id']);self.assertEqual(self.store.get_item(b['id'],True)['relations'][0]['item']['name'],'新的中文名')
        conflict=self.item('不能覆盖')
        before=Path(conflict['path']).read_bytes()
        with self.assertRaises(UserError):self.store.rename_file(a['id'],'不能覆盖')
        self.assertEqual(Path(conflict['path']).read_bytes(),before)

    def test_hardlinked_document_edit_is_refused(self):
        a=self.item();path=Path(a['path']);os.link(path,path.with_name('硬链接.md'))
        opened=self.store.read_content(a['id'])
        with self.assertRaises(UserError):self.store.save_content(a['id'],{'etag':opened['etag'],'content':'不能断开旧链接'})
        self.assertEqual(path.read_text(encoding='utf-8'),opened['content'])

    def test_link_is_not_followed_and_late_replacement_is_rejected(self):
        item=self.item();p=Path(item['path']);outside=self.root/'outside.txt';outside.write_text('private',encoding='utf-8')
        try:
            link=self.root/'link.txt';link.symlink_to(outside)
        except OSError:self.skipTest('symlink privilege unavailable')
        with self.assertRaises(UserError):self.store.register_source(self.pid,str(link),'references')
        p.unlink();p.symlink_to(outside)
        with self.assertRaises(UserError):self.store.read_content(item['id'])

    def test_invalid_files_and_disk_roots_are_not_registered(self):
        p=self.root/'x.cmd';p.write_text('do not execute',encoding='utf-8')
        for value in (str(p),str(self.root.anchor),'../relative'):
            with self.assertRaises(UserError):self.store.register_source(self.pid,value,'references')

    def test_range_reads_prefix_suffix_and_rejects_invalid(self):
        self.assertEqual(parse_range('bytes=10-19',100),(10,19,True))
        self.assertEqual(parse_range('bytes=-12',100),(88,99,True))
        self.assertEqual(parse_range('bytes=90-',100),(90,99,True))
        for value in ('bytes=100-','bytes=20-10','bytes=-0','bytes=0-1,3-4','nonsense'):
            with self.assertRaises(UserError):parse_range(value,100)

    def test_database_backup_is_queryable(self):
        import sqlite3
        self.item();backup=self.store.backup_database()
        db=sqlite3.connect(backup)
        try:self.assertEqual(db.execute('SELECT count(*) FROM items').fetchone()[0],1)
        finally:db.close()


if __name__=='__main__':unittest.main()
