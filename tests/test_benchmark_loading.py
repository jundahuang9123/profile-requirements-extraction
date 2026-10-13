"""A benchmark import uses raw sources only and never rewrites an earlier corpus."""
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'requirement-reuse-service'))
from requirement_reuse_service.workflow import benchmarks
from requirement_reuse_service.workflow.storage import Store


@pytest.fixture
def benchmark_store(tmp_path, monkeypatch):
    root = tmp_path / 'benchmark-data'
    raw = root / 'mobilitydcat' / 'input-raw'
    raw.mkdir(parents=True)
    (raw / 'base.md').write_text('Each Dataset must have a title.', encoding='utf-8')
    (raw / 'inspire.md').write_text('Spatial metadata must include a geographic extent.', encoding='utf-8')
    (raw / 'mobility.md').write_text('Traffic metadata must describe road direction.', encoding='utf-8')
    cases = {'mobilitydcat': {
        'raw': ['mobilitydcat/input-raw/base.md', 'mobilitydcat/input-raw/inspire.md',
                'mobilitydcat/input-raw/mobility.md'],
        'background': ['mobilitydcat/input-raw/base.md'],
        'base_profile': 'dcat-ap-2.0.1',
        'consolidation': ['mobilitydcat/input-preconsolidation/reference.json']},
        'other': {'raw': ['mobilitydcat/input-raw/mobility.md']},
        'empty': {'raw': []}}
    allowlist = root / 'runtime-inputs.json'
    allowlist.write_text(json.dumps({'benchmarks': cases}), encoding='utf-8')
    monkeypatch.setattr(benchmarks, 'BENCHMARK_ROOT', root)
    monkeypatch.setattr(benchmarks, 'RUNTIME_INPUTS', allowlist)
    return Store(str(tmp_path / 'workflow.sqlite3')), root, cases


def test_background_creates_new_versions_and_snapshot_without_mutating_original(benchmark_store):
    store, root, _ = benchmark_store
    evidence_import = benchmarks.load_benchmark(store, 'mobilitydcat', treat_base_as_background=False)
    original_sources = deepcopy(evidence_import['sources'])
    original_snapshot = deepcopy(evidence_import['snapshot'])
    before_bytes = {p: p.read_bytes() for p in (root / 'mobilitydcat' / 'input-raw').iterdir()}

    background_import = benchmarks.load_benchmark(store, 'mobilitydcat')
    old_base = next(s for s in original_sources if s['name'] == 'base.md')
    new_base = next(s for s in background_import['sources'] if s['name'] == 'base.md')
    assert old_base['source_id'] == new_base['source_id']
    assert old_base['raw_sha256'] == new_base['raw_sha256']
    assert old_base['source_version_id'] != new_base['source_version_id']
    assert old_base['source_role'] == 'normative_spec' and new_base['source_role'] == 'background'
    assert new_base['origin_uri'] == 'benchmark-data/mobilitydcat/input-raw/base.md'
    assert background_import['snapshot']['snapshot_id'] != original_snapshot['snapshot_id']
    assert background_import['snapshot']['exclusions'] == [
        {'source_version_id': new_base['source_version_id'], 'reason': 'background_not_evidence'}]
    evidence = [store.get('evidence', item) for item in background_import['snapshot']['evidence_ids']]
    assert {u['source_version_id'] for u in evidence} == {
        s['source_version_id'] for s in background_import['sources'] if s['name'] != 'base.md'}
    assert all('title' not in unit['content'] for unit in evidence)
    assert store.get('snapshot', original_snapshot['snapshot_id']) == original_snapshot
    assert all(store.get('source', item['source_version_id']) == item for item in original_sources)
    assert {p: p.read_bytes() for p in before_bytes} == before_bytes
    assert background_import['base_profile_id'] == 'dcat-ap-2.0.1'
    assert background_import['background_source_names'] == ['base.md']
    assert background_import['source_paths'][new_base['source_version_id']] == 'mobilitydcat/input-raw/base.md'
    assert benchmarks.load_benchmark(store, 'mobilitydcat') == background_import
    assert not store.list('run')


