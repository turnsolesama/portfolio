"""Fetch the pinned Deno runtime for maintainers; users receive it bundled."""
import hashlib
import json
from pathlib import Path
import zipfile
from urllib.request import urlopen

root = Path(__file__).resolve().parent
entry = json.loads((root / 'runtime.lock.json').read_text())['deno']
cache = root / '.build' / 'deno-download' / 'deno-runtime.zip'
cache.parent.mkdir(parents=True, exist_ok=True)
if not cache.exists() or hashlib.sha256(cache.read_bytes()).hexdigest() != entry['sha256']:
    with urlopen(entry['url'], timeout=60) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != entry['sha256']:
        raise RuntimeError('Deno SHA-256 mismatch')
    cache.write_bytes(data)
with zipfile.ZipFile(cache) as archive:
    if archive.testzip() is not None:
        raise RuntimeError('Deno archive is corrupt')
    archive.extract('deno.exe', root / '.build' / 'tools')
print('Deno ' + entry['version'] + ' verified and prepared')
