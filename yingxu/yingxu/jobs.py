"""Bounded asynchronous indexing and media previews."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time

from .runtime import ffmpeg_path
from .store import SAFE_EXTENSIONS, UserError, clean_path, has_link, uid


class Jobs:
    def __init__(self,store,on_change=None):
        self.store=store; self.on_change=on_change
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='yingxu-index')
        self.jobs={}; self.lock=threading.Lock()
        self.slots=threading.BoundedSemaphore(8)

    def submit(self,pid,category='references',paths=None,folder_id=''):
        self.store.get_project(pid)
        if folder_id!='':
            from .organize import Organize
            Organize(self.store).folder_path(pid,category,None if folder_id=='root' else folder_id)
        if paths is not None:
            if not isinstance(paths,list) or not 1<=len(paths)<=200:raise UserError('一次请选择1至200个文件或文件夹。')
            sources=[]
            for value in paths:
                path=clean_path(value)
                if path.is_file() and path.suffix.lower()=='.zip':
                    if path.is_relative_to(self.store.data_root):raise UserError('不能从应用数据目录导入 ZIP。')
                    sources.append({'archive':str(path),'name':path.name})
                else:sources.append(self.store.register_source(pid,value,category))
        else:sources=self.store.sources(pid)
        return self._enqueue(pid,category,sources,paths is not None,folder_id)

    def submit_archive(self,pid,category,path,folder_id=None,name=None,cleanup=False):
        from .organize import Organize
        Organize(self.store).folder_path(pid,category,folder_id)
        path=clean_path(path)
        if not path.is_file():raise UserError('ZIP 来源不存在。')
        if cleanup and (path.parent!=self.store.data_root/'archive-uploads' or path.suffix!='.zip'):
            raise UserError('临时 ZIP 路径无效。')
        return self._enqueue(pid,category,[{'archive':str(path),'name':name or path.name,'cleanup':cleanup}],True,folder_id)

    def _enqueue(self,pid,category,sources,restore_removed,folder_id):
        if not self.slots.acquire(False):raise UserError('导入队列已满，请等当前任务完成。',429)
        jid=uid()
        with self.lock:
            self.jobs[jid]={'id':jid,'state':'queued','done':0,'skipped':0,'errors':[],'message':'等待索引','project_id':pid}
            if len(self.jobs)>100:
                old=[key for key,val in self.jobs.items() if val['state'] in ('done','error')]
                for key in old[:len(self.jobs)-100]:self.jobs.pop(key,None)
        self.pool.submit(self._run,jid,pid,sources,restore_removed,category,folder_id)
        return {'job_id':jid}

    def get(self,jid):
        with self.lock:
            if jid not in self.jobs:raise UserError('任务记录已过期，请刷新项目。',404)
            result=dict(self.jobs[jid]);result['errors']=list(result['errors']);return result

    def _update(self,jid,**fields):
        with self.lock:self.jobs[jid].update(fields)

    @staticmethod
    def walk(root,excluded=None):
        excluded=Path(excluded).resolve() if excluded else None
        if excluded and (root==excluded or root.is_relative_to(excluded)):return
        if root.is_file():yield root;return
        stack=[root]
        ignored={'.git','.yingxu','node_modules','__pycache__','.venv','venv','.obsidian'}
        while stack:
            folder=stack.pop()
            try:
                with os.scandir(folder) as entries:
                    for entry in entries:
                        if entry.name.startswith('.') or entry.name in ignored:continue
                        try:
                            path=Path(entry.path)
                            if excluded and (path==excluded or path.is_relative_to(excluded)):continue
                            if has_link(path):continue
                            if entry.is_dir(follow_symlinks=False):stack.append(path)
                            elif entry.is_file(follow_symlinks=False) and path.suffix.lower() in SAFE_EXTENSIONS:yield path
                        except OSError:continue
            except OSError:continue

    def _run(self,jid,pid,sources,restore_removed=False,category='references',folder_id=''):
        self._update(jid,state='running',message='正在建立素材索引，可继续使用工作台')
        done=skipped=0;errors=[]
        destination=({'target_folder_id':None if folder_id in (None,'root') else folder_id,
                      'target_category':category} if folder_id!='' else {})
        try:
            for source in sources:
                try:
                    if 'archive' in source:
                        from .archive_import import import_zip
                        try:
                            result=import_zip(self.store,source['archive'],pid,category,folder_id,source['name'],
                                lambda message:self._update(jid,message=message))
                            done+=result['done'];skipped+=result['skipped'];self._update(jid,done=done,skipped=skipped)
                        finally:
                            if source.get('cleanup'):Path(source['archive']).unlink(missing_ok=True)
                        continue
                    root=clean_path(source['path']);batch=[]
                    for path in self.walk(root,self.store.data_root):
                        batch.append(path)
                        if len(batch)>=64:
                            added,unchanged=self.store.index_files(source,batch,restore_removed,**destination);done+=added;skipped+=unchanged
                            batch=[]
                            self._update(jid,done=done,skipped=skipped)
                    if batch:
                        added,unchanged=self.store.index_files(source,batch,restore_removed,**destination);done+=added;skipped+=unchanged
                except (OSError,UserError,ValueError) as e:
                    if len(errors)<20:errors.append(str(e))
            if self.on_change:self.on_change(pid)
            self._update(jid,state='done',done=done,skipped=skipped,errors=errors,message=f'完成：新增或更新 {done} 项，未变更或跳过 {skipped} 项')
        except Exception as e:
            self._update(jid,state='error',done=done,skipped=skipped,errors=[type(e).__name__],message='索引遇到错误，已有资料未移动；请查看服务日志。')
            import traceback;traceback.print_exc()
        finally:self.slots.release()


class Thumbnails:
    def __init__(self,store):
        self.store=store;self.root=store.data_root / 'thumbnails';self.root.mkdir(exist_ok=True)
        self.pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='yingxu-thumbnail')
        self.slots=threading.BoundedSemaphore(64);self.lock=threading.Lock();self.pending=set();self.failed={}
        self.ffmpeg=ffmpeg_path();self.generated=0

    def request(self,iid):
        item=self.store.get_item(iid)
        if item['kind'] not in ('image','video'):raise UserError('此条目没有媒体缩略图。',404)
        path=self.store.resolve_item_path(item);st=path.stat()
        key=hashlib.sha256(f'{path}|{st.st_size}|{st.st_mtime_ns}|640-v1'.encode()).hexdigest()
        target=self.root / (key+'.jpg')
        with self.lock:
            if target.exists():return target
            if key in self.failed:
                if time.monotonic()-self.failed[key]<300:raise UserError('缩略图暂不可用，可尝试打开原文件。',422)
                self.failed.pop(key,None)
            if key not in self.pending and self.slots.acquire(False):
                self.pending.add(key);self.pool.submit(self._generate,key,path,item['kind'],target)
        return None

    def _generate(self,key,path,kind,target):
        tmp=target.with_name(key+'.tmp.jpg')
        try:
            if kind=='image':
                from PIL import Image,ImageOps
                if path.stat().st_size>256*1024*1024:raise ValueError('Oversized preview')
                with Image.open(path) as source:
                    if source.width*source.height>40_000_000:raise ValueError('Oversized decoded image')
                    source.draft('RGB',(640,640))
                    # Small preview first; EXIF transpose after reducing pixels.
                    source.thumbnail((640,640))
                    preview=ImageOps.exif_transpose(source)
                    if preview.mode not in ('RGB','L'):
                        bg=Image.new('RGB',preview.size,(30,33,32))
                        if 'A' in preview.getbands():bg.paste(preview,mask=preview.getchannel('A'))
                        else:bg.paste(preview.convert('RGB'))
                        preview=bg
                    preview.save(tmp,'JPEG',quality=82,optimize=True)
            else:
                if not self.ffmpeg:raise ValueError('FFmpeg unavailable')
                subprocess.run([self.ffmpeg,'-nostdin','-hide_banner','-loglevel','error','-threads','1','-i',str(path),'-vf','scale=640:-2','-frames:v','1','-threads','1','-y',str(tmp)],
                    check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=18,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            os.replace(tmp,target)
            with self.lock:self.generated+=1;prune=self.generated%128==0
            if prune:self.prune()
        except Exception:
            with self.lock:
                if len(self.failed)>1024:self.failed.clear()
                self.failed[key]=time.monotonic()
        finally:
            if tmp.exists():tmp.unlink(missing_ok=True)
            with self.lock:self.pending.discard(key)
            self.slots.release()

    def prune(self):
        # Only generated cache members; never touch source assets.
        members=[];total=0
        for p in self.root.glob('*.jpg'):
            if re_cache_name(p.name) and not has_link(p):
                st=p.stat();members.append((st.st_mtime_ns,p,st.st_size));total+=st.st_size
        if total<=2*1024**3 and len(members)<=10000:return
        members.sort();remaining=len(members)
        for _,p,size in members:
            if total<=int(1.8*1024**3) and remaining<=9000:break
            p.unlink(missing_ok=True);total-=size;remaining-=1


def re_cache_name(name):
    import re
    return bool(re.fullmatch(r'[a-f0-9]{64}\.jpg',name))
