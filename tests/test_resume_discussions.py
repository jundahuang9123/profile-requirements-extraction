"""Resume runs only the discussions whose input is new, changed or unfinished."""
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'requirement-reuse-service'))
from requirement_reuse_service.main import app
from requirement_reuse_service.llm.client import LLMError, OutputValidationError
from requirement_reuse_service.models import ArtifactPayload
from requirement_reuse_service.workflow import api, engine
from requirement_reuse_service.workflow.engine import carry_over_cases, discussion_key, execute_run, freeze_snapshot, new_run
from requirement_reuse_service.workflow.evidence import register_source
from requirement_reuse_service.workflow.models import RunRequest, SnapshotRequest, SourceRequest
from requirement_reuse_service.workflow.storage import Store

NEEDS = ('Each dataset must publish its title.\n'
         'Each dataset should publish its title.\n'
         'Each dataset describes its spatial coverage.')
ROLES = ['consumer_discovery', 'publisher_feasibility']


class ScriptedClient:
    """Deterministic answers; failures can be switched on per role, unit or discussion."""

    def __init__(self):
        self.calls = []
        self.failing_extraction = None      # (role id, text in the unit)
        self.failing_discussion = None      # text in a discussed candidate

    def describe(self):
        return {'provider': 'offline-test', 'model': 'scripted'}

    def generate_structured(self, *, system, user, output_model, max_tokens=None, schema_repair_attempts=0):
        name = output_model.__name__
        data = json.loads(user)
        self.calls.append((name, data))
        if name == 'SpanElicitationResult':
            texts = [unit['source_spans'][0]['quote'] for unit in data['evidence_units']]
            if self.failing_extraction and data['role']['id'] == self.failing_extraction[0] and any(
                    self.failing_extraction[1] in text for text in texts):
                raise OutputValidationError('SpanElicitationResult', [{'loc': ['observations'], 'type': 'too_long'}])
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
            statements = [r['normalized_statement'] for r in data['context']['requirements']]
            if self.failing_discussion and any(self.failing_discussion in text for text in statements):
                raise LLMError('Provider unavailable (simulated).')
            return output_model.model_validate({'body': 'A human has to choose.', 'evidence_ids': [], 'finished': True})
        raise AssertionError(name)

    def count(self, name, since=0):
        return sum(call == name for call, _ in self.calls[since:])

    def turns_about(self, text, since=0):
        return sum(call == 'Turn' and any(text in r['normalized_statement'] for r in data['context']['requirements'])
                   for call, data in self.calls[since:])


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv('RQ1_WORKFLOW_STORE', str(tmp_path / 'workflow.sqlite3'))
    monkeypatch.setenv('RRS_LLM_PROVIDER', 'mock')
    store = Store()
    source = register_source(store, SourceRequest(artifact=ArtifactPayload(name='needs.md', content=NEEDS),
                                                  source_role='stakeholder_need'))
    snapshot = freeze_snapshot(store, SnapshotRequest(source_version_ids=[source['source_version_id']]))
    client = ScriptedClient()
    # Background work started by the API uses the scripted client instead of a provider.
    monkeypatch.setattr(api, 'execute_run', lambda store, run_id: engine.execute_run(store, run_id, client))
    monkeypatch.setattr(api, 'configured_client', lambda request: client)
    run = new_run(store, RunRequest(consolidation='exact', snapshot_id=snapshot['snapshot_id'], strategy='multi_agent', role_ids=ROLES))
    return store, run, client


def resume(store, run_id):
    saved = store.get('run', run_id)
    return TestClient(app).post(f'/api/rq1/v2/runs/{run_id}/resume', json={'expected_version': saved['version']})


def case_about(run, text):
    by_id = {r['revision_id']: r['normalized_statement'] for r in run['requirements']}
    return [case for case in run['deliberations'] if any(text in by_id[rid] for rid in case['revision_ids'])]


# The first role in panel order is re-run after the completed one; merges must not depend on that.
@pytest.mark.parametrize('failing_role', ROLES)
def test_resume_after_a_failed_role_keeps_finished_discussions_of_unchanged_candidates(setup, failing_role):
    store, run, client = setup
    client.failing_extraction = (failing_role, 'coverage')
    execute_run(store, run['run_id'], client)
    first = store.get('run', run['run_id'])
    assert first['status'] == 'awaiting_human' and first['metrics']['failed_role_count'] == 1
    [conflict_case] = case_about(first, 'title')
    [coverage_case] = case_about(first, 'coverage')
    assert conflict_case['status'] == coverage_case['status'] == 'unresolved'
    assert set(conflict_case['participants']) == {*ROLES, 'grounding_scope_critic'}
    other_role = next(role for role in ROLES if role != failing_role)
    assert set(coverage_case['participants']) == {other_role, 'grounding_scope_critic'}

    client.failing_extraction = None
    mark = len(client.calls)
    assert resume(store, run['run_id']).status_code == 202
    second = store.get('run', run['run_id'])
    assert second['status'] == 'awaiting_human' and second['metrics']['failed_role_count'] == 0
    # The must/should pair is unchanged: its discussion is kept, including messages and identity.
    [kept] = case_about(second, 'title')
    assert kept == conflict_case
    assert client.turns_about('title', mark) == 0
    # The coverage candidate is now a merge of both roles: it is a new candidate and is discussed.
    [rerun] = case_about(second, 'coverage')
    assert rerun['case_id'] != coverage_case['case_id'] and rerun['status'] == 'unresolved'
    assert set(rerun['participants']) == {*ROLES, 'grounding_scope_critic'}
    assert client.count('Turn', mark) == len(rerun['participants'])
    assert second['metrics']['deliberation_selected'] == 2 and second['metrics']['deliberation_reused'] == 1
    assert second['stages']['deliberation'] == 'completed'
    # Only the new candidates are assessed: the retried observation and the new merge.
    # The unchanged merged revisions keep their assessments.
    assert client.count('Qualification', mark) == 2
    # The superseded discussion stays in the attempt history.
    history = second['attempt_history'][-1]['deliberations']
    assert {case['case_id'] for case in history} == {conflict_case['case_id'], coverage_case['case_id']}


