"""Closed-book runner (scripts/closed_book.py) on a synthetic F/A PM run: scripted clients and fake HTTP only."""
import hashlib
import importlib.util
import json
import sqlite3
import sys
from copy import deepcopy
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'requirement-reuse-service'))
from requirement_reuse_service.llm.client import LLMError, OpenAICompatibleClient, OutputTokenLimitError  # noqa: E402
from requirement_reuse_service.llm.config import LLMConfig  # noqa: E402
from requirement_reuse_service.models import ArtifactPayload, UserTask  # noqa: E402
from requirement_reuse_service.workflow import engine  # noqa: E402
from requirement_reuse_service.workflow.evidence import register_source  # noqa: E402
from requirement_reuse_service.workflow.models import (RoleCitation, RoleProposal, RunRequest,  # noqa: E402
                                                       SnapshotRequest, SourceRequest)
from requirement_reuse_service.workflow.role_selection import as_selected, extraction_config, panel_roles  # noqa: E402
from requirement_reuse_service.workflow.storage import Store, digest  # noqa: E402

spec = importlib.util.spec_from_file_location('closed_book', ROOT / 'scripts' / 'closed_book.py')
cb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cb)

MODEL = 'gpt-oss-synthetic'           # a name the client sends a reasoning effort for
PM_ENDPOINT = 'https://pm-endpoint.invalid/v1'
SOURCES = [('synthetic-portal-guide.txt', 'Portal users can find the licence of a dataset before they request it.'),
           ('synthetic-access-note.txt', 'Requests for restricted tables go to the named data steward.')]
QUOTE = 'Portal users can find the licence of a dataset'
TASK = UserTask(id='T-synthetic-7', statement='Choose a dataset whose licence permits reuse in teaching.')
SIX = ('label', 'stakeholders', 'basis', 'purpose', 'focus_questions', 'rationale')


class ScriptedPM:
    """The PM extraction model: routes every unit to the first panel role and proposes nothing."""
    def __init__(self):
        self.calls = []

    def describe(self):
        return {'provider': 'openai-compatible', 'model': MODEL, 'base_url': PM_ENDPOINT, 'reasoning_effort': 'high'}

    def generate_structured(self, *, system, user, output_model, max_tokens=None, schema_repair_attempts=0):
        self.calls.append({'system': system, 'user': user, 'contract': output_model.__name__})
        data = json.loads(user)
        if output_model.__name__ == 'SourceRouting':
            return output_model.model_validate({'routes': [{'evidence_id': s['evidence_id'], 'kind': 'stakeholder_specific',
                'role_ids': [data['roles'][0]['id']], 'rationale': 'Synthetic route.'} for s in data['sections']]})
        assert output_model.__name__ == 'NeedSpanElicitationResult'
        return output_model.model_validate({'observations': []})


@pytest.fixture
def pm(tmp_path, monkeypatch):
    """A PM run under the F/A contract with an automatic-style sealed panel, extracted by ScriptedPM."""
    monkeypatch.setenv('RQ1_WORKFLOW_STORE', str(tmp_path / 'workflow.sqlite3'))
    monkeypatch.setenv('RRS_LLM_PROVIDER', 'disabled')
    monkeypatch.setattr(engine, 'freeze_step_models', lambda request: request)
    store = Store()
    sources = [register_source(store, SourceRequest(artifact=ArtifactPayload(name=name, content=text),
                                                    source_role='stakeholder_need')) for name, text in SOURCES]
    snapshot = engine.freeze_snapshot(store, SnapshotRequest(
        source_version_ids=[s['source_version_id'] for s in sources], user_tasks=[TASK]))
    run = engine.new_run(store, RunRequest(snapshot_id=snapshot['snapshot_id'], strategy='multi_agent',
        output_form='needs', stakeholder_workflow='fa_mediated', base_profile_id='dcat-ap-2.0.1',
        role_ids=['consumer_discovery'], discussion='automatic', step_models={'extraction': MODEL},
        step_model_options={'extraction': {'reasoning_effort': 'high'}}))
    evidence = next(e for e in run['evidence_ids'] if QUOTE in store.get('evidence', e)['content'])
    documented = as_selected(RoleProposal(label='Teaching librarians', stakeholders=['University librarians'],
        basis='documented', rationale='They select open datasets for course material.',
        purpose='Judge whether a dataset can be reused in teaching.',
        focus_questions=['Which licence applies to this dataset?'],
        evidence_links=[RoleCitation(evidence_id=evidence, quote=QUOTE)], task_ids=[TASK.id]), reason='Synthetic.')
    documented['source_support'] = [{'source_version_id': sources[0]['source_version_id'], 'name': SOURCES[0][0]}]
    proposed = as_selected(RoleProposal(label='Data stewards', stakeholders=['Statistical office stewards'],
        basis='proposed', rationale='They answer access requests for restricted tables.',
        purpose='State what requesters must know to ask for access.',
        focus_questions=['Whom does a requester contact?']), reason='Synthetic.')

    def panel(r):
        manifest = r['role_manifest']
        manifest.update(mode='automatic', selected_roles=[documented, proposed],
                        extraction_roles=[extraction_config(role, i) for i, role in enumerate([documented, proposed])])
        manifest['manifest_hash'] = digest({k: v for k, v in manifest.items() if k != 'manifest_hash'})
    store.mutate(run['run_id'], None, 'fixture_panel', panel)
    client = ScriptedPM()
    engine.elicit(store, store.get('run', run['run_id']), client)
    saved = store.get('run', run['run_id'])
    return {'store': store, 'path': tmp_path / 'workflow.sqlite3', 'run': saved, 'snapshot': snapshot,
            'client': client, 'roles': [documented, proposed], 'sources': sources}


