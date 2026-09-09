"""Build source and Windows packages from an explicit application-file allowlist."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import zipfile

VERSION = "2.4.0"
ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = ("server.py", "launcher.pyw", "start.vbs", "start.bat", "debug.bat", ".gitignore", "THIRD_PARTY_NOTICES.md")
SUBDIRS = {"aihub": {".py"}, "frontend": {".js", ".html", ".css", ".svg", ".ico"},
           "desktop": {".py", ".cs", ".manifest", ".txt", ".md"},
           "tests": {".py", ".js"}, "tools": {".py"}, "docs": {".md"}}
EXCLUDED_PARTS = {"data", "backups", "vendor", "runtime", "__pycache__", "_tmp", ".git"}


def source_files(root):
    root = Path(root).resolve()
    files = {}

    def add(name, path):
        if path.is_symlink():
            raise ValueError("Symlinks must not enter a release: " + name)
        resolved = path.resolve().relative_to(root)
        if EXCLUDED_PARTS.intersection(resolved.parts):
            raise ValueError("Excluded release location: " + name)
        files[name] = path.read_bytes()

    for name in ROOT_FILES:
        add(name, root / name)
    for folder, extensions in SUBDIRS.items():
        for path in sorted((root / folder).rglob("*")):
            if path.is_file() and path.suffix.lower() in extensions and not EXCLUDED_PARTS.intersection(path.relative_to(root).parts):
                add(path.relative_to(root).as_posix(), path)
    add("README.md", root / "docs/DISTRIBUTION_README.md")
    add("AGENTS.md", root / "docs/REPOSITORY_AGENTS.md")
    # The workstation's migration logs and personal inventory are never included.
    return files


def check_exe(data):
    if len(data) < 256 or data[:2] != b"MZ":
        raise ValueError("Expected a Windows executable")
    pe = struct.unpack_from("<I", data, 0x3c)[0]
    if pe + 96 > len(data) or data[pe:pe + 4] != b"PE\0\0":
        raise ValueError("Invalid PE header")
    if struct.unpack_from("<H", data, pe + 4)[0] != 0x8664:
        raise ValueError("Expected an x64 executable")
    if struct.unpack_from("<H", data, pe + 24 + 68)[0] != 2:
        raise ValueError("Expected a Windows GUI executable without a console")


def write_archive(path, files, version, kind):
    manifest = {"version": version, "kind": kind, "user_data_included": False,
                "files": [{"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                          for name, data in sorted(files.items())]}
    entries = {**files, "manifest.json": json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")}
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo("AI-Hub/" + name, date_time=(2026, 9, 7, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)
    return {"name": path.name, "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "files": len(entries), "kind": kind}


def build(root, output, exe, version=VERSION):
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[a-zA-Z0-9.]+)?", version):
        raise ValueError("Invalid release version")
    files = source_files(root)
    binary = Path(exe).read_bytes()
    check_exe(binary)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    release = {"version": version, "packages": []}
    for kind, contents in (("Source", files), ("Windows-x64", {**files, "AI Hub.exe": binary})):
        target = output / f"AI-Hub-v{version}-{kind}.zip"
        release["packages"].append(write_archive(target, contents, version, kind))
    manifest_path = output / f"AI-Hub-v{version}-release.json"
    manifest_path.write_text(json.dumps(release, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / f"AI-Hub-v{version}-SHA256.txt").write_text(
        "".join(f"{item['sha256']}  {item['name']}\n" for item in release["packages"]), encoding="utf-8")
    return release


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "releases")
    parser.add_argument("--version", default=VERSION)
    args = parser.parse_args()
    print(json.dumps(build(ROOT, args.output, args.exe, args.version), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
