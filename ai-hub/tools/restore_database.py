"""Validate a migration snapshot and produce a separate rollback database.

Never overwrite a live database. Stop the service and retain a current backup before
manually selecting this output as the database for the matching old application.
"""
import argparse
from pathlib import Path
import sqlite3


def prepare(backup, output):
    source, target = Path(backup).resolve(), Path(output).absolute()
    if not source.is_file() or target.exists():
        raise ValueError('备份必须存在，回退输出必须是尚不存在的新文件。')
    original = sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)
    try:
        if original.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('备份完整性检查失败。')
        tables = {r[0] for r in original.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'models','model_labels','meta'}.issubset(tables):
            raise ValueError('该文件不是 AI Hub 数据库备份。')
        # Exclusive create prevents clobbering a newly appeared live/other file.
        with target.open('xb'):
            pass
        restored = sqlite3.connect(str(target))
        try:
            original.backup(restored)
            if restored.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('回退输出未通过完整性检查，请勿使用。')
        finally:
            restored.close()
    finally:
        original.close()
    return str(target)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(prepare(args.backup, args.output))
