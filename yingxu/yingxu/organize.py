"""Physical project folders, reference organisation, and batch-safe soft trash."""
from __future__ import annotations

import os
import sys
from pathlib import Path
import sqlite3

from .store import CATEGORIES, UserError, clean_path, has_link, now, safe_name, uid


def _ids(values):
    if not isinstance(values,list) or not 1<=len(values)<=200 or any(not isinstance(v,str) for v in values):
        raise UserError('一次请选择 1 至 200 个条目。')
    if len(set(values))!=len(values):raise UserError('条目不能重复。')
    return values


def _rename(source,target):
    """Only publish to a vacant path; the caller verifies the project boundary."""
    if target.exists() or target.is_symlink():raise UserError('目标位置已有同名文件或文件夹，未覆盖任何内容。',409)
    clean_path(source);clean_path(target.parent)
    if os.name=='nt':os.rename(source,target)
    elif sys.platform == 'darwin':
        from .macos import rename_exclusive
        rename_exclusive(source,target)
    elif source.is_file():
        os.link(source,target);source.unlink()
    else:
        raise UserError('实际文件夹改名需要 Windows 桌面环境。')


class Organize:
    def __init__(self,store):self.store=store

    def _folder(self,db,folder_id,active=True):
        row=db.execute('SELECT * FROM folders WHERE id=?'+(' AND removed=0' if active else ''),(folder_id,)).fetchone()
        if row is None:raise UserError('文件夹不存在或已移入回收站。',404)
        return dict(row)

    def _folder_result(self,row,project,count=0):
        result=dict(row)
        result.update(path=str(Path(project['root'])/row['relative_path']),
                      folder_path=row['relative_path'][len(CATEGORIES[row['category']][1])+1:],count=count)
        return result

    def folders(self,project_id,category=''):
        project=self.store.get_project(project_id)
        if category and category not in CATEGORIES:raise UserError('分类不存在。')
        with self.store.connection() as db:
            args=[project_id];sql='SELECT * FROM folders WHERE project_id=? AND removed=0'
            if category:sql+=' AND category=?';args.append(category)
            total=db.execute('SELECT count(*) FROM ('+sql+')',args).fetchone()[0]
            rows=db.execute(sql+' ORDER BY category,relative_path COLLATE NOCASE,id LIMIT 5000',args).fetchall()
            counts={row[0]:row[1] for row in db.execute('SELECT folder_id,count(*) FROM items WHERE project_id=? AND removed=0 GROUP BY folder_id',(project_id,))}
        results=[self._folder_result(dict(row),project,counts.get(row['id'],0)) for row in rows]
        return {'folders':results,'total':total,'truncated':total>len(results)}

    def get_folder(self,folder_id):
        with self.store.connection() as db:
            row=self._folder(db,folder_id);project=self.store._project(db,row['project_id'])
            count=db.execute('SELECT count(*) FROM items WHERE folder_id=? AND removed=0',(folder_id,)).fetchone()[0]
        return self._folder_result(row,project,count)

    def folder_path(self,project_id,category,folder_id=None):
        if category not in CATEGORIES:raise UserError('分类不存在。')
        project=self.store.get_project(project_id);root=clean_path(project['root'])
        if folder_id in ('',None,'root'):target=root/CATEGORIES[category][1]
        else:
            with self.store.connection() as db:folder=self._folder(db,folder_id)
            if folder['project_id']!=project_id or folder['category']!=category:raise UserError('目标文件夹不属于这个项目和分类。')
            target=root/folder['relative_path']
        if category=='unclassified' and folder_id in ('',None,'root') and not target.exists():
            target.mkdir(exist_ok=True)
        path=clean_path(target)
        if not path.is_relative_to(root) or not path.is_dir():raise UserError('项目文件夹路径无效。',403)
        return path

    def create_folder(self,project_id,category,name,parent_id=None):
        name=safe_name(name);parent_id=None if parent_id in ('',None,'root') else parent_id
        with self.store.lock:
            project=self.store.get_project(project_id)
            with self.store.connection() as db:
                if db.execute('SELECT count(*) FROM folders WHERE project_id=? AND removed=0',(project_id,)).fetchone()[0]>=5000:
                    raise UserError('每个项目最多支持 5000 个活动文件夹。')
            parent=self.folder_path(project_id,category,parent_id)
            path=parent/name;root=clean_path(project['root'])
            if len(path.relative_to(root/CATEGORIES[category][1]).parts)>20:raise UserError('文件夹最多支持 20 层。')
            if path.exists() or path.is_symlink():raise UserError('这里已有同名文件夹；回收站里的同名文件夹请先恢复。',409)
            fid=uid();created=False
            try:
                with self.store.connection() as db:
                    db.execute('BEGIN IMMEDIATE')
                    self.store._project(db,project_id)
                    if parent_id:self._folder(db,parent_id)
                    path.mkdir();created=True
                    db.execute('INSERT INTO folders(id,project_id,category,parent_id,name,relative_path,created,updated) VALUES(?,?,?,?,?,?,?,?)',
                               (fid,project_id,category,parent_id,name,path.relative_to(root).as_posix(),now(),now()))
            except Exception:
                if created and path.is_dir() and not has_link(path):path.rmdir()
                raise
        return self.get_folder(fid)

    def update_project(self,project_id,data):
        if not isinstance(data,dict):raise UserError('项目资料格式不正确。')
        updates={}
        if 'name' in data:updates['name']=safe_name(data['name'])
        if 'description' in data:
            description=str(data['description'])
            if len(description)>4000:raise UserError('项目简介最多 4000 字。')
            updates['description']=description
        with self.store.lock,self.store.connection() as db:
            self.store._project(db,project_id)
            if updates:
                updates['updated']=now()
                db.execute('UPDATE projects SET '+','.join(key+'=?' for key in updates)+' WHERE id=?',[*updates.values(),project_id])
        return self.store.get_project(project_id)

    def _source_for_path(self,db,row,path):
        source=db.execute('SELECT * FROM sources WHERE id=?',(row['source_id'],)).fetchone()
        if source:
            root=Path(source['path'])
            if (source['is_file'] and root==path) or (not source['is_file'] and path.is_relative_to(root)):return source['id']
        db.execute('INSERT OR IGNORE INTO sources(id,project_id,path,category,is_file) VALUES(?,?,?,?,1)',
                   (uid(),row['project_id'],str(path),row['category']))
        return db.execute('SELECT id FROM sources WHERE project_id=? AND path=?',(row['project_id'],str(path))).fetchone()[0]

    def _repoint_file(self,db,source,target):
        rows=[dict(r) for r in db.execute('SELECT id,project_id,source_id,category FROM items WHERE path=?',(str(source),))]
        db.execute('UPDATE sources SET path=? WHERE path=? AND is_file=1',(str(target),str(source)))
        for row in rows:
            source_id=self._source_for_path(db,row,target)
            db.execute('UPDATE items SET path=?,source_id=?,updated=? WHERE id=?',(str(target),source_id,now(),row['id']))

    @staticmethod
    def _subtree_pattern(path):
        return str(path).replace('!','!!').replace('%','!%').replace('_','!_')+os.sep+'%'

    def _repoint_directory(self,db,source,target,project):
        pattern=self._subtree_pattern(source)
        for row in db.execute("SELECT id,path FROM sources WHERE path=? OR path LIKE ? ESCAPE '!'",(str(source),pattern)).fetchall():
            new_path=target/Path(row['path']).relative_to(source)
            db.execute('UPDATE sources SET path=? WHERE id=?',(str(new_path),row['id']))
        for row in db.execute("SELECT id,path FROM items WHERE path=? OR path LIKE ? ESCAPE '!'",(str(source),pattern)).fetchall():
            new_path=target/Path(row['path']).relative_to(source)
            db.execute('UPDATE items SET path=?,updated=? WHERE id=?',(str(new_path),now(),row['id']))
        root=Path(project['root'])
        for row in db.execute('SELECT id,relative_path FROM folders WHERE project_id=?',(project['id'],)).fetchall():
            old=root/row['relative_path']
            if old==source or old.is_relative_to(source):
                relative=(target/old.relative_to(source)).relative_to(root).as_posix()
                db.execute('UPDATE folders SET relative_path=?,updated=? WHERE id=?',(relative,now(),row['id']))

    def rename_folder(self,folder_id,name):
        name=safe_name(name)
        with self.store.lock:
            folder=self.get_folder(folder_id);project=self.store.get_project(folder['project_id'])
            source=self.folder_path(folder['project_id'],folder['category'],folder_id)
            target=source.with_name(name);root=clean_path(project['root'])
            if target==source:return folder
            if not target.is_relative_to(root) or target.exists():raise UserError('目标文件夹已存在或路径无效。',409)
            # Moving the directory must never carry a junction or another project's root.
            for current,dirs,files in os.walk(source,followlinks=False):
                if any(entry.startswith('.yingxu-upload-') for entry in files):
                    raise UserError('此文件夹内有文件正在上传，请等上传完成后再改名。',409)
                if any(has_link(Path(current)/entry) for entry in dirs+files):raise UserError('文件夹内含联接或符号链接，不能整体改名。',409)
            with self.store.connection() as db:
                for row in db.execute('SELECT id,root FROM projects'):
                    if row['id']!=project['id'] and Path(row['root']).is_relative_to(source):raise UserError('此目录包含另一个项目，不能整体改名。',409)
            moved=False
            try:
                with self.store.connection() as db:
                    db.execute('BEGIN IMMEDIATE');self.store._project(db,project['id']);self._folder(db,folder_id)
                    _rename(source,target);moved=True
                    self._repoint_directory(db,source,target,project)
                    db.execute('UPDATE folders SET name=?,updated=? WHERE id=?',(name,now(),folder_id))
            except Exception:
                if moved:_rename(target,source)
                raise
        return self.get_folder(folder_id)

    def move_items(self,ids,category,folder_id=None,move_files=True):
        ids=_ids(ids);folder_id=None if folder_id in ('',None,'root') else folder_id
        with self.store.lock:
            columns='id,project_id,source_id,name,category,folder_id,path,kind,ext'
            with self.store.connection() as db:
                found={r['id']:dict(r) for r in db.execute('SELECT '+columns+' FROM items WHERE removed=0 AND id IN ('+','.join('?' for _ in ids)+')',ids)}
            if len(found)!=len(ids):raise UserError('部分条目已不存在或已移入回收站。',404)
            items=[found[iid] for iid in ids]
            pids={item['project_id'] for item in items}
            if len(pids)!=1:raise UserError('一次只能移动同一个项目的条目。')
            pid=items[0]['project_id'];project=self.store.get_project(pid)
            destination=self.folder_path(pid,category,folder_id);root=clean_path(project['root'])
            plans=[];reserved=set();stats={'moved':0,'referenced':0,'unchanged':0,'copied':0}
            for item in items:
                path=self.store.resolve_item_path(item)
                owned=bool(move_files and path.is_relative_to(root))
                target=destination/path.name if owned else path
                changed=path!=target
                if changed:
                    key=os.path.normcase(str(target))
                    if key in reserved or target.exists() or target.is_symlink():raise UserError('目标文件夹已有同名文件：'+target.name+'；未移动任何文件。',409)
                    reserved.add(key)
                action='moved' if changed else ('referenced' if item['category']!=category or item.get('folder_id')!=folder_id else 'unchanged')
                stats[action]+=1;plans.append((item,path,target))
            completed=[]
            try:
                with self.store.connection() as db:
                    db.execute('BEGIN IMMEDIATE');self.store._project(db,pid)
                    if folder_id:self._folder(db,folder_id)
                    for item,path,target in plans:
                        if path!=target:
                            # Stale indexed targets also require explicit resolution.
                            for other in db.execute('SELECT project_id FROM items WHERE path=?',(str(path),)):
                                if db.execute('SELECT 1 FROM items WHERE project_id=? AND path=?',(other['project_id'],str(target))).fetchone():
                                    raise UserError('目标路径已有项目记录，请先恢复或整理同名条目。',409)
                            _rename(path,target);completed.append((path,target))
                            self._repoint_file(db,path,target)
                        db.execute('UPDATE items SET category=?,folder_id=?,updated=? WHERE id=?',(category,folder_id,now(),item['id']))
                        self.store._search_row(db,item['id'])
            except Exception:
                for old,new in reversed(completed):_rename(new,old)
                raise
            with self.store.connection() as db:
                returned=[dict(r) for r in db.execute('SELECT '+columns+' FROM items WHERE id IN ('+','.join('?' for _ in ids)+')',ids)]
            display=self.get_folder(folder_id)['folder_path'] if folder_id else ''
            for item in returned:item['folder_path']=display
        return {'ok':True,'project_id':pid,'items':returned,'stats':stats}

    def assign_imported(self,source,paths,category,folder_id=None):
        pid=source['project_id'];self.folder_path(pid,category,folder_id)
        names=[str(Path(path)) for path in paths]
        if not names:return {'ok':True,'project_id':pid,'items':[],'stats':{'moved':0,'referenced':0,'unchanged':0,'copied':0}}
        if len(names)>200:raise UserError('一次最多归类 200 个条目。')
        folder_id=None if folder_id in ('',None,'root') else folder_id
        stats={'moved':0,'referenced':0,'unchanged':0,'copied':0}
        with self.store.lock,self.store.connection() as db:
            self.store._project(db,pid)
            if folder_id:
                folder=self._folder(db,folder_id)
                if folder['project_id']!=pid or folder['category']!=category:raise UserError('导入目标文件夹已经改变。',409)
            rows=db.execute('SELECT id,category,folder_id FROM items WHERE project_id=? AND removed=0 AND path IN ('+','.join('?' for _ in names)+')',[pid,*names]).fetchall()
            for row in rows:
                if row['category']==category and row['folder_id']==folder_id:stats['unchanged']+=1;continue
                db.execute('UPDATE items SET category=?,folder_id=?,updated=? WHERE id=?',(category,folder_id,now(),row['id']))
                if row['category']!=category:self.store._search_row(db,row['id'])
                stats['referenced']+=1
        return {'ok':True,'project_id':pid,'items':[],'stats':stats}

    def _mark_batch(self,db,kind,target_id,pid,name,entities):
        batch_id=uid();created=now()
        db.execute('INSERT INTO trash_batches(id,kind,target_id,project_id,name,created) VALUES(?,?,?,?,?,?)',(batch_id,kind,target_id,pid,name,created))
        counts={'item':0,'folder':0,'project':0}
        tables={'item':'items','folder':'folders','project':'projects'}
        for entity_type,table in tables.items():
            selected=list(dict.fromkeys(entity_id for kind,entity_id in entities if kind==entity_type))
            for start in range(0,len(selected),500):
                batch=selected[start:start+500];marks=','.join('?' for _ in batch)
                active=[r[0] for r in db.execute('SELECT id FROM '+table+' WHERE removed=0 AND id IN ('+marks+')',batch)]
                if not active:continue
                marks=','.join('?' for _ in active)
                db.execute('UPDATE '+table+' SET removed=1,removed_batch=? WHERE id IN ('+marks+')',[batch_id,*active])
                db.executemany('INSERT INTO trash_members(batch_id,entity_type,entity_id) VALUES(?,?,?)',[(batch_id,entity_type,entity_id) for entity_id in active])
                if entity_type=='item':db.execute('DELETE FROM item_search WHERE rowid IN (SELECT rowid FROM items WHERE id IN ('+marks+'))',active)
                counts[entity_type]+=len(active)
        return {'ok':True,'id':batch_id,'batch_id':batch_id,'project_id':pid,'kind':kind,
                'count':sum(counts.values()),'item_count':counts['item'],'folder_count':counts['folder']}

    def delete_items(self,ids):
        ids=_ids(ids)
        with self.store.lock,self.store.connection() as db:
            rows=[db.execute('SELECT * FROM items WHERE id=? AND removed=0',(iid,)).fetchone() for iid in ids]
            if any(row is None for row in rows):raise UserError('条目已不存在或已移入回收站。',404)
            if len({row['project_id'] for row in rows})!=1:raise UserError('一次只能删除同一个项目的条目。')
            pid=rows[0]['project_id'];self.store._project(db,pid)
            name=rows[0]['name'] if len(rows)==1 else f'{len(rows)} 项素材'
            return self._mark_batch(db,'items',ids[0],pid,name,[('item',iid) for iid in ids])

    def delete_folder(self,folder_id):
        with self.store.lock,self.store.connection() as db:
            folder=self._folder(db,folder_id);pid=folder['project_id'];self.store._project(db,pid)
            ids=[row[0] for row in db.execute('''WITH RECURSIVE tree(id) AS (
                SELECT id FROM folders WHERE id=? UNION ALL SELECT f.id FROM folders f JOIN tree t ON f.parent_id=t.id)
                SELECT id FROM tree''',(folder_id,))]
            placeholders=','.join('?' for _ in ids)
            items=[row[0] for row in db.execute('SELECT id FROM items WHERE project_id=? AND removed=0 AND folder_id IN ('+placeholders+')',[pid,*ids])]
            return self._mark_batch(db,'folder',folder_id,pid,folder['name'],[('folder',fid) for fid in ids]+[('item',iid) for iid in items])

    def delete_project(self,project_id):
        with self.store.lock,self.store.connection() as db:
            project=self.store._project(db,project_id)
            folders=[row[0] for row in db.execute('SELECT id FROM folders WHERE project_id=? AND removed=0',(project_id,))]
            items=[row[0] for row in db.execute('SELECT id FROM items WHERE project_id=? AND removed=0',(project_id,))]
            return self._mark_batch(db,'project',project_id,project_id,project['name'],
                [('project',project_id)]+[('folder',fid) for fid in folders]+[('item',iid) for iid in items])

    def trash(self,project_id='',limit=200,offset=0):
        limit=max(1,min(500,int(limit)));offset=max(0,int(offset))
        with self.store.connection() as db:
            args=[];where='b.restored=0 AND b.purged=0'
            if project_id:where+=' AND b.project_id=?';args.append(project_id)
            total=db.execute('SELECT count(*) FROM trash_batches b WHERE '+where,args).fetchone()[0]
            rows=db.execute('''SELECT b.*,(SELECT count(*) FROM trash_members m WHERE m.batch_id=b.id) AS count
                FROM trash_batches b WHERE '''+where+' ORDER BY b.created DESC,b.id LIMIT ? OFFSET ?',[*args,limit,offset]).fetchall()
        entries=[{**dict(row),'batch_id':row['id']} for row in rows]
        return {'entries':entries,'total':total,'limit':limit,'offset':offset,'truncated':offset+len(entries)<total}

    def restore(self,batch_id):
        tables={'item':'items','folder':'folders','project':'projects'}
        with self.store.lock,self.store.connection() as db:
            batch=db.execute('SELECT * FROM trash_batches WHERE id=?',(batch_id,)).fetchone()
            if batch is None:raise UserError('回收站记录不存在。',404)
            if batch['purged']:raise UserError('记录已从映序回收站清理，请在 Windows 回收站找回文件。',409)
            if batch['recycle_started']:raise UserError('该批次曾提交 Windows 回收操作，不能直接恢复记录。请核对原文件和 Windows 回收站，找回文件后可重新导入；也可继续清理剩余记录。',409)
            if batch['restored']:return {'ok':True,'project_id':batch['project_id'],'kind':batch['kind'],'count':0}
            members=[]
            for member in db.execute('SELECT * FROM trash_members WHERE batch_id=?',(batch_id,)):
                row=db.execute('SELECT * FROM '+tables[member['entity_type']]+' WHERE id=? AND removed=1 AND removed_batch=?',(member['entity_id'],batch_id)).fetchone()
                if row:members.append((member['entity_type'],dict(row)))
            restoring={kind:{row['id'] for entity,row in members if entity==kind} for kind in tables}
            project=db.execute('SELECT * FROM projects WHERE id=?',(batch['project_id'],)).fetchone()
            if project is None:raise UserError('项目记录不存在。',404)
            if project['removed'] and project['id'] not in restoring['project']:raise UserError('请先恢复所属项目，再恢复这些内容。',409)
            for kind,row in members:
                parent_id=row.get('parent_id') if kind=='folder' else row.get('folder_id') if kind=='item' else None
                if parent_id and parent_id not in restoring['folder']:
                    parent=db.execute('SELECT removed FROM folders WHERE id=?',(parent_id,)).fetchone()
                    if parent is None or parent['removed']:raise UserError('请先恢复所属文件夹，再恢复这些内容。',409)
            for kind,row in members:
                db.execute('UPDATE '+tables[kind]+' SET removed=0,removed_batch=NULL WHERE id=?',(row['id'],))
                if kind=='item':self.store._search_row(db,row['id'])
            db.execute('UPDATE trash_batches SET restored=1 WHERE id=?',(batch_id,))
            return {'ok':True,'project_id':batch['project_id'],'kind':batch['kind'],'count':len(members)}
