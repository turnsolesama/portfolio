"""Read file-copy clipboard formats only, on an explicit paste request."""
import os
import sys
from .store import UserError


def read_files():
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        user = ctypes.WinDLL('user32', use_last_error=True)
        shell = ctypes.WinDLL('shell32', use_last_error=True)
        user.OpenClipboard.argtypes = [wintypes.HWND]
        user.OpenClipboard.restype = wintypes.BOOL
        user.GetClipboardData.argtypes = [wintypes.UINT]
        user.GetClipboardData.restype = wintypes.HANDLE
        user.CloseClipboard.argtypes = []
        shell.DragQueryFileW.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
        shell.DragQueryFileW.restype = wintypes.UINT
        if not user.OpenClipboard(None):
            raise UserError('剪贴板正被占用，请稍后再粘贴。', 409)
        try:
            handle = user.GetClipboardData(15)  # CF_HDROP, never interpret text as paths.
            count = shell.DragQueryFileW(handle, 0xffffffff, None, 0) if handle else 0
            if count > 128:raise UserError('一次最多粘贴 128 个文件。')
            result = []
            for index in range(count):
                length = shell.DragQueryFileW(handle, index, None, 0)
                value = ctypes.create_unicode_buffer(length + 1)
                shell.DragQueryFileW(handle, index, value, length + 1)
                result.append(value.value)
            return result
        finally:
            user.CloseClipboard()
    if sys.platform == 'darwin':
        from AppKit import NSPasteboard, NSPasteboardURLReadingFileURLsOnlyKey
        from Foundation import NSURL
        values = NSPasteboard.generalPasteboard().readObjectsForClasses_options_(
            [NSURL], {NSPasteboardURLReadingFileURLsOnlyKey: True}) or []
        if len(values) > 128:raise UserError('一次最多粘贴 128 个文件。')
        return [str(value.path()) for value in values if value.isFileURL()]
    raise UserError('当前系统不支持文件剪贴板，请使用导入或拖放。')
