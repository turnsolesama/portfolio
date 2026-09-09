import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock
from aihub import api, config, db as dbmod
from test_aihub import Fixture


class LabelMigration(unittest.TestCase):
    def test_wal_backup_preserves_old_values_and_rollback_is_separate(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'hub.sqlite'
            old = sqlite3.connect(path)
            old.execute('PRAGMA journal_mode=WAL')
            old.executescript(dbmod.SCHEMA.replace(',\n  scope TEXT, model_role TEXT, architecture TEXT', ''))
            old.execute("INSERT INTO models(path,rating,notes,source_url) VALUES('model',9,'user note','https://example.com')")
            old.execute("INSERT INTO model_labels VALUES('model','image','[\"style\"]','previous')")
            old.commit()
            with mock.patch.object(config,'DB_PATH',str(path)):
                current = dbmod.DB()
                backup = Path(current.migration_backup)
                self.assertTrue(backup.is_file())
                self.assertEqual(tuple(current.one('SELECT rating,notes,source_url FROM models')), (9,'user note','https://example.com'))
                self.assertEqual(tuple(current.one('SELECT domain,purposes,updated_at,scope FROM model_labels')), ('image','["style"]','previous',None))
                current.conn.close()
                second = dbmod.DB()
                self.assertIsNone(second.migration_backup)
                second.conn.close()
            spec = importlib.util.spec_from_file_location('restore_database',Path(__file__).parents[1]/'tools/restore_database.py')
            tool = importlib.util.module_from_spec(spec);spec.loader.exec_module(tool)
            restored=Path(folder)/'restored.sqlite'
            before=hashlib.sha256(backup.read_bytes()).hexdigest()
            tool.prepare(backup,restored)
            with sqlite3.connect(restored) as c:
                self.assertEqual([r[1] for r in c.execute('PRAGMA table_info(model_labels)')],['model_path','domain','purposes','updated_at'])
                self.assertEqual(c.execute('SELECT rating FROM models').fetchone()[0],9)
            c.close()
            self.assertEqual(before,hashlib.sha256(backup.read_bytes()).hexdigest())
            with self.assertRaises(ValueError):tool.prepare(backup,path)
            old.close()


class ClassificationAPI(Fixture):
    def test_preview_is_readonly_manual_dimensions_filter_before_pagination(self):
        self.db.upsert_model({'path':'one','filename':'component.pt','mtype':'Private','scope':'unknown','rating':8,'notes':'keep'})
        mid=self.db.one('SELECT rowid_pk FROM models')[0]
        body={'ids':[mid],'scope':'central','model_role':'Detection','architecture':'unverified-custom','domain':'vision'}
        result=api.models_classify(self.db,self.cfg,{},dict(body,preview=True))
        self.assertEqual(result[0],200)
        self.assertEqual(self.db.one('SELECT COUNT(*) FROM model_labels')[0],0)
        result=api.models_classify(self.db,self.cfg,{},body)
        self.assertEqual(result[0],200)
        response=json.loads(api.models_list(self.db,self.cfg,{'scope':'central','type':'Detection','family':'unverified-custom'},None)[2])
        self.assertEqual(response['total'],1)
        self.assertEqual(response['items'][0]['classification']['architecture_source'],'manual')
        self.assertFalse(response['items'][0]['classification']['registered'])
        self.assertEqual(tuple(self.db.one('SELECT rating,notes,mtype,scope FROM models')),(8,'keep','Private','unknown'))
        detail=json.loads(api.model_detail(self.db,self.cfg,{'id':str(mid)},None)[2])
        self.assertEqual(detail['classification'],response['items'][0]['classification'])

    def test_invalid_batch_dimension_is_atomic_and_readonly_preview_never_counts_as_registration(self):
        self.db.upsert_model({'path':'one','filename':'a.safetensors','mtype':'LoRA'})
        mid=self.db.one('SELECT rowid_pk FROM models')[0]
        self.assertEqual(api.models_classify(self.db,self.cfg,{},{'ids':[mid],'scope':'Private'})[0],400)
        self.assertEqual(self.db.one('SELECT COUNT(*) FROM model_labels')[0],0)
        response=json.loads(api.models_list(self.db,self.cfg,{'intake':'registered'},None)[2])
        self.assertEqual(response['total'],0)


if __name__=='__main__':unittest.main()
