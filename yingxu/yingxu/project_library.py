"""Logical project folders. Organisation never relocates project files."""
from __future__ import annotations

from .store import UserError, now, uid


class ProjectLibrary:
    def __init__(self, store):
        self.store = store
        with store.lock, store.connection() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS project_library_folders(
              id TEXT PRIMARY KEY, name TEXT NOT NULL,
              parent_id TEXT REFERENCES project_library_folders(id));
            CREATE TABLE IF NOT EXISTS project_library_entries(
              project_id TEXT PRIMARY KEY REFERENCES projects(id),
              folder_id TEXT REFERENCES project_library_folders(id), last_opened TEXT);
            CREATE INDEX IF NOT EXISTS project_library_parent ON project_library_folders(parent_id);
            CREATE INDEX IF NOT EXISTS project_library_folder ON project_library_entries(folder_id);
            ''')

    @staticmethod
    def _body(body, allowed):
        if not isinstance(body, dict) or not body or set(body) - set(allowed):
            raise UserError('项目库参数无效。')

    @staticmethod
    def _name(value):
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > 80 or any(ord(c) < 32 for c in value):
            raise UserError('分类名称请填写 1 至 80 个字符。')
        return value.strip()

    @staticmethod
    def _folder(db, folder_id):
        if not isinstance(folder_id, str):
            raise UserError('请选择有效的项目分类。')
        row = db.execute('SELECT * FROM project_library_folders WHERE id=?', (folder_id,)).fetchone()
        if row is None:
            raise UserError('项目分类不存在，请刷新后重试。', 404)
        return dict(row)

    def _parent(self, db, parent_id):
        if parent_id is not None:
            self._folder(db, parent_id)

    @staticmethod
    def _unique(db, name, parent_id, except_id=''):
        siblings = db.execute('SELECT id,name FROM project_library_folders WHERE parent_id IS ?', (parent_id,))
        if any(r['id'] != except_id and r['name'].casefold() == name.casefold() for r in siblings):
            raise UserError('这一层已有同名分类。', 409)

    def snapshot(self):
        with self.store.lock:
            projects = self.store.list_projects()
            with self.store.connection() as db:
                folders = [dict(r) for r in db.execute('SELECT * FROM project_library_folders ORDER BY name COLLATE NOCASE,id')]
                entries = {r['project_id']: dict(r) for r in db.execute('SELECT * FROM project_library_entries')}
            for project in projects:
                entry = entries.get(project['id'], {})
                project.update(folder_id=entry.get('folder_id'), last_opened=entry.get('last_opened'))
            recent = sorted((p for p in projects if p['last_opened']), key=lambda p: (p['last_opened'], p['id']), reverse=True)
            return {'folders': folders, 'projects': projects, 'recent_ids': [p['id'] for p in recent], 'total': len(projects)}

    def create_folder(self, body):
        self._body(body, {'name', 'parent_id'})
        name, parent = self._name(body.get('name')), body.get('parent_id')
        with self.store.lock, self.store.connection() as db:
            self._parent(db, parent)
            self._unique(db, name, parent)
            folder_id = uid()
            db.execute('INSERT INTO project_library_folders VALUES(?,?,?)', (folder_id, name, parent))
            return self._folder(db, folder_id)

    def update_folder(self, folder_id, body):
        self._body(body, {'name', 'parent_id'})
        with self.store.lock, self.store.connection() as db:
            folder = self._folder(db, folder_id)
            name = self._name(body.get('name', folder['name']))
            parent = body.get('parent_id', folder['parent_id'])
            self._parent(db, parent)
            cursor, seen = parent, set()
            while cursor is not None:
                if cursor == folder_id or cursor in seen:
                    raise UserError('不能把分类移入自身或自己的子分类。', 409)
                seen.add(cursor)
                cursor = self._folder(db, cursor)['parent_id']
            self._unique(db, name, parent, folder_id)
            db.execute('UPDATE project_library_folders SET name=?,parent_id=? WHERE id=?', (name, parent, folder_id))
            return self._folder(db, folder_id)

    def delete_folder(self, folder_id):
        with self.store.lock, self.store.connection() as db:
            self._folder(db, folder_id)
            if db.execute('SELECT 1 FROM project_library_folders WHERE parent_id=? LIMIT 1', (folder_id,)).fetchone():
                raise UserError('请先移走子分类，再删除这个空分类。', 409)
            if db.execute('SELECT 1 FROM project_library_entries e JOIN projects p ON p.id=e.project_id '
                          'WHERE e.folder_id=? AND p.removed=0 LIMIT 1', (folder_id,)).fetchone():
                raise UserError('请先移走分类中的项目，再删除空分类。', 409)
            db.execute('UPDATE project_library_entries SET folder_id=NULL WHERE folder_id=?', (folder_id,))
            db.execute('DELETE FROM project_library_folders WHERE id=?', (folder_id,))
            return {'deleted': True, 'id': folder_id}

    def assign_project(self, project_id, body):
        self._body(body, {'folder_id'})
        folder = body['folder_id']
        with self.store.lock, self.store.connection() as db:
            self.store._project(db, project_id)
            self._parent(db, folder)
            db.execute('INSERT INTO project_library_entries(project_id,folder_id) VALUES(?,?) '
                       'ON CONFLICT(project_id) DO UPDATE SET folder_id=excluded.folder_id', (project_id, folder))
            return dict(db.execute('SELECT * FROM project_library_entries WHERE project_id=?', (project_id,)).fetchone())

    def visit(self, project_id):
        with self.store.lock, self.store.connection() as db:
            self.store._project(db, project_id)
            db.execute('INSERT INTO project_library_entries(project_id,last_opened) VALUES(?,?) '
                       'ON CONFLICT(project_id) DO UPDATE SET last_opened=excluded.last_opened', (project_id, now()))
            return dict(db.execute('SELECT * FROM project_library_entries WHERE project_id=?', (project_id,)).fetchone())