class Answering:
    """A CB model: one valid need per role, optionally failing for some roles."""
    def __init__(self, fail=(), effort='high', provider='openai-compatible'):
        self.calls, self.fail, self.effort, self.provider = [], set(fail), effort, provider

    def describe(self):
        return {'provider': self.provider, 'model': MODEL, 'base_url': 'https://cb-endpoint.invalid/v1',
                'reasoning_effort': self.effort}

    def last_call_metadata(self):
        return {'token_usage': {'prompt_tokens': 900, 'completion_tokens': 300, 'total_tokens': 1200},
                'finish_reason': 'stop'}

    def generate_structured(self, *, system, user, output_model, max_tokens=None, schema_repair_attempts=0):
        self.calls.append({'system': system, 'user': user, 'max_tokens': max_tokens, 'repair': schema_repair_attempts})
        label = json.loads(user)['role']['label']
        if label in self.fail:
            raise LLMError('OpenAI-compatible request to https://cb-endpoint.invalid/v1/chat/completions failed: 503')
        return output_model.model_validate({'observations': [{
            'statement': f'Users can know the licence of a dataset when {label.lower()} plan reuse.',
            'need_condition': f'when {label.lower()} plan reuse', 'requirement_type': 'access_policy',
            'intent': {'resource_type': 'Dataset', 'metadata_need': 'licence'}, 'scope': 'Datasets',
            'rationale': 'Synthetic.'}]})


def requests_by_label(run, **options):
    return {r['label']: r for r in cb.plan(run, **options)['requests']}


def test_workflow_code_is_unchanged():
    assert engine.implementation_identity().startswith('451e85325e879a4c') and cb.CHECKED_IMPLEMENTATION == '451e85325e879a4c'


def test_the_copied_pm_text_is_what_elicit_sends_and_cb_drops_only_source_material(pm):
    run, client = pm['run'], pm['client']
    sent = [c for c in client.calls if c['contract'] == 'NeedSpanElicitationResult']
    assert sent and all(c['system'] == cb.pm_extraction_system(run, [TASK.id]) for c in sent)
    pm_payload = json.loads(sent[0]['user'])
    assert pm_payload['evidence_units'] and pm_payload['user_tasks']
    cb_payload = json.loads(requests_by_label(run)[pm_payload['role']['label']]['user'])
    assert set(cb_payload) == {'role', 'user_tasks', 'stakeholder_perspective'} and cb_payload['user_tasks'] == []
    assert cb_payload['stakeholder_perspective'] == pm_payload['stakeholder_perspective']
    assert cb_payload['role'] == {**pm_payload['role'], 'include': ['Needs within this perspective']}
    assert pm_payload['role']['include'] == ['Evidence-supported needs within this perspective']


