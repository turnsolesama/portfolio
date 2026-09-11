import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import zipfile
from contextlib import contextmanager
from unittest.mock import patch
from urllib.parse import urlencode

from yingxu.organize import Organize
from yingxu.search import GlobalSearch
from yingxu.skills import SkillLibrary
from yingxu.store import Store, UserError


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='yingxu-global-search-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.store = Store(self.root / 'data', self.root / 'projects')
        with patch('yingxu.skills.Path.home', return_value=self.root / 'home'):
            self.skills = SkillLibrary(self.store)
        self.search = GlobalSearch(self.store, self.skills)
        self.organize = Organize(self.store)
        self.a = self.store.create_project('项目甲', '第一部创作')
        self.b = self.store.create_project('项目乙', '跨项目故事')

    def item(self, name='正文', project=None, **values):
        return self.store.create_item({'project_id': (project or self.a)['id'], 'name': name,
                                       'category': 'scripts', 'content': '普通文本', **values})

    def ids(self, result):
        return [row['id'] for row in result['results']]

    def test_global_index_finds_other_project_body_and_all_categories(self):
        self.item(content='当前没有目标')
        b = self.item('远方正文', self.b, content='这里有跨库唯一词。')
        c = self.item('角色设定', self.a, category='characters', content='跨库唯一词也用于角色。')
        result = self.search.search('跨库唯一词')
        self.assertEqual(set(self.ids(result)), {b['id'], c['id']})
        self.assertEqual({row['category'] for row in result['results']}, {'scripts', 'characters'})
        self.assertEqual(next(row for row in result['results'] if row['id'] == b['id'])['project_name'], '项目乙')
        self.assertTrue(all('跨库唯一词' in row['snippet'] for row in result['results']))

    def test_project_name_description_and_item_tags_notes_are_searchable(self):
        item = self.item('笔记名字', tags=['标签关键'], notes='备注线索')
        self.store.update_item(item['id'], {'notes': '备注线索'})
        for term in ['笔记名字', '标签关键', '备注线索']:
            self.assertEqual(self.ids(self.search.search(term)), [item['id']])
        result = self.search.search('跨项目故事')['results']
        self.assertEqual(result[0]['type'], 'project')
        self.assertEqual(result[0]['id'], self.b['id'])

    def test_literal_substrings_match_inside_words_for_every_result_type(self):
        project = self.store.create_project('midnight project')
        item = self.item('midnight document')
        body_item = self.item('正文中的词', content='A midnight scene.')
        skill = self.skills.create({'name': 'midnight skill'})
        self.assertEqual(set(self.ids(self.search.search('night'))), {project['id'], item['id'], body_item['id'], skill['id']})

    def test_unicode_casefold_is_consistent_for_projects_items_and_skills(self):
        project = self.store.create_project('CAFÉ project')
        item = self.item('CAFÉ document')
        body_item = self.item('Unicode正文', content='CAFÉ STRASSE scene')
        skill = self.skills.create({'name': 'CAFÉ skill'})
        self.assertEqual(set(self.ids(self.search.search('café'))), {project['id'], item['id'], body_item['id'], skill['id']})
        self.assertEqual(self.ids(self.search.search('café straße')), [body_item['id']])

    def test_name_matches_use_readable_body_or_tags_without_json_array_text(self):
        item = self.item('保留草稿', content='真正的文档正文')
        result = self.search.search('保留草稿')['results'][0]
        self.assertEqual(result['id'], item['id'])
        self.assertEqual(result['snippet'], '真正的文档正文')
        self.store.update_item(item['id'], {'tags': ['实际标签']})
        self.assertEqual(self.search.search('保留草稿')['results'][0]['snippet'], '实际标签')

    def test_empty_tags_serialization_is_not_searchable_but_literal_tag_text_is(self):
        self.item('没有标签', content='普通正文')
        self.assertEqual(self.search.search('[]')['results'], [])
        tagged = self.item('有字面标签', tags=['[]'], content='普通正文')
        result = self.search.search('[]')
        self.assertEqual(self.ids(result), [tagged['id']])
        self.assertEqual(result['results'][0]['snippet'], '[]')

    def test_registered_internal_and_external_skills_body_search_does_not_modify(self):
        internal = self.skills.create({'name': '自建能力', 'content': '本段含技能深层词。'})
        external_path = self.skills.sources['codex'] / 'external-demo' / 'SKILL.md'
        external_path.parent.mkdir(parents=True)
        external_path.write_text('---\nname: 外部能力\ndescription: 合成说明\n---\n这里也有技能深层词。', encoding='utf-8')
        before = external_path.read_bytes()
        self.skills.refresh()
        result = self.search.search('技能深层词')
        self.assertEqual(len(result['results']), 2)
        self.assertEqual({row['source'] for row in result['results']}, {'yingxu', 'codex'})
        self.assertIn(internal['id'], self.ids(result))
        self.assertEqual(external_path.read_bytes(), before)

    def test_removed_projects_items_folders_and_skills_are_not_results(self):
        removed = self.item('回收关键词')
        self.organize.delete_items([removed['id']])
        project_item = self.item('回收关键词二', self.b)
        self.organize.delete_project(self.b['id'])
        skill = self.skills.create({'name': '回收关键词技能'})
        self.skills.remove(skill['id'])
        self.assertEqual(self.search.search('回收关键词')['results'], [])
        self.assertNotIn(project_item['id'], self.ids(self.search.search('回收关键词二')))

    def test_pagination_has_stable_order_and_no_duplicates(self):
        expected = {self.item('分页目标' + str(index))['id'] for index in range(7)}
        pages = [self.search.search('分页目标', limit=3, offset=offset) for offset in (0, 3, 6)]
        found = [iid for page in pages for iid in self.ids(page)]
        self.assertEqual(len(found), 7)
        self.assertEqual(set(found), expected)
        self.assertEqual(pages[0]['total'], 7)
        self.assertTrue(pages[0]['has_more'])
        self.assertFalse(pages[-1]['has_more'])

    def test_wildcard_and_sql_punctuation_are_literal_not_query_syntax(self):
        item = self.item('字面%_符号')
        self.item('其他文件')
        self.assertEqual(self.ids(self.search.search('%_')), [item['id']])
        self.assertEqual(self.search.search("' OR 1=1 --")['results'], [])

    def test_query_and_pagination_bounds_and_empty_query_never_scan(self):
        for q in ['词' * 201, '\x00', ' '.join(['x'] * 13)]:
            with self.assertRaises(UserError): self.search.search(q)
        for options in [{'limit': 0}, {'limit': 'bad'}, {'offset': -1}, {'offset': 100001}]:
            with self.assertRaises(UserError): self.search.search('词', **options)
        self.assertEqual(self.search.search('词', limit=999)['limit'], 50)
        with patch.object(self.store, 'connection', side_effect=AssertionError('empty query touched DB')):
            result = self.search.search('   ')
        self.assertEqual(result['results'], [])
        self.assertEqual(result['scanned']['items'], 0)

    def test_item_search_uses_cached_index_without_reading_document_bodies(self):
        item = self.item(content='缓存索引唯一词')
        with patch.object(Path, 'open', side_effect=AssertionError('unexpected file read')):
            result = self.search.search('缓存索引唯一词')
        self.assertEqual(self.ids(result), [item['id']])
        self.assertIn('未保存草稿', result['scope']['content_source'])

    def test_registered_plain_text_and_extracted_word_bodies_share_the_global_index(self):
        folder = self.root / 'documents'; folder.mkdir()
        text = folder / '普通文本.txt'; text.write_text('纯文本正文命中', encoding='utf-16')
        word = folder / '文档.docx'
        with zipfile.ZipFile(word, 'w') as archive:
            archive.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
            archive.writestr('word/document.xml', '<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>提取文档正文命中</w:t></w:r></w:p></w:body></w:document>')
        source = self.store.register_source(self.b['id'], str(folder), 'references')
        self.store.index_files(source, [text, word])
        result = self.search.search('正文命中')
        self.assertEqual({item['kind'] for item in result['results']}, {'text', 'docx'})
        self.assertTrue(all(item['project_id'] == self.b['id'] for item in result['results']))

    def test_replaced_hardlink_and_unregistered_source_cannot_leak_cached_content(self):
        item = self.item(content='受限关键词')
        os.link(item['path'], self.root / 'alias.md')
        result = self.search.search('受限关键词')
        self.assertEqual(result['results'], [])
        self.assertTrue(result['truncated'])
        second = self.item('第二个', content='越界关键词')
        other = self.root / 'outside.md'; other.write_text('实际另一个文件', encoding='utf-8')
        with self.store.connection() as db:
            db.execute('UPDATE items SET path=? WHERE id=?', (str(other), second['id']))
        self.assertEqual(self.search.search('越界关键词')['results'], [])

    def test_skill_path_must_stay_inside_its_registered_source(self):
        skill = self.skills.create({'name': '技能授权词', 'content': '普通正文'})
        external = self.root / 'unregistered' / 'SKILL.md'; external.parent.mkdir()
        external.write_text('技能授权词', encoding='utf-8')
        with self.store.connection() as db:
            db.execute('UPDATE yx_skills SET path=? WHERE id=?', (str(external), skill['id']))
        self.assertEqual(self.search.search('技能授权词')['results'], [])

    def test_budget_limits_are_explicit_and_never_claim_complete_results(self):
        for number in range(4): self.item('限量词' + str(number))
        with patch('yingxu.search.MAX_CANDIDATES', 2):
            # Defaults are resolved at function definition inside each request.
            result = self.search.search('限量词')
        self.assertTrue(result['truncated'])
        self.assertFalse(result['total_exact'])
        self.assertEqual(len(result['results']), 2)
        self.skills.create({'name': '不匹配名称', 'content': '容量正文词'})
        with patch('yingxu.search.MAX_SKILL_READ_BYTES', 1):
            result = self.search.search('容量正文词')
        self.assertEqual(result['results'], [])
        self.assertTrue(result['truncated'])
        self.assertTrue(any('读取上限' in warning for warning in result['warnings']))
        with patch('yingxu.search.MAX_SECONDS', 0):
            self.assertFalse(self.search.search('限量词')['total_exact'])

    def test_long_body_twelve_unicode_substrings_reuse_bounded_connections(self):
        words=['straße','café','night','场景','角色','镜头','对白','灯光','动作','表情','道具','画面']
        content=('STRASSE CAFÉ midnight 场景角色镜头对白灯光动作表情道具画面 '*2000)[:50000]
        expected={self.item(f'长文{index:02}',content=content)['id'] for index in range(12)}
        original=self.store.connection;connections=[]
        @contextmanager
        def counted():
            connections.append(True)
            with original() as db:yield db
        with patch.object(self.store,'connection',counted):
            result=self.search.search(' '.join(words))
        self.assertEqual(set(self.ids(result)),expected)
        self.assertFalse(result['truncated'])
        self.assertLessEqual(len(connections),5,'candidate checks must not open two databases per result')

    def test_candidate_removed_between_scan_and_validation_cannot_leak(self):
        item=self.item(content='并发撤销授权词')
        original=self.store.connection;count=0
        @contextmanager
        def changed():
            nonlocal count
            count+=1
            with original() as db:
                if count==3:db.execute('UPDATE projects SET removed=1 WHERE id=?',(self.a['id'],));db.commit()
                yield db
        with patch.object(self.store,'connection',changed):result=self.search.search('并发撤销授权词')
        self.assertNotIn(item['id'],self.ids(result));self.assertTrue(result['truncated'])


