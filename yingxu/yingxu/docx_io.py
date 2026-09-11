"""Conservative DOCX text preview/editing with no dependency or disk writes.

Only direct, ordinary body paragraphs can be edited. Changed paragraphs retain
their paragraph properties and existing run properties. All other XML bytes and all
other ZIP member payloads are preserved. This is not a Word layout editor.
"""

from __future__ import annotations

import copy
import base64
import posixpath
from urllib.parse import unquote
from contextlib import nullcontext
import io
import re
import stat
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.parsers import expat
from xml.sax.saxutils import escape

MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_MEMBER_BYTES = 64 * 1024 * 1024
MAX_XML_BYTES = 16 * 1024 * 1024
MAX_ENTRIES = 4096
MAX_COMPRESSION_RATIO = 200
MAX_XML_NODES = 250_000
MAX_XML_DEPTH = 128
MAX_PARAGRAPH_TEXT = 1024 * 1024

WORD_NAMESPACES = {
    "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "http://purl.oclc.org/ooxml/wordprocessingml/main",
}
NOTICE = (
    "此处是 Word 文本预览和普通段落编辑，不是完整排版编辑器。"
    "保存时保留段落样式和混合字体，新增文字沿用改动位置的字体；"
    "未修改段落保持原样。表格、超链接、域、图片、修订等复杂内容只读，"
    "页眉页脚、批注和分页版式请用 Word 等系统应用查看。"
)


class DocxError(ValueError):
    """A document cannot safely be previewed or edited."""


@dataclass
class _Node:
    tag: str
    start: int
    open_end: int
    self_closing: bool
    parent: "_Node | None" = None
    children: list = field(default_factory=list)
    text: list = field(default_factory=list)
    close_start: int = 0
    end: int = 0
    attrs: dict = field(default_factory=dict)
    opaque_markup: bool = False


def _word(node: _Node, name: str) -> bool:
    return node.tag in {f"{ns}}}{name}" for ns in WORD_NAMESPACES}


def _encoding(data: bytes) -> str:
    if data.startswith(b"\xff\xfe") or data.startswith(b"<\x00"):
        return "utf-16-le"
    if data.startswith(b"\xfe\xff") or data.startswith(b"\x00<"):
        return "utf-16-be"
    declaration = re.match(br"\s*<\?xml\b[^>]*encoding\s*=\s*['\"]([^'\"]+)", data[:256])
    if declaration and declaration.group(1).lower() not in {b"utf-8", b"utf8"}:
        raise DocxError("此 Word 文档使用了暂不支持的 XML 编码，请用 Word 另存为 DOCX。")
    return "utf-8"


def _tag_end(data: bytes, start: int, encoding: str) -> int:
    step = 2 if encoding.startswith("utf-16") else 1
    quote = None
    markers = {char.encode(encoding): char for char in "'\">"}
    for position in range(start, len(data), step):
        char = markers.get(data[position:position + step])
        if quote:
            if char == quote:
                quote = None
        elif char in {"'", '"'}:
            quote = char
        elif char == ">":
            return position + step
    raise DocxError("Word XML 标签不完整。")


