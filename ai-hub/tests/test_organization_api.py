import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from aihub import api, config, db as dbmod, jobs, organization, scan, images


class OrganizationAPI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.root = self.base / "Creative Assets"
        self.root.mkdir()
        self.data = self.base / "hub-data"
        self.data.mkdir()
        self.patches = [mock.patch.object(config, "DATA_DIR", str(self.data)),
                        mock.patch.object(config, "CONFIG_PATH", str(self.data / "config.json")),
                        mock.patch.object(config, "DB_PATH", str(self.data / "db.sqlite"))]
        for patch in self.patches: patch.start()
        self.db = dbmod.DB()
        self.cfg = config.default_config()
        self.original_app_cfg = api.APP_CFG
        api.APP_CFG = self.cfg

    def tearDown(self):
        api.APP_CFG = self.original_app_cfg
        self.db.conn.close()
        for patch in reversed(self.patches): patch.stop()
        self.tmp.cleanup()

    def request(self, method, path, body=None, expected=200):
        status, _, payload = api.dispatch(self.db, self.cfg, method, path, {}, body)
        data = json.loads(payload)
        self.assertEqual(status, expected, data)
        return data

    def setup_root(self, **kwargs):
        return self.request("POST", "/api/workspace/setup", {"root": str(self.root), **kwargs})

    @staticmethod
    def immediate(name, target, *args):
        target(*args)
        return {"name": name, "status": "done"}

    def test_setup_preserves_other_settings_and_does_not_organize(self):
        self.cfg["network"]["proxy"] = "http://localhost:8888"
        original = self.root / "sample.png"
        original.write_bytes(b"fixture")
        self.setup_root()
        self.assertFalse(self.cfg["organizer"]["on_startup"])
        self.assertEqual(self.cfg["network"]["proxy"], "http://localhost:8888")
        self.assertFalse((self.root / "00_AIHub_Library").exists())
        self.assertEqual(original.read_bytes(), b"fixture")
        self.assertTrue(self.request("GET", "/api/organizer/status")["workspace"]["available"])

    def test_create_new_workspace_and_wait_for_explicit_apply(self):
        self.root = self.base / "new workspace"
        self.setup_root(create=True)
        self.assertTrue((self.root / "20_Models").is_dir())
        self.assertTrue((self.root / "70_Output").is_dir())
        self.assertIsNone(self.request("GET", "/api/organizer/plan"))

    def test_end_to_end_preview_apply_undo_preserves_original(self):
        original = self.root / "fixture.png"
        original.write_bytes(b"FAKE IMAGE - never rendered")
        self.setup_root()
        with mock.patch.object(jobs, "start", side_effect=self.immediate):
            self.request("POST", "/api/organizer/preview", {})
            plan = self.request("GET", "/api/organizer/plan")
            self.assertEqual(len(plan["items"]), 1)
            self.assertFalse(Path(plan["items"][0]["target"]).exists())
            self.request("POST", "/api/organizer/apply", {"plan_id": plan["id"]})
            target = Path(plan["items"][0]["target"])
            self.assertTrue(target.samefile(original))
            runs = self.request("GET", "/api/organizer/status")["runs"]
            self.request("POST", "/api/organizer/undo", {"run_id": runs[0].get("id") or runs[0]["run_id"]})
            self.assertFalse(target.exists())
            self.assertEqual(original.read_bytes(), b"FAKE IMAGE - never rendered")

    def test_rejects_old_plan_after_root_changed(self):
        (self.root / "fixture.mp4").write_bytes(b"video")
        self.setup_root()
        with mock.patch.object(jobs, "start", side_effect=self.immediate):
            self.request("POST", "/api/organizer/preview", {})
        plan = self.request("GET", "/api/organizer/plan")
        self.root = self.base / "different-assets"
        self.root.mkdir()
        self.setup_root()
        self.request("POST", "/api/organizer/apply", {"plan_id": plan["id"]}, expected=400)

    def test_concurrent_scan_blocks_settings_and_apply(self):
        before = copy.deepcopy(self.cfg)
        with mock.patch.object(jobs, "running", side_effect=lambda name: name == "scan"):
            self.request("POST", "/api/workspace/setup", {"root": str(self.root)}, expected=409)
            self.request("POST", "/api/settings", {"ai_root": str(self.root)}, expected=409)
            self.request("POST", "/api/organizer/preview", {}, expected=409)
        self.assertEqual(self.cfg, before)

    def test_root_unavailable_pauses_scan_without_clearing_index(self):
        self.cfg["ai_root"] = str(self.root / "disconnected")
        self.cfg["scan_roots"] = [self.cfg["ai_root"]]
        with mock.patch.object(jobs, "run_full_pipeline") as run:
            self.request("POST", "/api/scan/start", {}, expected=400)
            run.assert_not_called()
        self.assertFalse(self.request("GET", "/api/overview")["workspace"]["available"])

    def test_startup_disabled_by_default_and_enabled_only_for_saved_root(self):
        self.setup_root()
        with mock.patch.object(jobs, "start") as start:
            self.assertFalse(organization.startup(self.db, self.cfg))
            start.assert_not_called()
        self.setup_root(on_startup=True)
        with mock.patch.object(jobs, "start", return_value={"status": "running"}) as start:
            self.assertTrue(organization.startup(self.db, self.cfg))
            self.assertEqual(start.call_args.args[0], "organize")
        self.cfg["ai_root"] = str(self.base / "missing")
        with mock.patch.object(jobs, "start") as start:
            self.assertFalse(organization.startup(self.db, self.cfg))
            start.assert_not_called()

    def test_bad_plan_id_and_invalid_input_are_rejected(self):
        self.setup_root()
        self.request("POST", "/api/organizer/apply", {"plan_id": "../config"}, expected=400)
        self.request("POST", "/api/organizer/undo", {"run_id": "../config"}, expected=400)
        self.request("POST", "/api/workspace/setup", {"root": str(self.root), "on_startup": "yes"}, expected=400)

    def test_scan_excludes_managed_library_and_app_state_but_keeps_root_files(self):
        self.setup_root()
        (self.root / "root.txt").write_text("asset")
        library = self.root / "00_AIHub_Library"
        library.mkdir()
        (library / "duplicate.txt").write_text("asset")
        app = self.root / "hub"
        app.mkdir()
        (app / "config.json").write_text("private")
        with mock.patch.object(config, "APP_DIR", str(app)):
            result = scan.scan_all(self.db, self.cfg)
        self.assertEqual(result["file_count"], 1)
        self.assertEqual(self.db.query("SELECT name FROM files")[0]["name"], "root.txt")

    def test_failed_save_does_not_change_live_config(self):
        before = copy.deepcopy(self.cfg)
        with mock.patch.object(config, "save_config", side_effect=OSError("fixture disk error")):
            self.request("POST", "/api/workspace/setup", {"root": str(self.root)}, expected=400)
        self.assertEqual(self.cfg, before)


if __name__ == "__main__":
    unittest.main()
