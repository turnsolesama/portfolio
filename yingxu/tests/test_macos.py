import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from macos_app import CloseGuard, Desktop
from yingxu.paths import default_data_root
from yingxu import macos


class MacAdaptersTests(unittest.TestCase):
    def test_default_directory_and_explicit_override(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve()
            with patch('yingxu.paths.sys.platform','darwin'), patch('yingxu.paths.Path.home',return_value=root), patch.dict(os.environ,{'YINGXU_DATA_DIR':''}):
                self.assertEqual(default_data_root(),root/'Library/Application Support/YingXu')
                self.assertFalse((root/'Library').exists())
                with patch.dict(os.environ,{'YINGXU_DATA_DIR':str(root/'override')}):
                    self.assertEqual(default_data_root(),root/'override')

    def test_close_cancel_stale_response_and_busy_request(self):
        guard=CloseGuard();first=guard.begin()
        self.assertIsNone(guard.begin())
        self.assertFalse(guard.respond('wrong-id',True))
        self.assertFalse(guard.respond(first,False))
        second=guard.begin()
        self.assertNotEqual(first,second)
        self.assertFalse(guard.respond(first,True))
        self.assertFalse(guard.respond(second,'true'))
        third=guard.begin();self.assertTrue(guard.respond(third,True))
        self.assertTrue(guard.allowed)

    def test_expired_close_never_destroys_window(self):
        guard=CloseGuard();request=guard.begin();guard.deadline=0
        self.assertFalse(guard.respond(request,True));self.assertFalse(guard.allowed)

    def test_bridge_validates_token_origin_and_request(self):
        app=Mock(token='local-token');host=Desktop(app,'http://127.0.0.1:8791')
        host.window=Mock();host.window.get_current_url.return_value=host.origin+'/?desktop=macos'
        bridge=host
        request=host.guard.begin();data={'action':'exit-response','requestId':request,'allow':True}
        self.assertFalse(bridge.post_message(data,'wrong'));host.window.destroy.assert_not_called()
        host.window.get_current_url.return_value='https://example.com/'
        self.assertFalse(bridge.post_message(data,'local-token'));host.window.destroy.assert_not_called()
        host.window.get_current_url.return_value=host.origin+'/?desktop=macos'
        self.assertTrue(bridge.post_message(data,'local-token'));host.window.destroy.assert_called_once()

    def test_finder_uses_argument_list_and_refuses_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();file=root/'literal $(name).txt';file.write_text('synthetic')
            with patch('yingxu.macos.subprocess.run') as run:
                macos.open_path(file,reveal=True)
                self.assertEqual(run.call_args.args[0],['/usr/bin/open','-R',str(file)])

    @unittest.skipUnless(sys.platform=='darwin','Requires Darwin renamex_np')
    def test_native_rename_refuses_existing_files_and_directories(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve()
            for is_directory in (False,True):
                a=root/('directory-a' if is_directory else 'a.txt')
                b=root/('directory-b' if is_directory else 'b.txt')
                if is_directory:a.mkdir();b.mkdir()
                else:a.write_bytes(b'original');b.write_bytes(b'keep')
                with self.assertRaises(FileExistsError):macos.rename_exclusive(a,b)
                self.assertTrue(a.exists());self.assertTrue(b.exists())
                c=root/('directory-c' if is_directory else 'c.txt')
                macos.rename_exclusive(a,c)
                self.assertFalse(a.exists());self.assertTrue(c.exists())