def test_prompt_has_the_six_role_fields_and_no_source_material(pm):
    run = pm['run']
    by_label = requests_by_label(run)
    as_sent = cb.system_as_sent(OpenAICompatibleClient(LLMConfig(provider='openai-compatible', model=MODEL,
        base_url='https://schema-only.invalid/v1')), by_label['Data stewards']['system'])
    assert as_sent.startswith(by_label['Data stewards']['system']) and 'ClosedBookNeedResult' in as_sent
    contents = [pm['store'].get('evidence', e)['content'] for e in run['evidence_ids']]
    forbidden = [*run['evidence_ids'], *contents, QUOTE, *(name for name, _ in SOURCES), TASK.id, TASK.statement,
                 *(s['source_version_id'] for s in pm['sources']), 'source_span_id', 'source_spans', 'evidence_units',
                 'supplied excerpt', 'task_justifications', 'rq2_hints', 'Allowed task IDs']
    for role in pm['roles']:
        request = by_label[role['label']]
        payload = json.loads(request['user'])
        assert payload['stakeholder_perspective'] == {key: role[key] for key in SIX}
        for text in (request['user'], request['system'], as_sent):
            assert not [item for item in forbidden if item in text]
    assert cb.plan(run)['leak_check']['found'] == []


@pytest.mark.parametrize('workflow', ['fa_mediated', 'independent'])
def test_closed_book_text_keeps_the_template_and_drops_source_wording(workflow):
    run = {'request': {'output_form': 'needs', 'stakeholder_workflow': workflow, 'requirements_scope': 'find_access_v1'}}
    text = cb.closed_book_system(run)
    assert text.startswith('No source passages are given.') and cb.EXTRACTION_GUIDANCE.split('.')[0] in text
    assert 'Use "[Actor] can [know/find/judge/do] [what] [for which resource] [stated condition]".' in text
    assert 'Never put the whole words must, shall or should in the need statement.' in text
    assert 'Do not name RDF vocabulary terms, classes or properties in statements.' in text
    assert ('This is the single planned pass for this stakeholder.' in text) == (workflow == 'fa_mediated')
    assert not [w for w in ('supplied', 'excerpt', 'source_span', 'task_id', 'task ID', 'source-supported', 'source text',
                            'rq2_hints', 'NeedSpanElicitationResult', 'discussion') if w in text]


def test_a_changed_workbench_text_stops_the_runner(monkeypatch):
    monkeypatch.setattr(cb, 'EXTRACTION_GUIDANCE', cb.EXTRACTION_GUIDANCE.replace('A quoted', 'A cited'))
    with pytest.raises(ValueError, match='no longer matches the workbench text'):
        cb.closed_book_system({'request': {'output_form': 'needs', 'stakeholder_workflow': 'fa_mediated'}})


def test_leak_check_reports_source_material_the_pm_panel_itself_carries(pm):
    run = deepcopy(pm['run'])
    manifest = run['role_manifest']
    manifest['selected_roles'][1]['rationale'] = f'Named in {SOURCES[0][0]}.'
    manifest['manifest_hash'] = digest({k: v for k, v in manifest.items() if k != 'manifest_hash'})
    found = cb.plan(run)['leak_check']['found']
    assert found == [{'role_id': manifest['selected_roles'][1]['role_id'], 'kind': 'source_name', 'value': SOURCES[0][0]}]


def test_output_parses_and_ids_are_deterministic(pm, tmp_path):
    run = pm['run']
    first = cb.run_closed_book(run, Answering(), tmp_path / 'a.json')
    second = cb.run_closed_book(run, Answering(), tmp_path / 'b.json')
    other = cb.run_closed_book(run, Answering(), tmp_path / 'c.json', rep=2)
    assert first['kind'] == 'closed_book_run' and first['status'] == 'completed'
    assert first['cb_run_id'] == second['cb_run_id'] == engine.uid('cb', run['run_id'], run['role_manifest']['manifest_hash'], 1)
    assert other['cb_run_id'] != first['cb_run_id']
    assert [n['need_id'] for n in first['needs']] == [n['need_id'] for n in second['needs']]
    assert [c['call_id'] for c in first['calls']] == [c['call_id'] for c in second['calls']]
    assert json.loads((tmp_path / 'a.json').read_text()) == first
    assert len(first['needs']) == len(first['roles']) == 2 and len(first['calls']) == 2
    need = first['needs'][0]
    assert need['obligation'] == 'unknown' and need['condition'] in need['statement'] and need['resource_type'] == 'Dataset'
    assert {first['pm_run_id'], first['manifest_hash'], first['base_profile_id'], first['base_profile_sha256']} == {
        run['run_id'], run['role_manifest']['manifest_hash'], 'dcat-ap-2.0.1', run['base_profile_sha256']}
    assert first['model'] == {'provider': 'openai-compatible', 'model': MODEL, 'reasoning_effort': 'high',
        'copied_from': 'role_runs', 'max_output_tokens': 8000, 'cutoff_retry_output_tokens': 12000, 'schema_repair_attempts': 1}
    for call in first['calls']:
        assert call['prompt_sha256'] == hashlib.sha256(call['system_prompt'].encode()).hexdigest()
        assert call['payload_sha256'] == hashlib.sha256(call['user_payload'].encode()).hexdigest()
        assert call['token_usage']['total_tokens'] == 1200 and call['latency_seconds'] >= 0 and call['output']
        assert call['max_output_tokens'] == 8000 and call['schema_repair_attempts'] == 1
    text = (tmp_path / 'a.json').read_text()
    assert 'invalid/v1' not in text and 'base_url' not in text
    assert first['diagnostics']['endpoint_matches_pm'] is False


