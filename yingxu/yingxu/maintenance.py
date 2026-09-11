"""Preview-bound cleanup of disposable previews and explicitly chosen history.

Never accepts a filesystem path from the caller. Original files, the catalogue,
database backups and unknown files are outside this module's allowlist.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import secrets
import stat
import threading
import time

from .store import UserError, clean_path, has_link

MAX_ENTRIES = 20000
MAX_SECONDS = 3.0
TOKEN_SECONDS = 300
GROUPS = {'thumbnails': '缩略图缓存', 'versions': '项目文稿历史',
          'external-versions': '外部文稿历史', 'skill_versions': 'SKILL 历史'}
HEX_ID = re.compile(r'[a-f0-9]{32}')
VERSION_NAME = re.compile(r'([a-f0-9]{32})\.(md|txt|json|csv|yaml|yml|docx|excalidraw)')
SKILL_NAME = re.compile(r'\d{4}-\d\d-\d\dT\d\d-\d\d-\d\d\.\d{3}\+00-00_[a-f0-9]{8}\.md')


def _identity(value):
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)


class Maintenance:
    def __init__(self, store):
        self.store = store
        self.root = store.data_root
        self.lock = threading.Lock()
        self.tokens = {}

    @staticmethod
    def _options(data):
        if data is None:data = {}
        if not isinstance(data, dict) or set(data)-{'include_cache','include_versions','keep_versions','older_than_days'}:
            raise UserError('维护选项无效，不能指定文件路径。')
        result = {'include_cache': True, 'include_versions': False,
                  'keep_versions': 20, 'older_than_days': 30, **data}
        if any(type(result[key]) is not bool for key in ('include_cache','include_versions')):
            raise UserError('维护开关无效。')
        if type(result['keep_versions']) is not int or not 1 <= result['keep_versions'] <= 1000:
            raise UserError('每篇文稿至少保留 1 个历史版本，最多设置 1000 个。')
        if type(result['older_than_days']) is not int or not 0 <= result['older_than_days'] <= 36500:
            raise UserError('历史保留天数无效。')
        return result

    def _safe(self, path):
        # Recheck every ancestor, not only the leaf, including app-data itself.
        if path == self.root or not path.is_relative_to(self.root):return None
        try:
            if clean_path(path) != path or any(has_link(p) for p in (path, *path.parents)):
                return None
            value = path.stat()
            if not stat.S_ISREG(value.st_mode) or value.st_nlink != 1:return None
            return value
        except (OSError, UserError):return None

    def _scan(self, options):
        started = time.monotonic();count = 0;truncated = False
        groups = {key: {'name': name, 'bytes': 0, 'files': 0,
                        'reclaimable_bytes': 0, 'reclaimable_files': 0} for key,name in GROUPS.items()}
        candidates = {};cutoff = time.time()-options['older_than_days']*86400

        def entries(folder):
            nonlocal count,truncated
            try:
                if not folder.is_dir() or clean_path(folder)!=folder or any(has_link(p) for p in (folder,*folder.parents)):return
                with os.scandir(folder) as iterator:
                    for entry in iterator:
                        count += 1
                        if count>MAX_ENTRIES or time.monotonic()-started>MAX_SECONDS:
                            truncated=True;return
                        yield Path(entry.path)
            except (OSError,UserError):return

        def member(key,path):
            value=self._safe(path)
            if value is None:return None
            groups[key]['bytes']+=value.st_size;groups[key]['files']+=1
            return (path,value)

        def choose(key,record):
            path,value=record
            relative=str(path.relative_to(self.root))
            candidates[relative]=_identity(value)
            groups[key]['reclaimable_bytes']+=value.st_size
            groups[key]['reclaimable_files']+=1

        for key in GROUPS:
            for path in entries(self.root/key):
                if key=='thumbnails':
                    if re.fullmatch(r'[a-f0-9]{64}\.jpg',path.name):
                        record=member(key,path)
                        if record and options['include_cache']:choose(key,record)
                    continue
                expected = r'[a-f0-9]{64}' if key=='external-versions' else r'[a-f0-9]{32}'
                if not re.fullmatch(expected,path.name):continue
                records=[];metadata={}
                for child in entries(path):
                    if key=='external-versions' and re.fullmatch(r'[a-f0-9]{32}\.metadata\.json',child.name):
                        record=member(key,child)
                        if record:metadata[child.name[:32]]=record
                    elif (SKILL_NAME.fullmatch(child.name) if key=='skill_versions' else VERSION_NAME.fullmatch(child.name)):
                        record=member(key,child)
                        if record:records.append(record)
                # Newest snapshots always remain, regardless of age. An unknown
                # or incomplete group is never grounds to delete its contents.
                records.sort(key=lambda r:(r[1].st_mtime_ns,r[0].name),reverse=True)
                if options['include_versions'] and not truncated:
                    for record in records[options['keep_versions']:]:
                        if record[1].st_mtime>=cutoff:continue
                        choose(key,record)
                        companion=metadata.get(record[0].stem)
                        if companion:choose(key,companion)
            if truncated:break
        if truncated:
            candidates.clear()
            for group in groups.values():group['reclaimable_bytes']=group['reclaimable_files']=0
        return groups,candidates,truncated

    def preview(self, data=None):
        options=self._options(data)
        with self.lock:
            groups,candidates,truncated=self._scan(options)
            token=secrets.token_urlsafe(32)
            # Two latest previews only; tokens never contain or expose paths.
            self.tokens={key:value for key,value in self.tokens.items() if value['expires']>time.monotonic()}
            while len(self.tokens)>=2:self.tokens.pop(next(iter(self.tokens)))
            self.tokens[token]={'expires':time.monotonic()+TOKEN_SECONDS,'options':options,'files':candidates,'truncated':truncated}
        return {'token':token,'expires_in':TOKEN_SECONDS,'options':options,
                'groups':[{'key':key,'label':group['name'],**{k:v for k,v in group.items() if k!='name'}} for key,group in groups.items()],
                'total_bytes':sum(g['bytes'] for g in groups.values()),
                'reclaimable_bytes':sum(g['reclaimable_bytes'] for g in groups.values()),
                'reclaimable_files':len(candidates),'truncated':truncated,
                'warnings':(['扫描达到上限，统计不完整；本次不提供清理，请缩小历史规模后重试。'] if truncated else [])+
                    ['原稿、数据库和数据库备份不参与清理；每篇文稿保留最新历史，默认不清理文稿历史。']}

    def execute(self, data):
        if not isinstance(data,dict) or set(data)!={'token'} or not isinstance(data['token'],str):
            raise UserError('清理必须使用刚才预览生成的确认令牌。')
        with self.lock,self.store.lock:
            preview=self.tokens.pop(data['token'],None)
            if not preview or preview['expires']<=time.monotonic() or preview['truncated']:
                raise UserError('清理预览已过期或不完整，请重新预览。',409)
            _,current,truncated=self._scan(preview['options'])
            if truncated:raise UserError('文件状态已变化，请重新预览后再清理。',409)
            removed=freed=skipped=0
            for relative,identity in preview['files'].items():
                if current.get(relative)!=identity:
                    skipped+=1;continue
                path=self.root/relative;value=self._safe(path)
                if value is None or _identity(value)!=identity:
                    skipped+=1;continue
                try:
                    _unlink_verified(path,identity)
                    removed+=1;freed+=identity[2]
                    if path.parts[-3]=='versions' and VERSION_NAME.fullmatch(path.name):
                        with self.store.connection() as db:
                            db.execute('DELETE FROM versions WHERE id=? AND path=?',(path.stem,str(path)))
                except OSError:skipped+=1
            return {'removed_files':removed,'removed_bytes':freed,'skipped_files':skipped,
                    'warnings':([f'{skipped} 个文件已变化、不可访问或清理失败，已跳过。'] if skipped else []),
                    'message':f'已清理 {removed} 个缓存或旧历史文件；保留原稿与最新历史。'}


def _unlink_verified(path, identity):
    """Delete the verified file identity, not a later replacement at its path."""
    if os.name=='nt':
        import ctypes
        from ctypes import wintypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateFileW.argtypes=(wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE)
        kernel.CreateFileW.restype=wintypes.HANDLE
        kernel.SetFileInformationByHandle.argtypes=(wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD)
        kernel.CloseHandle.argtypes=(wintypes.HANDLE,)
        # DELETE + FILE_READ_ATTRIBUTES, no sharing: replacements and concurrent
        # writes cannot race the identity check / disposition operation.
        handle=kernel.CreateFileW(str(path),0x10080,0,None,3,0x00200000,None)
        if handle==wintypes.HANDLE(-1).value:raise ctypes.WinError(ctypes.get_last_error())
        try:
            # Identity is checked through this open handle, including links.
            import msvcrt
            fd=msvcrt.open_osfhandle(handle,os.O_RDONLY)
            handle=None
            try:
                value=os.fstat(fd)
                if _identity(value)!=identity or value.st_nlink!=1:raise OSError('文件已变化')
                delete=wintypes.BOOL(True)
                if not kernel.SetFileInformationByHandle(msvcrt.get_osfhandle(fd),4,ctypes.byref(delete),ctypes.sizeof(delete)):
                    raise ctypes.WinError(ctypes.get_last_error())
            finally:os.close(fd)
        finally:
            if handle is not None:kernel.CloseHandle(handle)
    else:
        descriptor=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            value=os.stat(path.name,dir_fd=descriptor,follow_symlinks=False)
            if _identity(value)!=identity or not stat.S_ISREG(value.st_mode) or value.st_nlink!=1:
                raise OSError('文件已变化')
            os.unlink(path.name,dir_fd=descriptor)
        finally:os.close(descriptor)
