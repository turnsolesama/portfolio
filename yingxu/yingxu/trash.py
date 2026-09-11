"""Preview-bound Windows recycling. Catalogue tombstones prevent automatic revival."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import uuid
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time

from .store import CATEGORIES, UserError, clean_path, has_link


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


class _RecycleSink:
    """Keep COM callbacks alive; a non-null PostDeleteItem target proves recycling."""
    def __init__(self, ole):
        self.references = 1; self.finished = False; self.recycled = False
        self.path = None; self.result = None; self.ole = ole; self.callbacks = []
        pointer = ctypes.c_void_p; number = wintypes.DWORD; string = wintypes.LPCWSTR
        signatures = [
            (pointer,pointer), (), (), (), (ctypes.c_long,),
            (number,pointer,string), (number,pointer,string,ctypes.c_long,pointer),
            (number,pointer,pointer,string), (number,pointer,pointer,string,ctypes.c_long,pointer),
            (number,pointer,pointer,string), (number,pointer,pointer,string,ctypes.c_long,pointer),
            (number,pointer), (number,pointer,ctypes.c_long,pointer),
            (number,pointer,string), (number,pointer,string,string,number,ctypes.c_long,pointer),
            (number,number), (), (), ()]
        accepted = {uuid.UUID(value).bytes_le for value in ('00000000-0000-0000-c000-000000000046',
                                                           '04b0f1a7-9490-44bc-96e1-4296a31252e2')}
        def query(this, iid, destination):
            output = ctypes.cast(destination,ctypes.POINTER(pointer))
            if ctypes.string_at(iid,16) not in accepted:
                output[0] = None; return -2147467262
            output[0] = this; self.references += 1; return 0
        def addref(this): self.references += 1; return self.references
        def release(this): self.references -= 1; return self.references
        def pre_delete(this, flags, item):
            # TSF_DELETE_RECYCLE_IF_POSSIBLE: abort any explicit non-recycle path
            # before Shell touches the item. PostDeleteItem must also prove recycling.
            return 0 if flags & 0x80 else -2147467260  # E_ABORT
        def post_delete(this, flags, old_item, result, new_item):
            self.finished = True; self.result = result
            self.recycled = result >= 0 and bool(new_item)
            if self.recycled:
                text = pointer()
                try:
                    code = _method(new_item,5,number,ctypes.POINTER(pointer))(new_item,0x80058000,ctypes.byref(text))
                    if code >= 0 and text.value: self.path = ctypes.wstring_at(text)
                finally:
                    if text.value: self.ole.CoTaskMemFree(text)
            return 0
        handlers = {0:query,1:addref,2:release,11:pre_delete,12:post_delete}
        for index,args in enumerate(signatures):
            handler = handlers.get(index,lambda *args: 0)
            self.callbacks.append(ctypes.WINFUNCTYPE(ctypes.c_long,pointer,*args)(handler))
        self.table = (pointer*len(self.callbacks))(*[ctypes.cast(callback,pointer).value for callback in self.callbacks])
        self.object = ctypes.pointer(ctypes.cast(self.table,pointer))
        self.pointer = ctypes.cast(self.object,pointer)


def recycle_path(path):
    if os.name != "nt":
        raise OSError("当前平台没有可用的 Windows 回收站。")
    path = str(clean_path(path))
    if Path(path) == Path(Path(path).anchor):
        raise OSError("不能回收磁盘根目录。")
    kernel = ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetDriveTypeW.argtypes = (wintypes.LPCWSTR,)
    if kernel.GetDriveTypeW(Path(path).anchor) != 3:
        raise OSError('只支持固定本地磁盘的 Windows 回收站，未删除文件。')
    ole = ctypes.OleDLL("ole32")
    shell = ctypes.OleDLL("shell32")
    ole.CoInitializeEx.argtypes = (ctypes.c_void_p, wintypes.DWORD)
    ole.CoInitializeEx.restype = ctypes.c_long
    ole.CoCreateInstance.argtypes = (ctypes.POINTER(GUID), ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))
    shell.SHCreateItemFromParsingName.argtypes = (wintypes.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))
    ole.CoTaskMemFree.argtypes = (ctypes.c_void_p,)
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
        sink = _RecycleSink(ole)
        _check(_method(operation, 18, ctypes.c_void_p, ctypes.c_void_p)(operation, item, sink.pointer))
        _check(_method(operation, 21)(operation))
        aborted = wintypes.BOOL()
        _check(_method(operation, 22, ctypes.POINTER(wintypes.BOOL))(operation, ctypes.byref(aborted)))
        if aborted.value or os.path.lexists(path) or not sink.finished or not sink.recycled:
            raise OSError("未能确认文件已进入 Windows 回收站，映序回收站记录已保留。")
        return {'recycled':True,'recycle_path':sink.path}
    finally:
        if item:
            _method(item, 2)(item)
        if operation:
            _method(operation, 2)(operation)
        if initialized:
            ole.CoUninitialize()


def _key(path):
    return os.path.normcase(os.path.abspath(path)).casefold()


def _inside(path, root):
    return _key(path) == _key(root) or _key(path).startswith(_key(root).rstrip('\\/') + os.sep)


def _disk_state(path):
    """No document reads. Bind identity, timestamps, sizes, and complete directory listing."""
    path = Path(path)
    if not os.path.lexists(path):
        clean_path(path.parent)
        return None
    clean_path(path)
    result = []
    pending = [path]
    while pending:
        current = pending.pop()
        if has_link(current):
            raise UserError('路径中含联接或符号链接，不能回收。', 409)
        info = current.stat()
        if info.st_nlink > 1 and current.is_file():
            raise UserError('文件存在硬链接，不能从映序清理共享文件。', 409)
        digest = None
        if current.is_file():
            with current.open('rb') as source:
                digest = hashlib.file_digest(source, 'sha256').hexdigest()
            after = current.stat()
            if (info.st_ino, info.st_size, info.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
                raise UserError('文件正在变化，请稍后重新预览。', 409)
        result.append((str(current), info.st_dev, info.st_ino, info.st_size,
                       info.st_mtime_ns, info.st_ctime_ns, digest, current.is_dir()))
        if len(result) > 20000:
            raise UserError('目录超过 20000 个成员，请先分批整理。', 409)
        if current.is_dir():
            pending.extend(sorted(current.iterdir(), key=lambda p: str(p)))
    return sorted(result)


class TrashDeletion:
    def __init__(self, store, skills):
        self.store = store; self.skills = skills; self.plans = {}

    def _selection(self, data):
        if not isinstance(data, dict):
            raise UserError('清理请求格式不正确。')
        if data.get('all') is True:
            if 'entries' in data:
                raise UserError('请选择全部或指定条目。')
            with self.store.connection() as db:
                entries = [dict(row) for row in db.execute('SELECT id,kind FROM trash_batches WHERE restored=0 AND purged=0')]
                entries += [{'id': row[0], 'kind': 'skill'} for row in db.execute('SELECT id FROM yx_skills WHERE removed=1 AND purged=0')]
        else:
            entries = data.get('entries')
        if not isinstance(entries, list) or not 1 <= len(entries) <= 500:
            raise UserError('一次请选择 1 至 500 个回收站条目。')
        found = set(); result = []
        for entry in entries:
            if not isinstance(entry, dict) or entry.get('kind') not in ('items','folder','project','skill') or not re.fullmatch('[a-f0-9]{32}', str(entry.get('id', ''))):
                raise UserError('回收站条目格式不正确。')
            identity = (entry['id'], entry['kind'])
            if identity in found:
                raise UserError('不能重复选择同一条目。')
            found.add(identity); result.append({'id': identity[0], 'kind': identity[1]})
        return result

    def _entry(self, selected):
        result = {**selected, 'name': '回收站条目', 'paths': [], 'warnings': []}
        identities = []; candidates = []; directory = None; project = None
        with self.store.connection() as db:
            if selected['kind'] == 'skill':
                row = db.execute('SELECT * FROM yx_skills WHERE id=? AND removed=1 AND purged=0', (selected['id'],)).fetchone()
                if row is None: raise UserError('技能已恢复或已清理，请刷新回收站。', 409)
                row = dict(row); result['name'] = row['name']; identities.append(row)
                if row['source'] != 'yingxu' or not row['editable']:
                    result['warnings'].append('外部或共享 SKILL 只清除映序记录，保留原文件和外部工具。')
                else:
                    path = Path(row['path'])
                    if not _inside(path, self.skills.root) or path.name.casefold() != 'skill.md':
                        raise UserError('技能文件超出映序技能目录。', 409)
                    candidates.append(path)
            else:
                batch = db.execute('SELECT * FROM trash_batches WHERE id=? AND restored=0 AND purged=0', (selected['id'],)).fetchone()
                if batch is None or batch['kind'] != selected['kind']:
                    raise UserError('条目已恢复、已清理或类型不符，请刷新回收站。', 409)
                batch = dict(batch); result['name'] = batch['name']; identities.append(batch)
                project = db.execute('SELECT * FROM projects WHERE id=?', (batch['project_id'],)).fetchone()
                if project is None: raise UserError('所属项目记录不存在。', 409)
                project = dict(project); identities.append(project)
                members = []
                for member in db.execute('SELECT * FROM trash_members WHERE batch_id=? ORDER BY entity_type,entity_id', (batch['id'],)):
                    table = {'item':'items','folder':'folders','project':'projects'}[member['entity_type']]
                    row = db.execute('SELECT * FROM '+table+' WHERE id=? AND removed=1 AND removed_batch=?', (member['entity_id'], batch['id'])).fetchone()
                    if row is not None: members.append((member['entity_type'], dict(row)))
                identities.extend(members)
                if not members: raise UserError('该批次的内容已经恢复或被重新导入，请刷新。', 409)
                if selected['kind'] == 'project': directory = Path(project['root'])
                elif selected['kind'] == 'folder':
                    folder = next((row for kind,row in members if kind == 'folder' and row['id'] == batch['target_id']), None)
                    if folder is None: raise UserError('文件夹已恢复，请刷新。', 409)
                    directory = Path(project['root']) / folder['relative_path']
                    if not _inside(directory, project['root']) or _key(directory) == _key(project['root']):
                        raise UserError('文件夹目录不在项目内。', 409)
                owned = []
                for kind,row in members:
                    if kind != 'item': continue
                    if _inside(row['path'], project['root']): owned.append(Path(row['path']))
                    else: result['warnings'].append('外部引用仅清除映序记录，原文件保留：'+row['path'])
                if directory:
                    if not directory.is_absolute() or directory == Path(directory.anchor):
                        raise UserError('不能整体回收磁盘根目录。', 409)
                    if _inside(self.store.data_root, directory): raise UserError('目录包含应用数据，不能整体回收。', 409)
                    for other in db.execute('SELECT * FROM projects WHERE id<>?', (project['id'],)):
                        if _inside(other['root'], directory): raise UserError('目录包含其他项目，不能整体回收。', 409)
                    for row in db.execute('SELECT id,path,removed,removed_batch FROM items'):
                        if _inside(row['path'], directory) and (not row['removed'] or row['removed_batch'] != batch['id']):
                            cleared = row['removed'] and row['removed_batch'] and db.execute('SELECT 1 FROM trash_batches WHERE id=? AND purged=1',(row['removed_batch'],)).fetchone()
                            if cleared and not os.path.lexists(row['path']): continue
                            raise UserError('目录内有活动引用或其他回收批次，请先分别整理后再清理目录。', 409)
                    candidates = [directory]
                else: candidates.extend(owned)
                for path in candidates:
                    if _inside(path, self.store.data_root): raise UserError('应用数据和备份不能作为素材清理。', 409)
                    for row in db.execute('SELECT id,path,removed,removed_batch FROM items'):
                        if _key(row['path']) == _key(path) and (not row['removed'] or row['removed_batch'] != batch['id']):
                            raise UserError('文件仍被其他活动条目或回收批次引用，不能回收。', 409)
        states = []
        for path in dict.fromkeys(candidates):
            state = _disk_state(path)
            if state is None:
                result['warnings'].append('原路径已不存在，仅清除映序记录：'+str(path))
            else:
                if directory:
                    known = {_key(p) for p in owned}
                    known_dirs = {_key(directory)}
                    if selected['kind'] == 'project':
                        for relative in [value[1] for value in CATEGORIES.values()] + ['30_Workflows','.yingxu']:
                            current = Path(project['root']) / relative
                            while _inside(current, directory):
                                known_dirs.add(_key(current))
                                if current == directory: break
                                current = current.parent
                    for kind,row in members:
                        if kind == 'folder': known_dirs.add(_key(Path(project['root']) / row['relative_path']))
                    for owned_file in owned:
                        current = owned_file.parent
                        while _inside(current, directory):
                            known_dirs.add(_key(current))
                            if current == directory: break
                            current = current.parent
                    managed = {str(Path(project['root']) / p) for p in ('README_项目.md','AGENTS.md','.yingxu/PROJECT_CONTEXT.md','.yingxu/progress.json','.yingxu/files-index.jsonl')}
                    extras = []
                    for record in state:
                        if record[-1]:
                            if _key(record[0]) not in known_dirs:
                                raise UserError('目录含未登记的子目录，请先整理：'+record[0], 409)
                            continue
                        if _key(record[0]) not in known:
                            if record[0] not in managed:
                                raise UserError('目录含未索引文件，请先同步并重新移入回收站：'+record[0], 409)
                            extras.append(record[0])
                    if extras: result['warnings'].append('同时回收项目说明及交接文件：'+'；'.join(extras))
                    result['warnings'].append(f'整体目录包含 {sum(not r[-1] for r in state)} 个文件；目录成员变化后必须重新确认。')
                result['paths'].append(str(path))
            states.append((str(path), state))
        signature = hashlib.sha256(json.dumps([identities,states], ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        result['_signature'] = signature; result['_states'] = states
        return result

    @staticmethod
    def _public(entry):
        return {key:value for key,value in entry.items() if not key.startswith('_')}

    def preview(self, data):
        with self.skills.lock, self.store.lock:
            selection = self._selection(data); entries = []
            for selected in selection:
                try: entries.append(self._entry(selected))
                except (UserError,OSError,ValueError) as error:
                    entries.append({**selected, 'name':'回收站条目','paths':[], 'warnings':[], 'error':str(error)})
            current = time.monotonic()
            self.plans = {key:plan for key,plan in self.plans.items() if plan['expires'] > current}
            if len(self.plans) >= 32: self.plans.pop(next(iter(self.plans)))
            token = secrets.token_urlsafe(32)
            self.plans[token] = {'expires':current+600, 'entries':entries}
            return {'token':token, 'total':len(entries), 'entries':[self._public(entry) for entry in entries],
                    'paths':list(dict.fromkeys(path for entry in entries for path in entry['paths'])),
                    'warnings':list(dict.fromkeys(w for entry in entries for w in entry['warnings'])), 'expires_in':600}

    def _begin_recycle(self, entry):
        # Commit the recovery barrier before crossing the filesystem boundary.
        # A Shell failure can occur after moving a file; absence of a success
        # callback is never evidence that the original is still in place.
        table = 'yx_skills' if entry['kind']=='skill' else 'trash_batches'
        condition = 'removed=1' if entry['kind']=='skill' else 'restored=0'
        with self.store.connection() as db:
            changed = db.execute('UPDATE '+table+' SET recycle_started=1 WHERE id=? AND purged=0 AND '+condition,(entry['id'],))
            if changed.rowcount != 1: raise UserError('回收条目已变化，请重新预览。',409)

    def delete(self, data):
        token = data.get('token') if isinstance(data,dict) else None
        if not isinstance(token,str): raise UserError('缺少有效的清理确认。', 409)
        with self.skills.lock, self.store.lock:
            plan = self.plans.pop(token, None)
            if plan is None or plan['expires'] <= time.monotonic():
                raise UserError('清理确认已失效，请重新预览。', 409)
            # Validate every accepted entry before making the first filesystem change.
            for entry in plan['entries']:
                if 'error' in entry: continue
                fresh = self._entry(entry)
                if fresh['_signature'] != entry['_signature']:
                    raise UserError('内容或目录已变化，未执行清理，请重新预览。', 409)
            deleted = 0; failed = []; deleted_paths = []; recycled_paths = []
            for entry in plan['entries']:
                completed = []; attempted = []; intent = False
                try:
                    if 'error' in entry: raise UserError(entry['error'],409)
                    for path,state in entry['_states']:
                        if _disk_state(path) != state:
                            raise UserError('文件在清理过程中发生变化，请重新预览。',409)
                        if state is not None:
                            if not intent:
                                self._begin_recycle(entry); intent = True
                            attempted.append(path)
                            recycled = recycle_path(path)
                            if os.path.lexists(path): raise OSError("Windows 回收操作未完成，映序记录已保留。")
                            completed.append(path)
                            if isinstance(recycled,dict):
                                recycled_paths.append({'path':path,'recycle_path':recycled.get('recycle_path')})
                    # Individual batches commit only after every planned path succeeded.
                    with self.store.connection() as db:
                        if entry['kind'] == 'skill':
                            db.execute('UPDATE yx_skills SET purged=1 WHERE id=? AND removed=1', (entry['id'],))
                            db.execute('DELETE FROM yx_project_skills WHERE skill_id=?', (entry['id'],))
                        else:
                            db.execute('UPDATE trash_batches SET purged=1 WHERE id=? AND restored=0', (entry['id'],))
                    deleted += 1
                except (OSError,UserError,ValueError,sqlite3.Error) as error:
                    notice = '；本条目已有部分文件移入 Windows 回收站，剩余记录已保留。' if completed else ''
                    uncertain = [path for path in attempted if path not in completed]
                    if uncertain: notice += '；回收结果未完整确认，请检查 Windows 回收站。已阻止直接恢复这些记录，可重新预览后继续清理。'
                    failed.append({'id':entry['id'],'kind':entry['kind'],'name':entry['name'],'error':str(error)+notice,'deleted_paths':completed,'uncertain_paths':uncertain})
                finally:
                    deleted_paths.extend(completed)
            with self.store.connection() as db:
                remaining = db.execute('SELECT count(*) FROM trash_batches WHERE restored=0 AND purged=0').fetchone()[0]
                remaining += db.execute('SELECT count(*) FROM yx_skills WHERE removed=1 AND purged=0').fetchone()[0]
            return {'deleted':deleted,'failed':failed,'remaining':remaining,'deleted_paths':deleted_paths,'recycled_paths':recycled_paths}
