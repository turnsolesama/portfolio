import copy
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest import mock

from aihub import organizer as org


class Organizer(unittest.TestCase):
    """Only synthetic fixtures; never load this computer's AI assets/config."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aihub-organizer-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "Assets"
        self.root.mkdir()
        self.app = self.base / "HubApp"
        self.app.mkdir()
        self.journal = self.app / "organizer-runs"

    def file(self, relative, data=b"fixture", root=None):
        path = (root or self.root) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def model(self, relative, metadata):
        header = json.dumps({"__metadata__": metadata}).encode()
        return self.file(relative, struct.pack("<Q", len(header)) + header)

    def plan(self, **kwargs):
        return org.build_plan(str(self.root), str(self.app), **kwargs)

    def apply(self, plan=None):
        return org.apply_plan(plan or self.plan(), str(self.journal))

    def test_validate_rejects_root_home_relative_network_missing_and_file(self):
        bad = [Path(self.root.anchor), Path.home(), Path.home().parent, "relative", "\\\\server\\share",
               self.root / "missing", self.file("image.png")]
        for path in bad:
            with self.subTest(path=str(path)), self.assertRaises(ValueError):
                org.validate_root(path)
        self.assertEqual(org.validate_root(self.root), str(self.root))

    def test_system_directory_and_generated_library_cannot_be_roots(self):
        system = self.base / "System"
        (system / "child").mkdir(parents=True)
        library = self.root / org.LIBRARY_NAME / "child"
        library.mkdir(parents=True)
        with mock.patch.dict(os.environ, {"WINDIR": str(system)}):
            for path in (system, system / "child", library):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    org.validate_root(path)

    def test_plan_is_read_only_and_recognizes_media_and_documents(self):
        for filename in ("image.png", "clip.mp4", "voice.wav", "manual.pdf"):
            self.file(filename)
        self.file("unknown.exe")
        plan = self.plan()
        self.assertEqual(plan["summary"]["planned"], 4)
        self.assertEqual(plan["summary"]["unknown"], 1)
        self.assertEqual({x["category"] for x in plan["items"]}, set(org._MEDIA_CATS.values()) - {"05_Workflows"})
        self.assertFalse((self.root / org.LIBRARY_NAME).exists())
        self.assertFalse(self.journal.exists())

    def test_model_function_and_architecture_remain_independent(self):
        self.model("loras/brush_style.safetensors", {"modelspec.architecture": "sdxl_base_v1-0/lora"})
        self.model("loras/camera_motion.safetensors", {"modelspec.architecture": "Wan2.2/lora"})
        self.file("plain.safetensors", b"not a serialized payload")
        plan = self.plan()
        rows = {Path(item["source"]).name: item for item in plan["items"]}
        self.assertEqual(rows["brush_style.safetensors"]["category"], "01_Models/image/LoRA/style")
        self.assertEqual(rows["camera_motion.safetensors"]["category"], "01_Models/video/LoRA/motion")
        self.assertEqual(rows["plain.safetensors"]["category"], "01_Models/unknown/Unknown")
        self.assertEqual(rows["brush_style.safetensors"]["architecture"], "sdxl_base_v1-0/lora")
        self.assertEqual(rows["plain.safetensors"]["architecture"], "未确认")

    def test_pickle_extensions_are_never_deserialized(self):
        self.file("weights.ckpt", b"malicious pickle-like fixture")
        self.file("loras/model.pt", b"pickle fixture")
        with mock.patch("pickle.load", side_effect=AssertionError("must not deserialize")):
            self.assertEqual(self.plan()["summary"]["planned"], 2)

    def test_json_requires_workflow_structure(self):
        self.file("flow.json", json.dumps({"nodes": [{"id": 1, "type": "SaveImage"}], "links": []}).encode())
        self.file("api.json", json.dumps({"1": {"class_type": "SaveImage", "inputs": {}}}).encode())
        self.file("random.json", b'{"account":"private fixture"}')
        self.file("auth.json", b'{"1":{"class_type":"SaveImage","inputs":{}}}')
        self.assertEqual({Path(item["source"]).name for item in self.plan()["items"]}, {"flow.json", "api.json"})

    def test_app_projects_environments_training_and_private_files_are_excluded(self):
        for folder in ("10_Apps", "AI_Apps", ".venv", "node_modules", "training", "datasets", "Library", "data", "backups"):
            self.file(folder + "/photo.png")
        self.file("project-like/package.json", b"{}")
        self.file("project-like/photo.png")
        self.file("captions/photo.png")
        self.file("captions/photo.txt")
        self.file("model-pack/config.json", b"{}")
        self.file("model-pack/model.safetensors")
        self.file("passwords.pdf")
        self.file("api-key.txt")
        self.file(".hidden.png")
        self.file("private/report.pdf")
        self.app = self.root / "MyHub"
        self.file("photo.png", root=self.app)
        self.file("allowed/photo.png")
        self.assertEqual([Path(item["source"]).name for item in self.plan()["items"]], ["photo.png"])
        self.assertIn("allowed", self.plan()["items"][0]["source"])

    def test_ignore_subtree_and_maximum_counts_empty_directories(self):
        self.file("skip/photo.png")
        self.file("keep/photo.png")
        plan = self.plan(ignore_dirs=("skip",))
        self.assertEqual(len(plan["items"]), 1)
        for i in range(10):
            (self.root / ("empty-" + str(i))).mkdir()
        with mock.patch.object(org, "MAX_TRAVERSED_ENTRIES", 3):
            plan = self.plan(max_files=3)
        self.assertTrue(plan["warnings"])
        self.assertTrue(plan["summary"]["traversal_limited"])
        self.assertEqual(plan["summary"]["planned"], 0)
        for limit in (0, -1, True, 50001):
            with self.assertRaises(ValueError):
                self.plan(max_files=limit)

    def test_new_candidate_budget_advances_across_repeated_runs(self):
        for number in range(5):
            self.file(f"photo-{number}.png")
        first = self.plan(max_files=2)
        self.assertEqual((len(first["items"]), first["summary"]["candidate_limited"]), (2, True))
        self.assertEqual(self.apply(first)["created"], 2)
        second = self.plan(max_files=2)
        self.assertEqual((len(second["items"]), second["summary"]["already_linked"]), (2, 2))
        self.assertEqual(self.apply(second)["created"], 2)
        third = self.plan(max_files=2)
        self.assertEqual((len(third["items"]), third["summary"]["already_linked"]), (1, 4))
        self.assertFalse(third["summary"]["candidate_limited"])
        self.assertEqual(self.apply(third)["created"], 1)
        self.assertEqual(self.plan(max_files=2)["summary"]["already_linked"], 5)
        planned_sources = [item["source"] for plan in (first, second, third) for item in plan["items"]]
        self.assertEqual(len(set(planned_sources)), 5)

    def test_unknown_and_excluded_entries_do_not_consume_candidate_budget(self):
        for number in range(5):
            self.file(f"a-{number}.unknown")
            self.file(f"b-{number}-password.txt")
            (self.root / f"c-empty-{number}").mkdir()
        self.file("z-photo.png")
        plan = self.plan(max_files=1)
        self.assertEqual(len(plan["items"]), 1)
        self.assertEqual(Path(plan["items"][0]["source"]).name, "z-photo.png")
        self.assertFalse(plan["summary"]["candidate_limited"])
        self.assertFalse(plan["summary"]["traversal_limited"])

    def test_truncated_directory_is_not_mistaken_for_loose_assets(self):
        # The cutoff lands before the caption marker. Partial enumeration must
        # not classify even the preceding image from this training package.
        self.file("photo.png")
        self.file("photo.txt")
        with mock.patch.object(org, "MAX_TRAVERSED_ENTRIES", 1):
            plan = self.plan(max_files=1)
        self.assertEqual(plan["items"], [])
        self.assertTrue(plan["summary"]["traversal_limited"])
        self.assertIn("整体跳过", plan["warnings"][0])

    def test_package_check_is_complete_even_with_small_candidate_budget(self):
        self.file("photo.png")
        self.file("photo.txt")
        plan = self.plan(max_files=1)
        self.assertEqual(plan["items"], [])
        self.assertFalse(plan["summary"]["candidate_limited"])

    @unittest.skipUnless(os.name == "nt", "Windows paths are case-insensitive")
    def test_app_exclusion_is_case_insensitive_on_windows(self):
        self.app = self.root / "MyHub"
        self.file("photo.png", root=self.app)
        self.assertEqual(org.build_plan(str(self.root), str(self.app).swapcase())["items"], [])

    def test_hardlinks_preserve_sources_deduplicate_and_undo(self):
        source = self.file("original/photo.png", b"source content")
        stamp = org._stamp(source.stat())
        plan = self.plan()
        result = self.apply(plan)
        target = Path(plan["items"][0]["target"])
        self.assertEqual((result["created"], result["errors"]), (1, []))
        self.assertTrue(os.path.samefile(source, target))
        self.assertEqual(stamp, org._stamp(source.stat()))
        second = self.plan()
        self.assertEqual((len(second["items"]), second["summary"]["already_linked"]), (0, 1))
        runs = org.list_runs(str(self.journal), str(self.root))
        self.assertEqual(runs[0]["id"], result["run_id"])
        undo = org.undo_run(result["run_id"], str(self.journal), str(self.root))
        self.assertEqual(undo["removed"], 1)
        self.assertEqual(source.read_bytes(), b"source content")
        self.assertFalse(target.exists())
        self.assertEqual(org.list_runs(str(self.journal), str(self.root))[0]["status"], "undone")

    def test_same_name_files_have_distinct_stable_targets(self):
        self.file("one/image.png")
        self.file("two/image.png")
        first, second = self.plan(), self.plan()
        targets = [row["target"] for row in first["items"]]
        self.assertEqual(len(set(targets)), 2)
        self.assertEqual(targets, [row["target"] for row in second["items"]])

    def test_existing_targets_are_never_overwritten(self):
        self.file("source.png")
        plan = self.plan()
        target = Path(plan["items"][0]["target"])
        target.parent.mkdir(parents=True)
        target.write_bytes(b"existing independent file")
        result = self.apply(plan)
        self.assertEqual((result["created"], result["skipped"]), (0, 1))
        self.assertEqual(target.read_bytes(), b"existing independent file")
        self.assertEqual(self.plan()["summary"]["planned"], 0)

    def test_changed_or_replaced_source_is_skipped(self):
        source = self.file("source.png")
        plan = self.plan()
        source.write_bytes(b"changed source")
        self.assertEqual(self.apply(plan)["created"], 0)
        plan = self.plan()
        source.unlink()
        source.write_bytes(b"replacement")
        self.assertEqual(self.apply(plan)["created"], 0)

    def test_root_identity_is_revalidated(self):
        self.file("source.png")
        plan = self.plan()
        plan["root_identity"]["ino"] += 1
        with self.assertRaises(ValueError):
            self.apply(plan)

    def test_forged_source_target_category_and_protected_file_are_rejected(self):
        self.file("source.png")
        outside = self.file("outside.png", root=self.base)
        plan = self.plan()
        edits = [{"target": str(self.base / "outside.png")}, {"source": str(outside)},
                 {"category": "../../outside"}, {"target": str(self.root / org.LIBRARY_NAME / ".." / "escape.png")}]
        for change in edits:
            bad = copy.deepcopy(plan)
            bad["items"][0].update(change)
            with self.subTest(change=change):
                self.assertEqual(self.apply(bad)["created"], 0)
        executable = self.file("program.exe")
        bad = copy.deepcopy(plan)
        row = bad["items"][0]
        row.update(source=str(executable), **org._stamp(executable.stat()))
        row["target"] = str(org._target(self.root, executable, row["category"]))
        self.assertEqual(self.apply(bad)["created"], 0)

    def test_apply_keeps_app_dir_exclusion_and_new_project_markers(self):
        source = self.file("source.png")
        plan = self.plan()
        plan["app_dir"] = str(self.root)
        self.assertEqual(self.apply(plan)["created"], 0)
        plan = self.plan()
        self.file("package.json", b"{}")
        self.assertEqual(self.apply(plan)["created"], 0)
        self.assertTrue(source.exists())

    def test_source_in_library_cannot_be_forged_back_into_plan(self):
        self.file("source.png")
        plan = self.plan()
        forged = self.file(org.LIBRARY_NAME + "/hidden.png")
        row = plan["items"][0]
        row.update(source=str(forged), **org._stamp(forged.stat()))
        row["target"] = str(org._target(self.root, forged, row["category"]))
        self.assertEqual(self.apply(plan)["created"], 0)

    def test_reparse_attribute_on_root_or_ancestor_is_rejected(self):
        real_lstat = os.lstat
        info = real_lstat(self.root)
        fake = mock.Mock(st_mode=info.st_mode, st_file_attributes=0x400)
        for reparse in (self.root, self.root.parent):
            def guarded(path, *args, **kwargs):
                return fake if Path(path) == reparse else real_lstat(path, *args, **kwargs)
            with self.subTest(reparse=reparse), mock.patch.object(org.os, "lstat", side_effect=guarded):
                with self.assertRaises(ValueError):
                    org.validate_root(self.root)

    def _symlink(self, target, link, directory=False):
        try:
            os.symlink(target, link, target_is_directory=directory)
        except OSError as exc:
            self.skipTest("This Windows test account cannot create symbolic links: " + str(exc.winerror if hasattr(exc, "winerror") else exc.errno))
        self.addCleanup(lambda: link.unlink() if link.is_symlink() else None)

    def test_real_directory_symlinks_are_not_followed(self):
        external = self.base / "external"
        self.file("private.png", root=external)
        link = self.root / "linked-dir"
        self._symlink(external, link, True)
        self.assertEqual(self.plan()["summary"]["planned"], 0)
        with self.assertRaises(ValueError):
            org.validate_root(link)

    def test_real_file_symlinks_are_not_classified(self):
        external = self.file("external.png", root=self.base)
        self._symlink(external, self.root / "link.png")
        self.assertEqual(self.plan()["summary"]["planned"], 0)

    def _junction(self, target, link):
        if os.name != "nt":
            self.skipTest("NTFS junctions are Windows-specific")
        # Creation only. Cleanup is os.rmdir of this exact temporary link,
        # never a recursive command and never traversal of its target.
        result = subprocess.run(["cmd", "/d", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
        if result.returncode:
            self.skipTest("This fixture filesystem does not support junction creation")
        self.addCleanup(lambda: os.rmdir(link) if os.path.lexists(link) else None)

    def test_real_junction_directory_and_root_do_not_escape(self):
        external = self.base / "external"
        self.file("photo.png", root=external)
        link = self.root / "joined-assets"
        self._junction(external, link)
        self.assertEqual(self.plan()["summary"]["planned"], 0)
        with self.assertRaises(ValueError):
            org.validate_root(link)
        child = external / "child"
        child.mkdir()
        with self.assertRaises(ValueError):
            org.validate_root(link / "child")

    def test_real_junction_swap_cannot_create_outside_safe_root(self):
        self.file("source.png")
        plan = self.plan()
        external = self.base / "external"
        external.mkdir()
        self._junction(external, self.root / org.LIBRARY_NAME)
        self.assertEqual(self.apply(plan)["created"], 0)
        self.assertEqual(list(external.iterdir()), [])

    def test_real_junction_source_swap_is_rejected(self):
        source = self.file("original/source.png")
        plan = self.plan()
        original = source.parent
        # Both source and the destination below are exclusively temporary fixtures.
        moved = self.base / "original-moved"
        original.rename(moved)
        self._junction(moved, original)
        self.assertEqual(self.apply(plan)["created"], 0)
        self.assertTrue((moved / "source.png").exists())

    def test_file_reparse_attribute_is_rejected_at_apply_and_undo(self):
        self.file("source.png")
        plan = self.plan()
        row = plan["items"][0]
        real_lstat = os.lstat
        def reparse_stat(path, *args, **kwargs):
            info = real_lstat(path, *args, **kwargs)
            if Path(path) == Path(row["source"]):
                return mock.Mock(st_mode=info.st_mode, st_file_attributes=0x400)
            return info
        with mock.patch.object(org.os, "lstat", side_effect=reparse_stat):
            self.assertEqual(self.apply(plan)["created"], 0)
        result = self.apply(plan)
        with mock.patch.object(org.os, "lstat", side_effect=reparse_stat):
            self.assertEqual(org.undo_run(result["run_id"], str(self.journal), str(self.root))["removed"], 0)
        self.assertTrue(Path(row["target"]).exists())

    def test_destination_reparse_swap_is_rejected_after_preview(self):
        self.file("source.png")
        plan = self.plan()
        external = self.base / "external"
        external.mkdir()
        self._symlink(external, self.root / org.LIBRARY_NAME, True)
        result = self.apply(plan)
        self.assertEqual(result["created"], 0)
        self.assertEqual(list(external.iterdir()), [])

    def test_concurrent_run_is_rejected_without_source_changes(self):
        source = self.file("source.png")
        plan = self.plan()
        with org._lock(str(self.journal)):
            with self.assertRaisesRegex(ValueError, "正在执行"):
                self.apply(plan)
        self.assertEqual(source.read_bytes(), b"fixture")

    def test_changed_link_contents_and_replaced_target_are_not_undone(self):
        self.file("one.png")
        self.file("two.png")
        plan = self.plan()
        result = self.apply(plan)
        one, two = [Path(row["target"]) for row in plan["items"]]
        one.write_bytes(b"edited shared content")
        two.unlink()
        two.write_bytes(b"new independent target")
        undone = org.undo_run(result["run_id"], str(self.journal), str(self.root))
        self.assertEqual((undone["removed"], undone["skipped"]), (0, 2))
        self.assertTrue(one.exists())
        self.assertEqual(two.read_bytes(), b"new independent target")
        self.assertTrue(all(Path(row["source"]).exists() for row in plan["items"]))

    def test_missing_source_keeps_target_and_missing_target_is_idempotent(self):
        source = self.file("source.png")
        plan = self.plan()
        result = self.apply(plan)
        target = Path(plan["items"][0]["target"])
        source.unlink()
        undone = org.undo_run(result["run_id"], str(self.journal), str(self.root))
        self.assertEqual(undone["removed"], 0)
        self.assertTrue(target.exists())

    def test_interrupted_run_can_recover_after_link_before_created_record(self):
        self.file("source.png")
        plan = self.plan()
        append = org._append
        def fail_created(handle, event):
            if event["event"] == "created":
                raise KeyboardInterrupt("synthetic crash")
            append(handle, event)
        with mock.patch.object(org, "_append", side_effect=fail_created), self.assertRaises(KeyboardInterrupt):
            self.apply(plan)
        runs = org.list_runs(str(self.journal), str(self.root))
        self.assertEqual(runs[0]["status"], "interrupted")
        self.assertEqual(org.undo_run(runs[0]["run_id"], str(self.journal), str(self.root))["removed"], 1)
        self.assertTrue(Path(plan["items"][0]["source"]).exists())

    def test_bad_run_ids_and_other_root_cannot_undo(self):
        self.file("source.png")
        result = self.apply()
        for value in ("../outside", "x" * 32, "", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                org.undo_run(value, str(self.journal), str(self.root))
        other = self.base / "other"
        other.mkdir()
        self.assertEqual(org.list_runs(str(self.journal), str(other)), [])
        with self.assertRaises(ValueError):
            org.undo_run(result["run_id"], str(self.journal), str(other))

    def test_competing_link_creation_is_not_owned_or_undone(self):
        source = self.file("source.png")
        plan = self.plan()
        target = Path(plan["items"][0]["target"])
        link = os.link
        def competitor(src, dst, **kwargs):
            link(src, dst, **kwargs)
            raise FileExistsError("another process created this entry")
        with mock.patch.object(org.os, "link", side_effect=competitor):
            result = self.apply(plan)
        self.assertEqual(result["created"], 0)
        self.assertEqual(org.undo_run(result["run_id"], str(self.journal), str(self.root))["removed"], 0)
        self.assertTrue(target.exists())
        self.assertTrue(source.exists())

    def test_truncated_journal_tail_is_recoverable_and_history_remains_readable(self):
        self.file("source.png")
        result = self.apply()
        journal = self.journal / (result["run_id"] + ".jsonl")
        with journal.open("ab") as handle:
            handle.write(b'{"event":"partial')
        self.assertEqual(len(org.list_runs(str(self.journal), str(self.root))), 1)
        self.assertEqual(org.undo_run(result["run_id"], str(self.journal), str(self.root))["removed"], 1)
        self.assertEqual(org.list_runs(str(self.journal), str(self.root))[0]["status"], "undone")
        self.assertEqual(org.undo_run(result["run_id"], str(self.journal), str(self.root))["removed"], 0)

    def test_partial_errors_are_visible_in_run_history(self):
        source = self.file("source.png")
        plan = self.plan()
        source.write_bytes(b"updated after preview")
        self.apply(plan)
        row = org.list_runs(str(self.journal), str(self.root))[0]
        self.assertEqual((row["status"], row["errors"]), ("partial", 1))
        self.assertTrue(row["error_messages"])

    def test_undo_does_not_follow_target_symlink(self):
        self.file("source.png")
        plan = self.plan()
        result = self.apply(plan)
        target = Path(plan["items"][0]["target"])
        target.unlink()
        external = self.file("outside.png", root=self.base)
        self._symlink(external, target)
        self.assertEqual(org.undo_run(result["run_id"], str(self.journal), str(self.root))["removed"], 0)
        self.assertTrue(external.exists())


if __name__ == "__main__":
    unittest.main()
