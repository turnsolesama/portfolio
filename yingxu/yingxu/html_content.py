"""Bounded HTML source viewing and inert structural previews."""
from html import escape
from .store import UserError, decode_text
from .html_preview import MAX_BYTES, preview_html


def read_html_content(opened):
    raw = opened.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise UserError('HTML 超过 1 MiB，请使用本机应用查看。', 413)
    source, encoding = decode_text(raw)
    try:
        result = preview_html(raw)
    except (UserError, ValueError) as error:
        # A bounded source remains readable even when its DOM is too complex.
        message = str(error)
        result = {'html': '<p>' + escape(message) + '</p>',
                  'notice': '静态预览未生成：' + message + ' 可切换“查看源码”。'}
    return {'format': 'html', 'content': source, 'encoding': encoding,
            'editable': False, 'etag': None, 'preview_html': result['html'],
            'notice': result['notice'] + ' 源码只读，原文件保持不变。'}
