"""A bounded local SKILL.md catalogue. Content is data and is never executed."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import threading

from .store import UserError, clean_path, has_link, now, safe_name, uid

MAX_SKILL_BYTES = 1024 * 1024
MAX_SKILLS = 2000
MAX_DEPTH = 3
MAX_SCAN_ENTRIES = 20_000
SKIP_DIRS = {"cache", "caches", "__pycache__", "node_modules", "venv", "env"}
SOURCE_LABELS = {"yingxu": "映序本地", "codex": "Codex 技能", "claude": "Claude 技能"}


def _key(path):
    value = os.path.normcase(os.path.abspath(path))
    return value.casefold() if os.name == 'nt' else value


def _check_no_links(path):
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        if part.exists() or part.is_symlink():
            if has_link(part):
                raise UserError("技能路径包含联接或符号链接，请选择实际文件夹。")
    return path


def _scalar(value):
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        try:
            return str(json.loads(value))
        except (ValueError, TypeError):
            return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1].replace("''", "'")
    return value.split(" #", 1)[0].strip()


def _metadata(content, fallback="未命名技能"):
    """Read only a small subset of YAML scalars; no YAML objects or directives."""
    lines = content.lstrip("\ufeff").splitlines()
    result = {}
    if lines and lines[0].strip() == "---":
        stop = next((i for i in range(1, min(len(lines), 300)) if lines[i].strip() in {"---", "..."}), None)
        if stop is not None:
            i = 1
            while i < stop:
                match = re.match(r"^(name|description):[ \t]*(.*)$", lines[i])
                if not match:
                    i += 1
                    continue
                field, value = match.groups()
                subsequent = []
                cursor = i + 1
                while cursor < stop and (not lines[cursor].strip() or lines[cursor][:1].isspace()):
                    subsequent.append(lines[cursor])
                    cursor += 1
                if value.strip() in {"|", "|-", "|+", ">", ">-", ">+"}:
                    nonempty = [line for line in subsequent if line.strip()]
                    indent = min((len(line) - len(line.lstrip()) for line in nonempty), default=0)
                    text = [line[indent:] for line in subsequent]
                    parsed = " ".join(line.strip() for line in text) if value.strip().startswith(">") else "\n".join(text)
                    result[field] = parsed.strip()
                else:
                    parsed = _scalar(value)
                    if subsequent and not value.startswith(('"', "'")):
                        parsed += " " + " ".join(line.strip() for line in subsequent)
                    result[field] = parsed.strip()
                i = cursor
    return {
        "name": (result.get("name") or fallback).strip()[:160],
        "description": result.get("description", "").strip()[:4000],
    }


def _read(path):
    _check_no_links(path)
    if not path.is_file() or path.name.lower() != "skill.md":
        raise UserError("技能文件已经不存在。", 404)
    if path.stat().st_size > MAX_SKILL_BYTES:
        raise UserError("SKILL.md 超过 1 MiB，已跳过以保持工作台流畅。")
    with path.open("rb") as handle:
        raw = handle.read(MAX_SKILL_BYTES + 1)
    if len(raw) > MAX_SKILL_BYTES:
        raise UserError("SKILL.md 超过 1 MiB。")
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeError as exc:
        raise UserError("技能文件需使用 UTF-8 编码。") from exc
    if "\x00" in content:
        raise UserError("技能文件包含无效文本字符。")
    return raw, content, hashlib.sha256(raw).hexdigest()


class SkillLibrary:
    def __init__(self, store):
        self.store = store
        self.lock = threading.RLock()
        self.root = _check_no_links(Path(store.data_root) / "skills")
        self.root.mkdir(parents=True, exist_ok=True)
        self.versions_root = Path(store.data_root) / "skill_versions"
        self.sources = {
            "yingxu": self.root,
            "codex": Path.home() / ".codex" / "skills",
            "claude": Path.home() / ".claude" / "skills",
        }
        with store.lock, store.connection() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS yx_skills(
              id TEXT PRIMARY KEY,path TEXT NOT NULL,path_key TEXT UNIQUE NOT NULL,
              name TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',source TEXT NOT NULL,
              editable INTEGER NOT NULL DEFAULT 0,mtime INTEGER NOT NULL DEFAULT 0,
              size INTEGER NOT NULL DEFAULT 0,etag TEXT NOT NULL DEFAULT '',
              available INTEGER NOT NULL DEFAULT 1,created TEXT NOT NULL,updated TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS yx_skills_available ON yx_skills(available,source,name);
            CREATE TABLE IF NOT EXISTS yx_project_skills(
              project_id TEXT NOT NULL REFERENCES projects(id),
              skill_id TEXT NOT NULL REFERENCES yx_skills(id),created TEXT NOT NULL,
              PRIMARY KEY(project_id,skill_id));
            """)
            columns = {row[1] for row in db.execute('PRAGMA table_info(yx_skills)')}
            if 'removed' not in columns:
                db.execute('ALTER TABLE yx_skills ADD COLUMN removed INTEGER NOT NULL DEFAULT 0')
            if 'removed_at' not in columns:
                db.execute("ALTER TABLE yx_skills ADD COLUMN removed_at TEXT NOT NULL DEFAULT ''")
            if 'purged' not in columns:
                db.execute('ALTER TABLE yx_skills ADD COLUMN purged INTEGER NOT NULL DEFAULT 0')
            if 'recycle_started' not in columns:
                db.execute('ALTER TABLE yx_skills ADD COLUMN recycle_started INTEGER NOT NULL DEFAULT 0')
        self.refresh()

    @staticmethod
    def _item(row, bound=False):
        result = dict(row)
        result.pop("path_key", None)
        result["editable"] = bool(result["editable"])
        result["available"] = bool(result["available"])
        result["bound"] = bool(bound)
        result["source_label"] = SOURCE_LABELS.get(result["source"], result["source"])
        return result

    def _row(self, skill_id):
        with self.store.connection() as db:
            row = db.execute("SELECT * FROM yx_skills WHERE id=? AND removed=0", (str(skill_id),)).fetchone()
        if row is None:
            raise UserError("技能不存在，请刷新技能库。", 404)
        return dict(row)

    def _trusted_path(self, row, write=False):
        source = self.sources.get(row["source"])
        if source is None:
            raise UserError("技能来源无效。")
        path = _check_no_links(row["path"])
        root = _check_no_links(source)
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise UserError("技能路径超出已登记的技能库。") from exc
        if not path.is_file() or path.name.lower() != "skill.md":
            raise UserError("技能文件已经不存在，请刷新技能库。", 404)
        if write and (row["source"] != "yingxu" or not row["editable"] or path.stat().st_nlink > 1):
            raise UserError("外部技能和共享链接文件只读；请在映序中新建自己的技能。", 403)
        return path

    def directory(self, skill_id):
        """Resolve a registered active skill's location without reading its content."""
        with self.lock:
            return clean_path(self._trusted_path(self._row(skill_id)).parent)

    def _record(self, path, source, content, etag, previous=None):
        info = path.stat()
        metadata = _metadata(content, path.parent.name)
        return {
            "id": previous["id"] if previous else uid(),
            "path": str(path), "path_key": _key(path), **metadata,
            "source": source, "editable": int(source == "yingxu" and info.st_nlink == 1),
            "mtime": info.st_mtime_ns, "size": info.st_size, "etag": etag,
            "available": 1, "created": previous["created"] if previous else now(), "updated": now(),
        }

    def _upsert(self, db, record):
        db.execute("""
          INSERT INTO yx_skills(id,path,path_key,name,description,source,editable,mtime,size,etag,available,created,updated)
          VALUES(:id,:path,:path_key,:name,:description,:source,:editable,:mtime,:size,:etag,:available,:created,:updated)
          ON CONFLICT(path_key) DO UPDATE SET path=excluded.path,name=excluded.name,
            description=excluded.description,source=excluded.source,editable=excluded.editable,
            mtime=excluded.mtime,size=excluded.size,etag=excluded.etag,available=1,updated=excluded.updated
        """, record)

    def refresh(self):
        """Bounded refresh; unchanged files use metadata cache and keep bindings."""
        with self.lock:
            with self.store.connection() as db:
                previous = {row["path_key"]: dict(row) for row in db.execute("SELECT * FROM yx_skills")}
            records = []
            seen_paths = set()
            seen_files = set()
            seen_roots = set()
            errors = []
            skipped = 0
            visits = 0
            truncated = False
            for source, source_root in self.sources.items():
                if not source_root.exists():
                    continue
                try:
                    root = _check_no_links(source_root)
                    if not root.is_dir() or _key(root) in seen_roots:
                        continue
                    seen_roots.add(_key(root))
                except (UserError, OSError) as exc:
                    skipped += 1
                    errors.append(str(exc))
                    continue
                stack = [(root, 0)]
                while stack and len(records) < MAX_SKILLS and visits < MAX_SCAN_ENTRIES:
                    folder, depth = stack.pop()
                    try:
                        _check_no_links(folder)
                        with os.scandir(folder) as entries:
                            for entry in entries:
                                visits += 1
                                if visits > MAX_SCAN_ENTRIES or len(records) >= MAX_SKILLS:
                                    truncated = True
                                    break
                                path = Path(entry.path)
                                if has_link(path):
                                    skipped += 1
                                    continue
                                if entry.is_dir(follow_symlinks=False):
                                    if depth < MAX_DEPTH and not entry.name.startswith(".") and entry.name.casefold() not in SKIP_DIRS:
                                        stack.append((path, depth + 1))
                                    continue
                                if entry.name.lower() != "skill.md" or not entry.is_file(follow_symlinks=False):
                                    continue
                                try:
                                    # On Windows DirEntry.stat may report st_ino=0;
                                    # Path.lstat obtains the actual file identity.
                                    info = path.lstat()
                                    identity = (info.st_dev, info.st_ino) if info.st_ino else (_key(path),)
                                    key = _key(path)
                                    if key in seen_paths or identity in seen_files:
                                        skipped += 1
                                        continue
                                    if info.st_size > MAX_SKILL_BYTES:
                                        skipped += 1
                                        continue
                                    old = previous.get(key)
                                    if old and old["mtime"] == info.st_mtime_ns and old["size"] == info.st_size:
                                        record = dict(old)
                                        record.update(available=1, source=source, editable=int(source == "yingxu" and info.st_nlink == 1))
                                    else:
                                        _raw, content, etag = _read(path)
                                        record = self._record(path, source, content, etag, old)
                                    records.append(record)
                                    seen_paths.add(key)
                                    seen_files.add(identity)
                                except (OSError, UserError) as exc:
                                    skipped += 1
                                    if len(errors) < 20:
                                        errors.append(f"{path.name}：{exc}")
                    except (OSError, UserError) as exc:
                        skipped += 1
                        if len(errors) < 20:
                            errors.append(f"{folder.name}：{exc}")
                if stack or len(records) >= MAX_SKILLS or visits >= MAX_SCAN_ENTRIES:
                    truncated = True
            with self.store.lock, self.store.connection() as db:
                db.execute("UPDATE yx_skills SET available=0")
                for record in records:
                    self._upsert(db, record)
            result = self.list()
            result.update(scanned=len(records), skipped=skipped, errors=errors, truncated=truncated)
            return result

    def list(self, q="", project_id=""):
        if project_id:
            self.store.get_project(project_id)
        query = str(q or "").strip().casefold()[:300]
        with self.store.connection() as db:
            bound = {row[0] for row in db.execute("SELECT skill_id FROM yx_project_skills WHERE project_id=?", (project_id,))} if project_id else set()
            rows = db.execute("SELECT * FROM yx_skills WHERE available=1 AND removed=0 ORDER BY source!='yingxu',name,id").fetchall()
        skills = [self._item(row, row["id"] in bound) for row in rows
                  if not query or all(part in (row["name"] + " " + row["description"] + " " + row["path"]).casefold() for part in query.split())]
        return {"skills": skills, "total": len(skills)}

    def get(self, skill_id):
        with self.lock:
            row = self._row(skill_id)
            path = self._trusted_path(row)
            _raw, content, etag = _read(path)
            record = self._record(path, row["source"], content, etag, row)
            with self.store.lock, self.store.connection() as db:
                self._upsert(db, record)
            result = self._item(record)
            result.update(content=content, etag=etag)
            return result

    @staticmethod
    def _content(value):
        if not isinstance(value, str) or "\x00" in value:
            raise UserError("请输入有效的技能文本。")
        try:
            raw = value.encode("utf-8")
        except UnicodeError as exc:
            raise UserError("技能文本包含无效字符。") from exc
        if len(raw) > MAX_SKILL_BYTES:
            raise UserError("技能文本最多 1 MiB。")
        return raw

    def create(self, data):
        if not isinstance(data, dict):
            raise UserError("技能资料格式无效。")
        name = str(data.get("name", "")).strip()
        if not name or len(name) > 160:
            raise UserError("技能名称需为 1 至 160 字。")
        description = str(data.get("description", "")).strip()
        if len(description) > 4000:
            raise UserError("技能简介最多 4000 字。")
        content = data.get("content", f"# {name}\n\n## 使用范围\n\n## 执行步骤\n")
        self._content(content)
        if not content.lstrip("\ufeff").startswith("---\n") and not content.lstrip("\ufeff").startswith("---\r\n"):
            content = f"---\nname: {json.dumps(name, ensure_ascii=False)}\ndescription: {json.dumps(description, ensure_ascii=False)}\n---\n\n{content}"
        raw = self._content(content)
        with self.lock:
            _check_no_links(self.root)
            with self.store.connection() as db:
                count = db.execute("SELECT count(*) FROM yx_skills WHERE available=1 AND removed=0").fetchone()[0]
            if count >= MAX_SKILLS:
                raise UserError("技能库已达到 2000 项的本地索引上限。")
            folder = self.root / (safe_name(name) + "_" + uid()[:8])
            folder.mkdir()
            path = folder / "SKILL.md"
            with path.open("xb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            record = self._record(path, "yingxu", content, hashlib.sha256(raw).hexdigest())
            with self.store.lock, self.store.connection() as db:
                self._upsert(db, record)
            result = self._item(record)
            result["content"] = content
            return result

    def save(self, skill_id, data):
        if not isinstance(data, dict) or not isinstance(data.get("etag"), str):
            raise UserError("保存技能需要原版本 etag。")
        raw = self._content(data.get("content"))
        with self.lock:
            row = self._row(skill_id)
            path = self._trusted_path(row, write=True)
            previous, _content, etag = _read(path)
            if etag != data["etag"]:
                raise UserError("技能已被其他程序修改。请保留当前草稿，重新打开后合并。", 409)
            if previous.startswith(b"\xef\xbb\xbf"):
                raw = b"\xef\xbb\xbf" + raw
                if len(raw) > MAX_SKILL_BYTES:
                    raise UserError("技能文本最多 1 MiB。")
            if raw == previous:
                return self.get(skill_id)
            version_dir = _check_no_links(self.versions_root / row["id"])
            version_dir.mkdir(parents=True, exist_ok=True)
            backup = version_dir / (now().replace(":", "-") + "_" + uid()[:8] + ".md")
            with backup.open("xb") as handle:
                handle.write(previous)
                handle.flush()
                os.fsync(handle.fileno())
            temporary = path.parent / (".SKILL_" + uid() + ".tmp")
            try:
                with temporary.open("xb") as handle:
                    handle.write(raw)
                    handle.flush()
                    os.fsync(handle.fileno())
                self._trusted_path(row, write=True)
                if _read(path)[2] != etag:
                    raise UserError("技能在保存期间发生变化，请保留草稿后重新打开。", 409)
                os.replace(temporary, path)
            finally:
                if temporary.exists():
                    temporary.unlink()
            content = raw.decode("utf-8-sig")
            record = self._record(path, "yingxu", content, hashlib.sha256(raw).hexdigest(), row)
            with self.store.lock, self.store.connection() as db:
                self._upsert(db, record)
            result = self._item(record)
            result.update(content=content, etag=record["etag"])
            return result

    def bind(self, project_id, skill_id, bound):
        if not isinstance(bound, bool):
            raise UserError("技能绑定状态必须为 true 或 false。")
        self.store.get_project(project_id)
        row = self._row(skill_id)
        if bound:
            self._trusted_path(row)
        with self.store.lock, self.store.connection() as db:
            if bound:
                db.execute("INSERT OR IGNORE INTO yx_project_skills(project_id,skill_id,created) VALUES(?,?,?)", (project_id, skill_id, now()))
            else:
                db.execute("DELETE FROM yx_project_skills WHERE project_id=? AND skill_id=?", (project_id, skill_id))
        return {"ok": True}

    def bound_skills(self, project_id):
        self.store.get_project(project_id)
        with self.store.connection() as db:
            rows = db.execute("SELECT s.* FROM yx_skills s JOIN yx_project_skills b ON b.skill_id=s.id WHERE b.project_id=? AND s.removed=0 ORDER BY s.name,s.id", (project_id,)).fetchall()
        return [self._item(row, True) for row in rows]

    def remove(self, skill_id):
        """Remove only from YingXu. Source files and bindings remain recoverable."""
        with self.lock, self.store.lock, self.store.connection() as db:
            row = db.execute('SELECT * FROM yx_skills WHERE id=? AND removed=0', (skill_id,)).fetchone()
            if row is None:
                raise UserError('技能不存在或已在回收站。', 404)
            db.execute('UPDATE yx_skills SET removed=1,removed_at=? WHERE id=?', (now(), skill_id))
        return {'ok': True, 'kind': 'skill', 'batch_id': skill_id, 'count': 1,
                'source': row['source'], 'files_preserved': True}

    def trash(self):
        with self.store.connection() as db:
            rows = db.execute('SELECT * FROM yx_skills WHERE removed=1 AND purged=0 ORDER BY removed_at DESC,id').fetchall()
        return {'entries': [{'id': row['id'], 'batch_id': row['id'], 'target_id': row['id'],
                             'kind': 'skill', 'project_id': None, 'name': row['name'],
                             'created': row['removed_at'], 'count': 1, 'source': row['source'],
                             'editable': bool(row['editable']), 'path': row['path']}
                            for row in rows], 'total': len(rows)}

    def restore(self, skill_id):
        with self.lock, self.store.lock, self.store.connection() as db:
            row = db.execute('SELECT * FROM yx_skills WHERE id=? AND removed=1 AND purged=0', (skill_id,)).fetchone()
            if row is None:
                raise UserError('这个技能不在回收站。', 404)
            if row['recycle_started']:
                raise UserError('技能曾提交 Windows 回收操作，不能直接恢复记录。请先核对原文件和 Windows 回收站；可继续清理剩余记录。',409)
            db.execute("UPDATE yx_skills SET removed=0,removed_at='' WHERE id=?", (skill_id,))
        return {'ok': True, 'kind': 'skill', 'count': 1, 'available': bool(row['available'])}
