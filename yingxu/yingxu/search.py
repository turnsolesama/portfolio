"""Bounded global search of the active catalogue and registered SKILL files."""
from __future__ import annotations

import os
import json
import re
import sqlite3
import time
from contextlib import contextmanager

from .store import UserError
from .skills import MAX_SKILL_BYTES

MAX_CANDIDATES = 5000
MAX_SKILL_CANDIDATES = 2000
MAX_SKILL_READ_BYTES = 32 * 1024 * 1024
MAX_SECONDS = 2.0
MAX_SQL_STEPS = 2_000_000


class _BusySearch(Exception):
    pass


def _snippet(text, words):
    text = str(text or '')
    folded = text.casefold()
    position = next((folded.find(word.casefold()) for word in words if word.casefold() in folded), 0)
    if len(folded) != len(text) and position:
        # Casefold may expand one character (such as ß -> ss). Convert the
        # matched offset back to source coordinates before selecting a snippet.
        folded_offset = 0
        for source_offset, character in enumerate(text):
            if folded_offset >= position:
                position = source_offset
                break
            folded_offset += len(character.casefold())
    start = max(0, position - 65)
    return ('…' if start else '') + re.sub(r'\s+', ' ', text[start:start + 260]).strip() + ('…' if start + 260 < len(text) else '')


def _matches(text, words):
    folded = text.casefold()
    return all(word.casefold() in folded for word in words)


def _tag_text(value):
    try:
        tags = json.loads(value)
    except (ValueError, TypeError):
        return ''
    return '、'.join(str(tag) for tag in tags) if isinstance(tags, list) else ''


