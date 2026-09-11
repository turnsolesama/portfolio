"""Local-only interactive extension fixture. Stops when .build/browser-stop exists."""
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import Store, start_bridge
from engine import ffmpeg_path
from pages import bili_page


def main():
    root = Path(__file__).resolve().parents[1] / ".build"
    fixtures = root / "fixtures"
    fixtures.mkdir(exist_ok=True)
    video = fixtures / "sample.mp4"
    if not video.exists():
        subprocess.run([ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=160x90:rate=15", "-f", "lavfi", "-i", "sine=frequency=440", "-t", "3", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(video)], check=True)
    for name in ["watched", "unwatched"]:
        (fixtures / f"{name}.html").write_text(f'<!doctype html><title>{name} fixture</title><h1>{name}</h1><video controls preload="none" src="sample.mp4?source={name}"></video><button onclick="document.querySelector(\'video\').play()">Play fixture</button>', encoding="utf-8")
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *_): pass
    server = ThreadingHTTPServer(("127.0.0.1", 18797), functools.partial(Quiet, directory=str(fixtures)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    store = Store()
    bridge = start_bridge(store)
    (root / "test-pairing.txt").write_text(bridge.token)
    print("Fixture ready on 18797, bridge on 18796", flush=True)
    try:
        for _ in range(1200):
            if (root / "browser-stop").exists():
                break
            tabs, items, clients = store.snapshot()
            for tab in tabs:
                is_target = len(sys.argv) > 1 and bili_page(tab["url"]) == bili_page(sys.argv[1])
                if (tab["url"].endswith("/watched.html") or is_target) and not tab["watching"]:
                    store.toggle([tab["key"]])
            (root / "browser-result.json").write_text(json.dumps({"clients": clients, "tabs": tabs, "items": items}, ensure_ascii=False, indent=2), encoding="utf-8")
            time.sleep(.5)
    finally:
        bridge.shutdown()
        bridge.server_close()
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
