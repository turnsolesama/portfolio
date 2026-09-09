"""Explicit local registrations. Preview first; never create or move asset folders."""
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import threading
import time
import uuid
from . import config

STATES = ('pending', 'path_checked', 'historical_passed', 'current_passed')
STATE_LABELS = dict(zip(STATES, ('待验证', '仅路径检查', '历史执行通过', '当前复验通过')))
SECTIONS = {'project': 'projects', 'run': 'runs', 'workflow': 'workflows', 'knowledge': 'knowledge'}
TEMPLATES = [
    {'id': 'generic', 'version': '1', 'name': '通用项目', 'types': ['creative', 'tool'],
     'description': '六段参考结构：00_Brief、10_References、20_Assets、30_Workflows、40_Runs、90_Delivery。只说明职责，不自动创建或改排现有目录。'},
    {'id': 'film', 'version': '1', 'name': '影视创作', 'types': ['creative'],
     'description': '沿用影视专用结构：00_admin、01_script_storyboard 至 09_delivery，通过 mapping 关联各制作环节；不套用通用六段或训练 Runs。'},
    {'id': 'training', 'version': '1', 'name': '模型训练', 'types': ['training'],
     'description': '训练项目位于 50_Training/Projects，Datasets 保存训练数据，Runs 保存参数、日志和检查点。只登记已有结构，不创建或移动训练文件。'},
    {'id': 'external', 'version': '1', 'name': '已有应用结构（仅映射）', 'types': ['creative', 'training', 'tool'],
     'description': '保留专用应用或已有项目的原生内部布局，以当前说明、资产、输出、正式交付和 mapping 接入，不套模板或重排目录。'},
]
TEXT_SUFFIXES = {'.md', '.txt', '.html'}
BLOCKED = {'data', 'app_data', 'cache', 'caches', 'config', 'configs', 'configuration',
           'credentials', 'secrets', 'private', 'profiles', 'node_modules', 'vendor', 'runtime',
           'venv', '__pycache__', 'backups', '_renders', '_test_pdf', '_lo_profile', 'webview2'}
IDENTIFIER = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$')
SHA = re.compile(r'^[a-fA-F0-9]{64}$')
LIMIT = 4 * 1024 * 1024
_lock = threading.RLock()
_previews = {}


def _key(path):
    return os.path.normcase(os.path.abspath(path)).casefold()


def _within(path, parent):
    try:
        return os.path.commonpath([_key(path), _key(parent)]) == _key(parent)
    except ValueError:
        return False


def _ancestors(path):
    cursor = Path(path)
    while True:
        try:
            value = cursor.lstat()
            if stat.S_ISLNK(value.st_mode) or getattr(value, 'st_file_attributes', 0) & 0x400:
                raise ValueError('路径不能包含符号链接或联接。')
        except FileNotFoundError:
            pass
        if cursor.parent == cursor:
            break
        cursor = cursor.parent


def ai_root(cfg):
    value = cfg.get('ai_root')
    if not value or not isinstance(value, str) or not os.path.isabs(value):
        raise ValueError('请先配置专用 AI 资产根目录。')
    path = Path(os.path.abspath(value))
    _ancestors(path)
    if path.parent == path:
        raise ValueError('AI 根目录不能是整个磁盘。')
    return path