def _parse_xml(data: bytes, tree: bool = False):
    if len(data) > MAX_XML_BYTES:
        raise DocxError("Word XML 超过 16 MiB 的安全预览限制，请用系统应用打开。")
    encoding = _encoding(data)
    parser = expat.ParserCreate(namespace_separator="}")
    stack = []
    roots = []
    nodes = 0
    depth = 0

    def unsafe(*_args):
        raise DocxError("Word XML 包含 DTD 或实体声明，已拒绝处理。")

    def start(tag, attrs):
        nonlocal nodes, depth
        nodes += 1
        depth += 1
        if nodes > MAX_XML_NODES or depth > MAX_XML_DEPTH:
            raise DocxError("Word XML 结构过大或嵌套过深，已拒绝处理。")
        if not tree:
            return
        position = parser.CurrentByteIndex
        end = _tag_end(data, position, encoding)
        token = data[position:end].decode(encoding)
        node = _Node(tag, position, end, token.rstrip().endswith("/>"), stack[-1] if stack else None)
        node.attrs = attrs
        (stack[-1].children if stack else roots).append(node)
        stack.append(node)

    def end(_tag):
        nonlocal depth
        depth -= 1
        if not tree:
            return
        node = stack.pop()
        if node.self_closing:
            node.close_start = node.end = node.open_end
        else:
            node.close_start = parser.CurrentByteIndex
            node.end = _tag_end(data, node.close_start, encoding)

    def text(value):
        if tree and stack:
            stack[-1].text.append(value)

    def opaque(*_args):
        if tree and stack:
            stack[-1].opaque_markup = True

    parser.StartDoctypeDeclHandler = unsafe
    parser.EntityDeclHandler = unsafe
    parser.ExternalEntityRefHandler = unsafe
    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = text
    parser.CommentHandler = opaque
    parser.ProcessingInstructionHandler = opaque
    try:
        parser.Parse(data, True)
    except (expat.ExpatError, UnicodeError) as exc:
        raise DocxError("Word XML 无法安全解析，文件可能损坏。") from exc
    if tree:
        if len(roots) != 1:
            raise DocxError("Word 文档结构无效。")
        return roots[0], encoding
    return None


def _validated_package(handle):
    handle.seek(0, 2)
    if handle.tell() > MAX_ARCHIVE_BYTES:
        raise DocxError("DOCX 超过 128 MiB 的预览限制，请用系统应用打开。")
    handle.seek(0)
    package = zipfile.ZipFile(handle)
    try:
        entries = package.infolist()
        if len(entries) > MAX_ENTRIES:
            raise DocxError("DOCX 内部文件数量超出安全限制。")
        seen = set()
        total = 0
        for info in entries:
            name = info.filename
            normalized = name.casefold()
            parts = name.rstrip("/").split("/")
            if (not name or name.startswith("/") or "\\" in name or ":" in name
                    or any(part in {"", ".", ".."} for part in parts)
                    or normalized in seen or stat.S_ISLNK(info.external_attr >> 16)):
                raise DocxError("DOCX 包含重复或不安全的内部文件路径。")
            seen.add(normalized)
            if "vbaproject" in normalized or normalized.endswith(".vba"):
                raise DocxError("不支持包含宏的 Word 文件。")
            if info.flag_bits & 1:
                raise DocxError("暂不支持加密的 Word 文档。")
            if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                raise DocxError("DOCX 使用了不支持的压缩方式。")
            total += info.file_size
            if info.file_size > MAX_MEMBER_BYTES or total > MAX_TOTAL_BYTES:
                raise DocxError("DOCX 解压体积超出安全限制。")
            if info.file_size > 1024 * 1024 and info.file_size > max(1, info.compress_size) * MAX_COMPRESSION_RATIO:
                raise DocxError("DOCX 压缩比异常，已停止处理以避免资源耗尽。")
        exact_names = {info.filename for info in entries}
        if "word/document.xml" not in exact_names or "[Content_Types].xml" not in exact_names:
            raise DocxError("不是有效的 DOCX 文件，缺少文档正文或类型清单。")
        main = None
        for info in entries:
            if info.filename.lower().endswith((".xml", ".rels")):
                if info.file_size > MAX_XML_BYTES:
                    raise DocxError("Word XML 超过安全预览限制。")
                data = package.read(info)
                if info.filename == "[Content_Types].xml" and (
                    b"macroenabled" in data.lower() or b"vbaproject" in data.lower()
                    or "macroenabled" in data.decode(_encoding(data)).lower()
                    or "vbaproject" in data.decode(_encoding(data)).lower()
                ):
                    raise DocxError("不支持包含宏的 Word 文件。")
                if info.filename == "word/document.xml":
                    main = data
                else:
                    _parse_xml(data)
        if main is None:
            raise DocxError("DOCX 正文路径大小写不符合规范。")
        root, encoding = _parse_xml(main, tree=True)
        if not _word(root, "document"):
            raise DocxError("暂不支持此 Word 文档正文格式。")
        return package, main, root, encoding
    except Exception:
        package.close()
        raise


