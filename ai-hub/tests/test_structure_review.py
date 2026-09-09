"""Independent API integration review, isolated under temporary fixture roots."""
import copy
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock

from aihub import api, config, db as dbmod
from test_aihub import Fixture


class StructureReview(Fixture):
    def setUp(self):
        super().setUp()
        self.data = self.folder / "application-data"
        self.patch = mock.patch.object(config, "DATA_DIR", str(self.data))
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.cfg["network"] = {"proxy": "http://127.0.0.1:1234"}

    def request(self, method, path, body=None, params=None):
        response = api.dispatch(self.db, self.cfg, method, path, params or {}, body)
        data = json.loads(response[2])
        self.assertEqual(response[0], 200, data)
        return data

    def model_pair(self):
        folder = self.ai / "20_Models" / "Runtime" / "loras"
        folder.mkdir(parents=True)
        source = folder / "unknown.pt"
        source.write_bytes(b"fixture weights")
        alias = folder / "z-alias.pt"
        os.link(source, alias)
        for p in (source, alias):
            self.db.upsert_model({"path": str(p), "filename": p.name, "mtype": "LoRA", "scope": "central",
                                  "rating": 9, "notes": "keep user notes", "source_url": "https://example.com/model"})
        first = self.db.model_by_path(str(source))["rowid_pk"]
        second = self.db.model_by_path(str(alias))["rowid_pk"]
        self.request("POST", "/api/models/classify", {"ids": [second], "domain": "video", "purposes": ["motion"],
                                                       "scope": "training", "architecture": "ReviewedWan"})
        return first, second

    def detail(self, mid):
        return self.request("GET", "/api/model/" + str(mid))["classification"]

    def test_purpose_facet_counts_one_physical_model_once(self):
        self.model_pair()
        result = self.request("GET", "/api/models", params={"domain": "video", "scope": "training"})
        self.assertEqual(result["total"], 1)
        count = next(p["count"] for p in result["facets"]["purposes"] if p["id"] == "motion")
        self.assertEqual(count, 1)

    def test_partial_alias_update_preserves_other_effective_manual_dimensions(self):
        first, second = self.model_pair()
        preview = self.request("POST", "/api/models/classify", {"ids": [first], "scope": "archive", "preview": True})
        after = preview["items"][0]["after"]
        self.assertEqual((after["domain"], after["purposes"], after["architecture"]), ("video", ["motion"], "ReviewedWan"))
        self.request("POST", "/api/models/classify", {"ids": [first], "scope": "archive"})
        result = self.detail(first)
        self.assertEqual((result["scope"], result["domain"], result["purposes"], result["architecture"]),
                         ("archive", "video", ["motion"], "ReviewedWan"))
        self.assertEqual(result, self.detail(second))

    def test_reset_from_primary_alias_clears_effective_manual_classification(self):
        first, second = self.model_pair()
        preview = self.request("POST", "/api/models/classify", {"ids": [first], "reset": True, "preview": True})
        expected = preview["items"][0]["after"]
        self.request("POST", "/api/models/classify", {"ids": [first], "reset": True})
        after = self.detail(first)
        self.assertEqual((after["manual_domain"], after["manual_purposes"], after["manual_architecture"]), (None, None, None))
        self.assertEqual(after["domain"], expected["domain"])
        self.assertEqual(after, self.detail(second))

    def test_replaced_alias_updates_and_reset_do_not_modify_the_other_file_labels(self):
        first, second = self.model_pair()
        self.request("POST", "/api/models/classify", {"ids": [first], "domain": "image", "purposes": ["style"]})
        primary = Path(self.db.one("SELECT path FROM models WHERE rowid_pk=?", (first,))[0])
        alias = Path(self.db.one("SELECT path FROM models WHERE rowid_pk=?", (second,))[0])
        self.db.upsert_model({"path": str(primary), "alt_paths": json.dumps([str(alias)])})
        replacement = primary.parent / "new-file.tmp"
        replacement.write_bytes(b"replacement has a different identity")
        os.replace(replacement, alias)
        self.assertFalse(primary.samefile(alias))
        before = self.detail(first)
        self.request("POST", "/api/models/classify", {"ids": [second], "domain": "audio", "architecture": "OtherArchitecture"})
        self.assertEqual(self.detail(first), before)
        self.assertEqual(self.detail(second)["domain"], "audio")
        second_label = dict(self.db.one("SELECT * FROM model_labels WHERE model_path=?", (str(alias),)))
        self.request("POST", "/api/models/classify", {"ids": [first], "reset": True})
        self.assertEqual(dict(self.db.one("SELECT * FROM model_labels WHERE model_path=?", (str(alias),))), second_label)
        self.assertIsNone(self.detail(first)["manual_domain"])
        self.assertEqual(self.detail(second)["architecture"], "OtherArchitecture")

    def test_model_filters_and_label_reset_leave_preferences_intact(self):
        self.db.upsert_model({"path": str(self.ai / "component.pt"), "filename": "component.pt", "mtype": "Private",
                              "rating": 8, "notes": "notes", "source_url": "https://example.com/component"})
        mid = self.db.one("SELECT rowid_pk FROM models")[0]
        before = copy.deepcopy(self.cfg)
        self.request("POST", "/api/models/classify", {"ids": [mid], "scope": "central", "model_role": "Detection", "domain": "vision", "architecture": "RecordedByUser"})
        rows = self.request("GET", "/api/models", params={"scope": "central", "type": "Detection", "family": "RecordedByUser"})
        self.assertEqual(rows["total"], 1)
        self.assertEqual(self.request("GET", "/api/models", params={"intake": "registered"})["total"], 0)
        self.request("POST", "/api/models/classify", {"ids": [mid], "reset": True})
        self.assertEqual(tuple(self.db.one("SELECT rating,notes,source_url,mtype FROM models")), (8, "notes", "https://example.com/component", "Private"))
        self.assertEqual(self.cfg, before)

    def test_legacy_unknown_architecture_filter_finds_unconfirmed_models(self):
        self.db.upsert_model({"path": str(self.ai / "unknown.pt"), "filename": "unknown.pt", "mtype": "Unknown"})
        result = self.request("GET", "/api/models", params={"family": "Unknown"})
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["classification"]["architecture"], "未确认")

    def test_project_registry_api_preview_save_restore_never_moves_assets(self):
        self.db.upsert_model({"path": "fixture", "rating": 7, "notes": "keep", "source_url": "https://example.com"})
        before = copy.deepcopy(self.cfg)
        doc = self.ai / "40_Projects" / "Film" / "项目说明.md"
        doc.parent.mkdir(parents=True)
        doc.write_text("# Project", encoding="utf-8")
        record = {"id": "film", "name": "Film", "type": "creative", "root": str(doc.parent), "current_doc": str(doc),
                  "delivery": str(doc.parent / "90_Delivery"), "template": {"id": "external"}}
        preview = self.request("POST", "/api/registry/preview", {"kind": "project", "record": record})
        self.assertFalse(self.data.exists())
        self.request("POST", "/api/registry/save", {"token": preview["token"]})
        projects = self.request("GET", "/api/projects")
        self.assertEqual(len(projects["items"]), 1)
        self.assertTrue(projects["items"][0]["registered"])
        edit = self.request("POST", "/api/registry/preview", {"kind": "project", "record": {**record, "name": "Revised"}})
        self.request("POST", "/api/registry/save", {"token": edit["token"]})
        backups = self.request("GET", "/api/registry/backups")
        restore = self.request("POST", "/api/registry/restore-preview", {"backup_id": backups["items"][0]["id"]})
        self.request("POST", "/api/registry/save", {"token": restore["token"]})
        self.assertEqual(self.request("GET", "/api/projects")["items"][0]["name"], "Film")
        self.assertFalse(Path(record["delivery"]).exists())
        self.assertEqual(doc.read_text(encoding="utf-8"), "# Project")
        self.assertEqual(tuple(self.db.one("SELECT rating,notes,source_url FROM models")), (7, "keep", "https://example.com"))
        self.assertEqual(self.cfg, before)


