"""The per-run discussion setting changes routing only: machine output stays the same."""
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'requirement-reuse-service'))
from requirement_reuse_service.main import app
from requirement_reuse_service.models import ArtifactPayload
from requirement_reuse_service.workflow import api
from requirement_reuse_service.workflow.engine import execute_run, freeze_snapshot, new_run
from requirement_reuse_service.workflow.evaluation import workflow_metrics
from requirement_reuse_service.workflow.evidence import register_source
from requirement_reuse_service.workflow.models import RunRequest, SnapshotRequest, SourceRequest
from requirement_reuse_service.workflow.storage import Store

NEEDS = ('Each dataset must publish its title.\n'
         'Each dataset should publish its title.\n'
         'Each dataset describes its spatial coverage.')


class ScriptedClient:
    """Answers every workflow contract deterministically, without a provider."""

    def __init__(self):
        self.calls = []

    def describe(self):
        return {'provider': 'offline-test', 'model': 'scripted'}

    def generate_structured(self, *, system, user, output_model, max_tokens=None, schema_repair_attempts=0):
        name = output_model.__name__
        self.calls.append(name)
        data = json.loads(user)
        if name == 'SpanElicitationResult':
            observations = []
            for unit in data['evidence_units']:
                span = unit['source_spans'][0]
                text = span['quote']
                obligation = 'mandatory' if ' must ' in text else 'recommended' if ' should ' in text else 'unknown'
                links = [{'source_span_id': span['span_id'], 'component': 'statement'}]
                if obligation != 'unknown':
                    links.append({'source_span_id': span['span_id'], 'component': 'obligation'})
                observations.append({'observation_id': 'x', 'role_id': 'x', 'statement': text,
                    'extension_kind': 'new_information_need', 'base_property': None,
                    'requirement_type': 'descriptive_metadata', 'scope': 'Dataset', 'evidence_links': links,
                    'intent': {'resource_type': 'Dataset', 'metadata_need': 'title' if 'title' in text else 'coverage',
                               'value_kind': 'literal', 'obligation_hint': obligation},
                    'support_level': 'explicit'})
            return output_model.model_validate({'observations': observations})
        if name == 'Qualification':
            return output_model.model_validate({'support': 'explicit', 'rationale': 'Scripted assessment.',
                                                'findings': [], 'assessor': 'scripted'})
        if name == 'Turn':
            return output_model.model_validate({'body': 'A human has to choose.', 'evidence_ids': [], 'finished': True})
        raise AssertionError(name)


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    monkeypatch.setenv('RQ1_WORKFLOW_STORE', str(tmp_path / 'workflow.sqlite3'))
    monkeypatch.setenv('RRS_LLM_PROVIDER', 'mock')
    store = Store()
    source = register_source(store, SourceRequest(artifact=ArtifactPayload(name='needs.md', content=NEEDS),
                                                  source_role='stakeholder_need'))
    snapshot = freeze_snapshot(store, SnapshotRequest(source_version_ids=[source['source_version_id']]))
    return store, snapshot


def run_with(corpus, discussion, client=None):
    store, snapshot = corpus
    client = client or ScriptedClient()
    run = new_run(store, RunRequest(consolidation='exact', snapshot_id=snapshot['snapshot_id'], strategy='multi_agent',
                                   role_ids=['consumer_discovery'], discussion=discussion))
    execute_run(store, run['run_id'], client)
    return store.get('run', run['run_id']), client


def machine_view(run):
    """Run-independent content of the frozen machine output."""
    frozen = run['machine_snapshot']
    by_id = {r['revision_id']: r for r in frozen['requirements']}
    return (sorted((r['normalized_statement'], r['verification']['status'], r['qualification']['support'])
                   for r in frozen['requirements']),
            sorted(by_id[rid]['normalized_statement'] for rid in frozen['active_revision_ids']),
            sorted(c['kind'] for c in frozen['conflicts']))


def routing_view(run):
    by_id = {r['revision_id']: r['normalized_statement'] for r in run['requirements']}
    return {by_id[item['revision_id']]: (item['route'], item['reasons']) for item in run['metrics']['routing']}


