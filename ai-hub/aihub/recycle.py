"""Send one validated local file to Windows Recycle Bin, without console/UI.

Uses IFileOperation with FOFX_RECYCLEONDELETE; no permanent-delete fallback.
https://learn.microsoft.com/windows/win32/api/shobjidl_core/nf-shobjidl_core-ifileoperation-setoperationflags
"""
import ctypes
from ctypes import wintypes
import os
import uuid


class GUID(ctypes.Structure):
    _fields_ = [("data1", wintypes.DWORD), ("data2", wintypes.WORD), ("data3", wintypes.WORD), ("data4", ctypes.c_ubyte * 8)]

    @classmethod
    def from_string(cls, value):
        return cls.from_buffer_copy(uuid.UUID(value).bytes_le)


def _check(result):
    if result < 0:
        raise OSError(f"Windows 回收站操作失败 (0x{result & 0xffffffff:08X})，文件未确认删除。")


def _method(pointer, index, *argtypes):
    table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)(table[index])


def recycle_file(path):
    if os.name != "nt":
        raise OSError("当前平台没有可用的 Windows 回收站。")
    path = os.path.abspath(path)
    if not os.path.isfile(path) or os.path.islink(path):
        raise OSError("只能将存在的普通文件移入回收站。")
    ole = ctypes.OleDLL("ole32")
    shell = ctypes.OleDLL("shell32")
    ole.CoInitializeEx.argtypes = (ctypes.c_void_p, wintypes.DWORD)
    ole.CoInitializeEx.restype = ctypes.c_long
    ole.CoCreateInstance.argtypes = (ctypes.POINTER(GUID), ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))
    shell.SHCreateItemFromParsingName.argtypes = (wintypes.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))
    initialized = False
    operation, item = ctypes.c_void_p(), ctypes.c_void_p()
    try:
        _check(ole.CoInitializeEx(None, 2))  # COINIT_APARTMENTTHREADED
        initialized = True
        clsid = GUID.from_string("3ad05575-8857-4850-9277-11b85bdb8e09")
        iid = GUID.from_string("947aab5f-0a5c-4c13-b4d6-4bf7836fc9f8")
        item_iid = GUID.from_string("43826d1e-e718-42ee-bc55-a1e261c37bfe")
        _check(ole.CoCreateInstance(ctypes.byref(clsid), None, 1, ctypes.byref(iid), ctypes.byref(operation)))
        # Recycle, record undo, silence progress/errors, fail on first error.
        flags = 0x00080000 | 0x20000000 | 0x00100000 | 0x0400 | 0x0010 | 0x0004 | 0x2000
        _check(_method(operation, 5, wintypes.DWORD)(operation, flags))
        _check(shell.SHCreateItemFromParsingName(path, None, ctypes.byref(item_iid), ctypes.byref(item)))
        _check(_method(operation, 18, ctypes.c_void_p, ctypes.c_void_p)(operation, item, None))
        _check(_method(operation, 21)(operation))
        aborted = wintypes.BOOL()
        _check(_method(operation, 22, ctypes.POINTER(wintypes.BOOL))(operation, ctypes.byref(aborted)))
        if aborted.value or os.path.exists(path):
            raise OSError("回收站操作未完成，图库记录已保留。")
    finally:
        if item:
            _method(item, 2)(item)
        if operation:
            _method(operation, 2)(operation)
        if initialized:
            ole.CoUninitialize()
