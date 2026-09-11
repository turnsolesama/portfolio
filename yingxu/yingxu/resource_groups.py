"""Logical material stacks: group membership never changes files or categories."""
from __future__ import annotations

import re

from .store import UserError, now, uid


MAX_MEMBERS = 200
MAX_GROUPS = 500
_ACTIVE = "i.removed=0 AND (i.folder_id IS NULL OR EXISTS(SELECT 1 FROM folders f WHERE f.id=i.folder_id AND f.project_id=i.project_id AND f.removed=0))"
_BRIEF = """i.id,i.project_id,i.source_id,i.name,i.category,i.kind,i.ext,i.path,
    i.size,i.mtime,i.status,i.tags,substr(i.notes,1,240) AS notes,
    i.metadata,i.folder_id,i.sort_order,i.created,i.updated"""


class ResourceGroups:
    def __init__(self, store):
        self.store = store
        with store.lock, store.connection() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS resource_groups(
              id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
              name TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL,
              revision INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS resource_group_members(
              group_id TEXT NOT NULL REFERENCES resource_groups(id) ON DELETE CASCADE,
              item_id TEXT NOT NULL UNIQUE REFERENCES items(id),
              sort_order INTEGER NOT NULL,
              PRIMARY KEY(group_id,item_id));
            CREATE INDEX IF NOT EXISTS resource_groups_project ON resource_groups(project_id);
            CREATE INDEX IF NOT EXISTS resource_group_order ON resource_group_members(group_id,sort_order);
            ''')

    @staticmethod
    def _body(body, allowed):
        if not isinstance(body, dict) or set(body) - set(allowed):
            raise UserError('素材组参数无效。')

    @staticmethod
    def _id(value):
        if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{32}', value):
            raise UserError('请选择有效的项目、素材或素材组。')
        return value

    @staticmethod
    def _name(value):
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > 80 or any(ord(c) < 32 for c in value):
            raise UserError('素材组名称请填写 1 至 80 个字符。')
        return value.strip()

    def _ids(self, values, minimum=1):
        if not isinstance(values, list) or not minimum <= len(values) <= MAX_MEMBERS:
            raise UserError(f'请选择 {minimum} 至 {MAX_MEMBERS} 个素材。')
        ids = [self._id(value) for value in values]
        if len(set(ids)) != len(ids):
            raise UserError('素材列表不能重复。')
        return ids

    def _group(self, db, group_id):
        row = db.execute('SELECT g.* FROM resource_groups g JOIN projects p ON p.id=g.project_id '
                         'WHERE g.id=? AND p.removed=0', (self._id(group_id),)).fetchone()
        if row is None:
            raise UserError('素材组不存在或项目已移入回收站。', 404)
        return dict(row)

    @staticmethod
    def _revision(group, body):
        if 'revision' in body:
            revision = body['revision']
            if type(revision) is not int or revision < 1:
                raise UserError('素材组版本参数无效。')
            if revision != group['revision']:
                raise UserError('素材组已发生变化，请刷新后重试。', 409)

    @staticmethod
    def _touch(db, group_id):
        db.execute('UPDATE resource_groups SET updated=?,revision=revision+1 WHERE id=?', (now(), group_id))

    def _validate_members(self, db, project_id, ids, group_id=None):
        marks = ','.join('?' for _ in ids)
        rows = db.execute(f'SELECT i.id FROM items i WHERE i.project_id=? AND {_ACTIVE} AND i.id IN ({marks})',
                          [project_id, *ids]).fetchall()
        if len(rows) != len(ids):
            raise UserError('素材不存在、已移入回收站或不属于同一个项目。', 409)
        owners = db.execute(f'SELECT item_id,group_id FROM resource_group_members WHERE item_id IN ({marks})', ids).fetchall()
        if any(row['group_id'] != group_id for row in owners):
            raise UserError('部分素材已经在其他组中，请先从原组移出。', 409)
        return {row['item_id'] for row in owners}

    def _describe(self, db, group, detail=False):
        group = dict(group)
        # Keep the bounded group membership as the outer loop. A regular JOIN
        # can make SQLite scan every item in this project for every group.
        rows = db.execute(f'SELECT i.id,i.category FROM resource_group_members m CROSS JOIN items i ON i.id=m.item_id '
                          f'WHERE m.group_id=? AND i.project_id=? AND {_ACTIVE} ORDER BY m.sort_order,i.id',
                          (group['id'], group['project_id'])).fetchall()
        group.update(count=len(rows), member_ids=[r['id'] for r in rows], categories=sorted({r['category'] for r in rows}))
        members = [self.store.item_dict(row, brief=True) for row in db.execute(
            f'SELECT {_BRIEF} FROM resource_group_members m CROSS JOIN items i ON i.id=m.item_id '
            f'WHERE m.group_id=? AND i.project_id=? AND {_ACTIVE} ORDER BY m.sort_order,i.id LIMIT ?',
            (group['id'], group['project_id'], MAX_MEMBERS if detail else 4))]
        group['preview'] = members[:4]
        if detail:
            group['members'] = members
        return group

    def list(self, project_id):
        with self.store.lock, self.store.connection() as db:
            db.execute('BEGIN')
            self.store._project(db, self._id(project_id))
            groups = [self._describe(db, row) for row in db.execute(
                'SELECT * FROM resource_groups WHERE project_id=? ORDER BY created,id', (project_id,)).fetchall()]
            return {'groups': groups, 'total': len(groups)}

    def get(self, group_id):
        with self.store.lock, self.store.connection() as db:
            db.execute('BEGIN')
            return self._describe(db, self._group(db, group_id), detail=True)

    def create(self, body):
        self._body(body, {'project_id', 'name', 'item_ids'})
        project_id = self._id(body.get('project_id'))
        ids, name = self._ids(body.get('item_ids'), 2), self._name(body.get('name', '素材组'))
        with self.store.lock, self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            self.store._project(db, project_id)
            if db.execute('SELECT count(*) FROM resource_groups WHERE project_id=?', (project_id,)).fetchone()[0] >= MAX_GROUPS:
                raise UserError(f'每个项目最多 {MAX_GROUPS} 个素材组，请先整理现有分组。', 409)
            self._validate_members(db, project_id, ids)
            group_id, timestamp = uid(), now()
            db.execute('INSERT INTO resource_groups VALUES(?,?,?,?,?,1)', (group_id, project_id, name, timestamp, timestamp))
            db.executemany('INSERT INTO resource_group_members VALUES(?,?,?)', [(group_id, iid, n) for n, iid in enumerate(ids)])
            return self._describe(db, self._group(db, group_id), detail=True)

    def rename(self, group_id, body):
        self._body(body, {'name', 'revision'})
        name = self._name(body.get('name'))
        with self.store.lock, self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            group = self._group(db, group_id)
            self._revision(group, body)
            if name != group['name']:
                db.execute('UPDATE resource_groups SET name=? WHERE id=?', (name, group_id))
                self._touch(db, group_id)
            return self._describe(db, self._group(db, group_id), detail=True)

    def add(self, group_id, body):
        self._body(body, {'item_ids', 'revision'})
        ids = self._ids(body.get('item_ids'))
        with self.store.lock, self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            group = self._group(db, group_id)
            self._revision(group, body)
            existing = self._validate_members(db, group['project_id'], ids, group_id)
            added = [iid for iid in ids if iid not in existing]
            count, last = db.execute('SELECT count(*),coalesce(max(sort_order),-1) FROM resource_group_members WHERE group_id=?', (group_id,)).fetchone()
            if count + len(added) > MAX_MEMBERS:
                raise UserError(f'每个素材组最多 {MAX_MEMBERS} 个素材，包含暂在回收站的成员。', 409)
            if added:
                db.executemany('INSERT INTO resource_group_members VALUES(?,?,?)', [(group_id, iid, last + 1 + n) for n, iid in enumerate(added)])
                self._touch(db, group_id)
            return self._describe(db, self._group(db, group_id), detail=True)

    def remove(self, group_id, body):
        self._body(body, {'item_ids', 'revision'})
        ids = self._ids(body.get('item_ids'))
        with self.store.lock, self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            group = self._group(db, group_id)
            self._revision(group, body)
            members = {r[0] for r in db.execute('SELECT item_id FROM resource_group_members WHERE group_id=?', (group_id,))}
            if not set(ids) <= members:
                raise UserError('素材已不在这个组中，请刷新后重试。', 409)
            db.executemany('DELETE FROM resource_group_members WHERE group_id=? AND item_id=?', [(group_id, iid) for iid in ids])
            self._touch(db, group_id)
            return self._describe(db, self._group(db, group_id), detail=True)

    def transfer(self, group_id, body):
        """Move membership atomically; a failed target never removes the source."""
        self._body(body, {'ids', 'revision', 'target_group_id', 'target_revision'})
        ids = self._ids(body.get('ids'))
        if 'revision' not in body or 'target_group_id' not in body:
            raise UserError('拖动前请重新读取素材组。')
        target_id = body['target_group_id']
        if target_id is not None:
            self._id(target_id)
            if 'target_revision' not in body:
                raise UserError('拖动前请重新读取目标素材组。')
        elif 'target_revision' in body:
            raise UserError('移出组不需要目标版本。')
        with self.store.lock, self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            source = self._group(db, group_id)
            self._revision(source, body)
            owned = self._validate_members(db, source['project_id'], ids, group_id)
            if owned != set(ids):
                raise UserError('素材已不在这个组中，请刷新后重试。', 409)
            target = None
            if target_id is not None:
                target = self._group(db, target_id)
                if target['project_id'] != source['project_id']:
                    raise UserError('只能拖到同一项目的素材组。', 409)
                self._revision(target, {'revision': body['target_revision']})
                if target_id == group_id:
                    detail = self._describe(db, source, detail=True)
                    return {'source': detail, 'target': detail}
                count, last = db.execute('SELECT count(*),coalesce(max(sort_order),-1) FROM resource_group_members WHERE group_id=?', (target_id,)).fetchone()
                if count + len(ids) > MAX_MEMBERS:
                    raise UserError(f'目标组最多 {MAX_MEMBERS} 个素材，原组保持不变。', 409)
                db.executemany('UPDATE resource_group_members SET group_id=?,sort_order=? WHERE group_id=? AND item_id=?',
                               [(target_id, last + 1 + n, group_id, iid) for n, iid in enumerate(ids)])
                self._touch(db, target_id)
            else:
                db.executemany('DELETE FROM resource_group_members WHERE group_id=? AND item_id=?', [(group_id, iid) for iid in ids])
            self._touch(db, group_id)
            return {'source': self._describe(db, self._group(db, group_id), detail=True),
                    'target': self._describe(db, self._group(db, target_id), detail=True) if target is not None else None}

    def dissolve(self, group_id, body):
        self._body(body, {'revision'})
        with self.store.lock, self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            group = self._group(db, group_id)
            self._revision(group, body)
            members = self._describe(db, group)['member_ids']
            db.execute('DELETE FROM resource_groups WHERE id=?', (group_id,))
            return {'dissolved': True, 'id': group_id, 'project_id': group['project_id'], 'member_ids': members}
