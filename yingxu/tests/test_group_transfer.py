"""Atomic drag transfer of logical groups, using only temporary files."""
import concurrent.futures
import sqlite3
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from yingxu.resource_groups import ResourceGroups
from yingxu.store import Store, UserError

class GroupTransferTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='yingxu-transfer-');self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name).resolve();self.store=Store(root/'data',root/'projects');self.groups=ResourceGroups(self.store)
        self.project=self.store.create_project('合成分组转移')
        self.items=[self.store.create_item({'project_id':self.project['id'],'name':f'素材{n}','content':f'正文{n}\r\n'}) for n in range(6)]
        self.ids=[i['id'] for i in self.items]
        self.a=self.groups.create({'project_id':self.project['id'],'item_ids':self.ids[:2]})
        self.b=self.groups.create({'project_id':self.project['id'],'item_ids':self.ids[2:4]})
        self.original={i['path']:Path(i['path']).read_bytes() for i in self.items}
    def body(self,**kw):
        return dict(ids=self.ids[:1],revision=1,target_group_id=self.b['id'],target_revision=1,**kw)
    def snapshot(self):return self.groups.list(self.project['id'])
    def test_transfer_and_remove_preserve_files_and_touch_both_revisions(self):
        result=self.groups.transfer(self.a['id'],self.body())
        self.assertEqual(result['source']['member_ids'],self.ids[1:2]);self.assertEqual(result['target']['member_ids'],self.ids[2:4]+self.ids[:1])
        self.assertEqual((result['source']['revision'],result['target']['revision']),(2,2))
        removed=self.groups.transfer(self.b['id'],{'ids':self.ids[:1],'revision':2,'target_group_id':None})
        self.assertIsNone(removed['target']);self.assertEqual(removed['source']['member_ids'],self.ids[2:4])
        self.assertEqual(self.original,{p:Path(p).read_bytes() for p in self.original})
    def test_stale_missing_and_invalid_revisions_preserve_ownership(self):
        before=self.snapshot()
        for change in ({'revision':2},{'target_revision':2},{'revision':True},{'target_revision':False},{'ids':[self.ids[4]]},{'ids':[self.ids[0],self.ids[0]]},{'target_group_id':'invalid'}):
            with self.subTest(change=change),self.assertRaises(UserError):self.groups.transfer(self.a['id'],{**self.body(),**change})
            self.assertEqual(before,self.snapshot())
        for missing in ('revision','target_revision','target_group_id'):
            body=self.body();body.pop(missing)
            with self.assertRaises(UserError):self.groups.transfer(self.a['id'],body)
        self.assertEqual(before,self.snapshot())
    def test_full_target_or_cross_project_never_removes_source(self):
        before=self.snapshot()
        with patch('yingxu.resource_groups.MAX_MEMBERS',2),self.assertRaises(UserError):self.groups.transfer(self.a['id'],self.body())
        other=self.store.create_project('另一个项目');ids=[self.store.create_item({'project_id':other['id'],'name':f'其他{n}'})['id'] for n in range(2)]
        target=self.groups.create({'project_id':other['id'],'item_ids':ids})
        with self.assertRaises(UserError):self.groups.transfer(self.a['id'],{**self.body(),'target_group_id':target['id']})
        self.assertEqual(before,self.snapshot())
    def test_sql_failure_after_first_move_rolls_back_both_groups(self):
        before=self.snapshot()
        with self.store.connection() as db:db.execute(f"CREATE TRIGGER reject_transfer BEFORE UPDATE OF group_id ON resource_group_members WHEN NEW.item_id='{self.ids[1]}' BEGIN SELECT RAISE(ABORT,'synthetic'); END")
        with self.assertRaises(sqlite3.IntegrityError):self.groups.transfer(self.a['id'],{**self.body(),'ids':self.ids[:2]})
        self.assertEqual(before,self.snapshot());self.assertEqual(self.original,{p:Path(p).read_bytes() for p in self.original})
    def test_concurrent_moves_have_one_winner_and_no_missing_member(self):
        def move():
            try:return self.groups.transfer(self.a['id'],self.body())
            except UserError as error:return error.status
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:move(),range(2)))
        self.assertEqual(sum(isinstance(r,dict) for r in results),1);self.assertIn(409,results)
        with self.store.connection() as db:self.assertEqual(db.execute('SELECT count(*) FROM resource_group_members WHERE item_id=?',(self.ids[0],)).fetchone()[0],1)
    def test_same_group_noop_and_removed_member_refused(self):
        before=self.snapshot();result=self.groups.transfer(self.a['id'],{**self.body(),'target_group_id':self.a['id']});self.assertEqual(result['source']['revision'],1);self.assertEqual(before,self.snapshot())
        with self.store.connection() as db:db.execute('UPDATE items SET removed=1 WHERE id=?',(self.ids[0],))
        with self.assertRaises(UserError):self.groups.transfer(self.a['id'],self.body())
        with self.store.connection() as db:self.assertEqual(db.execute('SELECT group_id FROM resource_group_members WHERE item_id=?',(self.ids[0],)).fetchone()[0],self.a['id'])

if __name__=='__main__':unittest.main()
