"""Verify ZIP integrity and run only isolated synthetic HTTP checks on free ports."""
import argparse
import base64
import hashlib
import http.client
import json
import os
from pathlib import Path, PurePosixPath
import signal
import socket
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlencode
import zipfile


def request(port, method, path, data=None, token=None):
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
    headers = {}
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers['Content-Type'] = 'application/json'
    if token:
        headers['X-YingXu-Token'] = token
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        result = response.read()
        if response.status >= 400:
            raise RuntimeError(f'{method} {path} returned {response.status}')
        return json.loads(result)
    finally:
        connection.close()


def free_port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


def data_identity(path):
    value = str(path.resolve()).rstrip('\\/').translate(str.maketrans('abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'))
    return hashlib.sha256(value.encode()).hexdigest()


def wait_health(port, process=None):
    for _ in range(80):
        try:
            health = request(port, 'GET', '/api/health')
            if health.get('app') == 'yingxu' and health.get('ok'):
                return health
        except (OSError, ValueError, RuntimeError):
            pass
        if process and process.poll() is not None:
            raise RuntimeError('Isolated service exited before health check')
        time.sleep(.1)
    raise RuntimeError('Isolated service health timeout')


def check_server(port, data, projects):
    health = wait_health(port)
    assert health['version'] == '0.4.1'
    expected = data_identity(data)
    assert health['instance_id'] == expected
    bootstrap = request(port, 'GET', '/api/bootstrap')
    assert Path(bootstrap['data_root']) == data.resolve()
    assert Path(bootstrap['project_root']) == projects.resolve()
    assert request(port, 'GET', '/api/projects')['projects'] == []
    assert request(port, 'GET', '/api/skills')['skills'] == []
    token = bootstrap['token']
    settings = request(port, 'GET', '/api/settings')
    assert settings['capture_enabled'] is True and settings['capture_hotkey'] == 'Ctrl+Alt+Shift+S'
    assert settings['capture_mode'] == 'annotate'
    assert request(port, 'PATCH', '/api/settings', {'capture_mode': 'quick'}, token)['capture_mode'] == 'quick'
    assert request(port, 'GET', '/api/settings')['capture_mode'] == 'quick'
    assert request(port, 'PATCH', '/api/settings', {'capture_mode': 'annotate'}, token)['capture_mode'] == 'annotate'
    assert bootstrap['capabilities']['resource_groups'] is True
    project = request(port, 'POST', '/api/projects', {'name': '公开包 隔离验收'}, token)
    assert Path(project['root']).is_relative_to(projects.resolve())
    renamed = request(port, 'PATCH', '/api/projects/' + project['id'], {'name': '项目改名验收'}, token)
    assert renamed['name'] == '项目改名验收' and renamed['root'] == project['root']
    # Exercise persisted classification moves through the packaged HTTP API.
    parent = request(port, 'POST', '/api/project-folders', {'name': '1111'}, token)
    branch = request(port, 'POST', '/api/project-folders', {'name': '222'}, token)
    leaf = request(port, 'POST', '/api/project-folders', {'name': '下级', 'parent_id': branch['id']}, token)
    request(port, 'PATCH', '/api/project-library/' + project['id'], {'folder_id': branch['id']}, token)
    library_before = request(port, 'GET', '/api/project-library')
    moved_branch = request(port, 'PATCH', '/api/project-folders/' + branch['id'], {'parent_id': parent['id']}, token)
    assert moved_branch['parent_id'] == parent['id'] and moved_branch['name'] == '222'
    library_after = request(port, 'GET', '/api/project-library')
    assert library_after['projects'] == library_before['projects']
    assert next(f for f in library_after['folders'] if f['id'] == leaf['id'])['parent_id'] == branch['id']
    moved_branch = request(port, 'PATCH', '/api/project-folders/' + branch['id'], {'parent_id': None}, token)
    assert moved_branch['parent_id'] is None
    assert request(port, 'GET', '/api/project-library')['projects'] == library_before['projects']
    external_path = projects.parent / '外部编辑验收.md'
    original_external = b'\xef\xbb\xbf# External\r\nOriginal\r\n'
    external_path.write_bytes(original_external)
    external = request(port, 'POST', '/api/external-open', {'paths': [str(external_path)]}, token)['entries'][0]
    detail = request(port, 'GET', '/api/external/' + external['id'])
    assert detail['content']['editable']
    saved = request(port, 'POST', '/api/external/' + external['id'] + '/content',
                    {'etag': detail['content']['etag'], 'content': '# External\nEdited\n'}, token)
    assert saved['content']['content'] == '# External\r\nEdited\r\n'
    assert external_path.read_bytes() == b'\xef\xbb\xbf# External\r\nEdited\r\n'
    backups = list((data / 'external-versions').glob('*/*.md'))
    assert backups and any(p.read_bytes() == original_external for p in backups)
    assert len(request(port, 'GET', '/api/projects')['projects']) == 1
    folder = request(port, 'POST', '/api/folders', {'project_id': project['id'], 'category': 'characters', 'name': '第 1 集'}, token)
    item = request(port, 'POST', '/api/items', {'project_id': project['id'], 'category': 'characters', 'folder_id': folder['id'], 'name': '角色 测试', 'content': '# 合成角色\n不包含用户数据。'}, token)
    assert item['folder_id'] == folder['id']
    assert Path(item['path']).is_file()
    companion = request(port, 'POST', '/api/items', {'project_id': project['id'], 'category': 'scripts',
                        'name': '分组合成笔记', 'content': '素材组不会搬动原文件。'}, token)
    originals = {value['id']: (Path(value['path']), Path(value['path']).read_bytes(), value['category'], value['folder_id'])
                 for value in (item, companion)}
    group = request(port, 'POST', '/api/resource-groups', {'project_id': project['id'], 'item_ids': list(originals)}, token)
    assert group['member_ids'] == list(originals) and group['count'] == 2 and group['revision'] == 1
    listed = request(port, 'GET', '/api/resource-groups?' + urlencode({'project': project['id']}))
    assert listed['total'] == 1 and listed['groups'][0]['id'] == group['id']
    extra = [request(port, 'POST', '/api/items', {'project_id': project['id'], 'name': '转移验收' + str(n),
             'content': '合成素材'}, token) for n in range(2)]
    for value in extra:
        originals[value['id']] = (Path(value['path']), Path(value['path']).read_bytes(), value['category'], value['folder_id'])
    target = request(port, 'POST', '/api/resource-groups', {'project_id': project['id'], 'item_ids': [i['id'] for i in extra]}, token)
    moved = request(port, 'POST', '/api/resource-groups/' + group['id'] + '/transfer',
                    {'ids': [item['id']], 'revision': group['revision'], 'target_group_id': target['id'], 'target_revision': target['revision']}, token)
    assert moved['source']['member_ids'] == [companion['id']]
    assert moved['target']['member_ids'] == [i['id'] for i in extra] + [item['id']]
    assert moved['source']['revision'] == 2 and moved['target']['revision'] == 2
    removed = request(port, 'POST', '/api/resource-groups/' + target['id'] + '/transfer',
                      {'ids': [item['id']], 'revision': 2, 'target_group_id': None}, token)
    assert removed['target'] is None and removed['source']['member_ids'] == [i['id'] for i in extra]
    assert request(port, 'DELETE', '/api/resource-groups/' + target['id'], {'revision': removed['source']['revision']}, token)['dissolved']
    dissolved = request(port, 'DELETE', '/api/resource-groups/' + group['id'], {'revision': moved['source']['revision']}, token)
    assert dissolved['dissolved'] is True
    assert request(port, 'GET', '/api/resource-groups?' + urlencode({'project': project['id']}))['total'] == 0
    for item_id, (original_path, original_bytes, category, folder_id) in originals.items():
        after = request(port, 'GET', '/api/items/' + item_id)
        assert Path(after['path']) == original_path and original_path.read_bytes() == original_bytes
        assert after['category'] == category and after['folder_id'] == folder_id
    request(port, 'PATCH', '/api/items/' + item['id'], {'tags': ['原标签甲']}, token)
    request(port, 'PATCH', '/api/items/' + companion['id'], {'tags': ['原标签乙']}, token)
    batch = request(port, 'POST', '/api/items/batch-properties',
                    {'project_id': project['id'], 'ids': [item['id'], companion['id']], 'tags_add': ['共同标签', '共同标签'], 'status': '已完成'}, token)
    assert [value['id'] for value in batch['items']] == [item['id'], companion['id']]
    assert [value['tags'] for value in batch['items']] == [['原标签甲', '共同标签'], ['原标签乙', '共同标签']]
    assert all(value['status'] == '已完成' for value in batch['items'])
    for original_path, original_bytes, _, _ in originals.values():
        assert original_path.read_bytes() == original_bytes
    second = request(port, 'POST', '/api/projects', {'name': '另一合成项目'}, token)
    second_item = request(port, 'POST', '/api/items', {'project_id': second['id'], 'category': 'scripts', 'name': '搜索文稿', 'content': '# 合成文稿\n跨项目验收令牌'}, token)
    search = request(port, 'GET', '/api/search?' + urlencode({'q': '跨项目验收令牌', 'limit': 20}))
    assert any(result['type'] == 'item' and result['id'] == second_item['id'] and result['project_id'] == second['id'] for result in search['results'])
    with socket.socket() as connection:
        connection.connect(('127.0.0.1', port))
    return ['health version and data identity', 'configured data/projects roots', 'empty projects and SKILL library',
            'Chinese project/folder/document creation', 'capture settings default to enabled, Ctrl+Alt+Shift+S and annotate; quick/annotate modes persist',
            'cross-category group create/list/atomic transfer/remove/dissolve preserves file paths, bytes and categories',
            'batch tags append without replacing individual tags and batch status preserves original file bytes',
            'global search finds indexed document content across projects',
            'project rename preserves project root',
            'project classification subtree moves and returns to root without changing project records',
            'external Markdown saves original path with BOM/newlines, backup and no project import']


