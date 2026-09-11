"""Package an explicit public-file allowlist; include only verified private runtime archives, never user data."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = '0.4.0'
FIXED = (
    'README.md', 'RUNNING.md', 'LICENSE', 'AGENTS.md', 'API_CONTRACT.md', '.gitignore',
    'server.py', 'launcher.pyw', 'start.vbs', 'Stop-YingXu.ps1', 'YingXu.exe',
    'desktop/RuntimeCheck.cs', 'desktop/Core.cs', 'desktop/Program.cs', 'desktop/Tests.cs', 'desktop/build.py',
    'desktop/Integration.cs', 'desktop/Set-OpenWith.ps1', 'desktop/LifecycleTests.cs',
    'desktop/Capture.cs', 'desktop/CaptureTests.cs',
    'tools/markdown-editor/package.json', 'tools/markdown-editor/package-lock.json', 'tools/markdown-editor/build.mjs',
    'frontend/live-markdown-source.mjs', 'frontend/live-markdown.LICENSE.txt', 'frontend/live-markdown.manifest.json',
    'desktop/make_icon.py', 'desktop/brand.svg', 'desktop/brand.ico',
    'desktop/app.manifest', 'desktop/WebView2-LICENSE.txt',
    'tools/benchmark.py', 'tools/package_release.py', 'tools/verify_release.py',
    'tools/prepare_runtime.py', 'tools/runtime-lock.json', 'THIRD_PARTY_NOTICES.md',
    'docs/完整包验收.md', 'docs/功能指南.md', 'docs/安装与运行.md', 'docs/开发说明.md', 'docs/assets/workspace-map.svg',
)
PATTERNS = ('yingxu/*.py', 'frontend/*.html', 'frontend/*.css', 'frontend/*.js',
            'tests/test_*.py', 'tests/frontend_*.cjs')
TEXT_SUFFIXES = {'.md', '.py', '.pyw', '.js', '.cjs', '.mjs', '.css', '.html', '.cs', '.ps1', '.vbs', '.json', '.txt', '.manifest', '.svg'}


def files_to_package():
    paths = {ROOT / relative for relative in FIXED}
    for pattern in PATTERNS:
        paths.update(ROOT.glob(pattern))
    for path in sorted(paths):
        if not path.is_file() or path.is_symlink():
            raise ValueError(f'Missing or unsafe release member: {path.relative_to(ROOT)}')
        if path.suffix in TEXT_SUFFIXES:
            raw = path.read_bytes()
            text = raw.decode('utf-16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig')
            if re.search(r'(?i)(?:[A-Z]:[\\/]Users[\\/](?!Public(?:[\\/]|$))|F:[\\/]AI(?:[\\/]|$))', text):
                raise ValueError(f'Personal absolute path in {path.relative_to(ROOT)}')
        yield path


def runtime_files(folder):
    manifest = folder / 'RUNTIME_MANIFEST.json'
    data = json.loads(manifest.read_text(encoding='utf-8'))
    if data['sources'] != json.loads((ROOT / 'tools/runtime-lock.json').read_text(encoding='utf-8')):
        raise ValueError('Runtime source lock differs from release')
    expected = {'RUNTIME_MANIFEST.json'}
    for item in data['files']:
        path = folder / item['path']
        if not path.resolve().is_relative_to(folder.resolve()) or path.is_symlink():
            raise ValueError('Unsafe runtime member')
        if path.stat().st_size != item['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('Modified runtime member: ' + item['path'])
        expected.add(item['path'])
        yield path, 'runtime/' + item['path']
    actual = {p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()}
    if actual != expected:
        raise ValueError('Unlisted files in runtime; do not package a used environment')
    yield manifest, 'runtime/RUNTIME_MANIFEST.json'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-dir', type=Path, default=ROOT / 'runtime')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'releases')
    args = parser.parse_args()
    target = args.output_dir
    target.mkdir(exist_ok=True)
    package = target / f'YingXu-v{VERSION}-Windows-x64.zip'
    paths = [(p, p.relative_to(ROOT).as_posix()) for p in files_to_package()]
    paths += list(runtime_files(args.runtime_dir))
    manifest = {
        'application': 'YingXu', 'version': VERSION, 'root': 'YingXu/',
        'architecture': 'Windows x64', 'python_bundled': True,
        'requirements': ['Windows 10 22H2 / Windows 11 x64'],
        'bundled': ['CPython 3.13.15', 'Pillow 12.3.0', 'FFmpeg 9.0.1', 'WebView2 152.0.4191.62 x64'],
        'system_component': '.NET Framework 4.8, included in supported Windows versions',
        'files': [{'path': name, 'bytes': p.stat().st_size,
                   'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p, name in paths],
    }
    with zipfile.ZipFile(package, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, name in paths:
            archive.write(path, 'YingXu/' + name)
        archive.writestr('YingXu/RELEASE_MANIFEST.json', json.dumps(manifest, ensure_ascii=False, indent=2))
    result = {'file': package.name, 'version': VERSION, 'bytes': package.stat().st_size,
              'sha256': hashlib.sha256(package.read_bytes()).hexdigest(),
              'entries': len(paths) + 1, 'root': 'YingXu/', 'contains_user_data': False,
              'python_bundled': True}
    (target / f'YingXu-v{VERSION}-manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    (target / f'YingXu-v{VERSION}-SHA256.txt').write_text(f"{result['sha256']}  {package.name}\n", encoding='ascii')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