def safe_path(cfg, value, allowed=None, exists=False, directory=False, text=False):
    """Validate lexical components before resolving, including Windows reparse points."""
    if not isinstance(value, str) or not value or len(value) > 2000 or not os.path.isabs(value):
        raise ValueError('登记路径必须是本机绝对路径。')
    if value.startswith(('\\\\', '//')) or any(ord(c) < 32 for c in value):
        raise ValueError('网络、设备或控制字符路径不可登记。')
    if '..' in value.replace('\\', '/').split('/') or (os.name == 'nt' and ':' in value[2:]):
        raise ValueError('路径不能含上级跳转或备用数据流。')
    path = Path(os.path.abspath(value))
    base = ai_root(cfg)
    roots = allowed or [base]
    if not any(_within(path, parent) for parent in roots):
        raise ValueError('路径不在该登记允许的范围内。')
    if not _within(path, base):
        raise ValueError('登记路径超出 AI 根目录。')
    relative = path.relative_to(base)
    for index, part in enumerate(relative.parts):
        lowered = part.casefold()
        stem = lowered.split('.')[0]
        model_runtime = (not text and lowered == 'runtime' and index == 1
                         and relative.parts[0].casefold() == '20_models')
        if lowered.startswith('.') or (lowered in BLOCKED and not model_runtime) or stem in {'auth', 'credentials', 'secrets', 'config', 'profiles'}:
            raise ValueError('配置、私密内容、依赖和缓存不进入登记索引。')
        if part.rstrip(' .') != part or (os.name == 'nt' and any(c in part for c in '*?<>|"')):
            raise ValueError('路径包含不支持的名称。')
    _ancestors(path)
    if exists and not path.exists():
        raise ValueError('登记引用的文件或目录不存在。')
    if path.exists() and (not path.is_dir() if directory else not path.is_file()):
        raise ValueError('登记路径类型不匹配。')
    if text and path.suffix.lower() not in TEXT_SUFFIXES:
        raise ValueError('正文只允许 Markdown、纯文本或 HTML。')
    if text and path.exists() and path.stat().st_nlink > 1:
        raise ValueError('正文索引不接受可能映射到其他文件的硬链接。')
    return path


def _store():
    folder = Path(config.DATA_DIR)
    _ancestors(folder)
    for name in ('registry.json', 'registry.previous.json'):
        _ancestors(folder / name)
    return folder


def _raw(path):
    _ancestors(path)
    if not path.exists():
        return b''
    if not path.is_file() or path.stat().st_size > LIMIT:
        raise ValueError('登记文件类型或大小不合法。')
    return read_checked(path, LIMIT, single_link=True)


def read_checked(path, limit, single_link=False):
    """Read an already-allowlisted ordinary file, checking its open-handle identity."""
    path = Path(path)
    _ancestors(path)
    with path.open('rb') as handle:
        opened = os.fstat(handle.fileno())
        _ancestors(path)
        current = path.stat()
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
            raise ValueError('读取前文件身份发生变化。')
        if single_link and opened.st_nlink > 1:
            raise ValueError('不接受硬链接正文或登记文件。')
        if opened.st_size > limit:
            raise ValueError('文件超过允许的读取大小。')
        return handle.read(limit + 1)


def _empty():
    return {'version': 1, 'workspace': '', **{name: [] for name in SECTIONS.values()}}


def _decode(raw):
    value = json.loads(raw.decode('utf-8-sig'))
    if not isinstance(value, dict) or value.get('version') != 1:
        raise ValueError('登记文件版本不支持。')
    result = _empty()
    result['workspace'] = value.get('workspace', '')
    for name in SECTIONS.values():
        rows = value.get(name, [])
        if not isinstance(rows, list) or len(rows) > 2000 or any(not isinstance(r, dict) for r in rows):
            raise ValueError('登记文件记录结构不合法。')
        seen = set()
        required = {'projects': ('name', 'root', 'current_doc', 'delivery', 'type'),
                    'runs': ('output_dir', 'workflow_path', 'workflow_sha256'),
                    'workflows': ('path', 'state'), 'knowledge': ('path',)}[name]
        for row in rows:
            identifier = row.get('id')
            if not isinstance(identifier, str) or not IDENTIFIER.fullmatch(identifier) or identifier in seen:
                raise ValueError('登记 ID 不合法或重复。')
            if any(not isinstance(row.get(key), str) or not row[key] for key in required):
                raise ValueError('登记文件缺少必要字段。')
            seen.add(identifier)
        result[name] = rows
    return result


def read(cfg):
    with _lock:
        folder = _store()
        raw = _raw(folder / 'registry.json')
        warnings = []
        try:
            value = _decode(raw) if raw else _empty()
        except (ValueError, UnicodeError):
            try:
                value = _decode(_raw(folder / 'registry.previous.json'))
            except (ValueError, UnicodeError):
                raise ValueError('登记文件及备份无法读取；请保留原文件后人工恢复。') from None
            warnings.append('当前登记文件损坏，暂以最后一个有效备份读取；未自动覆盖原文件。')
        workspace = _key(ai_root(cfg))
        if value['workspace'] and value['workspace'] != workspace:
            raise ValueError('登记属于其他 AI 根目录，请勿在新根目录下直接套用。')
        return {**copy.deepcopy(value), 'revision': hashlib.sha256(raw).hexdigest(),
                'templates': copy.deepcopy(TEMPLATES), 'warnings': warnings}


