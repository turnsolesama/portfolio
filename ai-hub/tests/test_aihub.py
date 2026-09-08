import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import tempfile
import unittest
from unittest import mock
import zlib

from aihub import api, config, db as dbmod, images, management, meta
import server

loader = importlib.machinery.SourceFileLoader("aihub_launcher", str(Path(__file__).resolve().parents[1] / "launcher.pyw"))
spec = importlib.util.spec_from_loader(loader.name, loader)
launcher = importlib.util.module_from_spec(spec)
loader.exec_module(launcher)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.gettempdir()) / "aihub-test-fixtures"
        self.base.mkdir(exist_ok=True)
        self.folder = Path(tempfile.mkdtemp(dir=self.base)).resolve()
        self.folder.relative_to(self.base.resolve())
        self.ai = self.folder / "AI"
        self.mg = self.ai / "00_Management"
        (self.mg / "Catalogs").mkdir(parents=True)
        self.cfg = {"ai_root": str(self.ai), "catalog_dir": str(self.mg / "Catalogs"), "scan_roots": [str(self.ai)], "output_roots": []}
        self.previous_config = config.DB_PATH
        config.DB_PATH = str(self.folder / "test.db")
        self.db = dbmod.DB()

    def tearDown(self):
        self.db.conn.close()
        config.DB_PATH = self.previous_config
        self.folder.resolve().relative_to(self.base.resolve())
        shutil.rmtree(self.folder)

    def write_json(self, relative, value):
        path = self.mg / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")
        return path


class Assets(Fixture):
    def test_catalog_counts_do_not_mix_training_with_central_lora(self):
        self.write_json("Catalogs/models.json", {"updated_at": "snapshot", "models": [
            {"scope": "central", "category": "Checkpoint", "family": "SDXL"},
            {"scope": "central", "category": "LoRA", "family": "SDXL"},
            {"scope": "training", "category": "LoRA-Training", "family": "SDXL"}]})
        result = management.overview(self.cfg)
        self.assertEqual((result["catalog_records"], result["base_count"], result["lora_count"]), (3, 1, 1))
        self.assertIsNone(result["check"]["status"])

    def test_scan_preserves_user_rating_notes_and_version_state(self):
        self.db.upsert_model({"path": "weight", "filename": "weight", "rating": 8, "notes": "user text", "update_state": "available", "added_at": "original"})
        self.db.upsert_model({"path": "weight", "filename": "renamed", "update_state": "unchecked"})
        row = self.db.model_by_path("weight")
        self.assertEqual((row["rating"], row["notes"], row["update_state"], row["added_at"]), (8, "user text", "available", "original"))

    def test_ambiguous_basenames_do_not_select_an_arbitrary_model(self):
        for name, inode in (("first", "11"), ("second", "22")):
            self.db.upsert_model({"path": f"C:\\weights\\{name}\\style.safetensors", "filename": "style.safetensors", "inode": inode, "scope": "central", "missing": 0})
        index = self.db.model_index_by_name()
        self.assertNotIn("style.safetensors", index)
        self.assertEqual(index["first\\style.safetensors"], "C:\\weights\\first\\style.safetensors")

    def test_settings_save_does_not_clear_the_live_shared_config(self):
        old = api.APP_CFG
        api.APP_CFG = self.cfg
        try:
            with mock.patch.object(config, "save_config") as save:
                status, _, _ = api.settings_post(self.db, self.cfg, {}, {"ignore_dirs": ["cache"]})
            self.assertEqual(status, 200)
            self.assertEqual(self.cfg["ai_root"], str(self.ai))
            self.assertEqual(self.cfg["ignore_dirs"], ["cache"])
            save.assert_called_once()
        finally:
            api.APP_CFG = old

    def test_generated_report_can_be_read_but_unlisted_config_cannot(self):
        reports = self.folder / "reports"
        reports.mkdir()
        report = reports / "result.md"
        report.write_text("# A report", encoding="utf-8")
        private = self.ai / "private.json"
        private.write_text('{}')
        with mock.patch.object(config, "REPORTS_DIR", str(reports)):
            self.assertEqual(api.report_content(self.db, self.cfg, {"path": str(report)}, None)[0], 200)
            self.assertEqual(api.report_content(self.db, self.cfg, {"path": str(private)}, None)[0], 403)

    def test_favorites_empty_list_does_not_return_all_models(self):
        self.db.upsert_model({"path": "one", "filename": "one", "mtype": "LoRA", "scope": "central"})
        result = json.loads(api.models_list(self.db, self.cfg, {"ids": ""}, None)[2])
        self.assertEqual(result["total"], 0)

    def test_header_training_metadata_is_visible_before_rescan(self):
        record = api._row_json({"path": "one", "header_meta": json.dumps({"ss_sd_model_name": "base", "ss_network_dim": "64", "ss_network_alpha": "1"})})
        self.assertEqual((record["training_base"], record["lrank"], record["lalpha"]), ("base", "64", "1"))

    def test_workflow_review_is_not_reported_as_inference(self):
        self.write_json("Catalogs/workflows.json", [{"path": "old.json", "missing_models": ["old/path.safetensors"]}])
        self.write_json("Catalogs/workflow_path_review.json", {"copies": [{"source": "old.json", "reviewed_copy": "fixed.json", "changes": [{"from": "a", "to": "b"}]}]})
        result = management.workflows(self.cfg)["items"][0]
        self.assertEqual(result["status"], "reviewed_copy")
        self.assertEqual(result["generation_status"], "not_run")
        self.assertFalse(result["copy_exists"])


