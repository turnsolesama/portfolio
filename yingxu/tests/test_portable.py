import importlib.machinery
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from yingxu.paths import default_data_root, default_project_root, instance_id


class PortablePathsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='yingxu-portable-')
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {
            'YINGXU_DATA_DIR': '', 'YINGXU_PROJECTS_DIR': '',
            'LOCALAPPDATA': str(self.root / 'Local'),
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_defaults_are_per_user_and_do_not_create_directories(self):
        with patch('yingxu.paths.documents_directory', return_value=self.root / '文档'):
            self.assertEqual(default_data_root(), self.root / 'Local' / 'YingXu')
            self.assertEqual(default_project_root(), self.root / '文档' / 'YingXu' / 'Projects')
        self.assertEqual(list(self.root.iterdir()), [])

    def test_explicit_unicode_paths_override_both_defaults(self):
        with patch.dict(os.environ, {'YINGXU_DATA_DIR': str(self.root / '数据 空间'),
                                     'YINGXU_PROJECTS_DIR': str(self.root / '剧集 项目')}):
            self.assertEqual(default_data_root(), self.root / '数据 空间')
            self.assertEqual(default_project_root(), self.root / '剧集 项目')

    def test_relative_override_is_rejected(self):
        for key, function in [('YINGXU_DATA_DIR', default_data_root), ('YINGXU_PROJECTS_DIR', default_project_root)]:
            with patch.dict(os.environ, {key: 'relative/folder'}):
                with self.assertRaises(ValueError):
                    function()

    def test_identity_is_normalized_and_separates_data_roots(self):
        self.assertEqual(instance_id(self.root / '.'), instance_id(self.root))
        self.assertNotEqual(instance_id(self.root / 'one'), instance_id(self.root / 'two'))
        self.assertEqual(len(instance_id(self.root)), 64)

    def test_identity_preserves_non_ascii_characters_across_runtimes(self):
        import hashlib
        translation = str.maketrans('abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ')
        for name in ('Straße', 'ﬀ', 'ς', '中文', 'Ascii'):
            path = self.root / name
            path.mkdir()
            expected = hashlib.sha256(str(path.resolve()).translate(translation).encode()).hexdigest()
            self.assertEqual(instance_id(path), expected)

    def test_launcher_uses_same_defaults_and_rejects_foreign_service(self):
        loader = importlib.machinery.SourceFileLoader('portable_launcher', str(Path(__file__).resolve().parents[1] / 'launcher.pyw'))
        module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
        with patch('yingxu.paths.documents_directory', return_value=self.root / '文档'):
            loader.exec_module(module)
            self.assertEqual(module.DATA, default_data_root())
            self.assertEqual(module.PROJECTS, default_project_root())
        for identity, expected in [(instance_id(module.DATA), True), ('other-directory', False), (None, False)]:
            import json
            raw = json.dumps(dict(app='yingxu', ok=True, instance_id=identity)).encode()
            with patch.object(module.http.client, 'HTTPConnection') as connection:
                response = connection.return_value.getresponse.return_value
                response.status = 200
                response.read.return_value = raw
                self.assertEqual(bool(module.health(12345)), expected)


if __name__ == '__main__':
    unittest.main()
