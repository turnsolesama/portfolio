# -*- coding: utf-8 -*-
"""Portable configuration and explicitly selected local asset workspaces."""
import copy
import json
import os
import stat
import tempfile

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(APP_DIR, 'data')
CONFIG_PATH = os.path.join(DATA_DIR, 'config.json')
DB_PATH = os.path.join(DATA_DIR, 'aihub.db')
SOURCES_PATH = os.path.join(DATA_DIR, 'sources.json')
REPORTS_DIR = os.path.join(DATA_DIR, 'reports')
FILE_ATTRIBUTE_REPARSE_POINT = 0x400
DEFAULT_IGNORE_DIRS = {'.git', 'node_modules', '__pycache__', '.venv', 'venv',
                      '.pnpm-store', '.cache', '$recycle.bin', 'system volume information'}
STANDARD_DIRS = ('00_Management/Catalogs', '10_Apps', '20_Models', '30_Assets',
                 '40_Projects', '50_Training', '60_Workflows', '70_Output',
                 '80_Knowledge', '90_Archive')


def _is_reparse(st):
    return bool(getattr(st, 'st_file_attributes', 0) & FILE_ATTRIBUTE_REPARSE_POINT) or stat.S_ISLNK(st.st_mode)


def _key(path):
    return os.path.normcase(os.path.abspath(path)).casefold()


def _within(path, parent):
    try:
        return os.path.commonpath([_key(path), _key(parent)]) == _key(parent)
    except ValueError:
        return False


def _check_ancestors(path):
    # Validate before realpath can hide a symlink or junction.
    cursor = os.path.abspath(path)
    while True:
        if os.path.lexists(cursor):
            st = os.lstat(cursor)
            if _is_reparse(st):
                raise ValueError('安全区路径及其上级目录不能包含联接或符号链接。')
            if not stat.S_ISDIR(st.st_mode):
                raise ValueError('安全区路径被普通文件占用。')
        parent = os.path.dirname(cursor)
        if parent == cursor:
            break
        cursor = parent


def validate_asset_root(root, must_exist=True):
    """Validate an absolute local workspace without resolving links away."""
    if not isinstance(root, str) or not root.strip() or not os.path.isabs(root):
        raise ValueError('请选择本机的绝对目录路径。')
    if any(ord(c) < 32 for c in root) or root.startswith(('\\\\', '//')):
        raise ValueError('安全区必须是本机普通目录，不能使用网络或设备路径。')
    if os.name == 'nt' and (':' in root[2:] or any(c in root for c in '*?<>|"')):
        raise ValueError('目录路径包含不支持的字符。')
    if os.name == 'nt':
        reserved = {'con', 'prn', 'aux', 'nul'} | {'com%d' % n for n in range(1, 10)} | {'lpt%d' % n for n in range(1, 10)}
        parts = os.path.splitdrive(root)[1].replace('\\', '/').split('/')
        if any(p not in ('', '.', '..') and (p.rstrip(' .') != p or p.split('.')[0].casefold() in reserved) for p in parts):
            raise ValueError('目录路径包含 Windows 保留名称或末尾空格、句点。')
    path = os.path.abspath(root)
    if os.path.dirname(path) == path:
        raise ValueError('不能把整个磁盘作为安全区，请选择专用子目录。')
    home = os.path.expanduser('~')
    user_roots = [home, os.path.dirname(home), os.environ.get('USERPROFILE'),
                  os.environ.get('PUBLIC'), os.environ.get('APPDATA'), os.environ.get('LOCALAPPDATA')]
    if any(_key(path) == _key(p) for p in user_roots if p):
        raise ValueError('不能把用户主目录作为安全区，请选择专用资产目录。')
    protected = [os.environ.get(k) for k in ('WINDIR', 'SystemRoot', 'ProgramFiles',
                 'ProgramFiles(x86)', 'ProgramData')]
    if os.name == 'nt':
        drive = os.path.splitdrive(path)[0]
        protected += [os.path.join(drive + os.sep, name) for name in
                      ('Windows', 'Program Files', 'Program Files (x86)', 'ProgramData')]
    if any(_within(path, p) for p in protected if p):
        raise ValueError('不能把系统或应用数据目录作为资产安全区。')
    if _within(path, APP_DIR) or _within(path, DATA_DIR):
        raise ValueError('请选择软件目录以外的专用资产目录。')
    _check_ancestors(path)
    if must_exist and not os.path.isdir(path):
        raise ValueError('原资产目录当前不可用，请连接磁盘或重新选择目录。')
    return path


