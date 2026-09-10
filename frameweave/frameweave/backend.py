"""Small, loopback-only ComfyUI HTTP adapter. No third-party runtime code."""

import ipaddress
import json
import urllib.error
import urllib.parse
import urllib.request


class BackendError(RuntimeError):
    pass


def local_url(value):
    if not isinstance(value, str) or len(value) > 200:
        raise ValueError("后端地址无效")
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme != "http" or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("初版后端仅支持本机 http 地址，不允许凭据、查询参数")
    if parsed.path not in ("", "/"):
        raise ValueError("后端地址不可包含路径")
    host = parsed.hostname
    if host == "localhost":
        host = "127.0.0.1"
    try:
        if not ipaddress.ip_address(host).is_loopback:
            raise ValueError()
        port = parsed.port or 80
    except (ValueError, TypeError):
        raise ValueError("初版只连接本机回环地址，例如 http://127.0.0.1:8188") from None
    return f"http://{'[' + host + ']' if ':' in host else host}:{port}"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise BackendError("后端重定向已拒绝，请填写直接的本机服务地址")


class Backend:
    def __init__(self, url):
        self.url = local_url(url)
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def request(self, path, data=None, *, timeout=12, raw=False, headers=None, limit=32 * 1024 * 1024):
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("后端路径无效")
        request_headers = dict(headers or {})
        if data is not None and not isinstance(data, bytes):
            data = json.dumps(data, ensure_ascii=False).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.url + path, data=data, headers=request_headers)
        try:
            with self.opener.open(req, timeout=timeout) as response:
                body = response.read(limit + 1)
                if len(body) > limit:
                    raise BackendError("后端响应过大")
                if raw:
                    return body, response.headers.get("Content-Type", "application/octet-stream")
                return json.loads(body)
        except urllib.error.HTTPError as exc:
            detail = exc.read(65536).decode("utf-8", "replace")
            try:
                payload = json.loads(detail)
                detail = json.dumps(payload, ensure_ascii=False)
            except ValueError:
                pass
            raise BackendError(f"后端 HTTP {exc.code}: {detail[:5000]}") from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, RecursionError) as exc:
            raise BackendError(f"无法读取推理后端：{exc}") from None

    def upload(self, name, content, mime):
        import uuid
        boundary = "FrameWeave" + uuid.uuid4().hex
        # Only generated ASCII filenames enter multipart headers.
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{name}\"\r\n"
                f"Content-Type: {mime}\r\n\r\n").encode() + content
        body += (f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\nfalse\r\n--{boundary}--\r\n").encode()
        return self.request("/upload/image", body, timeout=60,
                            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
