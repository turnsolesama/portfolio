import unittest
import xml.etree.ElementTree as ET

from yingxu.svg_preview import (sanitize_svg, preview_svg, SvgPreviewError, MAX_BYTES, MAX_NODES, MAX_PATH_COMMANDS,
                               MAX_DEPTH, MAX_NUMBERS, MAX_PATH_DATA, SVG_NAMESPACE)


def svg(body='', attributes='viewBox="0 0 100 100"'):
    return ('<svg xmlns="http://www.w3.org/2000/svg" ' + attributes + '>' + body + '</svg>').encode('utf-8')


class SvgPreviewTests(unittest.TestCase):
    def assertRejected(self, raw):
        with self.assertRaises(SvgPreviewError):
            sanitize_svg(raw)

    def test_basic_shapes_text_and_viewbox_are_preserved_in_rebuilt_output(self):
        raw = svg('<g transform="translate(10 20) scale(2)"><rect x="1" y="2" width="8" height="9" rx="2" fill="#abcdef"/>'
                  '<circle cx="20" cy="20" r="4"/><ellipse cx="30" cy="30" rx="2" ry="3"/>'
                  '<line x1="0" y1="0" x2="4" y2="5"/><polygon points="0,0 10,0 5,10"/>'
                  '<polyline points="0,0 10,10"/><path d="M 0 0 L 10 10 C 1 2 3 4 5 6 Z"/>'
                  '<text x="0" y="30">中文 &amp; &lt;script&gt;<tspan dx="2">第二段</tspan>尾部</text></g>')
        before = bytes(raw)
        clean = sanitize_svg(raw)
        self.assertEqual(raw, before)
        root = ET.fromstring(clean)
        self.assertEqual(root.tag, '{' + SVG_NAMESPACE + '}svg')
        self.assertEqual(root.attrib['viewBox'], '0 0 100 100')
        text = root.find('.//{' + SVG_NAMESPACE + '}text')
        self.assertEqual(''.join(text.itertext()), '中文 & <script>第二段尾部')
        self.assertIn(b'&lt;script&gt;', clean)
        self.assertNotIn(b'<script>', clean)

    def test_linear_radial_gradients_and_local_inheritance_are_supported(self):
        raw = svg('<defs><linearGradient id="a" x1="0%" y1="0%" x2="100%" y2="0%">'
                  '<stop offset="0%" stop-color="red"/><stop offset="100%" stop-color="#0000ff" stop-opacity=".5"/>'
                  '</linearGradient><radialGradient id="b" href="#a" cx="50%" cy="50%" r="50%"/>'
                  '</defs><rect width="100" height="100" fill="url(#b)"/>')
        clean = sanitize_svg(raw)
        self.assertIn(b'fill="url(#b)"', clean)
        self.assertIn(b'href="#a"', clean)
        self.assertIn(b'offset="100%"', clean)

    def test_xlink_local_gradient_href_is_canonicalized_without_link_namespace(self):
        raw = svg('<defs><linearGradient id="a"/><linearGradient id="b" xlink:href="#a"/></defs>',
                  'xmlns:xlink="http://www.w3.org/1999/xlink"')
        clean = sanitize_svg(raw)
        self.assertIn(b'href="#a"', clean)
        self.assertNotIn(b'xlink:', clean)

    def test_safe_inline_style_becomes_presentation_attributes_with_no_css_parser_needed(self):
        raw = svg('<text style="fill:rgb(1, 2, 3);font-family:Arial, sans-serif;font-size:12pt;font-weight:700;text-anchor:middle" x="50" y="50">测试</text>')
        clean = sanitize_svg(raw)
        self.assertNotIn(b'style=', clean)
        self.assertIn(b'font-size="12pt"', clean)
        self.assertIn(b'fill="rgb(1, 2, 3)"', clean)

    def test_utf16_and_unqualified_root_are_rebuilt_as_utf8_svg(self):
        raw = '<?xml version="1.0" encoding="UTF-16"?><svg><text>测试</text></svg>'.encode('utf-16')
        clean = sanitize_svg(raw)
        self.assertIn('测试'.encode(), clean)
        self.assertEqual(ET.fromstring(clean).tag, '{' + SVG_NAMESPACE + '}svg')

    def test_scripts_events_foreign_objects_anchors_and_images_rejected(self):
        for body in ('<script>alert(1)</script>', '<rect onclick="alert(1)"/>', '<rect ONLOAD="alert(1)"/>',
                     '<foreignObject><div>unsafe</div></foreignObject>', '<a href="https://example.com"><text>link</text></a>',
                     '<image href="data:image/png;base64,AA=="/>', '<script xmlns="http://www.w3.org/1999/xhtml"/>'):
            with self.subTest(body=body): self.assertRejected(svg(body))

    def test_dtd_entity_and_processing_instruction_are_rejected_in_any_encoding(self):
        for source in ('<!DOCTYPE svg><svg/>', '<!DOCTYPE svg SYSTEM "file:///private"><svg/>',
                       '<!DOCTYPE svg [<!ENTITY a "boom">]><svg><text>&a;</text></svg>',
                       '<?xml-stylesheet href="https://example.com/a.css"?><svg/>',
                       '<svg><?custom content?></svg>'):
            for encoding in ('utf-8', 'utf-16'):
                with self.subTest(source=source, encoding=encoding): self.assertRejected(source.encode(encoding))

    def test_external_urls_data_css_escapes_and_unsupported_styles_rejected(self):
        for body in ('<rect fill="url(https://example.com/a.svg#x)"/>',
                     '<rect fill="url(data:image/svg+xml;base64,AAAA)"/>',
                     '<rect style="fill:url(file:///x)"/>', '<rect style="fill:var(--unsafe)"/>',
                     '<rect style="fill:expression(alert(1))"/>', '<rect style="fill: red !important"/>',
                     '<rect style="fill:u\\72l(#a)"/>', '<rect style="fill:/*x*/red"/>',
                     '<rect style="background-image:url(https://example.com)"/>', '<style>rect{fill:red}</style>',
                     '<linearGradient href="https://example.com/g.svg#a"/>', '<linearGradient href="data:text/plain,xxx"/>'):
            with self.subTest(body=body): self.assertRejected(svg(body))

    def test_animation_masks_patterns_clips_and_all_use_are_rejected(self):
        for body in ('<animate attributeName="x"/>', '<set attributeName="fill"/>', '<animateTransform/>',
                     '<mask id="m"/>', '<pattern id="p"/>', '<clipPath id="c"/>', '<use href="#self" id="self"/>'):
            with self.subTest(body=body): self.assertRejected(svg(body))

    def test_invalid_duplicate_or_wrong_kind_references_rejected(self):
        for body in ('<g id="a"/><g id="a"/>', '<rect fill="url(#missing)"/>',
                     '<rect id="a"/><circle fill="url(#a)"/>', '<linearGradient id="a" href="#a"/>',
                     '<linearGradient id="a" href="#b"/><radialGradient id="b" href="#a"/>'):
            with self.subTest(body=body): self.assertRejected(svg(body))

    def test_gradient_inheritance_depth_and_count_are_bounded(self):
        chain = ''.join('<linearGradient id="g%d" href="#g%d"/>' % (index, index + 1) for index in range(9))
        self.assertRejected(svg('<defs>' + chain + '<linearGradient id="g9"/></defs>'))
        self.assertRejected(svg('<defs>' + ''.join('<linearGradient id="g%d"/>' % index for index in range(65)) + '</defs>'))

    def test_payload_node_depth_and_attribute_limits_are_enforced(self):
        self.assertRejected(b' ' * (MAX_BYTES + 1))
        self.assertRejected(svg('<rect/>' * MAX_NODES))
        self.assertRejected(svg('<g>' * MAX_DEPTH + '</g>' * MAX_DEPTH))
        self.assertRejected(svg('<rect ' + ' '.join('x%d="1"' % index for index in range(41)) + '/>'))
        self.assertRejected(b'')
        with self.assertRaises(SvgPreviewError): sanitize_svg('<svg/>')

    def test_large_numeric_values_including_exponent_overflow_are_rejected(self):
        for body in ('<rect x="1e999"/>', '<circle r="-1"/>', '<rect width="1000001"/>',
                     '<path d="M0 0 L 1e999 2"/>', '<line x1="NaN"/>', '<ellipse rx="Infinity"/>'):
            with self.subTest(body=body): self.assertRejected(svg(body))

    def test_display_dimensions_viewbox_and_area_are_bounded(self):
        for attributes in ('width="8193"', 'height="100000"', 'width="8192" height="8192"',
                           'width="-1"', 'width="101%"', 'viewBox="0 0 0 1"', 'viewBox="0 0 1e999 100"',
                           'width="100in"', 'width="1calc(2)"'):
            with self.subTest(attributes=attributes): self.assertRejected(svg(attributes=attributes))
        self.assertIn(b'width="100%"', sanitize_svg(svg(attributes='width="100%" height="100%"')))
        self.assertIn(b'width="10cm"', sanitize_svg(svg(attributes='width="10cm" height="5cm"')))

    def test_numeric_and_path_data_complexity_limits(self):
        self.assertRejected(svg('<path d="M0 0 ' + 'Z' * MAX_PATH_COMMANDS + '"/>'))
        self.assertRejected(svg('<path d="M0 0 ' + ('L0 0 ' * (MAX_NUMBERS // 2 + 1)) + '"/>'))
        self.assertRejected(svg('<path d="M0 0 ' + ' ' * MAX_PATH_DATA + '"/>'))
        self.assertRejected(svg('<path d="M0 0 script(1)"/>'))
        self.assertRejected(svg('<polygon points="1 2 3"/>'))

    def test_transform_stacking_and_skew_are_bounded(self):
        for body in ('<g transform="scale(100000)"/>', '<g transform="skewX(89)"/>',
                     '<g transform="scale(100)"><g transform="scale(100)"><g transform="scale(2)"/></g></g>',
                     '<g transform="translate(url(#a))"/>', '<g transform="matrix(1,2,3)"/>'):
            with self.subTest(body=body): self.assertRejected(svg(body))
        self.assertIn(b'rotate(45)', sanitize_svg(svg('<g transform="rotate(45) translate(2,3) scale(2)"/>')))

    def test_dash_expansion_pathlength_and_extreme_font_or_stroke_are_rejected(self):
        for body in ('<path pathLength="1e-300"/>', '<path stroke-dasharray="url(https://example.com)"/>',
                     '<text font-size="1000000">text</text>', '<text font-size="10000%">text</text>',
                     '<path stroke-width="1000000"/>', '<path stroke-width="10000%"/>'):
            with self.subTest(body=body): self.assertRejected(svg(body))
        self.assertIn(b'stroke-dasharray="none"', sanitize_svg(svg('<path stroke-dasharray="none"/>')))

    def test_decorative_shadows_and_dashes_degrade_without_losing_diagram(self):
        raw = svg('<defs><linearGradient id="paint"><stop offset="0" stop-color="#abcdef"/>'
                  '<stop offset="1" stop-color="#123456"/></linearGradient>'
                  '<filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">'
                  '<feDropShadow dx="0" dy="4" stdDeviation="3" flood-color="#000" flood-opacity="0.2"/>'
                  '</filter></defs><g filter="url(#shadow)"><rect x="10" y="10" width="80" height="60" fill="url(#paint)"/>'
                  '<text x="20" y="40">合成流程图</text></g>'
                  '<line x1="0" y1="0" x2="100" y2="100" stroke="#000" stroke-dasharray="16 8"/>'
                  '<line x1="0" y1="100" x2="100" y2="0" style="stroke-dasharray:4 2;filter:url(#shadow)"/>')
        before = bytes(raw)
        result = preview_svg(raw)
        self.assertEqual(raw, before)
        self.assertEqual(sanitize_svg(raw), result['svg'])
        self.assertEqual(len(result['notices']), 2)
        self.assertTrue(any('滤镜' in notice for notice in result['notices']))
        self.assertTrue(any('实线' in notice for notice in result['notices']))
        root = ET.fromstring(result['svg'])
        self.assertEqual(len(root.findall('.//{' + SVG_NAMESPACE + '}rect')), 1)
        self.assertEqual(len(root.findall('.//{' + SVG_NAMESPACE + '}line')), 2)
        self.assertEqual(len(root.findall('.//{' + SVG_NAMESPACE + '}linearGradient')), 1)
        self.assertIn('合成流程图'.encode(), result['svg'])
        self.assertNotIn(b'<filter', result['svg'])
        self.assertNotIn(b'feDropShadow', result['svg'])
        self.assertNotIn(b'filter=', result['svg'])
        self.assertNotIn(b'stroke-dasharray="16 8"', result['svg'])

    def test_tiny_dashes_are_never_sent_to_renderer_and_plain_svg_has_no_notice(self):
        result = preview_svg(svg('<path stroke-dasharray="1e-300 1e-300" d="M0 0 L1000000 1000000"/>'))
        self.assertIn(b'stroke-dasharray="none"', result['svg'])
        self.assertNotIn(b'1e-300', result['svg'])
        self.assertEqual(len(result['notices']), 1)
        self.assertEqual(preview_svg(svg('<rect width="1" height="2"/>'))['notices'], [])

    def test_omitted_filter_subtrees_still_reject_active_or_external_content(self):
        for body in ('<filter id="f"><script>alert(1)</script></filter>',
                     '<filter id="f" onload="alert(1)"/>', '<filter id="f"><feDropShadow onclick="x"/></filter>',
                     '<filter id="f"><feImage href="https://example.com/image.png"/></filter>',
                     '<filter id="f"><feGaussianBlur href="https://example.com"/></filter>',
                     '<filter id="f"><animate attributeName="x"/></filter>',
                     '<filter id="f"><foreignObject/></filter>', '<filter id="f"><use href="#x"/></filter>',
                     '<g filter="url(https://example.com/effect.svg#f)"/>',
                     '<g style="filter:url(data:text/plain,unsafe)"/>'):
            with self.subTest(body=body): self.assertRejected(svg(body))

    def test_omitted_filters_still_obey_node_depth_and_attribute_limits(self):
        self.assertRejected(svg('<defs><filter id="f">' + '<feOffset dx="0"/>' * MAX_NODES + '</filter></defs>'))
        self.assertRejected(svg('<filter>' + '<feMerge>' * MAX_DEPTH + '</feMerge>' * MAX_DEPTH + '</filter>'))
        self.assertRejected(svg('<filter><feDropShadow stdDeviation="' + '1 ' * 3000 + '"/></filter>'))

    def test_unknown_namespaces_elements_attributes_and_nested_svg_rejected(self):
        for body in ('<custom/>', '<rect xmlns="urn:not-svg"/>', '<svg/>',
                     '<rect unknown="x"/>', '<g xml:base="https://example.com"/>',
                     '<text xmlns:x="urn:unknown" x:unsafe="x">t</text>'):
            with self.subTest(body=body): self.assertRejected(svg(body))
        self.assertRejected(b'<html xmlns="http://www.w3.org/1999/xhtml"/>')

    def test_metadata_comments_and_markup_in_text_cannot_become_executable(self):
        clean = sanitize_svg(svg('<!-- <script>ignored</script> --><title>静态标题</title><desc>说明</desc>'
                                '<text xml:space="preserve"> &lt;script&gt;&amp; </text>'))
        self.assertNotIn(b'<!--', clean)
        self.assertIn(b'xml:space="preserve"', clean)
        self.assertIn(b'&lt;script&gt;&amp;', clean)
        self.assertRejected(svg('<metadata><unsafe/></metadata>'))

    def test_sanitizing_already_sanitized_svg_is_stable(self):
        raw = svg('<g><rect style="fill:#abc;stroke:rgb(1,2,3)" width="10" height="10"/></g>')
        once = sanitize_svg(raw)
        self.assertEqual(sanitize_svg(once), once)


if __name__ == '__main__':
    unittest.main()
