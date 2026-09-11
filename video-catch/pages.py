"""Page identity and a narrow schema for browser-observed media tracks."""
from urllib.parse import urlsplit, parse_qs, urlencode, urlunsplit
import re


def youtube_page(url):
    p = urlsplit(url)
    if p.hostname in {"youtu.be", "www.youtu.be"}:
        ident = p.path.strip("/")
    elif p.hostname in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}:
        if p.path == "/watch":
            ident = parse_qs(p.query).get("v", [""])[0]
        elif p.path.startswith(("/shorts/", "/live/", "/embed/")):
            ident = p.path.strip("/").split("/")[-1]
        else:
            return None
    else:
        return None
    return f"https://www.youtube.com/watch?v={ident}" if re.fullmatch(r"[a-zA-Z0-9_-]{11}", ident) else None


def video_page(url):
    return bili_page(url) or youtube_page(url)


def bili_page(url):
    p = urlsplit(url)
    if p.hostname not in {"www.bilibili.com", "m.bilibili.com", "bilibili.com"}:
        return None
    match = re.fullmatch(r"/video/(BV[a-zA-Z0-9]+|av[0-9]+)/?", p.path)
    episode = re.fullmatch(r"/bangumi/play/(ep[0-9]+|ss[0-9]+)/?", p.path)
    if not match and not episode:
        return None
    part = parse_qs(p.query).get("p", ["1"])[0]
    query = urlencode({"p": int(part)}) if part.isdigit() and 1 < int(part) < 100000 else ""
    return urlunsplit(("https", "www.bilibili.com", p.path.rstrip("/") + "/", query, ""))


def observed_formats(data):
    # Never forward arbitrary page-supplied yt-dlp options or local-file protocols.
    from core import http_url
    if not isinstance(data, list) or len(data) > 100:
        return []
    result = []
    for row in data:
        if not isinstance(row, dict) or row.get("drm") or row.get("has_drm"):
            continue
        try:
            url = http_url(row.get("url"))
        except ValueError:
            continue
        role = row.get("role")
        if role not in {"video", "audio", "combined"}:
            continue
        item = {"url": url, "role": role}
        for field in ("width", "height", "bandwidth"):
            v = row.get(field)
            if isinstance(v, (int, float)) and 0 < v < 1_000_000_000:
                item[field] = int(v)
        codec = row.get("codec", "")
        if isinstance(codec, str) and re.fullmatch(r"[a-zA-Z0-9.,_-]{1,100}", codec):
            item["codec"] = codec
        result.append(item)
    roles = {r["role"] for r in result}
    # A single DASH video track is not a finished video with sound.
    return result if "combined" in roles or {"video", "audio"} <= roles else []


def downloader_formats(rows):
    result = []
    for index, row in enumerate(observed_formats(rows)):
        audio = row["role"] == "audio"
        fmt = {"url": row["url"], "format_id": str(index), "ext": "m4a" if audio else "mp4",
               "protocol": "https" if row["url"].startswith("https:") else "http"}
        if audio:
            fmt.update(vcodec="none", acodec=row.get("codec", "mp4a.40.2"))
        elif row["role"] == "video":
            fmt.update(acodec="none", vcodec=row.get("codec", "avc1"))
        for field in ("width", "height"):
            if field in row: fmt[field] = row[field]
        if "bandwidth" in row: fmt["tbr"] = row["bandwidth"] / 1000
        result.append(fmt)
    return result