class Graphs(unittest.TestCase):
    def test_subfolder_lora_is_counted_only_on_output_ancestors(self):
        graph = {"1": {"class_type": "LoraLoader", "inputs": {"lora_name": "styles\\a.safetensors"}},
                 "2": {"class_type": "UnusedLoader", "inputs": {"lora_name": "unused.safetensors"}},
                 "3": {"class_type": "SaveImage", "inputs": {"images": ["1", 0]}}}
        refs = meta.extract_refs_from_graph(graph)
        self.assertEqual(refs, [{"filename": "a.safetensors", "reference": "styles\\a.safetensors", "role": "LoRA"}])

    def test_sampler_in_disconnected_branch_is_excluded(self):
        graph = {"1": {"class_type": "KSampler", "inputs": {"steps": 10, "sampler_name": "active"}},
                 "2": {"class_type": "KSampler", "inputs": {"steps": 50, "sampler_name": "unused"}},
                 "3": {"class_type": "SaveImage", "inputs": {"images": ["1", 0]}}}
        self.assertEqual(meta.extract_sampler_from_graph(graph)["sampler"], "active")

    def test_disabled_nodes_and_non_graph_inputs_are_safe(self):
        self.assertEqual(meta.extract_refs_from_graph([]), [])
        self.assertEqual(meta.extract_refs_from_graph({"1": {"mode": 2, "inputs": {"lora_name": "skip.safetensors"}}}), [])
        malformed = {"1": {"class_type": "KSampler", "inputs": ["not", "an", "API graph"]}}
        self.assertEqual(meta.extract_refs_from_graph(malformed), [])
        self.assertEqual(meta.extract_sampler_from_graph(malformed), {})