def _walk(node):
    yield node
    for child in node.children:
        yield from _walk(child)


def _paragraph_text(node):
    pieces = []

    def visit(current):
        if current is not node and _word(current, "p"):
            return
        if _word(current, "t") or _word(current, "delText"):
            pieces.extend(current.text)
        elif _word(current, "tab"):
            pieces.append("\t")
        elif _word(current, "br") or _word(current, "cr"):
            pieces.append("\n")
        for child in current.children:
            visit(child)

    visit(node)
    return "".join(pieces)


def _editable(node):
    if node.parent is None or not _word(node.parent, "body"):
        return False
    properties = 0
    for child in node.children:
        if _word(child, "pPr"):
            properties += 1
            if properties > 1:
                return False
        elif _word(child, "r"):
            run_properties = 0
            for run_child in child.children:
                if _word(run_child, "rPr"):
                    run_properties += 1
                    if run_properties > 1:
                        return False
                elif not any(_word(run_child, tag) for tag in ("t", "tab", "br", "cr")) or run_child.children:
                    return False
                elif _word(run_child, "br") and run_child.attrs:
                    # Page/column breaks and clear=... carry layout meaning.
                    return False
        else:
            return False
    # Editing a tracked formatting change would discard part of its meaning.
    unsafe = {"pPrChange", "rPrChange", "sectPrChange", "ins", "del", "moveFrom", "moveTo"}
    return not any(child.opaque_markup or any(_word(child, tag) for tag in unsafe) for child in _walk(node))


def _paragraphs(root):
    body = next((child for child in root.children if _word(child, "body")), None)
    if body is None:
        raise DocxError("DOCX 缺少正文。")
    return [(f"p{index:06d}", node) for index, node in enumerate(
        (node for node in _walk(body) if _word(node, "p")), start=1)]


def _open_path(path):
    path = Path(path)
    if path.suffix.lower() != ".docx":
        raise DocxError("只支持 DOCX；旧版 DOC、模板和含宏文件请用系统应用打开。")
    return path.open("rb")


def _value(node, name="val", default=""):
    if node is None:
        return default
    return next((node.attrs.get(f"{ns}}}{name}") for ns in WORD_NAMESPACES
                 if f"{ns}}}{name}" in node.attrs), default)


def _child(node, name):
    return next((child for child in node.children if _word(child, name)), None) if node else None


def _formatting(properties):
    result = {}
    if properties is None:
        return result
    for name, key in (("b", "bold"), ("i", "italic"), ("u", "underline")):
        entry = _child(properties, name)
        if entry is not None:
            result[key] = _value(entry, default="true") not in {"0", "false", "off", "none"}
    color = _value(_child(properties, "color"))
    if re.fullmatch(r"[0-9a-fA-F]{6}", color):
        result["color"] = "#" + color
    size = _value(_child(properties, "sz"))
    if size.isdigit() and 8 <= int(size) <= 144:
        result["font_size"] = int(size) / 2
    return result