def reply(content, prompt=500, completion=200):
    return httpx.Response(200, json={'choices': [{'message': {'content': content}, 'finish_reason': 'stop'}],
        'usage': {'prompt_tokens': prompt, 'completion_tokens': completion, 'total_tokens': prompt + completion}},
        request=httpx.Request('POST', 'https://fake.invalid/v1/chat/completions'))


def real_client(monkeypatch, contents):
    bodies, answers = [], iter(contents)
    def post(url, *, json, headers, timeout):
        bodies.append(json)
        return reply(next(answers))
    monkeypatch.setattr(httpx, 'post', post)
    import uuid
    return OpenAICompatibleClient(LLMConfig(provider='openai-compatible', model=MODEL, reasoning_effort='high',
        base_url=f'https://{uuid.uuid4().hex}.invalid/v1', api_key='test-secret')), bodies


def answer(obligation='unknown', statement='Users can find whom to contact for a restricted table.'):
    return json.dumps({'observations': [{'statement': statement, 'need_condition': '', 'scope': 'Datasets',
                                         'intent': {'resource_type': 'Dataset', 'obligation_hint': obligation}}]})


def test_schema_repair_retry_goes_through_the_workbench_client(pm, tmp_path, monkeypatch):
    run = pm['run']
    one_role = deepcopy(run)
    client, bodies = real_client(monkeypatch, ['{"observations": [{"scope": "no statement"}]}', answer(),
                                               answer(), answer()])
    record = cb.run_closed_book(one_role, client, tmp_path / 'r.json', workers=1)
    first = next(c for c in record['calls'] if c['sequence'] == 1 and len(c['generations']) == 2)
    assert first['status'] == 'accepted' and [g['purpose'] for g in first['generations']] == ['initial', 'schema_correction']
    assert first['token_usage'] == {'prompt_tokens': 1000, 'completion_tokens': 400, 'total_tokens': 1400}
    sent = bodies[0]
    assert first['system_prompt'] == sent['messages'][0]['content'] and first['user_payload'] == sent['messages'][1]['content']
    assert sent['max_tokens'] == 8000 and sent['reasoning_effort'] == 'high' and sent['model'] == MODEL
    assert len(bodies[1]['messages']) == 4 and 'failed the JSON contract' in bodies[1]['messages'][3]['content']
    assert 'test-secret' not in (tmp_path / 'r.json').read_text()


def test_an_obligation_label_is_reset_to_unknown_after_the_repair(pm, tmp_path, monkeypatch):
    client, _ = real_client(monkeypatch, [answer('mandatory')] * 2 + [answer()] * 2)
    record = cb.run_closed_book(pm['run'], client, tmp_path / 'r.json', workers=1)
    recovered = [c for c in record['calls'] if c['status'] == 'label_recovered']
    assert len(recovered) == 1 and recovered[0]['label_resets'][0]['field'] == 'intent.obligation_hint'
    assert record['status'] == 'completed' and all(n['obligation'] == 'unknown' for n in record['needs'])


def test_a_cut_off_answer_is_asked_once_more_with_the_larger_budget(pm, tmp_path):
    class CutOnce(Answering):
        def generate_structured(self, **kwargs):
            if kwargs['max_tokens'] == 8000:
                self.calls.append(kwargs)
                raise OutputTokenLimitError('finish_reason=length')
            return super().generate_structured(**kwargs)
    record = cb.run_closed_book(pm['run'], CutOnce(), tmp_path / 'r.json')
    assert record['status'] == 'completed'
    assert sorted((c['purpose'], c['max_output_tokens'], c['status']) for c in record['calls']) == [
        ('initial', 8000, 'output_cutoff')] * 2 + [('larger_response_after_cutoff', 12000, 'accepted')] * 2


