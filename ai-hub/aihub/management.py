"""Read the maintained asset catalog and project evidence without changing assets."""
import collections
import json
import os
from pathlib import Path
import threading
from . import config, registry

_cache = {}
_lock = threading.RLock()


def read_json(path, default=None):
    path = Path(path)
    try:
        stamp = (path.stat().st_mtime_ns, path.stat().st_size)
        with _lock:
            saved = _cache.get(str(path))
            if saved and saved[0] == stamp:
                return saved[1]
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        with _lock:
            _cache[str(path)] = (stamp, value)
        return value
    except (OSError, ValueError):
        return default


def root(cfg):
    return Path(cfg.get("ai_root") or config.DATA_DIR) / "00_Management"


def catalog(cfg):
    return read_json(Path(cfg.get("catalog_dir") or root(cfg) / "Catalogs") / "models.json", {})


def audit_for_model(cfg, model):
    for record in catalog(cfg).get("models", []):
        if model.get("legacy_uid") == record.get("id"):
            return record
    return None


def overview(cfg):
    base = root(cfg)
    data = catalog(cfg)
    models = data.get("models", [])
    central = [m for m in models if m.get("scope") == "central"]
    migrations = base / "Migrations"
    checks = sorted(migrations.glob("*/final_library_check.json")) if migrations.is_dir() else []
    check = read_json(checks[-1], {}) if checks else {}
    duplicates = read_json(base / "Catalogs/duplicate_candidates.json", [])
    reviewed = read_json(base / "Catalogs/workflow_path_review.json", {})
    live = read_json(base / "Catalogs/live_inventory.json", {})
    return {"available": bool(models), "updated_at": data.get("updated_at"),
            "catalog_records": len(models), "central_records": len(central),
            "base_count": sum(m.get("category") in ("Checkpoint", "Diffusion") for m in central),
            "lora_count": sum(m.get("category") == "LoRA" for m in central),
            "family_counts": collections.Counter(m.get("family", "Unknown") for m in central if m.get("category") in ("LoRA", "Checkpoint", "Diffusion")),
            "check": {key: check.get(key) for key in ("checked_at", "status", "hardlinks_verified", "directory_pairs_verified", "models_checked")},
            "workflow_reviewed": len(reviewed.get("copies", [])), "workflow_pending": len(reviewed.get("needs_review", [])),
            "duplicate_groups": len(duplicates),
            "duplicate_candidate_bytes": sum(d.get("bytes_each", 0) * max(0, len(d.get("files", [])) - 1) for d in duplicates),
            "live_updated_at": live.get("updated_at"), "live_diff": {k: len(v) for k, v in live.get("diff", {}).items()},
            "entry_report": str(base / "START_HERE.md"),
            "verification_report": str(base / "验证与待办.md"),
            "next_steps_report": str(base / "模型选型与下一步.md")}


def registry_snapshot(cfg):
    result = registry.read(cfg)
    result['workflows'] = [{**row, **registry.workflow_status(cfg, row, result)} for row in result['workflows']]
    result['runs'] = [{**row, **registry.run_status(cfg, row, result)} for row in result['runs']]
    return result


def registration_preview(cfg, kind, record):
    return registry.preview(cfg, kind, record)


def registration_save(cfg, token):
    return registry.save(cfg, token)


def registration_backups(cfg):
    return registry.backups(cfg)


def registration_restore_preview(cfg, backup_id):
    return registry.restore_preview(cfg, backup_id)


def evidence_preview(cfg, value):
    return registry.evidence_preview(cfg, value)


def _registry(cfg):
    try:
        return registry.read(cfg)
    except ValueError as error:
        return {**registry._empty(), 'warnings': [str(error)]}


def _text_entry(path, folder, title=None, group='资料'):
    """A listed plain text file only; do not follow links or index private names."""
    try:
        path, folder = Path(path), Path(folder)
        if not registry._within(path, folder):
            return None
        registry._ancestors(path)
        relative = path.relative_to(folder)
        if any(part.startswith('.') or part.casefold() in registry.BLOCKED for part in relative.parts):
            return None
        if path.stem.casefold() in {'config', 'auth', 'profiles', 'credentials', 'secrets'}:
            return None
        if path.suffix.lower() not in registry.TEXT_SUFFIXES or not path.is_file():
            return None
        st = path.stat()
        if st.st_nlink > 1 or st.st_size > 2 * 1024 * 1024:
            return None
        return {'name': title or path.name, 'path': str(path), 'group': group,
                'kind': path.suffix[1:], 'mtime': st.st_mtime, 'size': st.st_size}
    except (OSError, ValueError):
        return None


def _project_dirs(folder):
    try:
        registry._ancestors(folder)
        return [path for path in sorted(folder.iterdir()) if path.is_dir() and not path.name.startswith(('.', '_'))
                and path.name.casefold() not in registry.BLOCKED
                and not path.is_symlink() and not getattr(path.lstat(), 'st_file_attributes', 0) & 0x400][:500]
    except (OSError, ValueError):
        return []