def _preview(package, root):
    """A bounded semantic preview; never resolve external images or XML links."""
    styles = {}
    if "word/styles.xml" in package.namelist():
        style_root, _ = _parse_xml(package.read("word/styles.xml"), tree=True)
        for node in style_root.children:
            if _word(node, "style"):
                styles[_value(node, "styleId")] = node
    relationships = {}
    relation_path = "word/_rels/document.xml.rels"
    if relation_path in package.namelist():
        relation_root, _ = _parse_xml(package.read(relation_path), tree=True)
        for node in relation_root.children:
            relationships[node.attrs.get("Id", "")] = node.attrs
    image_cache = {}
    image_bytes = 0
    output_image_bytes = 0
    image_count = 0

    def image_preview(drawing):
        nonlocal image_bytes, output_image_bytes, image_count
        alt = next((n.attrs.get("descr") or n.attrs.get("title") or ""
                    for n in _walk(drawing) if n.tag.endswith("}docPr")), "")[:500]
        unavailable = {"alt": alt or "Word 图片", "reason": "此图片格式暂不能预览，请用 Word 查看。"}
        if image_count >= 32:
            return {**unavailable, "reason": "图片超过预览数量限制，请用 Word 查看。"}
        image_count += 1
        blip = next((n for n in _walk(drawing) if n.tag.endswith("}blip")), None)
        if blip is None:
            return unavailable
        relationship_id = next((v for k, v in blip.attrs.items() if k.endswith("}embed")), None)
        relation = relationships.get(relationship_id, {})
        if not relation or relation.get("TargetMode", "").lower() == "external":
            return {**unavailable, "reason": "外部链接图片未加载。"}
        target = unquote(relation.get("Target", ""))
        if (not relation.get("Type", "").endswith("/image") or "\\" in target
                or ":" in target or "?" in target or "#" in target):
            return unavailable
        path = posixpath.normpath(target.lstrip("/") if target.startswith("/")
                                  else posixpath.join("word", target))
        if not path.startswith("word/media/") or path not in package.namelist():
            return unavailable
        info = package.getinfo(path)
        if info.file_size > 4 * 1024 * 1024 or image_bytes + info.file_size > 8 * 1024 * 1024:
            return {**unavailable, "reason": "图片超过预览数量或体积限制，请用 Word 查看。"}
        image_bytes += info.file_size
        if path in image_cache:
            value, size = image_cache[path]
            if output_image_bytes + size > 8 * 1024 * 1024:
                return {**unavailable, "reason": "图片超过预览体积限制，请用 Word 查看。"}
            output_image_bytes += size
            return {**value, "alt": alt or "Word 图片"}
        try:
            from PIL import Image, ImageOps
        except ImportError:
            return {**unavailable, "reason": "图片预览组件不可用，请用 Word 查看。"}
        try:
            data = package.read(info)
            with Image.open(io.BytesIO(data)) as picture:
                width, height = picture.size
                mime = {"PNG": "png", "JPEG": "jpeg", "GIF": "gif", "WEBP": "webp"}.get(picture.format)
                if not mime or width * height > 40_000_000 or width < 1 or height < 1:
                    return unavailable
                picture.verify()
            # Display a small static copy. Keep all original package members intact.
            # No animation or full-resolution photo remains active in the WebView.
            with Image.open(io.BytesIO(data)) as picture:
                animated = getattr(picture, "is_animated", False)
                picture.seek(0)
                transparent = "A" in picture.getbands() or "transparency" in picture.info
                picture.draft("RGB", (1600, 1600))
                picture.thumbnail((1600, 1600), Image.Resampling.LANCZOS, reducing_gap=3)
                with ImageOps.exif_transpose(picture) as oriented:
                    with oriented.convert("RGBA" if transparent else "RGB") as preview:
                        image_output = io.BytesIO()
                        preview.save(image_output, format="PNG" if transparent else "JPEG", quality=85)
                        shown_width, shown_height = preview.size
            thumbnail = image_output.getvalue()
            size = len(thumbnail)
            if size > 4 * 1024 * 1024 or output_image_bytes + size > 8 * 1024 * 1024:
                return {**unavailable, "reason": "图片超过预览体积限制，请用 Word 查看。"}
            output_image_bytes += size
            mime = "png" if transparent else "jpeg"
            value = {"src": f"data:image/{mime};base64," + base64.b64encode(thumbnail).decode("ascii"),
                     "width": shown_width, "height": shown_height,
                     "source_width": width, "source_height": height,
                     "note": "动画仅预览首帧，原文件保留完整动画。" if animated else ""}
            image_cache[path] = (value, size)
            return {**value, "alt": alt or "Word 图片"}
        except (Image.DecompressionBombError, ValueError, OSError, SyntaxError):
            return unavailable

    paragraphs = []
    ids = {}
    for identifier, node in _paragraphs(root):
        ids[id(node)] = identifier
        properties = _child(node, "pPr")
        chain = []
        style_id = _value(_child(properties, "pStyle"))
        seen = set()
        while style_id in styles and style_id not in seen and len(chain) < 16:
            seen.add(style_id)
            chain.insert(0, styles[style_id])
            style_id = _value(_child(styles[style_id], "basedOn"))
        paragraph_properties = [_child(style, "pPr") for style in chain] + [properties]
        heading, alignment, default_run = 0, "left", {}
        for style in chain:
            style_name = _value(_child(style, "name"))
            match = re.fullmatch(r"(?:heading\s*|标题\s*)([1-6])", style_name, re.IGNORECASE)
            if match:
                heading = int(match.group(1))
            default_run.update(_formatting(_child(style, "rPr")))
        for properties_entry in paragraph_properties:
            level = _value(_child(properties_entry, "outlineLvl"))
            if level.isdigit():
                heading = int(level) + 1 if 0 <= int(level) <= 5 else 0
            align = _value(_child(properties_entry, "jc"))
            if align in {"left", "start", "center", "right", "end", "both", "distribute"}:
                alignment = {"start": "left", "end": "right", "both": "justify", "distribute": "justify"}.get(align, align)
        runs = []
        images = []
        for entry in _walk(node):
            # Text-box paragraphs have their own descriptor; don't repeat them here.
            parent = entry.parent
            nested = False
            while parent is not None and parent is not node:
                if _word(parent, "p"):
                    nested = True
                    break
                parent = parent.parent
            if nested:
                continue
            if _word(entry, "r"):
                runs.append({"text": _paragraph_text(entry), **default_run, **_formatting(_child(entry, "rPr"))})
            elif _word(entry, "drawing") or _word(entry, "pict"):
                images.append(image_preview(entry))
        editable = _editable(node)
        paragraphs.append({"id": identifier, "text": _paragraph_text(node), "editable": editable,
                           "heading_level": heading, "alignment": alignment, "runs": runs, "images": images,
                           "readonly_reason": "" if editable else "表格、图片、链接或其他复杂段落保留原样，请用 Word 编辑。"})

    def blocks(parent):
        result = []
        for node in parent.children:
            if _word(node, "p"):
                result.append({"kind": "paragraph", "id": ids[id(node)]})
            elif _word(node, "tbl"):
                rows = []
                for row in node.children:
                    if not _word(row, "tr"):
                        continue
                    cells = []
                    for cell in row.children:
                        if not _word(cell, "tc"):
                            continue
                        prop = _child(cell, "tcPr")
                        span = _value(_child(prop, "gridSpan"), default="1")
                        merge = _child(prop, "vMerge")
                        cells.append({"colspan": min(100, max(1, int(span))) if span.isdigit() else 1,
                                      "vmerge": _value(merge, default="continue") if merge is not None else "",
                                      "blocks": blocks(cell)})
                    rows.append(cells)
                result.append({"kind": "table", "rows": rows})
            elif _word(node, "altChunk"):
                result.append({"kind": "unsupported", "text": "此处含外部导入内容，请用 Word 查看。"})
            elif not any(_word(node, tag) for tag in ("pPr", "rPr", "sectPr", "tblPr", "tblGrid", "trPr", "tcPr")):
                result.extend(blocks(node))
        return result

    body = _child(root, "body")
    return paragraphs, blocks(body)