def scan_excluded(path, cfg=None):
    """Shared read-only scanner guard for application data and organized aliases."""
    try:
        if _is_reparse(os.lstat(path)):
            return True
    except (OSError, TypeError, ValueError):
        return True
    cfg = cfg or {}
    excludes = [APP_DIR, DATA_DIR] + list(cfg.get('scan_exclude_paths') or [])
    if any(isinstance(p, str) and p and _within(path, p) for p in excludes):
        return True
    names = cfg.get('ignore_dirs', DEFAULT_IGNORE_DIRS)
    ignored = {str(n).casefold() for n in (names or [])} | {'00_aihub_library'}
    parts = os.path.normpath(path).replace('\\', '/').split('/')
    return any(part.casefold() in ignored for part in parts)


def scan_root_allowed(path, cfg=None):
    """Check each configured scan root once, including all lexical ancestors."""
    try:
        root = validate_asset_root(path)
        return not scan_excluded(root, cfg)
    except (OSError, TypeError, ValueError):
        return False


def detect_layout(ai_root, ignore_dirs=None):
    """A single root retains loose assets; scanners apply explicit exclusions."""
    result = {'scan_roots': [], 'aliases': {}, 'scan_exclude_paths': [os.path.abspath(APP_DIR)]}
    try:
        root = validate_asset_root(ai_root)
    except (OSError, ValueError):
        return result
    guard = {'ignore_dirs': list(DEFAULT_IGNORE_DIRS if ignore_dirs is None else ignore_dirs)}
    if not scan_excluded(root, guard):
        result['scan_roots'] = [root]
        result['scan_exclude_paths'].append(os.path.join(root, '00_AIHub_Library'))
    return result


def detect_output_roots(roots, ignore_dirs=None):
    """Bounded, link-free discovery supporting numbered, legacy and ComfyUI layouts."""
    found, seen, visited = [], set(), set()
    guard = {'ignore_dirs': list(DEFAULT_IGNORE_DIRS if ignore_dirs is None else ignore_dirs)}
    budget = 5000
    for candidate in list(roots or []):
        try:
            root = validate_asset_root(candidate)
        except (OSError, ValueError):
            continue
        stack = [(root, 0)]
        while stack and budget > 0:
            current, depth = stack.pop()
            key = _key(current)
            if key in visited or scan_excluded(current, guard):
                continue
            visited.add(key)
            budget -= 1
            base = os.path.basename(current).casefold()
            if 'output' in base or '输出' in base:
                if key not in seen:
                    found.append(current)
                    seen.add(key)
                continue
            if depth >= 5:
                continue
            try:
                with os.scandir(current) as entries:
                    children = []
                    for entry in entries:
                        try:
                            st = entry.stat(follow_symlinks=False)
                            if stat.S_ISDIR(st.st_mode) and not _is_reparse(st):
                                children.append(entry.path)
                        except OSError:
                            continue
                stack.extend((p, depth + 1) for p in sorted(children, key=str.casefold, reverse=True))
            except OSError:
                continue
    return sorted(found, key=str.casefold)


def initialize_root(root):
    """Explicit directory initialization; no model moves, deletion or config save."""
    root = validate_asset_root(root, must_exist=False)
    targets = [os.path.join(root, *p.split('/')) for p in STANDARD_DIRS]
    for target in targets:
        _check_ancestors(target)
    os.makedirs(root, exist_ok=True)
    for target in targets:
        _check_ancestors(target)
        os.makedirs(target, exist_ok=True)
    return dict(detect_layout(root), ai_root=root, output_roots=detect_output_roots([root]),
                catalog_dir=os.path.join(root, '00_Management', 'Catalogs'))


