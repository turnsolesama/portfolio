"""Atomic catalogue-only batch edits, using temporary synthetic fixtures."""
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
from yingxu.store import Store, UserError, uid
from yingxu.organize import Organize

class BatchPropertiesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='yingxu-batch-properties-')
        self.root = Path(self.tmp.name).resolve()
        self.store = Store(self.root/'data', self.root/'projects')
        self.pid = self.store.create_project('临时批量属性')['id']
        self.items = [self.store.create_item({'project_id':self.pid,'name':f'素材{i}','content':'原始正文',
            'category':'scripts' if i == 0 else 'references','tags':['原标签'],'status':'进行中'}) for i in range(2)]
        self.ids = [item['id'] for item in self.items]
    def tearDown(self): self.tmp.cleanup()
    def call(self, **fields): return self.store.batch_properties({'project_id':self.pid,'ids':self.ids,**fields})
    def snapshot(self):
        with self.store.connection() as db:
            return ([tuple(row) for row in db.execute('SELECT * FROM items ORDER BY id')],
                    [tuple(row) for row in db.execute('SELECT rowid,text FROM item_search ORDER BY rowid')])
    def test_append_preserves_unrelated_fields_files_and_updates_search(self):
        before = [self.store.get_item(iid) for iid in self.ids]
        original = [(Path(item['path']).read_bytes(),Path(item['path']).stat().st_mtime_ns) for item in self.items]
        with patch('yingxu.store.now',return_value='2030-01-02T03:04:05.000+00:00'):
            result = self.call(tags_add=[' 原标签 ','唯一批量标签','唯一批量标签'],status='已完成')
        self.assertEqual([item['id'] for item in result['items']],self.ids)
        for index,iid in enumerate(self.ids):
            current = self.store.get_item(iid)
            self.assertEqual(current['tags'],['原标签','唯一批量标签']); self.assertEqual(current['status'],'已完成')
            self.assertEqual(current['updated'],'2030-01-02T03:04:05.000+00:00')
            for key in before[index].keys() - {'tags','status','updated'}: self.assertEqual(current[key],before[index][key],key)
            self.assertEqual((Path(current['path']).read_bytes(),Path(current['path']).stat().st_mtime_ns),original[index])
            self.assertEqual(set(result['items'][index]),{'id','project_id','tags','status','updated'})
        self.assertEqual(self.store.list_items(self.pid,q='唯一批量标签')['total'],2)
    def test_omitted_fields_stay_byte_identical(self):
        raw = '[ "保留格式", "重复", "重复" ]'
        with self.store.connection() as db: db.execute('UPDATE items SET tags=? WHERE id=?',(raw,self.ids[0]))
        self.call(status='待审核')
        with self.store.connection() as db: self.assertEqual(db.execute('SELECT tags FROM items WHERE id=?',(self.ids[0],)).fetchone()[0],raw)
        self.call(tags_add=['新标签'])
        self.assertEqual([self.store.get_item(iid)['status'] for iid in self.ids],['待审核','待审核'])
    def test_strict_validation_never_writes(self):
        base = {'project_id':self.pid,'ids':self.ids,'status':'已完成'}
        invalid = [None,[],{},{**base,'unknown':True},{**base,'project_id':True},{**base,'project_id':'../project'},
            {**base,'ids':[]},{**base,'ids':'x'},{**base,'ids':[self.ids[0]]*2},{**base,'ids':[True]},
            {**base,'ids':[[]]},{**base,'ids':['x'*32]},{**base,'ids':[uid() for _ in range(201)]},
            {'project_id':self.pid,'ids':self.ids},*[{**base,'status':v} for v in [None,True,{},'错误',' 已完成']],
            *[{**base,'tags_add':v} for v in [None,[],{},'标签',[1],[' '],['x'*81],['换行\n'],['控制\x00'],['a']*51]]]
        before = self.snapshot()
        for value in invalid:
            with self.subTest(value=value),self.assertRaises(UserError): self.store.batch_properties(value)
            self.assertEqual(self.snapshot(),before)
    def test_overflow_and_corrupt_old_labels_rollback_all(self):
        self.store.update_item(self.ids[1],{'tags':[f'标签{i}' for i in range(50)]}); before = self.snapshot()
        with self.assertRaises(UserError) as error: self.call(tags_add=['新增'],status='已完成')
        self.assertEqual(error.exception.status,409); self.assertEqual(self.snapshot(),before)
        for broken in ['{','{}','[1]']:
            with self.store.connection() as db: db.execute('UPDATE items SET tags=? WHERE id=?',(broken,self.ids[1]))
            before = self.snapshot()
            with self.assertRaises(UserError): self.call(tags_add=['新增'])
            self.assertEqual(self.snapshot(),before)
    def test_fifty_existing_tags_accept_duplicate_without_truncation(self):
        tags = [f'标签{i}' for i in range(50)]
        self.store.update_item(self.ids[0],{'tags':tags}); self.call(tags_add=['标签49'])
        self.assertEqual(self.store.get_item(self.ids[0])['tags'],tags)
    def test_cross_project_missing_removed_item_all_reject(self):
        other = self.store.create_project('另一个项目')
        foreign = self.store.create_item({'project_id':other['id'],'name':'跨项目'})
        for invalid in [foreign['id'],uid()]:
            before = self.snapshot()
            with self.assertRaises(UserError): self.store.batch_properties({'project_id':self.pid,'ids':[self.ids[0],invalid],'tags_add':['不应保存']})
            self.assertEqual(self.snapshot(),before)
        self.store.remove_item(self.ids[1]); before = self.snapshot()
        with self.assertRaises(UserError): self.call(status='已完成')
        self.assertEqual(self.snapshot(),before)
    def test_removed_project_and_folder_cannot_update(self):
        folder = Organize(self.store).create_folder(self.pid,'scripts','临时文件夹')
        with self.store.connection() as db:
            db.execute('UPDATE items SET folder_id=? WHERE id=?',(folder['id'],self.ids[0]))
            db.execute('UPDATE folders SET removed=1 WHERE id=?',(folder['id'],))
        before = self.snapshot()
        with self.assertRaises(UserError): self.call(status='已完成')
        self.assertEqual(self.snapshot(),before)
        with self.store.connection() as db: db.execute('UPDATE projects SET removed=1 WHERE id=?',(self.pid,))
        with self.assertRaises(UserError) as error: self.call(status='已完成')
        self.assertEqual(error.exception.status,404); self.assertEqual(self.snapshot(),before)
    def test_validation_precedes_first_update(self):
        with self.store.connection() as db: db.execute("CREATE TRIGGER no_write BEFORE UPDATE ON items BEGIN SELECT RAISE(ABORT,'should not update'); END")
        with self.assertRaises(UserError): self.store.batch_properties({'project_id':self.pid,'ids':[self.ids[0],uid()],'status':'已完成'})
    def test_sql_failure_rolls_back_prior_item_and_fts(self):
        before = self.snapshot()
        with self.store.connection() as db: db.execute(f"CREATE TRIGGER fail_second BEFORE UPDATE ON items WHEN NEW.id='{self.ids[1]}' BEGIN SELECT RAISE(ABORT,'test failure'); END")
        with self.assertRaises(sqlite3.IntegrityError): self.call(tags_add=['事务标签'],status='已完成')
        self.assertEqual(self.snapshot(),before)
    def test_independent_stores_merge_concurrent_appends(self):
        other = Store(self.root/'data',self.root/'projects'); barrier = threading.Barrier(2); errors = []
        def run(store,tag):
            try:
                barrier.wait(timeout=5); store.batch_properties({'project_id':self.pid,'ids':self.ids,'tags_add':[tag]})
            except Exception as error: errors.append(error)
        threads = [threading.Thread(target=run,args=(s,t)) for s,t in [(self.store,'并发甲'),(other,'并发乙')]]
        for thread in threads: thread.start()
        for thread in threads: thread.join(timeout=10)
        self.assertFalse(any(t.is_alive() for t in threads)); self.assertEqual(errors,[])
        for iid in self.ids:
            item = self.store.get_item(iid); self.assertEqual(set(item['tags']),{'原标签','并发甲','并发乙'}); self.assertEqual(item['status'],'进行中')
    def test_two_hundred_registered_records_return_bounded_metadata(self):
        ids = list(self.ids)
        with self.store.connection() as db:
            for i in range(198):
                iid = uid(); ids.append(iid)
                db.execute('INSERT INTO items(id,project_id,source_id,name,category,kind,ext,path,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?)',
                    (iid,self.pid,self.items[0]['source_id'],f'合成{i}','references','text','.txt',str(self.root/f'registered-{i}.txt'),'before','before'))
        response = self.store.batch_properties({'project_id':self.pid,'ids':ids,'status':'待审核'})
        self.assertEqual([row['id'] for row in response['items']],ids); self.assertLess(len(json.dumps(response)),60000)

if __name__ == '__main__': unittest.main()