class MigrationFailureReview(unittest.TestCase):
    def test_failed_third_column_rolls_back_all_ddl_and_retains_verified_backup(self):
        class FailThirdColumn(sqlite3.Connection):
            fail_alter = False

            def execute(self, sql, *args, **kwargs):
                if self.fail_alter and sql == "ALTER TABLE model_labels ADD COLUMN architecture TEXT":
                    raise sqlite3.OperationalError("fixture interrupted migration")
                return super().execute(sql, *args, **kwargs)

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "legacy.sqlite"
            conn = sqlite3.connect(path, factory=FailThirdColumn)
            try:
                conn.executescript("CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT);"
                                   "CREATE TABLE models(path TEXT,rating INTEGER,notes TEXT);"
                                   "CREATE TABLE model_labels(model_path TEXT PRIMARY KEY,domain TEXT,purposes TEXT,updated_at TEXT);")
                conn.execute("INSERT INTO models VALUES('model',9,'keep notes')")
                conn.execute("INSERT INTO model_labels VALUES('model','video','[\"motion\"]','original')")
                conn.commit()
                conn.fail_alter = True
                with self.assertRaisesRegex(sqlite3.OperationalError, "interrupted"):
                    dbmod.migrate_labels(conn, path)
                self.assertEqual([r[1] for r in conn.execute("PRAGMA table_info(model_labels)")],
                                 ["model_path", "domain", "purposes", "updated_at"])
                self.assertEqual(conn.execute("SELECT rating,notes FROM models").fetchone(), (9, "keep notes"))
                self.assertIsNone(conn.execute("SELECT value FROM meta WHERE key='label_schema'").fetchone())
                backups = list((Path(folder) / "migrations").glob("*.sqlite"))
                self.assertEqual(len(backups), 1)
                backup = sqlite3.connect(backups[0])
                try:
                    self.assertEqual(backup.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                    self.assertEqual(backup.execute("SELECT domain,purposes FROM model_labels").fetchone(), ("video", '["motion"]'))
                finally:
                    backup.close()
            finally:
                conn.close()