def _suggested_root():
    parent = os.path.dirname(os.path.abspath(APP_DIR))
    if os.path.basename(parent).casefold() in {'10_apps', 'ai_apps', 'apps', 'applications'}:
        suggestion = os.path.dirname(parent)
    else:
        suggestion = os.path.join(parent, 'AI_Assets')
    try:
        return validate_asset_root(suggestion, must_exist=False)
    except (OSError, ValueError):
        fallback = os.path.join(os.path.expanduser('~'), 'AI_Assets')
        try:
            return validate_asset_root(fallback, must_exist=False)
        except (OSError, ValueError):
            return ''


def workspace_status(cfg):
    root = cfg.get('ai_root')
    configured = isinstance(root, str) and bool(root.strip())
    available, message = False, '首次使用请选择资产安全区；目录建议不会自动保存或整理。'
    if configured:
        try:
            validate_asset_root(root)
            available, message = True, '资产安全区已连接。'
        except (OSError, ValueError) as exc:
            message = str(exc)
    return {'configured': configured, 'available': available,
            'suggested_root': _suggested_root(), 'message': message}


def default_config(use_environment=True):
    requested = os.environ.get('AI_HUB_ROOT', '').strip() if use_environment else ''
    try:
        ai_root = validate_asset_root(requested) if requested else ''
    except (OSError, ValueError):
        ai_root = ''
    layout = detect_layout(ai_root)
    return {
        'ai_root': ai_root, 'scan_roots': layout['scan_roots'], 'aliases': layout['aliases'],
        'scan_exclude_paths': layout['scan_exclude_paths'],
        'output_roots': detect_output_roots(layout['scan_roots']),
        'catalog_dir': os.path.join(ai_root, '00_Management', 'Catalogs') if ai_root else '',
        'ignore_dirs': sorted(DEFAULT_IGNORE_DIRS),
        'organizer': {'enabled': False, 'root': '', 'on_startup': False},
        'server': {'host': '127.0.0.1', 'port': 8765},
        'network': {'civitai_base': 'https://civitai.com', 'hf_base': 'https://huggingface.co',
                    'civitai_token': '', 'proxy': '', 'request_interval': 1.2},
    }


def _read_config(path):
    try:
        with open(path, encoding='utf-8-sig') as stream:
            cfg = json.load(stream)
    except (OSError, ValueError) as exc:
        raise ValueError('data/config.json 无法读取或格式有误；原文件已保留，请修复后重试。') from exc
    if not isinstance(cfg, dict):
        raise ValueError('data/config.json 必须是配置对象；原文件已保留。')
    for key in ('server', 'network', 'organizer'):
        if key in cfg and not isinstance(cfg[key], dict):
            raise ValueError('data/config.json 的 %s 必须是配置对象；原文件已保留。' % key)
    return cfg


def load_config():
    if os.path.exists(CONFIG_PATH):
        cfg = _read_config(CONFIG_PATH)
        defaults = default_config(use_environment=False)
        # An existing installation never inherits another computer's env root.
        defaults.update(ai_root='', scan_roots=[], aliases={}, output_roots=[], catalog_dir='')
        for key, value in defaults.items():
            if key not in cfg:
                cfg[key] = copy.deepcopy(value)
            elif isinstance(value, dict) and isinstance(cfg[key], dict):
                for nested_key, nested_value in value.items():
                    cfg[key].setdefault(nested_key, copy.deepcopy(nested_value))
        os.makedirs(REPORTS_DIR, exist_ok=True)
        return cfg
    cfg = default_config()
    save_config(cfg)
    os.makedirs(REPORTS_DIR, exist_ok=True)
    return cfg


def save_config(cfg):
    if not isinstance(cfg, dict):
        raise ValueError('配置必须是对象。')
    encoded = json.dumps(cfg, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    if os.path.exists(CONFIG_PATH):
        _read_config(CONFIG_PATH)  # Never silently replace a damaged config.
    os.makedirs(DATA_DIR, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.config-', suffix='.tmp', dir=DATA_DIR)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, CONFIG_PATH)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