def _text(value, label, required=False, limit=2000):
    if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 and c not in '\n\t' for c in value):
        raise ValueError(label + '格式不合法。')
    if required and not value.strip():
        raise ValueError('请填写' + label + '。')
    return value.strip()


def _id(record):
    value = record.get('id')
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError('ID 限 1–80 位英文字母、数字、下划线和连字符，首位须字母或数字。')
    return value


def _paths(cfg, values, roots):
    if not isinstance(values, list) or len(values) > 100:
        raise ValueError('路径清单最多 100 项。')
    result = []
    for value in values:
        path = safe_path(cfg, value, roots, directory=True)
        if str(path) not in result:
            result.append(str(path))
    return result


def _project(cfg, record, document):
    base = ai_root(cfg)
    kind = record.get('type')
    if kind not in ('creative', 'training', 'tool'):
        raise ValueError('请选择创作、训练或工具开发项目类型。')
    roots = [base / '40_Projects', base / '50_Training/Projects', base / '10_Apps']
    path = safe_path(cfg, record.get('root'), roots, exists=True, directory=True)
    if any(_key(path) == _key(parent) for parent in roots):
        raise ValueError('请登记具体项目，而非整个项目或应用分区。')
    current = safe_path(cfg, record.get('current_doc'), [path], exists=True, text=True)
    delivery = safe_path(cfg, record.get('delivery'), [path], directory=True)
    identifier = _id(record)
    if any(p.get('id') != identifier and _key(p.get('delivery', '')) == _key(delivery) for p in document['projects']):
        raise ValueError('正式交付位置已被另一个项目登记。')
    if any(p.get('id') != identifier and _key(p.get('root', '')) == _key(path) for p in document['projects']):
        raise ValueError('同一项目目录不能重复登记。')
    template = record.get('template') or {'id': 'external', 'version': '1', 'applicable': False}
    if not isinstance(template, dict):
        raise ValueError('模板字段不合法。')
    selected = next((t for t in TEMPLATES if t['id'] == template.get('id')), None)
    if not selected or kind not in selected['types'] or str(template.get('version', '1')) != selected['version']:
        raise ValueError('模板类型或版本不适用于该项目。')
    mapping = record.get('mapping', {})
    if not isinstance(mapping, dict) or len(mapping) > 30:
        raise ValueError('项目结构映射最多 30 项。')
    clean_mapping = {}
    for role, relative in mapping.items():
        role = _text(role, '结构角色', required=True, limit=80)
        if not isinstance(relative, str) or os.path.isabs(relative):
            raise ValueError('内部结构映射须为项目内相对目录。')
        mapped = safe_path(cfg, str(path / relative), [path], directory=True)
        clean_mapping[role] = mapped.relative_to(path).as_posix()
    return {'id': identifier, 'name': _text(record.get('name', ''), '项目名称', True, 150),
            'type': kind, 'root': str(path), 'description': _text(record.get('description', ''), '项目说明'),
            'current_doc': str(current), 'delivery': str(delivery),
            'assets': _paths(cfg, record.get('assets', []), [path, base / '30_Assets', base / '20_Models', base / '50_Training/Projects']),
            'outputs': _paths(cfg, record.get('outputs', []), [path, base / '70_Output']),
            'template': {'id': selected['id'], 'version': selected['version'], 'applicable': selected['id'] != 'external'},
            'mapping': clean_mapping}


def _workflow_roots(cfg, document):
    base = ai_root(cfg)
    return [base / '60_Workflows'] + [Path(p['root']) for p in document['projects'] if isinstance(p.get('root'), str)]


def _digest(path):
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError('哈希核验只支持不超过 64 MiB 的证据；大模型请使用大小和修改时间快照。')
    return hashlib.sha256(read_checked(path, 64 * 1024 * 1024)).hexdigest()


