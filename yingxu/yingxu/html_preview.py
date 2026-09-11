"""Bounded static HTML fragments. Never loads resources, executes code or writes files."""
from html import escape
from html.parser import HTMLParser

from .store import UserError, decode_text

MAX_BYTES = 1024 * 1024
MAX_NODES = 2000
MAX_DEPTH = 32
MAX_OUTPUT_BYTES = 2 * 1024 * 1024
ALLOWED = frozenset(('h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'div', 'p', 'span',
    'section', 'article', 'header', 'footer', 'main', 'aside', 'nav', 'blockquote',
    'ul', 'ol', 'li', 'dl', 'dt', 'dd', 'table', 'thead', 'tbody', 'tfoot', 'tr',
    'td', 'th', 'caption', 'pre', 'code', 'strong', 'b', 'em', 'i', 'u', 's',
    'del', 'ins', 'small', 'sub', 'sup', 'mark', 'br', 'hr', 'figure', 'figcaption'))
VOID = frozenset(('area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
                  'link', 'meta', 'param', 'source', 'track', 'wbr'))
BLOCK_CONTENT = frozenset(('head', 'script', 'style', 'iframe', 'object', 'embed',
    'form', 'button', 'input', 'select', 'textarea', 'video', 'audio', 'canvas',
    'svg', 'math', 'template', 'noscript', 'noembed', 'noframes', 'frameset',
    'frame', 'xmp', 'plaintext'))
NOTICE = ('这是只读静态预览，不是完整网页；脚本、交互、原网页样式和资源链接不加载。'
          '图片仅显示文字占位，原 HTML 文件保持不变。')


class _StaticHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.stack = []
        self.blocked = 0
        self.nodes = 0
        self.output_bytes = 0

    def _node(self):
        self.nodes += 1
        if self.nodes > MAX_NODES:
            raise UserError('HTML 内容节点超过 2000 个，无法静态预览；请查看源码或使用系统应用。', 413)

    def _append(self, text):
        self.output_bytes += len(text.encode('utf-8'))
        if self.output_bytes > MAX_OUTPUT_BYTES:
            raise UserError('HTML 预览内容过大，请查看源码或使用系统应用。', 413)
        self.parts.append(text)

    @staticmethod
    def _attributes(tag, attrs):
        # No input-provided IDs, classes, URLs, CSS, names or event handlers.
        # Limited numeric table/list structure is the only retained attribute.
        result = []
        allowed = {'colspan', 'rowspan'} if tag in ('td', 'th') else {'start'} if tag == 'ol' else set()
        seen = set()
        for key, value in attrs:
            if key not in allowed or key in seen or not value or not value.isascii() or not value.isdecimal():
                continue
            seen.add(key)
            if len(value) > 5:
                continue
            number = int(value)
            if 1 <= number <= (10000 if key == 'start' else 32):
                result.append(f' {key}="{number}"')
        return ''.join(result)

    def handle_starttag(self, tag, attrs):
        self._node()
        if tag == 'img' and not self.blocked:
            alt = next((value for key, value in attrs if key == 'alt' and value), '')
            self._append('<span>[' + escape('图片：' + alt[:300] if alt else '图片未加载', quote=True) + ']</span>')
            return
        forbidden = tag in BLOCK_CONTENT
        emitted = not self.blocked and not forbidden and tag in ALLOWED
        if tag in VOID:
            if emitted:
                self._append(f'<{tag}>')
            return
        if len(self.stack) >= MAX_DEPTH:
            raise UserError('HTML 嵌套超过 32 层，无法静态预览；请查看源码或使用系统应用。', 413)
        self.stack.append((tag, emitted, forbidden))
        if forbidden:
            self.blocked += 1
        if emitted:
            self._append(f'<{tag}{self._attributes(tag, attrs)}>')

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        index = next((i for i in range(len(self.stack) - 1, -1, -1) if self.stack[i][0] == tag), None)
        if index is None:
            return
        while len(self.stack) > index:
            name, emitted, forbidden = self.stack.pop()
            self.blocked -= int(forbidden)
            if emitted:
                self._append(f'</{name}>')

    def handle_data(self, data):
        self._node()
        if not self.blocked:
            self._append(escape(data, quote=True))

    def handle_comment(self, data):
        self._node()

    def handle_decl(self, decl):
        self._node()

    def unknown_decl(self, data):
        self._node()

    def handle_pi(self, data):
        self._node()

    def finish(self):
        self.close()
        while self.stack:
            name, emitted, _ = self.stack.pop()
            if emitted:
                self._append(f'</{name}>')
        return ''.join(self.parts)


def preview_html(raw: bytes) -> dict:
    """Return an inert HTML fragment and notice; callers supply the sandbox/CSP.

    The fragment must be shown in an iframe sandbox without allow-* tokens and
    a caller-owned CSP. The original source is never returned as markup here.
    """
    if not isinstance(raw, bytes):
        raise UserError('HTML 预览需要原始文件字节。')
    if len(raw) > MAX_BYTES:
        raise UserError('HTML 超过 1 MiB，无法静态预览；请使用系统应用。', 413)
    text, _ = decode_text(raw)
    parser = _StaticHTML()
    try:
        parser.feed(text)
        result = parser.finish()
    except (AssertionError, ValueError) as error:
        raise UserError('HTML 结构无法安全预览，请查看源码或使用系统应用。') from error
    return {'html': result, 'notice': NOTICE}
