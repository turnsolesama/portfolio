# -*- coding: utf-8 -*-
"""Codex Switcher 2.1 — local Windows provider workspace."""
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont
from switcher_ui import BG, PANEL, FG, MUTED, ACCENT, SURFACE, Dialog, ScrollArea, table, style_app, fit_window, enable_dpi, set_taskbar_identity
import tomllib
import uuid
import winreg
import switcher_core as core

APP_DIR=Path(__file__).resolve().parent
DEMO='--demo' in sys.argv
DEMO_DIR=tempfile.TemporaryDirectory(prefix='switcher-demo-') if DEMO else None
DATA_DIR=Path(DEMO_DIR.name) if DEMO else APP_DIR
CONFIG_PATH=(DATA_DIR/'config.toml') if DEMO else Path(os.environ.get('CODEX_HOME') or Path.home()/'.codex')/'config.toml'
PROFILES_PATH=DATA_DIR/'profiles.json'
enable_dpi()

def get_key(name):
    if DEMO:return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,'Environment') as key:return winreg.QueryValueEx(key,name)[0]
    except OSError:return None

def set_key(name,value):
    if DEMO:return
    if not core.ENV.fullmatch(name) or name.upper() in core.RESERVED:raise ValueError('密钥变量名不合法')
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,'Environment') as key:
        if value is None:
            try:winreg.DeleteValue(key,name)
            except FileNotFoundError:pass
        else:winreg.SetValueEx(key,name,0,winreg.REG_SZ,value)
    result=ctypes.c_size_t()
    ctypes.windll.user32.SendMessageTimeoutW(0xffff,0x1a,0,ctypes.c_wchar_p('Environment'),2,1000,ctypes.byref(result))

def seed_demo():
    core.atomic_write(CONFIG_PATH, 'model = "demo-model"\n[desktop]\nexample = true\n')
    core.save_profiles(PROFILES_PATH, [
        {'id':'studio','name':'创作工作室','base_url':'https://studio.example/v1','env_key':'DEMO_API_KEY','model':'creative-model','wire_api':'responses'},
        {'id':'local','name':'本地推理服务','base_url':'http://127.0.0.1:8080/v1','env_key':'LOCAL_API_KEY','model':'local-model','wire_api':'responses'}])


