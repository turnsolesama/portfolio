"""Reproducible inputs; self-contained local Windows distribution."""
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import imageio_ffmpeg

ROOT = Path(__file__).resolve().parent
WORK = ROOT / ".build"
RELEASE = ROOT / "releases"
VERSION = "0.3.0"
DIST = RELEASE / f"VideoCatch-v{VERSION}"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    RELEASE.mkdir(exist_ok=True)
    tools = WORK / "tools"
    tools.mkdir(parents=True, exist_ok=True)
    shutil.copy2(imageio_ffmpeg.get_ffmpeg_exe(), tools / "ffmpeg.exe")
    subprocess.run([sys.executable, str(ROOT / "prepare_runtime.py")], check=True)
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--name", "VideoCatch",
                    "--icon", str(ROOT / "assets" / "videocatch.ico"), "--add-data", f"{ROOT / 'assets'};assets",
                    "--distpath", str(DIST), "--workpath", str(WORK / "pyinstaller"), "--specpath", str(WORK),
                    "--collect-all", "yt_dlp", "--collect-all", "yt_dlp_ejs", "--exclude-module", "imageio_ffmpeg", "--add-binary", f"{tools / 'ffmpeg.exe'};tools", "--add-binary", f"{tools / 'deno.exe'};tools",
                    str(ROOT / "app.py")], check=True, cwd=ROOT)
    target = DIST / "VideoCatch"
    shutil.copytree(ROOT / "extension", target / "extension", dirs_exist_ok=True)
    shutil.copytree(ROOT / "assets", target / "assets", dirs_exist_ok=True)
    for name in ["README.md", "使用指南.html", "TEST-REPORT.md"]:
        shutil.copy2(ROOT / name, target / name)
    licenses = target / "licenses"
    licenses.mkdir(exist_ok=True)
    shutil.copytree(ROOT / "licenses", licenses, dirs_exist_ok=True)
    packages = ["yt-dlp", "yt-dlp-ejs", "imageio-ffmpeg", "pyinstaller", "certifi", "requests", "urllib3", "mutagen", "brotli", "pycryptodomex", "websockets", "charset-normalizer", "idna"]
    for package in packages:
        dist = metadata.distribution(package)
        for file in dist.files or []:
            if "license" in file.name.lower() or "copying" in file.name.lower():
                src = Path(dist.locate_file(file))
                if src.is_file():
                    shutil.copy2(src, licenses / f"{package}-{file.name}")
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.exists():
        shutil.copy2(python_license, licenses / "Python-LICENSE.txt")
    (licenses / "THIRD_PARTY.md").write_text(
        "# Components\n\nPython: https://www.python.org/ (PSF license).\n"
        "Tcl/Tk: https://www.tcl-lang.org/ (BSD-style license; runtime license files included).\n"
        "yt-dlp: https://github.com/yt-dlp/yt-dlp (Unlicense).\n"
        "PyInstaller: https://pyinstaller.org/ (GPL with bootloader distribution exception).\n"
        "imageio-ffmpeg: https://github.com/imageio/imageio-ffmpeg (BSD-2-Clause).\n"
        "Deno 2.9.6: https://github.com/denoland/deno/tree/v2.9.6 (MIT).\n"
        "yt-dlp-ejs: https://github.com/yt-dlp/ejs (Unlicense).\n"
        "Bundled FFmpeg is supplied unmodified by imageio-ffmpeg 0.6.0 Windows wheel. "
        "FFmpeg is LGPL/GPL depending on enabled components; see the included binary license and build configuration. "
        "Build/source information: https://github.com/imageio/imageio-binaries and https://ffmpeg.org/download.html .\n",
        encoding="utf-8")
    (licenses / "FFmpeg-build.txt").write_bytes(subprocess.check_output([str(tools / "ffmpeg.exe"), "-version"]))
    (licenses / "FFmpeg-license.txt").write_bytes(subprocess.check_output([str(tools / "ffmpeg.exe"), "-L"], stderr=subprocess.STDOUT))
    files = {str(p.relative_to(target)).replace("\\", "/"): {"bytes": p.stat().st_size, "sha256": digest(p)}
             for p in target.rglob("*") if p.is_file() and p.name != "runtime-manifest.json"}
    manifest = {"version": VERSION, "python": sys.version.split()[0], "components": {**{p: metadata.version(p) for p in packages}, "deno": "2.9.6"}, "files": files}
    (target / "runtime-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    archive = RELEASE / f"VideoCatch-v{VERSION}-Windows-x64.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(target.rglob("*")):
            if p.is_file():
                z.write(p, str(p.relative_to(DIST)))
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert {p.split("/")[0] for p in z.namelist()} == {"VideoCatch"}
    info = {"file": archive.name, "bytes": archive.stat().st_size, "sha256": digest(archive), "zip_integrity": "passed", "root": "VideoCatch"}
    (RELEASE / f"checksums-v{VERSION}.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    extension_archive = RELEASE / f"VideoCatch-Extension-v{VERSION}.zip"
    with zipfile.ZipFile(extension_archive, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted((ROOT / "extension").iterdir()):
            if p.is_file(): z.write(p, "VideoCatch-extension/" + p.name)
    extension_info = {"file": extension_archive.name, "bytes": extension_archive.stat().st_size, "sha256": digest(extension_archive), "root": "VideoCatch-extension"}
    with zipfile.ZipFile(extension_archive) as z:
        assert z.testzip() is None
    (RELEASE / f"extension-checksums-v{VERSION}.json").write_text(json.dumps(extension_info, indent=2), encoding="utf-8")
    print(json.dumps(info, indent=2))
    print(json.dumps(extension_info, indent=2))


if __name__ == "__main__":
    main()
