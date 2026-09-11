"""Bounded static SVG image preview; original files are never modified.

Only sanitized output may be returned to the browser. Embed it as an <img>,
never inline HTML/object/iframe. Direct responses also require isolated CSP,
image/svg+xml and X-Content-Type-Options: nosniff. No third-party dependencies.
"""
from __future__ import annotations

import math
import re
from xml.parsers import expat
import xml.etree.ElementTree as ET

MAX_BYTES = 1024 * 1024
MAX_NODES = 2000
MAX_DEPTH = 32
MAX_ATTRIBUTES = 40
MAX_TEXT = 100000
MAX_PATH_DATA = 200000
MAX_PATH_COMMANDS = 20000
MAX_NUMBERS = 40000
MAX_COORDINATE = 1000000
MAX_DIMENSION = 8192
MAX_PIXELS = 40000000
MAX_GRADIENTS = 64
MAX_REFERENCES = 256
MAX_REFERENCE_DEPTH = 8
SVG_CSP = "default-src 'none'; sandbox; base-uri 'none'; form-action 'none'"
SVG_NAMESPACE = 'http://www.w3.org/2000/svg'
XLINK_NAMESPACE = 'http://www.w3.org/1999/xlink'
XML_NAMESPACE = 'http://www.w3.org/XML/1998/namespace'


class SvgPreviewError(ValueError):
    """The document is unsupported or exceeds the safe static subset."""


_NUMBER = r'[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?'
_TOKEN = re.compile(_NUMBER)
_LENGTH = re.compile(r'(' + _NUMBER + r')(px|pt|pc|mm|cm|in|%)?')
_ID = re.compile(r'[A-Za-z_][A-Za-z0-9_.:-]{0,127}')
_LOCAL_URL = re.compile(r'url\(\s*[\'"]?#([A-Za-z_][A-Za-z0-9_.:-]{0,127})[\'"]?\s*\)')
_TRANSFORM = re.compile(r'(matrix|translate|scale|rotate|skewX|skewY)\s*\(([^()]*)\)')
_SHAPES = {'path', 'rect', 'circle', 'ellipse', 'line', 'polyline', 'polygon'}
_GRADIENTS = {'linearGradient', 'radialGradient'}
_ELEMENTS = {'svg', 'g', 'defs', 'text', 'tspan', 'title', 'desc', 'stop'} | _SHAPES | _GRADIENTS
_PRESENTATION = {
    'fill', 'stroke', 'color', 'fill-opacity', 'stroke-opacity', 'opacity',
    'fill-rule', 'stroke-width', 'stroke-linecap', 'stroke-linejoin',
    'stroke-miterlimit', 'stroke-dasharray', 'stroke-dashoffset',
    'font-family', 'font-size', 'font-weight', 'font-style', 'text-anchor',
    'dominant-baseline', 'alignment-baseline', 'letter-spacing', 'word-spacing',
    'text-decoration', 'visibility', 'display', 'vector-effect',
    'stop-color', 'stop-opacity',
}
_SPECIFIC = {
    'svg': {'width', 'height', 'viewBox', 'preserveAspectRatio', 'version'},
    'g': set(), 'defs': set(),
    'path': {'d'},
    'rect': {'x', 'y', 'width', 'height', 'rx', 'ry'},
    'circle': {'cx', 'cy', 'r'},
    'ellipse': {'cx', 'cy', 'rx', 'ry'},
    'line': {'x1', 'y1', 'x2', 'y2'},
    'polyline': {'points'}, 'polygon': {'points'},
    'text': {'x', 'y', 'dx', 'dy', 'rotate', 'textLength', 'lengthAdjust'},
    'tspan': {'x', 'y', 'dx', 'dy', 'rotate', 'textLength', 'lengthAdjust'},
    'title': set(), 'desc': set(),
    'linearGradient': {'x1', 'y1', 'x2', 'y2', 'gradientUnits', 'gradientTransform', 'spreadMethod', 'href'},
    'radialGradient': {'cx', 'cy', 'r', 'fx', 'fy', 'fr', 'gradientUnits', 'gradientTransform', 'spreadMethod', 'href'},
    'stop': {'offset'},
}
_ENUMS = {
    'fill-rule': {'nonzero', 'evenodd'}, 'stroke-linecap': {'butt', 'round', 'square'},
    'stroke-linejoin': {'miter', 'round', 'bevel'}, 'font-style': {'normal', 'italic', 'oblique'},
    'text-anchor': {'start', 'middle', 'end'},
    'dominant-baseline': {'auto', 'alphabetic', 'middle', 'central', 'hanging', 'text-before-edge', 'text-after-edge', 'ideographic', 'mathematical'},
    'alignment-baseline': {'auto', 'baseline', 'before-edge', 'text-before-edge', 'middle', 'central', 'after-edge', 'text-after-edge', 'ideographic', 'alphabetic', 'hanging', 'mathematical'},
    'text-decoration': {'none', 'underline', 'overline', 'line-through'},
    'visibility': {'visible', 'hidden', 'collapse'}, 'display': {'inline', 'none'},
    'vector-effect': {'none', 'non-scaling-stroke'},
    'gradientUnits': {'userSpaceOnUse', 'objectBoundingBox'},
    'spreadMethod': {'pad', 'reflect', 'repeat'},
    'lengthAdjust': {'spacing', 'spacingAndGlyphs'}, 'version': {'1.0', '1.1', '2.0'},
}
_COMMON = {'id', 'class', 'style', 'transform'} | _PRESENTATION