def read_docx(path, handle=None, *, structured=True):
    """Return plain text and conservative editable paragraph descriptors."""
    try:
        with (nullcontext(handle) if handle is not None else _open_path(path)) as handle:
            package, _data, root, _enc = _validated_package(handle)
            with package:
                if not structured:
                    paragraphs = [{"id": identifier, "text": _paragraph_text(node), "editable": _editable(node)}
                                  for identifier, node in _paragraphs(root)]
                    return {"paragraphs": paragraphs, "content": "\n".join(p["text"] for p in paragraphs), "notice": NOTICE}
                paragraphs, blocks = _preview(package, root)
                return {"paragraphs": paragraphs, "blocks": blocks,
                        "content": "\n".join(p["text"] for p in paragraphs), "notice": NOTICE}
    except (zipfile.BadZipFile, RuntimeError, UnicodeError, OSError) as exc:
        raise DocxError("Word 文件无法读取，可能损坏、被加密或正在被占用。") from exc


def _opening(data, node, encoding):
    opening = data[node.start:node.open_end].decode(encoding)
    name = re.match(r"<([^\s/>]+)", opening).group(1)
    if node.self_closing:
        opening = opening[:-2] + ">"
    return opening, name


def _render_new_paragraph(data, node, text, encoding):
    opening, name = _opening(data, node, encoding)
    prefix = name.rsplit(":", 1)[0] + ":" if ":" in name else ""
    properties = next((child for child in node.children if _word(child, "pPr")), None)
    run = next((child for child in node.children if _word(child, "r")), None)
    pieces = [opening.encode(encoding)]
    if properties:
        pieces.append(data[properties.start:properties.end])
    if run:
        run_opening, run_name = _opening(data, run, encoding)
        run_prefix = run_name.rsplit(":", 1)[0] + ":" if ":" in run_name else ""
        pieces.append(run_opening.encode(encoding))
        run_properties = next((child for child in run.children if _word(child, "rPr")), None)
        if run_properties:
            pieces.append(data[run_properties.start:run_properties.end])
    else:
        run_name = prefix + "r"
        run_prefix = prefix
        pieces.append(f"<{run_name}>".encode(encoding))
    for part in re.split(r"([\n\t])", text):
        if part == "\n":
            rendered = f"<{run_prefix}br/>"
        elif part == "\t":
            rendered = f"<{run_prefix}tab/>"
        else:
            rendered = f'<{run_prefix}t xml:space="preserve">{escape(part)}</{run_prefix}t>'
        pieces.append(rendered.encode(encoding))
    pieces.append(f"</{run_name}></{name}>".encode(encoding))
    return b"".join(pieces)


