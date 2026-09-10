"""Verify ZIP integrity and run only isolated synthetic HTTP checks on free ports."""
import argparse
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
    assert health['version'] == '0.2.3'
    expected = data_identity(data)
    assert health['instance_id'] == expected
    bootstrap = request(port, 'GET', '/api/bootstrap')
    assert Path(bootstrap['data_root']) == data.resolve()
    assert Path(bootstrap['project_root']) == projects.resolve()
    assert request(port, 'GET', '/api/projects')['projects'] == []
    assert request(port, 'GET', '/api/skills')['skills'] == []
    token = bootstrap['token']
    project = request(port, 'POST', '/api/projects', {'name': '公开包 隔离验收'}, token)
    assert Path(project['root']).is_relative_to(projects.resolve())
    folder = request(port, 'POST', '/api/folders', {'project_id': project['id'], 'category': 'characters', 'name': '第 1 集'}, token)
    item = request(port, 'POST', '/api/items', {'project_id': project['id'], 'category': 'characters', 'folder_id': folder['id'], 'name': '角色 测试', 'content': '# 合成角色\n不包含用户数据。'}, token)
    assert item['folder_id'] == folder['id']
    assert Path(item['path']).is_file()
    with socket.socket() as connection:
        connection.connect(('127.0.0.1', port))
    return ['health version and data identity', 'configured data/projects roots', 'empty projects and SKILL library', 'Chinese project/folder/document creation']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    args = parser.parse_args()
    checked = []
    with tempfile.TemporaryDirectory(prefix='yingxu-解压验收 空间-') as temporary:
        base = Path(temporary)
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
        environment = os.environ.copy()
        environment.update(USERPROFILE=str(base / '空白用户'), LOCALAPPDATA=str(base / 'Local'),
                           APPDATA=str(base / 'Roaming'), YINGXU_DATA_DIR=str(base / '数据 覆盖'),
                           YINGXU_PROJECTS_DIR=str(base / '项目 覆盖'), PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
        environment.pop('YINGXU_RESUME_SESSION_TOKEN', None)
        data, projects = Path(environment['YINGXU_DATA_DIR']), Path(environment['YINGXU_PROJECTS_DIR'])
        port = free_port()
        pid = None
        try:
            result = subprocess.run([sys.executable, '-B', str(root / 'launcher.pyw'), '--no-browser', '--no-dialog', '--port', str(port)],
                                    cwd=root, env=environment, capture_output=True, timeout=35)
            if result.returncode:
                raise RuntimeError('Isolated launcher failed: ' + result.stderr.decode('utf-8', errors='replace'))
            pid_record = json.loads((data / 'server.pid.json').read_text(encoding='utf-8'))
            assert Path(pid_record['root']) == root and pid_record['port'] == port
            pid = pid_record['pid']
            checked += check_server(port, data, projects)
            second = subprocess.run([sys.executable, '-B', str(root / 'launcher.pyw'), '--no-browser', '--no-dialog', '--port', str(port)],
                                    cwd=root, env=environment, capture_output=True, timeout=10)
            assert second.returncode == 0 and json.loads(second.stdout)['status'] == 'reused'
            checked.append('launcher cold start and exact-data service reuse')
            foreign = dict(environment, YINGXU_DATA_DIR=str(base / '另一数据目录'))
            rejected = subprocess.run([sys.executable, '-B', str(root / 'launcher.pyw'), '--no-browser', '--no-dialog', '--port', str(port)],
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
            process = subprocess.Popen([sys.executable, '-S', '-B', str(root / 'server.py'), '--port', str(port), '--data', str(data), '--projects-root', str(projects)],
                                       cwd=root, env=environment, stdout=log, stderr=log, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            try:
                wait_health(port, process)
                check_server(port, data, projects)
                checked.append('CLI path overrides and no site-packages/Pillow startup')
            finally:
                process.terminate()
                process.wait(timeout=10)
    print(json.dumps({'ok': True, 'archive': args.archive.name, 'checks': checked, 'private_data_used': False}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
