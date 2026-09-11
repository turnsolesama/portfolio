"""Download worker runs in a separate process; never persists request data."""
import hashlib
import os
from pathlib import Path
import re
import sys
import time

from core import http_url, safe_headers
from pages import downloader_formats
from network import proxy_value


def javascript_runtimes():
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    for path in [root / "tools" / "deno.exe", root / ".build" / "tools" / "deno.exe"]:
        if path.is_file():
            return {"deno": {"path": str(path)}}
    return {"deno": {}}


def ffmpeg_path():
    bundled = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "tools" / "ffmpeg.exe"
    if bundled.exists():
        return str(bundled)
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return None


def clean_error(error):
    text = re.sub(r"\x1b\[[0-9;]*m", "", str(error))
    text = re.sub(r"https?://\S+", "[视频地址]", text)
    return text[-900:]


def download_worker(item, folder, events):
    import yt_dlp
    ident = item["id"]

    def send(**fields):
        events.put((ident, fields))

    class Logger:
        def debug(self, *_): pass
        def warning(self, *_): pass
        def error(self, *_): pass

    last = [0.0]
    result_path = [None]

    def progress(d):
        now = time.monotonic()
        if d["status"] == "finished":
            send(status="整理文件", progress="下载完成，正在检查 / 合并")
        elif d["status"] == "downloading" and now - last[0] > .25:
            last[0] = now
            done = d.get("downloaded_bytes") or 0
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            pct = f"{100 * done / total:.1f}%" if total else f"{done / 1048576:.1f} MB"
            rate = d.get("speed") or 0
            send(status="下载中", progress=f"{pct} · {rate / 1048576:.1f} MB/s")

    def finished(filename):
        result_path[0] = filename

    try:
        url = http_url(item["url"])
        folder = Path(folder).resolve()
        folder.mkdir(parents=True, exist_ok=True)
        options = {
            "format": "bestvideo*+bestaudio/best", "noplaylist": True, "playlistend": 1,
            "paths": {"home": str(folder)},
            "outtmpl": {"default": f"%(title).100s [{ident}] [%(id).50s].%(ext)s"},
            "windowsfilenames": True, "trim_file_name": 190, "overwrites": False,
            "continuedl": True, "cachedir": False, "socket_timeout": 20,
            "retries": 3, "fragment_retries": 3, "skip_unavailable_fragments": False,
            "logger": Logger(), "progress_hooks": [progress], "post_hooks": [finished],
            "http_headers": safe_headers(item.get("headers", {})),
            "quiet": True, "noprogress": True, "allow_unplayable_formats": False,
            "hls_prefer_native": True,
            "js_runtimes": javascript_runtimes(),
        }
        proxy = proxy_value(item.get("proxy"))
        if proxy is not None:
            options["proxy"] = proxy
        ffmpeg = ffmpeg_path()
        if ffmpeg:
            options["ffmpeg_location"] = ffmpeg
        send(status="解析中", progress="正在获取原始媒体")
        with yt_dlp.YoutubeDL(options) as downloader:
            formats = downloader_formats(item.get("formats", []))
            if formats:
                send(status="下载中", progress="下载浏览器已获取的音视频轨道，完成后合并")
                downloader.process_ie_result({"id": ident, "title": item.get("title") or ident,
                                              "webpage_url": url, "extractor": "VideoCatchBrowser",
                                              "formats": formats}, download=True)
            else:
                downloader.extract_info(url, download=True)
        if not result_path[0] or not Path(result_path[0]).is_file():
            raise RuntimeError("没有生成完整视频文件；此来源可能不是可下载的视频")
        send(status="已保存", progress="100%", path=str(Path(result_path[0]).resolve()), error="")
    except Exception as exc:
        message = clean_error(exc)
        if "timed out" in message.lower() or "timeout" in message.lower():
            message = "连接超时。若浏览器能播放，请点击「检测本机代理」或填写可用代理后重试。\n" + message
        send(status="失败", progress="可重新选择后重试", error=message)