class GlobalSearch:
    def __init__(self, store, skills):
        self.store = store
        self.skills = skills

    @staticmethod
    def _request(q, limit, offset):
        if not isinstance(q, str) or len(q) > 200 or '\x00' in q:
            raise UserError('全局搜索最多输入 200 个字符。')
        try:
            limit, offset = int(limit), int(offset)
        except (ValueError, TypeError, OverflowError) as exc:
            raise UserError('搜索分页参数无效。') from exc
        if offset < 0 or offset > 100000 or limit < 1:
            raise UserError('搜索分页参数超出范围。')
        words = q.strip().split()
        if len(words) > 12:
            raise UserError('一次最多搜索 12 个关键词。')
        return q.strip(), words, min(50, limit), offset

    def search(self, q='', limit=30, offset=0):
        q, words, limit, offset = self._request(q, limit, offset)
        start = time.monotonic()
        results, warnings = [], []
        truncated = False
        skipped = 0
        scanned = {'projects': 0, 'items': 0, 'skills': 0, 'skill_bytes': 0}
        scope = {'projects': '未删除的全部项目名称与简介',
                 'items': '未删除项目文件的名称、标签、备注及已索引正文（Markdown、文本、已提取的 Word）',
                 'skills': '已注册且可用的 SKILL 名称、简介与正文',
                 'content_source': '项目正文使用最近保存或同步的索引；未保存草稿不参与搜索，外部修改后请先同步。'}

        def response():
            results.sort(key=lambda result: (result['_rank'], result['name'].casefold(), result['type'], result['id']))
            page = [{key: value for key, value in result.items() if not key.startswith('_')} for result in results[offset:offset + limit]]
            return {'q': q, 'results': page, 'total': len(results), 'total_exact': not truncated,
                    'limit': limit, 'offset': offset, 'has_more': offset + limit < len(results),
                    'truncated': truncated, 'warnings': warnings, 'scope': scope, 'scanned': scanned,
                    'elapsed_ms': round((time.monotonic() - start) * 1000, 2)}

        if not words:
            return response()

        def rank(name):
            return 0 if name.casefold() == q.casefold() else 1 if _matches(name, words) else 2

        def expired():
            return time.monotonic() - start >= MAX_SECONDS

        def limited(message):
            nonlocal truncated
            truncated = True
            if message not in warnings:
                warnings.append(message)

        @contextmanager
        def bounded_lock(lock):
            if not lock.acquire(timeout=max(0, MAX_SECONDS - (time.monotonic() - start))):
                raise _BusySearch()
            try:
                yield
            finally:
                lock.release()

        def query(sql, args=(), maximum=MAX_CANDIDATES):
            steps = 0
            def progress():
                nonlocal steps
                steps += 1000
                return int(expired() or steps >= MAX_SQL_STEPS)
            def folded(value):
                if expired():
                    limited('本次搜索达到时间上限，结果不完整，请增加关键词重试。')
                    return ''
                return str(value or '').casefold()
            try:
                with self.store.connection() as db:
                    db.execute('PRAGMA busy_timeout=200')
                    db.create_function('yx_casefold', 1, folded, deterministic=True)
                    db.create_function('yx_tags', 1, _tag_text, deterministic=True)
                    db.create_function('yx_excerpt', 1, lambda value: '' if expired() else _snippet(value, words), deterministic=True)
                    db.set_progress_handler(progress, 1000)
                    rows = [dict(row) for row in db.execute(sql, [*args, maximum + 1])]
                if len(rows) > maximum:
                    limited('匹配候选超过本次扫描上限，请增加关键词缩小范围。')
                return rows[:maximum]
            except sqlite3.OperationalError as exc:
                if not any(word in str(exc).lower() for word in ('interrupt', 'locked', 'busy')):
                    raise
                limited('本次搜索达到时间或数据库扫描上限，结果不完整，请增加关键词重试。')
                return []

        predicates = ' AND '.join('instr(yx_casefold(name||char(10)||description),yx_casefold(?))>0' for _ in words)
        projects = query('SELECT id,name,description FROM projects WHERE removed=0 AND ' + predicates + ' ORDER BY name COLLATE NOCASE,id LIMIT ?', words)
        for project in projects:
            scanned['projects'] += 1
            results.append({'type': 'project', 'id': project['id'], 'project_id': project['id'],
                            'project_name': project['name'], 'name': project['name'], 'category': None,
                            'folder_id': None, 'snippet': _snippet(project['description'], words), '_rank': rank(project['name'])})

        # Search the existing extracted-text index with literal Unicode
        # substrings, consistently with project and SKILL matching. An FTS
        # token/prefix gate would wrongly drop e.g. night within midnight.
        combined = "i.name||char(10)||yx_tags(i.tags)||char(10)||i.notes||char(10)||CASE WHEN i.kind IN ('markdown','text','docx') THEN i.search_content ELSE '' END"
        predicates = ' AND '.join('instr(yx_casefold(' + combined + '),yx_casefold(?))>0' for _ in words)
        args = list(words)
        # Extract a bounded excerpt around the first content match inside SQLite;
        # never load all document bodies into Python merely to make result cards.
        excerpt = "yx_excerpt(CASE WHEN i.kind IN ('markdown','text','docx') THEN i.search_content ELSE '' END)"
        item_sql = 'SELECT i.id,i.project_id,p.name AS project_name,i.source_id,i.name,i.kind,i.category,i.folder_id,i.path,i.updated,i.size,i.mtime,i.tags,yx_excerpt(i.notes) AS notes,' + excerpt + ' AS excerpt FROM items i JOIN projects p ON p.id=i.project_id WHERE i.removed=0 AND p.removed=0 AND (i.folder_id IS NULL OR EXISTS(SELECT 1 FROM folders f WHERE f.id=i.folder_id AND f.removed=0)) AND ' + predicates + ' ORDER BY i.name COLLATE NOCASE,i.id LIMIT ?'
        items = [] if expired() else query(item_sql, args)
        for item in items:
            if expired():
                limited('本次搜索达到时间上限，尚有匹配文件未检查；请增加关键词重试。')
                break
            scanned['items'] += 1
            try:
                # Do not reveal cached text for a path that has become an unsafe
                # link, app-data path, absent file, or unregistered source.
                with bounded_lock(self.store.lock):
                    fresh = self.store.get_item(item['id'])
                    path = self.store.resolve_item_path(fresh)
                    if path.stat().st_nlink > 1:
                        raise UserError('共享硬链接不参与全文搜索。')
                if any(str(fresh.get(key)) != str(item.get(key)) for key in ('updated', 'path', 'project_id')):
                    raise UserError('搜索期间文件记录已变化。')
            except _BusySearch:
                limited('项目索引正在变更，本次搜索未检查完全部匹配文件，请稍后重试。')
                break
            except (UserError, OSError, ValueError):
                skipped += 1
                continue
            labels = _tag_text(item['tags'])
            metadata_summary = (item['notes'] + ' ' + labels).strip()
            summary = item['excerpt'] if any(word.casefold() in item['excerpt'].casefold() for word in words) else metadata_summary or item['excerpt']
            results.append({'type': 'item', 'id': item['id'], 'project_id': item['project_id'],
                            'project_name': item['project_name'], 'name': item['name'], 'kind': item['kind'],
                            'category': item['category'], 'folder_id': item['folder_id'],
                            'snippet': _snippet(summary, words), '_rank': rank(item['name'])})

        skills = [] if expired() else query('SELECT * FROM yx_skills WHERE removed=0 AND purged=0 AND available=1 ORDER BY name COLLATE NOCASE,id LIMIT ?', maximum=MAX_SKILL_CANDIDATES)
        for skill in skills:
            if expired():
                limited('本次搜索达到时间上限，SKILL 正文尚未全部检查；请增加关键词重试。')
                break
            scanned['skills'] += 1
            metadata = skill['name'] + '\n' + skill['description']
            matched_metadata = _matches(metadata, words)
            content = ''
            try:
                with bounded_lock(self.skills.lock):
                    fresh = self.skills._row(skill['id'])
                    if not fresh['available'] or fresh['purged'] or any(str(fresh[key]) != str(skill[key]) for key in ('updated', 'path', 'source')):
                        raise UserError('技能记录正在变化。')
                    path = self.skills._trusted_path(fresh)
                    before = path.stat()
                    if before.st_nlink > 1:
                        raise UserError('共享硬链接不参与全文搜索。')
                    if not matched_metadata:
                        if before.st_size > MAX_SKILL_BYTES or scanned['skill_bytes'] + before.st_size > MAX_SKILL_READ_BYTES:
                            limited('部分 SKILL 正文超过单文件 1 MiB 或本次 32 MiB 读取上限，未完成全文搜索。')
                            continue
                        with path.open('rb') as handle:
                            opened = os.fstat(handle.fileno())
                            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino) or opened.st_nlink > 1:
                                raise UserError('技能文件已经变化。')
                            raw = handle.read(min(MAX_SKILL_BYTES + 1, MAX_SKILL_READ_BYTES - scanned['skill_bytes']))
                        scanned['skill_bytes'] += len(raw)
                        if len(raw) > MAX_SKILL_BYTES:
                            limited('部分 SKILL 正文超过单文件 1 MiB 读取上限，未完成全文搜索。')
                            continue
                        after = path.stat()
                        if after.st_nlink > 1 or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
                            raise UserError('技能文件正在变化。')
                        self.skills._trusted_path(fresh)
                        content = raw.decode('utf-8-sig')
                        if '\x00' in content:
                            raise UserError('技能文件不是可搜索文本。')
            except _BusySearch:
                limited('SKILL 库正在变更，本次全文搜索未完成，请稍后重试。')
                break
            except (UserError, OSError, UnicodeError, ValueError):
                skipped += 1
                continue
            if matched_metadata or _matches(metadata + '\n' + content, words):
                results.append({'type': 'skill', 'id': skill['id'], 'project_id': None, 'project_name': None,
                                'name': skill['name'], 'category': None, 'folder_id': None, 'source': skill['source'],
                                'snippet': _snippet(content if content else skill['description'], words), '_rank': rank(skill['name'])})

        if expired():
            limited('本次搜索达到时间上限，结果不完整，请增加关键词重试。')
        if skipped:
            limited(f'有 {skipped} 个文件或 SKILL 因路径不可用、共享链接或状态变化而未参与搜索。')
        warnings.insert(0, scope['content_source'])
        return response()