def _reject(message):
    raise SvgPreviewError(message + '；可用原设计软件打开或导出 PNG。')


class _Sanitizer:
    def __init__(self):
        self.stack = []
        self.root = None
        self.node_count = self.text_count = self.path_count = self.number_count = 0
        self.path_commands = 0
        self.gradient_count = 0
        self.ids = {}
        self.references = []
        self.gradient_links = {}
        self.transform_factors = []

    def number(self, value):
        self.number_count += 1
        if self.number_count > MAX_NUMBERS:
            _reject('SVG 数字/路径复杂度超过预览上限')
        number = float(value)
        if not math.isfinite(number) or abs(number) > MAX_COORDINATE:
            _reject('SVG 坐标超出安全范围')
        return number

    def numbers(self, value, minimum=1, maximum=1000):
        values = []
        cursor = 0
        for match in _TOKEN.finditer(value):
            if value[cursor:match.start()].strip(' ,\t\r\n'):
                _reject('SVG 数值格式暂不支持')
            values.append(self.number(match.group()))
            if len(values) > maximum:
                _reject('SVG 数值列表过长')
            cursor = match.end()
        if value[cursor:].strip(' ,\t\r\n') or not minimum <= len(values) <= maximum:
            _reject('SVG 数值格式暂不支持')
        return values

    def length(self, value, nonnegative=False, dimension=False):
        match = _LENGTH.fullmatch(value)
        if not match:
            _reject('SVG 长度单位暂不支持')
        number = self.number(match[1])
        if nonnegative and number < 0:
            _reject('SVG 长度不能为负值')
        unit = match[2] or ''
        pixels = number * {'in': 96, 'cm': 96 / 2.54, 'mm': 96 / 25.4, 'pt': 96 / 72, 'pc': 16}.get(unit, 1)
        if dimension and (number <= 0 or (unit == '%' and number > 100) or abs(pixels) > MAX_DIMENSION):
            _reject('SVG 显示尺寸超过 8192 像素限制')
        return pixels if unit != '%' else None

    def reference(self, target, node, gradient_link=False):
        if not _ID.fullmatch(target):
            _reject('SVG 仅支持文档内渐变引用')
        self.references.append((target, node))
        if len(self.references) > MAX_REFERENCES:
            _reject('SVG 渐变引用数量过多')
        if gradient_link:
            self.gradient_links[id(node)] = target

    def color(self, value, node, paint=False):
        match = _LOCAL_URL.fullmatch(value)
        if match:
            if not paint:
                _reject('此 SVG 颜色属性不能引用其他内容')
            self.reference(match[1], node)
            return 'url(#' + match[1] + ')'
        if re.fullmatch(r'#[0-9a-fA-F]{3,4}|#[0-9a-fA-F]{6}|#[0-9a-fA-F]{8}', value):
            return value
        if re.fullmatch(r'[A-Za-z]{1,32}', value):
            return value
        match = re.fullmatch(r'(rgb|rgba|hsl|hsla)\(([0-9.,%+\-\s]+)\)', value)
        if match:
            parts = [part for part in re.split(r'[\s,]+', match[2].strip()) if part]
            expected = 4 if match[1].endswith('a') else 3
            if len(parts) == expected:
                for part in parts:
                    number = self.numbers(part.rstrip('%'), maximum=1)[0]
                    if not 0 <= number <= 360:
                        _reject('SVG 颜色值超出范围')
                return value
        _reject('SVG 仅支持静态颜色和文档内渐变')

    def transform(self, value):
        cursor = 0
        count = 0
        factor = 1.0
        for match in _TRANSFORM.finditer(value):
            if value[cursor:match.start()].strip(' ,\t\r\n'):
                _reject('SVG 变换格式暂不支持')
            name = match[1]
            args = self.numbers(match[2], maximum=6)
            allowed = {'matrix': {6}, 'translate': {1, 2}, 'scale': {1, 2}, 'rotate': {1, 3}, 'skewX': {1}, 'skewY': {1}}
            if len(args) not in allowed[name]:
                _reject('SVG 变换参数数量错误')
            if name == 'matrix':
                factor *= max(1, abs(args[0]) + abs(args[2]), abs(args[1]) + abs(args[3]))
            elif name == 'scale':
                factor *= max(1, *(abs(number) for number in args))
            elif name.startswith('skew'):
                if abs(args[0]) > 80:
                    _reject('SVG 倾斜变换超过安全范围')
                factor *= 1 + abs(math.tan(math.radians(args[0])))
            count += 1
            if count > 16 or factor > 10000:
                _reject('SVG 叠加变换过于复杂')
            cursor = match.end()
        if not count or value[cursor:].strip(' ,\t\r\n'):
            _reject('SVG 变换格式暂不支持')
        return factor

    def attribute(self, name, value, node):
        if len(value) > MAX_PATH_DATA or any(ord(char) < 32 and char not in '\t\n\r' for char in value):
            _reject('SVG 属性超过安全限制')
        value = value.strip()
        if name in _ENUMS:
            if value not in _ENUMS[name]:
                _reject('SVG 属性值暂不支持')
        elif name == 'id':
            if not _ID.fullmatch(value) or value in self.ids:
                _reject('SVG 标识无效或重复')
            self.ids[value] = node
        elif name == 'class':
            if len(value) > 256 or not re.fullmatch(r'[A-Za-z0-9_\-\s]*', value):
                _reject('SVG class 格式暂不支持')
        elif name in ('fill', 'stroke', 'color', 'stop-color'):
            value = self.color(value, node, name in ('fill', 'stroke'))
        elif name in ('opacity', 'fill-opacity', 'stroke-opacity', 'stop-opacity', 'offset'):
            percent = value.endswith('%')
            number = self.numbers(value[:-1] if percent else value, maximum=1)[0]
            if not 0 <= number <= (100 if percent else 1):
                _reject('SVG 透明度或渐变位置超出范围')
        elif name == 'font-family':
            if len(value) > 256 or not re.fullmatch(r'[\w\s,\'"\-]+', value, flags=re.UNICODE):
                _reject('SVG 只支持本地字体名称')
        elif name == 'font-weight':
            if value not in {'normal', 'bold', 'bolder', 'lighter'}:
                number = self.numbers(value, maximum=1)[0]
                if not 1 <= number <= 1000:
                    _reject('SVG 字重超出范围')
        elif name == 'stroke-dasharray':
            if value != 'none':
                # Tiny dashes can amplify browser work despite short input and
                # bounded coordinates. ViewBox/transform/pathLength make a
                # scalar minimum insufficient, so the light preview omits this.
                _reject('轻量 SVG 预览暂不支持虚线描边')
        elif name in ('stroke-width', 'font-size'):
            pixels = self.length(value, nonnegative=True)
            if pixels is None or pixels > 4096:
                _reject('SVG 字号或线宽超过轻量预览范围')
        elif name == 'stroke-miterlimit':
            if not 1 <= self.numbers(value, maximum=1)[0] <= 100:
                _reject('SVG 线条尖角范围过大')
        elif name == 'viewBox':
            numbers = self.numbers(value, minimum=4, maximum=4)
            if numbers[2] <= 0 or numbers[3] <= 0:
                _reject('SVG viewBox 尺寸无效')
        elif name == 'preserveAspectRatio':
            if not re.fullmatch(r'(?:none|x(?:Min|Mid|Max)Y(?:Min|Mid|Max)(?:\s+(?:meet|slice))?)', value):
                _reject('SVG 比例设置暂不支持')
        elif name == 'd':
            self.path_count += len(value)
            self.path_commands += len(re.findall('[MmZzLlHhVvCcSsQqTtAa]', value))
            if self.path_count > MAX_PATH_DATA or self.path_commands > MAX_PATH_COMMANDS:
                _reject('SVG 路径数据超过预览上限')
            if value and (value[0] not in 'Mm' or re.sub(_NUMBER, '', value).strip('MmZzLlHhVvCcSsQqTtAa ,\t\r\n')):
                _reject('SVG 路径数据格式无效')
            # Count every numeric parameter without sending anything to a renderer.
            for match in _TOKEN.finditer(value):
                self.number(match.group())
        elif name == 'points':
            if len(self.numbers(value, minimum=2, maximum=20000)) % 2:
                _reject('SVG 图形坐标必须成对')
        elif name in ('transform', 'gradientTransform'):
            factor = self.transform(value)
            inherited = self.transform_factors[-1] if self.transform_factors else 1
            if inherited * factor > 10000:
                _reject('SVG 嵌套缩放超过安全范围')
        elif name == 'href':
            if not value.startswith('#'):
                _reject('SVG 不允许外部文件、网络或 data 引用')
            self.reference(value[1:], node, gradient_link=True)
        elif name == 'space':
            if value not in ('default', 'preserve'):
                _reject('SVG 空白处理方式无效')
        elif name in ('x', 'y', 'dx', 'dy', 'rotate') and node.tag in ('text', 'tspan'):
            if name != 'rotate' and _LENGTH.fullmatch(value):
                self.length(value)
            else:
                self.numbers(value, maximum=1000)
        else:
            self.length(value, nonnegative=name in {'width', 'height', 'r', 'rx', 'ry', 'fr', 'textLength'},
                        dimension=node.tag == 'svg' and name in ('width', 'height'))
        return value

    def start(self, full_name, attributes):
        namespace, separator, name = full_name.rpartition('|')
        if not separator:
            name = full_name
        if namespace not in ('', SVG_NAMESPACE) or name not in _ELEMENTS:
            _reject('SVG 包含不支持的元素（脚本、动画、滤镜、引用或复杂内容）')
        self.node_count += 1
        if self.node_count > MAX_NODES or len(self.stack) >= MAX_DEPTH or len(attributes) > MAX_ATTRIBUTES:
            _reject('SVG 节点、层级或属性数量超过预览上限')
        if not self.stack:
            if name != 'svg' or self.root is not None:
                _reject('文件不是单个 SVG 文档')
        else:
            parent = self.stack[-1].tag
            if name == 'svg' or parent in ('title', 'desc'):
                _reject('SVG 嵌套文档或文本结构暂不支持')
            if name == 'stop' and parent not in _GRADIENTS:
                _reject('SVG 渐变色标位置无效')
            if name == 'tspan' and parent not in ('text', 'tspan'):
                _reject('SVG 文字片段位置无效')
            if parent in _GRADIENTS and name not in ('stop', 'title', 'desc'):
                _reject('SVG 渐变包含不支持内容')
            if parent in _SHAPES | {'stop'} and name not in ('title', 'desc'):
                _reject('SVG 图形包含不支持的嵌套内容')
            if parent in ('text', 'tspan') and name not in ('tspan', 'title', 'desc'):
                _reject('SVG 文本包含不支持内容')
        if name in _GRADIENTS:
            self.gradient_count += 1
            if self.gradient_count > MAX_GRADIENTS:
                _reject('SVG 渐变数量超过预览上限')
        node = ET.Element(name)
        if self.stack:
            self.stack[-1].append(node)
        else:
            self.root = node
            node.set('xmlns', SVG_NAMESPACE)
        pending_style = None
        factor = 1
        for full_attr, value in attributes.items():
            attr_namespace, attr_separator, attr = full_attr.rpartition('|')
            if not attr_separator:
                attr = full_attr
            if attr_namespace == XML_NAMESPACE and attr == 'space':
                node.set('{'+XML_NAMESPACE+'}space', self.attribute('space', value, node))
                continue
            if attr_namespace not in ('', XLINK_NAMESPACE) or (attr_namespace == XLINK_NAMESPACE and attr != 'href'):
                _reject('SVG 包含不支持的命名空间属性')
            if attr not in _COMMON | _SPECIFIC[name] or (attr == 'href' and name not in _GRADIENTS):
                _reject('SVG 包含不支持的属性（事件、外链或复杂样式）')
            if attr == 'style':
                pending_style = value
                continue
            if attr in node.attrib:
                _reject('SVG 属性重复')
            node.set(attr, self.attribute(attr, value, node))
            if attr in ('transform', 'gradientTransform'):
                factor *= self.transform(value)
        if pending_style:
            if len(pending_style) > 4096 or any(char in pending_style for char in '\\{}@!/*'):
                _reject('SVG 样式包含不支持的 CSS 语法')
            for declaration in pending_style.split(';'):
                if not declaration.strip():
                    continue
                prop, separator, value = declaration.partition(':')
                prop = prop.strip()
                if not separator or prop not in _PRESENTATION:
                    _reject('SVG 只支持静态颜色、线条和文字样式')
                node.set(prop, self.attribute(prop, value.strip(), node))
        inherited = self.transform_factors[-1] if self.transform_factors else 1
        if factor * inherited > 10000:
            _reject('SVG 嵌套缩放超过安全范围')
        self.transform_factors.append(factor * inherited)
        self.stack.append(node)

    def end(self, _name):
        self.stack.pop()
        self.transform_factors.pop()

    def text(self, value):
        self.text_count += len(value)
        if self.text_count > MAX_TEXT:
            _reject('SVG 文字超过预览上限')
        if not self.stack:
            if value.strip():
                _reject('SVG 根节点之外存在文本')
            return
        node = self.stack[-1]
        if node.tag not in ('text', 'tspan', 'title', 'desc'):
            if value.strip():
                _reject('SVG 非文字节点包含文本')
            return
        if len(node):
            child = node[-1]
            child.tail = (child.tail or '') + value
        else:
            node.text = (node.text or '') + value

    def finish(self):
        if self.root is None:
            _reject('SVG 文档为空')
        for target, _node in self.references:
            referenced = self.ids.get(target)
            if referenced is None or referenced.tag not in _GRADIENTS:
                _reject('SVG 引用不存在或不是受支持的渐变')
        for node in self.ids.values():
            seen = set()
            cursor = node
            while id(cursor) in self.gradient_links:
                if id(cursor) in seen or len(seen) >= MAX_REFERENCE_DEPTH:
                    _reject('SVG 渐变循环或引用链过长')
                seen.add(id(cursor))
                cursor = self.ids[self.gradient_links[id(cursor)]]
        # Canonical pixel dimensions also bound standalone SVG rasterization.
        width = self.length(self.root.get('width', '300'), dimension=True)
        height = self.length(self.root.get('height', '150'), dimension=True)
        if width is not None and height is not None and width * height > MAX_PIXELS:
            _reject('SVG 显示面积超过 4000 万像素限制')
        result = ET.tostring(self.root, encoding='utf-8', xml_declaration=True)
        if len(result) > MAX_BYTES:
            _reject('SVG 净化后体积超过 1 MiB')
        return result


