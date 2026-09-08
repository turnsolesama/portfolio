"""Portable setup tests use only generated temporary workspaces."""
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest import mock

from aihub import config


class PortableConfiguration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='aihub-portable-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.app = self.base / 'Programs' / 'Hub'
        self.app.mkdir(parents=True)
        self.data = self.app / 'data'
        for name, value in [('APP_DIR', self.app), ('DATA_DIR', self.data),
                            ('CONFIG_PATH', self.data / 'config.json'),
                            ('REPORTS_DIR', self.data / 'reports')]:
            patcher = mock.patch.object(config, name, str(value))
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.dict(os.environ, {'AI_HUB_ROOT': ''})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.root = self.base / 'Assets'
        self.root.mkdir()

    def test_fresh_install_has_no_author_drive_or_implicit_organization(self):
        cfg = config.load_config()
        self.assertEqual(cfg['ai_root'], '')
        self.assertEqual(cfg['scan_roots'], [])
        self.assertEqual(cfg['organizer'], {'enabled': False, 'root': '', 'on_startup': False})
        self.assertFalse(config.workspace_status(cfg)['configured'])
        self.assertFalse((self.app.parent / 'AI_Assets').exists())

    def test_first_run_suggestion_is_sibling_for_arbitrary_installation(self):
        for name in ('Disk_D', 'Disk_H'):
            app = self.base / name / 'Tools' / 'Hub'
            with mock.patch.object(config, 'APP_DIR', str(app)):
                status = config.workspace_status({})
            self.assertEqual(status['suggested_root'], str(app.parent / 'AI_Assets'))
            self.assertFalse(app.parent.exists())

    def test_numbered_and_legacy_install_suggest_shared_asset_root(self):
        for name in ('10_Apps', 'AI_Apps', '10_APPS'):
            app = self.base / 'AnotherDisk' / 'AI' / name / 'AI_Hub'
            with mock.patch.object(config, 'APP_DIR', str(app)):
                status = config.workspace_status({})
            self.assertEqual(status['suggested_root'], str(app.parent.parent))

    def test_missing_asset_directory_keeps_config_and_requests_reselection(self):
        missing = str(self.base / 'DisconnectedDisk' / 'AI')
        cfg = {'ai_root': missing, 'network': {'proxy': 'http://localhost:1234'}}
        before = json.dumps(cfg)
        status = config.workspace_status(cfg)
        self.assertTrue(status['configured'])
        self.assertFalse(status['available'])
        self.assertIn('重新选择', status['message'])
        self.assertEqual(json.dumps(cfg), before)
        self.assertFalse(Path(missing).exists())

    def test_changed_root_is_reported_available_without_saving(self):
        cfg = {'ai_root': str(self.root)}
        with mock.patch.object(config, 'save_config') as save:
            self.assertTrue(config.workspace_status(cfg)['available'])
            self.assertEqual(config.detect_layout(str(self.root))['scan_roots'], [str(self.root)])
        save.assert_not_called()

    def test_existing_settings_and_unknown_extensions_survive_load(self):
        original = {'ai_root': str(self.root), 'scan_roots': [str(self.root)],
                    'network': {'proxy': 'http://localhost:9000', 'custom': True},
                    'server': {'port': 8999}, 'extension': {'keep': [1, 2]}}
        self.data.mkdir()
        path = Path(config.CONFIG_PATH)
        path.write_text(json.dumps(original), encoding='utf-8')
        before = path.read_bytes()
        with mock.patch.dict(os.environ, {'AI_HUB_ROOT': str(self.base)}):
            cfg = config.load_config()
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(cfg['ai_root'], str(self.root))
        self.assertEqual(cfg['server']['port'], 8999)
        self.assertEqual(cfg['extension'], original['extension'])
        self.assertEqual(cfg['network']['custom'], True)
        self.assertEqual(cfg['organizer']['enabled'], False)

    def test_existing_missing_root_does_not_inherit_environment_override(self):
        self.data.mkdir()
        Path(config.CONFIG_PATH).write_text('{}', encoding='utf-8')
        with mock.patch.dict(os.environ, {'AI_HUB_ROOT': str(self.root)}):
            self.assertEqual(config.load_config()['ai_root'], '')

    def test_invalid_json_and_wrong_shapes_are_never_overwritten(self):
        self.data.mkdir()
        for invalid in ('{broken', '[]', '{"network": []}', '{"organizer": false}'):
            path = Path(config.CONFIG_PATH)
            path.write_text(invalid, encoding='utf-8')
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    config.load_config()
                with self.assertRaises(ValueError):
                    config.save_config({})
                self.assertEqual(path.read_text(encoding='utf-8'), invalid)

    def test_atomic_replace_failure_keeps_existing_file_and_cleans_temp(self):
        config.save_config({'ai_root': str(self.root), 'notes': 'original'})
        path = Path(config.CONFIG_PATH)
        before = path.read_bytes()
        with mock.patch.object(config.os, 'replace', side_effect=OSError('fixture denied')):
            with self.assertRaises(OSError):
                config.save_config({'ai_root': str(self.root), 'notes': 'changed'})
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(list(self.data.glob('.config-*.tmp')), [])

    def test_layout_does_not_omit_loose_assets(self):
        (self.root / 'loose.safetensors').write_bytes(b'fixture')
        (self.root / 'Models').mkdir()
        result = config.detect_layout(str(self.root))
        self.assertEqual(result['scan_roots'], [str(self.root)])
        self.assertIn(str(self.app), result['scan_exclude_paths'])
        self.assertIn(str(self.root / '00_AIHub_Library'), result['scan_exclude_paths'])

    def test_scanner_excludes_app_library_and_case_insensitive_ignored_names(self):
        cfg = {'ignore_dirs': ['MyCACHE']}
        for path in (self.app / 'data' / 'private.json', self.app / 'backups' / 'file',
                     self.root / '00_AIHub_Library' / 'model', self.root / 'mycache' / 'file'):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'fixture')
            self.assertTrue(config.scan_excluded(str(path), cfg))
        normal = self.root / 'Models' / 'file'
        normal.parent.mkdir()
        normal.write_bytes(b'fixture')
        self.assertFalse(config.scan_excluded(str(normal), cfg))

    def test_scanner_missing_unreadable_and_direct_reparse_entries_are_excluded(self):
        self.assertTrue(config.scan_excluded(str(self.root / 'missing')))
        with mock.patch.object(config.os, 'lstat', side_effect=PermissionError('fixture denied')):
            self.assertTrue(config.scan_excluded(str(self.root)))
        class Linked:
            st_mode = stat.S_IFREG
            st_file_attributes = 0x400
        with mock.patch.object(config.os, 'lstat', return_value=Linked()):
            self.assertTrue(config.scan_excluded(str(self.root)))

    def test_scan_root_guard_rejects_ancestor_links_and_accepts_normal_root(self):
        nested = self.root / 'Nested'
        nested.mkdir()
        self.assertTrue(config.scan_root_allowed(str(nested), {}))
        self.assertFalse(config.scan_root_allowed(str(self.root / 'missing'), {}))
        real_lstat = os.lstat
        class Linked:
            st_mode = stat.S_IFDIR
            st_file_attributes = 0x400
        def fake_lstat(path, *args, **kwargs):
            if os.path.normcase(str(path)) == os.path.normcase(str(self.root)):
                return Linked()
            return real_lstat(path, *args, **kwargs)
        with mock.patch.object(config.os, 'lstat', side_effect=fake_lstat):
            self.assertFalse(config.scan_root_allowed(str(nested), {}))

    def test_real_symbolic_link_root_file_and_outputs_are_not_followed(self):
        target = self.base / 'Outside'
        target.mkdir()
        (target / 'output').mkdir()
        model = target / 'model.safetensors'
        model.write_bytes(b'outside fixture')
        linked = self.root / 'linked'
        file_link = self.root / 'model.safetensors'
        try:
            os.symlink(target, linked, target_is_directory=True)
            os.symlink(model, file_link)
        except OSError as exc:
            self.skipTest('This Windows session cannot create test symlinks: %s' % exc.winerror)
        self.assertTrue(config.scan_excluded(str(linked)))
        self.assertTrue(config.scan_excluded(str(file_link)))
        self.assertFalse(config.scan_root_allowed(str(linked)))
        self.assertFalse(config.scan_root_allowed(str(linked / 'output')))
        self.assertEqual(config.detect_output_roots([str(self.root)]), [])
        with self.assertRaises(ValueError):
            config.initialize_root(str(linked / 'Assets'))
        self.assertFalse((target / 'Assets').exists())

    @unittest.skipUnless(os.name == 'nt', 'Windows junction fixture')
    def test_real_windows_junction_is_not_followed(self):
        target = self.base / 'OutsideJunction'
        target.mkdir()
        (target / 'output').mkdir()
        linked = self.root / 'junction'
        result = subprocess.run(['cmd', '/d', '/c', 'mklink', '/J', str(linked), str(target)],
                                capture_output=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.assertEqual(result.returncode, 0, 'Cannot create an isolated junction test fixture')
        self.assertTrue(config._is_reparse(os.lstat(linked)))
        self.assertTrue(config.scan_excluded(str(linked)))
        self.assertFalse(config.scan_root_allowed(str(linked)))
        self.assertFalse(config.scan_root_allowed(str(linked / 'output')))
        self.assertEqual(config.detect_output_roots([str(self.root)]), [])
        with self.assertRaises(ValueError):
            config.initialize_root(str(linked / 'Assets'))
        self.assertFalse((target / 'Assets').exists())
        # Remove only the verified temporary junction, never its target tree.
        self.assertTrue(linked.absolute().is_relative_to(self.base.absolute()))
        self.assertTrue(config._is_reparse(os.lstat(linked)))
        os.rmdir(linked)
        self.assertTrue((target / 'output').is_dir())

    def test_output_discovery_handles_case_numbered_and_portable_layouts(self):
        expected = [self.root / '70_Output',
                    self.root / 'AI_APPS' / 'COMFYUI_PORTABLE' / 'ComfyUI' / 'OuTpUt',
                    self.root / 'ComfyUI_Main' / 'ComfyUI' / 'output']
        for path in expected:
            path.mkdir(parents=True)
        (self.root / 'MYCACHE' / 'output').mkdir(parents=True)
        (self.root / '00_AIHub_Library' / 'Output').mkdir(parents=True)
        actual = config.detect_output_roots([str(self.root)], ['mycache'])
        self.assertEqual({str(p) for p in expected}, set(actual))
        self.assertEqual(len(actual), len(set(actual)))

    def test_initialize_creates_standard_layout_only_when_called(self):
        root = self.base / 'NewDisk' / 'AI'
        self.assertEqual(config.detect_layout(str(root))['scan_roots'], [])
        self.assertFalse(root.exists())
        with mock.patch.object(config, 'save_config') as save:
            result = config.initialize_root(str(root))
        self.assertEqual(result['ai_root'], str(root))
        self.assertEqual(result['output_roots'], [str(root / '70_Output')])
        self.assertTrue(all((root / p).is_dir() for p in config.STANDARD_DIRS))
        save.assert_not_called()

    def test_initialize_preserves_existing_files(self):
        model = self.root / '20_Models' / 'mine.safetensors'
        model.parent.mkdir()
        model.write_bytes(b'unchanged fixture')
        config.initialize_root(str(self.root))
        self.assertEqual(model.read_bytes(), b'unchanged fixture')

    def test_initialize_validates_all_targets_before_mutation(self):
        (self.root / '70_Output').write_bytes(b'file occupies directory')
        with self.assertRaises(ValueError):
            config.initialize_root(str(self.root))
        self.assertFalse((self.root / '00_Management').exists())

    def test_unsafe_root_paths_are_rejected(self):
        for path in ('', None, [], 'relative', os.path.abspath(os.sep),
                     os.path.expanduser('~'), str(self.app), str(self.data / 'assets')):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    config.validate_asset_root(path, must_exist=False)
        with mock.patch.dict(os.environ, {'WINDIR': str(self.root)}):
            with self.assertRaises(ValueError):
                config.validate_asset_root(str(self.root / 'system' / 'assets'), must_exist=False)

    def test_reparse_root_or_ancestor_is_rejected_before_realpath(self):
        real_lstat = os.lstat
        class Linked:
            st_mode = stat.S_IFDIR
            st_file_attributes = 0x400
        def fake_lstat(path, *args, **kwargs):
            if os.path.normcase(str(path)) == os.path.normcase(str(self.root)):
                return Linked()
            return real_lstat(path, *args, **kwargs)
        with mock.patch.object(config.os, 'lstat', side_effect=fake_lstat):
            with self.assertRaises(ValueError):
                config.validate_asset_root(str(self.root / 'nested'), must_exist=False)
            self.assertEqual(config.detect_layout(str(self.root))['scan_roots'], [])
            self.assertEqual(config.detect_output_roots([str(self.root)]), [])

    def test_discovery_skips_directory_reparse_entries(self):
        linked = self.root / 'FakeJunction'
        linked.mkdir()
        (linked / 'output').mkdir()
        real_scandir = os.scandir
        class LinkedStat:
            st_mode = stat.S_IFDIR
            st_file_attributes = 0x400
        class Entry:
            path = str(linked)
            def stat(self, **kwargs):
                return LinkedStat()
        class Entries:
            def __enter__(self):
                return iter([Entry()])
            def __exit__(self, *args):
                pass
        def fake_scandir(path):
            return Entries() if str(path) == str(self.root) else real_scandir(path)
        with mock.patch.object(config.os, 'scandir', side_effect=fake_scandir):
            self.assertEqual(config.detect_output_roots([str(self.root)]), [])


if __name__ == '__main__':
    unittest.main()
