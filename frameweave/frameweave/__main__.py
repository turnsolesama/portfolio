import argparse
import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

from .server import App, make_server


def main():
    parser = argparse.ArgumentParser(description="FrameWeave 帧织 · 轻量本地 AI 画布")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--backend")
    parser.add_argument("--model-root", action="append")
    parser.add_argument("--data-dir")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    data = Path(args.data_dir) if args.data_dir else Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share")) / "FrameWeave"
    app = App(data, base / "web", args.backend, args.model_root)
    try:
        server = make_server(app, args.port)
    except OSError:
        server = make_server(app, 0)
    url = f"http://127.0.0.1:{server.server_port}/"
    (data / "last-url.txt").write_text(url, encoding="utf-8")
    if sys.stdout:
        print(f"FrameWeave: {url}\nData: {data}", flush=True)
    threading.Thread(target=app.poll, daemon=True).start()
    if not args.no_browser:
        edge_paths = [Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
                      Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Microsoft/Edge/Application/msedge.exe"]
        edge = next((p for p in edge_paths if p.is_file()), None)
        if edge:
            subprocess.Popen([str(edge), "--app=" + url, "--window-size=1500,960", "--no-first-run"],
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            webbrowser.open(url)
        # Closing the canvas releases its service after a short idle grace period.
        # Backend generation continues; launch the client again to recover owned jobs.
        def idle_exit():
            while not app.closed.wait(15):
                if time.monotonic() - app.last_seen > 180:
                    app.closed.set()
                    server.shutdown()
        threading.Thread(target=idle_exit, daemon=True).start()
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        app.closed.set()
        server.server_close()


if __name__ == "__main__":
    main()
