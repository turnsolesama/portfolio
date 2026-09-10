"""Prepare only pinned upstream archives; never copy an installed environment.

Downloads are an explicit developer build step, not application startup behavior.
The default is offline: put the lock file's archives in --cache first.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / 'tools' / 'runtime-lock.json'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def unpack(archive, target):
    with zipfile.ZipFile(archive) as source:
        for entry in source.infolist():
            name = PurePosixPath(entry.filename)
            if name.is_absolute() or '..' in name.parts or '\\' in entry.filename or ':' in entry.filename:
                raise ValueError('Unsafe upstream archive member')
        if source.testzip():
            raise ValueError('Upstream ZIP checksum failed')
        source.extractall(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--download', action='store_true')
    parser.add_argument('--output', type=Path, default=ROOT / 'runtime')
    args = parser.parse_args()
    lock = json.loads(LOCK.read_text(encoding='utf-8'))
    args.cache.mkdir(parents=True, exist_ok=True)
    for name, entry in lock.items():
        archive = args.cache / entry['file']
        if not archive.is_file() and args.download:
            temporary = archive.with_suffix('.partial')
            request = urllib.request.Request(entry['url'], headers={'User-Agent': 'YingXu-release-builder'})
            with urllib.request.urlopen(request, timeout=180) as response, temporary.open('wb') as output:
                shutil.copyfileobj(response, output)
            temporary.replace(archive)
        if not archive.is_file() or archive.stat().st_size != entry['bytes'] or digest(archive) != entry['sha256']:
            raise ValueError('Missing or mismatched pinned archive: ' + name)
    target = args.output.resolve()
    if target.exists():
        raise ValueError('Use a new output directory; existing runtimes are never overwritten')
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='yingxu-runtime-build-', dir=target.parent) as temporary:
        base = Path(temporary)
        stage = base / 'runtime'
        unpack(args.cache / lock['python']['file'], stage)
        # Explicit app-relative import paths, no registry, environment, user site or pip.
        pth = next(stage.glob('python*._pth'))
        pth.write_text(pth.stem + '.zip\n.\n..\nLib/site-packages\n', encoding='ascii')
        unpack(args.cache / lock['pillow']['file'], stage / 'Lib' / 'site-packages')
        unpack(args.cache / lock['ffmpeg']['file'], base / 'ffmpeg')
        ffroot = next((base / 'ffmpeg').iterdir())
        shutil.copytree(ffroot, stage / 'ffmpeg')
        # ffprobe and ffplay are upstream companion tools, not used by YingXu.
        for name in ('ffprobe.exe', 'ffplay.exe'):
            (stage / 'ffmpeg' / 'bin' / name).unlink(missing_ok=True)
        browser = base / 'browser'
        browser.mkdir()
        subprocess.run(['expand.exe', str((args.cache / lock['webview2']['file']).resolve()), '-F:*', str(browser)],
                       check=True, stdout=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        browser_root = next(browser.rglob('msedgewebview2.exe')).parent
        shutil.copytree(browser_root, stage / 'webview2')
        shutil.copy2(ROOT / 'THIRD_PARTY_NOTICES.md', stage / 'THIRD_PARTY_NOTICES.md')
        inventory = [{'path': p.relative_to(stage).as_posix(), 'bytes': p.stat().st_size, 'sha256': digest(p)}
                     for p in sorted(stage.rglob('*')) if p.is_file()]
        (stage / 'RUNTIME_MANIFEST.json').write_text(json.dumps({'sources': lock, 'files': inventory}, indent=2), encoding='utf-8')
        shutil.move(str(stage), str(target))
    print(json.dumps({'runtime': str(target), 'files': len(inventory), 'bytes': sum(p['bytes'] for p in inventory)}))


if __name__ == '__main__':
    main()