def _render_run(data, run, text, encoding):
    opening, name = _opening(data, run, encoding)
    prefix = name.rsplit(":", 1)[0] + ":" if ":" in name else ""
    pieces = [opening.encode(encoding)]
    properties = _child(run, "rPr")
    if properties:
        pieces.append(data[properties.start:properties.end])
    for part in re.split(r"([\n\t])", text):
        if part == "\n":
            value = f"<{prefix}br/>"
        elif part == "\t":
            value = f"<{prefix}tab/>"
        else:
            value = f'<{prefix}t xml:space="preserve">{escape(part)}</{prefix}t>'
        pieces.append(value.encode(encoding))
    pieces.append(f"</{name}>".encode(encoding))
    return b"".join(pieces)


def _render_paragraph(data, node, text, encoding):
    """Keep all run formatting, assigning inserted text to its edit position.

    Use a linear common-prefix/suffix replacement, not an unbounded text diff.
    Runs outside the changed range retain their original XML bytes exactly.
    """
    runs = [child for child in node.children if _word(child, "r")]
    if not runs:
        return _render_new_paragraph(data, node, text, encoding)
    original = _paragraph_text(node)
    prefix = 0
    while prefix < min(len(original), len(text)) and original[prefix] == text[prefix]:
        prefix += 1
    suffix = 0
    while (suffix < min(len(original) - prefix, len(text) - prefix)
           and original[len(original) - suffix - 1] == text[len(text) - suffix - 1]):
        suffix += 1
    end = len(original) - suffix
    inserted = text[prefix:len(text) - suffix if suffix else len(text)]
    offset = 0
    anchor = None
    updates = []
    for index, run in enumerate(runs):
        before = _paragraph_text(run)
        stop = offset + len(before)
        # At a run boundary, typing continues the preceding run's formatting.
        if anchor is None and (stop > prefix or (stop == prefix and prefix == end) or index == len(runs) - 1):
            anchor = index
        left = before[:max(0, min(len(before), prefix - offset))]
        right = before[max(0, min(len(before), end - offset)):]
        after = left + (inserted if anchor == index else "") + right
        if before != after:
            updates.append((run.start, run.end, _render_run(data, run, after, encoding)))
        offset = stop
    pieces, cursor = [], node.start
    for start, stop, value in updates:
        pieces.extend((data[cursor:start], value))
        cursor = stop
    pieces.append(data[cursor:node.end])
    return b"".join(pieces)