def test_a_failed_role_is_kept_sanitized_and_resume_calls_only_that_role(pm, tmp_path):
    out = tmp_path / 'r.json'
    record = cb.run_closed_book(pm['run'], Answering(fail={'Data stewards'}), out)
    assert record['status'] == 'incomplete' and len(record['diagnostics']['failed_roles']) == 1
    failed = next(c for c in record['calls'] if c['status'] == 'failed')
    assert failed['error'] == {'type': 'LLMError', 'message': 'OpenAI-compatible request to <url> failed: 503'}
    assert 'cb-endpoint' not in out.read_text()
    client = Answering()
    resumed = cb.run_closed_book(pm['run'], client, out, resume=True)
    assert resumed['status'] == 'completed' and len(client.calls) == 1
    assert json.loads(client.calls[0]['user'])['role']['label'] == 'Data stewards'
    stewards = next(r for r in resumed['roles'] if r['label'] == 'Data stewards')
    assert len(stewards['call_ids']) == 2 and resumed['created_at'] == record['created_at']
    assert [n['need_id'] for n in resumed['needs'] if n['role_label'] == 'Teaching librarians'] == [
        n['need_id'] for n in record['needs'] if n['role_label'] == 'Teaching librarians']
    with pytest.raises(ValueError, match='another --with-shared-extractor'):
        cb.run_closed_book(pm['run'], Answering(), out, resume=True, with_shared_extractor=True)


def test_roles_pm_routed_no_units_are_recorded_and_the_shared_extractor_is_opt_in(pm):
    run = pm['run']
    planned = cb.plan(run)
    stewards = next(r for r in planned['requests'] if r['label'] == 'Data stewards')
    assert [r['kind'] for r in planned['requests']] == ['panel', 'panel']
    assert planned['pm_roles_without_units'] == [stewards['role_id']] and stewards['pm_evidence_unit_count'] == 0
    assert planned['pm_shared_extractor_unit_count'] == 0
    shared = cb.plan(run, with_shared_extractor=True)['requests'][-1]
    payload = json.loads(shared['user'])
    assert shared['kind'] == 'shared_extractor' and shared['role_id'] == 'shared_source_extractor'
    assert payload['role']['label'] == 'Shared needs' and 'stakeholder_perspective' not in payload
    assert payload['role']['purpose'].startswith('State common metadata needs')
    assert {c['field'] for c in shared['role_text_changes']} == {'label', 'purpose'}


def test_model_comes_from_role_runs_else_step_models_and_must_match_the_client(pm):
    run = deepcopy(pm['run'])
    assert cb.plan(run)['model'] == {'provider': 'openai-compatible', 'model': MODEL, 'reasoning_effort': 'high',
                                     'source': 'role_runs'}
    with pytest.raises(ValueError, match='not the PM extraction model'):
        cb.client_identity(Answering(effort='low'), cb.plan(run)['model'], PM_ENDPOINT)
    for report in run['role_runs']:
        report['provider'] = 'offline-mock'
    assert cb.plan(run)['model'] == {'provider': None, 'model': MODEL, 'reasoning_effort': 'high', 'source': 'step_models'}
    run['role_runs'][0]['provider'] = {'provider': 'openai-compatible', 'model': 'another-model'}
    run['role_runs'][1]['provider'] = {'provider': 'openai-compatible', 'model': MODEL}
    with pytest.raises(ValueError, match='different models'):
        cb.plan(run)


def test_only_needs_form_fa_runs_with_their_extraction_policy_are_accepted(pm):
    for change in ({'request': {**pm['run']['request'], 'output_form': 'candidates'}},
                   {'request': {**pm['run']['request'], 'stakeholder_workflow': 'independent', 'requirements_scope': None}},
                   {'elicitation_policy_version': 'rq1-older-elicitation'},
                   {'stakeholder_audit': {'fa_contract': {'policy_version': 'rq1-find-access-v0'}}}):
        with pytest.raises(ValueError):
            cb.plan({**pm['run'], **change})
    with pytest.raises(ValueError, match='lacks role_runs'):
        cb.plan({k: v for k, v in pm['run'].items() if k != 'role_runs'})


