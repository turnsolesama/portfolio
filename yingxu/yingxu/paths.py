"""Portable, side-effect-free defaults shared by HTTP and desktop launchers."""
import hashlib
import os
import sys
from pathlib import Path


def absolute_directory(value):
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError('映序目录配置必须使用绝对路径。')
    return path.resolve()


def default_data_root():
    value = os.environ.get('YINGXU_DATA_DIR')
    if value:
        return absolute_directory(value)
    if sys.platform == 'darwin':
        return absolute_directory(Path.home() / 'Library' / 'Application Support' / 'YingXu')
    local = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local')
    return absolute_directory(local / 'YingXu')


def documents_directory():
    if os.name == 'nt':
        import ctypes
        buffer = ctypes.create_unicode_buffer(32768)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buffer) == 0 and buffer.value:
            return Path(buffer.value)
    return Path.home() / 'Documents'


def default_project_root():
    value = os.environ.get('YINGXU_PROJECTS_DIR')
    return absolute_directory(value) if value else absolute_directory(documents_directory() / 'YingXu' / 'Projects')


def instance_id(data_root):
    # Python and .NET have different Unicode uppercase tables (for example ß).
    # Resolve the physical spelling, then fold ASCII only in this shared protocol.
    normalized = str(Path(data_root).resolve()).rstrip('\\/')
    if os.name == 'nt':
        normalized = normalized.translate(str.maketrans('abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'))
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()
