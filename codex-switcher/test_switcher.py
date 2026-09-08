import json
from pathlib import Path
import tempfile
import tomllib
import unittest
import switcher_core as c

def profile(**changes):
    return dict(id='demo',name='演示服务',base_url='https://api.example/v1',env_key='DEMO_API_KEY',model='demo-model',wire_api='responses',**changes)

class SwitcherTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def test_validate_valid_profile(self):self.assertEqual(c.validate(profile()),profile())
    def test_reject_invalid_urls(self):
        for url in ['file:///x','https://user:key@api.example','https://api.example?key=secret','http://remote.example','https://api.example/#secret','https://api.example:bad','https://api.ex ample']:
            with self.subTest(url=url),self.assertRaises(ValueError):c.validate({**profile(),'base_url':url})
    def test_loopback_http_allowed(self):self.assertEqual(c.validate({**profile(),'base_url':'http://127.0.0.1:8080/v1'})['wire_api'],'responses')
    def test_reject_system_env_and_invalid_ids(self):
        for name in ['PATH','CODEX_HOME','bad-key','KEY\nX']:
            with self.assertRaises(ValueError):c.validate({**profile(),'env_key':name})
        for name in ['a.b','a"b','9foo','a'*65]:
            with self.assertRaises(ValueError):c.validate({**profile(),'id':name})
    def test_chat_protocol_not_silently_converted(self):
        with self.assertRaises(ValueError):c.validate({**profile(),'wire_api':'chat'})
    def test_export_omits_keys_and_extra_fields(self):
        output=c.export_profiles([{**profile(),'api_key':'SECRET_SENTINEL','token':'OTHER_SENTINEL'}])
        self.assertNotIn('SENTINEL',output)
        self.assertFalse(json.loads(output)['contains_secrets'])
    def test_empty_profiles_are_preserved(self):
        path=self.root/'profiles.json';c.save_profiles(path,[]);self.assertEqual(c.load_profiles(path),[])
    def test_invalid_store_is_not_replaced(self):
        path=self.root/'profiles.json';path.write_text('{bad')
        with self.assertRaises(ValueError):c.load_profiles(path)
        self.assertEqual(path.read_text(),'{bad')
    def test_save_checks_concurrent_edit(self):
        path=self.root/'profiles.json';digest=c.file_hash(path);c.save_profiles(path,[])
        with self.assertRaises(ValueError):c.save_profiles(path,[profile()],digest)
    def test_duplicate_id_rejected(self):
        with self.assertRaises(ValueError):c.save_profiles(self.root/'p.json',[profile(),profile()])
    def test_legacy_invalid_record_remains_readable_and_unchanged(self):
        path=self.root/'profiles.json';old={**profile(),'id':'legacy','env_key':'bad-key','wire_api':'chat'}
        path.write_text(json.dumps({'profiles':[old]}),encoding='utf-8')
        before=path.read_bytes()
        self.assertEqual(c.load_profiles(path),[old]);self.assertTrue(c.profile_issue(old))
        self.assertEqual(path.read_bytes(),before)
        c.save_profiles(path,[old,profile()])
        self.assertEqual(c.load_profiles(path),[old,profile()])
    def test_legacy_invalid_record_cannot_be_added_or_changed(self):
        path=self.root/'profiles.json';old={**profile(),'wire_api':'chat'}
        with self.assertRaises(ValueError):c.save_profiles(path,[old])
        path.write_text(json.dumps({'profiles':[old]}),encoding='utf-8')
        with self.assertRaises(ValueError):c.save_profiles(path,[{**old,'name':'changed'}])
        with self.assertRaises(ValueError):c.render_config('model="demo"',old)
    def test_legacy_record_can_be_repaired(self):
        path=self.root/'profiles.json'
        path.write_text(json.dumps({'profiles':[{**profile(),'wire_api':'chat'}]}),encoding='utf-8')
        c.save_profiles(path,[profile()]);self.assertEqual(c.load_profiles(path),[profile()])
    def test_json_list_import(self):
        rows,_=c.import_text(json.dumps([{**profile(),'apiKey':'secret'}]));self.assertEqual(rows[0]['secret'],'secret')
    def test_json_provider_map_import(self):
        rows,_=c.import_text(json.dumps({'providers':{'service':profile()}}));self.assertEqual(len(rows),1)
    def test_native_export_roundtrip(self):
        rows,_=c.import_text(c.export_profiles([profile()]));self.assertEqual(rows[0]['profile'],profile())
    def test_codex_toml_import_multiple_providers(self):
        rows,_=c.import_text('model="test"\n[model_providers.first]\nbase_url="https://one.example"\nenv_key="ONE_KEY"\n[model_providers.second]\nbase_url="https://two.example"\nenv_key="TWO_KEY"')
        self.assertEqual([x['profile']['model'] for x in rows],['test','test'])
    def test_settings_config_wrapper(self):
        config='model="model-x"\n[model_providers.third]\nbase_url="https://api.example/v1"\nenv_key="THIRD_KEY"'
        raw={'codex':{'providers':{'export-id':{'name':'Third','settingsConfig':{'config':config,'env':{'THIRD_KEY':'fake-secret'}}}}}}
        rows,_=c.import_text(json.dumps(raw));self.assertEqual(rows[0]['secret'],'fake-secret');self.assertEqual(rows[0]['profile']['model'],'model-x')
    def test_env_import_does_not_execute_or_expand(self):
        rows,_=c.import_text('OPENAI_BASE_URL=https://api.example/v1\nOPENAI_API_KEY=$(never-execute)\nOPENAI_MODEL=test')
        self.assertEqual(rows[0]['secret'],'$(never-execute)')
    def test_unsupported_auth_export_has_no_sensitive_error(self):
        with self.assertRaises(ValueError) as cm:c.import_text('{"tokens":{"access_token":"PRIVATE_SENTINEL"}}')
        self.assertNotIn('PRIVATE_SENTINEL',str(cm.exception))
    def test_file_size_limit(self):
        with self.assertRaises(ValueError):c.import_text('x'*(2*1024*1024+1))
    def test_merge_deduplicates_and_renames_collisions(self):
        existing=[profile()];records=[{'profile':profile(),'secret':'keep-private'},{'profile':{**profile(),'base_url':'https://other.example'},'secret':'new'}]
        merged,added,skipped=c.merge_profiles(existing,records)
        self.assertEqual(skipped,1);self.assertEqual(added[0]['profile']['id'],'demo-2');self.assertEqual(existing,[profile()]);self.assertEqual(len(merged),2)
    def test_extra_fields_reported(self):
        _,warnings=c.import_text(json.dumps({**profile(),'http_headers':{'x':'value'}}));self.assertTrue(warnings)
    def test_config_preserves_nested_models_and_user_provider(self):
        original='model="old"\nmodel_provider="custom"\n# Keep comment\n[model_providers.custom]\nname="Mine"\nbase_url="https://custom.example"\n[profiles.work]\nmodel="nested-model"\n[desktop]\nsetting=true\n'
        out=c.render_config(original,profile());data=tomllib.loads(out)
        self.assertEqual(data['profiles']['work']['model'],'nested-model');self.assertEqual(data['model_providers']['custom']['name'],'Mine');self.assertIn('# Keep comment',out)
        self.assertEqual(data['model_provider'],'switcher_demo')
    def test_config_escaping_and_idempotence(self):
        p={**profile(),'name':'quote " / \\ 文本','model':'a"b\\c'}
        first=c.render_config('model="old"\n',p);second=c.render_config(first,p)
        self.assertEqual(tomllib.loads(first),tomllib.loads(second));self.assertEqual(second.count('[model_providers.switcher_demo]'),1)
    def test_official_mode_only_removes_owned_provider(self):
        original='model="old"\n[model_providers.other]\nname="keep"\n'
        out=c.render_config(c.render_config(original,profile()),None);data=tomllib.loads(out)
        self.assertNotIn('model_provider',data);self.assertEqual(data['model_providers'],{'other':{'name':'keep'}})
    def test_legacy_block_migration(self):
        old='model_provider="demo"\nmodel="old"\n'+c.BEGIN+'\n[model_providers.demo]\nname="old"\n'+c.END+'\n[desktop]\nsetting=true\n'
        out=tomllib.loads(c.render_config(old,profile()));self.assertNotIn('demo',out['model_providers']);self.assertTrue(out['desktop']['setting'])
    def test_collision_rejected_without_overwrite(self):
        with self.assertRaises(ValueError):c.render_config('[model_providers.switcher_demo]\nname="mine"',profile())
    def test_unusual_toml_fails_closed_or_preserves(self):
        text='note="""\n[not_a_table]\nmodel="quoted"\n"""\nmodel="real"\n'
        try:out=c.render_config(text,profile())
        except ValueError:return
        self.assertEqual(tomllib.loads(out)['note'],tomllib.loads(text)['note'])
    def test_apply_backup_and_restore(self):
        path=self.root/'config.toml';original='model="old"\n[desktop]\nx=true\n';path.write_text(original)
        c.apply_config(path,profile(),c.file_hash(path));saved=list((self.root/'switcher-backups').glob('*.bak'))
        self.assertEqual(len(saved),1);self.assertEqual(saved[0].read_text(),original)
        c.restore_backup(path,saved[0],c.file_hash(path));self.assertEqual(path.read_text(),original)
    def test_apply_concurrent_guard(self):
        path=self.root/'config.toml';digest=c.file_hash(path);path.write_text('model="new"')
        with self.assertRaises(ValueError):c.apply_config(path,profile(),digest)
        self.assertEqual(path.read_text(),'model="new"')
    def test_restore_rejects_arbitrary_path(self):
        path=self.root/'config.toml';other=self.root/'other.bak';other.write_text('model="x"')
        with self.assertRaises(ValueError):c.restore_backup(path,other,'missing')
    def test_invalid_config_never_backed_up_or_overwritten(self):
        path=self.root/'config.toml';path.write_text('broken="')
        with self.assertRaises(ValueError):c.apply_config(path,profile())
        self.assertEqual(path.read_text(),'broken="');self.assertFalse((self.root/'switcher-backups').exists())

if __name__=='__main__':unittest.main()
