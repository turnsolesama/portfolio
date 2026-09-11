"""Per-download network preferences. Does not change system/browser settings."""
from concurrent.futures import ThreadPoolExecutor
import socket
from urllib.parse import urlsplit
from urllib.request import build_opener, ProxyHandler, Request

SYSTEM = "自动（系统设置）"
DIRECT = "直连"


def proxy_value(value):
    value = (value or "").strip()
    if not value or value == SYSTEM:
        return None
    if value == DIRECT:
        return ""
    if "://" not in value:
        value = "http://" + value
    try:
        p = urlsplit(value)
        if p.scheme not in {"http", "https", "socks5", "socks5h"} or not p.hostname or not p.port or p.path not in {"", "/"} or p.query or p.fragment:
            raise ValueError()
    except ValueError:
        raise ValueError("代理地址格式应为 http://127.0.0.1:端口 或 socks5://127.0.0.1:端口") from None
    return value.rstrip("/")


def discover_local_proxies():
    # Common local client ports only; no remote scanning and no personal config reading.
    def check(port):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=.2):
                pass
            proxy = f"http://127.0.0.1:{port}"
            opener = build_opener(ProxyHandler({"http": proxy, "https": proxy}))
            request = Request("https://www.youtube.com/generate_204", headers={"User-Agent": "VideoCatch"})
            with opener.open(request, timeout=5) as response:
                return proxy if response.status in {200, 204} else None
        except Exception:
            return None
    with ThreadPoolExecutor(max_workers=5) as pool:
        return [p for p in pool.map(check, [7897, 7890, 10809, 2080, 8080]) if p]