def test_resume_reruns_only_a_discussion_that_failed(setup):
    store, run, client = setup
    client.failing_discussion = 'coverage'
    execute_run(store, run['run_id'], client)
    first = store.get('run', run['run_id'])
    [failed] = case_about(first, 'coverage')
    [finished] = case_about(first, 'title')
    assert failed['status'] == 'failed' and finished['status'] == 'unresolved'
    assert first['status'] == 'awaiting_human' and not first['metrics']['failed_role_count']

    client.failing_discussion = None
    mark = len(client.calls)
    assert resume(store, run['run_id']).status_code == 202
    second = store.get('run', run['run_id'])
    assert case_about(second, 'title') == [finished]
    [retried] = case_about(second, 'coverage')
    assert retried['status'] == 'unresolved' and retried['messages']
    # Nothing but the failed discussion is requested again.
    assert [name for name, _ in client.calls[mark:]] == ['Turn'] * len(retried['participants'])
    assert second['metrics']['deliberation_reused'] == 1
    assert second['attempt_history'][-1]['deliberations'] == first['deliberations']


def test_a_run_whose_discussions_all_finished_is_not_resumed(setup):
    store, run, client = setup
    execute_run(store, run['run_id'], client)
    response = resume(store, run['run_id'])
    assert response.status_code == 422 and 'completed' in response.text


def test_reviewer_requested_discussions_are_carried_over_and_not_repeated(setup):
    store, run, client = setup
    client.failing_extraction = ('publisher_feasibility', 'coverage')
    execute_run(store, run['run_id'], client)
    first = store.get('run', run['run_id'])
    title = next(r for r in first['requirements'] if r['revision_id'] in first['active_revision_ids']
                 and 'must' in r['normalized_statement'])
    opened = TestClient(app).post(f'/api/rq1/v2/runs/{run["run_id"]}/deliberations', json={
        'expected_version': first['version'], 'revision_ids': [title['revision_id']], 'question': 'Is the title mandatory?'})
    assert opened.status_code == 200, opened.text
    requested = next(c for c in store.get('run', run['run_id'])['deliberations'] if c['case_id'] == opened.json()['result']['case_id'])
    assert requested['status'] == 'unresolved' and requested['messages']

    client.failing_extraction = None
    mark = len(client.calls)
    assert resume(store, run['run_id']).status_code == 202
    second = store.get('run', run['run_id'])
    assert [c for c in second['deliberations'] if c['case_id'] == requested['case_id']] == [requested]
    assert not any(data.get('triggers') == requested['triggers'] for name, data in client.calls[mark:] if name == 'Turn')


def frozen(revision, support='explicit', checked_at='2026-10-12T00:00:00+00:00', roles=('a',)):
    return {'revision_id': revision, 'content_hash': 'hash-' + revision, 'contributing_roles': list(roles),
            'verification': {'status': 'pass', 'component_checks': {'statement_premise': True}, 'revision_hash': 'hash-' + revision,
                             'checked_at': checked_at, 'links': [{'checked_at': checked_at}]},
            'qualification': {'support': support, 'rationale': 'r', 'findings': [], 'assessor': 'x', 'revision_hash': 'hash-' + revision}}


def case(case_id, records, status='queued', triggers=('obligation',)):
    return {'case_id': case_id, 'revision_ids': [r['revision_id'] for r in records], 'triggers': list(triggers),
            'participants': ['a', 'grounding_scope_critic'], 'policy_version': 'rq1-selective-v5', 'status': status,
            'messages': [{'body': 'earlier'}] if status != 'queued' else [], 'frozen_requirements': records}


def test_discussion_key_ignores_recheck_times_and_order_but_not_content():
    one, two = frozen('r1'), frozen('r2')
    base = case('c', [one, two])
    assert discussion_key(base) == discussion_key(case('d', [frozen('r2', checked_at='later'), frozen('r1', checked_at='later')]))
    assert discussion_key(base) != discussion_key(case('c', [frozen('r1', support='uncertain'), two]))
    assert discussion_key(base) != discussion_key(case('c', [frozen('r1', roles=('a', 'b')), two]))
    assert discussion_key(base) != discussion_key(case('c', [one, two], triggers=('scope',)))


@pytest.mark.parametrize('status, kept', [('unresolved', True), ('budget_exhausted', True), ('failed', False),
                                          ('cancelled', False), ('running', False), ('queued', False)])
def test_only_finished_routed_cases_are_reused(status, kept):
    earlier = case('old', [frozen('r1')], status=status)
    routed = case('new', [frozen('r1', checked_at='later')])
    human = case('asked', [frozen('r1')], status='running', triggers=('human_request: why?',))
    cases, to_run, reused = carry_over_cases([earlier, human], [routed])
    assert cases == ([earlier] if kept else [routed]) + [human]
    assert to_run == ([] if kept else ['new']) and reused == int(kept)


def test_unmatched_and_duplicate_earlier_cases_are_not_carried_over():
    earlier = [case('old-1', [frozen('r1')], status='unresolved'), case('old-2', [frozen('r1')], status='unresolved'),
               case('gone', [frozen('r9')], status='unresolved')]
    cases, to_run, reused = carry_over_cases(earlier, [case('new', [frozen('r1')])])
    assert [c['case_id'] for c in cases] == ['old-1'] and to_run == [] and reused == 1