def _snapshots(cfg, rows, roots):
    if not isinstance(rows, list) or not rows or len(rows) > 100:
        raise ValueError('通过状态需要 1–100 条明确的依赖和输出证据。')
    result = []
    for item in rows:
        if not isinstance(item, dict):
            raise ValueError('证据快照格式不合法。')
        path = safe_path(cfg, item.get('path'), roots)
        size, stamp = item.get('size'), item.get('mtime_ns')
        if isinstance(stamp, str) and re.fullmatch(r'[0-9]{1,20}', stamp):
            stamp = int(stamp)
        if type(size) is not int or size < 0 or type(stamp) is not int or stamp < 0:
            raise ValueError('证据须记录整数 size 和十进制 mtime_ns。')
        # Nanoseconds exceed JavaScript's safe integer range. Serialize losslessly.
        row = {'path': str(path), 'size': size, 'mtime_ns': str(stamp)}
        if item.get('sha256'):
            if not isinstance(item['sha256'], str) or not SHA.fullmatch(item['sha256']):
                raise ValueError('证据 SHA-256 不合法。')
            row['sha256'] = item['sha256'].lower()
        result.append(row)
    return result


def _workflow(cfg, record, document, check_current=True):
    state = record.get('state', 'pending')
    if state not in STATES:
        raise ValueError('工作流验证状态不合法。')
    path = safe_path(cfg, record.get('path'), _workflow_roots(cfg, document), exists=state == 'path_checked')
    if path.suffix.lower() != '.json':
        raise ValueError('工作流须为明确登记的 JSON 文件。')
    result = {'id': _id(record), 'path': str(path), 'state': state, 'validation': None}
    if any(w.get('id') != result['id'] and _key(w.get('path', '')) == _key(path) for w in document['workflows']):
        raise ValueError('同一工作流路径不能重复登记。')
    if state == 'path_checked':
        evidence = record.get('validation') or {}
        if not isinstance(evidence, dict):
            raise ValueError('路径检查证据格式不合法。')
        kept = {}
        if evidence.get('date'):
            try:
                date = dt.date.fromisoformat(evidence['date'])
                if date > dt.date.today():
                    raise ValueError()
            except (ValueError, TypeError):
                raise ValueError('验证日期须为非未来的 YYYY-MM-DD。') from None
            kept['date'] = date.isoformat()
        if evidence.get('workflow_sha256'):
            digest = evidence['workflow_sha256']
            if not isinstance(digest, str) or not SHA.fullmatch(digest):
                raise ValueError('工作流版本的 SHA-256 不合法。')
            kept['workflow_sha256'] = digest.lower()
        base = ai_root(cfg)
        projects = [Path(p['root']) for p in document['projects'] if isinstance(p.get('root'), str)]
        for key, roots in (('dependencies', [base / '20_Models', base / '60_Workflows', base / '10_Apps'] + projects),
                           ('outputs', [base / '70_Output'] + projects)):
            if evidence.get(key):
                kept[key] = _snapshots(cfg, evidence[key], roots)
        if evidence.get('note'):
            kept['note'] = _text(evidence['note'], '验证说明')
        result['validation'] = kept or None
        return result
    if state not in ('historical_passed', 'current_passed'):
        return result
    evidence = record.get('validation')
    if not isinstance(evidence, dict):
        raise ValueError('通过状态必须附带验证证据。')
    try:
        date = dt.date.fromisoformat(evidence.get('date', ''))
        if date > dt.date.today():
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError('验证日期须为非未来的 YYYY-MM-DD。') from None
    digest = evidence.get('workflow_sha256')
    if not isinstance(digest, str) or not SHA.fullmatch(digest):
        raise ValueError('请提供工作流版本的 SHA-256。')
    base = ai_root(cfg)
    projects = [Path(p['root']) for p in document['projects'] if isinstance(p.get('root'), str)]
    result['validation'] = {'date': date.isoformat(), 'workflow_sha256': digest.lower(),
        'dependencies': _snapshots(cfg, evidence.get('dependencies'), [base / '20_Models', base / '60_Workflows', base / '10_Apps'] + projects),
        'outputs': _snapshots(cfg, evidence.get('outputs'), [base / '70_Output'] + projects),
        'note': _text(evidence.get('note', ''), '验证说明')}
    if state == 'current_passed' and check_current:
        checked = workflow_status(cfg, result, document)
        if not checked['current_match']:
            raise ValueError('当前证据不匹配，不能登记为当前复验通过：' + checked['verification_reason'])
    return result


