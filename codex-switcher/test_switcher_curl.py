"""Pure parsing regressions; fixtures contain no real credentials."""
import json
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest.mock import patch
import switcher_core as c

SAMPLE = Path(__file__).with_name('examples').joinpath('deepseek.curl').read_text(encoding='utf-8')


class CurlTests(unittest.TestCase):
    def parse(self, text=SAMPLE):
        records, warnings = c.import_text(text)
        self.assertEqual(len(records), 1)
        return records[0], warnings

    def test_official_example_preserves_model_effort_and_variable(self):
        item, notes = self.parse()
        self.assertEqual(item['profile'], dict(id='deepseek', name='DeepSeek', base_url='https://api.deepseek.com',
                         model='deepseek-v4-pro', env_key='DEEPSEEK_API_KEY', wire_api='responses', reasoning_effort='high'))
        self.assertEqual(item['secret'], '')
        self.assertIn('转换', '\n'.join(notes))

    def test_user_markdown_link_and_escaped_underscores(self):
        url = 'https://api.deepseek.com/chat/completions'
        item, _ = self.parse(SAMPLE.replace(url, f'[{url}]({url})').replace('_', r'\_'))
        self.assertEqual(item['profile']['env_key'], 'DEEPSEEK_API_KEY')
        self.assertEqual(item['profile']['reasoning_effort'], 'high')

    def test_fenced_curl_and_config(self):
        item, _ = self.parse('```bash\n'+SAMPLE+'\n```')
        again, _ = self.parse('```json\n'+c.export_profiles([item['profile']])+'\n```')
        self.assertEqual(again['profile'], item['profile'])

    def test_unclosed_fence_is_rejected(self):
        with self.assertRaises(ValueError): self.parse('```bash\n'+SAMPLE)

    def test_windows_line_continuations_and_curl_exe(self):
        for marker in ('^', '`'):
            with self.subTest(marker=marker):
                item, _ = self.parse(SAMPLE.replace('curl ', 'curl.exe ').replace('\\\n', marker+'\r\n'))
                self.assertEqual(item['profile']['model'], 'deepseek-v4-pro')

    def test_variable_forms_do_not_read_env(self):
        for variable in ('${TEST_API_KEY}', '$TEST_API_KEY', '%TEST_API_KEY%', '$env:TEST_API_KEY'):
            with self.subTest(variable=variable), patch.dict('os.environ', {'TEST_API_KEY': 'NEVER_READ_SENTINEL'}):
                item, notes = self.parse(SAMPLE.replace('${DEEPSEEK_API_KEY}', variable))
                self.assertEqual(item['secret'], '')
                self.assertEqual(item['profile']['env_key'], 'TEST_API_KEY')
                self.assertNotIn('NEVER_READ_SENTINEL', repr((item, notes)))

    def test_literal_key_is_preview_only_and_never_exported(self):
        item, notes = self.parse(SAMPLE.replace('${DEEPSEEK_API_KEY}', 'FAKE_TEST_SECRET'))
        self.assertEqual(item['secret'], 'FAKE_TEST_SECRET')
        merged, _, _ = c.merge_profiles([], [item])
        self.assertNotIn('FAKE_TEST_SECRET', c.export_profiles(merged))
        self.assertNotIn('FAKE_TEST_SECRET', '\n'.join(notes))

    def test_generic_responses_suffix_and_nested_reasoning(self):
        item, _ = self.parse('curl --url=https://api.example/v1/responses --request=POST --json=\'{"model":"model_example","reasoning":{"effort":"high"}}\'')
        self.assertEqual(item['profile']['base_url'], 'https://api.example/v1')
        self.assertEqual(item['profile']['model'], 'model_example')
        self.assertEqual(item['profile']['reasoning_effort'], 'high')

    def test_deepseek_native_responses_and_v1(self):
        for endpoint in ('/responses', '/v1/responses', '/v1/chat/completions'):
            item, _ = self.parse(SAMPLE.replace('/chat/completions', endpoint))
            self.assertEqual(item['profile']['base_url'], 'https://api.deepseek.com')

    def test_unknown_chat_hosts_never_guessed(self):
        for host in ('api.other.example', 'api.deepseek.com.other.example', 'api.deepseek.com:8443'):
            with self.subTest(host=host), self.assertRaisesRegex(ValueError, '尚未确认'):
                self.parse(SAMPLE.replace('api.deepseek.com', host))

    def test_request_option_variants(self):
        for flag in ('--data', '--data-raw', '--data-binary', '--json', '-d'):
            self.parse(SAMPLE.replace('-d ', flag+' ').replace('curl ', 'curl -sS -XPOST '))
        self.parse(SAMPLE.replace('-H ', '-H').replace('-d ', '-d'))

    def test_unsafe_or_unsupported_commands_are_not_executed(self):
        with patch('subprocess.run') as run, patch('os.system') as system:
            for suffix in ('; echo PRIVATE_SENTINEL', ' | echo PRIVATE_SENTINEL', ' > output.txt', '\ncurl https://other.example/responses'):
                with self.subTest(suffix=suffix), self.assertRaises(ValueError) as raised:
                    self.parse(SAMPLE+suffix)
                self.assertNotIn('PRIVATE_SENTINEL', str(raised.exception))
            run.assert_not_called(); system.assert_not_called()

    def test_file_references_are_never_read(self):
        with patch('builtins.open', side_effect=AssertionError('parser must not open files')):
            with self.assertRaisesRegex(ValueError, '@文件'):
                self.parse('curl https://api.deepseek.com/responses -d @private.json')

    def test_reject_wrong_method_missing_body_multi_body_and_advanced_flags(self):
        for text in (SAMPLE+' -X GET', SAMPLE+' -d {}', 'curl https://api.example/responses', SAMPLE+' --config private.txt'):
            with self.subTest(text=text[:60]), self.assertRaises(ValueError): self.parse(text)

    def test_invalid_bodies_have_sanitized_errors(self):
        for body in ('{"model":"PRIVATE_SENTINEL"', '[]', '{"model":2}', '{}'):
            with self.assertRaises(ValueError) as raised:
                self.parse("curl https://api.deepseek.com/responses -d '"+body+"'")
            self.assertNotIn('PRIVATE_SENTINEL', str(raised.exception))

    def test_reject_duplicate_and_custom_headers(self):
        for header in ('Authorization: Bearer PRIVATE_SENTINEL', 'X-Private: PRIVATE_SENTINEL', 'Content-Type: text/plain'):
            with self.assertRaises(ValueError) as raised: self.parse(SAMPLE+" -H '"+header+"'")
            self.assertNotIn('PRIVATE_SENTINEL', str(raised.exception))

    def test_query_userinfo_and_markdown_mismatch_rejected(self):
        url = 'https://api.deepseek.com/chat/completions'
        for replacement in (url+'?key=PRIVATE_SENTINEL', 'https://user:PRIVATE_SENTINEL@api.deepseek.com/chat/completions', f'[{url}](https://evil.example/responses)'):
            with self.assertRaises(ValueError) as raised: self.parse(SAMPLE.replace(url, replacement))
            self.assertNotIn('PRIVATE_SENTINEL', str(raised.exception))

    def test_command_substitution_and_reserved_variable_rejected(self):
        for value in ('$(echo PRIVATE_SENTINEL)', '`echo PRIVATE_SENTINEL`', '${PATH}', '${bad-name}', '<API_KEY>'):
            with self.assertRaises(ValueError) as raised: self.parse(SAMPLE.replace('${DEEPSEEK_API_KEY}', value))
            self.assertNotIn('PRIVATE_SENTINEL', str(raised.exception))

    def test_effort_and_thinking_validation(self):
        for value in ('"unsupported"', 'false', '1', '{}', 'null'):
            with self.subTest(value=value), self.assertRaises(ValueError): self.parse(SAMPLE.replace('"high"', value))
        with self.assertRaises(ValueError): self.parse(SAMPLE.replace('"enabled"', '"disabled"'))
        with self.assertRaises(ValueError): self.parse(SAMPLE.replace('"high"', '"high", "reasoning":{"effort":"low"}'))

    def test_effort_roundtrip_import_export_and_store(self):
        item, _ = self.parse()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'profiles.json'
            c.save_profiles(path, [item['profile']])
            self.assertEqual(c.load_profiles(path), [item['profile']])
            imported, _ = self.parse(c.export_profiles(c.load_profiles(path)))
            self.assertEqual(imported['profile'], item['profile'])

    def test_render_preserves_nested_settings_and_updates_only_selected_effort(self):
        item, _ = self.parse()
        source = 'model="old"\nmodel_reasoning_effort="xhigh"\n[projects.demo]\nmodel_reasoning_effort="low"\n'
        result = tomllib.loads(c.render_config(source, item['profile']))
        self.assertEqual(result['model'], 'deepseek-v4-pro')
        self.assertEqual(result['model_reasoning_effort'], 'high')
        self.assertEqual(result['projects'], {'demo': {'model_reasoning_effort': 'low'}})
        self.assertEqual(result['model_providers']['switcher_deepseek']['base_url'], 'https://api.deepseek.com')

    def test_effort_toml_import_and_unspecified_preservation(self):
        item, _ = self.parse()
        rendered = c.render_config('model_reasoning_effort="low"', item['profile'])
        imported, _ = self.parse(rendered)
        self.assertEqual(imported['profile']['reasoning_effort'], 'high')
        no_effort = dict(item['profile']); no_effort.pop('reasoning_effort')
        result = tomllib.loads(c.render_config('model_reasoning_effort="xhigh"', no_effort))
        self.assertEqual(result['model_reasoning_effort'], 'xhigh')
        self.assertEqual(tomllib.loads(c.render_config(rendered, None))['model_reasoning_effort'], 'high')

    def test_duplicate_import_leaves_existing_profiles_untouched(self):
        item, _ = self.parse()
        profiles, added, skipped = c.merge_profiles([item['profile']], [item])
        self.assertEqual((profiles, added, skipped), ([item['profile']], [], 1))


if __name__ == '__main__': unittest.main()
