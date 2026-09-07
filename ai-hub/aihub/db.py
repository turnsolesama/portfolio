# -*- coding: utf-8 -*-
"""SQLite 存储层：files / dirs / models / images / img_refs。"""
import json
import sqlite3
import threading
import time
import os

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(
  key TEXT PRIMARY KEY, value TEXT
);
CREATE TABLE IF NOT EXISTS dirs(
  path TEXT PRIMARY KEY, parent TEXT, name TEXT, depth INTEGER,
  size INTEGER DEFAULT 0, file_count INTEGER DEFAULT 0, dir_count INTEGER DEFAULT 0,
  ignored INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS files(
  path TEXT PRIMARY KEY, parent TEXT, name TEXT, ext TEXT,
  size INTEGER, mtime REAL, category TEXT, mtype TEXT, inode TEXT
);
CREATE INDEX IF NOT EXISTS idx_files_parent ON files(parent);
CREATE INDEX IF NOT EXISTS idx_files_name ON files(name);
CREATE TABLE IF NOT EXISTS models(
  rowid_pk INTEGER PRIMARY KEY,
  path TEXT UNIQUE,
  filename TEXT, norm_name TEXT, ext TEXT,
  mtype TEXT, family TEXT, family_conf TEXT, scope TEXT,
  size INTEGER, mtime REAL,
  inode TEXT, alt_paths TEXT,
  legacy_uid TEXT, header_meta TEXT,
  trigger_words TEXT, training_base TEXT, lrank REAL, lalpha REAL, method TEXT,
  source_url TEXT, source_type TEXT, source_conf TEXT,
  civitai_model_id TEXT, civitai_version_id TEXT, civitai_version_name TEXT, civitai_version_date TEXT,
  latest_version_id TEXT, latest_version_name TEXT, latest_version_date TEXT, latest_base_model TEXT,
  preview_path TEXT, preview_url TEXT,
  update_state TEXT DEFAULT 'unchecked',
  last_checked TEXT, check_error TEXT,
  hash TEXT, hash_status TEXT DEFAULT 'none',
  img_count INTEGER DEFAULT 0, days_used INTEGER DEFAULT 0,
  last_used REAL, first_used REAL,
  rating INTEGER DEFAULT 0, notes TEXT DEFAULT '',
  missing INTEGER DEFAULT 0, added_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_models_type ON models(mtype);
CREATE INDEX IF NOT EXISTS idx_models_family ON models(family);
CREATE INDEX IF NOT EXISTS idx_models_state ON models(update_state);
CREATE TABLE IF NOT EXISTS model_labels(
  model_path TEXT PRIMARY KEY, domain TEXT, purposes TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS images(
  path TEXT PRIMARY KEY, name TEXT, parent TEXT,
  size INTEGER, mtime REAL, width INTEGER, height INTEGER,
  has_meta INTEGER DEFAULT 0, engine TEXT,
  checkpoint TEXT, loras TEXT, others TEXT, model_refs TEXT,
  sampler TEXT, steps INTEGER, cfg REAL, seed TEXT, prompt TEXT
);
CREATE INDEX IF NOT EXISTS idx_images_parent ON images(parent);
CREATE TABLE IF NOT EXISTS img_refs(
  image_path TEXT, model_path TEXT, role TEXT, filename TEXT
);
CREATE INDEX IF NOT EXISTS idx_refs_model ON img_refs(model_path);
CREATE INDEX IF NOT EXISTS idx_refs_image ON img_refs(image_path);
"""


def connect(readonly: bool = False) -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


class DB:
    """线程安全封装：写操作全局锁，扫描在单线程内批量写。"""

    def __init__(self):
        self.lock = threading.RLock()
        self.asset_lock = threading.RLock()
        self.conn = connect()
        with self.lock:
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    # ---------- meta ----------
    def get_meta(self, key, default=None):
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_meta(self, key, value):
        with self.lock:
            self.conn.execute(
                "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, str(value)))
            self.conn.commit()

    # ---------- scan writes ----------
    def replace_scan_tables(self, dirs_rows, files_rows):
        with self.lock:
            self.conn.execute("DELETE FROM dirs")
            self.conn.execute("DELETE FROM files")
            self._bulk_insert("INSERT OR REPLACE INTO dirs VALUES(?,?,?,?,?,?,?,?)", dirs_rows)
            self._bulk_insert("INSERT OR REPLACE INTO files VALUES(?,?,?,?,?,?,?,?,?)", files_rows)
            self.conn.commit()

    def _bulk_insert(self, sql, rows, batch=4000):
        buf = []
        for r in rows:
            buf.append(r)
            if len(buf) >= batch:
                self.conn.executemany(sql, buf)
                buf = []
        if buf:
            self.conn.executemany(sql, buf)

    # ---------- models ----------
    def upsert_model(self, m: dict):
        """按 path 唯一插入或更新。"""
        cols = [k for k in m.keys()]
        m = dict(m)
        m.setdefault("added_at", time.strftime("%Y-%m-%d %H:%M:%S"))
        cols = list(m.keys())
        placeholders = ",".join("?" for _ in cols)
        updates = ",".join(f"{c}=excluded.{c}" for c in cols if c not in ("path", "added_at", "update_state"))
        sql = f"INSERT INTO models({','.join(cols)}) VALUES({placeholders}) ON CONFLICT(path) DO UPDATE SET {updates}"
        with self.lock:
            self.conn.execute(sql, [m[c] for c in cols])
            self.conn.commit()

    def model_by_path(self, path):
        return self.conn.execute("SELECT * FROM models WHERE path=?", (path,)).fetchone()

    def model_index_by_name(self):
        """Match known path suffixes; ambiguous basenames are left unresolved."""
        groups = {}
        rows = self.conn.execute(
            "SELECT path, filename, scope, inode, alt_paths FROM models WHERE missing=0 ORDER BY scope").fetchall()
        for r in rows:
            identity = r["inode"] or r["path"]
            for path in [r["path"], *jload(r["alt_paths"], []), r["filename"] or ""]:
                parts = path.replace("/", "\\").lower().split("\\")
                for start in range(len(parts)):
                    key = "\\".join(parts[start:])
                    if key:
                        groups.setdefault(key, {})[identity] = r["path"]
        return {key: next(iter(matches.values())) for key, matches in groups.items() if len(matches) == 1}

    def commit(self):
        with self.lock:
            self.conn.commit()

    # ---------- queries ----------
    def query(self, sql, params=()):
        return self.conn.execute(sql, params).fetchall()

    def one(self, sql, params=()):
        return self.conn.execute(sql, params).fetchone()


def dict_from_row(row) -> dict:
    return {k: row[k] for k in row.keys()}


def jload(s, default):
    if not s:
        return default
    try:
        return json.loads(s)
    except Exception:
        return default
