"""Synthetic HTML only: static structure survives and active/network markup cannot."""
import unittest
from html.parser import HTMLParser

from yingxu.html_preview import preview_html, MAX_BYTES, MAX_NODES, MAX_DEPTH
from yingxu.store import UserError


class OutputAudit(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.attrs = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs.extend(attrs)


class HTMLPreviewTests(unittest.TestCase):
    def preview(self, text):
        return preview_html(text.encode('utf-8'))

    def test_structure_text_and_table_numeric_attributes(self):
        value = self.preview('<h1>标题</h1><div><p>中文<strong>加粗</strong><br>换行</p><ol start="3"><li>步骤</li></ol><table><tr><td colspan="2" rowspan="3">单元格</td></tr></table></div>')
        self.assertIn('<h1>标题</h1>', value['html'])
        self.assertIn('<strong>加粗</strong>', value['html'])
        self.assertIn('<ol start="3">', value['html'])
        self.assertIn('<td colspan="2" rowspan="3">', value['html'])
        self.assertIn('只读静态预览', value['notice'])

    def test_scripts_styles_foreign_content_and_forms_are_removed_with_contents(self):
        for tag in ('script', 'style', 'iframe', 'object', 'form', 'svg', 'math', 'template', 'canvas', 'textarea', 'select', 'noscript'):
            with self.subTest(tag=tag):
                value = self.preview(f'<p>之前</p><{tag}>secret <b>hidden</b></{tag}><p>之后</p>')['html']
                self.assertEqual(value, '<p>之前</p><p>之后</p>')

    def test_all_urls_css_event_handlers_and_dom_names_are_discarded(self):
        value = self.preview('<div id="app" name="location" class="x" style="background:url(https://bad.test/a)" onclick="attack()"><a href="javascript:attack()" target="_top" ping="/api/open" download="x">链接文字</a><p data-url="/api/secret" xmlns="evil" onmouseover="attack()">正文</p></div>')['html']
        self.assertEqual(value, '<div>链接文字<p>正文</p></div>')
        self.assertEqual(OutputAudit(value).attrs, [])

    def test_images_become_escaped_text_placeholders_without_any_url(self):
        value = self.preview('<img src="https://bad.test/x" srcset="/api/media/x 2x" alt="&lt;script&gt;你好&lt;/script&gt;"><img src="data:image/svg+xml,evil"><img src="file:///private">')['html']
        self.assertNotIn('<img', value)
        self.assertNotIn('src', value)
        self.assertIn('&lt;script&gt;你好&lt;/script&gt;', value)
        self.assertEqual(value.count('图片未加载'), 2)

    def test_head_base_meta_links_comments_and_processing_instructions_do_not_survive(self):
        value = self.preview('<!DOCTYPE html><?instruction evil?><html><head><base href="https://bad"><meta http-equiv="refresh" content="0;url=https://bad"><link rel="stylesheet" href="https://bad"><title>隐藏标题</title></head><body><!-- secret --><p>内容</p></body></html>')['html']
        self.assertEqual(value, '<p>内容</p>')

    def test_encoding_uses_existing_utf8_bom_utf16_and_gb18030_decoder(self):
        for encoding in ('utf-8-sig', 'utf-16', 'gb18030'):
            with self.subTest(encoding=encoding):
                self.assertEqual(preview_html('<h2>中文标题</h2>'.encode(encoding))['html'], '<h2>中文标题</h2>')

    def test_malformed_nesting_is_balanced_and_escaped(self):
        self.assertEqual(self.preview('<div><p>甲<b>乙</div>丙</p>')['html'], '<div><p>甲<b>乙</b></p></div>丙')
        self.assertEqual(self.preview('<p>1 &lt; 2 &amp; 3</p>')['html'], '<p>1 &lt; 2 &amp; 3</p>')

    def test_unclosed_blocked_subtree_never_leaks_raw_content(self):
        self.assertEqual(self.preview('<p>安全</p><iframe><p>隐藏<script>bad</script>')['html'], '<p>安全</p>')

    def test_numeric_attributes_are_bounded_and_repeated_or_nonnumeric_values_dropped(self):
        value = self.preview('<td colspan="99999" rowspan="-1" onclick="x">a</td><td colspan="2" colspan="3">b</td><ol start="10001"><li>c</li></ol>')['html']
        self.assertEqual(value, '<td>a</td><td colspan="2">b</td><ol><li>c</li></ol>')

    def test_byte_node_depth_and_output_limits_fail_explicitly(self):
        for raw in (b'x' * (MAX_BYTES + 1), b'<br>' * (MAX_NODES + 1), ('<div>' * (MAX_DEPTH + 1)).encode(), b'&' * 500000):
            with self.subTest(size=len(raw)):
                with self.assertRaises(UserError) as error:
                    preview_html(raw)
                self.assertEqual(error.exception.status, 413)

    def test_limits_also_count_discarded_tags_and_comments(self):
        for raw in (b'<meta>' * (MAX_NODES + 1), b'<!--x-->' * (MAX_NODES + 1), b'<form>' + b'<div>' * MAX_DEPTH):
            with self.subTest(size=len(raw)):
                with self.assertRaises(UserError):
                    preview_html(raw)

    def test_fragment_has_only_whitelisted_output_and_no_url_attributes(self):
        value = self.preview('<div><unknown><p>x</p></unknown><embed src="x"><video src="x"><source src="y"></video><button onclick="x">bad</button><pre><code>&lt;iframe src=x&gt;</code></pre></div>')['html']
        audit = OutputAudit(value)
        self.assertEqual(audit.tags, ['div', 'p', 'pre', 'code'])
        self.assertEqual(audit.attrs, [])

    def test_self_closing_tags_empty_html_and_invalid_input(self):
        self.assertEqual(self.preview('<div/><p>后续</p>')['html'], '<div></div><p>后续</p>')
        self.assertEqual(preview_html(b'')['html'], '')
        with self.assertRaises(UserError):
            preview_html('<p>not bytes</p>')


if __name__ == '__main__':
    unittest.main()