class Images(Fixture):
    @staticmethod
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)

    def test_png_reads_later_text_blocks_after_crc(self):
        path = self.folder / "multi.png"
        path.write_bytes(b"\x89PNG\r\n\x1a\n" + self.chunk(b"tEXt", b"note\0first") + self.chunk(b"tEXt", b"prompt\0{}") + self.chunk(b"IEND", b""))
        self.assertEqual(meta.parse_png_metadata(str(path)), {"note": "first", "prompt": "{}"})

    def test_png_international_and_compressed_text(self):
        path = self.folder / "international.png"
        text = "中文元数据".encode("utf-8")
        path.write_bytes(b"\x89PNG\r\n\x1a\n" + self.chunk(b"iTXt", b"plain\0\0\0zh\0title\0" + text)
                         + self.chunk(b"iTXt", b"compressed\0\1\0\0\0" + zlib.compress(text))
                         + self.chunk(b"zTXt", b"legacy\0\0" + zlib.compress(b"metadata")) + self.chunk(b"IEND", b""))
        self.assertEqual(meta.parse_png_metadata(str(path)), {"plain": "中文元数据", "compressed": "中文元数据", "legacy": "metadata"})

    def png(self, path, graph):
        def chunk(kind, data):
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
        path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) + chunk(b"tEXt", b"prompt\0" + json.dumps(graph).encode()) + chunk(b"IEND", b""))

    def test_incremental_unknown_refs_persist_and_removed_refs_are_cleared(self):
        folder = self.folder / "output"
        folder.mkdir()
        image = folder / "sample.png"
        self.cfg["output_roots"] = [str(folder)]
        self.png(image, {"1": {"class_type": "LoraLoader", "inputs": {"lora_name": "missing.safetensors"}}})
        images.run_image_scan(self.db, self.cfg)
        self.assertEqual(len(json.loads(self.db.get_meta("ghost_refs"))), 1)
        images.run_image_scan(self.db, self.cfg)
        self.assertEqual(len(json.loads(self.db.get_meta("ghost_refs"))), 1)
        self.png(image, {})
        images.run_image_scan(self.db, self.cfg)
        self.assertEqual(self.db.one("SELECT COUNT(*) n FROM img_refs")["n"], 0)


class Startup(Fixture):
    def test_existing_service_is_reused_without_spawning(self):
        with mock.patch.object(launcher, "health", return_value={"app": "ai-hub"}), mock.patch.object(launcher.subprocess, "Popen") as spawn:
            self.assertEqual(launcher.ensure_running(8888)["status"], "reused")
            spawn.assert_not_called()


    def test_new_service_uses_no_window_and_writes_pid(self):
        kernel = mock.Mock()
        proc = mock.Mock(pid=1234)
        with mock.patch.object(launcher, "ROOT", self.folder), mock.patch.object(launcher, "DATA", self.folder), \
             mock.patch.object(launcher, "health", side_effect=[None, None, {"app": "ai-hub"}]), \
             mock.patch.object(launcher, "port_busy", return_value=False), \
             mock.patch.object(launcher, "acquire_mutex", return_value=(kernel, 9, True)), \
             mock.patch.object(launcher.subprocess, "Popen", return_value=proc) as spawn:
            result = launcher.ensure_running(8888)
            self.assertEqual(result["status"], "started")
            self.assertTrue(spawn.call_args.kwargs["creationflags"] & launcher.subprocess.CREATE_NO_WINDOW)
            self.assertEqual(json.loads((self.folder / "server.pid.json").read_text())["pid"], 1234)
            kernel.ReleaseMutex.assert_called_once_with(9)

    def test_busy_port_does_not_spawn_or_terminate_another_service(self):
        with mock.patch.object(launcher, "health", return_value=None), \
             mock.patch.object(launcher, "acquire_mutex", return_value=(mock.Mock(), 9, True)), \
             mock.patch.object(launcher, "port_busy", return_value=True), \
             mock.patch.object(launcher.subprocess, "Popen") as spawn:
            with self.assertRaisesRegex(RuntimeError, "占用"):
                launcher.ensure_running(8888)
            spawn.assert_not_called()


class StaticPaths(unittest.TestCase):
    def test_encoded_traversal_and_other_drive_are_denied(self):
        handler = object.__new__(server.Handler)
        handler._send = mock.Mock()
        for path in ("%2e%2e/server.py", "F:/outside.css"):
            handler._send_file(path)
            self.assertEqual(handler._send.call_args.args[0], 404)


if __name__ == "__main__":
    unittest.main()