def test_store_is_read_only_and_matches_the_stored_run(pm, monkeypatch):
    path, run_id = pm['path'], pm['run']['run_id']
    before = hashlib.sha256(path.read_bytes()).digest(), path.stat().st_mtime_ns
    opened = []
    real_connect = sqlite3.connect
    monkeypatch.setattr(cb.sqlite3, 'connect', lambda target, **kw: opened.append((target, kw)) or real_connect(target, **kw))
    run = cb.read_store_run(path, run_id)
    assert opened and all(target.endswith('?mode=ro') and kw.get('uri') for target, kw in opened)
    assert (hashlib.sha256(path.read_bytes()).digest(), path.stat().st_mtime_ns) == before
    assert {k: run[k] for k in ('role_manifest', 'role_runs', 'step_models')} == {
        k: pm['run'][k] for k in ('role_manifest', 'role_runs', 'step_models')}
    assert run['stakeholder_audit'] == {'fa_contract': pm['run']['stakeholder_audit']['fa_contract']}
    assert cb.plan(run)['requests'] == cb.plan(pm['run'])['requests']
    db = real_connect(opened[0][0], uri=True)
    with pytest.raises(sqlite3.OperationalError, match='readonly'):
        db.execute("UPDATE objects SET body='{}' WHERE kind='run'")
    db.close()
    missing = path.with_name('absent.sqlite3')
    with pytest.raises(ValueError, match='No workbench store'):
        cb.read_store_run(missing, run_id)
    assert not missing.exists()


def test_cli_end_to_end_with_the_workbench_client_and_fake_http(pm, tmp_path, monkeypatch):
    out = tmp_path / 'cb.json'
    args = ['--store', str(pm['path']), '--run-id', pm['run']['run_id'], '--out', str(out)]
    monkeypatch.setenv('RRS_LLM_PROVIDER', 'openai-compatible')
    monkeypatch.setenv('RRS_LLM_BASE_URL', 'https://configured-endpoint.invalid/v1')
    monkeypatch.setenv('RRS_LLM_MODEL', 'some-default-model')
    monkeypatch.setenv('RRS_LLM_API_KEY', 'test-secret')
    assert cb.main(args) == 2 and not out.exists()                    # no --allow-live-provider
    bodies = []
    monkeypatch.setattr(httpx, 'post', lambda url, *, json, headers, timeout: bodies.append(json) or reply(answer()))
    assert cb.main([*args, '--allow-live-provider']) == 0
    record = json.loads(out.read_text())
    assert record['status'] == 'completed' and len(bodies) == 2 and len(record['needs']) == 2
    assert {b['model'] for b in bodies} == {MODEL} and {b['reasoning_effort'] for b in bodies} == {'high'}
    assert all(b['max_tokens'] == 8000 for b in bodies)
    text = out.read_text()
    assert 'test-secret' not in text and 'configured-endpoint' not in text and PM_ENDPOINT not in text
    assert cb.main([*args, '--allow-live-provider']) == 2             # an existing record needs --resume


def test_prompts_only_records_the_requests_without_a_client(pm, tmp_path, monkeypatch):
    monkeypatch.setattr(cb, 'make_client', lambda model: pytest.fail('no client in prompts-only mode'))
    path = tmp_path / 'pm.json'
    path.write_text(json.dumps(pm['run']))
    out = tmp_path / 'prompts.json'
    assert cb.main(['--run-json', str(path), '--out', str(out), '--prompts-only']) == 0
    record = json.loads(out.read_text())
    assert record['status'] == 'prompts_only' and record['calls'] == [] and record['needs'] == []
    assert [r['user_payload'] for r in record['planned_requests']] == [r['user'] for r in cb.plan(pm['run'])['requests']]
    assert [r['status'] for r in record['roles']] == ['not_called', 'not_called']
    path.write_text(json.dumps({'export_kind': 'saved_review_state', 'run': pm['run']}))
    assert cb.read_run_json(path) == pm['run']


def test_panel_roles_come_from_the_sealed_manifest(pm):
    run = deepcopy(pm['run'])
    assert [r['role_id'] for r in cb.plan(run)['requests']] == [r.id for r in panel_roles(run)]
    run['role_manifest']['selected_roles'][0]['label'] = 'Edited after sealing'
    with pytest.raises(ValueError, match='manifest hash'):
        cb.plan(run)