def workflow_status(cfg, record, document=None):
    document = document or read(cfg)
    state = record.get('state', 'pending')
    reason, matched, evidence_valid = '', False, False
    try:
        clean = _workflow(cfg, record, document, check_current=False)
        evidence = clean['validation']
        evidence_valid = evidence is not None and state in ('historical_passed', 'current_passed')
        path = safe_path(cfg, clean['path'], _workflow_roots(cfg, document), exists=True)
        if state == 'path_checked':
            if evidence and evidence.get('workflow_sha256') and _digest(path) != evidence['workflow_sha256']:
                raise ValueError('路径检查对应的工作流哈希已变化，保留原记录并等待重新检查。')
            matched = True
        elif evidence:
            if _digest(path) != evidence['workflow_sha256']:
                raise ValueError('工作流哈希已变化。')
            base = ai_root(cfg)
            for name in ('dependencies', 'outputs'):
                for item in evidence[name]:
                    target = safe_path(cfg, item['path'], [base], exists=True)
                    st = target.stat()
                    if st.st_size != item['size'] or st.st_mtime_ns != int(item['mtime_ns']):
                        raise ValueError('依赖或输出证据已变化。')
                    if item.get('sha256') and _digest(target) != item['sha256']:
                        raise ValueError('依赖或输出哈希已变化。')
            matched = True
    except (ValueError, OSError, KeyError, TypeError) as error:
        reason = str(error)
    if state == 'current_passed' and not matched:
        state = 'historical_passed' if evidence_valid else 'pending'
    if state == 'historical_passed' and not evidence_valid:
        state = 'pending'
    if state == 'path_checked' and not matched:
        state = 'pending'
    if state not in STATES:
        state = 'pending'
    return {'verification_state': state, 'verification_label': STATE_LABELS[state],
            'current_match': matched, 'verification_reason': reason,
            'validation': copy.deepcopy(record.get('validation'))}


def _run(cfg, record, document):
    project_id = record.get('project_id') or None
    project = next((p for p in document['projects'] if p['id'] == project_id), None)
    if project_id and not project:
        raise ValueError('请先登记所属项目。')
    base = ai_root(cfg)
    roots = [base / '70_Output/Projects' / project['id'], Path(project['root'])] + [Path(p) for p in project.get('outputs', [])] if project else [base / '70_Output/Tests/Unassigned']
    state = record.get('validation_status', 'pending')
    if state not in STATES:
        raise ValueError('运行验证状态不合法。')
    output = safe_path(cfg, record.get('output_dir'), roots, directory=True, exists=state == 'path_checked')
    if any(_key(output) == _key(parent) for parent in roots):
        raise ValueError('请登记具体运行输出目录。')
    if any(row.get('id') != record.get('id') and _key(row['output_dir']) == _key(output) for row in document['runs']):
        raise ValueError('该输出目录已归属另一次运行。')
    workflow = safe_path(cfg, record.get('workflow_path'), _workflow_roots(cfg, document), exists=state == 'path_checked')
    digest = record.get('workflow_sha256')
    if workflow.suffix.lower() != '.json' or not isinstance(digest, str) or not SHA.fullmatch(digest):
        raise ValueError('运行须绑定工作流 JSON 路径与 SHA-256。')
    models = record.get('models', [])
    if not isinstance(models, list) or len(models) > 100:
        raise ValueError('模型清单格式不合法。')
    models = [_text(m, '模型标识', True, 300) for m in models]
    seed = record.get('seed')
    if seed is not None and (type(seed) is not int or abs(seed) > 2**64):
        raise ValueError('Seed 须为整数或留空。')
    if state == 'path_checked' and _digest(workflow) != digest.lower():
        raise ValueError('路径检查的工作流哈希与登记版本不一致。')
    if state in ('historical_passed', 'current_passed'):
        evidence = next((w for w in document['workflows'] if _key(w['path']) == _key(workflow)
                         and (w.get('validation') or {}).get('workflow_sha256') == digest.lower()), None)
        if not evidence:
            raise ValueError('运行的通过状态须引用相同工作流版本的验证登记。')
        verified = workflow_status(cfg, evidence, document)
        if verified['verification_state'] not in ('historical_passed', 'current_passed') or (state == 'current_passed' and verified['verification_state'] != state):
            raise ValueError('工作流当前证据不足以支持该运行状态。')
        if not any(_within(item['path'], output) for item in evidence['validation']['outputs']):
            raise ValueError('验证输出证据不属于本次运行目录。')
    return {'id': _id(record), 'project_id': project_id, 'output_dir': str(output),
            'workflow_path': str(workflow), 'workflow_sha256': digest.lower(), 'models': models,
            'seed': seed, 'validation_status': state}


