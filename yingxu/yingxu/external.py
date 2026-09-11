"""Session-scoped access to explicitly opened files, without importing projects."""
from __future__ import annotations

import os
import hashlib
import io
import json
import stat as stat_module
from contextlib import contextmanager
from pathlib import Path
import threading
import time

from .store import KINDS, TEXT_LIMIT, UserError, clean_path, decode_text, has_link, uid

PREVIEW_KINDS = frozenset(('markdown','text','docx','excalidraw','pdf','image','svg','html','video','audio'))
MAX_OPEN = 200
MAX_SESSION = 256
TTL = 24 * 60 * 60
WORD_LIMIT = 32 * 1024 * 1024
EDIT_KINDS = frozenset(('markdown', 'text', 'docx', 'excalidraw'))
EDIT_NOTICE = '直接编辑原文件；保存前备份，外部修改会触发冲突保护。未加入项目。'


class ExternalPreviews:
    def __init__(self, data_root):
        self.data_root = Path(data_root).resolve()
        self.entries = {}
        self.lock = threading.RLock()

    def _path(self, value):
        if not isinstance(value,str) or not value.strip() or '\x00' in value:
            raise UserError('请选择本机文件的绝对路径。')
        path = clean_path(value)
        if path == self.data_root or path.is_relative_to(self.data_root):
            raise UserError('应用数据、备份和缓存不能作为外部文件预览。',403)
        if not path.is_file() or KINDS.get(path.suffix.lower()) not in PREVIEW_KINDS:
            raise UserError('暂不支持此文件；可预览文本、Word、PDF、图片、SVG、HTML、视频和音频。',415)
        if path.stat().st_nlink > 1:
            raise UserError('共享硬链接文件不能作为外部预览，避免绕过应用数据边界。',403)
        return path

    @staticmethod
    def _metadata(entry,path):
        stat = path.stat(); identity = (stat.st_dev,stat.st_ino)
        if identity != entry['identity']:
            raise UserError('文件已被替换，请重新用映序打开。',409)
        iid = entry['id']
        return {'id':iid,'name':path.stem,'filename':path.name,'kind':KINDS[path.suffix.lower()],
                'ext':path.suffix.lower(),'path':str(path),'size':stat.st_size,'mtime':stat.st_mtime_ns,
                'editable':False,'external':True,'media_url':'/api/external-media/'+iid,
                'content_url':'/api/external/'+iid,'notice':'本地文件未加入项目，也未复制原文件；支持的文稿可编辑保存。'}

    def open(self,data):
        if not isinstance(data,dict) or set(data) != {'paths'}:
            raise UserError('请选择要打开的文件。')
        values=data.get('paths')
        if not isinstance(values,list) or not 1 <= len(values) <= MAX_OPEN:
            raise UserError('一次可打开 1 至 200 个文件。')
        # Validate the complete request before publishing any capability IDs.
        paths=[]; seen=set()
        for value in values:
            path=self._path(value); key=os.path.normcase(str(path))
            if key not in seen: paths.append(path); seen.add(key)
        with self.lock:
            current=time.monotonic()
            self.entries={key:value for key,value in self.entries.items() if value['expires']>current}
            result=[]
            for path in paths:
                stat=path.stat()
                existing = next((entry for entry in self.entries.values()
                    if os.path.normcase(entry['path']) == os.path.normcase(str(path))
                    and entry['identity'] == (stat.st_dev, stat.st_ino)), None)
                if existing:
                    existing['expires'] = current + TTL
                    result.append(self._metadata(existing, path))
                    continue
                while len(self.entries) >= MAX_SESSION:
                    self.entries.pop(next(iter(self.entries)))
                iid=uid()
                entry={'id':iid,'path':str(path),'identity':(stat.st_dev,stat.st_ino),'expires':current+TTL}
                result.append(self._metadata(entry,path)); self.entries[iid]=entry
            return {'entries':result}

    def resolve(self,iid):
        with self.lock:
            entry=self.entries.get(iid)
            if entry is None or entry['expires']<=time.monotonic():
                self.entries.pop(iid,None)
                raise UserError('外部文件预览已过期，请重新打开文件。',404)
            path=self._path(entry['path'])
            self._metadata(entry,path)
            entry['expires']=time.monotonic()+TTL
            return path

    def detail(self,iid):
        with self.lock:
            path=self.resolve(iid); result=self._metadata(self.entries[iid],path)
        kind=result['kind']
        content={'format':kind,'content':'','editable':False,'notice':result['notice']}
        if kind == 'html':
            from .html_content import read_html_content
            with self.open_media(iid) as opened:
                content = read_html_content(opened)
        if kind == 'svg':
            from .svg_content import read_svg_content
            with self.open_media(iid) as opened:
                content = read_svg_content(opened)
        if kind in EDIT_KINDS:
            with self.lock:
                raw = self._read(iid, WORD_LIMIT if kind == 'docx' else TEXT_LIMIT)
            writable = bool(path.stat().st_mode & stat_module.S_IWRITE)
            content.update(etag=hashlib.sha256(raw).hexdigest(), editable=writable,
                           notice=EDIT_NOTICE if writable else '文件为只读，请先修改文件权限或使用系统应用另存副本。')
        if kind in ('markdown','text','excalidraw'):
            text,encoding=decode_text(raw)
            if kind == 'excalidraw':
                from .canvas import validate
                validate(text)
            content.update(content=text,encoding=encoding)
        elif kind=='docx':
            from .docx_io import read_docx
            try:
                preview=read_docx(path,handle=io.BytesIO(raw))
            except ValueError as error: raise UserError(str(error)) from error
            content.update(preview)
            content['paragraphs']=[{**paragraph,'editable':writable and paragraph['editable']} for paragraph in preview['paragraphs']]
            content['editable']=any(paragraph['editable'] for paragraph in content['paragraphs'])
            content['notice']=(EDIT_NOTICE if writable else '文件为只读。')+' '+preview.get('notice','')
        self.resolve(iid)  # Recheck identity and links after reading, before returning text.
        result['content']=content
        result['editable']=content['editable']
        result['notice']=content['notice']
        return result

    def _read(self, iid, limit):
        """Bounded bytes from the capability's verified file handle."""
        with self.open_media(iid) as handle:
            if os.fstat(handle.fileno()).st_size > limit:
                raise UserError('文件超过编辑大小限制，请使用系统应用打开。', 413)
            raw = handle.read(limit + 1)
        if len(raw) > limit:
            raise UserError('文件超过编辑大小限制，请使用系统应用打开。', 413)
        self.resolve(iid)
        return raw

    @staticmethod
    def _text_bytes(before, content):
        if not isinstance(content, str):
            raise UserError('文稿内容必须是文本。')
        text, encoding = decode_text(before)
        if encoding == 'utf-8-sig' and not before.startswith(b'\xef\xbb\xbf'):
            encoding = 'utf-8'
        if encoding == 'utf-16':
            encoding = 'utf-16-le' if before.startswith(b'\xff\xfe') else 'utf-16-be'
        # The editor may produce LF. Preserve a uniform original line ending;
        # mixed-ending source mode supplies its exact draft without normalization.
        crlf = text.count('\r\n'); lf = text.count('\n') - crlf; cr = text.count('\r') - crlf
        if sum(bool(count) for count in (crlf, lf, cr)) == 1:
            ending = '\r\n' if crlf else '\r' if cr else '\n'
            content = content.replace('\r\n', '\n').replace('\r', '\n').replace('\n', ending)
        try:
            if len(content.encode('utf-8')) > TEXT_LIMIT:
                raise UserError('文稿最多 2 MiB。', 413)
            after = content.encode(encoding)
            if encoding in ('utf-16-le', 'utf-16-be'):
                after = before[:2] + after
        except UnicodeError as error:
            raise UserError('新文字无法使用原文件编码保存，请先用系统编辑器另存为 UTF-8。') from error
        if len(after) > TEXT_LIMIT:
            raise UserError('文稿最多 2 MiB。', 413)
        return after

    def save(self, iid, data):
        """Save only the explicit capability, with etag, backup and atomic replace.

        HTTP callers must require the existing session token and same origin.
        No arbitrary path is accepted by this method. No project index is changed.
        """
        with self.lock:
            path = self.resolve(iid)
            kind = KINDS[path.suffix.lower()]
            field = 'paragraphs' if kind == 'docx' else 'content'
            if kind not in EDIT_KINDS:
                raise UserError('此文件类型只能预览。', 415)
            if not isinstance(data, dict) or set(data) != {'etag', field}:
                raise UserError('保存请求必须包含原文件版本和修改内容。')
            if not isinstance(data['etag'], str) or len(data['etag']) != 64:
                raise UserError('文件版本无效，请重新打开文稿。', 409)
            mode = path.stat().st_mode
            if not mode & stat_module.S_IWRITE:
                raise UserError('文件为只读，无法保存；请使用系统应用另存副本。', 403)
            limit = WORD_LIMIT if kind == 'docx' else TEXT_LIMIT
            before = self._read(iid, limit)
            digest = hashlib.sha256(before).hexdigest()
            if digest != data['etag']:
                raise UserError('原文件已被其他程序修改。草稿仍保留，请重新打开并比较后保存。', 409)
            if kind == 'docx':
                from .docx_io import edit_docx
                try:
                    after = edit_docx(path, data[field], handle=io.BytesIO(before))
                except ValueError as error:
                    raise UserError(str(error)) from error
                if len(after) > WORD_LIMIT:
                    raise UserError('Word 文件超过 32 MiB，请使用系统应用编辑。', 413)
            else:
                if kind == 'excalidraw':
                    from .canvas import validate
                    validate(data[field])
                after = self._text_bytes(before, data[field])
            if after == before:
                return self.detail(iid)
            vid = uid()
            key = hashlib.sha256(os.path.normcase(str(path)).encode('utf-8')).hexdigest()
            folder = self.data_root / 'external-versions' / key
            if any(has_link(parent) for parent in (folder, *folder.parents) if parent.exists()):
                raise UserError('备份目录包含链接，已停止保存。', 403)
            folder.mkdir(parents=True, exist_ok=True)
            clean_path(folder)  # Refuse redirected backup directories too.
            backup = folder / (vid + path.suffix)
            temporary = path.with_name('.' + path.name + '.' + vid + '.tmp')
            try:
                with backup.open('xb') as handle:
                    handle.write(before); handle.flush(); os.fsync(handle.fileno())
                with (folder / (vid + '.metadata.json')).open('x', encoding='utf-8') as handle:
                    json.dump({'path': str(path), 'sha256': digest, 'created': time.time(),
                               'size': len(before), 'file': backup.name}, handle, ensure_ascii=False)
                    handle.flush(); os.fsync(handle.fileno())
                with temporary.open('xb') as handle:
                    handle.write(after); handle.flush(); os.fsync(handle.fileno())
                os.chmod(temporary, stat_module.S_IMODE(mode))
                if hashlib.sha256(self._read(iid, limit)).hexdigest() != digest:
                    raise UserError('保存过程中原文件发生改变，已停止覆盖；草稿仍保留。', 409)
                self.resolve(iid)
                os.replace(temporary, path)
                current = path.stat()
                # Other tabs for this explicit path remain valid capabilities;
                # their older etags still prevent overwriting this saved revision.
                for entry in self.entries.values():
                    if os.path.normcase(entry['path']) == os.path.normcase(str(path)):
                        entry['identity'] = (current.st_dev, current.st_ino)
            except OSError as error:
                raise UserError('文件无法保存，可能被占用或没有写入权限；原稿备份和草稿已保留。', 409) from error
            finally:
                if temporary.exists():
                    temporary.unlink()
            result = self.detail(iid)
            result['backup_id'] = vid
            return result

    @contextmanager
    def open_media(self,iid):
        with self.lock:
            path=self.resolve(iid); identity=self.entries[iid]['identity']
            handle=path.open('rb')
            try:
                stat=os.fstat(handle.fileno())
                if stat.st_nlink > 1:
                    raise UserError('文件已变为共享硬链接，已停止预览。',403)
                if (stat.st_dev,stat.st_ino)!=identity:
                    raise UserError('文件已被替换，请重新打开。',409)
                self.resolve(iid)
            except Exception:
                handle.close(); raise
        try: yield handle
        finally: handle.close()