def test_loader_never_reads_reference_or_preconsolidation_inputs(benchmark_store, monkeypatch):
    store, _, _ = benchmark_store
    original = Path.read_bytes
    files_read = []

    def record_reads(path):
        files_read.append(path)
        assert 'input-preconsolidation' not in path.parts and 'reference.json' != path.name
        return original(path)

    monkeypatch.setattr(Path, 'read_bytes', record_reads)
    result = benchmarks.load_benchmark(store, 'mobilitydcat')
    assert len(files_read) == 3
    assert len(result['sources']) == 3
    other = benchmarks.load_benchmark(store, 'other')
    assert other['base_profile_id'] is None and other['background_source_names'] == []


def test_named_case_rejects_custom_or_changed_sources_but_preserves_custom_option(benchmark_store):
    from requirement_reuse_service.workflow.evidence import register_source
    from requirement_reuse_service.workflow.engine import freeze_snapshot
    from requirement_reuse_service.workflow.models import SourceRequest, SnapshotRequest
    from requirement_reuse_service.models import ArtifactPayload

    store, root, _ = benchmark_store
    loaded = benchmarks.load_benchmark(store, 'mobilitydcat')
    benchmarks.validate_case_snapshot(store, 'mobilitydcat', loaded['snapshot']['snapshot_id'])
    reference = register_source(store, SourceRequest(artifact=ArtifactPayload(
        name='answers.md', content='Dataset metadata must describe road direction.'), source_role='observation'))
    custom = freeze_snapshot(store, SnapshotRequest(source_version_ids=[reference['source_version_id']]))
    with pytest.raises(ValueError, match='non-allowlisted or changed'):
        benchmarks.validate_case_snapshot(store, 'mobilitydcat', custom['snapshot_id'])
    (root / 'mobilitydcat/input-raw/mobility.md').write_text('Changed input.')
    with pytest.raises(ValueError, match='non-allowlisted or changed'):
        benchmarks.validate_case_snapshot(store, 'mobilitydcat', loaded['snapshot']['snapshot_id'])


def test_benchmark_api_loads_without_run_or_provider_and_exposes_pinned_choices(benchmark_store, monkeypatch):
    from fastapi.testclient import TestClient
    from requirement_reuse_service.main import app
    from requirement_reuse_service.workflow import api
    store, _, _ = benchmark_store
    monkeypatch.setattr(api, 'Store', lambda: store)
    client = TestClient(app)
    cases = client.get('/api/rq1/v2/benchmarks').json()
    assert cases[0] == {'case_id': 'mobilitydcat', 'base_profile_id': 'dcat-ap-2.0.1',
        'background_source_names': ['base.md'], 'raw_file_count': 3}
    profiles = client.get('/api/rq1/v2/base-profiles').json()
    assert {p['id'] for p in profiles} == {'dcat-ap-2.0.1', 'dcat-ap-2.1.1',
        'dcat-ap-3.0.0', 'dcat-ap-3.0.1', 'dcat-2.0.0', 'dcat-3.0.0'}
    assert {p['family'] for p in profiles} == {'DCAT', 'DCAT-AP'}
    assert next(p['label'] for p in profiles if p['id'] == 'dcat-3.0.0') == 'W3C DCAT 3'
    assert all(p['label'] and p['description'] for p in profiles)
    assert all(len(p['sha256']) == 64 for p in profiles)
    response = client.post('/api/rq1/v2/benchmarks/mobilitydcat/load', json={})
    assert response.status_code == 200
    result = response.json()
    assert len(result['sources']) == 3 and len(result['snapshot']['evidence_ids']) == 2
    assert all('raw_base64' not in s and 'representation' not in s for s in result['sources'])
    assert not store.list('run')
    assert client.post('/api/rq1/v2/benchmarks/unknown/load', json={}).status_code == 422


def test_saved_export_keeps_background_provenance_outside_evidence(benchmark_store, monkeypatch):
    from fastapi.testclient import TestClient
    from requirement_reuse_service.main import app
    from requirement_reuse_service.workflow import api, engine
    from requirement_reuse_service.workflow.models import RunRequest
    store, _, _ = benchmark_store
    loaded = benchmarks.load_benchmark(store, 'mobilitydcat')
    run = engine.new_run(store, RunRequest(snapshot_id=loaded['snapshot']['snapshot_id'], strategy='rules'))
    monkeypatch.setattr(api, 'Store', lambda: store)
    response = TestClient(app).get(f'/api/rq1/v2/runs/{run["run_id"]}/export')
    assert response.status_code == 200
    payload = response.json()
    assert [s['name'] for s in payload['background_sources']] == ['base.md']
    assert {s['name'] for s in payload['sources']} == {'inspire.md', 'mobility.md'}
    assert payload['background_sources'][0]['raw_sha256'] == loaded['sources'][0]['raw_sha256']
    assert all(u['source_version_id'] != payload['background_sources'][0]['source_version_id']
               for u in payload['evidence_units'])