def _knowledge(cfg, record, document):
    path = safe_path(cfg, record.get('path'), [ai_root(cfg) / '80_Knowledge'], exists=True, text=True)
    return {'id': _id(record), 'path': str(path), 'title': _text(record.get('title', path.name), '知识标题', True, 150),
            'description': _text(record.get('description', ''), '知识说明')}


def run_status(cfg, record, document=None):
    document = document or read(cfg)
    state = record.get('validation_status', 'pending')
    effective, reason = state, ''
    try:
        _run(cfg, record, document)
    except (ValueError, OSError, KeyError, TypeError) as error:
        reason = str(error)
        effective = 'pending'
        if state == 'current_passed':
            try:
                _run(cfg, {**record, 'validation_status': 'historical_passed'}, document)
            except (ValueError, OSError, KeyError, TypeError):
                pass
            else:
                effective = 'historical_passed'
    if effective not in STATES:
        effective = 'pending'
    return {'effective_validation_status': effective, 'validation_label': STATE_LABELS[effective],
            'validation_reason': reason}


def evidence_preview(cfg, value):
    """Collect explicitly selected metadata; never assert a run result or read images."""
    if not isinstance(value, dict):
        raise ValueError('证据预览格式不合法。')
    document = read(cfg)
    base = ai_root(cfg)
    workflow = safe_path(cfg, value.get('workflow_path'), _workflow_roots(cfg, document), exists=True)
    if workflow.suffix.lower() != '.json':
        raise ValueError('请选择工作流 JSON 文件。')
    projects = [Path(p['root']) for p in document['projects'] if isinstance(p.get('root'), str)]
    result = {'workflow_sha256': _digest(workflow)}
    for name, roots in (('dependencies', [base / '20_Models', base / '60_Workflows', base / '10_Apps'] + projects),
                        ('outputs', [base / '70_Output'] + projects)):
        values = value.get(name, [])
        if not isinstance(values, list) or len(values) > 100:
            raise ValueError('证据路径清单最多 100 项。')
        rows, seen = [], set()
        for entry in values:
            path = safe_path(cfg, entry, roots, exists=True)
            if _key(path) in seen:
                continue
            st = path.stat()
            rows.append({'path': str(path), 'size': st.st_size, 'mtime_ns': str(st.st_mtime_ns)})
            seen.add(_key(path))
        result[name] = rows
    return result


def validate(cfg, kind, record, document=None):
    if kind not in SECTIONS or not isinstance(record, dict):
        raise ValueError('登记类型或记录格式不合法。')
    document = document or read(cfg)
    return {'project': _project, 'run': _run, 'workflow': _workflow, 'knowledge': _knowledge}[kind](cfg, record, document)


def _preview(cfg, kind, record, document, previous=None):
    token = uuid.uuid4().hex
    now = time.time()
    with _lock:
        for key in list(_previews):
            if _previews[key]['expires_at'] < now:
                del _previews[key]
        if len(_previews) >= 200:
            raise ValueError('预览数量过多，请稍后重试。')
        _previews[token] = {'kind': kind, 'record': copy.deepcopy(record), 'revision': document['revision'],
                            'workspace': _key(ai_root(cfg)), 'store': _key(_store()), 'expires_at': now + 600}
    return {'token': token, 'kind': kind, 'record': record, 'previous': previous,
            'revision': document['revision'], 'expires_at': now + 600, 'warnings': document.get('warnings', [])}


