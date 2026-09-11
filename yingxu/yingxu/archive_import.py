"""Bounded ZIP-to-project import. Original archives are never changed."""
import os
from pathlib import Path
import shutil
import stat
import struct
import tempfile
import unicodedata
import zipfile
import zlib

from .store import CATEGORIES, SAFE_EXTENSIONS, UserError, clean_path, now, safe_name, uid
from .organize import Organize, _rename

MAX_ARCHIVE = 8 * 1024**3
MAX_EXPANDED = 32 * 1024**3
MAX_ENTRIES = 10000
MAX_DIRECTORY = 32 * 1024**2


def _check_directory(handle):
    """Bound the central directory before ZipFile allocates its member records."""
    handle.seek(0, 2); size = handle.tell()
    if size > MAX_ARCHIVE: raise UserError('ZIP 最大支持 8 GiB。')
    handle.seek(max(0, size-65557)); tail = handle.read()
    offset = tail.rfind(b'PK\x05\x06')
    if offset < 0 or len(tail)-offset < 22: raise UserError('ZIP 文件不完整或已损坏。')
    _, disk, central_disk, count_disk, count, central_size, central_offset, comment = struct.unpack_from('<4s4H2LH', tail, offset)
    if len(tail)-offset != 22+comment or disk or central_disk or count_disk != count:
        raise UserError('暂不支持分卷 ZIP，或压缩包目录已损坏。')
    if count == 65535 or central_size == 0xffffffff or central_offset == 0xffffffff:
        position = size-len(tail)+offset
        if position < 20: raise UserError('ZIP64 目录不完整。')
        handle.seek(position-20); locator = handle.read(20)
        signature, disk, record, disks = struct.unpack('<4sLQL', locator)
        if signature != b'PK\x06\x07' or disk or disks != 1 or record > size-56:
            raise UserError('不支持这个 ZIP64 分卷格式。')
        handle.seek(record); values = struct.unpack('<4sQ2H2L4Q', handle.read(56))
        if values[0] != b'PK\x06\x06' or values[4] or values[5] or values[6] != values[7]:
            raise UserError('ZIP64 目录不完整。')
        count, central_size = values[7], values[8]
    if count > MAX_ENTRIES or central_size > MAX_DIRECTORY:
        raise UserError('ZIP 最多支持 10000 个条目，目录信息不得超过 32 MiB。')
    handle.seek(0)


def _member_name(info):
    name = info.orig_filename
    if not info.flag_bits & 0x800:
        try: name = name.encode('cp437').decode('gb18030')
        except (UnicodeError, LookupError): pass
    name = unicodedata.normalize('NFC', name).replace('\\', '/')
    parts = name.rstrip('/').split('/')
    if not name or name.startswith('/') or any(not p or p in ('.', '..') or safe_name(p) != p.lstrip('.') for p in parts):
        raise UserError('ZIP 含有不支持或越界的文件路径，未导入。')
    mode = stat.S_IFMT(info.external_attr >> 16)
    if mode not in (0, stat.S_IFREG, stat.S_IFDIR) or info.external_attr & 0x400:
        raise UserError('ZIP 含有链接或特殊文件，未导入。')
    return tuple(parts), info.is_dir() or name.endswith('/')