def _safe_json(path, default):
    try:
        raw = registry._raw(Path(path))
        return json.loads(raw.decode('utf-8-sig')) if raw else default
    except (OSError, ValueError, UnicodeError):
        return default


def projects(cfg):
    ai_root = root(cfg).parent
    document = _registry(cfg)
    records = catalog(cfg).get('models', [])
    registered = {registry._key(p.get('root', '')): p for p in document['projects']}
    discovered = {}
    for folder, kind in ((ai_root / '40_Projects', 'creative'), (ai_root / '50_Training/Projects', 'training'), (ai_root / '10_Apps', 'tool')):
        for path in _project_dirs(folder):
            doc_names = ('项目说明.md', 'README_项目.md', 'PROJECT.md')
            if kind != 'tool':
                doc_names += ('README_训练项目.md', 'README.md')
            current = next((str(path / name) for name in doc_names if _text_entry(path / name, path)), None)
            if kind == 'tool' and not current and _text_entry(path / 'AGENTS.md', path):
                # A pair of explicit development instructions and a project
                # README is a candidate marker, never registration or progress.
                if _text_entry(path / 'README.md', path):
                    current = str(path / 'README.md')
            if kind == 'tool' and not current and registry._key(path) not in registered:
                continue
            discovered[registry._key(path)] = (path, kind, current)
    for key, record in registered.items():
        try:
            path = registry.safe_path(cfg, record['root'], [ai_root / '40_Projects', ai_root / '50_Training/Projects', ai_root / '10_Apps'], directory=True)
            discovered[key] = (path, record.get('type', 'creative'), record.get('current_doc'))
        except (ValueError, KeyError, OSError):
            continue
    items = []
    for key, (project, kind, current) in discovered.items():
        record = registered.get(key)
        name = record['name'] if record else project.name
        needle = '/projects/' + project.name.casefold() + '/'
        weights = [m for m in records if needle in m.get('canonical_path', '').replace('\\', '/').casefold()
                   or (kind == 'training' and project.name.casefold() in m.get('filename', '').casefold() and m.get('scope') == 'central' and m.get('category') == 'LoRA')]
        doc = _text_entry(current, project) if current else None
        specialist_dir = root(cfg) / 'Projects' / project.name
        try:
            registry._ancestors(specialist_dir)
            specialist = [_text_entry(path, specialist_dir) for path in list(specialist_dir.glob('*.md'))[:100]]
        except (OSError, ValueError):
            specialist = []
        specialist = [entry for entry in specialist if entry]
        item = {'name': name, 'path': str(project), 'root': str(project), 'type': kind,
                'id': record['id'] if record else None, 'registered': bool(record),
                'datasets': [str(p) for p in _project_dirs(project / 'Datasets')],
                'runs': [str(p) for p in _project_dirs(project / 'Runs')],
                'report': doc['path'] if doc else (specialist[0]['path'] if specialist else None),
                'current_doc': doc['path'] if doc else None,
                'description': record.get('description', '') if record else '',
                'assets': record.get('assets', []) if record else [],
                'outputs': record.get('outputs', []) if record else [],
                'delivery': record.get('delivery') if record else None,
                'template': record.get('template') if record else None,
                'mapping': record.get('mapping', {}) if record else {},
                'output_runs': [{**r, **registry.run_status(cfg, r, document)} for r in document['runs'] if record and r.get('project_id') == record['id']],
                'families': sorted({m.get('family', 'Unknown') for m in weights}),
                'weights': [{k: m.get(k) for k in ('id', 'filename', 'category', 'scope', 'family', 'canonical_path', 'metadata', 'variant_note', 'training_note')} for m in weights],
                'status': ('已登记' if doc and project.is_dir() else '登记引用不可用') if record else '未登记',
                'registration_source': '用户登记' if record else ('一级开发说明候选（未登记）' if kind == 'tool' else '一级目录发现（未套用项目模板）'),
                'weight_count': len(weights)}
        items.append(item)
    items.sort(key=lambda item: (item['type'], item['name'].casefold()))
    return {'items': items, 'templates': registry.TEMPLATES, 'warnings': document.get('warnings', []),
            'coverage': '创作、训练和有项目说明的工具目录；未登记项不推断进度，登记只映射现有结构。'}


