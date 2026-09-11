"""Reproducible 100,000-row synthetic catalogue benchmark; no real media reads.

All generated database and context files live in one TemporaryDirectory. The
only retained output is the requested JSON report. The application's Store and
ContextExporter are imported unchanged; no production database is opened.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import platform
import sqlite3
import statistics
import struct
import subprocess
import sys
import tempfile
import time
import tracemalloc

APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))
from yingxu.store import CATEGORIES, STATUSES, Store, json_text, tokenize


def say(message):
    print(message, flush=True)


def percentile(values, fraction):
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def summary(samples):
    return {'runs': len(samples), 'samples_ms': [round(x, 3) for x in samples],
            'p50_ms': round(statistics.median(samples), 3),
            'p95_ms': round(percentile(samples, 0.95), 3),
            'min_ms': round(min(samples), 3), 'max_ms': round(max(samples), 3)}


def cpu_description():
    if os.name == 'nt':
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
                return winreg.QueryValueEx(key, 'ProcessorNameString')[0].strip()
        except OSError:
            pass
    return platform.processor() or platform.machine()


def seed(store, count):
    project = store.create_project('十万条合成性能项目', '仅数据库基准；没有真实媒体文件。')
    source = store.sources(project['id'])[0]
    categories = list(CATEGORIES)
    topics = ['雨夜', '晴空', '森林', '车站', '沙漠', '雪山', '海岸', '城堡']
    columns = ('rowid,id,project_id,source_id,name,category,kind,ext,path,size,mtime,status,tags,notes,'
               'metadata,sort_order,created,updated,search_content')
    sql = 'INSERT INTO items(' + columns + ') VALUES(' + ','.join('?' for _ in range(19)) + ')'
    start = time.perf_counter()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with store.connection() as db:
        for offset in range(0, count, 1000):
            rows = []
            fulltext = []
            for number in range(offset, min(offset + 1000, count)):
                category = categories[number % len(categories)]
                topic = topics[number % len(topics)]
                name = f'{CATEGORIES[category][0]} {number:06d} {topic} 林舟'
                kind, extension = ('video', '.mp4') if category in ('previs', 'delivery') else (
                    ('markdown', '.md') if category in ('shots', 'scripts') else ('image', '.png'))
                phrase = f'{topic}场景中角色林舟手持道具穿过空间，镜头记录人物动作与光线变化。'
                length = 512 + number % 513
                content = (phrase * (length // len(phrase) + 1))[:length]
                tags = json_text([topic, '合成基准', f'分组{number % 12}'])
                notes = '合成数据，不对应磁盘媒体。'
                metadata = json_text({'shot_number': f'S{number:06d}', 'duration': 4 + number % 12,
                                      'model': 'synthetic-model', 'seed': number})
                updated = (base + timedelta(seconds=number % 86400)).isoformat(timespec='milliseconds')
                iid = f'{number + 1:032x}'
                rows.append((number + 1, iid, project['id'], source['id'], name, category, kind, extension,
                             str(Path(project['root']) / CATEGORIES[category][1] / (f'synthetic-{number:06d}' + extension)),
                             2_000_000 + number, number, STATUSES[(number // 3) % len(STATUSES)], tags, notes,
                             metadata, number, updated, updated, content))
                fulltext.append((number + 1, tokenize('\n'.join([name, notes, tags, metadata, content]))))
            db.executemany(sql, rows)
            db.executemany('INSERT INTO item_search(rowid,text) VALUES(?,?)', fulltext)
            db.commit()
            if (offset + 1000) % 10000 == 0 or offset + 1000 >= count:
                say(f'已写入 {min(offset + 1000, count):,} / {count:,} 条合成索引，{time.perf_counter()-start:.1f} 秒')
        db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    return project, time.perf_counter()-start


def measure(store, project_id, arguments, repeats=5):
    samples = []
    result = None
    for _ in range(repeats):
        started = time.perf_counter()
        result = store.list_items(project_id, limit=60, **arguments)
        samples.append((time.perf_counter()-started) * 1000)
    encoded = json.dumps(result, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    tracemalloc.start()
    try:
        traced = store.list_items(project_id, limit=60, **arguments)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return {**summary(samples), 'arguments': arguments, 'total_matches': result['total'],
            'returned_items': len(result['items']), 'response_bytes': len(encoded),
            'tracemalloc_peak_bytes': peak, 'traced_returned_items': len(traced['items'])}


def cold_process(store, project_id):
    samples = []
    for _ in range(5):
        command = [sys.executable, '-B', str(Path(__file__).resolve()), '--child',
                   '--data', str(store.data_root), '--projects', str(store.project_root), '--project-id', project_id]
        completed = subprocess.run(command, check=True, capture_output=True, text=True, encoding='utf-8',
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        samples.append(json.loads(completed.stdout)['elapsed_ms'])
    return {**summary(samples), 'definition': '每次启动新 Python 进程，初始化 Store 后首次列表查询；不含进程启动时间。',
            'os_file_cache_cleared': False,
            'limitation': '操作系统文件缓存未清空，因此不能声称测得真正磁盘冷读。Store 每次查询本身也新建 SQLite 连接。'}


def query_plans(store, project_id):
    variants = {
        'updated': ('SELECT i.* FROM items i WHERE i.project_id=? AND i.removed=0 ORDER BY i.updated DESC,i.id LIMIT 60', (project_id,)),
        'name': ('SELECT i.* FROM items i WHERE i.project_id=? AND i.removed=0 ORDER BY i.name COLLATE NOCASE,i.id LIMIT 60', (project_id,)),
        'order': ('SELECT i.* FROM items i WHERE i.project_id=? AND i.removed=0 ORDER BY i.sort_order,i.name,i.id LIMIT 60', (project_id,)),
        'category_status': ('SELECT i.* FROM items i WHERE i.project_id=? AND i.removed=0 AND i.category=? AND i.status=? ORDER BY i.updated DESC,i.id LIMIT 60',
                            (project_id, 'scenes', '待审核')),
    }
    with store.connection() as db:
        return {name: [row[3] for row in db.execute('EXPLAIN QUERY PLAN ' + sql, args)] for name, (sql, args) in variants.items()}


def benchmark(args):
    # Only this context manager's uniquely named temporary tree is removed.
    with tempfile.TemporaryDirectory(prefix='yingxu-benchmark-', dir=args.temp_parent) as temporary:
        root = Path(temporary)
        store = Store(root / 'data', root / 'projects')
        project, seed_seconds = seed(store, args.count)
        scenarios = {
            'ordinary_list': {},
            'chinese_fts': {'q': '雨夜'},
            'category_and_status': {'category': 'scenes', 'status': '待审核'},
            'sort_name': {'sort': 'name'},
            'sort_order': {'sort': 'order'},
            'deep_offset_90000': {'offset': 90000},
        }
        measured = {}
        for name, arguments in scenarios.items():
            measured[name] = measure(store, project['id'], arguments)
            say(f"{name}: P50 {measured[name]['p50_ms']:.1f} ms / P95 {measured[name]['p95_ms']:.1f} ms")
        cold = cold_process(store, project['id'])
        say(f"新进程首次列表: P50 {cold['p50_ms']:.1f} ms / P95 {cold['p95_ms']:.1f} ms")
        plans = query_plans(store, project['id'])
        with store.connection() as db:
            db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            database = {'file_bytes': store.db_path.stat().st_size,
                        'page_size': db.execute('PRAGMA page_size').fetchone()[0],
                        'page_count': db.execute('PRAGMA page_count').fetchone()[0],
                        'journal_mode': db.execute('PRAGMA journal_mode').fetchone()[0],
                        'indexed_items': db.execute('SELECT count(*) FROM items').fetchone()[0],
                        'fts_rows': db.execute('SELECT count(*) FROM item_search').fetchone()[0]}
        context_result = {'measured': False}
        if not args.skip_context:
            from yingxu.context import ContextExporter
            exporter = ContextExporter(store)
            try:
                tracemalloc.start()
                start = time.perf_counter()
                exported = exporter.export(project['id'])
                elapsed = time.perf_counter()-start
                _, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                snapshot = json.loads(Path(exported['json_path']).read_text(encoding='utf-8'))
                context_result = {'measured': True, 'runs': 1, 'elapsed_seconds': round(elapsed, 3),
                                  'tracemalloc_peak_bytes': peak, 'tracemalloc_enabled_during_timing': True,
                                  'indexed_files': snapshot['index']['count'],
                                  'index_jsonl_bytes': Path(exported['index_path']).stat().st_size,
                                  'progress_json_bytes': Path(exported['json_path']).stat().st_size,
                                  'markdown_bytes': Path(exported['path']).stat().st_size}
                say(f'上下文全量导出: {elapsed:.2f} 秒，Python 峰值 {peak/1024/1024:.2f} MiB')
            finally:
                if tracemalloc.is_tracing():
                    tracemalloc.stop()
                exporter.close()
        report = {
            'schema_version': 1, 'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'title': f'映序 {args.count:,} 条合成索引性能基准',
            'benchmark_kind': 'synthetic_database_not_real_video_decoding',
            'environment': {'python': sys.version, 'sqlite': sqlite3.sqlite_version, 'platform': platform.platform(),
                            'cpu': cpu_description(), 'logical_cpus': os.cpu_count(),
                            'architecture': platform.machine() or str(struct.calcsize('P') * 8) + '-bit',
                            'temporary_volume': root.anchor, 'database_location': '独立临时目录，完成后自动清理'},
            'dataset': {'count': args.count, 'batch_size': 1000, 'document_characters_min': 512,
                        'document_characters_max': 1024, 'chinese_fts_tokenizer': 'Store.tokenize 每个 CJK 字符切分，unicode61 FTS5',
                        'chinese_topic_count': 8, 'category_count': len(CATEGORIES), 'status_count': len(STATUSES),
                        'actual_media_files_created': 0, 'real_assets_read': 0, 'seed_seconds': round(seed_seconds, 3)},
            'database': database, 'new_process_first_list': cold, 'steady_queries': measured,
            'query_plans': plans, 'context_export': context_result,
            'limitations': [
                '合成数据库基准，不是 10 万真实视频解码。没有测试视频时长、不同编码、超大图片、3D 文件或硬盘碎片。',
                '每种列表测 5 次并报告 P50/P95；P95 是 5 个样本的线性插值，样本量有限。',
                '新进程首次列表没有清空操作系统文件缓存，不等价于真正磁盘冷缓存。',
                '列表时间包含 SQL 总数/分类计数、60 条查询与对象转换，不包含 HTTP、浏览器 DOM 绘制、缩略图生成或 JSON 序列化。',
                'response_bytes 另外测量紧凑 UTF-8 JSON 体积；tracemalloc 为独立列表测量，只覆盖 Python 分配，不含 SQLite 原生内存或完整进程 RSS。',
                '上下文导出若启用只测一次，计时期间开着 tracemalloc，因此速度可能低于正常运行；它流式导出全文件元数据，不读取文件正文。',
                '测试未改 Store 算法、未额外 ANALYZE/FTS optimize、未触碰应用数据或现有项目。',
            ],
        }
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = output.with_name(output.name + '.tmp')
    temporary_output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary_output, output)
    say(f'已写入 {output}；合成数据库已清理。')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--count', type=int, default=100000)
    parser.add_argument('--output', type=Path, default=APP_ROOT / 'docs' / 'performance.json')
    parser.add_argument('--temp-parent', type=Path)
    parser.add_argument('--skip-context', action='store_true')
    parser.add_argument('--child', action='store_true')
    parser.add_argument('--data', type=Path)
    parser.add_argument('--projects', type=Path)
    parser.add_argument('--project-id')
    args = parser.parse_args()
    if args.child:
        if not (args.data and args.projects and args.project_id):
            parser.error('child process requires explicit fixture paths')
        store = Store(args.data, args.projects)
        start = time.perf_counter()
        result = store.list_items(args.project_id, limit=60)
        print(json.dumps({'elapsed_ms': (time.perf_counter()-start)*1000, 'returned': len(result['items'])}))
        return
    if args.count < 90100:
        parser.error('count must be at least 90100 for the requested offset 90000 scenario')
    benchmark(args)


if __name__ == '__main__':
    main()
