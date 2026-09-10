"""Portable workflow integrity, binding safety and offline library tests."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from frameweave.packages import PackageStore, apply_values, inspect_document, normalize_document


def sample():
    return {"name": "影像试样", "description": "图片与视频都使用 API 图",
            "prompt": {"1": {"class_type": "Text", "inputs": {"text": "morning light", "seed": 42}},
                       "2": {"class_type": "Output", "inputs": {"text": ["1", 0]}}},
            "fields": [{"id": "prompt", "node_id": "1", "input": "text", "type": "text", "label": "画面提示词", "default": "morning light", "required": True},
                       {"id": "seed", "node_id": "1", "input": "seed", "type": "integer", "label": "种子", "default": 42, "min": 0, "max": 1000}]}


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = PackageStore(self.root / "library")

    def test_create_export_import_has_stable_identity_and_retains_graph(self):
        first = self.store.save(sample())
        document = self.store.export(first["id"])
        another = PackageStore(self.root / "another")
        second = another.save(document)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(document["prompt"], sample()["prompt"])
        self.assertNotIn("id", document)
        self.assertNotIn("created_at", document)
        self.assertNotIn("prompt", self.store.list()[0])

    def test_user_values_modify_only_bound_inputs_without_mutating_template(self):
        document = sample()
        original = copy.deepcopy(document)
        result = apply_values(document, {"prompt": "a green teapot", "seed": 123})
        self.assertEqual(result["1"]["inputs"], {"text": "a green teapot", "seed": 123})
        self.assertEqual(result["2"], original["prompt"]["2"])
        self.assertEqual(document, original)

    def test_invalid_user_values_are_not_coerced(self):
        for values in ({"seed": True}, {"seed": 1.5}, {"seed": 1001}, {"seed": float("nan")},
                       {"prompt": ""}, {"prompt": {}}, {"unexpected": "value"}, []):
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    apply_values(sample(), values)

    def test_cannot_bind_nonexistent_input_link_or_same_field_twice(self):
        for change in ({"node_id": "absent"}, {"input": "absent"}, {"node_id": "2", "input": "text"}):
            document = sample()
            document["fields"][0].update(change)
            with self.assertRaises(ValueError):
                normalize_document(document)
        document = sample()
        document["fields"].append({**document["fields"][0], "id": "other"})
        with self.assertRaises(ValueError):
            normalize_document(document)

    def test_reject_reserved_or_duplicate_parameter_ids(self):
        for value in ("__proto__", "constructor", "../x", "seed", ""):
            document = sample()
            document["fields"][0]["id"] = value
            with self.assertRaises(ValueError):
                normalize_document(document)

    def test_graph_cycles_broken_links_and_ui_format_rejected(self):
        document = sample()
        for link in (["missing", 0], ["2", 0], ["1", -1]):
            graph = copy.deepcopy(document["prompt"])
            graph["1"]["inputs"]["text"] = link
            with self.assertRaises(ValueError):
                inspect_document(graph)
        with self.assertRaisesRegex(ValueError, "API"):
            inspect_document({"nodes": [], "links": []})

    def test_package_format_and_limits_are_enforced_before_saving(self):
        for change in ({"version": 2}, {"format": "script"}, {"name": ""}, {"description": "x" * 2001}):
            with self.assertRaises(ValueError):
                self.store.save({**sample(), **change})
        with self.assertRaises(ValueError):
            inspect_document({"payload": "x" * (2 * 1024 * 1024)})
        self.assertFalse(self.store.directory.exists())

    def test_image_bindings_are_portable_and_require_new_input(self):
        graph = {"9": {"class_type": "LoadImage", "inputs": {"image": "private-image.png"}}}
        inspection = inspect_document(graph)
        image = inspection["fields"][0]
        self.assertEqual(image["type"], "image")
        document = {**inspection, "name": "图片参考"}
        package = self.store.save(document)
        self.assertNotIn("private-image", json.dumps(self.store.export(package["id"])))
        with self.assertRaises(ValueError):
            apply_values(package, {})
        for invalid in ("../image.png", "C:/private/image.png", "/root/image.png"):
            with self.assertRaises(ValueError):
                apply_values(package, {image["id"]: invalid})
        result = apply_values(package, {image["id"]: "frameweave/safe.png"})
        self.assertEqual(result["9"]["inputs"]["image"], "frameweave/safe.png")

    def test_select_values_preserve_type_and_boolean_is_not_integer(self):
        document = sample()
        field = document["fields"][1]
        field.update(type="select", options=[42, 123])
        self.assertEqual(apply_values(document, {"seed": 123})["1"]["inputs"]["seed"], 123)
        for value in ("42", True, 99):
            with self.assertRaises(ValueError):
                apply_values(document, {"seed": value})

    def test_inspection_uses_schema_bounds_and_labels_positive_negative(self):
        graph = {"1": {"class_type": "Text", "inputs": {"text": "yes"}},
                 "2": {"class_type": "Text", "inputs": {"text": "no"}},
                 "3": {"class_type": "Sampler", "inputs": {"positive": ["1", 0], "negative": ["2", 0], "steps": 8}}}
        info = {"Sampler": {"input": {"required": {"steps": ["INT", {"min": 1, "max": 200}]}}}}
        result = inspect_document(graph, info)
        fields = {field["node_id"]: field for field in result["fields"]}
        self.assertIn("正向", fields["1"]["label"])
        self.assertIn("负向", fields["2"]["label"])
        self.assertEqual(fields["3"]["max"], 200)
        self.assertTrue(all(field["recommended"] for field in fields.values()))

    def test_unknown_custom_nodes_can_be_imported_offline_but_are_not_executed(self):
        graph = {"node": {"class_type": "MyPlugin", "inputs": {"text": "data only"}, "_meta": {"title": "private title"}}}
        result = inspect_document({"prompt": graph, "extra_data": {"private": "omit"}})
        self.assertEqual(result["requirements"]["nodes"], ["MyPlugin"])
        self.assertNotIn("_meta", result["prompt"]["node"])
        self.assertNotIn("extra_data", result)

    def test_library_detects_tampering_and_recovers_other_packages(self):
        package = self.store.save(sample())
        path = self.store.directory / (package["id"] + ".json")
        document = json.loads(path.read_text(encoding="utf-8"))
        document["prompt"]["1"]["inputs"]["text"] = "tampered"
        path.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "变化"):
            self.store.get(package["id"])
        self.assertEqual(self.store.list(), [])
        with self.assertRaises(ValueError):
            self.store.get("../../outside")
        with self.assertRaisesRegex(ValueError, "导入"):
            self.store.get("p-" + "0" * 24)

    def test_corrupt_deep_json_does_not_break_library(self):
        package = self.store.save(sample())
        path = self.store.directory / (package["id"] + ".json")
        path.write_bytes(b"[" * 2000 + b"0" + b"]" * 2000)
        with self.assertRaises(ValueError):
            self.store.get(package["id"])
        self.assertEqual(self.store.list(), [])

    def test_large_bounds_and_select_integers_rejected_without_overflow(self):
        for value in (10 ** 400, -10 ** 400, 9007199254740993):
            document = sample()
            document["fields"][1]["min"] = value
            with self.assertRaises(ValueError):
                normalize_document(document)
            document = sample()
            document["fields"][1].update(type="select", default=value, options=[value])
            with self.assertRaises(ValueError):
                normalize_document(document)

    def test_unexposed_image_cannot_produce_nonportable_package(self):
        document = inspect_document({"9": {"class_type": "LoadImage", "inputs": {"image": "local.png"}}})
        document["fields"] = []
        with self.assertRaisesRegex(ValueError, "上传参数"):
            normalize_document(document)


if __name__ == "__main__":
    unittest.main()
