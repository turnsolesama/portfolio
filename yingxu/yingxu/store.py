"""Local project catalogue. Files remain ordinary files; SQLite stores organisation."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import sqlite3
import threading
import uuid

CATEGORIES = {
    'scripts': ('剧本与文档', '00_Brief/剧本与文档'),
    'shots': ('分镜', '00_Brief/分镜'),
    'characters': ('角色', '20_Assets/角色'),
    'scenes': ('场景', '20_Assets/场景'),
    'props': ('道具', '20_Assets/道具'),
    'previs': ('白模预演', '40_Runs/白模预演'),
    'generated': ('生成素材', '40_Runs/生成素材'),
    'delivery': ('成片交付', '90_Delivery'),
    'references': ('参考资料', '10_References'),
}
STATUSES = ['待开始', '进行中', '待审核', '已完成']
KINDS = {
    **dict.fromkeys(['.md', '.markdown'], 'markdown'),
    **dict.fromkeys(['.txt', '.json', '.csv', '.srt', '.vtt', '.yaml', '.yml'], 'text'),
    **dict.fromkeys(['.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.tif', '.tiff', '.avif'], 'image'),
    **dict.fromkeys(['.mp4', '.mov', '.webm', '.mkv', '.avi', '.m4v'], 'video'),
    **dict.fromkeys(['.wav', '.mp3', '.ogg', '.flac', '.m4a', '.aac'], 'audio'),
    **dict.fromkeys(['.blend', '.fbx', '.obj', '.glb', '.gltf', '.stl'], 'model'),
    '.docx': 'docx', '.pdf': 'pdf', '.doc': 'file', '.pptx': 'file', '.xlsx': 'file', '.rtf': 'file',
}
SAFE_EXTENSIONS = frozenset(KINDS)
TEXT_LIMIT = 2 * 1024 * 1024
_NO_TARGET_FOLDER = object()


class UserError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def uid():
    return uuid.uuid4().hex


def json_text(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def tokenize(value):
    # Each CJK character becomes an FTS token, so Chinese phrase queries work
    # without a large language model, dictionary download, or ASCII-only search.
    return re.sub(r'([\u3400-\u9fff\uf900-\ufaff])', r' \1 ', str(value)).lower()


def safe_name(value):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(value)).strip(' .')[:100]
    if not name or name.upper().split('.')[0] in {'CON', 'PRN', 'AUX', 'NUL', *['COM'+str(i) for i in range(10)], *['LPT'+str(i) for i in range(10)]}:
        raise UserError('请输入有效的名称。')
    return name


def has_link(path):
    p = Path(path)
    try:
        return p.is_symlink() or bool(getattr(p.lstat(), 'st_file_attributes', 0) & 0x400)
    except OSError:
        return True


def clean_path(path):
    value = os.path.abspath(os.path.expanduser(str(path).strip().strip('"')))
    if not os.path.isabs(str(path).strip().strip('"')) or value.startswith('\\\\'):
        raise UserError('请选择本机磁盘上的绝对路径。')
    p = Path(value)
    if not p.exists():
        raise UserError('文件或文件夹已经不存在。', 404)
    for parent in (p, *p.parents):
        if has_link(parent):
            raise UserError('为避免重复扫描或误改文件，请选择实际文件夹，不选择联接或符号链接。')
    return p.resolve()


def decode_text(raw):
    for encoding in (['utf-16'] if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else ['utf-8-sig', 'gb18030']):
        try:
            return raw.decode(encoding), encoding
        except UnicodeError:
            pass
    raise UserError('文本编码无法识别，请用系统编辑器另存为 UTF-8。')


class Store:
    def __init__(self, data_root, project_root):
        self.data_root = Path(data_root).resolve()
        self.project_root = Path(project_root).resolve()
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.project_root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_root / 'yingxu.sqlite3'
        self.lock = threading.RLock()
        self._init()

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.db_path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA busy_timeout=15000')
        try:
            with db:
                yield db
        finally:
            db.close()

    def _init(self):
        with self.connection() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
            CREATE TABLE IF NOT EXISTS projects(
              id TEXT PRIMARY KEY,name TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',
              color TEXT DEFAULT '#b6c7ae',root TEXT UNIQUE NOT NULL,created TEXT,updated TEXT);
            CREATE TABLE IF NOT EXISTS sources(
              id TEXT PRIMARY KEY,project_id TEXT REFERENCES projects(id),path TEXT NOT NULL,
              category TEXT NOT NULL,is_file INTEGER NOT NULL,UNIQUE(project_id,path));
            CREATE TABLE IF NOT EXISTS items(
              id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES projects(id),source_id TEXT REFERENCES sources(id),
              name TEXT NOT NULL,category TEXT NOT NULL,kind TEXT NOT NULL,ext TEXT NOT NULL,
              path TEXT NOT NULL,size INTEGER DEFAULT 0,mtime INTEGER DEFAULT 0,status TEXT DEFAULT '待开始',
              tags TEXT DEFAULT '[]',notes TEXT DEFAULT '',metadata TEXT DEFAULT '{}',sort_order INTEGER DEFAULT 0,
              created TEXT,updated TEXT,search_content TEXT DEFAULT '',removed INTEGER DEFAULT 0,
              UNIQUE(project_id,path));
            CREATE INDEX IF NOT EXISTS items_category_order ON items(project_id,removed,category,updated DESC,id);
            CREATE INDEX IF NOT EXISTS items_project_order ON items(project_id,removed,updated DESC,id);
            CREATE INDEX IF NOT EXISTS items_status ON items(project_id,removed,status,category);
            CREATE INDEX IF NOT EXISTS items_kind ON items(project_id,removed,kind);
            CREATE INDEX IF NOT EXISTS items_sort ON items(project_id,removed,sort_order,id);
            CREATE INDEX IF NOT EXISTS items_name ON items(project_id,removed,name,id);
            CREATE INDEX IF NOT EXISTS items_name_nocase ON items(project_id,removed,name COLLATE NOCASE,id);
            CREATE INDEX IF NOT EXISTS items_order_name ON items(project_id,removed,sort_order,name,id);
            CREATE INDEX IF NOT EXISTS items_category_name ON items(project_id,removed,category,name COLLATE NOCASE,id);
            CREATE INDEX IF NOT EXISTS items_category_sort ON items(project_id,removed,category,sort_order,name,id);
            CREATE VIRTUAL TABLE IF NOT EXISTS item_search USING fts5(text,tokenize='unicode61 remove_diacritics 2');
            CREATE TABLE IF NOT EXISTS relations(
              id TEXT PRIMARY KEY,source_id TEXT REFERENCES items(id),target_id TEXT REFERENCES items(id),
              relation TEXT NOT NULL,UNIQUE(source_id,target_id,relation));
            CREATE INDEX IF NOT EXISTS relations_target ON relations(target_id);
            CREATE TABLE IF NOT EXISTS versions(
              id TEXT PRIMARY KEY,item_id TEXT REFERENCES items(id),created TEXT,size INTEGER,
              path TEXT NOT NULL,sha256 TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS versions_item ON versions(item_id,created DESC);
            ''')
            # Additive migrations preserve earlier catalogues and soft removals.
            for table, columns in {
                'projects': [('removed', 'INTEGER NOT NULL DEFAULT 0'), ('removed_batch', 'TEXT')],
                'items': [('folder_id', 'TEXT'), ('removed_batch', 'TEXT')],
            }.items():
                existing={row[1] for row in db.execute('PRAGMA table_info('+table+')')}
                for column, declaration in columns:
                    if column not in existing:db.execute('ALTER TABLE '+table+' ADD COLUMN '+column+' '+declaration)
            db.executescript('''
            CREATE TABLE IF NOT EXISTS folders(
              id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES projects(id),category TEXT NOT NULL,
              parent_id TEXT REFERENCES folders(id),name TEXT NOT NULL,relative_path TEXT NOT NULL,
              created TEXT NOT NULL,updated TEXT NOT NULL,removed INTEGER NOT NULL DEFAULT 0,removed_batch TEXT,
              UNIQUE(project_id,relative_path COLLATE NOCASE));
            CREATE INDEX IF NOT EXISTS folders_tree ON folders(project_id,removed,category,parent_id,name);
            CREATE INDEX IF NOT EXISTS items_folder_updated ON items(project_id,removed,folder_id,updated DESC,id);
            CREATE INDEX IF NOT EXISTS items_folder_name ON items(project_id,removed,folder_id,name COLLATE NOCASE,id);
            CREATE INDEX IF NOT EXISTS items_folder_order ON items(project_id,removed,folder_id,sort_order,name,id);
            CREATE INDEX IF NOT EXISTS items_path ON items(path);
            CREATE TABLE IF NOT EXISTS trash_batches(
              id TEXT PRIMARY KEY,kind TEXT NOT NULL,target_id TEXT NOT NULL,project_id TEXT NOT NULL,
              name TEXT NOT NULL,created TEXT NOT NULL,restored INTEGER NOT NULL DEFAULT 0);
            CREATE INDEX IF NOT EXISTS trash_project ON trash_batches(restored,project_id,created DESC);
            CREATE TABLE IF NOT EXISTS trash_members(
              batch_id TEXT NOT NULL REFERENCES trash_batches(id),entity_type TEXT NOT NULL,entity_id TEXT NOT NULL,
              PRIMARY KEY(batch_id,entity_type,entity_id));
            INSERT OR IGNORE INTO trash_batches(id,kind,target_id,project_id,name,created)
              SELECT id,'items',id,project_id,name,coalesce(updated,created,'') FROM items WHERE removed=1 AND removed_batch IS NULL;
            INSERT OR IGNORE INTO trash_members(batch_id,entity_type,entity_id)
              SELECT id,'item',id FROM items WHERE removed=1 AND removed_batch IS NULL;
            UPDATE items SET removed_batch=id WHERE removed=1 AND removed_batch IS NULL;
            ''')
            if 'purged' not in {row[1] for row in db.execute('PRAGMA table_info(trash_batches)')}:
                db.execute('ALTER TABLE trash_batches ADD COLUMN purged INTEGER NOT NULL DEFAULT 0')
            if 'recycle_started' not in {row[1] for row in db.execute('PRAGMA table_info(trash_batches)')}:
                db.execute('ALTER TABLE trash_batches ADD COLUMN recycle_started INTEGER NOT NULL DEFAULT 0')

    def _project(self, db, pid):
        row = db.execute('SELECT * FROM projects WHERE id=? AND removed=0', (pid,)).fetchone()
        if row is None:
            raise UserError('项目不存在。', 404)
        return dict(row)

    def get_project(self, pid):
        with self.connection() as db:
            return self._project(db, pid)

    def list_projects(self):
        with self.connection() as db:
            rows = [dict(r) for r in db.execute('SELECT * FROM projects WHERE removed=0 ORDER BY created DESC')]
            for row in rows:
                counts = db.execute("SELECT count(*) AS total,sum(category='shots') AS shots,sum(category='shots' AND status='已完成') AS completed,sum(kind IN ('markdown','text','docx')) AS documents FROM items WHERE project_id=? AND removed=0", (row['id'],)).fetchone()
                row['counts'] = {k: int(v or 0) for k, v in dict(counts).items()}
        return rows

    def create_project(self, name, description=''):
        name = safe_name(name)
        if len(str(description)) > 4000:
            raise UserError('项目简介最多4000字。')
        pid = uid()
        root = self.project_root / (name + '_' + pid[:6])
        root.mkdir()
        for folder in [v[1] for v in CATEGORIES.values()] + ['30_Workflows']:
            (root / folder).mkdir(parents=True, exist_ok=True)
        (root / 'README_项目.md').write_text(f'# {name}\n\n{description}\n\n此项目由映序管理，文件可独立使用。\n', encoding='utf-8')
        with self.lock, self.connection() as db:
            db.execute('INSERT INTO projects(id,name,description,root,created,updated) VALUES(?,?,?,?,?,?)', (pid,name,str(description),str(root),now(),now()))
            db.execute('INSERT INTO sources VALUES(?,?,?,?,?)', (uid(),pid,str(root),'references',0))
        return self.get_project(pid)

    @staticmethod
    def item_dict(row,brief=False):
        d = dict(row)
        for key, fallback in [('tags', []), ('metadata', {})]:
            try:
                d[key] = json.loads(d[key])
            except (ValueError, TypeError):
                d[key] = fallback
        d.pop('search_content', None)
        d.pop('rowid', None)
        if brief:
            d['notes']=d['notes'][:240]
            d['metadata']={k:v for k,v in d['metadata'].items() if k in ('shot_number','duration','shot_size','camera','version','width','height') and isinstance(v,(str,int,float,bool))}
        d['thumbnail_url'] = '/api/thumbnail/' + d['id'] if d['kind'] in ('image', 'video') else None
        d['media_url'] = '/api/media/' + d['id']
        return d

    def get_item(self, iid, detail=False):
        with self.connection() as db:
            row = db.execute('SELECT * FROM items WHERE id=? AND removed=0', (iid,)).fetchone()
            if row is None:
                raise UserError('条目不存在或已移出工作台。', 404)
            self._project(db,row['project_id'])
            item = self.item_dict(row)
            folder=db.execute('SELECT relative_path FROM folders WHERE id=?',(row['folder_id'],)).fetchone() if row['folder_id'] else None
            item['folder_path']=folder[0][len(CATEGORIES[row['category']][1])+1:] if folder else ''
            if detail:
                item['relations'] = []
                for relation in db.execute('SELECT * FROM relations WHERE source_id=? OR target_id=?', (iid,iid)):
                    target = relation['target_id'] if relation['source_id'] == iid else relation['source_id']
                    related = db.execute('SELECT * FROM items WHERE id=? AND removed=0', (target,)).fetchone()
                    if related:
                        item['relations'].append({**dict(relation),'item':self.item_dict(related)})
                item['versions'] = [dict(v) for v in db.execute('SELECT id,created,size FROM versions WHERE item_id=? ORDER BY created DESC LIMIT 100', (iid,))]
                item['content_preview'] = row['search_content'][:500]
            return item

    def resolve_item_path(self, item):
        # Re-evaluate at every file access: a previously indexed path may now be a link.
        p = clean_path(item['path'])
        if p==self.data_root or p.is_relative_to(self.data_root):
            raise UserError('应用备份与缓存不能作为可编辑素材访问。',403)
        with self.connection() as db:
            source = db.execute('SELECT * FROM sources WHERE id=? AND project_id=?', (item['source_id'],item['project_id'])).fetchone()
        if source is None:
            raise UserError('条目没有有效的本地来源。',403)
        root = clean_path(source['path'])
        if source['is_file']:
            valid = p == root
        else:
            valid = p.is_relative_to(root)
        if not valid or not p.is_file() or p.suffix.lower() not in SAFE_EXTENSIONS:
            raise UserError('文件不在授权的素材来源内。',403)
        return p

    def _search_row(self, db, iid):
        identity=db.execute('SELECT rowid,removed FROM items WHERE id=?',(iid,)).fetchone()
        db.execute('DELETE FROM item_search WHERE rowid=?', (identity['rowid'],))
        if identity['removed']:return
        r = db.execute('SELECT name,notes,tags,metadata,search_content FROM items WHERE id=?', (iid,)).fetchone()
        text = '\n'.join([r['name'],r['notes'],r['tags'],r['metadata'],r['search_content']])
        db.execute('INSERT INTO item_search(rowid,text) VALUES(?,?)',(identity['rowid'],tokenize(text)))

    def _parse_query(self, q):
        try:
            parts = shlex.split(q)
        except ValueError:
            raise UserError('搜索引号不完整。示例：tag:夜景 type:video 雨夜')
        filters, words = {}, []
        keys={'tag':'tag','标签':'tag','type':'kind','类型':'kind','status':'status','状态':'status','category':'category','分类':'category'}
        for part in parts:
            head, sep, rest = part.partition(':')
            if sep and head in keys and rest:
                filters.setdefault(keys[head],[]).append(rest)
            else:
                words.append(part)
        return filters, words

    def list_items(self, pid, category='', q='', status='', kind='', limit=60, offset=0, sort='updated',folder=''):
        import time
        start = time.perf_counter()
        limit = max(1,min(60,int(limit)))
        offset = max(0,min(10_000_000,int(offset)))
        if len(q)>1000:
            raise UserError('搜索内容过长。')
        clauses=['i.project_id=?','i.removed=0']; args=[pid]
        if folder=='root':clauses.append('i.folder_id IS NULL')
        elif folder:
            with self.connection() as db:
                target=db.execute('SELECT * FROM folders WHERE id=? AND project_id=? AND removed=0',(folder,pid)).fetchone()
            if target is None:raise UserError('文件夹不存在或已移入回收站。',404)
            if category and category!='all' and category!=target['category']:raise UserError('文件夹不属于这个分类。')
            clauses.append('i.folder_id=?');args.append(folder)
        filters, words = self._parse_query(q)
        for k,v in [('category',category),('status',status),('kind',kind)]:
            if v and v != 'all': filters.setdefault(k,[]).append(v)
        labels={v[0]:k for k,v in CATEGORIES.items()}
        kind_labels={'图片':'image','视频':'video','音频':'audio','文档':'docx','模型':'model','文本':'text','markdown':'markdown'}
        for k, values in filters.items():
            for value in values:
                if k=='tag':
                    clauses.append('EXISTS(SELECT 1 FROM json_each(i.tags) WHERE value=?)');args.append(value)
                else:
                    if k=='category': value=labels.get(value,value)
                    if k=='kind': value=kind_labels.get(value,value)
                    clauses.append(f'i.{k}=?');args.append(value)
        if words:
            match=[]
            for word in words:
                toks = re.findall(r'\w+',tokenize(word),re.UNICODE)
                if toks: match.append('"'+' '.join(toks)+'"'+('' if re.search(r'[\u3400-\u9fff]',word) else '*'))
            if match:
                clauses.append('i.rowid IN (SELECT rowid FROM item_search WHERE item_search MATCH ?)')
                args.append(' AND '.join(match))
        ordering={'updated':'i.updated DESC,i.id','name':'i.name COLLATE NOCASE,i.id','order':'i.sort_order,i.name,i.id'}.get(sort,'i.updated DESC,i.id')
        sql=' FROM items i WHERE '+' AND '.join(clauses)
        with self.connection() as db:
            self._project(db,pid)
            total=db.execute('SELECT count(*)'+sql,args).fetchone()[0]
            columns='i.id,i.project_id,i.source_id,i.name,i.category,i.kind,i.ext,i.path,i.size,i.mtime,i.status,i.tags,substr(i.notes,1,240) AS notes,i.sort_order,i.created,i.updated,i.removed,i.folder_id'
            columns+=",coalesce((SELECT substr(f.relative_path,length(CASE i.category "+' '.join("WHEN '"+k+"' THEN '"+v[1]+"'" for k,v in CATEGORIES.items())+" END)+2) FROM folders f WHERE f.id=i.folder_id),'') AS folder_path"
            # Never pull document bodies or huge generation workflows into a list page.
            meta_keys=('shot_number','duration','shot_size','camera','version','width','height')
            columns+=',json_object('+','.join("'"+k+"',json_extract(i.metadata,'$."+k+"')" for k in meta_keys)+') AS metadata'
            rows=db.execute('SELECT '+columns+sql+' ORDER BY '+ordering+' LIMIT ? OFFSET ?',[*args,limit,offset]).fetchall()
            counts={r[0]:r[1] for r in db.execute('SELECT category,count(*) FROM items WHERE project_id=? AND removed=0 GROUP BY category',(pid,))}
        return {'items':[self.item_dict(r,brief=True) for r in rows],'total':total,'limit':limit,'offset':offset,
                'categories':[{'key':k,'label':v[0],'count':counts.get(k,0)} for k,v in CATEGORIES.items()],
                'elapsed_ms':round((time.perf_counter()-start)*1000,2)}

    def register_source(self,pid,path,category):
        if category not in CATEGORIES: raise UserError('未知分类。')
        p=clean_path(path)
        if p.is_file() and p.suffix.lower() not in SAFE_EXTENSIONS: raise UserError('此文件类型暂不支持导入。')
        if p == Path(p.anchor): raise UserError('请选择具体素材文件夹，不能扫描整个磁盘。')
        if p == self.data_root or p.is_relative_to(self.data_root): raise UserError('不能把应用数据库或缓存作为素材导入。')
        with self.lock,self.connection() as db:
            self._project(db,pid)
            db.execute('INSERT OR IGNORE INTO sources VALUES(?,?,?,?,?)',(uid(),pid,str(p),category,int(p.is_file())))
            return dict(db.execute('SELECT * FROM sources WHERE project_id=? AND path=?',(pid,str(p))).fetchone())

    def sources(self,pid):
        with self.connection() as db:
            self._project(db,pid)
            return [dict(r) for r in db.execute('SELECT * FROM sources WHERE project_id=?',(pid,))]

    def inspect_file(self,path):
        p=Path(path); stat=p.stat(); kind=KINDS[p.suffix.lower()]
        content=''; meta={}
        if kind in ('markdown','text') and stat.st_size<=TEXT_LIMIT:
            try: content=decode_text(p.read_bytes())[0]
            except (UserError,OSError): pass
        elif kind=='docx' and stat.st_size<=32*1024*1024:
            try:
                from .docx_io import read_docx
                content=read_docx(p)['content'][:TEXT_LIMIT]
            except (ValueError,OSError,UserError): pass
        elif kind=='image' and stat.st_size<=100*1024*1024:
            try:
                from PIL import Image
                with Image.open(p) as im:
                    meta.update(width=im.width,height=im.height)
                    for key in ('parameters','prompt','workflow'):
                        if key in im.info:
                            val=str(im.info[key])[:32768]
                            meta['source_'+key]=val
            except Exception: pass
        return stat,kind,content,meta

    def index_files(self,source,paths,restore_removed=False,target_folder_id=_NO_TARGET_FOLDER,target_category=None):
        # Read/parse files outside the write transaction; commit a bounded batch.
        records=[]; skipped=0;added=0;eligible_paths=[];indexed_ids=set()
        assign_target=target_folder_id is not _NO_TARGET_FOLDER
        if assign_target:
            target_folder_id=None if target_folder_id in (None,'','root') else target_folder_id
            target_category=target_category or source['category']
            if target_category not in CATEGORIES:raise UserError('目标分类不存在。')
        source_root=clean_path(source['path'])
        project=self.get_project(source['project_id'])
        with self.connection() as db:
            folder_rows=[dict(r) for r in db.execute('SELECT * FROM folders WHERE project_id=?',(source['project_id'],))]
        project_root=Path(project['root'])
        def folder_maps(rows):
            return ({os.path.normcase(str(project_root/f['relative_path'])):f for f in rows},
                    {f['id'] for f in rows if f['removed']})
        folder_by_path,removed_folder_ids=folder_maps(folder_rows)
        def locate_folder(path,mapping):
            nearest=None
            if not path.is_relative_to(project_root):return None,False
            for parent in path.parents:
                if parent==project_root:break
                found=mapping.get(os.path.normcase(str(parent)))
                if found:
                    if found['removed']:return None,True
                    if nearest is None:nearest=found
            return nearest,False
        with self.connection() as db:
            for p in paths:
                try:
                    p=Path(p)
                    actual=p.resolve()
                    if os.path.normcase(str(actual))!=os.path.normcase(str(p.absolute())) or has_link(p):
                        skipped+=1;continue
                    if actual==self.data_root or actual.is_relative_to(self.data_root):
                        skipped+=1;continue
                    if (source['is_file'] and actual!=source_root) or (not source['is_file'] and not actual.is_relative_to(source_root)):
                        skipped+=1;continue
                    if locate_folder(actual,folder_by_path)[1]:
                        skipped+=1;continue
                    st=p.stat()
                    row=db.execute('SELECT id,size,mtime,removed,folder_id,removed_batch FROM items WHERE project_id=? AND path=?',(source['project_id'],str(p))).fetchone()
                    if row and row['removed_batch'] and not restore_removed and db.execute('SELECT 1 FROM trash_batches WHERE id=? AND purged=1',(row['removed_batch'],)).fetchone():
                        skipped+=1;continue
                    if row and row['folder_id'] in removed_folder_ids:
                        skipped+=1;continue
                    eligible_paths.append(str(p))
                    if row and ((row['removed'] and not restore_removed) or (not row['removed'] and row['size']==st.st_size and row['mtime']==st.st_mtime_ns)):
                        skipped+=1;continue
                    stat,kind,content,meta=self.inspect_file(p)
                    records.append((p,row,stat,kind,content,meta))
                except (OSError,ValueError):
                    skipped+=1
        project=self.get_project(source['project_id'])
        with self.lock,self.connection() as db:
            self._project(db,source['project_id'])
            folder_by_path,removed_folder_ids=folder_maps([dict(r) for r in db.execute('SELECT * FROM folders WHERE project_id=?',(source['project_id'],))])
            if assign_target and target_folder_id:
                destination=db.execute('SELECT category FROM folders WHERE id=? AND project_id=? AND removed=0',(target_folder_id,source['project_id'])).fetchone()
                if destination is None:raise UserError('导入目标文件夹已移入回收站，已停止本批导入。',409)
                if destination['category']!=target_category:raise UserError('导入目标分类已经改变。',409)
            for p,row,st,kind,content,meta in records:
                # Another writer may have indexed the newly created path meanwhile.
                row=db.execute('SELECT id,size,mtime,removed,folder_id,removed_batch FROM items WHERE project_id=? AND path=?',(source['project_id'],str(p))).fetchone()
                if row and row['removed_batch'] and not restore_removed and db.execute('SELECT 1 FROM trash_batches WHERE id=? AND purged=1',(row['removed_batch'],)).fetchone():
                    skipped+=1;continue
                located,removed_ancestor=locate_folder(p,folder_by_path)
                if removed_ancestor or (row and row['folder_id'] in removed_folder_ids):
                    skipped+=1;continue
                if row and row['removed'] and not restore_removed:
                    skipped+=1;continue
                if row:
                    iid=row['id']
                    old=json.loads(db.execute('SELECT metadata FROM items WHERE id=?',(iid,)).fetchone()[0])
                    # Extracted fields have their own namespace; user's prompt is independent.
                    old={k:v for k,v in old.items() if k not in ('width','height','source_prompt','source_workflow','source_parameters')}
                    old.update(meta);meta=old
                    db.execute('UPDATE items SET size=?,mtime=?,search_content=?,metadata=?,updated=?,removed=0,removed_batch=NULL WHERE id=?',(st.st_size,st.st_mtime_ns,content,json_text(meta),now(),iid))
                else:
                    iid=uid();category=source['category']
                    root=Path(project['root'])
                    if p.is_relative_to(root):
                        rel=p.relative_to(root).as_posix()
                        for key,(_,folder) in CATEGORIES.items():
                            if rel.startswith(folder+'/'): category=key;break
                    db.execute('INSERT INTO items(id,project_id,source_id,name,category,kind,ext,path,size,mtime,metadata,created,updated,search_content) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        (iid,source['project_id'],source['id'],p.stem,category,kind,p.suffix.lower(),str(p),st.st_size,st.st_mtime_ns,json_text(meta),now(),now(),content))
                    if located:
                        db.execute('UPDATE items SET folder_id=?,category=? WHERE id=?',(located['id'],located['category'],iid))
                self._search_row(db,iid)
                indexed_ids.add(iid)
                added+=1
            if assign_target:
                # Unchanged indexed files still need explicit target assignment.
                # This stays in the same transaction as validation/insertion and
                # never reparses their document bodies or generation metadata.
                for start in range(0,len(eligible_paths),200):
                    paths_batch=eligible_paths[start:start+200]
                    rows=db.execute('SELECT id,category,folder_id FROM items WHERE project_id=? AND removed=0 AND path IN ('+','.join('?' for _ in paths_batch)+')',[source['project_id'],*paths_batch]).fetchall()
                    for row in rows:
                        if row['folder_id'] in removed_folder_ids:continue
                        if row['category']==target_category and row['folder_id']==target_folder_id:continue
                        db.execute('UPDATE items SET category=?,folder_id=?,updated=? WHERE id=?',(target_category,target_folder_id,now(),row['id']))
                        if row['id'] not in indexed_ids:
                            added+=1;skipped=max(0,skipped-1)
        return added,skipped

    def create_item(self,data):
        pid=data.get('project_id');category=data.get('category','scripts')
        if category not in CATEGORIES: raise UserError('请选择有效分类。')
        project=self.get_project(pid)
        name=safe_name(data.get('name','未命名文档'))
        if name.lower().endswith('.md'):name=name[:-3]
        if data.get('status','待开始') not in STATUSES:raise UserError('状态不存在。')
        if not isinstance(data.get('tags',[]),list) or len(data.get('tags',[]))>50:raise UserError('标签格式不正确。')
        if not isinstance(data.get('metadata',{}),dict) or len(json_text(data.get('metadata',{})))>131072:raise UserError('属性格式不正确。')
        content=str(data.get('content',f'# {name}\n\n'))
        if len(content.encode('utf-8'))>TEXT_LIMIT:raise UserError('文档最多2 MiB。')
        root=clean_path(project['root'])
        from .organize import Organize
        folder=Organize(self).folder_path(pid,category,data.get('folder_id'))
        path=folder / (name+'.md')
        if path.exists():path=folder / (name+'_'+uid()[:6]+'.md')
        with path.open('x',encoding='utf-8',newline='') as f:f.write(content)
        source=next(s for s in self.sources(pid) if s['path']==str(root))
        self.index_files(source,[path])
        with self.connection() as db:iid=db.execute('SELECT id FROM items WHERE project_id=? AND path=?',(pid,str(path))).fetchone()[0]
        return self.update_item(iid,{k:v for k,v in data.items() if k in ('status','tags','metadata')})

    def update_item(self,iid,data):
        self.get_item(iid)
        updates={}
        for key in ('name','category','status','tags','notes','metadata','sort_order'):
            if key not in data:continue
            val=data[key]
            if key=='name':val=safe_name(val)
            elif key=='category' and val not in CATEGORIES:raise UserError('分类不存在。')
            elif key=='status' and val not in STATUSES:raise UserError('状态不存在。')
            elif key=='tags':
                if not isinstance(val,list) or len(val)>50:raise UserError('最多50个标签。')
                val=json_text(list(dict.fromkeys(str(x).strip()[:80] for x in val if str(x).strip())))
            elif key=='notes':
                val=str(val)
                if len(val)>20000:raise UserError('备注过长。')
            elif key=='metadata':
                if not isinstance(val,dict) or len(json_text(val))>131072:raise UserError('属性格式不正确或过长。')
                val=json_text(val)
            elif key=='sort_order':val=int(val)
            updates[key]=val
        if 'category' in updates:updates['folder_id']=None
        if updates:
            with self.lock,self.connection() as db:
                updates['updated']=now()
                db.execute('UPDATE items SET '+','.join(k+'=?' for k in updates)+' WHERE id=?',[*updates.values(),iid])
                self._search_row(db,iid)
        return self.get_item(iid,True)

    def batch_properties(self, data):
        """Append tags/update status atomically, without reading or changing files."""
        if not isinstance(data, dict) or set(data) - {'project_id', 'ids', 'tags_add', 'status'}:
            raise UserError('批量属性字段不正确。')
        pid, ids = data.get('project_id'), data.get('ids')
        valid_id = lambda value: isinstance(value, str) and re.fullmatch(r'[a-f0-9]{32}', value)
        if not valid_id(pid):
            raise UserError('请选择有效项目。')
        if (not isinstance(ids, list) or not 1 <= len(ids) <= 200
                or any(not valid_id(iid) for iid in ids) or len(set(ids)) != len(ids)):
            raise UserError('请选择 1 至 200 个不重复的有效素材。')
        if not {'tags_add', 'status'} & data.keys():
            raise UserError('请填写要追加的标签或选择制作状态。')
        if 'status' in data and (not isinstance(data['status'], str) or data['status'] not in STATUSES):
            raise UserError('状态不存在。')
        additions = None
        if 'tags_add' in data:
            values = data['tags_add']
            if not isinstance(values, list) or not 1 <= len(values) <= 50:
                raise UserError('请填写 1 至 50 个追加标签。')
            additions = []
            for value in values:
                if (not isinstance(value, str) or not 1 <= len(value.strip()) <= 80
                        or re.search(r'[\x00-\x1f\x7f]', value)):
                    raise UserError('每个标签需为 1 至 80 个字符，不能含控制字符。')
                value = value.strip()
                if value not in additions:
                    additions.append(value)
        with self.lock, self.connection() as db:
            # SQLite serializes independent Store instances too, so tag merging
            # always reads the latest committed labels before calculating a union.
            db.execute('BEGIN IMMEDIATE')
            self._project(db, pid)
            marks = ','.join('?' for _ in ids)
            rows = {row['id']: row for row in db.execute(
                f'SELECT i.* FROM items i WHERE i.id IN ({marks}) AND i.project_id=? AND i.removed=0 '
                'AND (i.folder_id IS NULL OR EXISTS(SELECT 1 FROM folders f '
                'WHERE f.id=i.folder_id AND f.project_id=i.project_id AND f.removed=0))', [*ids, pid])}
            if len(rows) != len(ids):
                raise UserError('部分素材已删除、移出项目或不在有效文件夹中，请刷新后重试。整批未修改。', 409)
            planned = []
            for iid in ids:
                row = rows[iid]
                try:
                    tags = json.loads(row['tags'])
                except (ValueError, TypeError):
                    raise UserError('素材原有标签数据异常，整批未修改。', 409) from None
                if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
                    raise UserError('素材原有标签数据异常，整批未修改。', 409)
                if additions is not None:
                    tags = list(dict.fromkeys([*tags, *additions]))
                    if len(tags) > 50:
                        raise UserError('追加后有素材超过 50 个标签，整批未修改。', 409)
                planned.append((iid, tags, data.get('status', row['status'])))
            updated = now()
            result = []
            for iid, tags, status in planned:
                changes = {'updated': updated}
                if additions is not None:
                    changes['tags'] = json_text(tags)
                if 'status' in data:
                    changes['status'] = status
                db.execute('UPDATE items SET ' + ','.join(key + '=?' for key in changes) + ' WHERE id=?', [*changes.values(), iid])
                self._search_row(db, iid)
                result.append({'id': iid, 'project_id': pid, 'tags': tags, 'status': status, 'updated': updated})
        return {'items': result}

    def remove_item(self,iid):
        from .organize import Organize
        return Organize(self).delete_items([iid])

    def add_relation(self,source_id,target_id,relation):
        a=self.get_item(source_id);b=self.get_item(target_id)
        if a['project_id']!=b['project_id'] or source_id==target_id:raise UserError('请关联同项目的其他条目。')
        relation=str(relation).strip()[:100]
        if not relation:raise UserError('请输入关联用途。')
        with self.lock,self.connection() as db:
            db.execute('INSERT OR IGNORE INTO relations VALUES(?,?,?,?)',(uid(),source_id,target_id,relation))
            return dict(db.execute('SELECT id FROM relations WHERE source_id=? AND target_id=? AND relation=?',(source_id,target_id,relation)).fetchone())

    def remove_relation(self,rid):
        with self.lock,self.connection() as db:db.execute('DELETE FROM relations WHERE id=?',(rid,))
        return {'ok':True}

    def read_content(self,iid):
        item=self.get_item(iid);path=self.resolve_item_path(item)
        fmt=item['kind']
        if fmt not in ('markdown','text','docx'):
            return {'format':'binary','content':'','etag':None,'editable':False}
        limit=32*1024*1024 if fmt=='docx' else TEXT_LIMIT
        if path.stat().st_size>limit:raise UserError('文件较大，请使用系统编辑器打开。')
        raw=path.read_bytes();etag=hashlib.sha256(raw).hexdigest()
        if fmt=='docx':
            from .docx_io import read_docx
            try:result=read_docx(path)
            except ValueError as e:raise UserError(str(e))
            return {'format':fmt,'etag':etag,'editable':any(p['editable'] for p in result['paragraphs']),**result}
        text,encoding=decode_text(raw)
        return {'format':fmt,'content':text,'etag':etag,'editable':True,'encoding':encoding,'notice':'保存会先备份原文件；外部修改会触发冲突保护。'}

    def save_content(self,iid,data):
        with self.lock:
            item=self.get_item(iid);path=self.resolve_item_path(item)
            if item['kind'] not in ('markdown','text','docx'):raise UserError('此类型不能在工作台编辑。')
            if path.stat().st_nlink>1:raise UserError('文件有多个硬链接。为保留原有路径关系，请复制一份到项目后再编辑。',409)
            limit=32*1024*1024 if item['kind']=='docx' else TEXT_LIMIT
            if path.stat().st_size>limit:raise UserError('文件较大，请使用系统编辑器打开。')
            before=path.read_bytes();digest=hashlib.sha256(before).hexdigest()
            if not data.get('etag') or digest!=data['etag']:raise UserError('原文件已被其他程序修改。你的编辑仍保留，请先复制草稿并重新打开比较。',409)
            if item['kind']=='docx':
                from .docx_io import edit_docx
                try:after=edit_docx(path,data.get('paragraphs',[]))
                except ValueError as e:raise UserError(str(e))
            else:
                content=data.get('content')
                if not isinstance(content,str) or len(content.encode('utf-8'))>TEXT_LIMIT:raise UserError('文档最多2 MiB。')
                _,encoding=decode_text(before)
                if encoding=='utf-8-sig' and not before.startswith(b'\xef\xbb\xbf'):encoding='utf-8'
                try:after=content.encode(encoding)
                except UnicodeError:raise UserError('新文字超出原文件编码范围，请先用系统编辑器将文件另存为 UTF-8。')
            if after==before:return self.read_content(iid)
            vid=uid();backup=self.data_root / 'versions' / iid / (vid+path.suffix)
            backup.parent.mkdir(parents=True,exist_ok=True)
            with backup.open('xb') as f:f.write(before);f.flush();os.fsync(f.fileno())
            temporary=path.with_name('.'+path.name+'.'+uid()+'.tmp')
            try:
                with temporary.open('xb') as f:f.write(after);f.flush();os.fsync(f.fileno())
                if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise UserError('文件在保存过程中改变，已停止覆盖，草稿仍保留。',409)
                os.replace(temporary,path)
            finally:
                if temporary.exists():temporary.unlink()
            with self.connection() as db:db.execute('INSERT INTO versions VALUES(?,?,?,?,?,?)',(vid,iid,now(),len(before),str(backup),digest))
            # A file may be referenced by several projects. Refresh all known views.
            with self.connection() as db:
                sources=[dict(r) for r in db.execute('SELECT DISTINCT s.* FROM sources s JOIN items i ON i.source_id=s.id WHERE i.path=? AND i.removed=0',(str(path),))]
            for source in sources:self.index_files(source,[path])
            return self.read_content(iid)

    def backup_database(self):
        folder=self.data_root / 'backups';folder.mkdir(exist_ok=True)
        target=folder / ('yingxu-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uid()[:6]+'.sqlite3')
        with self.lock,self.connection() as source:
            dest=sqlite3.connect(target)
            try:source.backup(dest)
            finally:dest.close()
        return target

    def rename_file(self,iid,new_name):
        with self.lock:
            item=self.get_item(iid);path=self.resolve_item_path(item)
            name=safe_name(new_name)
            if name.lower().endswith(path.suffix.lower()):name=name[:-len(path.suffix)]
            name=safe_name(name)
            target=path.with_name(name+path.suffix)
            if target==path:return self.get_item(iid,True)
            if target.exists():raise UserError('同文件夹已有这个名称，请换一个名称。',409)
            if os.name!='nt':raise UserError('原文件重命名目前仅支持 Windows。')
            with self.connection() as db:
                # BEGIN IMMEDIATE prevents app writers racing the filesystem rename.
                db.execute('BEGIN IMMEDIATE')
                rows=db.execute('SELECT id FROM items WHERE path=?',(str(path),)).fetchall()
                os.rename(path,target)  # Windows fails rather than replacing an existing target.
                try:
                    db.execute('UPDATE sources SET path=? WHERE path=? AND is_file=1',(str(target),str(path)))
                    db.execute('UPDATE items SET path=?,name=?,updated=? WHERE path=?',(str(target),name,now(),str(path)))
                    for row in rows:self._search_row(db,row['id'])
                    db.commit()
                except Exception:
                    os.rename(target,path)
                    raise
            return self.get_item(iid,True)
