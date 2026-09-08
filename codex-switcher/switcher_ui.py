"""Native layout primitives with DPI-scaled spacing and fixed action areas."""
import ctypes
import tkinter as tk
from tkinter import ttk

BG = '#12151b'
PANEL = '#1b2029'
SURFACE = '#242b37'
FG = '#edf1f8'
MUTED = '#a0aabc'
ACCENT = '#b9c8ff'
BORDER = '#333d4e'
APP_USER_MODEL_ID = 'Turnsole.CodexSwitcher.Desktop'


def set_taskbar_identity(demo=False):
    """Give the Python-hosted window its own Windows taskbar group before Tk starts."""
    identity=APP_USER_MODEL_ID+('.Demo' if demo else '')
    setter=ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
    setter.argtypes=[ctypes.c_wchar_p]
    setter.restype=ctypes.c_long
    result=setter(identity)
    if result!=0:
        raise OSError('Windows 无法设置切换器任务栏标识', result)
    return identity


def enable_dpi():
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def style_app(root, scale=None):
    if scale is not None:
        root.tk.call('tk', 'scaling', scale * 96 / 72)
    root.scale = float(root.tk.call('tk', 'scaling')) * 72 / 96
    root.px = lambda value: max(1, round(value * root.scale))
    px = root.px
    s = ttk.Style(root)
    s.theme_use('clam')
    s.configure('.', background=BG, foreground=FG, font=('Microsoft YaHei UI', 10))
    s.configure('TFrame', background=BG)
    s.configure('Panel.TFrame', background=PANEL)
    s.configure('TLabel', background=BG, foreground=FG)
    s.configure('Muted.TLabel', foreground=MUTED)
    s.configure('Title.TLabel', font=('Microsoft YaHei UI', 18, 'bold'))
    s.configure('Section.TLabel', background=PANEL, font=('Microsoft YaHei UI', 12, 'bold'))
    s.configure('Panel.TLabel', background=PANEL)
    s.configure('PanelMuted.TLabel', background=PANEL, foreground=MUTED)
    s.configure('TButton', background=SURFACE, foreground=FG, borderwidth=0,
                padding=(px(12), px(8)), anchor='center')
    s.map('TButton', background=[('active', '#34405a'), ('disabled', '#202632')],
          foreground=[('disabled', '#69768a')])
    s.configure('Primary.TButton', background=ACCENT, foreground='#182345')
    s.map('Primary.TButton', background=[('active', '#d3ddff'), ('disabled', '#34405a')],
          foreground=[('active', '#182345'), ('disabled', '#8e9bb0')])
    s.configure('TMenubutton', background=SURFACE, foreground=FG, padding=(px(10), px(8)), borderwidth=0)
    s.configure('TEntry', fieldbackground=SURFACE, foreground=FG, insertcolor=FG,
                padding=px(8), bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER)
    s.configure('Treeview', background=PANEL, fieldbackground=PANEL, foreground=FG,
                rowheight=px(40), borderwidth=0, bordercolor=PANEL, lightcolor=PANEL, darkcolor=PANEL)
    s.configure('Treeview.Heading', background=SURFACE, foreground=MUTED,
                padding=(px(8), px(8)), relief='flat')
    s.map('Treeview', background=[('selected', '#35496a')], foreground=[('selected', '#ffffff')])
    s.configure('TCheckbutton', background=BG, foreground=FG, padding=px(4))
    s.map('TCheckbutton', background=[('active', SURFACE)])
    for orientation in ('Vertical', 'Horizontal'):
        name=orientation+'.TScrollbar'
        s.layout(name, [(orientation+'.Scrollbar.trough', {'sticky': 'nswe', 'children': [
            (orientation+'.Scrollbar.thumb', {'sticky': 'nswe', 'expand': '1'})]})])
        s.configure(name, background='#3a4558', troughcolor=PANEL, bordercolor=PANEL,
                    lightcolor='#3a4558', darkcolor='#3a4558', borderwidth=0,
                    width=px(8), arrowsize=px(8), gripcount=0)
        s.map(name, background=[('active', '#677a99'), ('pressed', '#8498b7')])
    s.configure('TPanedwindow', background=BG, sashwidth=px(12))
    return s


def fit_window(window, parent, width, height, minimum=(780, 520)):
    px = parent.px
    screen_w, screen_h = window.winfo_screenwidth(), window.winfo_screenheight()
    available_w, available_h = max(320, screen_w - px(32)), max(300, screen_h - px(80))
    width, height = min(px(width), available_w), min(px(height), available_h)
    window.minsize(min(px(minimum[0]), available_w), min(px(minimum[1]), available_h))
    x = (screen_w-width)//2 if parent is window else max(0, min(parent.winfo_rootx() + (parent.winfo_width() - width) // 2, screen_w - width))
    y = (screen_h-height)//2 if parent is window else max(0, min(parent.winfo_rooty() + (parent.winfo_height() - height) // 2, screen_h - height - px(40)))
    window.geometry(f'{width}x{height}+{x}+{y}')