@pytest.mark.parametrize('raw_path', [
    '../secret.md', '/tmp/secret.md', 'mobilitydcat/reference/answers.md',
    'mobilitydcat/input-preconsolidation/answers.md', 'mobilitydcat/input-raw/../answers.md'])
def test_loader_rejects_non_raw_or_escaping_paths_before_reading(benchmark_store, raw_path):
    store, root, cases = benchmark_store
    cases['unsafe'] = {'raw': [raw_path]}
    (root / 'runtime-inputs.json').write_text(json.dumps({'benchmarks': cases}))
    with pytest.raises(ValueError, match='raw-document path'):
        benchmarks.load_benchmark(store, 'unsafe')
    assert not store.list('source') and not store.list('snapshot')


def test_background_must_be_allowlisted_and_missing_files_do_not_partially_register(benchmark_store):
    store, root, cases = benchmark_store
    cases['invalid'] = {'raw': ['mobilitydcat/input-raw/mobility.md'],
                        'background': ['mobilitydcat/reference/answers.json']}
    (root / 'runtime-inputs.json').write_text(json.dumps({'benchmarks': cases}))
    with pytest.raises(ValueError, match='also be an allowlisted raw input'):
        benchmarks.load_benchmark(store, 'invalid')
    cases['missing'] = {'raw': ['mobilitydcat/input-raw/mobility.md', 'mobilitydcat/input-raw/absent.md']}
    (root / 'runtime-inputs.json').write_text(json.dumps({'benchmarks': cases}))
    with pytest.raises(FileNotFoundError):
        benchmarks.load_benchmark(store, 'missing')
    assert not store.list('source') and not store.list('snapshot')


def test_empty_unknown_or_all_background_corpus_is_refused(benchmark_store):
    store, root, cases = benchmark_store
    with pytest.raises(ValueError, match='Unknown benchmark case'):
        benchmarks.load_benchmark(store, 'unknown')
    with pytest.raises(ValueError, match='no allowlisted raw inputs'):
        benchmarks.load_benchmark(store, 'empty')
    cases['only_base'] = {'raw': ['mobilitydcat/input-raw/base.md'],
                          'background': ['mobilitydcat/input-raw/base.md']}
    (root / 'runtime-inputs.json').write_text(json.dumps({'benchmarks': cases}))
    with pytest.raises(ValueError, match='at least one parsed evidence source'):
        benchmarks.load_benchmark(store, 'only_base')
    assert not store.list('snapshot')


def test_preflight_uses_background_roles_and_reserves_base_context(benchmark_store, monkeypatch, tmp_path):
    store, root, cases = benchmark_store
    # Keep this small audit independent of cases with deliberately empty input lists.
    (root / 'runtime-inputs.json').write_text(json.dumps({'benchmarks': {'mobilitydcat': cases['mobilitydcat']}}))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
    import preflight_benchmarks
    monkeypatch.setattr(preflight_benchmarks, 'base_profile_context_chars', lambda _id: 321)
    result = preflight_benchmarks.audit(tmp_path / 'preflight')
    mobility = result['mobilitydcat']
    assert mobility['status'] == 'ready_with_document_limitations'
    assert mobility['evidence_units'] == 2 and mobility['background_excluded_units'] == 1
    assert mobility['base_profile_context_chars'] == 321
    assert mobility['extraction_role_reserve_chars'] == 5321
    assert len(mobility['snapshot_exclusions']) == 1
    assert [s['source_role'] for s in mobility['sources']] == ['background', 'normative_spec', 'normative_spec']
    retained = preflight_benchmarks.audit(tmp_path / 'preflight-retained', treat_base_as_background=False)['mobilitydcat']
    assert retained['evidence_units'] == 3 and retained['background_excluded_units'] == 0
