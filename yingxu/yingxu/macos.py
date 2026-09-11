"""macOS file operations. Never replace a destination or permanently delete files."""
import ctypes
import errno
import os
from pathlib import Path
import subprocess
import sys


def rename_exclusive(source, target):
    if sys.platform != 'darwin':
        raise OSError('macOS exclusive rename is unavailable on this platform')
    # Darwin renamex_np(RENAME_EXCL) atomically refuses an existing destination,
    # including directories. An exists() check followed by rename() is not safe.
    library = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
    rename = library.renamex_np
    rename.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint)
    rename.restype = ctypes.c_int
    if rename(os.fsencode(source), os.fsencode(target), 0x00000004):
        number = ctypes.get_errno()
        if number == errno.EEXIST:
            raise FileExistsError(number, '目标位置已有文件，未覆盖内容。', str(target))
        raise OSError(number, os.strerror(number), str(source))


def open_path(path, reveal=False):
    from .store import clean_path
    path = clean_path(path)
    if not path.exists():
        raise FileNotFoundError(str(path))
    subprocess.run(['/usr/bin/open', *(['-R'] if reveal else []), str(path)],
                   check=True, timeout=15, capture_output=True)


def recycle(path):
    from .store import clean_path
    from Foundation import NSFileManager, NSURL
    path = clean_path(path)
    if path == Path(path.anchor):
        raise OSError('不能回收磁盘根目录。')
    ok, result, error = NSFileManager.defaultManager().trashItemAtURL_resultingItemURL_error_(
        NSURL.fileURLWithPath_(str(path)), None, None)
    if not ok or result is None or os.path.lexists(path):
        raise OSError('未能确认文件进入废纸篓，回收记录已保留。' + (str(error) if error else ''))
    return {'recycled': True, 'recycle_path': str(result.path())}