def check_media(port, root, base, interpreter, environment):
    fixture = base / '合成媒体'
    fixture.mkdir()
    png, video = fixture / '图片.png', fixture / '视频.mp4'
    code = 'from PIL import Image;import sys;Image.new("RGB",(960,540),(64,128,192)).save(sys.argv[1])'
    subprocess.run([interpreter, '-B', '-c', code, str(png)], env=environment, check=True)
    ffmpeg = root / 'runtime/ffmpeg/bin/ffmpeg.exe'
    subprocess.run([str(ffmpeg), '-nostdin', '-hide_banner', '-loglevel', 'error', '-loop', '1', '-i', str(png),
                    '-t', '1', '-c:v', 'libx264', '-threads', '1', '-pix_fmt', 'yuv420p', str(video)],
                   env=environment, capture_output=True, check=True, timeout=30)
    bootstrap = request(port, 'GET', '/api/bootstrap')
    assert bootstrap['capabilities']['image_thumbnails'] and bootstrap['capabilities']['ffmpeg']
    token = bootstrap['token']
    project = request(port, 'POST', '/api/projects', {'name': '媒体隔离验收'}, token)
    job = request(port, 'POST', '/api/import', {'project_id': project['id'], 'paths': [str(fixture)]}, token)
    for _ in range(100):
        status = request(port, 'GET', '/api/jobs/' + job['job_id'])
        if status['state'] in ('done', 'error'):
            break
        time.sleep(.1)
    assert status['state'] == 'done' and not status['errors']
    items = request(port, 'GET', '/api/items?project=' + project['id'])['items']
    media = [x for x in items if x['kind'] in ('image', 'video')]
    assert {x['kind'] for x in media} == {'image', 'video'}
    for item in media:
        if item['kind'] == 'image':
            assert item['metadata']['width'] == 960 and item['metadata']['height'] == 540
        for _ in range(100):
            connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
            try:
                connection.request('GET', '/api/thumbnail/' + item['id'])
                response = connection.getresponse()
                raw = response.read()
                if response.status == 200:
                    assert raw.startswith(b'\xff\xd8') and len(raw) > 100
                    break
                assert response.status == 202
            finally:
                connection.close()
            time.sleep(.1)
        else:
            raise AssertionError('Bundled thumbnail timed out')
    # Upload a project-owned PNG. The media fixture above is an external source
    # and deliberately cannot be used as a Markdown attachment.
    png_bytes = png.read_bytes()
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
    try:
        connection.request('POST', '/api/upload?' + urlencode({'project': project['id'], 'category': 'references', 'name': '截图验收.png'}),
                           body=png_bytes, headers={'Content-Type': 'image/png', 'X-YingXu-Token': token})
        response = connection.getresponse()
        uploaded = json.loads(response.read())
        assert response.status == 201
    finally:
        connection.close()
    assert Path(uploaded['path']).is_relative_to(Path(project['root']))
    note = request(port, 'POST', '/api/items', {'project_id': project['id'], 'category': 'scripts',
                   'name': '截图附件笔记', 'content': '# 附件验收\n正文保持不变。'}, token)
    note_bytes = Path(note['path']).read_bytes()
    link = request(port, 'GET', '/api/markdown-assets/link?' + urlencode({'note': note['id'], 'image': uploaded['id']}))
    assert link['markdown'].startswith('![') and link['relative_path'] in link['markdown']
    assert link['preview_url'].startswith('/api/markdown-assets/image?')
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
    try:
        connection.request('GET', link['preview_url'])
        response = connection.getresponse()
        assert response.status == 200 and response.getheader('Content-Type') == 'image/png'
        assert response.read() == png_bytes
    finally:
        connection.close()
    assert Path(note['path']).read_bytes() == note_bytes
    return ['bundled Pillow image metadata and JPEG thumbnail', 'bundled FFmpeg H.264 generation and video thumbnail without PATH',
            'project PNG upload and Markdown link/image routes preserve exact image bytes and original note']


