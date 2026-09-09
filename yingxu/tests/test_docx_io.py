"""Safety and preservation tests using only synthetic temporary DOCX files."""

import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from yingxu import docx_io


W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
CONTENT_TYPES = b'''<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'''


class DocxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "中文剧本.docx"

    def make(self, body, extra=None, encoding="utf-8"):
        declaration = "UTF-8" if encoding == "utf-8" else "UTF-16"
        source = f'<?xml version="1.0" encoding="{declaration}"?><w:document xmlns:w="{W}"><w:body>{body}<w:sectPr/></w:body></w:document>'
        xml = source.encode(encoding)
        if encoding == "utf-16-le":
            xml = b"\xff\xfe" + xml
        elif encoding == "utf-16-be":
            xml = b"\xfe\xff" + xml
        with zipfile.ZipFile(self.path, "w", zipfile.ZIP_DEFLATED) as result:
            result.comment = b"preserve package comment"
            result.writestr("[Content_Types].xml", CONTENT_TYPES)
            result.writestr("word/document.xml", xml)
            result.writestr("word/media/picture.png", b"synthetic opaque bytes\x00\x01")
            result.writestr("customXml/item1.xml", b'<custom exact="yes"> untouched </custom>')
            for name, data in (extra or {}).items():
                result.writestr(name, data)
        return xml

    def read_saved(self, data):
        target = Path(self.temp.name) / "保存.docx"
        target.write_bytes(data)
        return docx_io.read_docx(target)

    def test_chinese_edit_preserves_other_payloads_and_unchanged_xml(self):
        unchanged = '<w:p w:rsidR="01020304">  <w:r><w:t>第二段 原样保留</w:t></w:r> </w:p>'
        original = self.make('<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:b/></w:rPr><w:t>第一段</w:t></w:r><w:r><w:rPr><w:i/></w:rPr><w:t>混排</w:t></w:r></w:p>' + unchanged)
        source_bytes = self.path.read_bytes()
        preview = docx_io.read_docx(self.path)
        self.assertEqual(preview["paragraphs"][0]["text"], "第一段混排")
        self.assertTrue(preview["paragraphs"][0]["editable"])
        self.assertIn("混合字体", preview["notice"])
        result = docx_io.edit_docx(self.path, [{"id": "p000001", "text": "角色 <林舟> & 雨夜\n第二行\t动作"}])
        self.assertEqual(self.path.read_bytes(), source_bytes, "module must never overwrite source")
        with zipfile.ZipFile(io.BytesIO(source_bytes)) as before, zipfile.ZipFile(io.BytesIO(result)) as after:
            self.assertEqual(before.namelist(), after.namelist())
            self.assertEqual(before.comment, after.comment)
            for name in before.namelist():
                if name != "word/document.xml":
                    self.assertEqual(before.read(name), after.read(name))
            updated = after.read("word/document.xml")
            self.assertIn(unchanged.encode(), updated)
            self.assertIn(b'<w:pPr><w:jc w:val="center"/></w:pPr>', updated)
            self.assertIn(b"<w:rPr><w:b/></w:rPr>", updated)
            self.assertNotIn(b"<w:i/>", updated)
            self.assertEqual(original[:original.index(b"<w:p>")], updated[:updated.index(b"<w:p>")])
        self.assertEqual(self.read_saved(result)["paragraphs"][0]["text"], "角色 <林舟> & 雨夜\n第二行\t动作")

    def test_unchanged_save_preserves_archive_exactly(self):
        self.make('<w:p><w:r><w:t>原文</w:t></w:r></w:p>')
        original = self.path.read_bytes()
        self.assertEqual(docx_io.edit_docx(self.path, []), original)
        self.assertEqual(docx_io.edit_docx(self.path, [{"id": "p000001", "text": "原文"}]), original)

    def test_empty_paragraphs_and_utf16_can_be_edited(self):
        for encoding in ("utf-8", "utf-16-le", "utf-16-be"):
            with self.subTest(encoding=encoding):
                self.make('<w:p/><w:p><w:r/></w:p>', encoding=encoding)
                preview = docx_io.read_docx(self.path)
                self.assertEqual([p["editable"] for p in preview["paragraphs"]], [True, True])
                result = docx_io.edit_docx(self.path, [{"id": "p000001", "text": "新段落"}, {"id": "p000002", "text": "人物"}])
                self.assertEqual(self.read_saved(result)["content"], "新段落\n人物")

    def test_complex_and_table_content_is_read_only(self):
        body = (
            '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>表格</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
            '<w:p><w:hyperlink><w:r><w:t>链接</w:t></w:r></w:hyperlink></w:p>'
            '<w:p><w:r><w:fldChar w:fldCharType="begin"/><w:t>域结果</w:t></w:r></w:p>'
            '<w:p><w:r><w:drawing/><w:t>图片旁</w:t></w:r></w:p>'
            '<w:p><w:ins><w:r><w:t>修订</w:t></w:r></w:ins></w:p>'
            '<w:sdt><w:sdtContent><w:p><w:r><w:t>控件</w:t></w:r></w:p></w:sdtContent></w:sdt>'
        )
        self.make(body)
        preview = docx_io.read_docx(self.path)
        self.assertEqual(len(preview["paragraphs"]), 6)
        self.assertTrue(all(not p["editable"] for p in preview["paragraphs"]))
        self.assertIn("表格", preview["content"])
        for paragraph in preview["paragraphs"]:
            with self.assertRaises(docx_io.DocxError):
                docx_io.edit_docx(self.path, [{"id": paragraph["id"], "text": "不可保存"}])

    def test_rejects_unknown_duplicate_ids_and_invalid_characters(self):
        self.make('<w:p/>')
        bad_inputs = [
            [{"id": "unknown", "text": "字"}],
            [{"id": "p000001", "text": "一"}, {"id": "p000001", "text": "二"}],
            [{"id": "p000001", "text": "\x00"}],
            [{"id": "p000001", "text": "\ud800"}],
            [{"id": "p000001", "text": None}],
            {},
        ]
        for edits in bad_inputs:
            with self.subTest(edits=repr(edits)), self.assertRaises(docx_io.DocxError):
                docx_io.edit_docx(self.path, edits)

    def test_rejects_dtd_entities_in_any_xml_member(self):
        for name in ("word/document.xml", "customXml/evil.xml"):
            self.make('<w:p/>')
            unsafe = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "boom">]><x>&a;</x>'
            if name == "word/document.xml":
                with zipfile.ZipFile(self.path) as source:
                    members = {n: source.read(n) for n in source.namelist()}
                members[name] = unsafe
                with zipfile.ZipFile(self.path, "w") as result:
                    for n, data in members.items():
                        result.writestr(n, data)
            else:
                with zipfile.ZipFile(self.path, "a") as result:
                    result.writestr(name, unsafe)
            with self.subTest(name=name), self.assertRaisesRegex(docx_io.DocxError, "DTD"):
                docx_io.read_docx(self.path)

    def test_rejects_zip_bombs_paths_macros_and_limits(self):
        self.make('<w:p/>', {"word/media/bomb.bin": b"0" * (2 * 1024 * 1024)})
        with self.assertRaisesRegex(docx_io.DocxError, "压缩比"):
            docx_io.read_docx(self.path)
        for name in ("../escape.xml", "word/vbaProject.bin", "word\\escape.xml"):
            self.make('<w:p/>', {name: b"bad"})
            with self.subTest(name=name), self.assertRaises(docx_io.DocxError):
                docx_io.read_docx(self.path)
        for constant, value in (("MAX_ENTRIES", 1), ("MAX_ARCHIVE_BYTES", 1), ("MAX_TOTAL_BYTES", 1), ("MAX_MEMBER_BYTES", 1), ("MAX_XML_BYTES", 1), ("MAX_XML_DEPTH", 1), ("MAX_XML_NODES", 1)):
            self.make('<w:p/>')
            with self.subTest(limit=constant), patch.object(docx_io, constant, value), self.assertRaises(docx_io.DocxError):
                docx_io.read_docx(self.path)

    def test_preserves_alternative_namespace_prefix(self):
        original = self.make('<w:p><w:r><w:t>中文</w:t></w:r></w:p>')
        with zipfile.ZipFile(self.path) as source:
            members = {n: source.read(n) for n in source.namelist()}
        members["word/document.xml"] = original.replace(b"w:", b"word:").replace(b"xmlns:w=", b"xmlns:word=")
        with zipfile.ZipFile(self.path, "w") as result:
            for name, data in members.items():
                result.writestr(name, data)
        result = docx_io.edit_docx(self.path, [{"id": "p000001", "text": "新的正文"}])
        self.assertEqual(self.read_saved(result)["content"], "新的正文")

    def test_page_breaks_and_unhandled_markup_are_read_only(self):
        self.make(
            '<w:p><w:r><w:t>分页</w:t><w:br w:type="page"/></w:r></w:p>'
            '<w:p><!-- preserve custom marker --><w:r><w:t>注记</w:t></w:r></w:p>'
            '<w:p><w:r><?custom preserve?><w:t>处理指令</w:t></w:r></w:p>'
        )
        preview = docx_io.read_docx(self.path)
        self.assertTrue(all(not p["editable"] for p in preview["paragraphs"]))

    def test_rejects_macro_content_type_and_non_docx(self):
        self.make('<w:p/>')
        with zipfile.ZipFile(self.path) as source:
            members = {name: source.read(name) for name in source.namelist()}
        members["[Content_Types].xml"] = CONTENT_TYPES.replace(
            b"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
            b"application/vnd.ms-word.document.macroEnabled.main+xml",
        )
        with zipfile.ZipFile(self.path, "w") as result:
            for name, data in members.items():
                result.writestr(name, data)
        with self.assertRaisesRegex(docx_io.DocxError, "宏"):
            docx_io.read_docx(self.path)
        unsupported = self.path.with_suffix(".docm")
        unsupported.write_bytes(self.path.read_bytes())
        with self.assertRaisesRegex(docx_io.DocxError, "DOCX"):
            docx_io.read_docx(unsupported)


if __name__ == "__main__":
    unittest.main()
