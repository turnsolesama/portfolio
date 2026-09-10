"""Small validated preferences, written atomically only when the user changes them."""
from __future__ import annotations

import json
import os
from pathlib import Path
import threading

from .store import UserError, clean_path, has_link, uid

DEFAULTS = {
    'confirm_delete': True,
    'confirm_trash_delete': True,
    'close_to_tray': True,
    'default_view': 'grid',
    'default_sort': 'updated',
    'autoplay_media': False,
}
OPTIONS = {'default_view': {'grid','list','board'}, 'default_sort': {'updated','name','order'}}


class Settings:
    def __init__(self, data_root):
        self.root = Path(data_root)
        self.path = self.root / 'settings.json'
        self.lock = threading.RLock()

    @staticmethod
    def validate(values):
        if not isinstance(values, dict) or any(key not in DEFAULTS for key in values):
            raise UserError('设置中包含未知字段。')
        for key,value in values.items():
            if key in OPTIONS:
                if not isinstance(value,str) or value not in OPTIONS[key]:
                    raise UserError('设置选项无效：'+key)
            elif type(value) is not bool:
                raise UserError('设置必须使用 true 或 false：'+key)
        return dict(values)

    def _check_path(self):
        clean_path(self.root)
        if os.path.lexists(self.path):
            if has_link(self.path) or not self.path.is_file() or self.path.stat().st_nlink > 1:
                raise UserError('设置文件不是独立的普通文件，已停止读写。',409)

    def get(self):
        with self.lock:
            self._check_path()
            if not self.path.exists(): return dict(DEFAULTS)
            if self.path.stat().st_size > 16384:
                raise UserError('设置文件异常过大，原文件已保留。',409)
            try:
                stored = json.loads(self.path.read_text(encoding='utf-8-sig'))
                return {**DEFAULTS,**self.validate(stored)}
            except (ValueError,UnicodeError,UserError) as error:
                raise UserError('设置文件格式异常，原文件已保留，请先修复设置文件。',409) from error

    def update(self, patch):
        patch = self.validate(patch)
        with self.lock:
            values = {**self.get(),**patch}
            temporary = self.root / ('.settings-'+uid()+'.tmp')
            try:
                with temporary.open('x',encoding='utf-8',newline='\n') as output:
                    json.dump(values,output,ensure_ascii=False,indent=2)
                    output.write('\n'); output.flush(); os.fsync(output.fileno())
                self._check_path()
                os.replace(temporary,self.path)
            finally:
                temporary.unlink(missing_ok=True)
            return values
