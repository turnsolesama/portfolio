import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('release_packager', Path(__file__).resolve().parents[1] / 'tools' / 'package_release.py')
PACKAGER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACKAGER)


class ReleaseAllowlistTests(unittest.TestCase):
    def test_unknown_data_and_logs_are_not_collected(self):
        with tempfile.TemporaryDirectory(prefix='yingxu-package-test-') as temporary:
            root = Path(temporary).resolve()
            for name in ('README.md', 'private.sqlite3', 'server.log', 'settings.json'):
                (root / name).write_text('synthetic bytes', encoding='utf-8')
            with patch.object(PACKAGER, 'ROOT', root), patch.object(PACKAGER, 'FIXED', ('README.md',)), patch.object(PACKAGER, 'PATTERNS', ()):
                self.assertEqual(list(PACKAGER.files_to_package()), [root / 'README.md'])

    def test_personal_profile_paths_block_publication(self):
        with tempfile.TemporaryDirectory(prefix='yingxu-package-test-') as temporary:
            root = Path(temporary).resolve()
            private_path = 'C:' + '/Users/' + 'example-person/Documents/private.txt'
            (root / 'README.md').write_text(private_path, encoding='utf-8')
            with patch.object(PACKAGER, 'ROOT', root), patch.object(PACKAGER, 'FIXED', ('README.md',)), patch.object(PACKAGER, 'PATTERNS', ()):
                with self.assertRaises(ValueError):
                    list(PACKAGER.files_to_package())

    def test_missing_required_member_blocks_publication(self):
        with tempfile.TemporaryDirectory(prefix='yingxu-package-test-') as temporary:
            with patch.object(PACKAGER, 'ROOT', Path(temporary).resolve()), patch.object(PACKAGER, 'FIXED', ('YingXu.exe',)), patch.object(PACKAGER, 'PATTERNS', ()):
                with self.assertRaises(ValueError):
                    list(PACKAGER.files_to_package())

    def test_utf16_windows_launcher_is_checked_without_changing_bytes(self):
        with tempfile.TemporaryDirectory(prefix='yingxu-package-test-') as temporary:
            root = Path(temporary).resolve()
            path = root / 'start.vbs'
            raw = 'MsgBox "映序"'.encode('utf-16')
            path.write_bytes(raw)
            with patch.object(PACKAGER, 'ROOT', root), patch.object(PACKAGER, 'FIXED', ('start.vbs',)), patch.object(PACKAGER, 'PATTERNS', ()):
                self.assertEqual(list(PACKAGER.files_to_package()), [path])
                self.assertEqual(path.read_bytes(), raw)
                path.write_text('C:' + '/Users/' + 'example-person/private', encoding='utf-16')
                with self.assertRaises(ValueError):
                    list(PACKAGER.files_to_package())


if __name__ == '__main__':
    unittest.main()