class SearchHttpTests(unittest.TestCase):
    def test_http_route_has_global_scope_and_rejects_path_and_foreign_origin(self):
        from server import Application, Server
        with tempfile.TemporaryDirectory(prefix='yingxu-search-http-') as directory:
            root = Path(directory)
            with patch('yingxu.skills.Path.home', return_value=root / 'home'):
                app = Application(root / 'data', root / 'projects')
            server = Server(('127.0.0.1', 0), app)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            try:
                project = app.store.create_project('HTTP全局项目')
                def get(path, headers=None):
                    connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                    connection.request('GET', path, headers=headers or {})
                    response = connection.getresponse(); payload = response.read(); status = response.status
                    connection.close(); return status, json.loads(payload)
                status, result = get('/api/search?' + urlencode({'q': 'HTTP全局项目'}))
                self.assertEqual(status, 200)
                self.assertEqual(result['results'][0]['id'], project['id'])
                self.assertEqual(get('/api/search?q=test&path=C:/private.txt')[0], 400)
                self.assertEqual(get('/api/search?q=test&project=ignored')[0], 400)
                self.assertEqual(get('/api/search?q=test', {'Origin': 'https://foreign.invalid'})[0], 403)
                self.assertEqual(get('/api/search?' + urlencode({'q': 'x' * 201}))[0], 400)
                self.assertTrue(app.bootstrap()['capabilities']['global_search'])
            finally:
                server.shutdown(); server.server_close(); thread.join()
                app.jobs.pool.shutdown(wait=True); app.thumbnails.pool.shutdown(wait=True); app.context.close()


if __name__ == '__main__':
    unittest.main()
