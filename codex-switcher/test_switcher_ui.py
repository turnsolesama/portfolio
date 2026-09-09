"""Layout and interaction regressions. Always uses isolated demo data, off screen."""
import importlib.machinery
import importlib.util
import ctypes
import json
import struct
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


@unittest.skipUnless(sys.platform == 'win32', 'Windows Tk application')
class LayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        loader = importlib.machinery.SourceFileLoader('switcher_demo_test', str(Path(__file__).with_name('codex_switcher.pyw')))
        cls.mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
        with patch.object(sys, 'argv', ['test_switcher_ui', '--demo']):
            loader.exec_module(cls.mod)

    @classmethod
    def tearDownClass(cls):
        cls.mod.DEMO_DIR.cleanup()

    def setUp(self):
        self.mod.seed_demo()
        self.app = None
        self.errors = []
        self.message_patch = patch.object(self.mod.messagebox, 'showerror', side_effect=lambda *a, **k: self.errors.append(a))
        self.message_patch.start()

    def tearDown(self):
        if self.app:
            self.app.update_idletasks()
            self.app.destroy()
        self.message_patch.stop()
        self.assertFalse(self.errors, self.errors)

    def open_app(self, scale=1):
        self.app = self.mod.App(ui_scale=scale, testing=True)
        self.app.report_callback_exception = lambda *exc: self.errors.append(str(exc))
        self.app.update()
        return self.app

    def rect(self, widget):
        return (widget.winfo_rootx(), widget.winfo_rooty(), widget.winfo_width(), widget.winfo_height())

    def assert_inside(self, child, parent):
        x, y, w, h = self.rect(child)
        px, py, pw, ph = self.rect(parent)
        self.assertTrue(child.winfo_ismapped(), str(child))
        self.assertGreater(w, 1)
        self.assertGreater(h, 1)
        self.assertGreaterEqual(x, px)
        self.assertGreaterEqual(y, py)
        self.assertLessEqual(x+w, px+pw+1, (str(child), (x,y,w,h), (px,py,pw,ph)))
        self.assertLessEqual(y+h, py+ph+1, (str(child), (x,y,w,h), (px,py,pw,ph)))

    def assert_readable_button(self, button, parent):
        self.assert_inside(button, parent)
        font = self.mod.tkfont.Font(font=('Microsoft YaHei UI', 10))
        self.assertGreaterEqual(button.winfo_width(), font.measure(button.cget('text'))+self.app.px(8))

    def main_bounds(self):
        a = self.app
        for panel in (a.left_panel, a.right_panel):
            self.assert_inside(panel, a)
        for button in [a.apply_button, *a.action_buttons]:
            self.assert_readable_button(button, a.right_panel)
        for button in [a.add_button, a.import_button, a.more_button, a.refresh_button]:
            self.assert_readable_button(button, a.left_panel)
        self.assert_inside(a.tree, a.left_panel)
        self.assert_inside(a.detail_scroll, a.right_panel)
        self.assertGreater(a.tree.winfo_height(), a.px(90))
        self.assertGreater(a.panes.winfo_height()/a.winfo_height(), .6)
        self.assertLessEqual(a.detail_scroll.winfo_y()+a.detail_scroll.winfo_height(), a.detail_actions.winfo_y())
        for left, right in zip(a.action_buttons, a.action_buttons[1:]):
            lx, _, lw, _ = self.rect(left)
            self.assertLessEqual(lx+lw, self.rect(right)[0])

    def test_main_controls_fit_at_four_dpi_scales(self):
        for scale in (1, 1.25, 1.5, 2):
            with self.subTest(scale=scale):
                a = self.open_app(scale)
                a.tree.selection_set('studio'); a.update()
                self.main_bounds()
                w, h = a.minsize(); a.geometry(f'{w}x{h}+30000+30000'); a.update()
                self.main_bounds()
                a.destroy(); self.app = None

    def test_windows_identity_and_window_icons(self):
        a=self.open_app()
        shell=ctypes.windll.shell32
        getter=shell.GetCurrentProcessExplicitAppUserModelID
        getter.argtypes=[ctypes.POINTER(ctypes.c_wchar_p)];getter.restype=ctypes.c_long
        value=ctypes.c_wchar_p()
        self.assertEqual(getter(ctypes.byref(value)),0)
        try:self.assertEqual(value.value,'Turnsole.CodexSwitcher.Desktop.Demo')
        finally:
            free=ctypes.windll.ole32.CoTaskMemFree
            free.argtypes=[ctypes.c_void_p];free(ctypes.cast(value,ctypes.c_void_p))
        user=ctypes.windll.user32
        send=user.SendMessageW
        send.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_size_t,ctypes.c_ssize_t]
        send.restype=ctypes.c_void_p
        # Tk's outer wrapper is the native top-level seen by the Windows taskbar.
        hwnd=int(a.frame(),16)
        self.assertTrue(send(hwnd,0x007f,0,0),'Small taskbar/title icon missing')
        self.assertTrue(send(hwnd,0x007f,1,0),'Large taskbar icon missing')
        dialog=a.edit(a.profiles[0]);a.update()
        self.assertTrue(send(int(dialog.frame(),16),0x007f,1,0),'Dialog icon missing')

    def test_header_only_shows_plain_demo_context(self):
        a=self.open_app()
        self.assertEqual(a.environment_label.cget('style'),'Muted.TLabel')
        self.assertEqual(a.environment_label.cget('text'),'演示环境 · 隔离配置')
        a.destroy();self.app=None
        # Module paths were bound to its temporary directory at import; only
        # render the production header while explicitly blocking key lookup.
        self.assertEqual(self.mod.CONFIG_PATH.parent,Path(self.mod.DEMO_DIR.name))
        with patch.object(self.mod,'DEMO',False),patch.object(self.mod,'get_key',return_value=None):
            a=self.open_app()
            self.assertIsNone(a.environment_label)
            self.main_bounds()

    def test_icon_assets_and_dpi_headers(self):
        data=Path(__file__).with_name('switcher.ico').read_bytes()
        self.assertEqual(struct.unpack_from('<HHH',data),(0,1,7))
        sizes=[]
        for index in range(7):
            width,height,_,_,_,_,length,offset=struct.unpack_from('<BBBBHHII',data,6+index*16)
            sizes.append(width or 256)
            self.assertEqual(width,height)
            self.assertLessEqual(offset+length,len(data))
            self.assertEqual(struct.unpack_from('<I',data,offset)[0],40,'Tk needs BMP ICO entries')
        self.assertEqual(sorted(sizes),[16,24,32,48,64,128,256])
        for scale,expected in ((1,36),(1.25,45),(1.5,54),(2,72)):
            a=self.open_app(scale)
            self.assertEqual(a.brand_image.width(),expected)
            self.assertEqual(a.brand_image.height(),expected)
            self.assertTrue(a.brand_image.transparency_get(0,0))
            self.assertFalse(a.brand_image.transparency_get(expected//2,expected//2))
            self.assert_inside(a.brand_mark,a)
            a.destroy();self.app=None

    def test_grouped_details_wrap_and_badge_tracks_selection_at_four_scales(self):
        for scale in (1, 1.25, 1.5, 2):
            with self.subTest(scale=scale):
                a = self.open_app(scale)
                self.assertEqual(a.detail_badge.cget('style'), 'ActiveBadge.TLabel')
                a.tree.selection_set('studio'); a.update()
                self.assertEqual(a.detail_badge.cget('style'), 'Badge.TLabel')
                self.assertEqual(len(a.detail_fields), 6)
                for small in (False, True):
                    if small:
                        w,h=a.minsize();a.geometry(f'{w}x{h}+30000+30000');a.update()
                    for field,value in a.detail_fields:
                        self.assert_inside(value,field)
                        self.assertGreaterEqual(int(value.cget('wraplength')),a.px(65))
                    self.assert_inside(a.brand_mark,a)
                    self.main_bounds()
                a.destroy();self.app=None

    def test_status_badges_have_readable_contrast(self):
        a=self.open_app();style=self.mod.ttk.Style(a)
        def lum(color):
            values=[v/65535 for v in a.winfo_rgb(color)]
            values=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in values]
            return sum(v*w for v,w in zip(values,(.2126,.7152,.0722)))
        for name in ('Badge.TLabel','ActiveBadge.TLabel','WarningBadge.TLabel','Group.TLabel','Field.TLabel'):
            dark,light=sorted([lum(style.lookup(name,'background')),lum(style.lookup(name,'foreground'))])
            self.assertGreaterEqual((light+.05)/(dark+.05),4.5,name)

    def test_splitter_limits_preserve_action_space(self):
        a = self.open_app()
        for position in (1, a.panes.winfo_width()-1):
            a.panes.sashpos(0, position); a._clamp_panes(); a.update()
            self.main_bounds()

    def test_long_details_scroll_without_displacing_actions(self):
        a = self.open_app(1.5)
        p = {**a.profiles[0], 'name': '很长的服务名称' * 40, 'base_url': 'https://example.test/'+'long-path/'*45,
             'model': 'model-name-'*40, 'env_key': 'LONG_'+'K'*120}
        self.mod.core.save_profiles(self.mod.PROFILES_PATH, [p])
        a.refresh(p['id']); a.update()
        self.main_bounds()
        canvas = a.detail_scroll.canvas
        self.assertGreater(canvas.bbox('all')[3], canvas.winfo_height())
        canvas.yview_moveto(1); a.update()
        self.assertGreater(canvas.yview()[0], 0)
        self.main_bounds()

    def test_search_selection_and_clear(self):
        a = self.open_app()
        a.search.set('local'); a.update()
        self.assertEqual(set(a.tree.get_children()), {'__account__', 'local'})
        a.tree.selection_set('local'); a.update()
        self.assertEqual(a.selected()['id'], 'local')
        a.search.set(''); a.update()
        self.assertEqual(len(a.tree.get_children()), 3)
        self.assertEqual(a.selected()['id'], 'local')

    def test_dialog_footers_fit_normal_and_small_at_four_scales(self):
        payload = json.dumps([{'id': f'provider-{i}', 'name': '导入的服务 '+str(i),
                              'base_url': f'https://provider{i}.example/v1', 'http_headers': {'example': 'ignored'}} for i in range(80)])
        for scale in (1, 1.25, 1.5, 2):
            with self.subTest(scale=scale):
                a = self.open_app(scale)
                for make in [lambda: a.edit(a.profiles[0]), a.import_paste, lambda: a.preview_import(payload), a.restore]:
                    dialog = make(); a.update()
                    for small in (False, True):
                        if small:
                            w,h = dialog.minsize(); dialog.geometry(f'{w}x{h}+30000+30000'); a.update()
                        self.assert_inside(dialog.footer, dialog)
                        for button in dialog.buttons.winfo_children():
                            self.assert_readable_button(button, dialog)
                        body = getattr(dialog, 'scroll_area', dialog.body)
                        self.assert_inside(body, dialog)
                        self.assertGreater(body.winfo_height(), a.px(100))
                        self.assertLessEqual(body.winfo_y()+body.winfo_height(), dialog.footer.winfo_y())
                        if hasattr(dialog, 'tree'):
                            self.assert_inside(dialog.tree, dialog)
                            self.assertGreater(dialog.tree.winfo_height(), a.px(60))
                    dialog.destroy(); a.update()
                a.destroy(); self.app = None

    def test_copy_generates_unique_id_and_preserves_originals(self):
        a = self.open_app()
        existing = list(a.profiles)+[{**a.profiles[0], 'id': 'studio-copy', 'name': '已有副本'}]
        self.mod.core.save_profiles(self.mod.PROFILES_PATH, existing)
        a.refresh('studio'); a.update()
        config_before = self.mod.CONFIG_PATH.read_bytes()
        dialog = a.duplicate(); a.update()
        self.assertEqual(dialog.variables['id'].get(), 'studio-copy-2')
        self.assertEqual(dialog.entries['secret'].cget('show'), '●')
        dialog.save_button.invoke(); a.update()
        self.assertEqual(len(a.profiles), 4)
        self.assertEqual(a.profiles[:3], existing)
        self.assertEqual(self.mod.CONFIG_PATH.read_bytes(), config_before)

    def test_paste_preview_and_import_do_not_apply_or_store_keys(self):
        a = self.open_app()
        before = self.mod.CONFIG_PATH.read_bytes()
        dialog = a.import_paste(); a.update()
        dialog.text.insert('1.0', json.dumps({'name': 'Imported demo', 'base_url': 'https://import.example/v1', 'apiKey': 'FAKE_TEST_SECRET'}))
        dialog.parse_button.invoke(); a.update()
        preview = a.last_dialog
        self.assertEqual(preview.title(), '导入预览')
        self.assertFalse(preview.keep_keys.get())
        with patch.object(self.mod, 'set_key') as write_key:
            preview.save_button.invoke(); a.update(); write_key.assert_not_called()
        self.assertEqual(len(a.profiles), 3)
        self.assertNotIn('FAKE_TEST_SECRET', self.mod.PROFILES_PATH.read_text(encoding='utf-8'))
        self.assertEqual(self.mod.CONFIG_PATH.read_bytes(), before)

    def test_duplicate_import_and_empty_restore_disable_actions(self):
        a = self.open_app()
        dialog = a.preview_import(self.mod.core.export_profiles(a.profiles)); a.update()
        self.assertTrue(dialog.save_button.instate(['disabled']))
        dialog.destroy()
        dialog = a.restore(); a.update()
        self.assertTrue(dialog.restore_button.instate(['disabled']))

    def test_deepseek_curl_preview_import_edit_and_duplicate(self):
        a = self.open_app()
        before = self.mod.CONFIG_PATH.read_bytes()
        sample = Path(__file__).with_name('examples').joinpath('deepseek.curl').read_text(encoding='utf-8')
        dialog = a.import_paste(); a.update()
        dialog.text.insert('1.0', sample)
        dialog.parse_button.invoke(); a.update()
        preview = a.last_dialog
        values = preview.tree.item('0', 'values')
        self.assertEqual(values[2], 'deepseek-v4-pro')
        self.assertEqual(values[3], 'Responses / high')
        self.assertEqual(values[4], 'DEEPSEEK_API_KEY')
        self.assertTrue(preview.key_check.instate(['disabled']))
        self.assertIn('转换', preview.warning_text.get('1.0', 'end'))
        with patch.object(self.mod, 'set_key') as write_key:
            preview.save_button.invoke(); a.update(); write_key.assert_not_called()
        p = next(p for p in a.profiles if p['id'] == 'deepseek')
        self.assertEqual(p['reasoning_effort'], 'high')
        dialog = a.edit(p); a.update()
        self.assertEqual(dialog.variables['reasoning_effort'].get(), 'high')
        dialog.save_button.invoke(); a.update()
        self.assertEqual(next(p for p in a.profiles if p['id'] == 'deepseek')['reasoning_effort'], 'high')
        preview = a.preview_import(sample); a.update()
        self.assertTrue(preview.save_button.instate(['disabled']))
        self.assertEqual(self.mod.CONFIG_PATH.read_bytes(), before)

    def test_invalid_paste_keeps_user_text_for_repair(self):
        a = self.open_app(); dialog = a.import_paste(); a.update()
        value = 'curl https://example.test/responses -d @private.json'
        dialog.text.insert('1.0', value)
        with patch.object(self.mod.messagebox, 'showerror') as error:
            dialog.parse_button.invoke(); a.update(); error.assert_called_once()
        self.assertEqual(dialog.text.get('1.0', 'end-1c'), value)
        self.assertTrue(dialog.winfo_exists())

    def test_sdk_paste_and_file_import_preserve_config(self):
        a=self.open_app();before=self.mod.CONFIG_PATH.read_bytes()
        for name in ('deepseek.py','deepseek.mjs'):
            sample=Path(__file__).with_name('examples')/name
            self.mod.seed_demo();a.refresh();a.update()
            if name.endswith('.py'):
                dialog=a.import_paste();a.update()
                dialog.text.insert('1.0',sample.read_text(encoding='utf-8'))
                dialog.parse_button.invoke();a.update()
            else:
                with patch.object(self.mod.filedialog,'askopenfilename',return_value=str(sample)):
                    a.import_file();a.update()
            preview=a.last_dialog
            self.assertEqual(preview.tree.item('0','values')[2:4],('deepseek-v4-pro','Responses / high'))
            self.assertTrue(preview.key_check.instate(['disabled']))
            with patch.object(self.mod,'set_key') as save_key:
                preview.save_button.invoke();a.update();save_key.assert_not_called()
            self.assertEqual(self.mod.CONFIG_PATH.read_bytes(),before)
            self.assertEqual(next(p for p in a.profiles if p['id']=='deepseek')['reasoning_effort'],'high')

    def test_control_states_keep_readable_contrast(self):
        a=self.open_app();style=self.mod.ttk.Style(a)
        def luminance(color):
            rgb=a.winfo_rgb(color)
            values=[v/65535 for v in rgb]
            linear=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in values]
            return sum(v*w for v,w in zip(linear,(.2126,.7152,.0722)))
        def contrast(fg,bg):
            a,b=sorted((luminance(fg),luminance(bg)))
            return (b+.05)/(a+.05)
        for name in ('TButton','Primary.TButton','TMenubutton','TCombobox','Treeview.Heading','TCheckbutton'):
            for state in ((),('active',),('pressed','active'),('focus',),('disabled',),('disabled','active')):
                with self.subTest(style=name,state=state):
                    bg=style.lookup(name,'fieldbackground' if name=='TCombobox' else 'background',state)
                    fg=style.lookup(name,'foreground',state)
                    self.assertGreaterEqual(contrast(fg,bg),4.5)
                    if name in ('TMenubutton','TCombobox'):
                        self.assertGreaterEqual(contrast(style.lookup(name,'arrowcolor',state),bg),4.5)
                    if name!='Primary.TButton':self.assertLess(luminance(bg),.15)
        # Hover cannot override disabled colors through an earlier state rule.
        for name in ('TButton','Primary.TButton','TMenubutton','TCombobox'):
            self.assertEqual(style.lookup(name,'background',('disabled','active')),style.lookup(name,'background',('disabled',)))

    def test_legacy_invalid_row_does_not_block_library_or_hide_protocol(self):
        a = self.open_app()
        legacy = {**a.profiles[0], 'id':'legacy', 'env_key':'bad-key', 'wire_api':'chat'}
        self.mod.PROFILES_PATH.write_text(json.dumps({'profiles':a.profiles+[legacy]}),encoding='utf-8')
        a.refresh('legacy');a.update()
        self.assertEqual(len(a.tree.get_children()),4)
        self.assertTrue(a.apply_button.instate(['disabled']))
        self.assertEqual(a.detail_state.get(),'需要修正')
        self.main_bounds()
        dialog=a.edit(legacy);a.update()
        self.assertEqual(dialog.variables['wire_api'].get(),'chat')
        dialog.variables['wire_api'].set('responses');dialog.variables['env_key'].set('REPAIRED_KEY')
        dialog.save_button.invoke();a.update()
        self.assertFalse(a.apply_button.instate(['disabled']))
        self.assertEqual(len(a.profiles),3)


if __name__ == '__main__':
    unittest.main()
