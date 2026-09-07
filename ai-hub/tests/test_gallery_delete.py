import json
from pathlib import Path
from unittest import mock
from test_aihub import Fixture
from aihub import api, images, jobs, recycle


class GalleryDeletion(Fixture):
    def setUp(self):
        super().setUp()
        self.output = self.ai / "output"
        self.output.mkdir()
        self.cfg["output_roots"] = [str(self.output)]
        self.image = self.output / "中文 image.png"
        self.image.write_bytes(b"test image placeholder")
        self.stat = self.image.stat()
        self.db.conn.execute("INSERT INTO images(path,name,parent,size,mtime) VALUES(?,?,?,?,?)", (str(self.image), self.image.name, str(self.output), self.stat.st_size, self.stat.st_mtime))
        self.db.upsert_model({"path": "model", "filename": "style.safetensors", "mtype": "LoRA", "rating": 8, "notes": "keep"})
        self.db.conn.executemany("INSERT INTO img_refs(image_path,model_path,role,filename) VALUES(?,?,?,?)", [(str(self.image), "model", "LoRA", "style.safetensors"), (str(self.image), None, "Other", "missing.safetensors")])
        self.db.conn.execute("INSERT INTO files(path,parent,name,size,category) VALUES(?,?,?,?,?)", (str(self.image), str(self.output), self.image.name, self.stat.st_size, "image"))
        self.db.conn.execute("INSERT INTO dirs(path,size,file_count) VALUES(?,?,?)", (str(self.output), self.stat.st_size, 1))
        self.db.set_meta("unique_size", self.stat.st_size)
        images.recompute_usage(self.db)
        images.refresh_ghost_refs(self.db)
        self.body = {"path": str(self.image), "size": self.stat.st_size, "mtime": self.stat.st_mtime}

    def delete(self, **changes):
        return api.image_delete(self.db, self.cfg, {}, dict(self.body, **changes))

    def test_recycle_updates_gallery_references_storage_and_preserves_model_notes(self):
        recycled = self.folder / "recycled.png"
        recycled.resolve().relative_to(self.folder.resolve())
        with mock.patch.object(recycle, "recycle_file", side_effect=lambda path: Path(path).rename(recycled)) as operation:
            result = self.delete()
        self.assertEqual(result[0], 200)
        operation.assert_called_once_with(str(self.image))
        self.assertTrue(recycled.is_file())
        self.assertEqual(self.db.one("SELECT COUNT(*) n FROM images")["n"], 0)
        self.assertEqual(self.db.one("SELECT COUNT(*) n FROM img_refs")["n"], 0)
        model = self.db.model_by_path("model")
        self.assertEqual((model["img_count"], model["rating"], model["notes"]), (0, 8, "keep"))
        self.assertEqual(json.loads(self.db.get_meta("ghost_refs")), [])
        self.assertEqual(self.db.one("SELECT file_count FROM dirs")["file_count"], 0)
        self.assertEqual(self.db.get_meta("unique_size"), "0")
        self.assertEqual(self.delete()[0], 404)

    def test_recycle_failure_keeps_file_and_index(self):
        with mock.patch.object(recycle, "recycle_file", side_effect=OSError("Recycle unavailable")):
            self.assertEqual(self.delete()[0], 409)
        self.assertTrue(self.image.is_file())
        self.assertEqual(self.db.one("SELECT COUNT(*) n FROM images")["n"], 1)
        self.assertEqual(self.db.model_by_path("model")["img_count"], 1)

    def test_outside_output_and_non_image_paths_are_rejected(self):
        with mock.patch.object(recycle, "recycle_file") as operation:
            self.assertEqual(self.delete(path=str(self.folder / "private.png"))[0], 403)
            self.assertEqual(self.delete(path=str(self.output / "weights.safetensors"))[0], 403)
            self.assertEqual(self.delete(path="relative.png")[0], 400)
            operation.assert_not_called()

    def test_changed_image_is_not_deleted(self):
        with mock.patch.object(recycle, "recycle_file") as operation:
            self.assertEqual(self.delete(size=999)[0], 409)
            self.image.write_bytes(b"new content written after the gallery was loaded")
            self.assertEqual(self.delete()[0], 409)
            operation.assert_not_called()

    def test_unindexed_image_is_not_deleted(self):
        unindexed = self.output / "unindexed.png"
        unindexed.write_bytes(b"unindexed")
        with mock.patch.object(recycle, "recycle_file") as operation:
            self.assertEqual(self.delete(path=str(unindexed))[0], 404)
            operation.assert_not_called()

    def test_scan_busy_returns_conflict_without_touching_file(self):
        with mock.patch.object(jobs, "running", return_value=True), mock.patch.object(recycle, "recycle_file") as operation:
            self.assertEqual(self.delete()[0], 409)
            operation.assert_not_called()

    def test_directory_filter_includes_images_directly_in_selected_directory(self):
        listing = json.loads(api.images_list(self.db, self.cfg, {"dir": str(self.output)}, None)[2])
        self.assertEqual(listing["total"], 1)

    def test_model_filter_accepts_model_filename_and_exact_path(self):
        for model in ("style.safetensors", "model"):
            listing = json.loads(api.images_list(self.db, self.cfg, {"model": model}, None)[2])
            self.assertEqual(listing["total"], 1)
