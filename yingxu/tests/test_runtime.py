"""Runtime portability and update checks; all fixtures are temporary."""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from yingxu import __version__, runtime


class RuntimeTests(unittest.TestCase):
    def test_bundled_ffmpeg_without_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            exe = root / 'runtime/ffmpeg/bin/ffmpeg.exe'
            exe.parent.mkdir(parents=True)
            exe.write_bytes(b'fixture only')
            with patch.object(runtime, 'APP_ROOT', root), patch.dict(os.environ, {'PATH': ''}):
                self.assertEqual(runtime.ffmpeg_path(), str(exe))

    def test_source_checkout_can_use_system_tool(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(runtime, 'APP_ROOT', Path(temporary)), patch.object(runtime.shutil, 'which', return_value='system-tool'):
                self.assertEqual(runtime.ffmpeg_path(), 'system-tool')

    def test_missing_pillow_is_reported(self):
        runtime.image_support.cache_clear()
        try:
            with patch.dict('sys.modules', {'PIL': None}):
                self.assertFalse(runtime.image_support())
        finally:
            runtime.image_support.cache_clear()

    def test_old_background_is_rejected_without_termination(self):
        loader = importlib.machinery.SourceFileLoader('runtime_launcher_fixture', str(Path(__file__).resolve().parents[1] / 'launcher.pyw'))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        launcher = importlib.util.module_from_spec(spec)
        loader.exec_module(launcher)
        self.assertIsNone(launcher.require_current_service(None))
        self.assertEqual(launcher.require_current_service({'version': __version__}), {'version': __version__})
        with self.assertRaisesRegex(RuntimeError, '旧版'):
            launcher.require_current_service({'version': '0.2.1'})


if __name__ == '__main__':
    unittest.main()
