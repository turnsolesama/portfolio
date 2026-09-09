"""Identity/classification contracts use synthetic weights; no user assets."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from aihub import classification as c, meta, organizer as org, organization, scan
from test_aihub import Fixture


class StructureClassification(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "Assets"
        self.root.mkdir()
        self.app = self.base / "Hub"
        self.app.mkdir()

    def file(self, name, payload=b"not executable model data"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return path

    def test_unknown_role_does_not_invent_private_scope_or_architecture(self):
        path = self.file("20_Models/detection/face_yolov8m.pt")
        model = scan._model_row_from_fs(str(path), {"size": path.stat().st_size, "mtime": 0}, [str(path)])
        self.assertEqual((model["mtype"], model["scope"]), ("Detection", "central"))
        result = c.classify(model)
        self.assertEqual((result["model_role"], result["domain"], result["architecture"]), ("Detection", "vision", "未确认"))
        self.assertTrue(result["classification_pending"])
        legacy = c.classify({"path": str(self.root / "plain.pt"), "mtype": "Private"})
        self.assertEqual((legacy["model_role"], legacy["scope"]), ("Unknown", "unknown"))

    def test_manual_dimensions_independent_and_legacy_labels_supported(self):
        model = {"mtype": "Private", "path": str(self.root / "a.pt")}
        result = c.classify(model, manual={"scope": "archive", "model_role": "LoRA", "domain": "video",
                                          "purposes": '["motion"]', "architecture": "reviewed-family"})
        self.assertEqual((result["scope"], result["model_role"], result["domain"], result["purposes"]),
                         ("archive", "LoRA", "video", ["motion"]))
        self.assertEqual(result["architecture_source"], "manual")
        self.assertFalse(result["classification_pending"])
        old = c.classify({"mtype": "LoRA"}, manual={"domain": "image", "purposes": '["style"]'})
        self.assertEqual(old["purposes"], ["style"])

    def test_live_identity_unifies_browser_registration_and_manual_alias(self):
        source = self.file("20_Models/Runtime/loras/plain.pt")
        alias = self.root / "20_Models/Library/plain.pt"
        alias.parent.mkdir()
        os.link(source, alias)
        rows = [{"rowid_pk": 1, "path": str(source), "filename": source.name, "mtype": "LoRA"},
                {"rowid_pk": 2, "path": str(alias), "filename": alias.name, "mtype": "Private"}]
        catalog = {"models": [{"id": "stable-a", "canonical_path": str(alias), "family": "Wan2.2"}]}
        labels = [{"model_path": str(alias), "domain": "video", "purposes": '["motion"]'}]
        unique = c.deduplicate_models(rows)
        self.assertEqual(len(unique), 1)
        self.assertEqual(unique[0]["alias_rowids"], [1, 2])
        classes = c.decorate(rows, catalog, labels)
        self.assertEqual(classes[1], classes[2])
        self.assertTrue(classes[1]["registered"])
        self.assertEqual(classes[1]["registration_status"], "registered")
        context = c.classification_context(rows, catalog, labels)
        plan = org.build_plan(self.root, self.app, model_context=context)
        self.assertEqual(len(plan["items"]), 1)
        item = plan["items"][0]
        for field in ("scope", "model_role", "domain", "purposes", "architecture", "registered", "indexed"):
            self.assertEqual(item[field], classes[1][field], field)
        self.assertEqual(plan["strategy"], "existing_library_view")
        self.assertIsNone(item["target"])
        self.assertFalse((self.root / org.LIBRARY_NAME).exists())

    def test_catalog_id_must_exist_and_missing_identities_do_not_merge(self):
        rows = [{"rowid_pk": 1, "path": str(self.root / "one.pt"), "legacy_uid": "removed-id"},
                {"rowid_pk": 2, "path": str(self.root / "two.pt")}]
        self.assertEqual(len(c.deduplicate_models(rows)), 2)
        result = c.decorate(rows, {"models": []}, [])
        self.assertTrue(result[1]["indexed"])
        self.assertFalse(result[1]["registered"])
        self.assertEqual(result[1]["registration_status"], "indexed")

    def test_replaced_historical_alias_cannot_supply_labels_or_catalog_identity(self):
        source = self.file("20_Models/loras/a.pt")
        alias = source.with_name("z.pt")
        os.link(source, alias)
        replacement = self.file("replacement.pt", b"different identity")
        os.replace(replacement, alias)
        self.assertFalse(source.samefile(alias))
        missing = str(source.with_name("old-offline.pt"))
        rows = [{"rowid_pk": 1, "path": str(source), "filename": source.name, "mtype": "LoRA",
                 "alt_paths": json.dumps([str(alias), missing])}]
        labels = [{"model_path": str(alias), "domain": "video", "purposes": '["motion"]'}]
        catalog = {"models": [{"id": "stable-a", "canonical_path": str(source), "old_path": str(alias)}]}
        unique = c.deduplicate_models(rows)
        self.assertNotIn(str(alias), unique[0]["compatibility_paths"])
        self.assertIn(missing, unique[0]["compatibility_paths"])
        context = c.classification_context(rows, catalog, labels)
        original = c.classify(**c.context_for(context, source))
        replacement = c.classify(**c.context_for(context, alias))
        self.assertEqual(original["domain"], "unknown")
        self.assertTrue(original["registered"])
        self.assertEqual(replacement["domain"], "video")
        self.assertFalse(replacement["registered"])
        self.assertEqual(c.context_for(context, alias)["model"]["path"], str(alias))

    def test_stale_shared_catalog_uid_does_not_register_replaced_alias(self):
        source = self.file("20_Models/a.pt")
        other = self.file("20_Models/z.pt", b"distinct")
        catalog = {"models": [{"id": "same-old-id", "canonical_path": str(source), "old_path": str(other)}]}
        rows = [{"rowid_pk": 1, "path": str(source), "legacy_uid": "same-old-id"},
                {"rowid_pk": 2, "path": str(other), "legacy_uid": "same-old-id"}]
        result = c.decorate(rows, catalog, [])
        self.assertTrue(result[1]["registered"])
        self.assertFalse(result[2]["registered"])

    def test_existing_library_blocks_forged_plan_and_startup(self):
        self.file("plain.pt")
        portable = org.build_plan(self.root, self.app)
        (self.root / "20_Models").mkdir()
        with self.assertRaisesRegex(ValueError, "已有模型库"):
            org.apply_plan(portable, self.app / "runs")
        cfg = {"ai_root": str(self.root), "organizer": {"enabled": True, "on_startup": True, "root": str(self.root)}}
        with mock.patch.object(organization.jobs, "start") as start:
            self.assertFalse(organization.startup(None, cfg))
            start.assert_not_called()
        self.assertFalse((self.root / org.LIBRARY_NAME).exists())

    def test_portable_manual_classification_applies_and_stale_labels_reject(self):
        source = self.file("loras/plain.pt")
        rows = [{"rowid_pk": 1, "path": str(source), "filename": source.name, "mtype": "LoRA"}]
        labels = [{"model_path": str(source), "domain": "image", "purposes": '["lighting"]'}]
        context = c.classification_context(rows, {}, labels)
        plan = org.build_plan(self.root, self.app, model_context=context)
        self.assertEqual(plan["items"][0]["category"], "01_Models/image/LoRA/lighting")
        changed = c.classification_context(rows, {}, [{**labels[0], "domain": "video"}])
        stale = org.apply_plan(plan, self.app / "runs", model_context=changed)
        self.assertEqual(stale["created"], 0)
        self.assertEqual(stale["skipped"], 1)
        result = org.apply_plan(plan, self.app / "runs", model_context=context)
        self.assertEqual(result["created"], 1)
        self.assertEqual(org.undo_run(result["id"], self.app / "runs", self.root)["removed"], 1)

    def test_indexed_package_is_virtual_without_reading_config_or_pickle(self):
        source = self.file("20_Models/Packages/Pipeline/pytorch_model.bin")
        self.file("20_Models/Packages/Pipeline/config.json", b'{"private":"do not read"}')
        self.file("20_Models/Packages/Pipeline/tokenizer.json", b'{}')
        rows = [{"rowid_pk": 1, "path": str(source), "filename": source.name, "mtype": "Package"}]
        context = c.classification_context(rows)
        with mock.patch("pickle.load", side_effect=AssertionError("must not execute")):
            plan = org.build_plan(self.root, self.app, model_context=context)
        self.assertEqual(len(plan["items"]), 1)
        self.assertEqual(plan["items"][0]["model_role"], "Package")
        self.assertIsNone(plan["items"][0]["target"])


class ScanIdentity(Fixture):
    def test_scan_groups_each_identity_once_and_does_not_repeat_catalog_alias(self):
        runtime = self.ai / "20_Models" / "Runtime" / "detection"
        runtime.mkdir(parents=True)
        first = runtime / "one.pt"
        second = runtime / "two.pt"
        first.write_bytes(b"fixture-one")
        second.write_bytes(b"fixture-two-distinct")
        library = self.ai / "20_Models" / "Library"
        library.mkdir()
        alias = library / "one.pt"
        os.link(first, alias)
        self.write_json("Catalogs/models.json", {"models": [{"id": "one", "canonical_path": str(alias), "category": "Detection"}]})
        result = scan.scan_all(self.db, self.cfg)
        self.assertEqual(len(result["model_groups"]), 2)
        paths = [p for group in result["model_groups"].values() for p in group["paths"]]
        self.assertEqual(len(paths), 3)
        self.assertEqual(len(paths), len(set(paths)))
        built = scan.build_models(self.db, self.cfg, result)
        self.assertEqual((built["catalog"], built["filesystem"]), (1, 1))
        self.assertEqual(self.db.one("SELECT COUNT(*) n FROM models")["n"], 2)


if __name__ == "__main__":
    unittest.main()
