import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from yingxu.maintenance import Maintenance, _identity, _unlink_verified
from yingxu.store import Store, UserError


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='yingxu-maintenance-')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.store=Store(self.root/'data',self.root/'projects')
        self.maintenance=Maintenance(self.store)

    def file(self, relative, content=b'old', age=100):
        path=self.store.data_root/relative;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(content);stamp=time.time()-age*86400;os.utime(path,(stamp,stamp))
        return path

    def history(self):
        folder='versions/'+'a'*32
        return [self.file(folder+'/'+f'{i:032x}.md',age=100-i) for i in range(3)]

    def test_preview_default_and_confirmed_cleanup_preserve_original_database_and_history(self):
        history=self.history();thumbnail=self.file('thumbnails/'+'b'*64+'.jpg')
        unknown=self.file('thumbnails/my-photo.jpg');backup=self.file('backups/yingxu-old.sqlite3')
        original=self.root/'projects'/'original.md';original.write_bytes(b'original')
        db_before=self.store.db_path.read_bytes()
        result=self.maintenance.preview()
        self.assertEqual(result['reclaimable_files'],1)
        self.assertTrue(thumbnail.exists())
        self.assertNotIn(str(self.root),str(result))
        cleaned=self.maintenance.execute({'token':result['token']})
        self.assertEqual(cleaned['removed_files'],1,cleaned)
        self.assertEqual(cleaned['removed_bytes'],3)
        self.assertFalse(thumbnail.exists())
        self.assertTrue(all(p.exists() for p in [*history,unknown,backup,original]))
        self.assertEqual(self.store.db_path.read_bytes(),db_before)

    def test_history_opt_in_keeps_newest_and_age_policy(self):
        old,middle,new=self.history()
        result=self.maintenance.preview({'include_cache':False,'include_versions':True,'keep_versions':1,'older_than_days':99})
        self.assertEqual(result['reclaimable_files'],2)
        cleaned=self.maintenance.execute({'token':result['token']})
        self.assertEqual(cleaned['removed_files'],2,cleaned)
        self.assertFalse(old.exists());self.assertFalse(middle.exists());self.assertTrue(new.exists())

    def test_changed_identity_hardlink_and_latest_changed_are_preserved(self):
        old,middle,new=self.history()
        preview=self.maintenance.preview({'include_versions':True,'keep_versions':1,'older_than_days':0})
        new.unlink();middle.write_bytes(b'changed backup')
        result=self.maintenance.execute({'token':preview['token']})
        self.assertTrue(middle.exists());self.assertFalse(old.exists())
        self.assertEqual(result['skipped_files'],1)
        cache=self.file('thumbnails/'+'b'*64+'.jpg')
        p=self.maintenance.preview();os.link(cache,self.root/'outside-link.jpg')
        self.assertEqual(self.maintenance.execute({'token':p['token']})['removed_files'],0)
        self.assertTrue(cache.exists())

    def test_path_injection_expired_replayed_and_truncated_tokens_rejected(self):
        for options in ({'path':str(self.root)}, {'keep_versions':0}, {'include_versions':1}):
            with self.assertRaises(UserError):self.maintenance.preview(options)
        self.file('thumbnails/'+'b'*64+'.jpg')
        p=self.maintenance.preview()
        with self.assertRaises(UserError):self.maintenance.execute({'token':p['token'],'path':'x'})
        self.maintenance.tokens[p['token']]['expires']=0
        with self.assertRaises(UserError):self.maintenance.execute({'token':p['token']})
        p=self.maintenance.preview();self.maintenance.execute({'token':p['token']})
        with self.assertRaises(UserError):self.maintenance.execute({'token':p['token']})
        self.history()
        with patch('yingxu.maintenance.MAX_ENTRIES',0):p=self.maintenance.preview({'include_versions':True})
        self.assertTrue(p['truncated']);self.assertEqual(p['reclaimable_files'],0)
        with self.assertRaises(UserError):self.maintenance.execute({'token':p['token']})

    def test_failed_unlink_never_falls_back_or_touches_unknown_files(self):
        cache=self.file('thumbnails/'+'b'*64+'.jpg');unknown=self.file('thumbnails/keep-me.txt')
        p=self.maintenance.preview()
        with patch('yingxu.maintenance._unlink_verified',side_effect=PermissionError('synthetic lock')):
            result=self.maintenance.execute({'token':p['token']})
        self.assertEqual(result['removed_files'],0);self.assertEqual(result['skipped_files'],1)
        self.assertEqual(cache.read_bytes(),b'old');self.assertEqual(unknown.read_bytes(),b'old')

    def test_external_companion_and_skill_history_preserve_latest(self):
        for index in range(3):
            self.file('external-versions/'+'a'*64+'/'+f'{index:032x}.md',age=100-index)
            self.file('external-versions/'+'a'*64+'/'+f'{index:032x}.metadata.json',age=100-index)
            self.file('skill_versions/'+'b'*32+f'/2026-01-0{index+1}T00-00-00.000+00-00_12345678.md',age=100-index)
        p=self.maintenance.preview({'include_versions':True,'keep_versions':1,'older_than_days':0})
        self.assertEqual(p['reclaimable_files'],6)
        result=self.maintenance.execute({'token':p['token']})
        self.assertEqual(result['removed_files'],6,result)
        self.assertEqual(len(list((self.store.data_root/'external-versions'/('a'*64)).iterdir())),2)
        self.assertEqual(len(list((self.store.data_root/'skill_versions'/('b'*32)).iterdir())),1)

    def test_open_handle_identity_rejects_replacement_without_deleting_it(self):
        path=self.file('thumbnails/'+'b'*64+'.jpg')
        identity=_identity(path.stat())
        replacement=self.file('thumbnails/replacement.jpg',b'new file')
        os.replace(replacement,path)
        with self.assertRaises(OSError):_unlink_verified(path,identity)
        self.assertEqual(path.read_bytes(),b'new file')

    def test_redirected_ancestor_and_hardlinked_cache_are_never_candidates(self):
        path=self.file('thumbnails/'+'b'*64+'.jpg')
        with patch('yingxu.maintenance.has_link',side_effect=lambda p:Path(p)==path.parent):
            self.assertEqual(self.maintenance.preview()['reclaimable_files'],0)
        os.link(path,self.root/'outside.jpg')
        self.assertEqual(self.maintenance.preview()['reclaimable_files'],0)


if __name__=='__main__':unittest.main()