def check_static_formats(port, base):
    token = request(port, 'GET', '/api/bootstrap')['token']
    samples = {
        'safe.svg': b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 60"><defs><filter id="s"><feDropShadow stdDeviation="2"/></filter></defs><rect filter="url(#s)" width="40" height="30" fill="#567456" stroke-dasharray="16 8"/></svg>',
        'safe.html': b'<h1>Heading</h1><table><tr><td>Cell</td></tr></table><script>window.BAD=1</script>',
    }
    for name, raw in samples.items():
        path = base / name
        path.write_bytes(raw)
        opened = request(port, 'POST', '/api/external-open', {'paths': [str(path)]}, token)['entries'][0]
        content = request(port, 'GET', opened['content_url'])['content']
        assert content['editable'] is False
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
        try:
            connection.request('GET', opened['media_url'])
            response = connection.getresponse()
            media = response.read()
            assert response.status == 200 and response.getheader('X-Content-Type-Options') == 'nosniff'
            if name.endswith('.svg'):
                assert media == base64.b64decode(content['preview_url'].split(',', 1)[1])
                assert 'sandbox' in response.getheader('Content-Security-Policy')
                assert b'<rect' in media and b'<filter' not in media
                assert '滤镜' in content['notice'] and '实线' in content['notice']
            else:
                assert content['content'] == raw.decode() and '<table>' in content['preview_html']
                assert '<script' not in content['preview_html'] and 'window.BAD' not in content['preview_html']
                assert media == raw and response.getheader('Content-Type').startswith('text/plain')
                assert response.getheader('Content-Disposition') == 'attachment'
        finally:
            connection.close()
        assert path.read_bytes() == raw
    return ['bundled SVG sanitizer and isolated HTML static/source routes preserve original files']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    args = parser.parse_args()
    checked = []
    with tempfile.TemporaryDirectory(prefix='yingxu-解压验收 空间-') as temporary:
        base = Path(temporary).resolve()
        with zipfile.ZipFile(args.archive) as archive:
            assert archive.testzip() is None
            names = archive.namelist()
            assert len(names) == len(set(names))
            for name in names:
                path = PurePosixPath(name)
                assert path.parts[0] == 'YingXu' and '..' not in path.parts and not path.is_absolute() and '\\' not in name
            manifest = json.loads(archive.read('YingXu/RELEASE_MANIFEST.json'))
            for member in manifest['files']:
                raw = archive.read('YingXu/' + member['path'])
                assert len(raw) == member['bytes'] and hashlib.sha256(raw).hexdigest() == member['sha256']
            assert len(names) == len(manifest['files']) + 1
            archive.extractall(base)
        checked += ['ZIP CRC and duplicate/path checks', 'all members match SHA-256 manifest', 'single YingXu root']
        root = base / 'YingXu'
        editor = json.loads((root / 'frontend/live-markdown.manifest.json').read_text(encoding='utf-8'))
        editor_bytes = (root / 'frontend/live-markdown.js').read_bytes()
        assert editor['file'] == 'live-markdown.js'
        assert len(editor_bytes) == editor['bytes']
        assert hashlib.sha256(editor_bytes).hexdigest() == editor['sha256']
        assert editor['dependencies'] and (root / 'frontend/live-markdown.LICENSE.txt').stat().st_size > 0
        assert (root / 'frontend/live-markdown.css').is_file()
        assert (root / 'frontend/global-search.js').is_file() and (root / 'frontend/global-search.css').is_file()
        for relative in ('frontend/capture.js', 'frontend/resource-groups.js', 'frontend/resource-groups.css',
                         'yingxu/markdown_assets.py', 'yingxu/resource_groups.py',
                         'frontend/docx-editor.js', 'frontend/docx-editor.css',
                         'frontend/html-preview.js', 'frontend/html-preview.css', 'frontend/svg-preview.css',
                         'yingxu/svg_preview.py', 'yingxu/svg_content.py',
                         'yingxu/html_preview.py', 'yingxu/html_content.py'):
            assert (root / relative).is_file()
        assert not any('node_modules' in PurePosixPath(name).parts for name in names)
        checked.append('offline Markdown bundle SHA-256, stylesheet and licenses; no Node runtime')
        environment = os.environ.copy()
        environment.update(USERPROFILE=str(base / '空白用户'), LOCALAPPDATA=str(base / 'Local'),
                           APPDATA=str(base / 'Roaming'), YINGXU_DATA_DIR=str(base / '数据 覆盖'),
                           YINGXU_PROJECTS_DIR=str(base / '项目 覆盖'), PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
        environment.pop('YINGXU_RESUME_SESSION_TOKEN', None)
        environment.pop('YINGXU_PYTHON', None)
        environment.update(PATH=str(Path(os.environ['WINDIR']) / 'System32'),
                           PYTHONPATH=str(base / 'not-installed'), PYTHONHOME=str(base / 'not-installed'))
        interpreter = str(root / 'runtime/python.exe')
        assert Path(interpreter).is_file() and manifest['python_bundled']
        probe = subprocess.run([interpreter, '-B', '-c',
            'import sys,json,PIL,sqlite3;print(json.dumps(dict(executable=sys.executable,paths=sys.path,pillow=PIL.__version__)))'],
            env=environment, cwd=base, capture_output=True, check=True, text=True, encoding='utf-8')
        runtime = json.loads(probe.stdout)
        assert Path(runtime['executable']) == Path(interpreter)
        assert all(Path(p).is_relative_to(root) for p in runtime['paths'])
        checked.append('bundled Python/Pillow isolated from PATH, PYTHONHOME and user site-packages')
        data, projects = Path(environment['YINGXU_DATA_DIR']), Path(environment['YINGXU_PROJECTS_DIR'])
        port = free_port()
        pid = None
        try:
            result = subprocess.run([interpreter, '-B', str(root / 'launcher.pyw'), '--no-browser', '--no-dialog', '--port', str(port)],
                                    cwd=root, env=environment, capture_output=True, timeout=35)
            if result.returncode:
                raise RuntimeError('Isolated launcher failed: ' + result.stderr.decode('utf-8', errors='replace'))
            pid_record = json.loads((data / 'server.pid.json').read_text(encoding='utf-8'))
            assert Path(pid_record['root']) == root and pid_record['port'] == port
            pid = pid_record['pid']
            checked += check_server(port, data, projects)
            checked += check_media(port, root, base, interpreter, environment)
            checked += check_static_formats(port, base)
            second = subprocess.run([interpreter, '-B', str(root / 'launcher.pyw'), '--no-browser', '--no-dialog', '--port', str(port)],
                                    cwd=root, env=environment, capture_output=True, timeout=10)
            assert second.returncode == 0 and json.loads(second.stdout)['status'] == 'reused'
            checked.append('launcher cold start and exact-data service reuse')
            foreign = dict(environment, YINGXU_DATA_DIR=str(base / '另一数据目录'))
            rejected = subprocess.run([interpreter, '-B', str(root / 'launcher.pyw'), '--no-browser', '--no-dialog', '--port', str(port)],
                                      cwd=root, env=foreign, capture_output=True, timeout=10)
            assert rejected.returncode == 1
            assert not (Path(foreign['YINGXU_DATA_DIR']) / 'yingxu.sqlite3').exists()
            assert wait_health(port)['instance_id'] == data_identity(data)
            checked.append('different data directory refuses occupied service without stopping it')
        finally:
            if pid:
                os.kill(pid, signal.SIGTERM)
                time.sleep(.3)
        data, projects = base / '命令行 数据', base / '命令行 项目'
        port = free_port()
        with (base / 'test.log').open('wb') as log:
            process = subprocess.Popen([interpreter, '-S', '-B', str(root / 'server.py'), '--port', str(port), '--data', str(data), '--projects-root', str(projects)],
                                       cwd=root, env=environment, stdout=log, stderr=log, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            try:
                wait_health(port, process)
                check_server(port, data, projects)
                checked.append('CLI path overrides with isolated bundled interpreter')
            finally:
                process.terminate()
                process.wait(timeout=10)
    print(json.dumps({'ok': True, 'archive': args.archive.name, 'checks': checked, 'private_data_used': False}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
