"""Black-box loopback HTTP tests; the mock backend never performs inference."""

import base64
import copy
import http.client
import json
import re
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from frameweave.server import App, make_server


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jhXcAAAAASUVORK5CYII="
)
API_JOB = {"kind": "api", "prompt": {
    "1": {"class_type": "TestOutput", "inputs": {"text": "a quiet scene"}}
}}


class MockComfy:
    """Small independent implementation of the public endpoints needed here."""

    def __init__(self):
        self.info = {"TestOutput": {"input": {"required": {"text": ["STRING"]}},
                                    "output": [], "output_node": True}}
        self.pending = []
        self.running = []
        self.history = {}
        self.calls = []
        self.rejections = False
        self.queue_available = True
        self.next_id = 0
        self.content = bytes(range(256)) * 2048
        self.stream_gate = None
        state = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def send_json(self, value, status=200):
                payload = json.dumps(value).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self):
                parsed = urllib.parse.urlsplit(self.path)
                state.calls.append(("GET", parsed.path, self.headers.get("Range")))
                if parsed.path == "/object_info":
                    self.send_json(state.info)
                elif parsed.path == "/system_stats":
                    self.send_json({"devices": [], "system": {"comfyui_version": "test"}})
                elif parsed.path == "/queue":
                    if not state.queue_available:
                        self.send_json({"error": "temporarily unavailable"}, 503)
                    else:
                        self.send_json({"queue_pending": [[0, value] for value in state.pending],
                                        "queue_running": [[0, value] for value in state.running]})
                elif parsed.path.startswith("/history/"):
                    key = urllib.parse.unquote(parsed.path.rsplit("/", 1)[-1])
                    self.send_json({key: state.history[key]} if key in state.history else {})
                elif parsed.path == "/view":
                    query = urllib.parse.parse_qs(parsed.query)
                    if query.get("filename") != ["result.mp4"]:
                        self.send_json({"error": "unknown media"}, 404)
                        return
                    content = state.content
                    range_value = self.headers.get("Range")
                    match = re.fullmatch(r"bytes=(\d+)-(\d*)", range_value or "")
                    start, end = 0, len(content) - 1
                    if match:
                        start = int(match[1])
                        end = min(int(match[2]) if match[2] else end, end)
                        if start > end:
                            self.send_json({"error": "range not satisfiable"}, 416)
                            return
                    part = content[start:end + 1]
                    self.send_response(206 if match else 200)
                    self.send_header("Content-Type", "video/mp4")
                    self.send_header("Content-Length", str(len(part)))
                    self.send_header("Accept-Ranges", "bytes")
                    if match:
                        self.send_header("Content-Range", f"bytes {start}-{end}/{len(content)}")
                    self.end_headers()
                    first = 128 * 1024
                    try:
                        self.wfile.write(part[:first])
                        self.wfile.flush()
                        if state.stream_gate is not None and not match:
                            state.stream_gate.wait(5)
                        self.wfile.write(part[first:])
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                else:
                    self.send_json({"error": "not found"}, 404)

            def do_POST(self):
                path = urllib.parse.urlsplit(self.path).path
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                if path == "/upload/image":
                    state.calls.append(("POST", path, body))
                    match = re.search(br'filename="([^"]+)"', body)
                    self.send_json({"name": match[1].decode("ascii"), "subfolder": "", "type": "input"})
                    return
                data = json.loads(body)
                state.calls.append(("POST", path, data))
                if path == "/prompt":
                    if state.rejections:
                        self.send_json({"error": "bad graph", "node_errors": {"1": {"message": "backend rejected"}}}, 400)
                        return
                    state.next_id += 1
                    key = "job-" + str(state.next_id)
                    state.pending.append(key)
                    self.send_json({"prompt_id": key, "number": len(state.pending), "node_errors": {}})
                elif path == "/queue":
                    for key in data.get("delete", []):
                        if key in state.pending:
                            state.pending.remove(key)
                    self.send_json({})
                elif path == "/interrupt":
                    self.send_json({})
                else:
                    self.send_json({"error": "not found"}, 404)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={"poll_interval": 0.02}, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def stop(self):
        if self.stream_gate is not None:
            self.stream_gate.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)


class ServiceHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.web = self.root / "web"
        self.web.mkdir()
        (self.web / "index.html").write_text("<title>Test Canvas</title>", encoding="utf-8")
        (self.root / "private.txt").write_text("MUST_NOT_BE_SERVED", encoding="utf-8")
        self.backend = MockComfy()
        self.addCleanup(self.backend.stop)
        self.start_client()
        self.addCleanup(self.stop_client)

    def start_client(self):
        self.app = App(self.root / "data", self.web, self.backend.url)
        self.server = make_server(self.app)
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={"poll_interval": 0.02}, daemon=True)
        self.thread.start()
        self.port = self.server.server_port
        status, _, payload = self.request("GET", "/api/bootstrap")
        self.assertEqual(status, 200)
        self.token = json.loads(payload)["csrf"]

    def stop_client(self):
        self.app.closed.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def request(self, method, path, data=None, headers=None, raw=None, csrf=True):
        outgoing = {"Host": f"127.0.0.1:{self.port}"}
        body = raw
        if method == "POST":
            outgoing["Content-Type"] = "application/json"
            if csrf:
                outgoing["X-FW-Token"] = self.token
            if body is None:
                body = json.dumps({} if data is None else data).encode()
        outgoing.update(headers or {})
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        try:
            connection.request(method, path, body=body, headers=outgoing)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def post(self, path, data=None, **kwargs):
        status, headers, body = self.request("POST", path, data, **kwargs)
        return status, headers, json.loads(body)

    def submit(self):
        status, _, job = self.post("/api/jobs", copy.deepcopy(API_JOB))
        self.assertEqual(status, 200, job)
        return job

    def complete(self, job):
        key = job["id"]
        self.backend.pending.remove(key)
        self.backend.history[key] = {
            "status": {"status_str": "success", "completed": True},
            "outputs": {"1": {"videos": [{"filename": "result.mp4", "subfolder": "", "type": "output"}]}}
        }
        self.app.update_jobs()
        status, _, payload = self.request("GET", "/api/jobs")
        self.assertEqual(status, 200)
        output = next(value for value in json.loads(payload)["jobs"] if value["id"] == key)
        self.assertEqual(output["status"], "completed")
        return output["outputs"][0]["url"]

    def test_bootstrap_has_protective_headers_and_no_cors_grant(self):
        status, headers, payload = self.request("GET", "/api/bootstrap")
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(payload)["csrf"])
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_host_origin_and_csrf_reject_cross_site_access(self):
        for headers in ({"Host": "attacker.invalid"}, {"Origin": "https://attacker.invalid"},
                        {"Sec-Fetch-Site": "cross-site"}):
            with self.subTest(headers=headers):
                self.assertEqual(self.request("GET", "/api/bootstrap", headers=headers)[0], 403)
        for headers in ({"Host": "attacker.invalid"}, {"Origin": "https://attacker.invalid"},
                        {"X-FW-Token": "invalid"}):
            with self.subTest(headers=headers):
                self.assertEqual(self.post("/api/jobs", API_JOB, headers=headers)[0], 403)
        self.assertEqual(self.post("/api/jobs", API_JOB, csrf=False)[0], 403)
        self.assertEqual(self.request("OPTIONS", "/api/jobs")[0], 403)
        self.assertFalse(self.backend.calls)

    def test_bad_json_content_type_and_request_length_are_rejected(self):
        for raw in (b"{", b"[]", b"null", b'{"steps":NaN}', b'{"steps":Infinity}'):
            with self.subTest(raw=raw):
                self.assertEqual(self.post("/api/jobs", raw=raw)[0], 400)
        self.assertEqual(self.post("/api/jobs", API_JOB, headers={"Content-Type": "text/plain"})[0], 415)
        for length in ("0", "-1", str(29 * 1024 * 1024)):
            with self.subTest(length=length):
                self.assertEqual(self.post("/api/jobs", raw=b"", headers={"Content-Length": length})[0], 413)
        self.assertFalse(self.backend.calls)

    def test_settings_only_accept_local_backend_and_local_absolute_roots(self):
        bad_urls = ("https://127.0.0.1:8188", "http://example.com:8188", "http://192.168.1.1:8188",
                    "http://user:password@127.0.0.1:8188", "http://127.0.0.1:8188/path",
                    "http://127.0.0.1:8188?token=secret")
        for value in bad_urls:
            with self.subTest(url=value):
                self.assertEqual(self.post("/api/settings", {"backend_url": value})[0], 400)
        for roots in (["relative/models"], ["//server/share"], "not a list"):
            with self.subTest(roots=roots):
                status, _, _ = self.post("/api/settings", {"backend_url": self.backend.url, "model_roots": roots})
                self.assertEqual(status, 400)
        status, _, result = self.post("/api/settings", {
            "backend_url": self.backend.url.replace("127.0.0.1", "localhost"),
            "model_roots": [str(self.root), str(self.root)]})
        self.assertEqual(status, 200)
        self.assertEqual(result["settings"]["backend_url"], self.backend.url)
        saved = json.loads((self.root / "data" / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["model_roots"], [str(self.root.resolve())])

    def test_static_file_traversal_cannot_expose_sibling_files(self):
        for path in ("/../private.txt", "/%2e%2e/private.txt", "/%2e%2e%5cprivate.txt",
                     "/C%3a/private.txt", "/missing.html"):
            with self.subTest(path=path):
                status, _, body = self.request("GET", path)
                self.assertIn(status, (400, 404))
                self.assertNotIn(b"MUST_NOT_BE_SERVED", body)
        status, _, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"Test Canvas", body)

    def test_upload_uses_content_type_and_generated_name(self):
        for content in (b"<svg onload='alert(1)'/>", b"<html>not image</html>", b"MZexecutable data"):
            with self.subTest(content=content):
                status, _, _ = self.post("/api/upload", {"name": "image.png", "data": base64.b64encode(content).decode()})
                self.assertEqual(status, 400)
        self.assertEqual(self.post("/api/upload", {"data": "not base64!"})[0], 400)
        self.assertFalse(self.backend.calls)
        status, _, result = self.post("/api/upload", {
            "name": "../../injected.svg", "mime": "text/html", "data": base64.b64encode(PNG).decode()})
        self.assertEqual(status, 200, result)
        self.assertRegex(result["name"], r"^frameweave-[a-f0-9]{32}\.png$")
        self.assertRegex(result["url"], r"^/api/media/[a-f0-9]{32}$")
        uploaded = next(call[2] for call in self.backend.calls if call[:2] == ("POST", "/upload/image"))
        self.assertIn(PNG, uploaded)
        self.assertIn(b"Content-Type: image/png", uploaded)
        self.assertNotIn(b"injected.svg", uploaded)

    def test_compile_rejection_never_reaches_backend_prompt(self):
        invalid = {"kind": "api", "prompt": {"1": {"class_type": "UninstalledNode", "inputs": {}}}}
        status, _, result = self.post("/api/jobs", invalid)
        self.assertEqual(status, 400, result)
        self.assertFalse(any(call[:2] == ("POST", "/prompt") for call in self.backend.calls))
        self.assertEqual(json.loads(self.request("GET", "/api/jobs")[2])["jobs"], [])

    def test_backend_rejection_does_not_create_phantom_job_and_can_recover(self):
        self.backend.rejections = True
        status, _, result = self.post("/api/jobs", API_JOB)
        self.assertEqual(status, 502, result)
        self.assertEqual(json.loads(self.request("GET", "/api/jobs")[2])["jobs"], [])
        self.backend.rejections = False
        job = self.submit()
        self.assertEqual(job["status"], "queued")
        posted = [call[2] for call in self.backend.calls if call[:2] == ("POST", "/prompt")][-1]
        self.assertEqual(posted["prompt"], API_JOB["prompt"])
        self.assertTrue(posted["client_id"])

    def test_pending_cancel_only_deletes_owned_job(self):
        job = self.submit()
        self.backend.pending.append("foreign-job")
        status, _, _ = self.post("/api/jobs/foreign-job/cancel")
        self.assertEqual(status, 400)
        status, _, result = self.post(f"/api/jobs/{job['id']}/cancel")
        self.assertEqual(status, 200, result)
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(self.backend.pending, ["foreign-job"])
        changes = [call for call in self.backend.calls if call[:2] == ("POST", "/queue")]
        self.assertEqual([call[2] for call in changes], [{"delete": [job["id"]]}])
        self.assertFalse(any(call[:2] == ("POST", "/interrupt") for call in self.backend.calls))

    def test_running_cancel_never_uses_shared_global_interrupt(self):
        job = self.submit()
        self.backend.pending.remove(job["id"])
        self.backend.running.extend([job["id"], "foreign-running"])
        status, _, _ = self.post(f"/api/jobs/{job['id']}/cancel")
        self.assertEqual(status, 400)
        self.assertEqual(self.backend.running, [job["id"], "foreign-running"])
        self.assertFalse(any(call[0] == "POST" and call[1] in ("/queue", "/interrupt") for call in self.backend.calls))

    def test_disconnect_preserves_job_and_history_recovers_after_restart(self):
        job = self.submit()
        self.backend.queue_available = False
        self.app.update_jobs()
        jobs = json.loads(self.request("GET", "/api/jobs")[2])["jobs"]
        self.assertEqual(jobs[0]["status"], "queued")
        self.backend.queue_available = True
        self.stop_client()
        self.start_client()
        restored = json.loads(self.request("GET", "/api/jobs")[2])["jobs"]
        self.assertEqual(restored[0]["id"], job["id"])
        self.assertEqual(restored[0]["status"], "queued")
        url = self.complete(job)
        self.assertRegex(url, r"^/api/media/[a-f0-9]{32}$")

    def test_backend_change_is_blocked_until_owned_jobs_finish(self):
        job = self.submit()
        status, _, _ = self.post("/api/settings", {"backend_url": "http://127.0.0.1:9"})
        self.assertEqual(status, 400)
        self.assertEqual(self.app.backend.url, self.backend.url)
        self.post(f"/api/jobs/{job['id']}/cancel")
        self.assertEqual(self.post("/api/settings", {"backend_url": "http://127.0.0.1:9"})[0], 200)

    def test_unowned_media_cannot_proxy_backend_arbitrary_files(self):
        status, _, _ = self.request("GET", "/api/media/" + "0" * 32 + "?filename=private.txt")
        self.assertEqual(status, 404)
        self.assertFalse(any(call[:2] == ("GET", "/view") for call in self.backend.calls))

    def test_owned_result_media_forwards_range_and_exact_bytes(self):
        url = self.complete(self.submit())
        status, headers, content = self.request("GET", url, headers={"Range": "bytes=17-300"})
        self.assertEqual(status, 206)
        self.assertEqual(content, self.backend.content[17:301])
        self.assertEqual(headers["Content-Range"], f"bytes 17-300/{len(self.backend.content)}")
        self.assertEqual(headers["Accept-Ranges"], "bytes")
        self.assertEqual(headers["Content-Type"], "video/mp4")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertIn(("GET", "/view", "bytes=17-300"), self.backend.calls)

    def test_owned_media_streams_before_backend_finishes_body(self):
        url = self.complete(self.submit())
        gate = threading.Event()
        self.backend.stream_gate = gate
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
        try:
            connection.request("GET", url)
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            prefix = response.read(64)
            self.assertEqual(prefix, self.backend.content[:64])
            self.assertFalse(gate.is_set(), "first bytes must arrive before backend is allowed to finish")
            gate.set()
            self.assertEqual(prefix + response.read(), self.backend.content)
        finally:
            gate.set()
            connection.close()


if __name__ == "__main__":
    unittest.main()
