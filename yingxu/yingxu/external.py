"""Session-only, read-only previews of explicitly opened files. No project writes."""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
import threading
import time

from .store import KINDS, TEXT_LIMIT, UserError, clean_path, decode_text, uid

PREVIEW_KINDS = frozenset(('markdown','text','docx','pdf','image','video','audio'))
MAX_OPEN = 200
MAX_SESSION = 256
TTL = 24 * 60 * 60


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
            raise UserError('暂不支持此文件；可预览文本、Word、PDF、图片、视频和音频。',415)
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
                'content_url':'/api/external/'+iid,'notice':'外部文件只读预览；未加入项目，也未复制原文件。'}

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
            while len(self.entries)+len(paths)>MAX_SESSION: self.entries.pop(next(iter(self.entries)))
            result=[]
            for path in paths:
                stat=path.stat(); iid=uid()
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
        if kind in ('markdown','text'):
            if path.stat().st_size>TEXT_LIMIT:
                raise UserError('文本超过 2 MiB，请使用系统编辑器打开。',413)
            # Read at most the preview limit even if another app grows the file.
            with self.open_media(iid) as handle: raw=handle.read(TEXT_LIMIT+1)
            if len(raw)>TEXT_LIMIT: raise UserError('文本超过预览大小限制。',413)
            text,encoding=decode_text(raw); content.update(content=text,encoding=encoding)
        elif kind=='docx':
            if path.stat().st_size>32*1024*1024:
                raise UserError('Word 文件超过 32 MiB，请使用系统应用打开。',413)
            from .docx_io import read_docx
            try:
                with self.open_media(iid) as handle: preview=read_docx(path,handle=handle)
            except ValueError as error: raise UserError(str(error)) from error
            content.update(preview)
            content['paragraphs']=[{**paragraph,'editable':False} for paragraph in preview['paragraphs']]
            content['notice']=result['notice']+' '+preview.get('notice','')
        self.resolve(iid)  # Recheck identity and links after reading, before returning text.
        result['content']=content
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
