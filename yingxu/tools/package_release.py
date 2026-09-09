"""Package an explicit public-file allowlist; never include runtime/user data."""
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = '0.2.1'
FIXED = (
    'README.md', 'RUNNING.md', 'LICENSE', 'AGENTS.md', 'API_CONTRACT.md', '.gitignore',
    'server.py', 'launcher.pyw', 'start.vbs', 'Stop-YingXu.ps1', 'YingXu.exe',
    'desktop/Core.cs', 'desktop/Program.cs', 'desktop/Tests.cs', 'desktop/build.py',
    'desktop/make_icon.py', 'desktop/brand.svg', 'desktop/brand.ico',
    'desktop/app.manifest', 'desktop/WebView2-LICENSE.txt',
    'tools/benchmark.py', 'tools/package_release.py', 'tools/verify_release.py',
    'docs/功能指南.md', 'docs/安装与运行.md', 'docs/开发说明.md', 'docs/assets/workspace-map.svg',
)
PATTERNS = ('yingxu/*.py', 'frontend/*.html', 'frontend/*.css', 'frontend/*.js',
            'tests/test_*.py', 'tests/frontend_context_menu.cjs')
TEXT_SUFFIXES = {'.md', '.py', '.pyw', '.js', '.cjs', '.css', '.html', '.cs', '.ps1', '.vbs', '.json', '.txt', '.manifest', '.svg'}


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


def main():
    target = ROOT / 'releases'
    target.mkdir(exist_ok=True)
    package = target / f'YingXu-v{VERSION}-Windows-x64.zip'
    paths = list(files_to_package())
    manifest = {
        'application': 'YingXu', 'version': VERSION, 'root': 'YingXu/',
        'architecture': 'Windows x64', 'python_bundled': False,
        'requirements': ['Windows 10/11 x64', 'Python >=3.11', '.NET Framework >=4.8', 'Microsoft Edge WebView2 Runtime'],
        'optional': ['Pillow for image thumbnails', 'FFmpeg on PATH for video thumbnails'],
        'files': [{'path': p.relative_to(ROOT).as_posix(), 'bytes': p.stat().st_size,
                   'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths],
    }
    with zipfile.ZipFile(package, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in paths:
            archive.writestr('YingXu/' + path.relative_to(ROOT).as_posix(), path.read_bytes())
        archive.writestr('YingXu/RELEASE_MANIFEST.json', json.dumps(manifest, ensure_ascii=False, indent=2))
    result = {'file': package.name, 'version': VERSION, 'bytes': package.stat().st_size,
              'sha256': hashlib.sha256(package.read_bytes()).hexdigest(),
              'entries': len(paths) + 1, 'root': 'YingXu/', 'contains_user_data': False,
              'python_bundled': False}
    (target / f'YingXu-v{VERSION}-manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    (target / f'YingXu-v{VERSION}-SHA256.txt').write_text(f"{result['sha256']}  {package.name}\n", encoding='ascii')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
