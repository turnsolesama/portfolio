"""Regression tests for malformed model metadata and copyable diagnostics."""

import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from frameweave.diagnostics import diagnose, inspect_safetensors, safe_relative
from frameweave.workflows import catalog, compile_workflow
from test_workflows import fixture


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

    def diagnose(self, request=None, info=None, online=True, environment=None):
        info = fixture() if info is None else info
        status = {"online": online, "system": {"pytorch_version": "2.10.0"},
                  "devices": [{"type": "cuda", "name": "Test GPU"}]}
        return diagnose({}, info, status, request or {"kind": "sdxl"}, catalog(info), environment)

    def test_offline_nodes_models_and_runtime_are_unknown_not_missing(self):
        result = self.diagnose({"kind": "h3_t2v"}, online=False)
        relevant = [row for row in result["checks"] if row["category"] in {"node", "model", "runtime", "backend"}]
        self.assertTrue(relevant)
        self.assertTrue(all(row["status"] == "unknown" for row in relevant))
        self.assertFalse(result["ready"])
        self.assertEqual(result["counts"]["missing"], 0)

    def test_complete_online_config_is_statically_ready_with_explicit_scope(self):
        result = self.diagnose()
        self.assertTrue(result["ready"])
        self.assertEqual(result["mode"], "sdxl")
        self.assertIn("GPU", result["scope"])
        self.assertIn("T", result["checked_at"])
        self.assertEqual(sum(result["counts"].values()), len(result["checks"]))
        self.assertEqual(len({row["id"] for row in result["checks"]}), len(result["checks"]))
        for row in result["checks"]:
            self.assertIsInstance(row["action"]["steps"], list)
            self.assertIn(row["status"], ("ok", "missing", "error", "warning", "unknown"))

    def test_dependencies_match_actual_compiler_for_all_request_variants(self):
        cases = [{"kind": "h3_t2v"}, {"kind": "h3_t2v", "negative": "blur"},
                 {"kind": "h3_i2v", "references": ["first.png"]},
                 {"kind": "h3_ref", "references": ["style.png"]},
                 {"kind": "h3_t2v", "sampler": "dual_clock_euler", "lora": "loras/turbo.safetensors"},
                 {"kind": "krea"}, {"kind": "krea", "references": ["first.png"]},
                 {"kind": "krea", "references": ["first.png"], "denoise": .7, "negative": "blur"},
                 {"kind": "sdxl", "references": ["first.png"], "lora": "loras/turbo.safetensors"},
                 {"kind": "sdxl"}]
        for case in cases:
            with self.subTest(case=case):
                request = {"positive": "Test scene.", **case}
                graph = compile_workflow(request, fixture())["prompt"]
                result = self.diagnose(request)
                actual = {row["name"].removeprefix("节点 · ") for row in result["checks"] if row["category"] == "node"}
                expected = {node["class_type"] for node in graph.values()}
                self.assertEqual(actual, expected)

    def test_h3_decode_fallback_requires_complete_native_decode_set(self):
        info = fixture()
        del info["VAEDecodeAudio"]
        result = self.diagnose({"kind": "h3_t2v"}, info=info)
        nodes = {row["name"]: row for row in result["checks"] if row["category"] == "node"}
        self.assertIn("节点 · MiniMaxH3AVDecodeT8", nodes)
        self.assertNotIn("节点 · LTXVSeparateAVLatent", nodes)
        self.assertEqual(nodes["节点 · MiniMaxH3AVDecodeT8"]["status"], "missing")

    def test_missing_edit_and_lora_dependencies_block_readiness(self):
        info = fixture()
        del info["Krea2OstrisEditModelPatch"]
        del info["LoraLoader"]
        for request, node in [({"kind": "krea", "references": ["first.png"]}, "Krea2OstrisEditModelPatch"),
                              ({"kind": "sdxl", "lora": "loras/turbo.safetensors"}, "LoraLoader")]:
            result = self.diagnose(request, info=info)
            row = next(item for item in result["checks"] if item["name"] == "节点 · " + node)
            self.assertEqual(row["status"], "missing")
            self.assertFalse(result["ready"])

    def test_reference_media_must_be_present_in_selected_backend(self):
        result = self.diagnose({"kind": "h3_i2v", "references": ["lost.png"]})
        self.assertEqual(next(row for row in result["checks"] if row["id"] == "input.images")["status"], "missing")
        self.assertNotIn("lost.png", result["repair_prompt"])

    def test_api_does_not_invent_model_roles_for_non_model_graph(self):
        info = {"Number": {"input": {"required": {"value": ["INT"]}}, "output": ["INT"]}}
        result = self.diagnose({"kind": "api", "prompt": {"1": {"class_type": "Number", "inputs": {"value": 3}}}}, info=info)
        self.assertFalse(any(row["category"] == "model" for row in result["checks"]))
        self.assertTrue(result["ready"])

    def test_api_checks_actual_loader_model_enum_and_wrapped_workflow(self):
        graph = {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "checkpoints/missing.safetensors"}}}
        result = self.diagnose({"kind": "api", "workflow": {"prompt": graph}})
        models = [row for row in result["checks"] if row["category"] == "model"]
        self.assertEqual(len(models), 1)
        self.assertIn("checkpoint", models[0]["id"])
        self.assertEqual(models[0]["status"], "missing")
        self.assertFalse(result["ready"])

    def test_api_custom_loader_model_file_enum_is_checked(self):
        info = {"CustomLoader": {"input": {"required": {"weights": [["valid.gguf"]]}}, "output": ["MODEL"]}}
        result = self.diagnose({"kind": "api", "prompt": {"1": {"class_type": "CustomLoader", "inputs": {"weights": "missing.gguf"}}}}, info=info)
        self.assertTrue(any(row["category"] == "model" and row["status"] == "missing" for row in result["checks"]))

    def test_api_offline_enumeration_is_unknown(self):
        graph = {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "missing.safetensors"}}}
        result = self.diagnose({"kind": "api", "prompt": graph}, online=False)
        self.assertEqual(result["counts"]["missing"], 0)
        self.assertEqual(next(row for row in result["checks"] if row["id"] == "models.api")["status"], "unknown")

    def test_empty_api_graph_is_error_instead_of_unrelated_image_model_checks(self):
        result = self.diagnose({"kind": "api", "prompt": {}})
        self.assertFalse(result["ready"])
        self.assertEqual(next(row for row in result["checks"] if row["id"] == "workflow.empty")["status"], "error")
        self.assertFalse(any(row["category"] == "model" for row in result["checks"]))

    def test_incompatible_known_architecture_is_error(self):
        result = self.diagnose({"kind": "krea", "models": {"dit": "diffusion_models/minimax_h3_fl2va_int8.safetensors"}})
        row = next(row for row in result["checks"] if row["id"].startswith("model.dit.") and not row["id"].endswith(".file"))
        self.assertEqual(row["status"], "error")
        self.assertFalse(result["ready"])

    def test_encoder_mode_and_parameter_schema_are_checked(self):
        info = fixture()
        info["CLIPLoader"]["input"]["required"]["type"] = [["minimax"]]
        result = self.diagnose({"kind": "krea"}, info=info)
        self.assertEqual(next(row for row in result["checks"] if row["id"] == "schema.clip_type")["status"], "missing")
        result = self.diagnose({"kind": "h3_t2v", "fps": 30})
        self.assertEqual(next(row for row in result["checks"] if row["id"] == "workflow.schema")["status"], "error")

    def test_unknown_runtime_does_not_falsely_report_missing_torch_or_cuda(self):
        result = diagnose({}, fixture(), {"online": True}, {"kind": "sdxl"}, catalog(fixture()))
        runtime = [row for row in result["checks"] if row["category"] == "runtime"]
        self.assertTrue(all(row["status"] == "unknown" for row in runtime))
        self.assertFalse(result["ready"])
        result = diagnose({}, fixture(), {"online": True, "system": {"pytorch_version": "2"}, "devices": [{"type": "cpu"}]}, {"kind": "sdxl"}, catalog(fixture()))
        self.assertEqual(next(row for row in result["checks"] if row["id"] == "runtime.cuda")["status"], "warning")

    def test_invalid_request_shapes_and_limits_raise_value_error(self):
        cases = [[], {"kind": []}, {"kind": "bad"}, {"models": []}, {"models": {"dit": []}},
                 {"positive": []}, {"references": "x"}, {"references": ["../x.png"]},
                 {"denoise": []}, {"fps": []}, {"width": True}, {"lora": []},
                 {"kind": "api", "prompt": []}, {"kind": "api", "prompt": {"1": {"class_type": [], "inputs": {}}}},
                 {"kind": "api", "prompt": {"1": {"class_type": "X", "inputs": []}}},
                 {"kind": "api", "prompt": {str(i): {"class_type": "X", "inputs": {}} for i in range(1001)}}]
        for request in cases:
            with self.subTest(request_type=type(request)):
                with self.assertRaises(ValueError):
                    diagnose({}, {}, {"online": False}, request, {})

    def test_repair_redacts_multilevel_paths_media_prompts_commands_and_snapshot(self):
        name = "PrivateClient/SecretAccount/TopSecretPerson/custom_model.safetensors"
        info = fixture()
        info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"] = [[name]]
        result = self.diagnose({"kind": "sdxl", "models": {"checkpoint": name},
                                "positive": "PersonalStory", "negative": "PersonalNegative",
                                "references": ["PersonalMedia.png"], "command": "python SecretCommand.py"}, info=info,
                               environment={"checks": [{"status": "warning", "detail": "C:/SecretAccount/TopSecretPerson", "name": "PersonalName", "action": {"steps": ["SecretCommand"]}}]})
        for secret in ("PrivateClient", "SecretAccount", "TopSecretPerson", "custom_model", "PersonalStory", "PersonalNegative", "PersonalMedia", "SecretCommand", "PersonalName"):
            self.assertNotIn(secret, result["repair_prompt"])

    def test_api_private_type_does_not_leak_into_repair(self):
        graph = {"private-user-id": {"class_type": "PersonalNameSecretNode", "inputs": {"prompt": "PrivateStory"}}}
        result = self.diagnose({"kind": "api", "prompt": graph})
        for secret in ("private-user-id", "PersonalNameSecretNode", "PrivateStory"):
            self.assertNotIn(secret, result["repair_prompt"])


if __name__ == "__main__":
    unittest.main()
