import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from yingxu.store import Store, UserError
from yingxu.skills import SkillLibrary
from yingxu.organize import Organize
from yingxu.trash import TrashDeletion


class TrashDeletionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='yingxu-trash-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.home = patch('yingxu.skills.Path.home', return_value=self.root/'home')
        self.home.start(); self.addCleanup(self.home.stop)
        self.store = Store(self.root/'data', self.root/'projects')
        self.skills = SkillLibrary(self.store); self.org = Organize(self.store)
        self.deletion = TrashDeletion(self.store,self.skills)
        self.project = self.store.create_project('临时回收项目')
        self.recycled = self.root/'fake-recycle'; self.recycled.mkdir()
        self.calls = []
        def recycle(path):
            self.calls.append(str(path))
            Path(path).rename(self.recycled/(str(len(self.calls))+'-'+Path(path).name))
        self.recycler = patch('yingxu.trash.recycle_path',side_effect=recycle)
        self.mock_recycle = self.recycler.start(); self.addCleanup(self.recycler.stop)

    def item(self,name='正文',folder=None):
        return self.store.create_item({'project_id':self.project['id'],'category':'scripts',
                                      'name':name,'content':'合成正文','folder_id':folder})

    def plan(self,batch,kind='items'):
        return self.deletion.preview({'entries':[{'id':batch.get('batch_id',batch['id']),'kind':kind}]})

    def execute(self,plan):
        return self.deletion.delete({'token':plan['token']})

    def test_success_recycles_and_tombstone_survives_restart_and_reimport(self):
        item=self.item(); batch=self.org.delete_items([item['id']]); plan=self.plan(batch)
        self.assertEqual(plan['paths'],[item['path']])
        self.assertEqual(self.execute(plan)['deleted'],1)
        self.assertFalse(Path(item['path']).exists()); self.assertEqual(self.org.trash()['total'],0)
        with self.assertRaises(UserError): self.org.restore(batch['batch_id'])
        with self.assertRaises(UserError): self.execute(plan)
        # An OS restore must not silently recreate a deliberately cleared record.
        next(self.recycled.iterdir()).rename(item['path'])
        source=self.store.sources(self.project['id'])[0]
        self.store.index_files(source,[Path(item['path'])])
        reopened=Store(self.store.data_root,self.store.project_root)
        self.assertEqual(Organize(reopened).trash()['total'],0)
        self.assertEqual(reopened.list_items(self.project['id'])['total'],0)
        reopened.index_files(source,[Path(item['path'])],restore_removed=True)
        self.assertEqual(reopened.list_items(self.project['id'])['total'],1)

    def test_stale_bytes_even_with_restored_timestamp_refuse_entire_plan(self):
        item=self.item(); path=Path(item['path']); batch=self.org.delete_items([item['id']]); plan=self.plan(batch)
        info=path.stat(); path.write_bytes(b'x'*info.st_size); os.utime(path,ns=(info.st_atime_ns,info.st_mtime_ns))
        with self.assertRaises(UserError): self.execute(plan)
        self.assertEqual(self.calls,[]); self.assertTrue(path.exists())

    def test_restored_or_reimported_member_cannot_be_deleted_by_old_confirmation(self):
        item=self.item(); batch=self.org.delete_items([item['id']]); plan=self.plan(batch)
        self.org.restore(batch['id'])
        with self.assertRaises(UserError): self.execute(plan)
        self.assertTrue(Path(item['path']).exists()); self.assertEqual(self.calls,[])

    def test_partial_failure_retains_batch_and_reports_completed_paths(self):
        a=self.item('a'); b=self.item('b'); batch=self.org.delete_items([a['id'],b['id']]); plan=self.plan(batch)
        original=self.mock_recycle.side_effect
        def second_failure(path):
            if self.calls: raise OSError('合成回收失败')
            original(path)
        self.mock_recycle.side_effect=second_failure
        result=self.execute(plan)
        self.assertEqual(result['deleted'],0); self.assertEqual(len(result['failed']),1)
        self.assertEqual(len(result['failed'][0]['deleted_paths']),1)
        self.assertEqual(self.org.trash()['total'],1)
        with self.assertRaises(UserError): self.org.restore(batch['id'])
        self.mock_recycle.side_effect=original
        retry=self.plan(batch); self.assertTrue(retry['warnings'])
        self.assertEqual(self.execute(retry)['deleted'],1)

    def test_recycler_failure_or_false_success_does_not_clear_record(self):
        item=self.item(); batch=self.org.delete_items([item['id']])
        self.mock_recycle.side_effect=OSError('合成失败')
        self.assertEqual(self.execute(self.plan(batch))['deleted'],0)
        self.mock_recycle.side_effect=lambda path: None
        self.assertEqual(self.execute(self.plan(batch))['deleted'],0)
        self.assertEqual(self.org.trash()['total'],1); self.assertTrue(Path(item['path']).exists())

    def test_recycle_intent_database_failure_prevents_any_filesystem_operation(self):
        item=self.item(); batch=self.org.delete_items([item['id']])
        skill=self.skills.create({'name':'意图写入失败'}); self.skills.remove(skill['id'])
        for selected,kind,table in ((batch,'items','trash_batches'),(skill,'skill','yx_skills')):
            plan=self.plan(selected,kind)
            with self.store.connection() as db:
                db.execute('CREATE TRIGGER refuse_recycle_intent BEFORE UPDATE OF recycle_started ON '+table+" BEGIN SELECT RAISE(ABORT,'synthetic intent failure'); END")
            result=self.execute(plan)
            self.assertEqual(result['deleted'],0); self.assertEqual(result['failed'][0]['uncertain_paths'],[])
            self.assertEqual(self.calls,[])
            with self.store.connection() as db: db.execute('DROP TRIGGER refuse_recycle_intent')
        self.assertTrue(Path(item['path']).exists()); self.assertTrue(Path(skill['path']).exists())

    def test_shell_move_then_exception_preserves_recovery_barrier_for_items_and_skills(self):
        item=self.item(); batch=self.org.delete_items([item['id']])
        skill=self.skills.create({'name':'结果不明合成技能'}); self.skills.remove(skill['id'])
        original=self.mock_recycle.side_effect
        def move_then_fail(path):
            original(path); raise OSError('synthetic result unknown after move')
        self.mock_recycle.side_effect=move_then_fail
        for selected,kind in ((batch,'items'),(skill,'skill')):
            result=self.execute(self.plan(selected,kind))
            self.assertEqual(result['deleted'],0); self.assertEqual(len(result['failed'][0]['uncertain_paths']),1)
        reopened=Store(self.store.data_root,self.store.project_root)
        with self.assertRaises(UserError): Organize(reopened).restore(batch['id'])
        with self.assertRaises(UserError): SkillLibrary(reopened).restore(skill['id'])
        self.assertEqual(reopened.list_items(self.project['id'])['total'],0)

    def test_final_catalogue_commit_failure_after_recycle_cannot_fake_restore(self):
        item=self.item(); batch=self.org.delete_items([item['id']]); plan=self.plan(batch)
        with self.store.connection() as db:
            db.execute("CREATE TRIGGER refuse_purge BEFORE UPDATE OF purged ON trash_batches BEGIN SELECT RAISE(ABORT,'synthetic final commit failure'); END")
        result=self.execute(plan)
        self.assertEqual(result['deleted'],0); self.assertEqual(result['deleted_paths'],[item['path']])
        self.assertFalse(Path(item['path']).exists())
        with self.assertRaises(UserError): self.org.restore(batch['id'])

    def test_external_reference_and_skill_clear_only_and_stay_hidden_after_refresh(self):
        external=self.root/'external.md'; external.write_text('外部合成资料',encoding='utf-8')
        source=self.store.register_source(self.project['id'],str(external),'references')
        self.store.index_files(source,[external]); item=self.store.list_items(self.project['id'])['items'][0]
        batch=self.org.delete_items([item['id']]); plan=self.plan(batch)
        self.assertEqual(plan['paths'],[]); self.assertIn('外部引用',plan['warnings'][0])
        self.assertEqual(self.execute(plan)['deleted'],1); self.assertTrue(external.exists())
        skill_path=self.skills.sources['codex']/'external'/'SKILL.md'; skill_path.parent.mkdir(parents=True)
        skill_path.write_text('# 外部技能',encoding='utf-8'); self.skills.refresh(); skill=self.skills.list()['skills'][0]
        self.skills.remove(skill['id']); plan=self.plan(skill,'skill')
        self.assertEqual(plan['paths'],[]); self.assertIn('外部',plan['warnings'][0])
        self.assertEqual(self.execute(plan)['deleted'],1)
        again=SkillLibrary(self.store); self.assertEqual(again.trash()['total'],0)
        self.assertEqual(again.list()['total'],0); self.assertTrue(skill_path.exists()); self.assertEqual(self.calls,[])
        with self.assertRaises(UserError): again.restore(skill['id'])

    def test_empty_project_with_managed_metadata_and_defaults_is_recyclable(self):
        root=Path(self.project['root']); (root/'AGENTS.md').write_text('# 合成项目入口',encoding='utf-8')
        (root/'.yingxu').mkdir()
        for name in ('PROJECT_CONTEXT.md','progress.json','files-index.jsonl'):
            (root/'.yingxu'/name).write_text('synthetic',encoding='utf-8')
        batch=self.org.delete_project(self.project['id']); plan=self.plan(batch,'project')
        self.assertNotIn('error',plan['entries'][0]); self.assertEqual(plan['paths'],[str(root)])
        self.assertTrue(plan['warnings']); self.assertEqual(self.execute(plan)['deleted'],1)
        self.assertFalse(root.exists())

    def test_unknown_file_or_empty_directory_blocks_whole_project(self):
        root=Path(self.project['root']); unknown=root/'unknown'; unknown.mkdir()
        batch=self.org.delete_project(self.project['id']); plan=self.plan(batch,'project')
        self.assertIn('error',plan['entries'][0]); self.assertEqual(self.execute(plan)['deleted'],0)
        unknown.rmdir(); (root/'unknown.txt').write_text('未知合成文件',encoding='utf-8')
        self.assertIn('error',self.plan(batch,'project')['entries'][0]); self.assertEqual(self.calls,[])

    def test_project_directory_added_after_preview_is_stale(self):
        batch=self.org.delete_project(self.project['id']); plan=self.plan(batch,'project')
        (Path(self.project['root'])/'new-unknown').mkdir()
        with self.assertRaises(UserError): self.execute(plan)
        self.assertEqual(self.calls,[])

    def test_other_batch_or_active_shared_reference_blocks_owned_file(self):
        item=self.item(); second=self.store.create_project('共享引用')
        source=self.store.register_source(second['id'],item['path'],'references')
        self.store.index_files(source,[Path(item['path'])]); batch=self.org.delete_items([item['id']])
        self.assertIn('error',self.plan(batch)['entries'][0]); self.assertEqual(self.calls,[])
        parent_batch=self.org.delete_project(self.project['id'])
        self.assertIn('error',self.plan(parent_batch,'project')['entries'][0])

    def test_hardlink_blocks_recycling(self):
        item=self.item(); os.link(item['path'],self.root/'shared-link.md')
        batch=self.org.delete_items([item['id']]); self.assertIn('error',self.plan(batch)['entries'][0])

    def test_cleared_child_tombstone_does_not_permanently_block_parent_cleanup(self):
        item=self.item(); child=self.org.delete_items([item['id']])
        parent=self.org.delete_project(self.project['id'])
        self.assertIn('error',self.plan(parent,'project')['entries'][0])
        self.assertEqual(self.execute(self.plan(child))['deleted'],1)
        plan=self.plan(parent,'project')
        self.assertNotIn('error',plan['entries'][0])
        self.assertEqual(self.execute(plan)['deleted'],1)

    def test_clear_all_selection_is_bounded_and_preview_required(self):
        for index in range(2): self.org.delete_items([self.item(str(index))['id']])
        skill=self.skills.create({'name':'本地合成技能'}); self.skills.remove(skill['id'])
        plan=self.deletion.preview({'all':True}); self.assertEqual(plan['total'],3)
        self.assertEqual(self.execute(plan)['deleted'],3); self.assertEqual(self.org.trash()['total'],0)
        with self.assertRaises(UserError): self.deletion.delete({'token':'invented'})


if __name__ == '__main__': unittest.main()
