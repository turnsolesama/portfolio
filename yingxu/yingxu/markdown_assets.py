"""Resolve Markdown image links only to registered raster images in its project."""
from contextlib import contextmanager
import os
from pathlib import Path
import re
from urllib.parse import quote, unquote, urlencode

from .store import UserError, clean_path

RASTER_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'}
MAX_IMAGE_BYTES = 32 * 1024 * 1024


class MarkdownAssets:
    def __init__(self, store):
        self.store = store

    def _note(self, note_id):
        note = self.store.get_item(note_id)
        if note['kind'] != 'markdown':
            raise UserError('只有项目 Markdown 文稿可以引用图片附件。')
        path = self.store.resolve_item_path(note)
        root = clean_path(self.store.get_project(note['project_id'])['root'])
        if not path.is_relative_to(root) or path.stat().st_nlink > 1:
            raise UserError('图片附件只用于项目中的独立文稿。', 403)
        return note, path, root

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
