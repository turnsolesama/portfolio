import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from yingxu.skills import SkillLibrary, _metadata
from yingxu.store import Store, UserError


class SkillLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / "home"
        self.home.mkdir()
        self.home_patch = patch("yingxu.skills.Path.home", return_value=self.home)
        self.home_patch.start()
        self.addCleanup(self.home_patch.stop)
        self.store = Store(self.root / "data", self.root / "projects")
        self.project = self.store.create_project("测试短片")

    def external(self, name="分镜规划", content=None):
        path = self.home / ".codex" / "skills" / name / "SKILL.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content or f"---\nname: {name}\ndescription: >\n  中文分镜规划\n  支持项目关联\n---\n\n# 只读技能\n", encoding="utf-8")
        return path

    def test_external_preview_search_readonly_and_metadata(self):
        path = self.external()
        library = SkillLibrary(self.store)
        listing = library.list("分镜 中文")
        self.assertEqual(listing["total"], 1)
        row = listing["skills"][0]
        self.assertEqual(row["source"], "codex")
        self.assertFalse(row["editable"])
        self.assertNotIn("content", row)
        self.assertEqual(row["description"], "中文分镜规划 支持项目关联")
        preview = library.get(row["id"])
        self.assertIn("只读技能", preview["content"])
        before = path.read_bytes()
        with self.assertRaises(UserError) as error:
            library.save(row["id"], {"etag": preview["etag"], "content": "overwrite"})
        self.assertEqual(error.exception.status, 403)
        self.assertEqual(path.read_bytes(), before)

    def test_directory_resolves_registered_skill_without_reading_or_mutating_it(self):
        path=self.external(); library=SkillLibrary(self.store); skill=library.list()['skills'][0]
        with patch('yingxu.skills._read',side_effect=AssertionError('must not read body')), patch.object(library,'_upsert',side_effect=AssertionError('must not update index')):
            self.assertEqual(library.directory(skill['id']),path.parent)
        library.remove(skill['id'])
        with self.assertRaises(UserError): library.directory(skill['id'])

    def test_create_save_backup_conflict_and_binding_survives_refresh(self):
        library = SkillLibrary(self.store)
        skill = library.create({"name": "镜头检查", "description": "审核运动连续性", "content": "# 检查\n\n检查人物走位。"})
        self.assertTrue(skill["editable"])
        self.assertEqual(skill["source"], "yingxu")
        self.assertTrue(Path(skill["path"]).is_relative_to(library.root))
        original = Path(skill["path"]).read_bytes()
        library.bind(self.project["id"], skill["id"], True)
        saved = library.save(skill["id"], {"etag": skill["etag"], "content": skill["content"] + "\n检查轴线。"})
        self.assertNotEqual(saved["etag"], skill["etag"])
        backups = list((library.versions_root / skill["id"]).glob("*.md"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)
        self.assertFalse(list(Path(skill["path"]).parent.glob("*.tmp")))
        with self.assertRaises(UserError) as error:
            library.save(skill["id"], {"etag": skill["etag"], "content": "stale"})
        self.assertEqual(error.exception.status, 409)
        library.refresh()
        bound = library.bound_skills(self.project["id"])
        self.assertEqual([item["id"] for item in bound], [skill["id"]])
        self.assertTrue(library.list(project_id=self.project["id"])["skills"][0]["bound"])
        self.assertTrue(library.bind(self.project["id"], skill["id"], False)["ok"])
        self.assertEqual(library.bound_skills(self.project["id"]), [])

    def test_external_change_and_missing_preserve_binding(self):
        path = self.external()
        library = SkillLibrary(self.store)
        skill = library.list()["skills"][0]
        library.bind(self.project["id"], skill["id"], True)
        path.write_text("---\nname: 新技能名称\ndescription: 已改变\n---\n正文", encoding="utf-8")
        library.refresh()
        updated = library.get(skill["id"])
        self.assertEqual(updated["name"], "新技能名称")
        path.unlink()
        library.refresh()
        self.assertEqual(library.list()["total"], 0)
        missing = library.bound_skills(self.project["id"])[0]
        self.assertFalse(missing["available"])
        with self.assertRaises(UserError) as error:
            library.get(skill["id"])
        self.assertEqual(error.exception.status, 404)
        library.bind(self.project["id"], skill["id"], False)

    def test_depth_cache_size_and_count_limits(self):
        self.external("有效")
        base = self.home / ".codex" / "skills"
        for folder in (".cache/bad", "cache/bad", "a/b/c/d"):
            path = base / folder / "SKILL.md"
            path.parent.mkdir(parents=True)
            path.write_text("# hidden/deep", encoding="utf-8")
        large = base / "large" / "SKILL.md"
        large.parent.mkdir()
        large.write_bytes(b"x" * (1024 * 1024 + 1))
        library = SkillLibrary(self.store)
        self.assertEqual(library.list()["total"], 1)
        self.external("额外")
        with patch("yingxu.skills.MAX_SKILLS", 1):
            refreshed = library.refresh()
            self.assertEqual(refreshed["total"], 1)
            self.assertTrue(refreshed["truncated"])

    def test_symlinks_and_hardlink_duplicates_are_not_editable(self):
        original = self.external()
        library = SkillLibrary(self.store)
        alias = library.root / "hardlink" / "SKILL.md"
        alias.parent.mkdir()
        try:
            os.link(original, alias)
        except OSError:
            self.skipTest("filesystem does not support hard links")
        library.refresh()
        self.assertEqual(library.list()["total"], 1)
        self.assertFalse(library.list()["skills"][0]["editable"])
        linked = library.root / "symlink"
        try:
            linked.symlink_to(original.parent, target_is_directory=True)
        except OSError:
            return  # Windows accounts may not have symlink creation permission.
        result = library.refresh()
        self.assertEqual(result["total"], 1)
        self.assertGreaterEqual(result["skipped"], 1)

    def test_frontmatter_is_text_and_input_is_bounded(self):
        metadata = _metadata("---\nname: '镜头 ''分析'''\ndescription: |\n  第一行\n  第二行\nother: !!python/object/apply:os.system [\"bad\"]\n---\n内容")
        self.assertEqual(metadata["name"], "镜头 '分析'")
        self.assertEqual(metadata["description"], "第一行\n第二行")
        library = SkillLibrary(self.store)
        for data in ({"name": ""}, {"name": "有效", "content": "\x00"}, {"name": "有效", "content": "a" * (1024 * 1024 + 1)}):
            with self.subTest(data=list(data)), self.assertRaises(UserError):
                library.create(data)
        with self.assertRaises(UserError):
            library.bind("missing", "missing", True)


if __name__ == "__main__":
    unittest.main()
