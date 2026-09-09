"""Regression tests for independently reproduced review findings.

Every file and database is synthetic and temporary. No installed application
data, existing skills, or real creative assets are scanned or modified.
"""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
from pathlib import Path
import struct
import tempfile
import threading
import tracemalloc
import unittest
from unittest.mock import patch
import zlib

from yingxu.jobs import Jobs
from yingxu.store import Store, UserError, now, uid


def make_png(path, width, text=None):
    """Create an opaque synthetic RGB PNG with metadata, without image tools."""
    def chunk(kind, value):
        return (struct.pack(">I", len(value)) + kind + value
                + struct.pack(">I", zlib.crc32(kind + value) & 0xFFFFFFFF))

    payload = b"\x89PNG\r\n\x1a\n"
    payload += chunk(b"IHDR", struct.pack(">IIBBBBB", width, 1, 8, 2, 0, 0, 0))
    for name, value in (text or {}).items():
        payload += chunk(b"tEXt", name.encode("ascii") + b"\0" + value.encode("ascii"))
    payload += chunk(b"IDAT", zlib.compress(b"\0" + b"\0\0\0" * width))
    payload += chunk(b"IEND", b"")
    path.write_bytes(payload)


class ReviewRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # An ordinary importable directory contains the protected app-data tree.
        self.materials = self.root / "materials"
        self.store = Store(self.materials / "appdata", self.root / "projects")
        self.project = self.store.create_project("合成回归测试项目")

    def jobs(self):
        jobs = Jobs(self.store)
        self.addCleanup(jobs.pool.shutdown, wait=True)
        return jobs

    def finish_job(self, jobs, result):
        # A sentinel on the same one-worker queue completes after the real job.
        jobs.pool.submit(lambda: None).result(timeout=10)
        status = jobs.get(result["job_id"])
        self.assertEqual(status["state"], "done", status)
        self.assertEqual(status["errors"], [], status)
        return status

    def index_external(self, path, project=None, category="scripts"):
        project = project or self.project
        source = self.store.register_source(project["id"], path, category)
        self.store.index_files(source, [path])
        with self.store.connection() as db:
            item_id = db.execute(
                "SELECT id FROM items WHERE project_id=? AND path=?",
                (project["id"], str(path)),
            ).fetchone()[0]
        return source, self.store.get_item(item_id)

    def test_application_data_excluded_from_walk_index_and_legacy_access(self):
        backup = self.store.data_root / "versions" / "synthetic-backup.md"
        backup.parent.mkdir()
        backup.write_text("恢复版本，不能当作项目文件编辑。", encoding="utf-8")
        original = backup.read_bytes()
        asset = self.materials / "剧本.md"
        asset.write_text("普通素材可以被导入。", encoding="utf-8")

        walked = list(Jobs.walk(self.materials, self.store.data_root))
        self.assertIn(asset, walked)
        self.assertNotIn(backup, walked)
        self.assertEqual(list(Jobs.walk(self.store.data_root, self.store.data_root)), [])

        jobs = self.jobs()
        self.finish_job(jobs, jobs.submit(self.project["id"], "scripts", [str(self.materials)]))
        listed = self.store.list_items(self.project["id"])["items"]
        self.assertEqual([row["path"] for row in listed], [str(asset)])

        source = next(s for s in self.store.sources(self.project["id"]) if s["path"] == str(self.materials))
        self.assertEqual(self.store.index_files(source, [backup]), (0, 1))
        with self.assertRaises(UserError):
            self.store.register_source(self.project["id"], backup, "scripts")

        # Simulate a row created by an older version before this boundary fix.
        legacy_id = uid()
        with self.store.connection() as db:
            db.execute(
                """INSERT INTO items(id,project_id,source_id,name,category,kind,ext,path,size,mtime,created,updated)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (legacy_id, self.project["id"], source["id"], "旧版误索引备份", "scripts", "markdown", ".md",
                 str(backup), len(original), backup.stat().st_mtime_ns, now(), now()),
            )
        with self.assertRaises(UserError) as error:
            self.store.read_content(legacy_id)
        self.assertEqual(error.exception.status, 403)
        with self.assertRaises(UserError) as error:
            self.store.save_content(legacy_id, {"etag": "irrelevant", "content": "不得写入"})
        self.assertEqual(error.exception.status, 403)
        self.assertEqual(backup.read_bytes(), original)

    def test_simultaneous_first_index_does_not_duplicate_or_raise(self):
        asset = self.materials / "并发剧本.md"
        asset.write_text("两个索引请求同时发现这份雨夜剧本。", encoding="utf-8")
        source = self.store.register_source(self.project["id"], asset, "scripts")
        original_inspect = self.store.inspect_file
        barrier = threading.Barrier(2)

        def inspect_after_both_observed_absence(path):
            result = original_inspect(path)
            barrier.wait(timeout=5)
            return result

        with patch.object(self.store, "inspect_file", side_effect=inspect_after_both_observed_absence):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(self.store.index_files, source, [asset]) for _ in range(2)]
                for future in futures:
                    future.result(timeout=10)
        self.assertEqual(self.store.list_items(self.project["id"])["total"], 1)
        self.assertEqual(self.store.list_items(self.project["id"], q="雨夜")["total"], 1)
        with self.store.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM item_search").fetchone()[0], 1)

    def test_list_page_does_not_materialize_document_bodies_or_large_workflows(self):
        source = self.store.sources(self.project["id"])[0]
        body = "x" * (256 * 1024)
        metadata = json.dumps({"source_workflow": "w" * (64 * 1024), "prompt": "p" * 8192, "shot_number": "001", "duration": 4})
        with self.store.connection() as db:
            db.executemany(
                """INSERT INTO items(id,project_id,source_id,name,category,kind,ext,path,size,mtime,created,updated,search_content,metadata,notes)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [(uid(), self.project["id"], source["id"], f"文档{i:03d}", "scripts", "markdown", ".md",
                  str(self.root / f"synthetic-{i}.md"), len(body), 0, now(), now(), body, metadata, "n" * 1000)
                 for i in range(60)],
            )
        tracemalloc.start()
        try:
            result = self.store.list_items(self.project["id"])
            _current, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertEqual(len(result["items"]), 60)
        self.assertLess(peak, 4 * 1024 * 1024, f"List page allocated {peak:,} bytes; 15 MiB of bodies must stay in SQLite.")
        self.assertLess(len(json.dumps(result).encode("utf-8")), 128 * 1024)
        for item in result["items"]:
            self.assertNotIn("search_content", item)
            self.assertNotIn("source_workflow", item["metadata"])
            self.assertNotIn("prompt", item["metadata"])
            self.assertEqual(item["metadata"]["shot_number"], "001")
            self.assertLessEqual(len(item["notes"]), 240)

    def test_replaced_image_refreshes_extracted_fields_preserving_user_prompt(self):
        image = self.materials / "generation.png"
        make_png(image, 1, {"parameters": "old-parameters", "prompt": '{"seed":1}', "workflow": '{"nodes":[]}'})
        source, item = self.index_external(image, category="generated")
        metadata = self.store.get_item(item["id"])["metadata"]
        self.assertEqual(metadata["source_parameters"], "old-parameters")
        metadata.update(prompt="用户手写的镜头提示词", model="用户选定的模型")
        self.store.update_item(item["id"], {"metadata": metadata})

        make_png(image, 2, {"parameters": "new-parameters-longer", "prompt": '{"seed":234}', "workflow": '{"nodes":[2]}'} )
        self.store.index_files(source, [image])
        updated = self.store.get_item(item["id"])["metadata"]
        self.assertEqual((updated["width"], updated["height"]), (2, 1))
        self.assertEqual(updated["source_parameters"], "new-parameters-longer")
        self.assertEqual(updated["source_prompt"], '{"seed":234}')
        self.assertEqual(updated["source_workflow"], '{"nodes":[2]}')
        self.assertEqual(updated["prompt"], "用户手写的镜头提示词")
        self.assertEqual(updated["model"], "用户选定的模型")

        make_png(image, 3)
        self.store.index_files(source, [image])
        stripped = self.store.get_item(item["id"])["metadata"]
        self.assertEqual(stripped["width"], 3)
        self.assertFalse(any(key.startswith("source_") for key in stripped))
        self.assertEqual(stripped["prompt"], "用户手写的镜头提示词")

    def test_save_refreshes_chinese_search_in_every_referencing_project(self):
        second = self.store.create_project("第二个项目")
        shared = self.materials / "共用剧本.md"
        shared.write_text("旧版故事发生在雨夜。", encoding="utf-8")
        _source_a, item_a = self.index_external(shared)
        _source_b, item_b = self.index_external(shared, second)
        first = self.store.read_content(item_a["id"])
        saved = self.store.save_content(item_a["id"], {"etag": first["etag"], "content": "新版故事发生在晴天。"})
        self.assertNotEqual(first["etag"], saved["etag"])
        self.assertEqual(self.store.read_content(item_b["id"])["content"], "新版故事发生在晴天。")
        for project in (self.project, second):
            with self.subTest(project=project["name"]):
                self.assertEqual(self.store.list_items(project["id"], q="晴天")["total"], 1)
                self.assertEqual(self.store.list_items(project["id"], q="雨夜")["total"], 0)

    def test_rescan_keeps_removed_hidden_but_explicit_import_restores_same_item(self):
        asset = self.materials / "暂时移出.md"
        asset.write_text("用于恢复测试的角色说明。", encoding="utf-8")
        _source, item = self.index_external(asset)
        self.store.update_item(item["id"], {"status": "待审核", "tags": ["恢复标签"], "notes": "原备注保留"})
        self.store.remove_item(item["id"])
        jobs = self.jobs()
        self.finish_job(jobs, jobs.submit(self.project["id"]))
        self.assertEqual(self.store.list_items(self.project["id"], q="恢复标签")["total"], 0)

        self.finish_job(jobs, jobs.submit(self.project["id"], "scripts", [str(asset)]))
        restored = self.store.get_item(item["id"])
        self.assertEqual(restored["status"], "待审核")
        self.assertEqual(restored["tags"], ["恢复标签"])
        self.assertEqual(restored["notes"], "原备注保留")
        self.assertEqual(self.store.list_items(self.project["id"], q="角色说明")["total"], 1)
        self.assertEqual(self.store.list_items(self.project["id"], q="恢复标签")["items"][0]["id"], item["id"])
        self.assertTrue(asset.exists())

    def test_actual_paginated_name_and_order_queries_use_sort_indexes(self):
        for name, order in (("c", 3), ("A", 1), ("b", 2)):
            item = self.store.create_item({"project_id": self.project["id"], "category": "scripts", "name": name})
            self.store.update_item(item["id"], {"sort_order": order})
        original_connection = self.store.connection
        statements = []

        @contextmanager
        def traced_connection():
            with original_connection() as db:
                db.set_trace_callback(statements.append)
                try:
                    yield db
                finally:
                    db.set_trace_callback(None)

        for sort in ("name", "order"):
            for category in ("", "scripts"):
                with self.subTest(sort=sort, category=category):
                    statements.clear()
                    with patch.object(self.store, "connection", traced_connection):
                        page = self.store.list_items(self.project["id"], category=category, sort=sort, limit=1, offset=1)
                    self.assertEqual(page["total"], 3)
                    self.assertEqual([item["name"] for item in page["items"]], ["b"])
                    query = next(sql for sql in statements if sql.startswith("SELECT i.") and "ORDER BY" in sql)
                    with original_connection() as db:
                        plan = [row[3] for row in db.execute("EXPLAIN QUERY PLAN " + query)]
                    self.assertTrue(any("USING INDEX" in step for step in plan), plan)
                    self.assertFalse(any("TEMP B-TREE" in step for step in plan), plan)


if __name__ == "__main__":
    unittest.main()