def edit_docx(path, edits, handle=None):
    """Return a new DOCX byte string; callers must manage backup/etag/atomic save.

    Paragraph IDs are valid only for the corresponding read/etag. Unknown IDs,
    duplicate edits and any attempt to edit complex content are rejected.
    """
    if not isinstance(edits, list):
        raise DocxError("Word 段落修改必须是列表。")
    try:
        with (nullcontext(handle) if handle is not None else _open_path(path)) as handle:
            package, data, root, encoding = _validated_package(handle)
            with package:
                paragraphs = dict(_paragraphs(root))
                seen = set()
                replacements = []
                total_text = 0
                for edit in edits:
                    if not isinstance(edit, dict) or not isinstance(edit.get("id"), str) or not isinstance(edit.get("text"), str):
                        raise DocxError("Word 段落修改缺少有效的 id 或 text。")
                    identifier, text = edit["id"], edit["text"]
                    if identifier in seen:
                        raise DocxError("不能重复修改同一 Word 段落。")
                    seen.add(identifier)
                    node = paragraphs.get(identifier)
                    if node is None:
                        raise DocxError("Word 段落已变化或不存在，请重新打开文档。")
                    if not _editable(node):
                        raise DocxError("该段落包含表格或复杂 Word 内容，只能在系统应用中编辑。")
                    if len(text) > MAX_PARAGRAPH_TEXT or any(
                        not (char in "\t\n\r" or 0x20 <= ord(char) <= 0xD7FF
                             or 0xE000 <= ord(char) <= 0xFFFD or 0x10000 <= ord(char) <= 0x10FFFF)
                        for char in text
                    ):
                        raise DocxError("段落过长或包含 XML 不支持的字符。")
                    total_text += len(text)
                    if total_text > MAX_XML_BYTES:
                        raise DocxError("本次 Word 修改内容超出安全限制。")
                    text = text.replace("\r\n", "\n").replace("\r", "\n")
                    if text != _paragraph_text(node):
                        replacements.append((node.start, node.end, _render_paragraph(data, node, text, encoding)))
                if not replacements:
                    handle.seek(0)
                    return handle.read()
                pieces = []
                cursor = 0
                for start, end, value in sorted(replacements):
                    pieces.extend((data[cursor:start], value))
                    cursor = end
                pieces.append(data[cursor:])
                updated = b"".join(pieces)
                # Enforce size and verify namespace/escaping before returning bytes.
                _parse_xml(updated)
                output = io.BytesIO()
                with zipfile.ZipFile(output, "w") as result:
                    result.comment = package.comment
                    for info in package.infolist():
                        payload = updated if info.filename == "word/document.xml" else package.read(info)
                        result.writestr(copy.copy(info), payload)
                return output.getvalue()
    except (zipfile.BadZipFile, RuntimeError, UnicodeError, OSError) as exc:
        raise DocxError("Word 文件无法安全编辑，可能损坏、被加密或正在被占用。") from exc