def test_on_request_opens_no_case_but_keeps_machine_output_and_reasons(corpus):
    automatic, auto_client = run_with(corpus, 'automatic')
    on_request, request_client = run_with(corpus, 'on_request')
    # The default behaviour is unchanged: the conflict pair and the candidate with a finding are discussed.
    assert automatic['request']['discussion'] == 'automatic'
    # One case for the must/should pair, one for the candidate whose obligation is unknown.
    assert sorted((len(c['revision_ids']), c['triggers']) for c in automatic['deliberations']) == [
        (1, ['obligation']), (2, ['obligation'])]
    assert auto_client.calls.count('Turn') > 0 and automatic['stages']['deliberation'] == 'completed'
    # With discussion on request nothing is discussed and no discussion call is made.
    assert on_request['deliberations'] == [] and 'Turn' not in request_client.calls
    assert on_request['status'] == 'awaiting_human' and on_request['stages']['deliberation'] == 'skipped'
    # Extraction, verification, assessment and consolidation are identical.
    assert machine_view(on_request) == machine_view(automatic)
    assert request_client.calls == [name for name in auto_client.calls if name != 'Turn']
    # Every candidate keeps its routing reasons; only the destination changes.
    auto_routes, request_routes = routing_view(automatic), routing_view(on_request)
    assert auto_routes.keys() == request_routes.keys()
    for statement, (route, reasons) in auto_routes.items():
        expected = 'human_review' if route == 'deliberation' else route
        assert request_routes[statement] == (expected, reasons)
    assert sorted(route for route, _ in auto_routes.values()) == ['deliberation'] * 3
    assert on_request['metrics']['discussion_mode'] == 'on_request'
    assert on_request['metrics']['deliberation_selected'] == 0
    assert workflow_metrics(on_request)['deliberation']['mode'] == 'on_request'
    assert workflow_metrics(automatic)['deliberation']['mode'] == 'automatic'


def test_reviewer_can_still_request_a_targeted_discussion(corpus, monkeypatch):
    store, _ = corpus
    run, _ = run_with(corpus, 'on_request')
    record = next(r for r in run['requirements'] if r['revision_id'] in run['active_revision_ids']
                  and 'coverage' in r['normalized_statement'])
    reviewer_client = ScriptedClient()
    monkeypatch.setattr(api, 'configured_client', lambda request: reviewer_client)
    opened = TestClient(app).post(f'/api/rq1/v2/runs/{run["run_id"]}/deliberations', json={
        'expected_version': run['version'], 'revision_ids': [record['revision_id']], 'question': 'Is coverage required?'})
    assert opened.status_code == 200, opened.text
    saved = store.get('run', run['run_id'])
    [case] = saved['deliberations']
    assert case['triggers'] == ['human_request: Is coverage required?']
    assert case['status'] == 'unresolved' and reviewer_client.calls.count('Turn') == len(case['participants'])
    assert saved['stages']['deliberation'] == 'completed'


def test_api_accepts_the_setting_and_rejects_unknown_values(corpus):
    store, snapshot = corpus
    client = TestClient(app)
    body = {'snapshot_id': snapshot['snapshot_id'], 'strategy': 'mock', 'role_selection': 'automatic'}
    created = client.post('/api/rq1/v2/runs', json={**body, 'discussion': 'on_request'})
    assert created.status_code == 202, created.text
    assert created.json()['request']['discussion'] == 'on_request'
    assert client.post('/api/rq1/v2/runs', json=body).json()['request']['discussion'] == 'automatic'
    assert client.post('/api/rq1/v2/runs', json={**body, 'discussion': 'never'}).status_code == 422


def test_runs_saved_before_the_setting_existed_keep_automatic_discussion(corpus):
    store, snapshot = corpus
    run = new_run(store, RunRequest(consolidation='exact', snapshot_id=snapshot['snapshot_id'], strategy='multi_agent',
                                   role_ids=['consumer_discovery']))
    store.mutate(run['run_id'], None, 'legacy_fixture', lambda r: r['request'].pop('discussion'))
    client = ScriptedClient()
    execute_run(store, run['run_id'], client)
    saved = store.get('run', run['run_id'])
    assert len(saved['deliberations']) == 2 and saved['metrics']['discussion_mode'] == 'automatic'
    assert workflow_metrics(saved)['deliberation']['mode'] == 'automatic'
