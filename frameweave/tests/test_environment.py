"""Boundaries for read-only environment discovery; no installed AI required."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch, Mock

from frameweave import environment as env


STATS = {"system": {"comfyui_version": "0.30.0", "python_version": "3.11.9"},
         "devices": [{"name": "test GPU", "type": "cuda", "vram_total": 17179869184}]}


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def installation(self):
        root = self.base / "ComfyUI"
        root.mkdir(exist_ok=True)
        (root / "main.py").write_text("raise AssertionError('never run user code')", encoding="utf-8")
        (root / "comfy").mkdir(exist_ok=True)
        (root / "models").mkdir(exist_ok=True)
        return root

    def discover(self, settings=None, records=None, stats=None):
        with patch.object(env, "_processes", return_value=(records or [], "unknown")), \
                patch.object(env, "_gpu", return_value={"gpus": [], "status": "unknown", "detail": "驱动状态未知"}), \
                patch.object(env, "_common_roots", return_value=[]), \
                patch.object(env, "_registry_roots", return_value=[]), \
                patch.object(env, "_request_stats", return_value=stats):
            return env.discover_environment(settings or {})

    def test_valid_response_is_cleaned_not_copied(self):
        payload = json.loads(json.dumps(STATS))
        payload["secret"] = "private"
        payload["devices"][0]["private_path"] = "C:/Private"
        with patch.object(env, "_request_stats", return_value=payload) as request:
            result = env._probe({"url": "http://127.0.0.1:8188", "source": "test"})
        self.assertTrue(result["online"])
        self.assertNotIn("private", json.dumps(result))
        self.assertEqual(request.call_args.kwargs, {"timeout": 1, "limit": 131072})

    def test_unrelated_or_malicious_services_are_not_comfy(self):
        for stats in (None, [], {}, {"system": []}, {"system": {"comfyui_version": "test"}, "devices": []},
                      {"system": STATS["system"], "devices": [1]},
                      {"system": STATS["system"], "devices": [{}]},
                      {"system": STATS["system"], "devices": [{}] * 33}):
            with self.subTest(stats=stats), patch.object(env, "_request_stats", return_value=stats):
                self.assertFalse(env._probe({"url": "http://127.0.0.1:8188", "source": "test"})["online"])

    def test_probe_timeout_is_unknown_not_missing(self):
        with patch.object(env, "_request_stats", side_effect=TimeoutError("C:/secret")):
            result = env._probe({"url": "http://127.0.0.1:8188", "source": "test"})
        self.assertEqual(result["status"], "unknown")
        self.assertNotIn("secret", json.dumps(result))

    def test_candidate_ports_deduplicate_and_reject_remote(self):
        result = self.discover({"backend_url": "http://localhost:8188"})
        self.assertEqual(len(result["candidates"]), 4)
        self.assertEqual(result["candidates"][0]["source"], "当前设置")
        result = self.discover({"backend_url": "http://example.org:8190"})
        self.assertFalse(any("example.org" in c["url"] for c in result["candidates"]))
        self.assertTrue(any(c["id"] == "backend_setting" for c in result["checks"]))

    def test_offline_and_inaccessible_information_remain_unknown(self):
        result = self.discover()
        self.assertEqual(result["installations"], [])
        self.assertEqual(result["hardware"]["status"], "unknown")
        self.assertFalse(any(c["status"] == "missing" for c in result["checks"]))
        self.assertFalse(any(c["online"] for c in result["candidates"]))

    def test_process_port_requires_independently_valid_comfy_directory(self):
        exe = self.base / "python.exe"
        records = [{"Name": "python.exe", "ExecutablePath": str(exe),
                    "CommandLine": f'"{exe}" "{self.base / "main.py"}" --port 9200'}]
        self.assertEqual(env._process_hints(records), ([], []))
        root = self.installation()
        records[0]["CommandLine"] = f'"{exe}" "{root / "main.py"}" --port=9200'
        hints, ports = env._process_hints(records)
        self.assertEqual(ports, [9200])
        self.assertEqual(hints[0][0], root)

    def test_yuh_host_layout_is_detected_without_private_hardcoded_path(self):
        root = self.base / "Studio/resources/engine/ComfyUI"
        root.mkdir(parents=True)
        (root / "main.py").touch()
        (root / "comfy").mkdir()
        hints, ports = env._process_hints([{"Name": "YUH Studio.exe", "ExecutablePath": str(self.base / "Studio/YUH Studio.exe")}])
        self.assertEqual(hints[0][0], root)
        self.assertEqual(ports, [])

    def test_yuh_runtime_interpreter_requires_existing_verified_host(self):
        host = self.base / "Studio"
        root = host / "resources/engine/ComfyUI"
        root.mkdir(parents=True)
        appdata = self.base / "AppData"
        exe = appdata / "YUH Studio/runtime/venv312/Scripts/python.exe"
        exe.parent.mkdir(parents=True)
        exe.touch()
        with patch.dict(os.environ, {"APPDATA": str(appdata)}):
            self.assertEqual(env._python_paths(root, None), [])
            (host / "YUH Studio.exe").touch()
            self.assertEqual(env._python_paths(root, None), [exe])

    def test_process_command_lines_are_not_returned_or_executed(self):
        root = self.installation()
        exe = self.base / "python.exe"
        records = [{"Name": "python.exe", "ExecutablePath": str(exe),
                    "CommandLine": f'"{exe}" "{root / "main.py"}" --port 9001 --token SECRET_TOKEN'}]
        result = self.discover(records=records)
        self.assertNotIn("SECRET_TOKEN", json.dumps(result))
        self.assertNotIn("CommandLine", json.dumps(result))
        self.assertTrue(any(c["url"].endswith(":9001") for c in result["candidates"]))

    def test_explicit_installation_does_not_walk_or_execute(self):
        root = self.installation()
        with patch.object(os, "walk", side_effect=AssertionError("no recursive scan")), \
                patch.object(subprocess, "run", side_effect=AssertionError("no interpreter execution")):
            result = self.discover({"comfy_roots": [str(root)]})
        self.assertEqual(result["installations"][0]["model_roots"], [str(root / "models")])
        self.assertEqual(result["installations"][0]["python"]["status"], "unknown")

    def test_metadata_only_reads_associated_environment(self):
        root = self.installation()
        exe = root / ".venv/Scripts/python.exe"
        exe.parent.mkdir(parents=True)
        exe.write_text("never execute", encoding="utf-8")
        package = root / ".venv/Lib/site-packages/torch-2.10.0.dist-info"
        package.mkdir(parents=True)
        (package / "METADATA").write_text("Name: torch\nVersion: 2.10.0\n", encoding="utf-8")
        result = self.discover({"comfy_roots": [str(root)]})
        install = result["installations"][0]
        self.assertEqual(install["python"]["path"], str(exe))
        torch = next(p for p in install["packages"] if p["name"] == "torch")
        self.assertEqual(torch, {"name": "torch", "version": "2.10.0", "status": "ok"})
        self.assertIn("未执行", install["detail"])
        self.assertNotIn(str(root), json.dumps(result["checks"], ensure_ascii=False))

    def test_package_directory_permission_error_remains_unknown(self):
        with patch.object(Path, "is_dir", side_effect=PermissionError("secret")):
            result = env._package_metadata(self.base / "python.exe")
        self.assertTrue(all(p["status"] == "unknown" for p in result))

    def test_unreadable_or_invalid_existing_metadata_stays_unknown(self):
        exe = self.base / "python.exe"
        package = self.base / "Lib/site-packages/torch-2.10.0.dist-info"
        package.mkdir(parents=True)
        metadata = package / "METADATA"
        metadata.write_text("Name: someone_else\nVersion: 1.0\n", encoding="utf-8")
        result = env._package_metadata(exe)
        self.assertEqual(next(p for p in result if p["name"] == "torch")["status"], "unknown")
        with patch.object(Path, "open", side_effect=PermissionError("secret")):
            result = env._package_metadata(exe)
        self.assertEqual(next(p for p in result if p["name"] == "torch")["status"], "unknown")

    def test_config_supports_plain_absolute_base_path_only(self):
        models = self.base / "Models"
        models.mkdir()
        config = self.base / "extra.yaml"
        config.write_text(f"main:\n  base_path: '{models}'\nother:\n  base_path: !!python/object:malicious\n", encoding="utf-8")
        self.assertEqual(env._config_roots(str(config), self.base), [models])
        self.assertEqual(env._config_roots("relative.yaml", self.base), [])
        config.write_text("x" * 65537, encoding="utf-8")
        self.assertEqual(env._config_roots(str(config), self.base), [])

    def test_invalid_settings_do_not_crash_or_scan_arbitrary_roots(self):
        for settings in ({"backend_url": []}, {"comfy_roots": "C:/"}, {"comfy_roots": [None, "../", "\\\\host\\share"]}):
            result = self.discover(settings)
            self.assertEqual(result["installations"], [])
            self.assertLessEqual(len(result["candidates"]), env.MAX_CANDIDATES)

    def test_gpu_timeout_is_not_claimed_missing_and_has_fixed_argv(self):
        with patch.object(env.shutil, "which", return_value=str(self.base / "nvidia-smi")), \
                patch.object(env, "_exists", return_value=True), \
                patch.object(env, "_run_fixed", side_effect=subprocess.TimeoutExpired("nvidia-smi", 3)) as run:
            result = env._gpu()
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(run.call_args.args[0][1:], ["--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"])
        self.assertEqual(run.call_args.args[1], 3)

    def test_gpu_response_is_validated_and_does_not_claim_cuda(self):
        with patch.object(env.shutil, "which", return_value=str(self.base / "nvidia-smi")), \
                patch.object(env, "_exists", return_value=True), \
                patch.object(env, "_run_fixed", return_value=Mock(returncode=0, stdout="NVIDIA Test, 16384, 580.1\n")):
            result = env._gpu()
        self.assertEqual(result["gpus"][0]["memory_total_mb"], 16384)
        self.assertIn("未验证", result["detail"])

    def test_process_probe_timeout_is_unknown(self):
        with patch.object(env.os, "name", "nt"), patch.object(env, "_path", return_value=self.base), \
                patch.object(env, "_exists", return_value=True), \
                patch.object(env, "_run_fixed", side_effect=subprocess.TimeoutExpired("powershell", 3)):
            self.assertEqual(env._processes(), ([], "unknown"))

    def test_hidden_fixed_command_never_uses_shell(self):
        with patch.object(subprocess, "run", return_value=Mock()) as run:
            env._run_fixed(["fixed.exe", "--fixed"], 3)
        self.assertNotIn("shell", run.call_args.kwargs)
        self.assertEqual(run.call_args.kwargs["timeout"], 3)
        self.assertEqual(run.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertEqual(run.call_args.kwargs["creationflags"], getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def test_process_port_and_candidate_counts_are_bounded(self):
        root = self.installation()
        records = [{"Name": "python.exe", "ExecutablePath": str(self.base / "python.exe"),
                    "CommandLine": f'python "{root / "main.py"}" --port {port}'} for port in range(9000, 9040)]
        result = self.discover({"backend_url": "http://127.0.0.1:8190"}, records=records)
        self.assertEqual(len(result["candidates"]), env.MAX_CANDIDATES)
        self.assertEqual(len(result["installations"]), 1)

    def test_bad_process_port_values_do_not_form_urls(self):
        root = self.installation()
        for port in ("0", "65536", "999999999", "80;Write-Output", "-1", "8.0"):
            records = [{"Name": "python.exe", "ExecutablePath": str(self.base / "python.exe"),
                        "CommandLine": f'python "{root / "main.py"}" --port {port}'}]
            self.assertEqual(env._process_hints(records)[1], [])

    def test_actual_slow_header_response_has_total_deadline(self):
        class SlowHandler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                try:
                    for byte in b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n":
                        self.wfile.write(bytes([byte]))
                        self.wfile.flush()
                        time.sleep(0.03)
                except OSError:
                    pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), SlowHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        started = time.monotonic()
        try:
            with self.assertRaises((OSError, ValueError, env.http.client.HTTPException)):
                env._request_stats(f"http://127.0.0.1:{server.server_port}", timeout=0.15)
            self.assertLess(time.monotonic() - started, 0.7)
        finally:
            server.shutdown()
            server.server_close()

    def test_http_probe_refuses_redirects_and_oversized_responses(self):
        class InvalidHandler(BaseHTTPRequestHandler):
            mode = "redirect"

            def log_message(self, *args):
                pass

            def do_GET(self):
                self.send_response(302 if self.mode == "redirect" else 200)
                self.send_header("Location", "http://example.com/")
                self.send_header("Content-Length", "999999999")
                self.end_headers()

        server = ThreadingHTTPServer(("127.0.0.1", 0), InvalidHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for mode in ("redirect", "size"):
                InvalidHandler.mode = mode
                with self.subTest(mode=mode), self.assertRaises(ValueError):
                    env._request_stats(f"http://127.0.0.1:{server.server_port}")
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