class ScrollArea(ttk.Frame):
    """Only content scrolls; surrounding headers and action rows keep their space."""
    def __init__(self, parent, px, panel=False):
        super().__init__(parent, style='Panel.TFrame' if panel else 'TFrame')
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, background=PANEL if panel else BG, highlightthickness=0, borderwidth=0)
        self.bar = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.canvas.grid(row=0, column=0, sticky='nsew')
        self.bar.grid(row=0, column=1, sticky='ns')
        self.content = ttk.Frame(self.canvas, style='Panel.TFrame' if panel else 'TFrame')
        self.window_id = self.canvas.create_window(0, 0, anchor='nw', window=self.content)
        self.content.bind('<Configure>', self._content_changed)
        self.canvas.bind('<Configure>', self._canvas_changed)
        self.px = px

    def _content_changed(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))

    def _canvas_changed(self, event):
        self.canvas.itemconfigure(self.window_id, width=max(1, event.width))
        self._content_changed()

    def wheel(self, delta):
        bounds = self.canvas.bbox('all')
        if bounds and bounds[3] > self.canvas.winfo_height():
            self.canvas.yview_scroll(-1 if delta > 0 else 1, 'units')


class Dialog(tk.Toplevel):
    def __init__(self, parent, title, subtitle='', width=720, height=570, scroll=False):
        super().__init__(parent)
        self.title(title)
        self.configure(background=BG)
        self.transient(parent)
        if getattr(parent,'icon_path',None):
            self.iconbitmap(parent.icon_path)
        self.px = parent.px
        px = self.px
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        head = ttk.Frame(self, padding=(px(22), px(18), px(22), px(14)))
        head.grid(row=0, column=0, sticky='ew')
        head.columnconfigure(0, weight=1)
        ttk.Label(head, text=title, style='Title.TLabel').grid(row=0, column=0, sticky='w')
        self.subtitle = ttk.Label(head, text=subtitle, style='Muted.TLabel', justify='left')
        self.subtitle.grid(row=1, column=0, sticky='ew', pady=(px(5), 0))
        head.bind('<Configure>', lambda e: self.subtitle.configure(wraplength=max(80, e.width - px(44))))
        if scroll:
            self.scroll_area = ScrollArea(self, px)
            self.scroll_area.grid(row=1, column=0, sticky='nsew', padx=px(22))
            self.body = self.scroll_area.content
        else:
            self.body = ttk.Frame(self, padding=(px(22), 0, px(22), 0))
            self.body.grid(row=1, column=0, sticky='nsew')
        self.footer = ttk.Frame(self, padding=(px(22), px(14), px(22), px(18)))
        self.footer.grid(row=2, column=0, sticky='ew')
        self.footer.columnconfigure(0, weight=1)
        self.buttons = ttk.Frame(self.footer)
        self.buttons.grid(row=0, column=1, sticky='e')
        self.feedback = tk.StringVar()
        self.notice = ttk.Label(self.footer, textvariable=self.feedback, style='Muted.TLabel', justify='left')
        self.notice.grid(row=0, column=0, sticky='w', padx=(0, px(10)))
        self.footer.bind('<Configure>', lambda e: self.notice.configure(wraplength=max(px(70), e.width - self.buttons.winfo_reqwidth() - px(65))))
        self.bind('<Escape>', lambda _e: self.destroy())
        self.bind('<MouseWheel>', self._wheel, add='+')
        parent.update_idletasks()
        fit_window(self, parent, width, height, minimum=(560, 430))
        if getattr(parent, 'testing', False):
            self.geometry('+30000+30000')
        self.grab_set()
        parent.last_dialog = self

    def _wheel(self, event):
        if hasattr(self, 'scroll_area') and not isinstance(event.widget, (tk.Text, ttk.Treeview)):
            self.scroll_area.wheel(event.delta)

    def button(self, text, command, primary=False):
        button = ttk.Button(self.buttons, text=text, width=8, command=command,
                            style='Primary.TButton' if primary else 'TButton')
        button.pack(side='left', padx=(self.px(8), 0))
        return button


def table(parent, columns, px, height=6, selectmode='browse'):
    parent.columnconfigure(0, weight=1)
    parent.rowconfigure(0, weight=1)
    tree = ttk.Treeview(parent, columns=[item[0] for item in columns], show='headings',
                        selectmode=selectmode, height=height)
    for key, title, width in columns:
        tree.heading(key, text=title, anchor='w')
        tree.column(key, width=px(width), minwidth=px(55), stretch=True)
    vertical = ttk.Scrollbar(parent, orient='vertical', command=tree.yview)
    horizontal = ttk.Scrollbar(parent, orient='horizontal', command=tree.xview)
    tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
    tree.grid(row=0, column=0, sticky='nsew')
    vertical.grid(row=0, column=1, sticky='ns')
    horizontal.grid(row=1, column=0, sticky='ew')
    return tree