def preview(cfg, kind, record):
    document = read(cfg)
    clean = validate(cfg, kind, record, document)
    previous = next((p for p in document[SECTIONS[kind]] if p['id'] == clean['id']), None)
    return _preview(cfg, kind, clean, document, previous)


def backups(cfg):
    read(cfg)
    path = _store() / 'registry.previous.json'
    try:
        raw = _raw(path)
        if not raw:
            return {'items': []}
        value = _decode(raw)
    except (ValueError, UnicodeError):
        return {'items': [], 'warning': '上一份备份当前不可读取。'}
    return {'items': [{'id': hashlib.sha256(raw).hexdigest(), 'name': '上一次有效登记',
                       'mtime': path.stat().st_mtime, 'counts': {name: len(value[name]) for name in SECTIONS.values()}}]}


def restore_preview(cfg, backup_id):
    document = read(cfg)
    if not isinstance(backup_id, str) or not SHA.fullmatch(backup_id):
        raise ValueError('请选择列出的备份 ID。')
    raw = _raw(_store() / 'registry.previous.json')
    if hashlib.sha256(raw).hexdigest() != backup_id:
        raise ValueError('备份已变化，请重新预览。')
    restored = _decode(raw)
    if restored['workspace'] != _key(ai_root(cfg)):
        raise ValueError('备份属于其他 AI 根目录。')
    for kind, section in SECTIONS.items():
        restored[section] = [validate(cfg, kind, row, restored) for row in restored[section]]
    result = _preview(cfg, 'restore', restored, document)
    with _lock:
        _previews[result['token']]['backup_id'] = backup_id
    return result


def _atomic(path, data):
    _ancestors(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _ancestors(path.parent)
    name = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.registry-', delete=False) as handle:
            name = handle.name
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        _ancestors(path)
        os.replace(name, path)
        name = None
    finally:
        if name and os.path.isfile(name):
            os.unlink(name)


def save(cfg, token):
    with _lock:
        pending = _previews.get(token) if isinstance(token, str) else None
        if not pending or pending['expires_at'] < time.time():
            raise ValueError('预览已过期或不存在，请重新预览。')
        if pending['workspace'] != _key(ai_root(cfg)) or pending['store'] != _key(_store()):
            raise ValueError('预览环境已变化。')
        document = read(cfg)
        if document['revision'] != pending['revision']:
            raise ValueError('登记已被其他操作修改，请重新预览。')
        kind = pending['kind']
        if kind == 'restore':
            raw = _raw(_store() / 'registry.previous.json')
            if hashlib.sha256(raw).hexdigest() != pending['backup_id']:
                raise ValueError('备份已变化，请重新预览。')
            output = copy.deepcopy(pending['record'])
            for name, section in SECTIONS.items():
                output[section] = [validate(cfg, name, row, output) for row in output[section]]
            clean = output
        else:
            clean = validate(cfg, kind, pending['record'], document)
            output = {key: copy.deepcopy(document[key]) for key in ('version', 'workspace', *SECTIONS.values())}
            section = SECTIONS[kind]
            output[section] = [r for r in output[section] if r['id'] != clean['id']] + [clean]
        output['workspace'] = _key(ai_root(cfg))
        data = json.dumps(output, ensure_ascii=False, indent=2).encode('utf-8')
        if len(data) > LIMIT:
            raise ValueError('登记文件超过大小限制。')
        _decode(data)  # Apply the exact same shape and row limits before writing.
        folder = _store()
        previous = _raw(folder / 'registry.json')
        if hashlib.sha256(previous).hexdigest() != pending['revision']:
            raise ValueError('登记在保存前已变化，请重新预览。')
        if previous:
            try:
                _decode(previous)
            except (ValueError, UnicodeError):
                pass  # Never replace a valid fallback with a corrupt primary.
            else:
                _atomic(folder / 'registry.previous.json', previous)
        _atomic(folder / 'registry.json', data)
        del _previews[token]
        return {'saved': True, 'kind': kind, 'record': clean, 'revision': hashlib.sha256(data).hexdigest()}