def workflows(cfg):
    base = root(cfg) / "Catalogs"
    original = _safe_json(base / "workflows.json", [])
    review = _safe_json(base / "workflow_path_review.json", {})
    if not isinstance(original, list):
        original = []
    if not isinstance(review, dict):
        review = {}
    fixed = {row["source"]: row for row in review.get("copies", []) if isinstance(row, dict) and isinstance(row.get('source'), str)}
    pending = {row["source"]: row for row in review.get("needs_review", []) if isinstance(row, dict) and isinstance(row.get('source'), str)}
    items = []
    for workflow in original:
        if not isinstance(workflow, dict) or not isinstance(workflow.get('path'), str):
            continue
        path = workflow["path"]
        item = {"name": Path(path).name, "path": path, "exists": Path(path).is_file(),
                "dependencies": workflow.get("model_dependencies", []), "missing": workflow.get("missing_models", []),
                "unavailable_nodes": workflow.get("unavailable_node_types", []), "status": "path_checked",
                "copy": None, "changes": [], "generation_status": "not_run"}
        if path in fixed:
            match = fixed[path]
            item.update(status="reviewed_copy", copy=match.get("reviewed_copy"), changes=match.get("changes", []))
            item["copy_exists"] = bool(match.get('reviewed_copy')) and Path(match["reviewed_copy"]).is_file()
        elif path in pending:
            item.update(status="needs_review", missing=pending[path].get("unresolved", item["missing"]))
        elif item["missing"] or item["unavailable_nodes"] or workflow.get("error"):
            item["status"] = "needs_review"
        items.append(item)
    document = _registry(cfg)
    registered = {registry._key(w.get('path', '')): w for w in document['workflows']}
    seen = set()
    for item in items:
        record = registered.get(registry._key(item['path']))
        if record:
            item.update(registry.workflow_status(cfg, record, document))
            item['registered'] = True
            item['id'] = record['id']
            seen.add(record['id'])
        else:
            # A legacy copy/path-review list is not dated execution evidence.
            state = 'path_checked' if item['status'] in ('path_checked', 'reviewed_copy') else 'pending'
            item.update(verification_state=state, verification_label=registry.STATE_LABELS[state],
                        verification_reason='仅历史静态路径记录，未登记执行证据。', current_match=False,
                        validation=None, registered=False, id=None)
    for record in document['workflows']:
        if record['id'] in seen:
            continue
        checked = registry.workflow_status(cfg, record, document)
        items.append({'id': record['id'], 'name': Path(record['path']).name, 'path': record['path'],
                      'exists': Path(record['path']).is_file(), 'dependencies': [], 'missing': [],
                      'unavailable_nodes': [], 'status': 'registered', 'copy': None, 'changes': [],
                      'generation_status': 'evidence_registered', 'registered': True, **checked})
    return {'items': items, 'counts': dict(collections.Counter(item['status'] for item in items)),
            'verification_counts': dict(collections.Counter(item['verification_state'] for item in items)),
            'warnings': document.get('warnings', []),
            'coverage': '验证结论来自逐工作流登记；路径检查、历史执行和当前证据匹配分开显示。'}


def reports(cfg, generated_dir):
    base = root(cfg)
    locations = [(base, '工作入口'), (base / 'Reports', '模型与 LoRA'), (Path(generated_dir), '终端生成报告'),
                 (base.parent / '80_Knowledge/Guides', '知识 · 指南')]
    locations += [(path, '项目 · ' + path.name) for path in _project_dirs(base / 'Projects')]
    result = {}
    def add(entry):
        if entry:
            result.setdefault(registry._key(entry['path']), entry)
    for folder, group in locations:
        try:
            registry._ancestors(folder)
            for path in list(folder.iterdir())[:1000] if folder.is_dir() else []:
                add(_text_entry(path, folder, group=group))
        except (ValueError, OSError):
            continue
    for project in projects(cfg)['items']:
        if project['report']:
            # Current project documentation takes precedence over legacy specialist reports.
            folder = Path(project['root']) if registry._within(project['report'], project['root']) else base / 'Projects' / Path(project['root']).name
            add(_text_entry(project['report'], folder, title=project['name'] + ' · 项目说明', group='项目说明'))
    knowledge = base.parent / '80_Knowledge'
    document = _registry(cfg)
    explicit = list(document['knowledge'])
    try:
        manifest_path = knowledge / 'manifest.json'
        raw = registry._raw(manifest_path)
        manifest = json.loads(raw.decode('utf-8-sig')) if raw else {}
        rows = manifest.get('documents', []) if isinstance(manifest, dict) else []
        for row in rows[:500] if isinstance(rows, list) else []:
            if isinstance(row, dict) and isinstance(row.get('path'), str) and not os.path.isabs(row['path']) and '..' not in row['path'].replace('\\','/').split('/'):
                explicit.append({'path': str(knowledge / row['path']), 'title': row.get('title')})
    except (ValueError, OSError, UnicodeError):
        pass
    for row in explicit:
        try:
            path = registry.safe_path(cfg, row.get('path'), [knowledge], exists=True, text=True)
            add(_text_entry(path, knowledge, title=row.get('title'), group='知识 · 已登记'))
        except (ValueError, OSError):
            continue
    return list(result.values())


def is_report(cfg, generated_dir, path):
    # Check the requested spelling too: an unlisted symlink alias is never authorized.
    try:
        registry._ancestors(path)
    except (ValueError, OSError, TypeError):
        return False
    return any(registry._key(path) == registry._key(item['path']) for item in reports(cfg, generated_dir))


def read_report(cfg, generated_dir, path, limit=400 * 1024):
    if not is_report(cfg, generated_dir, path):
        raise ValueError('正文未进入允许的资料索引。')
    return registry.read_checked(Path(path), 2 * 1024 * 1024, single_link=True)[:limit].decode('utf-8', errors='replace')
