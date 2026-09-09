"""Registration safety and evidence tests use temporary files, never local assets."""
import copy
import datetime as dt
import hashlib
import json
import os
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from aihub import config, management, registry


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='aihub-registry-test-')
        self.base = Path(self.temporary.name)
        self.ai = self.base / 'AI'
        self.ai.mkdir()
        self.data = self.base / 'data'
        self.cfg = {'ai_root': str(self.ai)}
        self.patch = patch.object(config, 'DATA_DIR', str(self.data))
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(self.temporary.cleanup)

    def file(self, relative, value='test'):
        path = self.ai / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding='utf-8')
        return path

    def project(self, name='Film', kind='creative', folder='40_Projects'):
        doc = self.file(f'{folder}/{name}/项目说明.md', '# Project')
        return {'id': name.lower(), 'name': name, 'type': kind, 'root': str(doc.parent),
                'current_doc': str(doc), 'delivery': str(doc.parent / '90_Delivery')}

    def store(self, kind, value):
        return registry.save(self.cfg, registry.preview(self.cfg, kind, value)['token'])

    def snapshot(self, path):
        st = path.stat()
        return {'path': str(path), 'size': st.st_size, 'mtime_ns': str(st.st_mtime_ns)}

    def link_directory(self, link, target):
        link.absolute().relative_to(self.base)
        target.absolute().relative_to(self.base)
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError:
            if os.name != 'nt':
                self.skipTest('Directory links unavailable')
            result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(target)], capture_output=True)
            if result.returncode:
                self.skipTest('Creating a temporary junction is unavailable')
        def remove_link_only():
            # os.rmdir removes a directory link itself; never recurse into it.
            if os.path.lexists(link):
                link.absolute().relative_to(self.base)
                os.rmdir(link)
        self.addCleanup(remove_link_only)

    def workflow(self):
        path = self.file('60_Workflows/Example/graph.json', '{"node":1}')
        dep = self.file('20_Models/Components/fixture.bin', 'fake dependency')
        output = self.file('70_Output/Projects/Film/run-001/evidence.txt', 'fake output evidence')
        return {'id': 'example', 'path': str(path), 'state': 'current_passed', 'validation': {
            'date': dt.date.today().isoformat(), 'workflow_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'dependencies': [self.snapshot(dep)], 'outputs': [self.snapshot(output)]}}

    def test_project_preview_is_readonly_and_save_maps_existing_structure(self):
        item = self.project()
        item.update(template={'id': 'film'}, mapping={'storyboard': '01_script_storyboard'},
                    assets=[str(self.ai / '30_Assets/References')], outputs=[str(self.ai / '70_Output/Projects/Film')])
        preview = management.registration_preview(self.cfg, 'project', item)
        self.assertFalse(self.data.exists())
        self.assertFalse(Path(item['delivery']).exists())
        saved = management.registration_save(self.cfg, preview['token'])
        self.assertTrue(saved['saved'])
        self.assertFalse(Path(item['delivery']).exists())
        row = management.projects(self.cfg)['items'][0]
        self.assertTrue(row['registered'])
        self.assertEqual(row['status'], '已登记')
        self.assertEqual(row['mapping'], {'storyboard': '01_script_storyboard'})
        self.assertEqual(row['current_doc'], item['current_doc'])
        self.assertEqual(saved['record']['template']['version'], '1')

    def test_discovers_creative_training_and_only_explicit_tool_projects(self):
        creative = self.project('Motion')
        training = self.project('Train', 'training', '50_Training/Projects')
        self.file('10_Apps/RuntimeOnly/README.md', '# Application')
        self.file('10_Apps/Tool/PROJECT.md', '# Development project')
        self.file('10_Apps/DeveloperTool/README.md', '# Development guide')
        self.file('10_Apps/DeveloperTool/AGENTS.md', '# Project development rules')
        self.file('10_Apps/NestedOnly/docs/AGENTS.md', '# Do not recursively discover')
        self.file('10_Apps/NestedOnly/README.md', '# Installed app')
        result = management.projects(self.cfg)
        self.assertEqual({p['type'] for p in result['items']}, {'creative', 'training', 'tool'})
        self.assertEqual(len(result['items']), 4)
        self.assertTrue(all(p['status'] == '未登记' and p['template'] is None for p in result['items']))
        developer = next(p for p in result['items'] if p['name'] == 'DeveloperTool')
        self.assertEqual(developer['registration_source'], '一级开发说明候选（未登记）')
        self.assertEqual(developer['current_doc'], str(self.ai / '10_Apps/DeveloperTool/README.md'))
        reports = management.reports(self.cfg, self.data / 'reports')
        self.assertTrue({creative['current_doc'], training['current_doc']}.issubset({p['path'] for p in reports}))

    def test_project_fields_and_template_are_validated(self):
        base = self.project()
        for change in ({'id': '../bad'}, {'type': 'everything'}, {'template': {'id': 'training'}},
                       {'mapping': {'escape': '../Other'}}, {'delivery': str(self.ai / '70_Output/Final')},
                       {'root': str(self.ai / '40_Projects')}, {'current_doc': str(self.file('40_Projects/Film/config.md'))}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                registry.preview(self.cfg, 'project', {**base, **change})
        self.assertFalse(self.data.exists())

    def test_cannot_repeat_root_or_share_formal_delivery(self):
        first = self.project()
        self.store('project', first)
        with self.assertRaisesRegex(ValueError, '重复|另一个'):
            self.store('project', {**first, 'id': 'other'})
        nested_doc = self.file('40_Projects/Film/Sub/项目说明.md')
        parent_delivery = str(nested_doc.parent / 'Final')
        self.store('project', {**first, 'delivery': parent_delivery})
        with self.assertRaisesRegex(ValueError, '正式交付'):
            self.store('project', {'id': 'sub', 'name': 'Sub', 'type': 'creative', 'root': str(nested_doc.parent),
                                  'current_doc': str(nested_doc), 'delivery': parent_delivery})

    def test_preview_is_single_use_and_bound_to_revision_workspace_and_store(self):
        first = registry.preview(self.cfg, 'project', self.project())
        stale = registry.preview(self.cfg, 'project', self.project('Second'))
        registry.save(self.cfg, first['token'])
        with self.assertRaises(ValueError):
            registry.save(self.cfg, first['token'])
        with self.assertRaisesRegex(ValueError, '修改'):
            registry.save(self.cfg, stale['token'])
        fresh = registry.preview(self.cfg, 'project', self.project('Second'))
        other = self.base / 'OtherAI'; other.mkdir()
        with self.assertRaisesRegex(ValueError, '环境'):
            registry.save({'ai_root': str(other)}, fresh['token'])
        with patch.object(config, 'DATA_DIR', str(self.base / 'other-data')), self.assertRaisesRegex(ValueError, '环境'):
            registry.save(self.cfg, fresh['token'])
        with patch.object(registry.time, 'time', return_value=fresh['expires_at'] + 1), self.assertRaisesRegex(ValueError, '过期'):
            registry.save(self.cfg, fresh['token'])

    def test_write_enforces_the_same_row_limit_as_read(self):
        path = self.file('80_Knowledge/Topics/example.md')
        self.data.mkdir()
        document = registry._empty()
        document['workspace'] = registry._key(self.ai)
        document['knowledge'] = [{'id': f'item-{i}', 'path': str(path), 'title': 'Example', 'description': ''} for i in range(2000)]
        primary = self.data / 'registry.json'
        primary.write_text(json.dumps(document), encoding='utf-8')
        before = primary.read_bytes()
        preview = registry.preview(self.cfg, 'knowledge', {'id': 'item-2001', 'path': str(path)})
        with self.assertRaisesRegex(ValueError, '结构'):
            registry.save(self.cfg, preview['token'])
        self.assertEqual(primary.read_bytes(), before)
        self.assertEqual(len(registry.read(self.cfg)['knowledge']), 2000)

    def test_backup_restore_preview_and_corrupt_primary_fallback(self):
        item = self.project()
        self.store('project', item)
        self.store('project', {**item, 'description': 'updated'})
        listing = management.registration_backups(self.cfg)
        preview = management.registration_restore_preview(self.cfg, listing['items'][0]['id'])
        self.assertEqual(registry.read(self.cfg)['projects'][0]['description'], 'updated')
        management.registration_save(self.cfg, preview['token'])
        self.assertEqual(registry.read(self.cfg)['projects'][0]['description'], '')
        (self.data / 'registry.json').write_text('{bad json', encoding='utf-8')
        fallback = registry.read(self.cfg)
        self.assertTrue(fallback['warnings'])
        self.assertEqual(fallback['projects'][0]['description'], 'updated')
        self.assertEqual((self.data / 'registry.json').read_text(), '{bad json')
        self.store('project', {**item, 'description': 'repair'})
        self.assertEqual(registry.read(self.cfg)['projects'][0]['description'], 'repair')
        self.assertEqual(json.loads((self.data / 'registry.previous.json').read_text())['projects'][0]['description'], 'updated')

    def test_restore_rejects_arbitrary_path_and_changed_backup(self):
        item = self.project(); self.store('project', item); self.store('project', {**item, 'description': 'new'})
        with self.assertRaises(ValueError):
            registry.restore_preview(self.cfg, str(self.data / 'registry.previous.json'))
        preview = registry.restore_preview(self.cfg, registry.backups(self.cfg)['items'][0]['id'])
        (self.data / 'registry.previous.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, '备份已变化'):
            registry.save(self.cfg, preview['token'])

    def test_workflow_requires_complete_dated_evidence(self):
        item = self.workflow()
        for field in ('date', 'workflow_sha256', 'dependencies', 'outputs'):
            bad = copy.deepcopy(item); bad['validation'].pop(field)
            with self.subTest(field=field), self.assertRaises(ValueError):
                registry.preview(self.cfg, 'workflow', bad)
        for state in ('passed', 'folder_verified', 'all_passed'):
            with self.assertRaises(ValueError):
                registry.preview(self.cfg, 'workflow', {**item, 'state': state})
        bad = copy.deepcopy(item); bad['validation']['date'] = (dt.date.today() + dt.timedelta(days=1)).isoformat()
        with self.assertRaises(ValueError):
            registry.preview(self.cfg, 'workflow', bad)
        self.store('workflow', item)
        self.assertEqual(management.registry_snapshot(self.cfg)['workflows'][0]['verification_state'], 'current_passed')

    def test_path_check_preserves_optional_date_hash_and_never_becomes_execution(self):
        item = self.workflow()
        item['state'] = 'path_checked'
        item['validation']['note'] = 'Only inspected file paths'
        self.store('workflow', item)
        snapshot = management.registry_snapshot(self.cfg)['workflows'][0]
        self.assertEqual(snapshot['verification_state'], 'path_checked')
        self.assertEqual(snapshot['validation']['date'], item['validation']['date'])
        self.assertEqual(snapshot['validation']['workflow_sha256'], item['validation']['workflow_sha256'])
        self.assertEqual(snapshot['validation']['note'], 'Only inspected file paths')
        Path(item['path']).write_text('changed workflow')
        changed = management.registry_snapshot(self.cfg)['workflows'][0]
        self.assertEqual(changed['verification_state'], 'pending')
        self.assertEqual(changed['validation']['date'], item['validation']['date'])
        minimal = {'id': 'minimal', 'path': str(self.file('60_Workflows/minimal.json', '{}')), 'state': 'path_checked'}
        self.assertIsNone(registry.preview(self.cfg, 'workflow', minimal)['record']['validation'])
        dated = {**minimal, 'validation': {'date': dt.date.today().isoformat()}}
        self.assertEqual(registry.preview(self.cfg, 'workflow', dated)['record']['validation'], dated['validation'])

    def test_templates_describe_existing_structures_without_creating_them(self):
        templates = {row['id']: row for row in registry.read(self.cfg)['templates']}
        for folder in ('00_Brief', '10_References', '20_Assets', '30_Workflows', '40_Runs', '90_Delivery'):
            self.assertIn(folder, templates['generic']['description'])
        self.assertIn('00_admin', templates['film']['description'])
        self.assertIn('01_script_storyboard', templates['film']['description'])
        self.assertIn('09_delivery', templates['film']['description'])
        self.assertIn('Datasets', templates['training']['description'])
        self.assertIn('Runs', templates['training']['description'])
        self.assertEqual(list(self.ai.iterdir()), [])

    def test_workflow_change_downgrades_current_but_preserves_historical_evidence(self):
        item = self.workflow(); self.store('workflow', item)
        Path(item['path']).write_text('{"node":2}')
        status = management.registry_snapshot(self.cfg)['workflows'][0]
        self.assertEqual(status['verification_state'], 'historical_passed')
        self.assertFalse(status['current_match'])
        self.assertIn('哈希', status['verification_reason'])
        self.assertEqual(status['validation']['date'], item['validation']['date'])
        with self.assertRaises(ValueError):
            registry.preview(self.cfg, 'workflow', item)
        malformed = {**item, 'state': 'historical_passed', 'validation': {}}
        self.assertEqual(registry.workflow_status(self.cfg, malformed)['verification_state'], 'pending')

    def test_dependency_or_output_change_invalidates_current_and_save_rechecks(self):
        for section in ('dependencies', 'outputs'):
            with self.subTest(section=section):
                item = self.workflow()
                preview = registry.preview(self.cfg, 'workflow', item)
                target = Path(item['validation'][section][0]['path']);target.write_text('changed size and content')
                with self.assertRaisesRegex(ValueError, '当前证据'):
                    registry.save(self.cfg, preview['token'])
                historical = {**item, 'state': 'historical_passed'}
                self.assertEqual(registry.preview(self.cfg, 'workflow', historical)['record']['state'], 'historical_passed')

    def test_stat_snapshots_do_not_hash_large_models_unless_explicitly_requested(self):
        item = self.workflow()
        original = registry._digest
        visited = []
        def capture(path):
            visited.append(str(path)); return original(path)
        with patch.object(registry, '_digest', side_effect=capture):
            self.store('workflow', item)
        self.assertEqual(set(visited), {item['path']})
        bad = copy.deepcopy(item);bad['validation']['dependencies'][0]['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, '哈希'):
            registry.preview(self.cfg, 'workflow', bad)

    def test_legacy_path_records_never_imply_execution(self):
        self.file('00_Management/Catalogs/workflows.json', json.dumps([{'path': 'old.json'}]))
        self.file('00_Management/Catalogs/workflow_path_review.json', json.dumps({'copies': [{'source': 'old.json', 'reviewed_copy': 'fixed.json', 'changes': []}]}))
        item = management.workflows(self.cfg)['items'][0]
        self.assertEqual(item['status'], 'reviewed_copy')
        self.assertEqual(item['verification_state'], 'path_checked')
        self.assertEqual(item['generation_status'], 'not_run')
        self.assertFalse(item['current_match'])

    def test_runs_have_project_and_version_provenance_without_creating_output(self):
        project = self.project();self.store('project', project)
        workflow = self.workflow();self.store('workflow', workflow)
        run = {'id': 'run-001', 'project_id': project['id'],
               'output_dir': str(self.ai / '70_Output/Projects/Film/run-001'),
               'workflow_path': workflow['path'], 'workflow_sha256': workflow['validation']['workflow_sha256'],
               'models': ['fixture-model'], 'seed': 123, 'validation_status': 'current_passed'}
        self.store('run', run)
        self.assertEqual(management.projects(self.cfg)['items'][0]['output_runs'][0]['seed'], 123)
        with self.assertRaisesRegex(ValueError, '输出证据'):
            registry.preview(self.cfg, 'run', {**run, 'id': 'run-002', 'output_dir': str(self.ai / '70_Output/Projects/Film/run-002')})
        unassigned = {**run, 'id': 'test-001', 'project_id': None, 'validation_status': 'pending',
                      'output_dir': str(self.ai / '70_Output/Tests/Unassigned/20260910-test')}
        self.store('run', unassigned)
        self.assertFalse(Path(unassigned['output_dir']).exists())
        with self.assertRaises(ValueError):
            registry.preview(self.cfg, 'run', {**unassigned, 'output_dir': str(self.ai / '70_Output')})
        Path(workflow['validation']['outputs'][0]['path']).write_text('changed output')
        snapshot = management.registry_snapshot(self.cfg)
        self.assertEqual(snapshot['workflows'][0]['verification_state'], 'historical_passed')
        self.assertEqual(snapshot['runs'][0]['validation_status'], 'current_passed')
        self.assertEqual(snapshot['runs'][0]['effective_validation_status'], 'historical_passed')
        self.assertEqual(management.projects(self.cfg)['items'][0]['output_runs'][0]['effective_validation_status'], 'historical_passed')

    def test_path_checked_run_requires_existing_paths_and_matching_workflow(self):
        workflow = self.workflow()
        out = self.ai / '70_Output/Tests/Unassigned/path-check'
        run = {'id': 'checked', 'output_dir': str(out), 'workflow_path': workflow['path'],
               'workflow_sha256': workflow['validation']['workflow_sha256'], 'validation_status': 'path_checked'}
        with self.assertRaises(ValueError):
            registry.preview(self.cfg, 'run', run)
        out.mkdir(parents=True)
        self.assertEqual(registry.preview(self.cfg, 'run', run)['record']['validation_status'], 'path_checked')
        Path(workflow['path']).unlink()
        with self.assertRaises(ValueError):
            registry.preview(self.cfg, 'run', run)
        Path(workflow['path']).write_text('new graph')
        with self.assertRaisesRegex(ValueError, '哈希'):
            registry.preview(self.cfg, 'run', run)

    def test_evidence_preview_reads_only_workflow_and_never_asserts_success(self):
        workflow = self.workflow()
        values = {'workflow_path': workflow['path'],
                  'dependencies': [workflow['validation']['dependencies'][0]['path']],
                  'outputs': [workflow['validation']['outputs'][0]['path']]}
        original = registry.read_checked
        reads = []
        def capture(path, *args, **kwargs):
            reads.append(str(path)); return original(path, *args, **kwargs)
        with patch.object(registry, 'read_checked', side_effect=capture):
            result = management.evidence_preview(self.cfg, values)
        self.assertEqual(reads, [workflow['path']])
        self.assertNotIn('date', result)
        self.assertNotIn('state', result)
        self.assertEqual(result['dependencies'], workflow['validation']['dependencies'])
        self.assertEqual(result['outputs'], workflow['validation']['outputs'])
        self.assertFalse(self.data.exists())
        empty = management.evidence_preview(self.cfg, {'workflow_path': workflow['path']})
        self.assertEqual((empty['dependencies'], empty['outputs']), ([], []))
        with self.assertRaises(ValueError):
            management.evidence_preview(self.cfg, {**values, 'outputs': [str(self.ai / '10_Apps/App/data/auth.json')]})
        with self.assertRaises(ValueError):
            management.evidence_preview(self.cfg, {**values, 'dependencies': values['dependencies'] * 101})

    def test_model_runtime_dependencies_allow_metadata_but_not_text_or_app_runtime(self):
        workflow = self.workflow()
        model = self.file('20_Models/Runtime/sample.safetensors', 'fixture weight')
        original = registry.read_checked
        reads = []
        def capture(path, *args, **kwargs):
            reads.append(str(path)); return original(path, *args, **kwargs)
        with patch.object(registry, 'read_checked', side_effect=capture):
            result = management.evidence_preview(self.cfg, {'workflow_path': workflow['path'], 'dependencies': [str(model)]})
        self.assertEqual(result['dependencies'], [self.snapshot(model)])
        self.assertEqual(reads, [workflow['path']])
        doc = self.file('20_Models/Runtime/readme.md')
        with self.assertRaises(ValueError):
            registry.safe_path(self.cfg, str(doc), text=True)
        app_runtime = self.file('10_Apps/Tool/runtime/example.py')
        with self.assertRaises(ValueError):
            management.evidence_preview(self.cfg, {'workflow_path': workflow['path'], 'dependencies': [str(app_runtime)]})

    def test_nanosecond_snapshot_survives_javascript_json_precision(self):
        workflow = self.workflow()
        # A realistic Windows timestamp whose low digits are lost as a JS Number.
        target = Path(workflow['validation']['dependencies'][0]['path'])
        timestamp = 1789012345678901200
        os.utime(target, ns=(timestamp, timestamp))
        evidence = management.evidence_preview(self.cfg, {'workflow_path': workflow['path'],
                    'dependencies': [str(target)], 'outputs': [workflow['validation']['outputs'][0]['path']]})
        stamp = evidence['dependencies'][0]['mtime_ns']
        self.assertIsInstance(stamp, str)
        self.assertEqual(int(stamp), target.stat().st_mtime_ns)
        self.assertNotEqual(int(float(stamp)), int(stamp))
        # parse_int=float models the JSON.parse numeric precision boundary.
        browser = json.loads(json.dumps(evidence), parse_int=float)
        self.assertEqual(browser['dependencies'][0]['mtime_ns'], stamp)
        browser['dependencies'][0]['size'] = int(browser['dependencies'][0]['size'])
        browser['outputs'][0]['size'] = int(browser['outputs'][0]['size'])
        workflow['validation'] = {'date': dt.date.today().isoformat(), **browser}
        self.store('workflow', workflow)
        self.assertEqual(management.registry_snapshot(self.cfg)['workflows'][0]['verification_state'], 'current_passed')

    def test_reparse_attribute_is_rejected_without_symlink_privileges(self):
        path = self.file('80_Knowledge/Guides/real.md')
        original = Path.lstat
        def lstat(current, *args, **kwargs):
            value = original(current, *args, **kwargs)
            if current == path.parent:
                from types import SimpleNamespace
                return SimpleNamespace(st_mode=value.st_mode, st_file_attributes=0x400)
            return value
        with patch.object(Path, 'lstat', lstat), self.assertRaisesRegex(ValueError, '联接'):
            registry.preview(self.cfg, 'knowledge', {'id': 'reparse', 'path': str(path)})

    def test_knowledge_guides_and_manifest_index_only_safe_text(self):
        guide = self.file('80_Knowledge/Guides/tutorial.md', '# Guide')
        nested = self.file('80_Knowledge/Guides/Topic/lesson.md', '# Lesson')
        private = self.file('80_Knowledge/Guides/config.md', 'do not index')
        cached = self.file('80_Knowledge/Guides/_renders/draft.md', 'draft')
        script = self.file('80_Knowledge/Guides/build.py', 'do not execute')
        manifest = {'documents': [{'path': 'Guides/Topic/lesson.md', 'title': 'Lesson'},
                                  {'path': '../40_Projects/private.md'}, {'path': 'Guides/_renders/draft.md'}]}
        self.file('80_Knowledge/manifest.json', json.dumps(manifest))
        reports = management.reports(self.cfg, self.data / 'reports')
        paths = {row['path'] for row in reports}
        self.assertTrue({str(guide), str(nested)}.issubset(paths))
        self.assertFalse({str(private), str(cached), str(script)} & paths)
        self.assertEqual(management.read_report(self.cfg, self.data / 'reports', str(guide)), '# Guide')
        with self.assertRaises(ValueError):
            management.read_report(self.cfg, self.data / 'reports', str(private))

    def test_knowledge_registration_and_secret_paths_are_rejected(self):
        good = self.file('80_Knowledge/Topics/example.md')
        self.store('knowledge', {'id': 'example', 'path': str(good), 'title': 'Example'})
        self.assertTrue(management.is_report(self.cfg, self.data / 'reports', str(good)))
        for relative in ('80_Knowledge/.env', '80_Knowledge/cache/note.md', '80_Knowledge/Guides/auth.md',
                         '10_Apps/Application/data/credentials.md', '80_Knowledge/Topics/../Topics/example.md'):
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                registry.preview(self.cfg, 'knowledge', {'id': 'bad', 'path': str(self.ai / relative)})

    def test_hardlinked_text_is_not_indexed(self):
        source = self.file('private-secret.txt', 'private')
        target = self.ai / '80_Knowledge/Guides/alias.md';target.parent.mkdir(parents=True)
        os.link(source, target)
        self.assertFalse(management.is_report(self.cfg, self.data / 'reports', str(target)))
        with self.assertRaises(ValueError):
            registry.preview(self.cfg, 'knowledge', {'id': 'alias', 'path': str(target)})

    def test_symlink_escape_cannot_be_indexed_or_registered(self):
        outside = self.base / 'outside';outside.mkdir();(outside / 'secret.md').write_text('private')
        link = self.ai / '80_Knowledge/Guides';link.parent.mkdir()
        self.link_directory(link, outside)
        self.assertFalse(management.is_report(self.cfg, self.data / 'reports', str(link / 'secret.md')))
        with self.assertRaises(ValueError):
            registry.preview(self.cfg, 'knowledge', {'id': 'escape', 'path': str(link / 'secret.md')})

    def test_registry_storage_cannot_be_redirected_with_symlink(self):
        outside = self.base / 'outside';outside.mkdir()
        self.link_directory(self.data, outside)
        with self.assertRaises(ValueError):
            registry.preview(self.cfg, 'project', self.project())
        self.assertEqual(list(outside.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
