"""Regression tests for malformed model metadata and copyable diagnostics."""

import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from frameweave.diagnostics import diagnose, inspect_safetensors, safe_relative


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def model(self, dtype="F32", shape=None, payload=b"\x00" * 4):
        header = json.dumps({"weight": {"dtype": dtype, "shape": [1] if shape is None else shape,
                                         "data_offsets": [0, len(payload)]}}).encode()
        path = self.root / "test.safetensors"
        path.write_bytes(struct.pack("<Q", len(header)) + header + payload)
        return path

    def test_valid_structure_does_not_claim_checksum(self):
        state, message, size = inspect_safetensors(self.model())
        self.assertEqual(state, "ok")
        self.assertGreater(size, 4)
        self.assertIn("未", message)
        self.assertIn("SHA-256", message)

    def test_invalid_dtype_types_do_not_crash_or_pass(self):
        for dtype in ([], {}, None, 123):
            with self.subTest(dtype=dtype):
                state, _, _ = inspect_safetensors(self.model(dtype=dtype))
                self.assertEqual(state, "error")

    def test_unknown_dtype_does_not_claim_known_valid_structure(self):
        state, _, _ = inspect_safetensors(self.model(dtype="NOT_A_REAL_DTYPE"))
        self.assertIn(state, ("warning", "error"))

    def test_truncated_header_and_missing_tensor_bytes_are_errors(self):
        path = self.root / "broken.safetensors"
        for content in (b"", b"1234567", struct.pack("<Q", 200) + b"{}", struct.pack("<Q", 3) + b"bad"):
            with self.subTest(content=content):
                path.write_bytes(content)
                self.assertEqual(inspect_safetensors(path)[0], "error")
        path = self.model()
        path.write_bytes(path.read_bytes()[:-1])
        self.assertEqual(inspect_safetensors(path)[0], "error")

    def test_tensor_shape_must_match_payload_length(self):
        self.assertEqual(inspect_safetensors(self.model(shape=[2]))[0], "error")

    def test_relative_names_reject_absolute_traversal_and_streams(self):
        for name in ("../model.safetensors", "folder/../../file", "C:/file", "/file", "file:stream", "x\x00y"):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    safe_relative(name)
        self.assertEqual(safe_relative("folder\\model.safetensors"), "folder/model.safetensors")

    def test_repair_prompt_omits_file_exception_private_path(self):
        private_path = "C:/SensitiveClient/PrivateProject/model.safetensors"
        with patch("frameweave.diagnostics.resolve_model", return_value=Path("model.safetensors")), \
                patch("frameweave.diagnostics.inspect_safetensors", side_effect=PermissionError(13, "Permission denied", private_path)):
            result = diagnose({}, {}, {"online": True},
                              {"kind": "sdxl", "models": {"checkpoint": "model.safetensors"}},
                              {"checkpoint": ["model.safetensors"]})
        self.assertNotIn("SensitiveClient", result["repair_prompt"])
        self.assertNotIn("PrivateProject", result["repair_prompt"])
        self.assertTrue(any(row["status"] == "error" for row in result["checks"]))

    def test_ref_mode_checks_reference_node_instead_of_first_last_node(self):
        info = {name: {} for name in ("UNETLoader", "CLIPLoader", "VAELoader", "MiniMaxH3ImageToVideo", "SaveVideo")}
        result = diagnose({}, info, {"online": True}, {"kind": "h3_ref"}, {})
        reference = [row for row in result["checks"] if row["name"] == "节点 · MiniMaxH3ReferenceToVideo"]
        self.assertEqual(len(reference), 1)
        self.assertEqual(reference[0]["status"], "missing")


if __name__ == "__main__":
    unittest.main()
