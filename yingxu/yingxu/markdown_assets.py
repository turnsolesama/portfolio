"""Resolve Markdown image links only to registered raster images in its project."""
from contextlib import contextmanager
import os
from pathlib import Path
import re
from urllib.parse import quote, unquote, urlencode, urlsplit

from .store import UserError, clean_path

RASTER_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'}
MAX_IMAGE_BYTES = 32 * 1024 * 1024


class MarkdownAssets:
    def __init__(self, store):
        self.store = store

    def _note(self, note_id):
        note = self.store.get_item(note_id)
        if note['kind'] != 'markdown':
            raise UserError('只有项目 Markdown 文稿可以引用文件附件。')
        path = self.store.resolve_item_path(note)
        root = clean_path(self.store.get_project(note['project_id'])['root'])
        if not path.is_relative_to(root) or path.stat().st_nlink > 1:
            raise UserError('附件链接只用于项目中的独立文稿。', 403)
        return note, path, root

    def _file(self, item_id, project_id, root):
        if not isinstance(item_id, str) or not re.fullmatch(r'[a-f0-9]{32}', item_id):
            raise UserError('文件链接的资源标识无效。')
        item = self.store.get_item(item_id)
        path = self.store.resolve_item_path(item)
        if item['project_id'] != project_id or not path.is_relative_to(root) or path.stat().st_nlink > 1:
            raise UserError('只能链接当前项目内已登记的独立文件。', 403)
        return item, path

    def file_link(self, note_id, item_id):
        """Build standard relative Markdown plus a stable, verified item fragment."""
        with self.store.lock:
            note, note_path, root = self._note(note_id)
            item, path = self._file(item_id, note['project_id'], root)
            relative = quote(Path(os.path.relpath(path, note_path.parent)).as_posix(), safe='/.-_~')
            destination = relative + '#yx-item=' + item['id']
            label = re.sub(r'[\r\n\t]', ' ', item['name'])[:180] or '文件'
            label = re.sub(r'([\\`*_\[\]<>])', r'\\\1', label)
            return {'relative_path': relative, 'item_id': item['id'], 'markdown': f'[{label}]({destination})'}

    def resolve_file(self, note_id, relative):
        """Resolve only registered local project files; this never opens or writes them."""
        if not isinstance(relative, str) or len(relative) > 4096 or any(ord(c) < 32 or ord(c) == 127 for c in relative):
            raise UserError('文件链接路径无效。')
        try:
            parts = urlsplit(relative)
            if re.search(r'%(?![0-9a-fA-F]{2})', parts.path):
                raise ValueError('invalid percent escape')
            decoded = unquote(parts.path, errors='strict')
        except (ValueError, UnicodeError) as error:
            raise UserError('文件链接路径无法识别。') from error
        if (parts.scheme or parts.netloc or parts.query or not decoded or decoded.startswith(('/', '\\'))
                or ':' in decoded or '\\' in decoded or any(ord(c) < 32 or ord(c) == 127 for c in decoded)):
            raise UserError('只允许当前项目内的相对文件链接。', 403)
        fragment_id = None
        if parts.fragment:
            match = re.fullmatch(r'yx-item=([a-f0-9]{32})', parts.fragment)
            if not match:
                raise UserError('文件链接的资源标识无效。')
            fragment_id = match[1]
        with self.store.lock:
            note, note_path, root = self._note(note_id)
            candidate = Path(os.path.abspath(note_path.parent / decoded))
            if not candidate.is_relative_to(root):
                raise UserError('文件链接超出当前项目。', 403)
            if fragment_id:
                item, _ = self._file(fragment_id, note['project_id'], root)
            else:
                candidate = clean_path(candidate)
                with self.store.connection() as db:
                    row = db.execute('SELECT id FROM items WHERE project_id=? AND path=? AND removed=0',
                                     (note['project_id'], str(candidate))).fetchone()
                if row is None:
                    raise UserError('链接文件尚未登记或已移入回收站。', 404)
                item, _ = self._file(row['id'], note['project_id'], root)
            return {key: item[key] for key in ('id', 'project_id', 'name', 'kind')}

    def _image(self, image_id, project_id, root):
        image = self.store.get_item(image_id)
        path = self.store.resolve_item_path(image)
        info = path.stat()
        if (image['project_id'] != project_id or not path.is_relative_to(root)
                or path.suffix.lower() not in RASTER_EXTENSIONS or info.st_nlink > 1):
            raise UserError('只能显示当前项目中已登记的独立图片附件。', 403)
        if info.st_size > MAX_IMAGE_BYTES:
            raise UserError('内嵌图片超过 32 MiB，请使用资源预览。', 413)
        return image, path

    def link(self, note_id, image_id):
        with self.store.lock:
            note, note_path, root = self._note(note_id)
            image, path = self._image(image_id, note['project_id'], root)
            relative = Path(os.path.relpath(path, note_path.parent)).as_posix()
            encoded = quote(relative, safe='/.-_~')
            alt = re.sub(r'[\[\]\\\r\n]', '', image['name'])[:180] or '截图'
            return {'relative_path': encoded, 'markdown': f'![{alt}]({encoded})',
                    'preview_url': '/api/markdown-assets/image?' + urlencode({'note': note_id, 'path': encoded})}

    @contextmanager
    def open_image(self, note_id, relative):
        if not isinstance(relative, str) or len(relative) > 4096:
            raise UserError('图片引用路径无效。')
        relative = unquote(relative)
        if (not relative or relative.startswith(('/', '\\')) or ':' in relative
                or '\\' in relative or any(ord(c) < 32 for c in relative)):
            raise UserError('只允许项目内的相对图片路径。', 403)
        with self.store.lock:
            note, note_path, root = self._note(note_id)
            path = clean_path(note_path.parent / relative)
            if not path.is_relative_to(root):
                raise UserError('图片不在当前项目中。', 403)
            with self.store.connection() as db:
                row = db.execute('SELECT id FROM items WHERE project_id=? AND path=? AND removed=0',
                                 (note['project_id'], str(path))).fetchone()
            if row is None:
                raise UserError('图片尚未登记或已移入回收站，请同步项目。', 404)
            _, path = self._image(row['id'], note['project_id'], root)
            before = path.stat()
            handle = path.open('rb')
            try:
                opened = os.fstat(handle.fileno())
                if ((before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
                        or opened.st_nlink > 1 or opened.st_size > MAX_IMAGE_BYTES):
                    raise UserError('图片文件已变化，请重试。', 409)
                clean_path(path)
            except BaseException:
                handle.close()
                raise
        try:
            yield handle
        finally:
            handle.close()