def sanitize_svg(raw: bytes) -> bytes:
    """Parse and rebuild a bounded, inert SVG subset, or raise SvgPreviewError.

    This never reads URLs, opens files, invokes a browser, or loads an SVG engine.
    Callers must read at most MAX_BYTES + 1 from an authorized verified handle.
    """
    if not isinstance(raw, bytes):
        raise SvgPreviewError('SVG 预览只接受已读取的文件字节。')
    if not raw or len(raw) > MAX_BYTES:
        raise SvgPreviewError('SVG 文件为空或超过 1 MiB 预览限制。')
    sanitizer = _Sanitizer()
    parser = expat.ParserCreate(namespace_separator='|')
    parser.buffer_text = True
    parser.StartElementHandler = sanitizer.start
    parser.EndElementHandler = sanitizer.end
    parser.CharacterDataHandler = sanitizer.text
    def forbidden(*_args):
        _reject('SVG 不支持 DTD、实体声明或处理指令')
    parser.StartDoctypeDeclHandler = forbidden
    parser.EntityDeclHandler = forbidden
    parser.ExternalEntityRefHandler = forbidden
    parser.UnparsedEntityDeclHandler = forbidden
    parser.SkippedEntityHandler = forbidden
    parser.ProcessingInstructionHandler = forbidden
    try:
        parser.Parse(raw, True)
        return sanitizer.finish()
    except (expat.ExpatError, OverflowError, RecursionError) as error:
        raise SvgPreviewError('SVG XML 无法安全解析；请用原设计软件打开。') from error