def import_zip(store, path, pid, category, folder_id=None, name=None, progress=lambda message: None):
    organize = Organize(store)
    folder_id = None if folder_id in ('', None, 'root') else folder_id
    parent = organize.folder_path(pid, category, folder_id)
    project_root = clean_path(store.get_project(pid)['root'])
    source_path = clean_path(path)
    if not source_path.is_file(): raise UserError('ZIP 来源不存在。')
    base_name = safe_name(Path(name or source_path.name).stem)
    depth = len(parent.relative_to(project_root/CATEGORIES[category][1]).parts)+1
    try:
        with source_path.open('rb') as source:
            before = os.fstat(source.fileno())
            _check_directory(source)
            with zipfile.ZipFile(source) as archive:
                entries = archive.infolist()
                if len(entries) > MAX_ENTRIES: raise UserError('ZIP 条目过多。')
                files = []; directories = set(); seen = {}; skipped = 0; expanded = 0
                for info in entries:
                    parts, is_dir = _member_name(info)
                    key = tuple(p.casefold() for p in parts)
                    if key in seen: raise UserError('ZIP 含有重复或仅大小写不同的路径，未导入。')
                    seen[key] = (parts, is_dir)
                    if info.flag_bits & 1: raise UserError('第一版暂不支持加密 ZIP，请先解密。')
                    if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                        raise UserError('请使用 ZIP 的标准存储或 Deflate 压缩方式。')
                    expanded += info.file_size
                    if expanded > MAX_EXPANDED or (info.file_size > 1024**2 and info.file_size > max(1, info.compress_size)*2000):
                        raise UserError('ZIP 解压体积超过 32 GiB，或压缩比异常。')
                    if any(p.startswith('.') or p == '__MACOSX' for p in parts):
                        skipped += int(not is_dir); continue
                    if not is_dir and Path(parts[-1]).suffix.lower() not in SAFE_EXTENSIONS:
                        skipped += 1; continue
                    count = len(parts) if is_dir else len(parts)-1
                    if depth+count > 20: raise UserError('解压后的文件夹超过 20 层。')
                    for n in range(1, count+1): directories.add(parts[:n])
                    if not is_dir: files.append((info, parts))
                # Include implicit directories when checking portable path collisions.
                portable = {}
                for parts in directories:
                    key = tuple(p.casefold() for p in parts)
                    if key in portable and portable[key] != parts: raise UserError('ZIP 文件夹名称存在大小写冲突。')
                    portable[key] = parts
                    if key in seen and (not seen[key][1] or seen[key][0] != parts):
                        raise UserError('ZIP 文件与文件夹路径冲突。')
                if not files: raise UserError(f'ZIP 中没有可导入的素材，已跳过 {skipped} 个不支持或隐藏的文件。')
                if len(directories)+1 > 5000: raise UserError('ZIP 文件夹数量超过项目上限。')
                required = sum(info.file_size for info, _ in files)
                if shutil.disk_usage(parent).free < required+512*1024**2: raise UserError('项目磁盘剩余空间不足。',507)
                staging_parent=project_root/'.yingxu'/'archive-staging'
                (project_root/'.yingxu').mkdir(exist_ok=True)
                clean_path(project_root/'.yingxu')
                staging_parent.mkdir(exist_ok=True);clean_path(staging_parent)
                with tempfile.TemporaryDirectory(prefix='.yingxu-archive-', dir=staging_parent) as temporary:
                    stage = Path(temporary).resolve()
                    if not stage.is_relative_to(staging_parent): raise UserError('临时解压路径无效。')
                    for parts in sorted(directories, key=lambda p: (len(p), p)):
                        (stage.joinpath(*parts)).mkdir(exist_ok=True)
                    for index, (info, parts) in enumerate(files, 1):
                        progress(f'正在解压 {index}/{len(files)}：{parts[-1]}')
                        target = stage.joinpath(*parts); clean_path(target.parent)
                        written = 0
                        with archive.open(info) as incoming, target.open('xb') as output:
                            while block := incoming.read(1024**2):
                                written += len(block)
                                if written > info.file_size: raise UserError('ZIP 解压大小与目录记录不一致。')
                                output.write(block)
                        if written != info.file_size: raise UserError('ZIP 文件不完整。')
                    after = os.fstat(source.fileno())
                    if (before.st_size,before.st_mtime_ns) != (after.st_size,after.st_mtime_ns):
                        raise UserError('ZIP 在导入期间发生变化，请重试。')
                    with store.lock:
                        if organize.folder_path(pid,category,folder_id) != parent: raise UserError('导入期间目标文件夹发生变化。',409)
                        target = parent/base_name; suffix = 1
                        while target.exists() or target.is_symlink():
                            target = parent/(base_name[:85]+f'_{suffix}'); suffix += 1
                        ids = {():uid(), **{parts:uid() for parts in directories}}
                        published = False
                        try:
                            with store.connection() as db:
                                db.execute('BEGIN IMMEDIATE'); store._project(db,pid)
                                existing = db.execute('SELECT count(*) FROM folders WHERE project_id=? AND removed=0',(pid,)).fetchone()[0]
                                if existing+len(ids)>5000: raise UserError('导入后将超过项目 5000 个文件夹上限。')
                                _rename(stage,target); published = True
                                for parts in sorted(ids,key=lambda p:(len(p),p)):
                                    destination = target.joinpath(*parts)
                                    db.execute('INSERT INTO folders(id,project_id,category,parent_id,name,relative_path,created,updated) VALUES(?,?,?,?,?,?,?,?)',
                                        (ids[parts],pid,category,ids[parts[:-1]] if parts else folder_id,destination.name,destination.relative_to(project_root).as_posix(),now(),now()))
                        except Exception:
                            if published: _rename(target,stage)
                            raise
                    source_record = next(s for s in store.sources(pid) if s['path']==str(project_root))
                    done = 0
                    try:
                        for start in range(0,len(files),64):
                            progress(f'正在索引解压素材 {start}/{len(files)}')
                            added, unchanged = store.index_files(source_record,[target.joinpath(*parts) for _,parts in files[start:start+64]])
                            done += added; skipped += unchanged
                    except Exception as error:
                        raise UserError(f'文件已完整解压至「{target.name}」，索引未完成；请点击同步项目文件。') from error
                    return {'done':done,'skipped':skipped,'folder_id':ids[()],'name':target.name}
    except (zipfile.BadZipFile, EOFError, struct.error, RuntimeError, zlib.error) as error:
        raise UserError('ZIP 文件损坏或使用了暂不支持的格式，未完成解压。') from error
