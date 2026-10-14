"""Load only a benchmark's allowlisted raw inputs into a new corpus snapshot.

Reference and preconsolidation files are deliberately absent from this path. A source's
role contributes to its version identifier, so registering background creates a new
version without changing sources or snapshots used by an earlier run.
"""
from __future__ import annotations

import base64
import json
import hashlib
from datetime import datetime
from pathlib import Path

from ..models import ArtifactPayload, UserTask
from .evidence import register_source
from .models import SnapshotRequest, SourceRequest, UseCaseInput
from .storage import Store, digest


BENCHMARK_ROOT = Path(__file__).resolve().parents[3] / 'benchmark-data'
RUNTIME_INPUTS = BENCHMARK_ROOT / 'runtime-inputs.json'


def benchmark_cases() -> dict:
    """Read extraction settings, never evaluator manifests or reference answers."""
    document = json.loads(RUNTIME_INPUTS.read_text(encoding='utf-8'))
    cases = document.get('benchmarks')
    if not isinstance(cases, dict):
        raise ValueError('The benchmark runtime allowlist has no cases.')
    return cases


def benchmark_settings(case_id: str) -> dict:
    cases = benchmark_cases()
    if case_id not in cases:
        raise ValueError(f'Unknown benchmark case: {case_id}.')
    config = cases[case_id]
    if not isinstance(config, dict):
        raise ValueError('Benchmark extraction settings must be an object.')
    raw = config.get('raw', [])
    background = config.get('background', [])
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise ValueError('Benchmark raw inputs must be an exact list of file paths.')
    if not isinstance(background, list) or not all(isinstance(item, str) for item in background):
        raise ValueError('Benchmark background inputs must be an exact list of file paths.')
    if len(raw) != len(set(raw)) or len(background) != len(set(background)):
        raise ValueError('Benchmark input paths must not be repeated.')
    if not set(background).issubset(raw):
        raise ValueError('Every background input must also be an allowlisted raw input.')
    if config.get('base_profile') is not None and not isinstance(config['base_profile'], str):
        raise ValueError('Benchmark base_profile must be a registry ID or absent.')
    for relative in raw:
        raw_input_path(relative)
    return {'case_id': case_id, 'raw': raw, 'background': background,
            'base_profile_id': config.get('base_profile')}


def raw_input_path(relative: str) -> Path:
    """Reject escapes and evaluator/preconsolidation paths even in a malformed allowlist."""
    path = Path(relative)
    root = BENCHMARK_ROOT.resolve()
    resolved = (root / path).resolve()
    if (path.is_absolute() or '..' in path.parts or len(path.parts) < 3 or
            path.parts[1] != 'input-raw' or not resolved.is_relative_to(root)):
        raise ValueError(f'Benchmark input is not an allowlisted raw-document path: {relative}.')
    return resolved


def source_request(relative: str, source_role: str) -> SourceRequest:
    """Prepare a role-specific version of one raw document without touching its file."""
    path = raw_input_path(relative)
    raw = path.read_bytes()
    return SourceRequest(artifact=ArtifactPayload(
        name=path.name, content=base64.b64encode(raw).decode('ascii'), content_encoding='base64'),
        source_id='benchmark-' + digest(relative), source_role=source_role,
        origin_uri='benchmark-data/' + relative)


def use_case_inputs(case_id: str) -> tuple[list[UserTask], UseCaseInput | None]:
    """Freeze user-authored purpose-based tasks, without generating any tasks."""
    root = BENCHMARK_ROOT.resolve()
    path = (root / case_id / 'use-cases.json').resolve()
    if not path.is_relative_to(root) or path.parent != root / case_id:
        raise ValueError('Use-case input must belong to the selected case.')
    if not path.exists(): return [], None
    raw = path.read_bytes()
    rows = json.loads(raw)
    if not isinstance(rows, list): raise ValueError('Use-case input must be a list.')
    required = {'id','statement','kind','basis','author','written_at'}
    tasks = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != required or any(
                not isinstance(value,str) or not value.strip() for value in row.values()):
            raise ValueError('Each use case needs nonempty id, statement, kind, basis, author and written_at.')
        try: datetime.fromisoformat(row['written_at'].replace('Z','+00:00'))
        except ValueError as exc: raise ValueError('Use-case written_at must be an ISO date or timestamp.') from exc
        tasks.append(UserTask(**row, source='benchmark-data/' + case_id + '/use-cases.json'))
    if len({task.id for task in tasks}) != len(tasks): raise ValueError('Use-case IDs must be unique.')
    return tasks, UseCaseInput(file='benchmark-data/' + case_id + '/use-cases.json',
                              sha256=hashlib.sha256(raw).hexdigest())


def load_benchmark(store: Store, case_id: str, treat_base_as_background: bool = True) -> dict:
    """Register raw inputs and freeze a new snapshot using the case's explicit defaults.

    This makes no run and no model call. Unspecified base versions stay unspecified.
    Background documents remain stored for provenance, but freeze_snapshot excludes
    their evidence units from the extraction corpus.
    """
    from .engine import freeze_snapshot

    settings = benchmark_settings(case_id)
    if not settings['raw']:
        raise ValueError(f'Benchmark {case_id} has no allowlisted raw inputs.')
    tasks, task_input = use_case_inputs(case_id)
    background = set(settings['background']) if treat_base_as_background else set()
    # Read every file before registration; a missing document must not leave a partial
    # benchmark import. Parsing failures are reported by the snapshot freeze.
    requests = [(relative, source_request(relative, 'background' if relative in background else 'normative_spec'))
                for relative in settings['raw']]
    sources = [register_source(store, request) for _, request in requests]
    snapshot = freeze_snapshot(store, SnapshotRequest(
        source_version_ids=[source['source_version_id'] for source in sources],
        user_tasks=tasks, use_case_input=task_input,
        name=f'Benchmark {case_id}' + (' (base specifications as background)' if background else '')))
    return {'case_id': case_id, 'sources': sources, 'snapshot': snapshot,
            'base_profile_id': settings['base_profile_id'],
            'background_source_names': [Path(relative).name for relative in settings['background']],
            'treat_base_as_background': treat_base_as_background,
            'source_paths': {source['source_version_id']: relative
                             for (relative, _), source in zip(requests, sources)}}


def validate_case_snapshot(store: Store, case_id: str, snapshot_id: str) -> None:
    """A named benchmark may use only authentic allowlisted raw-document versions.

    A deliberate subset is allowed; changing to Custom is required to use any other
    source. Background exclusions retain provenance but never become model evidence.
    """
    settings = benchmark_settings(case_id)
    expected = {'benchmark-data/' + relative: (relative, digest(raw_input_path(relative).read_bytes()))
                for relative in settings['raw']}
    snapshot = store.get('snapshot', snapshot_id)
    identifiers = set(snapshot['source_version_ids']) | {
        item['source_version_id'] for item in snapshot.get('exclusions', [])}
    for identifier in identifiers:
        source = store.get('source', identifier)
        while source.get('parent_source_version_id'):
            source = store.get('source', source['parent_source_version_id'])
        entry = expected.get(source.get('origin_uri'))
        if not entry or (source['source_id'] != 'benchmark-' + digest(entry[0])
                or source['raw_sha256'] != entry[1]
                or source['source_role'] not in {'normative_spec', 'background'}):
            raise ValueError('This benchmark snapshot contains non-allowlisted or changed inputs. '
                             'Reload its raw inputs or choose Custom documents.')
