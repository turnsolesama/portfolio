"""Read-only, bounded SVG content for explicitly opened previews."""
import base64

from .store import UserError
from .svg_preview import MAX_BYTES, sanitize_svg


def read_svg_bytes(opened):
    raw = opened.read(MAX_BYTES + 1)
    try:
        return sanitize_svg(raw)
    except ValueError as error:
        raise UserError(str(error), 415) from error


def read_svg_content(opened):
    safe = read_svg_bytes(opened)
    return {'format': 'svg', 'content': '', 'etag': None, 'editable': False,
            'preview_url': 'data:image/svg+xml;base64,' + base64.b64encode(safe).decode('ascii'),
            'notice': 'SVG 静态预览；脚本、外链、动画和复杂滤镜不支持，原文件保持不变。'}