class App(tk.Tk):
    def __init__(self, ui_scale=None, testing=False):
        # Windows otherwise groups this GUI with pythonw.exe and uses Python's icon.
        self.taskbar_identity=set_taskbar_identity(demo=DEMO)
        super().__init__()
        self.testing=testing
        self.title('Codex Switcher '+core.VERSION+' · 服务工作台' + (' · 演示' if DEMO else ''))
        self.configure(bg=BG)
        style_app(self, ui_scale)
        px = self.px
        fit_window(self, self, 1120, 750, minimum=(900, 570))
        if testing:
            self.geometry('+30000+30000')
        self.icon_path=str(APP_DIR/'switcher.ico')
        try:
            self.iconbitmap(default=self.icon_path)
            self.iconbitmap(self.icon_path)
        except tk.TclError:
            pass
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        head = ttk.Frame(self, padding=(px(20), px(16), px(20), px(12)))
        head.grid(row=0, column=0, sticky='ew')
        head.columnconfigure(0, weight=1)
        ttk.Label(head, text='Codex Switcher', style='Title.TLabel').grid(row=0, column=0, sticky='w')
        ttk.Label(head, text='服务配置工作台', style='Muted.TLabel').grid(row=1, column=0, sticky='w', pady=(px(3),0))
        ttk.Label(head, text='演示环境 · 隔离配置' if DEMO else '本机管理 · '+core.VERSION,
                  style='Muted.TLabel').grid(row=0, column=1, rowspan=2, sticky='e')
        self.status = tk.StringVar()
        self.status_display = tk.StringVar()
        self.count = tk.StringVar()
        status = ttk.Frame(self, style='Panel.TFrame', padding=(px(14), px(10)))
        status.grid(row=1, column=0, sticky='ew', padx=px(20), pady=(0,px(14)))
        status.columnconfigure(1, weight=1)
        ttk.Label(status, text='当前配置', style='PanelMuted.TLabel').grid(row=0,column=0,padx=(0,px(14)))
        self.current_label = ttk.Label(status, textvariable=self.status_display, style='Panel.TLabel')
        self.current_label.grid(row=0,column=1,sticky='ew')
        self.status.trace_add('write', lambda *_: self._fit_status())
        self.current_label.bind('<Configure>', lambda _e: self._fit_status())
        self.panes = ttk.Panedwindow(self, orient='horizontal')
        self.panes.grid(row=2,column=0,sticky='nsew',padx=px(20))
        left = ttk.Frame(self.panes, style='Panel.TFrame', padding=px(14))
        right = ttk.Frame(self.panes, style='Panel.TFrame')
        self.left_panel, self.right_panel = left, right
        self.panes.add(left, weight=3)
        self.panes.add(right, weight=2)
        self._pane_width = 0
        self.panes.bind('<Configure>', self._resize_panes)
        self.panes.bind('<ButtonRelease-1>', self._clamp_panes)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(3, weight=1)
        caption = ttk.Frame(left, style='Panel.TFrame')
        caption.grid(row=0,column=0,sticky='ew',pady=(0,px(12)))
        caption.columnconfigure(0,weight=1)
        ttk.Label(caption,text='服务库',style='Section.TLabel').grid(row=0,column=0,sticky='w')
        self.view_count = tk.StringVar()
        ttk.Label(caption,textvariable=self.view_count,style='PanelMuted.TLabel').grid(row=0,column=1,sticky='e')
        self.toolbar = ttk.Frame(left,style='Panel.TFrame')
        self.toolbar.grid(row=1,column=0,sticky='ew',pady=(0,px(12)))
        self.toolbar.columnconfigure(3,weight=1)
        self.add_button = ttk.Button(self.toolbar,text='＋ 新增',width=6,style='Primary.TButton',command=self.edit)
        self.add_button.grid(row=0,column=0,padx=(0,px(8)))
        self.import_button = ttk.Menubutton(self.toolbar,text='导入配置',width=8)
        import_menu = tk.Menu(self.import_button,tearoff=False,bg=SURFACE,fg=FG,activebackground='#35496a',activeforeground=FG)
        import_menu.add_command(label='从文件导入…',command=self.import_file)
        import_menu.add_command(label='粘贴配置…',command=self.import_paste)
        self.import_button.configure(menu=import_menu)
        self.import_button.grid(row=0,column=1,padx=(0,px(8)))
        self.more_button = ttk.Menubutton(self.toolbar,text='更多',width=5)
        more = tk.Menu(self.more_button,tearoff=False,bg=SURFACE,fg=FG,activebackground='#35496a',activeforeground=FG)
        more.add_command(label='导出配置（不含密钥）…',command=self.export)
        more.add_command(label='配置备份与恢复…',command=self.restore)
        self.more_button.configure(menu=more)
        self.more_button.grid(row=0,column=2)
        self.refresh_button = ttk.Button(self.toolbar,text='刷新',width=4,command=self.refresh)
        self.refresh_button.grid(row=0,column=4,sticky='e',padx=(px(8),0))
        search_row = ttk.Frame(left,style='Panel.TFrame')
        search_row.grid(row=2,column=0,sticky='ew',pady=(0,px(12)))
        search_row.columnconfigure(1,weight=1)
        ttk.Label(search_row,text='搜索',style='PanelMuted.TLabel').grid(row=0,column=0,padx=(0,px(8)))
        self.search = tk.StringVar()
        self.search.trace_add('write',lambda *_:self.render())
        self.search_entry = ttk.Entry(search_row,textvariable=self.search)
        self.search_entry.grid(row=0,column=1,sticky='ew')
        ttk.Button(search_row,text='×',width=2,command=lambda:self.search.set('')).grid(row=0,column=2,padx=(px(6),0))
        self.bind('<Control-f>',lambda _e:self.search_entry.focus_set())
        table_frame = ttk.Frame(left,style='Panel.TFrame')
        table_frame.grid(row=3,column=0,sticky='nsew')
        self.tree = table(table_frame,[('name','服务名称',210),('model','模型',160),('key','密钥状态',95)],px,height=6)
        self.tree.bind('<<TreeviewSelect>>',lambda _e:self.details())
        self.tree.bind('<Double-1>',lambda _e:self.edit(self.selected()) if self.selected() else None)
        self.tree.bind('<Configure>',self._resize_columns)
        ttk.Label(left,text='选择服务查看详情；双击编辑。',style='PanelMuted.TLabel').grid(row=4,column=0,sticky='w',pady=(px(9),0))
        right.columnconfigure(0,weight=1)
        right.rowconfigure(1,weight=1)
        detail_head = ttk.Frame(right,style='Panel.TFrame',padding=(px(18),px(15),px(18),px(10)))
        detail_head.grid(row=0,column=0,sticky='ew')
        detail_head.columnconfigure(0,weight=1)
        ttk.Label(detail_head,text='服务详情',style='Section.TLabel').grid(row=0,column=0,sticky='w')
        self.detail_state = tk.StringVar()
        ttk.Label(detail_head,textvariable=self.detail_state,style='PanelMuted.TLabel').grid(row=0,column=1,sticky='e')
        self.detail_scroll = ScrollArea(right,px,panel=True)
        self.detail_scroll.grid(row=1,column=0,sticky='nsew',padx=(px(18),px(8)))
        self.detail_content = self.detail_scroll.content
        self.detail_content.columnconfigure(0,weight=1)
        self.detail_content.bind('<Configure>',self._wrap_detail,add='+')
        self.detail_labels = []
        self.detail_actions = ttk.Frame(right,style='Panel.TFrame',padding=(px(18),px(12),px(18),px(16)))
        self.detail_actions.grid(row=2,column=0,sticky='ew')
        self.detail_actions.columnconfigure(0,weight=1)
        self.apply_button = ttk.Button(self.detail_actions,text='应用所选配置',style='Primary.TButton',command=self.apply)
        self.apply_button.grid(row=0,column=0,sticky='ew',pady=(0,px(8)))
        row = ttk.Frame(self.detail_actions,style='Panel.TFrame')
        row.grid(row=1,column=0,sticky='ew')
        self.action_buttons = []
        for column,(label,action) in enumerate([('编辑服务',lambda:self.edit(self.selected())),('创建副本',self.duplicate),('移除记录',self.remove)]):
            row.columnconfigure(column,weight=1,uniform='actions')
            button = ttk.Button(row,text=label,width=4,command=action)
            button.grid(row=0,column=column,sticky='ew',padx=(0 if column==0 else px(4),0 if column==2 else px(4)))
            self.action_buttons.append(button)
        self.apply_hint = ttk.Label(self.detail_actions,text='应用前自动备份；重开 Codex 后生效。',style='PanelMuted.TLabel',justify='left')
        self.apply_hint.grid(row=2,column=0,sticky='ew',pady=(px(10),0))
        self.detail_actions.bind('<Configure>',lambda e:self.apply_hint.configure(wraplength=max(px(100),e.width-px(36))))
        footer = ttk.Frame(self,padding=(px(20),px(10),px(20),px(12)))
        footer.grid(row=3,column=0,sticky='ew')
        footer.columnconfigure(0,weight=1)
        self.feedback = tk.StringVar(value='就绪。导入后需手动应用；导出不包含密钥。')
        self.feedback_label = ttk.Label(footer,textvariable=self.feedback,style='Muted.TLabel',justify='left')
        self.feedback_label.grid(row=0,column=0,sticky='ew')
        ttk.Label(footer,text='v'+core.VERSION,style='Muted.TLabel').grid(row=0,column=1,padx=(px(12),0))
        footer.bind('<Configure>',lambda e:self.feedback_label.configure(wraplength=max(px(100),e.width-px(120))))
        self.bind('<MouseWheel>',self._detail_wheel,add='+')
        self.profiles=[]
        self.refresh()

    def _fit_status(self):
        value=self.status.get()
        available=max(self.px(100),self.current_label.winfo_width())
        font=tkfont.Font(font=self.current_label.cget('font'))
        if font.measure(value)>available:
            while value and font.measure(value+'…')>available:
                value=value[:-1]
            value+='…'
        self.status_display.set(value)

    def _resize_panes(self,event):
        if event.width!=self._pane_width:
            self._pane_width=event.width
            self.after_idle(lambda:self._clamp_panes(initial=True))

    def _clamp_panes(self,_event=None,initial=False):
        width=self.panes.winfo_width()
        if width<2:return
        minimum_left=min(self.px(360),int(width*.54))
        minimum_right=min(self.px(300),int(width*.43))
        position=int(width*.55) if initial else self.panes.sashpos(0)
        self.panes.sashpos(0,max(minimum_left,min(position,width-minimum_right)))

    def _resize_columns(self,event):
        width=max(180,event.width-self.px(3))
        for key,fraction in [('name',.43),('model',.35),('key',.22)]:
            self.tree.column(key,width=int(width*fraction),minwidth=self.px(55))

    def _wrap_detail(self,event):
        for label in self.detail_labels:
            label.configure(wraplength=max(self.px(100),event.width-self.px(14)))

    def _detail_wheel(self,event):
        widget=event.widget
        while widget is not None:
            if widget==self.detail_scroll:
                self.detail_scroll.wheel(event.delta)
                break
            widget=getattr(widget,'master',None)

    def note(self,text):self.feedback.set(text)
    def error(self,e):messagebox.showerror('操作未完成',str(e),parent=self)
    def selected(self):
        ids=self.tree.selection()
        return next((p for p in self.profiles if ids and p['id']==ids[0]),None)
    def refresh(self,select=None):
        try:self.profiles=core.load_profiles(PROFILES_PATH);self.profile_hash=core.file_hash(PROFILES_PATH)
        except (ValueError,OSError) as e:self.error(e);return
        try:
            data=tomllib.loads(CONFIG_PATH.read_text(encoding='utf-8-sig')) if CONFIG_PATH.exists() else {}
            self.active=data.get('model_provider','__account__');self.current_model=data.get('model','未指定')
            self.status.set(('官方账号登录' if self.active in {'__account__','openai'} else 'API 服务 · '+self.active)+'  /  '+self.current_model)
        except (ValueError,OSError):self.active='';self.current_model='';self.status.set('Codex 配置无法解析，请检查配置或恢复备份')
        self.count.set(f'{len(self.profiles)} 个 API 服务  ·  Responses 接口  ·  应用配置前自动备份'+('  ·  演示环境' if DEMO else ''))
        self.render(select)
    def render(self,select=None):
        previous=select or (self.tree.selection()[0] if self.tree.selection() else None)
        self.tree.delete(*self.tree.get_children())
        self.tree.insert('','end',iid='__account__',values=('官方账号登录','使用现有模型','官方登录'))
        q=self.search.get().strip().casefold()
        for p in self.profiles:
            if q and q not in ' '.join(p.values()).casefold():continue
            active=self.active in {p['id'],'switcher_'+p['id']}
            key_state='需修正' if core.profile_issue(p) else ('已设置' if get_key(p['env_key']) else '待设置')
            self.tree.insert('','end',iid=p['id'],values=(('● ' if active else '')+p['name'],p['model'] or '沿用当前模型',key_state))
        choose=previous if previous and self.tree.exists(previous) else '__account__'
        self.tree.selection_set(choose);self.tree.see(choose);self.view_count.set(f'{len(self.tree.get_children())-1} 个 API 服务');self.details()
    def details(self):
        p=self.selected()
        for widget in self.detail_content.winfo_children():widget.destroy()
        self.detail_labels=[]
        px=self.px
        name=p['name'] if p else '官方账号登录'
        issue=core.profile_issue(p) if p else ''
        active=self.active in ({p['id'],'switcher_'+p['id']} if p else {'__account__','openai'})
        self.detail_state.set('需要修正' if issue else ('当前使用中' if active else '未应用'))
        self.apply_button.configure(state='disabled' if issue else 'normal')
        title=ttk.Label(self.detail_content,text=name,style='Panel.TLabel',font=('Microsoft YaHei UI',16,'bold'),justify='left')
        title.grid(row=0,column=0,sticky='ew',pady=(px(3),px(4)));self.detail_labels.append(title)
        subtitle=ttk.Label(self.detail_content,text=('API 服务 · '+p['id']) if p else '使用已有的官方登录信息',style='PanelMuted.TLabel',justify='left')
        subtitle.grid(row=1,column=0,sticky='ew',pady=(0,px(20)));self.detail_labels.append(subtitle)
        fields=[('服务地址',p['base_url']),('模型',p['model'] or '沿用当前配置中的模型'),('密钥变量',p['env_key']),('密钥状态','需先修正配置' if issue else ('已设置' if get_key(p['env_key']) else '待设置 · 编辑服务后补充')),('接口协议',p['wire_api'] or 'Responses')] if p else [('登录方式','Codex 官方账号'),('当前模型',self.current_model or '未指定'),('配置说明','切回官方模式后，保留现有登录信息、工作区和其他设置。')]
        if p:fields.append(('推理强度',p.get('reasoning_effort') or '沿用当前配置'))
        if issue:fields.insert(0,('需要修正',issue+'。原记录已保留，请编辑后再应用。'))
        for index,(label,value) in enumerate(fields):
            ttk.Label(self.detail_content,text=label,style='PanelMuted.TLabel').grid(row=2+index*2,column=0,sticky='w',pady=(0,px(5)))
            widget=ttk.Label(self.detail_content,text=value,style='Panel.TLabel',justify='left')
            widget.grid(row=3+index*2,column=0,sticky='ew',pady=(0,px(18)));self.detail_labels.append(widget)
        for button in self.action_buttons:button.configure(state='normal' if p else 'disabled')
        self.detail_scroll.canvas.yview_moveto(0)
        self._wrap_detail(type('Size',(),{'width':max(self.px(200),self.detail_content.winfo_width())})())

    def edit(self,profile=None,duplicate=False):
        original_id=profile['id'] if profile and not duplicate else None
        defaults=dict(profile or {'id':'','name':'','base_url':'https://','env_key':'','model':''})
        if duplicate:
            base=defaults['id'][:45]+'-copy';candidate=base;number=2
            while any(p['id']==candidate for p in self.profiles):
                candidate=base+'-'+str(number);number+=1
            defaults.update(id=candidate,name=defaults['name'][:110]+' 副本',env_key='')
        w=Dialog(self,'创建服务副本' if duplicate else ('编辑服务' if profile else '新增服务'),
                 '保存服务信息后，可在主界面手动应用配置。',width=720,height=620,scroll=True)
        form=w.body;px=self.px
        for column in (0,1):form.columnconfigure(column,weight=1,uniform='form')
        variables={};w.entries={}
        fields=[('name','显示名称',0,0,1),('id','服务 ID',0,1,1),('base_url','API 地址',1,0,2),
                ('model','模型名称 · 可留空',2,0,1),('env_key','密钥变量 · 可自动生成',2,1,1),('secret','API Key · 隐藏输入',3,0,2)]
        for key,label,row,column,span in fields:
            cell=ttk.Frame(form,padding=(0,0,px(12) if span==1 and column==0 else 0,px(14)))
            cell.grid(row=row,column=column,columnspan=span,sticky='ew');cell.columnconfigure(0,weight=1)
            ttk.Label(cell,text=label,style='Muted.TLabel').grid(row=0,column=0,sticky='w',pady=(0,px(6)))
            var=tk.StringVar(value=defaults.get(key,''));variables[key]=var
            entry=ttk.Entry(cell,textvariable=var,show='●' if key=='secret' else '',width=12)
            entry.grid(row=1,column=0,sticky='ew');w.entries[key]=entry
        protocol=ttk.Frame(form);protocol.grid(row=4,column=0,columnspan=2,sticky='ew',pady=(0,px(12)))
        ttk.Label(protocol,text='接口协议',style='Muted.TLabel').pack(side='left',padx=(0,px(12)))
        variables['wire_api']=tk.StringVar(value=defaults.get('wire_api') or 'responses')
        choices=list(dict.fromkeys(['responses',variables['wire_api'].get()]))
        w.entries['wire_api']=ttk.Combobox(protocol,textvariable=variables['wire_api'],values=choices,state='readonly',width=14)
        w.entries['wire_api'].pack(side='left')
        effort=ttk.Frame(form);effort.grid(row=5,column=0,columnspan=2,sticky='ew',pady=(0,px(12)))
        ttk.Label(effort,text='推理强度 · 留空沿用',style='Muted.TLabel').pack(side='left',padx=(0,px(12)))
        variables['reasoning_effort']=tk.StringVar(value=defaults.get('reasoning_effort',''))
        effort_choices=list(dict.fromkeys(['',*core.EFFORTS,variables['reasoning_effort'].get()]))
        w.entries['reasoning_effort']=ttk.Combobox(effort,textvariable=variables['reasoning_effort'],values=effort_choices,state='readonly',width=14)
        w.entries['reasoning_effort'].pack(side='left')
        hint=ttk.Label(form,text='API Key 留空时保留该变量的原值。模型、推理强度留空时沿用当前配置。旧版接口配置保留原值；请先确认服务支持 Responses，再修改协议。',style='Muted.TLabel',justify='left')
        hint.grid(row=6,column=0,columnspan=2,sticky='ew',pady=(0,px(12)))
        form.bind('<Configure>',lambda e:hint.configure(wraplength=max(px(100),e.width-px(16))),add='+')
        w.variables=variables;w.feedback.set('仅保存服务，不立即切换。')
        expected=self.profile_hash
        def save():
            try:
                raw={k:v.get().strip() for k,v in variables.items()};secret=raw.pop('secret')
                if not raw['env_key']:raw['env_key']='CODEX_'+core.slug(raw['id']).upper().replace('-','_')+'_API_KEY'
                p=core.validate(raw)
                if any(x['id']==p['id'] and x['id']!=original_id for x in self.profiles):raise ValueError('服务 ID 已存在')
                if secret and (len(secret)>8192 or any(c in secret for c in '\r\n\0')):raise ValueError('API Key 格式不合法')
                old=get_key(p['env_key'])
                if secret and old and not messagebox.askyesno('更新密钥','该用户环境变量已有值。确认更新？',parent=w):return
                records=[x for x in self.profiles if x['id']!=original_id]+[p]
                if secret:set_key(p['env_key'],secret)
                try:core.save_profiles(PROFILES_PATH,records,expected)
                except Exception:
                    if secret:set_key(p['env_key'],old)
                    raise
                w.destroy();self.refresh(p['id']);self.note('服务已保存；尚未切换 Codex。')
            except (ValueError,OSError) as e:messagebox.showerror('无法保存',str(e),parent=w)
        w.button('取消',w.destroy)
        w.save_button=w.button('保存服务',save,primary=True)
        w.entries['name'].focus_set()
        return w
    def duplicate(self):
        p=self.selected()
        if p:return self.edit(p,duplicate=True)
    def remove(self):
        p=self.selected()
        if not p:return self.note('官方登录入口不可移除。')
        if self.active in {p['id'],'switcher_'+p['id']}:return self.note('此服务仍在使用，请先切换其他配置，再移除。')
        if not messagebox.askyesno('移除服务','只移除列表记录，保留环境变量和 Codex 配置。继续？',parent=self):return
        try:core.save_profiles(PROFILES_PATH,[x for x in self.profiles if x['id']!=p['id']],self.profile_hash);self.refresh();self.note('服务记录已移除。')
        except (ValueError,OSError) as e:self.error(e)
    def apply(self):
        if not self.tree.selection():return
        p=self.selected()
        try:
            text=CONFIG_PATH.read_text(encoding='utf-8-sig') if CONFIG_PATH.exists() else ''
            digest=core.file_hash(CONFIG_PATH);core.render_config(text,p)
            if p and not get_key(p['env_key']) and not DEMO:raise ValueError('密钥变量尚未设置，请编辑服务后再应用')
            target=p['name']+'\n'+p['base_url']+'\n模型：'+(p['model'] or '沿用当前')+'\n推理强度：'+(p.get('reasoning_effort') or '沿用当前') if p else '官方账号登录'
            if not messagebox.askyesno('应用配置',target+'\n\n将备份并更新 config.toml。不会自动关闭当前任务。继续？',parent=self):return
            core.apply_config(CONFIG_PATH,p,digest);self.refresh(p['id'] if p else '__account__');self.note('已应用。请自行关闭并重开 Codex；当前运行中的任务未被结束。')
        except (ValueError,OSError) as e:self.error(e)
    def import_file(self):
        path=filedialog.askopenfilename(parent=self,title='选择服务配置或 cURL 示例',filetypes=[('配置 / cURL 文件','*.json *.toml *.env *.curl *.txt *.sh'),('所有文件','*')])
        if not path:return
        try:
            if Path(path).stat().st_size>2*1024*1024:raise ValueError('导入文件上限为 2 MiB')
            self.preview_import(Path(path).read_text(encoding='utf-8-sig'))
        except (ValueError,OSError,UnicodeError) as e:self.error(e)
    def import_paste(self):
        w=Dialog(self,'粘贴配置','支持 cURL、JSON、Codex TOML 和 .env；仅解析文本，不执行命令。',width=800,height=600)
        w.body.columnconfigure(0,weight=1);w.body.rowconfigure(0,weight=1)
        text=tk.Text(w.body,bg=PANEL,fg=FG,insertbackground=FG,relief='flat',wrap='word',
                     font=('Consolas',11),width=20,height=6,padx=self.px(12),pady=self.px(12),undo=True)
        text.grid(row=0,column=0,sticky='nsew');w.text=text
        bar=ttk.Scrollbar(w.body,orient='vertical',command=text.yview)
        bar.grid(row=0,column=1,sticky='ns');text.configure(yscrollcommand=bar.set)
        text.focus_set();w.feedback.set('下一步预览，不会立即导入。')
        def parse():
            value=text.get('1.0','end')
            try:core.import_text(value)
            except (ValueError,OSError) as e:
                messagebox.showerror('无法解析',str(e),parent=w);return
            w.destroy();self.preview_import(value)
        w.button('取消',w.destroy);w.parse_button=w.button('解析并预览',parse,primary=True)
        return w
    def preview_import(self,text):
        try:
            records,warnings=core.import_text(text)
            profiles,added,skipped=core.merge_profiles(self.profiles,records)
        except (ValueError,OSError) as e:return self.error(e)
        expected=self.profile_hash
        w=Dialog(self,'导入预览',f'可新增 {len(added)} 项 · 重复跳过 {skipped} 项。核对服务、模型和协议后再导入。',width=1080,height=680)
        w.body.columnconfigure(0,weight=1);w.body.rowconfigure(0,weight=1)
        area=ttk.Frame(w.body);area.grid(row=0,column=0,sticky='nsew')
        tree=table(area,[('name','服务',110),('url','地址',210),('model','模型',170),('protocol','协议 / 推理',140),('key','认证',200)],self.px,height=5,selectmode='extended')
        w.tree=tree
        for i,item in enumerate(added):
            p=item['profile']
            tree.insert('','end',iid=str(i),values=(p['name'],p['base_url'],p['model'] or '沿用当前',
                        'Responses / '+(p.get('reasoning_effort') or '沿用'),
                        '附带密钥（隐藏）' if item['secret'] else p['env_key']))
        tree.selection_set(tree.get_children())
        if warnings:
            warnarea=ttk.Frame(w.body);warnarea.grid(row=1,column=0,sticky='ew',pady=(self.px(10),0))
            warnarea.columnconfigure(0,weight=1)
            notice=tk.Text(warnarea,height=3,width=20,wrap='word',bg=BG,fg=MUTED,relief='flat',font=('Microsoft YaHei UI',10))
            w.warning_text=notice
            notice.insert('1.0','\n'.join(warnings));notice.configure(state='disabled');notice.grid(row=0,column=0,sticky='ew')
            bar=ttk.Scrollbar(warnarea,orient='vertical',command=notice.yview);bar.grid(row=0,column=1,sticky='ns');notice.configure(yscrollcommand=bar.set)
        keep_keys=tk.BooleanVar(value=False)
        w.keep_keys=keep_keys
        w.key_check=ttk.Checkbutton(w.body,text='同时保存附带的 API Key',variable=keep_keys)
        w.key_check.grid(row=2,column=0,sticky='w',pady=(self.px(10),0))
        if not any(item['secret'] for item in added):w.key_check.configure(state='disabled')
        ttk.Label(w.body,text='勾选后写入独立的用户环境变量；不覆盖已有密钥。',style='Muted.TLabel').grid(row=3,column=0,sticky='w')
        def save():
            selected=[added[int(i)] for i in tree.selection()]
            if not selected:return
            written=[]
            try:
                final=list(self.profiles)
                for item in selected:
                    p=dict(item['profile'])
                    if keep_keys.get() and item['secret']:
                        p['env_key']='CODEX_IMPORT_'+uuid.uuid4().hex.upper()+'_API_KEY'
                        set_key(p['env_key'],item['secret']);written.append(p['env_key'])
                    final.append(p)
                core.save_profiles(PROFILES_PATH,final,expected)
                w.destroy();self.refresh();self.note(f'已导入 {len(selected)} 个服务，重复项已跳过；尚未切换。')
            except (ValueError,OSError) as e:
                for key in written:set_key(key,None)
                messagebox.showerror('未完成导入',str(e),parent=w)
        w.button('取消',w.destroy);w.save_button=w.button('导入所选',save,primary=True)
        def selection_changed(_event=None):
            count=len(tree.selection());w.feedback.set(f'已选 {count} 项 · 导入后需手动应用')
            w.save_button.configure(state='normal' if count else 'disabled')
        tree.bind('<<TreeviewSelect>>',selection_changed);selection_changed()
        return w
    def export(self):
        path=filedialog.asksaveasfilename(parent=self,title='导出配置（不含密钥）',defaultextension='.json',initialfile='codex-profiles.json')
        if not path:return
        try:
            if Path(path).resolve() in {PROFILES_PATH.resolve(),CONFIG_PATH.resolve()}:raise ValueError('请选择新的导出文件，不要覆盖当前配置')
            core.atomic_write(path,core.export_profiles(self.profiles));self.note('配置已导出，未读取或导出密钥。')
        except (ValueError,OSError) as e:self.error(e)
    def restore(self):
        files=sorted((CONFIG_PATH.parent/'switcher-backups').glob(CONFIG_PATH.name+'.*.bak'),reverse=True)
        w=Dialog(self,'配置备份','选择一个检查点恢复。恢复前会再次备份当前配置。',width=780,height=560)
        digest=core.file_hash(CONFIG_PATH)
        w.body.columnconfigure(0,weight=1);w.body.rowconfigure(0,weight=1)
        area=ttk.Frame(w.body);area.grid(row=0,column=0,sticky='nsew')
        tree=table(area,[('name','备份时间 / 文件',530),('size','大小',110)],self.px,height=5);w.tree=tree
        for i,path in enumerate(files):tree.insert('','end',iid=str(i),values=(path.name,f'{path.stat().st_size:,} B'))
        w.feedback.set('首次应用配置后，这里会出现备份。' if not files else f'共 {len(files)} 份备份；请选择一项。')
        def recover():
            if not tree.selection():return
            if not messagebox.askyesno('恢复配置','用所选备份恢复 config.toml？当前文件会另存备份。',parent=w):return
            try:core.restore_backup(CONFIG_PATH,files[int(tree.selection()[0])],digest);w.destroy();self.refresh();self.note('已恢复配置。重新打开 Codex 后生效。')
            except (ValueError,OSError) as e:messagebox.showerror('未能恢复',str(e),parent=w)
        w.button('取消',w.destroy);w.restore_button=w.button('恢复所选',recover,primary=True)
        w.restore_button.configure(state='disabled')
        tree.bind('<<TreeviewSelect>>',lambda _e:w.restore_button.configure(state='normal' if tree.selection() else 'disabled'))
        return w

if __name__ == '__main__':
    if DEMO:
        seed_demo()
    App().mainloop()
