"""映序 local HTTP application. No external services, package installs or telemetry."""
from __future__ import annotations
import argparse
from contextlib import nullcontext
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import parse_qs,urlsplit

from yingxu import __version__
from yingxu.runtime import image_support
from yingxu.paths import default_data_root, default_project_root, instance_id
from yingxu.store import Store,UserError,CATEGORIES,STATUSES,SAFE_EXTENSIONS
from yingxu.store import safe_name,uid,clean_path
from yingxu.jobs import Jobs,Thumbnails

ROOT=Path(__file__).resolve().parent


class Application:
    def __init__(self,data_root,project_root):
        self.store=Store(data_root,project_root)
        resume_token=os.environ.pop('YINGXU_RESUME_SESSION_TOKEN','')
        self.token=resume_token if re.fullmatch(r'[A-Za-z0-9_-]{40,128}',resume_token) else secrets.token_urlsafe(32)
        self.picker_lock=threading.Lock()
        self.native_picker=None
        self.demo_lock=threading.Lock()
        from yingxu.skills import SkillLibrary
        from yingxu.context import ContextExporter
        from yingxu.organize import Organize
        self.organize=Organize(self.store)
        self.skills=SkillLibrary(self.store)
        self.context=ContextExporter(self.store,self.skills)
        self.jobs=Jobs(self.store,self.context.request)
        self.thumbnails=Thumbnails(self.store)
        from yingxu.trash import TrashDeletion
        self.trash_deletion=TrashDeletion(self.store,self.skills)
        from yingxu.settings import Settings
        from yingxu.external import ExternalPreviews
        from yingxu.project_library import ProjectLibrary
        self.settings=Settings(self.store.data_root)
        self.external=ExternalPreviews(self.store.data_root)
        self.project_library=ProjectLibrary(self.store)
        from yingxu.search import GlobalSearch
        self.search=GlobalSearch(self.store,self.skills)
        from yingxu.resource_groups import ResourceGroups
        self.resource_groups=ResourceGroups(self.store)
        from yingxu.markdown_assets import MarkdownAssets
        self.markdown_assets=MarkdownAssets(self.store)

    def bootstrap(self):
        return {'app':'yingxu','version':__version__,'token':self.token,'settings':self.settings.get(),
          'project_root':str(self.store.project_root),'data_root':str(self.store.data_root),
          'categories':[{'key':k,'label':v[0]} for k,v in CATEGORIES.items()], 'statuses':STATUSES,
          'capabilities':{'thumbnails':image_support(), 'image_thumbnails':image_support(),'ffmpeg':bool(self.thumbnails.ffmpeg),'docx_edit':True,'platform':sys.platform,'native_picker':os.name=='nt' or self.native_picker is not None,'skills':True,'project_context':True,'folders':True,'trash':True,'move_files':True,'trash_delete':True,'settings':True,'external_open':True,'project_library':True,'global_search':True,'resource_groups':True}}

    def changed(self,project_id=None):
        with self.store.connection() as db:
            rows=db.execute('SELECT id FROM projects WHERE removed=0'+(' AND id=?' if project_id else ''),
                            (project_id,) if project_id else ()).fetchall()
        for row in rows:self.context.request(row['id'])

    def trash(self,project_id='',limit=48,offset=0,q=''):
        limit=max(1,min(200,int(limit)));offset=max(0,min(10_000_000,int(offset)))
        where='b.restored=0 AND b.purged=0';args=[]
        if project_id:where+=' AND b.project_id=?';args.append(project_id)
        union='''SELECT b.id,b.id AS batch_id,b.kind,b.target_id,b.project_id,b.name,b.created,
            (SELECT count(*) FROM trash_members m WHERE m.batch_id=b.id) AS count,
            NULL AS source,NULL AS editable,NULL AS path FROM trash_batches b WHERE '''+where+'''
            UNION ALL SELECT id,id,'skill',id,NULL,name,removed_at,1,source,editable,path
            FROM yx_skills WHERE removed=1 AND purged=0'''
        q=str(q).strip()
        if len(q)>1000:raise UserError('搜索内容过长。')
        filtered=' FROM ('+union+')'
        if q:filtered+=' WHERE instr(lower(name),lower(?))>0';args.append(q)
        with self.store.connection() as db:
            total=db.execute('SELECT count(*)'+filtered,args).fetchone()[0]
            entries=[dict(row) for row in db.execute('SELECT *'+filtered+' ORDER BY created DESC,id LIMIT ? OFFSET ?',[*args,limit,offset])]
        return {'entries':entries,'total':total,'limit':limit,'offset':offset,'truncated':offset+len(entries)<total}

    def pick(self,kind):
        if sys.platform=='darwin' and self.native_picker is not None:
            if kind not in ('folder','files'):raise UserError('选择器类型不正确。')
            if not self.picker_lock.acquire(False):raise UserError('已有一个文件选择窗口打开。',409)
            try:return {'paths':list(self.native_picker(kind) or [])}
            finally:self.picker_lock.release()
        if os.name!='nt':raise UserError('当前环境不支持原生选择器，请粘贴本机绝对路径。')
        if not self.picker_lock.acquire(False):raise UserError('已有一个文件选择窗口打开，请先完成选择。',409)
        try:
            if kind=='folder':
                script="Add-Type -AssemblyName System.Windows.Forms; $d=New-Object Windows.Forms.FolderBrowserDialog; $d.Description='选择要引用的素材文件夹'; $d.ShowNewFolderButton=$false; if($d.ShowDialog() -eq 'OK'){@($d.SelectedPath)|ConvertTo-Json -Compress} else {'[]'}"
            elif kind=='files':
                script="Add-Type -AssemblyName System.Windows.Forms; $d=New-Object Windows.Forms.OpenFileDialog; $d.Title='选择素材、剧本或分镜文件'; $d.Multiselect=$true; $d.Filter='创作文件|*.md;*.txt;*.docx;*.doc;*.pdf;*.png;*.jpg;*.jpeg;*.webp;*.gif;*.mp4;*.mov;*.webm;*.mkv;*.wav;*.mp3;*.blend;*.glb;*.fbx;*.obj;*.srt;*.json;*.csv|所有文件|*.*'; if($d.ShowDialog() -eq 'OK'){@($d.FileNames)|ConvertTo-Json -Compress} else {'[]'}"
            else:raise UserError('选择器类型不正确。')
            import base64
            prefix='[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding; '
            encoded=base64.b64encode((prefix+script).encode('utf-16-le')).decode('ascii')
            ps=Path(os.environ.get('WINDIR','C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
            try:
                result=subprocess.run([str(ps),'-NoProfile','-STA','-EncodedCommand',encoded],capture_output=True,timeout=300,creationflags=subprocess.CREATE_NO_WINDOW)
            except subprocess.TimeoutExpired:raise UserError('选择窗口等待超时，请重新打开。')
            if result.returncode:raise UserError('选择器未能打开，请使用粘贴路径导入。')
            try:paths=json.loads(result.stdout.decode('utf-8-sig').strip() or '[]')
            except (ValueError,UnicodeError):raise UserError('未能读取选择结果，请使用粘贴路径导入。')
            return {'paths':[paths] if isinstance(paths,str) else paths}
        finally:self.picker_lock.release()

    def open_file(self,data):
        item=self.store.get_item(data.get('id'));path=self.store.resolve_item_path(item)
        action=data.get('action','open')
        if sys.platform=='darwin':
            if action not in ('reveal','open'):raise UserError('不支持的打开方式。')
            from yingxu.macos import open_path
            open_path(path,reveal=action=='reveal')
            return {'ok':True}
        if os.name!='nt':raise UserError('此操作需要 Windows 桌面环境。')
        if action=='reveal':subprocess.Popen(['explorer.exe','/select,',str(path)],creationflags=subprocess.CREATE_NO_WINDOW)
        elif action=='open':os.startfile(str(path))
        else:raise UserError('不支持的打开方式。')
        return {'ok':True}

    def open_folder(self,data):
        if not isinstance(data,dict) or set(data)-{'project_id','category','folder_id','skill_id'}:
            raise UserError('请选择已登记的项目文件夹或 SKILL。')
        skill_target='skill_id' in data
        if skill_target and (set(data)!={'skill_id'} or not isinstance(data['skill_id'],str) or not re.fullmatch('[a-f0-9]{32}',data['skill_id'])):
            raise UserError('SKILL 位置请求仅接受一个有效的 skill_id。')
        if os.name!='nt' and sys.platform!='darwin':raise UserError('此操作需要桌面环境。')
        with self.skills.lock,self.store.lock:
            if skill_target:
                path=self.skills.directory(data['skill_id'])
            else:
                project=self.store.get_project(data.get('project_id'))
                root=clean_path(project['root'])
                folder_id=data.get('folder_id')
                if folder_id not in (None,'','root'):
                    folder=self.organize.get_folder(folder_id)
                    if folder['project_id']!=project['id']:raise UserError('文件夹不属于这个项目。',403)
                    path=self.organize.folder_path(project['id'],folder['category'],folder_id)
                elif data.get('category') not in (None,'','all'):
                    path=self.organize.folder_path(project['id'],data['category'])
                else:path=root
                if not path.is_relative_to(root):raise UserError('文件夹不存在或路径已改变。',404)
            path=clean_path(path)
            if not path.is_dir():raise UserError('文件夹不存在或路径已改变。',404)
            if sys.platform=='darwin':
                from yingxu.macos import open_path
                open_path(path)
            else:
                explorer=Path(os.environ.get('WINDIR','C:/Windows'))/'explorer.exe'
                subprocess.Popen([str(explorer),str(path)],creationflags=subprocess.CREATE_NO_WINDOW)
        return {'ok':True}

    def receive_upload(self,handler,query):
        pid=query.get('project','');category=query.get('category','references')
        if category not in CATEGORIES:raise UserError('请选择有效分类。')
        project=self.store.get_project(pid)
        if handler.headers.get('Transfer-Encoding'):raise UserError('请使用工作台拖放上传，当前传输格式不支持。')
        try:length=int(handler.headers.get('Content-Length','-1'))
        except ValueError:raise UserError('无法读取文件大小。')
        if not 0<=length<=128*1024**3:raise UserError('单文件须小于128 GiB。',413)
        filename=safe_name(query.get('name',''))
        if Path(filename).suffix.lower() not in SAFE_EXTENSIONS:raise UserError('此文件类型暂不支持导入。')
        root=clean_path(project['root'])
        folder_id=query.get('folder_id')
        folder=self.organize.folder_path(pid,category,None if folder_id in ('','root',None) else folder_id)
        folder.mkdir(parents=True,exist_ok=True);clean_path(folder)
        if shutil.disk_usage(folder).free<length+512*1024*1024:raise UserError('项目磁盘剩余空间不足。',507)
        target=folder/filename
        if target.exists():target=target.with_name(target.stem+'_'+uid()[:6]+target.suffix)
        temporary=folder/('.yingxu-upload-'+uid()+'.tmp')
        try:
            with self.store.lock:
                self.organize.folder_path(pid,category,None if folder_id in ('','root',None) else folder_id)
                output=temporary.open('xb')
            with output as out:
                remaining=length
                while remaining:
                    chunk=handler.rfile.read(min(1024*1024,remaining))
                    if not chunk:raise UserError('上传中断，未完成的文件不会进入项目。')
                    out.write(chunk);remaining-=len(chunk)
                out.flush();os.fsync(out.fileno())
            with self.store.lock:
                # The destination may have been recycled during a long stream.
                # Revalidate before publication; failed uploads leave only removable temp data.
                current_folder=self.organize.folder_path(pid,category,None if folder_id in ('','root',None) else folder_id)
                if current_folder!=folder:raise UserError('上传期间目标文件夹已改变，请重新导入。',409)
                # Exclusive destination publication, so racing uploads cannot replace a file.
                if os.name=='nt':os.rename(temporary,target)
                else:
                    os.link(temporary,target);temporary.unlink()
                source=next(s for s in self.store.sources(pid) if s['path']==str(root))
                self.store.index_files(source,[target])
                self.organize.assign_imported(source,[target],category,None if folder_id in ('','root',None) else folder_id)
                with self.store.connection() as db:iid=db.execute('SELECT id FROM items WHERE project_id=? AND path=?',(pid,str(target))).fetchone()[0]
            self.context.request(pid)
            return self.store.get_item(iid,True)
        finally:
            if temporary.exists():temporary.unlink(missing_ok=True)


class Server(ThreadingHTTPServer):
    daemon_threads=True
    allow_reuse_address=False
    def __init__(self,address,app):
        self.app=app
        self.slots=threading.BoundedSemaphore(24)
        super().__init__(address,Handler)
    def process_request(self,request,client_address):
        if not self.slots.acquire(timeout=1):
            self.shutdown_request(request);return
        try:super().process_request(request,client_address)
        except Exception:self.slots.release();raise
    def process_request_thread(self,request,client_address):
        try:super().process_request_thread(request,client_address)
        finally:self.slots.release()


def parse_range(header,length):
    if not header:return 0,length-1,False
    match=re.fullmatch(r'bytes=(\d*)-(\d*)',header.strip())
    if not match or (not match[1] and not match[2]):raise UserError('不支持的媒体范围。',416)
    if not match[1]:
        size=int(match[2]);start=max(0,length-size);end=length-1
        if size<=0:raise UserError('媒体范围无效。',416)
    else:
        start=int(match[1]);end=min(int(match[2]) if match[2] else length-1,length-1)
    if start>=length or start>end:raise UserError('媒体范围超出文件。',416)
    return start,end,True


class Handler(BaseHTTPRequestHandler):
    server_version=f'YingXu/{__version__}'
    protocol_version='HTTP/1.1'

    def setup(self):
        super().setup();self.connection.settimeout(30)

    @property
    def app(self):return self.server.app

    def log_message(self,fmt,*args):
        # No query strings, local file paths, tokens, or document text in access logs.
        if args and isinstance(args[0],str) and 'api/health' in args[0]:return
        print(f'[{self.log_date_time_string()}] {self.command} {urlsplit(self.path).path} {args[1] if len(args)>1 else ""}',flush=True)

    def headers_common(self,content_type):
        self.send_header('Content-Type',content_type)
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('X-Frame-Options','SAMEORIGIN')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; font-src 'self'; connect-src 'self'; object-src 'self'; frame-src 'self' blob:; base-uri 'none'; form-action 'none'; frame-ancestors 'self'")

    def check_origin(self,write=False):
        expected=f'127.0.0.1:{self.server.server_port}'
        if self.headers.get('Host')!=expected:raise UserError('仅允许本机工作台访问。',403)
        origin=self.headers.get('Origin')
        if origin and origin!='http://'+expected:raise UserError('请求来源不受信任。',403)
        if self.headers.get('Sec-Fetch-Site')=='cross-site':raise UserError('禁止跨站访问本地文件。',403)
        if write and not secrets.compare_digest(self.headers.get('X-YingXu-Token',''),self.app.token):raise UserError('会话已更新，请刷新工作台后重试。',403)

    def body(self):
        if self.headers.get('Transfer-Encoding'):raise UserError('不支持此请求传输格式。')
        try:size=int(self.headers.get('Content-Length','0'))
        except ValueError:raise UserError('请求长度不正确。')
        if not 0<=size<=4*1024*1024:raise UserError('请求过大。',413)
        if size and not self.headers.get('Content-Type','').startswith('application/json'):raise UserError('仅接受 JSON 请求。',415)
        try:
            data=json.loads(self.rfile.read(size).decode('utf-8')) if size else {}
            if not isinstance(data,dict):raise ValueError()
            return data
        except (ValueError,UnicodeError):raise UserError('请求格式不正确。')

    def json(self,data,status=200,extra=None):
        raw=json.dumps(data,ensure_ascii=False,separators=(',',':')).encode('utf-8')
        self.send_response(status);self.headers_common('application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(raw)))
        for k,v in (extra or {}).items():self.send_header(k,v)
        self.end_headers()
        if self.command!='HEAD':self.wfile.write(raw)

    def file(self,path,media=False,immutable=False,opened=None):
        path=Path(path);length=os.fstat(opened.fileno()).st_size if opened is not None else path.stat().st_size
        try:start,end,partial=parse_range(self.headers.get('Range') if media else None,length)
        except UserError as e:
            self.json({'error':str(e)},416,{'Content-Range':f'bytes */{length}'});return
        mime=mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
        if path.suffix=='.js':mime='application/javascript'
        if path.suffix in ('.md','.txt','.srt','.vtt','.json','.yaml','.yml','.csv'):mime='text/plain; charset=utf-8'
        self.send_response(206 if partial else 200);self.headers_common(mime)
        self.send_header('Content-Length',str(max(0,end-start+1)))
        self.send_header('Cache-Control','private, max-age=86400' if immutable else 'no-cache')
        if media:
            self.send_header('Accept-Ranges','bytes')
            if partial:self.send_header('Content-Range',f'bytes {start}-{end}/{length}')
        if mime=='application/octet-stream':self.send_header('Content-Disposition','attachment')
        self.end_headers()
        if self.command=='HEAD':return
        with (nullcontext(opened) if opened is not None else path.open('rb')) as f:
            f.seek(start);remaining=end-start+1
            while remaining>0:
                chunk=f.read(min(128*1024,remaining))
                if not chunk:break
                self.wfile.write(chunk);remaining-=len(chunk)

    def handle_request(self):
        try:
            self.check_origin(self.command not in ('GET','HEAD'))
            parsed=urlsplit(self.path);path=parsed.path
            query={k:v[-1] for k,v in parse_qs(parsed.query).items()}
            if self.command in ('GET','HEAD'):
                if path=='/api/health':return self.json({'app':'yingxu','ok':True,'version':__version__,'instance_id':instance_id(self.app.store.data_root)})
                if path=='/api/bootstrap':return self.json(self.app.bootstrap())
                if path=='/api/settings':return self.json(self.app.settings.get())
                if path=='/api/project-library':return self.json(self.app.project_library.snapshot())
                if path=='/api/markdown-assets/link':
                    if set(query)-{'note','image'}:raise UserError('图片引用仅接受笔记与素材 ID。')
                    return self.json(self.app.markdown_assets.link(query.get('note',''),query.get('image','')))
                if path=='/api/markdown-assets/image':
                    if set(query)-{'note','path'}:raise UserError('笔记图片仅接受笔记 ID 与相对路径。')
                    with self.app.markdown_assets.open_image(query.get('note',''),query.get('path','')) as opened:
                        return self.file(opened.name,media=True,opened=opened)
                if path=='/api/resource-groups':
                    if set(query)-{'project'}:raise UserError('素材组列表仅接受项目参数。')
                    return self.json(self.app.resource_groups.list(query.get('project','')))
                group=re.fullmatch(r'/api/resource-groups/([a-f0-9]{32})',path)
                if group:
                    if query:raise UserError('素材组详情仅接受素材组 ID。')
                    return self.json(self.app.resource_groups.get(group[1]))
                if path=='/api/projects':return self.json({'projects':self.app.store.list_projects()})
                if path=='/api/search':
                    if set(query)-{'q','limit','offset'}:raise UserError('全局搜索仅接受关键词与分页参数。')
                    return self.json(self.app.search.search(query.get('q',''),query.get('limit',30),query.get('offset',0)))
                if path=='/api/items':return self.json(self.app.store.list_items(query.get('project',''),**{k:query[k] for k in ('category','q','status','kind','limit','offset','sort','folder') if k in query}))
                if path=='/api/folders':return self.json(self.app.organize.folders(query.get('project',''),query.get('category','')))
                if path=='/api/trash':return self.json(self.app.trash(query.get('project',''),query.get('limit',48),query.get('offset',0),query.get('q','')))
                if path=='/api/skills':return self.json(self.app.skills.list(query.get('q',''),query.get('project','')))
                if path=='/api/context':return self.json(self.app.context.get(query.get('project','')))
                external=re.fullmatch(r'/api/(external|external-media)/([a-f0-9]{32})',path)
                if external:
                    if query:raise UserError('外部预览仅接受已登记的文件 ID。')
                    if external[1]=='external':return self.json(self.app.external.detail(external[2]))
                    with self.app.external.open_media(external[2]) as opened:
                        return self.file(opened.name,media=True,opened=opened)
                native=re.fullmatch(r'/api/native-file/([a-f0-9]{32})',path)
                if native:return self.json({'path':str(self.app.store.resolve_item_path(self.app.store.get_item(native[1])))})
                match=re.fullmatch(r'/api/(items|content|media|thumbnail|jobs|skills)/([a-f0-9]{32})',path)
                if match:
                    resource,iid=match.groups()
                    if resource=='items':return self.json(self.app.store.get_item(iid,True))
                    if resource=='content':return self.json(self.app.store.read_content(iid))
                    if resource=='jobs':return self.json(self.app.jobs.get(iid))
                    if resource=='skills':return self.json(self.app.skills.get(iid))
                    if resource=='media':return self.file(self.app.store.resolve_item_path(self.app.store.get_item(iid)),media=True)
                    if resource=='thumbnail':
                        target=self.app.thumbnails.request(iid)
                        return self.file(target,immutable=False) if target else self.json({'pending':True},202,{'Retry-After':'1'})
                if path.startswith('/api/'):raise UserError('接口不存在。',404)
                relative=path.lstrip('/') or 'index.html'
                static=(ROOT/'frontend'/relative).resolve()
                if not static.is_relative_to(ROOT/'frontend') or not static.is_file() or static.suffix not in ('.html','.js','.css','.svg','.ico','.png','.woff2'):
                    raise UserError('页面文件不存在。',404)
                return self.file(static)
            if self.command=='POST' and path=='/api/upload':return self.json(self.app.receive_upload(self,query),201)
            data=self.body()
            group=re.fullmatch(r'/api/resource-groups/([a-f0-9]{32})(/members|/transfer)?',path)
            if group:
                if group[2]=='/transfer':
                    if self.command=='POST':return self.json(self.app.resource_groups.transfer(group[1],data))
                    raise UserError('接口或请求方式不存在。',404)
                if group[2]:
                    if self.command=='POST':return self.json(self.app.resource_groups.add(group[1],data))
                    if self.command=='DELETE':return self.json(self.app.resource_groups.remove(group[1],data))
                else:
                    if self.command=='PATCH':return self.json(self.app.resource_groups.rename(group[1],data))
                    if self.command=='DELETE':return self.json(self.app.resource_groups.dissolve(group[1],data))
                raise UserError('接口或请求方式不存在。',404)
            if self.command=='PATCH' and path=='/api/settings':return self.json(self.app.settings.update(data))
            library_folder=re.fullmatch(r'/api/project-folders/([a-f0-9]{32})',path)
            if library_folder:
                if self.command=='PATCH':return self.json(self.app.project_library.update_folder(library_folder[1],data))
                if self.command=='DELETE':return self.json(self.app.project_library.delete_folder(library_folder[1]))
            library_project=re.fullmatch(r'/api/project-library/([a-f0-9]{32})(/visit)?',path)
            if library_project:
                if self.command=='POST' and library_project[2]:return self.json(self.app.project_library.visit(library_project[1]))
                if self.command=='PATCH' and not library_project[2]:return self.json(self.app.project_library.assign_project(library_project[1],data))
            if self.command=='POST':
                if path=='/api/resource-groups':return self.json(self.app.resource_groups.create(data),201)
                if path=='/api/project-folders':return self.json(self.app.project_library.create_folder(data),201)
                if path=='/api/external-open':return self.json(self.app.external.open(data))
                if path=='/api/projects':
                    project=self.app.store.create_project(data.get('name',''),data.get('description',''));self.app.context.request(project['id']);return self.json(project,201)
                if path=='/api/items/batch-properties':
                    result=self.app.store.batch_properties(data)
                    self.app.context.request(data['project_id']);return self.json(result)
                if path=='/api/items':
                    item=self.app.store.create_item(data);self.app.context.request(item['project_id']);return self.json(item,201)
                if path=='/api/import':return self.json(self.app.jobs.submit(data.get('project_id'),data.get('category','references'),data.get('paths',[]),data.get('folder_id','')),202)
                if path=='/api/rescan':return self.json(self.app.jobs.submit(data.get('project_id')),202)
                if path=='/api/pick':return self.json(self.app.pick(data.get('kind')))
                if path=='/api/open':return self.json(self.app.open_file(data))
                if path=='/api/open-folder':return self.json(self.app.open_folder(data))
                if path=='/api/rename':
                    result=self.app.store.rename_file(data.get('id'),data.get('name',''))
                    for project in self.app.store.list_projects():self.app.context.request(project['id'])
                    return self.json(result)
                if path=='/api/relations':
                    result=self.app.store.add_relation(data.get('source_id'),data.get('target_id'),data.get('relation','关联'));self.app.context.request(self.app.store.get_item(data.get('source_id'))['project_id']);return self.json(result,201)
                if path=='/api/demo':
                    from yingxu.demo import create_demo
                    with self.app.demo_lock:project=create_demo(self.app.store)
                    self.app.context.request(project['id']);return self.json(project,201)
                if path=='/api/skills':return self.json(self.app.skills.create(data),201)
                if path=='/api/skills/refresh':return self.json(self.app.skills.refresh())
                if path=='/api/skills/bind':
                    result=self.app.skills.bind(data.get('project_id'),data.get('skill_id'),bool(data.get('bound')));self.app.context.request(data.get('project_id'));return self.json(result)
                if path=='/api/context/refresh':return self.json(self.app.context.export(data.get('project_id')))
                if path=='/api/backup':return self.json({'path':str(self.app.store.backup_database())})
                if path=='/api/trash/delete-preview':return self.json(self.app.trash_deletion.preview(data))
                if path=='/api/trash/delete':
                    result=self.app.trash_deletion.delete(data);self.app.changed();return self.json(result)
                if path=='/api/folders':
                    result=self.app.organize.create_folder(data.get('project_id'),data.get('category'),data.get('name',''),data.get('parent_id'))
                    self.app.changed(result['project_id']);return self.json(result,201)
                if path=='/api/move':
                    result=self.app.organize.move_items(data.get('ids'),data.get('category'),data.get('folder_id'))
                    self.app.changed();return self.json(result)
                if path=='/api/trash/items':
                    result=self.app.organize.delete_items(data.get('ids'));self.app.changed(result['project_id']);return self.json(result)
                restoring=re.fullmatch(r'/api/trash/([a-f0-9]{32})/restore',path)
                if restoring:
                    result=self.app.skills.restore(restoring[1]) if data.get('kind')=='skill' else self.app.organize.restore(restoring[1])
                    self.app.changed();return self.json(result)
            organization=re.fullmatch(r'/api/(folders|projects)/([a-f0-9]{32})',path)
            if organization:
                resource,oid=organization.groups()
                if resource=='folders':
                    if self.command=='PATCH':result=self.app.organize.rename_folder(oid,data.get('name',''))
                    elif self.command=='DELETE':result=self.app.organize.delete_folder(oid)
                    else:raise UserError('接口或请求方式不存在。',404)
                else:
                    if self.command=='PATCH':result=self.app.organize.update_project(oid,data)
                    elif self.command=='DELETE':
                        project=self.app.store.get_project(oid)
                        result=self.app.organize.delete_project(oid)
                        self.app.context.archive(project)
                    else:raise UserError('接口或请求方式不存在。',404)
                self.app.changed();return self.json(result)
            match=re.fullmatch(r'/api/(items|content|relations|skills)/([a-f0-9]{32})',path)
            if match:
                resource,iid=match.groups()
                if resource=='skills' and self.command=='PUT':
                    result=self.app.skills.save(iid,data)
                    for project in self.app.store.list_projects():self.app.context.request(project['id'])
                    return self.json(result)
                if resource=='skills' and self.command=='DELETE':
                    result=self.app.skills.remove(iid);self.app.changed();return self.json(result)
                if resource=='relations' and self.command=='DELETE':
                    with self.app.store.connection() as db:row=db.execute('SELECT i.project_id FROM relations r JOIN items i ON i.id=r.source_id WHERE r.id=?',(iid,)).fetchone()
                    result=self.app.store.remove_relation(iid)
                    if row:self.app.context.request(row[0])
                    return self.json(result)
                item=self.app.store.get_item(iid)
                if resource=='items' and self.command=='PATCH':result=self.app.store.update_item(iid,data)
                elif resource=='items' and self.command=='DELETE':result=self.app.organize.delete_items([iid])
                elif resource=='content' and self.command=='PUT':result=self.app.store.save_content(iid,data)
                else:raise UserError('接口或请求方式不存在。',404)
                if resource=='content':
                    with self.app.store.connection() as db:
                        project_ids=[r[0] for r in db.execute('SELECT DISTINCT project_id FROM items WHERE path=? AND removed=0',(item['path'],))]
                    for pid in project_ids:self.app.context.request(pid)
                else:self.app.context.request(item['project_id'])
                return self.json(result)
            raise UserError('接口或请求方式不存在。',404)
        except UserError as e:
            if self.command not in ('GET','HEAD'):self.close_connection=True
            self.json({'error':str(e)},e.status)
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError,socket.timeout):pass
        except (ValueError,TypeError,KeyError) as e:
            self.close_connection=True;self.json({'error':'请求字段不正确，请检查输入。'},400)
        except OSError:
            traceback.print_exc();self.close_connection=True;self.json({'error':'文件操作失败，可能被占用或已移动；你的原文件和草稿会保留。'},409)
        except Exception:
            traceback.print_exc();self.close_connection=True;self.json({'error':'工作台遇到错误，请查看本地服务日志。'},500)

    do_GET=handle_request
    do_HEAD=handle_request
    do_POST=handle_request
    do_PUT=handle_request
    do_PATCH=handle_request
    do_DELETE=handle_request


def main():
    parser=argparse.ArgumentParser(description='映序 · 本地视频创作工作台')
    parser.add_argument('--port',type=int,default=8791)
    parser.add_argument('--data',type=Path,default=default_data_root())
    parser.add_argument('--projects-root',type=Path,default=default_project_root())
    args=parser.parse_args()
    if not 1024<=args.port<=65535:raise SystemExit('端口范围应为1024至65535。')
    app=Application(args.data,args.projects_root)
    server=Server(('127.0.0.1',args.port),app)
    print(f'映序 {__version__} · http://127.0.0.1:{args.port}',flush=True)
    try:server.serve_forever(poll_interval=.3)
    finally:
        server.server_close();app.context.close()


if __name__=='__main__':main()
