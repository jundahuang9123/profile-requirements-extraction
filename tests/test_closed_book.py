"""Closed-book runner (scripts/closed_book.py) on a synthetic F/A PM run: scripted clients and fake HTTP only."""
import hashlib
import importlib.util
import json
import sqlite3
import sys
import threading
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, as_completed, wait
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
from requirement_reuse_service.workflow.base_profile import load_profile  # noqa: E402
from requirement_reuse_service.workflow.evidence import register_source  # noqa: E402
from requirement_reuse_service.workflow.models import (NeedSpanElicitationResult, RoleCitation,  # noqa: E402
                                                       RoleProposal, RunRequest, SnapshotRequest, SourceRequest)
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
DOMAIN, EXTENSION = 'teaching data', 'TeachDCAT-AP'            # synthetic case: no built-in values
OPTIONS = {'domain': DOMAIN, 'extension_name': EXTENSION, 'override_case_values': True}
LINE = 'an extension of DCAT-AP 2.0.1 for teaching data'      # the fixture pins dcat-ap-2.0.1


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


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


def reseal(manifest):
    manifest['manifest_hash'] = digest({k: v for k, v in manifest.items() if k != 'manifest_hash'})


@pytest.fixture
def pm(tmp_path, monkeypatch):
    """A PM run under the F/A contract with an automatic-style sealed panel, extracted by ScriptedPM through the
    workbench's call recording (TrackedClient), and the runner's read of it from the store."""
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
        reseal(manifest)
    store.mutate(run['run_id'], None, 'fixture_panel', panel)
    client = ScriptedPM()
    engine.elicit(store, store.get('run', run['run_id']), engine.TrackedClient(client, store, run['run_id']))
    saved = store.get('run', run['run_id'])
    path = tmp_path / 'workflow.sqlite3'
    return {'store': store, 'path': path, 'run': saved, 'snapshot': snapshot, 'client': client,
            'roles': [documented, proposed], 'sources': sources, 'inputs': cb.read_store(path, run['run_id'])}


def using(pm, run):
    """The store inputs of the fixture with another run document (snapshot, evidence and recorded calls kept)."""
    return {**pm['inputs'], 'run': run}


def changed(pm, label=None, stakeholders=None, case=None, role=1):
    """The fixture's inputs with another label or other stakeholder names for one role (resealed), or another case."""
    run = deepcopy(pm['run'])
    manifest = run['role_manifest']
    if label:
        manifest['selected_roles'][role]['label'] = manifest['extraction_roles'][role]['label'] = label
    if stakeholders:
        manifest['selected_roles'][role]['stakeholders'] = stakeholders
    if case:
        run['request']['benchmark_case_id'] = case
    reseal(manifest)
    return using(pm, run)


class Answering:
    """A CB model: one valid need per role, optionally failing for some roles."""
    def __init__(self, fail=(), effort='high', provider='openai-compatible', endpoint=PM_ENDPOINT):
        self.calls, self.fail, self.effort, self.provider, self.endpoint = [], set(fail), effort, provider, endpoint

    def describe(self):
        return {'provider': self.provider, 'model': MODEL, 'base_url': self.endpoint, 'reasoning_effort': self.effort}

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


def requests_by_label(inputs, **options):
    return {r['label']: r for r in cb.plan(inputs, **{**OPTIONS, **options})['requests']}


def descriptions(schema, path=''):
    if isinstance(schema, dict):
        found = [(path, schema['description'])] if isinstance(schema.get('description'), str) else []
        return found + [item for key, value in schema.items() for item in descriptions(value, f'{path}/{key}')]
    if isinstance(schema, list):
        return [item for i, value in enumerate(schema) for item in descriptions(value, f'{path}/{i}')]
    return []


def test_workflow_code_is_unchanged():
    assert engine.implementation_identity().startswith('451e85325e879a4c') and cb.CHECKED_IMPLEMENTATION == '451e85325e879a4c'


def test_the_copied_pm_text_is_what_elicit_sends_and_the_parity_check_passes(pm):
    run, client = pm['run'], pm['client']
    sent = [c for c in client.calls if c['contract'] == 'NeedSpanElicitationResult']
    assert sent and all(c['system'] == cb.pm_extraction_system(run, [TASK.id]) for c in sent)
    recorded = pm['inputs']['extraction_calls']
    assert len(recorded) == len(sent) and {c['system_hash'] for c in recorded} == {digest(sent[0]['system'])}
    parity = cb.plan(pm['inputs'], **OPTIONS)['parity_check']
    assert parity['status'] == 'passed' and parity['calls_checked'] == parity['calls_matching'] == len(sent)
    assert parity['expected_system_hash'] == digest(cb.pm_extraction_system(run, [TASK.id]))
    assert parity['runs'] == [{'run_id': run['run_id'], 'extraction_calls': len(sent)}]
    pm_payload = json.loads(sent[0]['user'])
    assert pm_payload['evidence_units'] and pm_payload['user_tasks'] and pm_payload['stakeholder_perspective']
    cb_payload = json.loads(requests_by_label(pm['inputs'])[pm_payload['role']['label']]['user'])
    assert cb_payload == {'domain': LINE, 'role': {'label': pm_payload['role']['label'],
                                                   'stakeholders': pm_payload['stakeholder_perspective']['stakeholders']}}


def test_the_parity_check_refuses_another_text_skips_citation_retries_and_follows_derived_runs(pm, tmp_path):
    inputs, run, store = pm['inputs'], pm['run'], pm['store']
    text = cb.pm_extraction_system(run, [TASK.id])
    other = deepcopy(inputs)
    other['extraction_calls'][0]['system_hash'] = digest('Another extraction text.')
    with pytest.raises(ValueError, match='not what PM sent'):
        cb.plan(other, **OPTIONS)
    retried = deepcopy(inputs)
    retried['extraction_calls'].append({**retried['extraction_calls'][0], 'call_id': 'synthetic-retry',
                                        'system_hash': digest(text + engine.CITATION_RETRY_NOTE)})
    parity = cb.plan(retried, **OPTIONS)['parity_check']
    assert parity['status'] == 'passed' and parity['citation_retry_calls_excluded'] == 1
    unchecked = {**inputs, 'extraction_calls': []}
    assert cb.plan(unchecked, **OPTIONS)['parity_check']['status'] == 'not_checked'
    with pytest.raises(ValueError, match='parity check'):
        cb.run_closed_book(unchecked, Answering(), tmp_path / 'r.json', **OPTIONS)
    assert not (tmp_path / 'r.json').exists()
    # A run derived after extraction copies the role reports and makes no extraction call of its own.
    body = store.get_run(run['run_id'], parts=False)
    store.put('run', 'run-derived-synthetic', {**body, 'run_id': 'run-derived-synthetic',
                                               'derived_from': {'run_id': run['run_id'], 'stage': 'elicitation'}})
    derived = cb.read_store(pm['path'], 'run-derived-synthetic')
    assert derived['lineage'] == [{'run_id': 'run-derived-synthetic', 'extraction_calls': 0},
                                  {'run_id': run['run_id'], 'extraction_calls': len(inputs['extraction_calls'])}]
    assert cb.plan(derived, **OPTIONS)['parity_check']['status'] == 'passed'
    # One that extracted again has other reports: the calls of the run it came from are not its own.
    changed_reports = [{**report, 'raw_outputs': [{'observations': []}]} for report in body['role_runs']]
    store.put('run', 'run-reextracted-synthetic', {**body, 'run_id': 'run-reextracted-synthetic',
                                                   'role_runs': changed_reports,
                                                   'derived_from': {'run_id': run['run_id'], 'stage': 'role_selection'}})
    reextracted = cb.read_store(pm['path'], 'run-reextracted-synthetic')
    assert reextracted['lineage'] == [{'run_id': 'run-reextracted-synthetic', 'extraction_calls': 0}]
    assert cb.plan(reextracted, **OPTIONS)['parity_check']['status'] == 'not_checked'


def test_each_role_gets_only_its_label_its_stakeholders_and_the_domain_line(pm):
    planned = cb.plan(pm['inputs'], **OPTIONS)
    by_label = {r['label']: r for r in planned['requests']}
    assert planned['domain'] == {'text': DOMAIN, 'base_release': 'DCAT-AP 2.0.1', 'line': LINE}
    system = planned['requests'][0]['system']
    as_sent = cb.system_as_sent(OpenAICompatibleClient(LLMConfig(provider='openai-compatible', model=MODEL,
        base_url='https://schema-only.invalid/v1')), system)
    assert as_sent == cb.with_schema(system) and as_sent.startswith(system) and 'ClosedBookNeedResult' in as_sent
    contents = [pm['store'].get('evidence', e)['content'] for e in pm['run']['evidence_ids']]
    forbidden = [*pm['run']['evidence_ids'], *contents, QUOTE, *(name for name, _ in SOURCES), TASK.id, TASK.statement,
                 *(s['source_version_id'] for s in pm['sources']), 'source_span_id', 'source_spans', 'evidence_units',
                 'supplied excerpt', 'task_justifications', 'rq2_hints', 'Allowed task IDs', 'stakeholder_perspective',
                 'Evidence-supported', 'Invented stakeholder preferences', EXTENSION, 'TeachDCAT']
    for role in pm['roles']:
        request = by_label[role['label']]
        assert json.loads(request['user']) == {'domain': LINE, 'role': {'label': role['label'],
                                                                        'stakeholders': role['stakeholders']}}
        texts = [role['purpose'], role['rationale'], *role['focus_questions'], role['role_id']]
        for text in (request['user'], request['system'], as_sent):
            assert not [item for item in [*forbidden, *texts] if item in text]
        assert request['extension_name_masked'] == []
    leak = planned['leak_check']
    assert leak['scope'] == 'snapshot' and leak['found'] == [] and leak['not_checked'] == []
    assert leak['checked']['evidence_units'] == len(contents) and leak['checked']['use_case_statement'] == 1
    # The system text, the schema-correction turn, the domain line, 2 labels and 2 stakeholder names.
    assert planned['extension_check'] == {'name': EXTENSION, 'forms': [EXTENSION, 'TeachDCAT'], 'fields_checked': 7,
                                          'found': [], 'mask_extension_name': False, 'masked': 0}


@pytest.mark.parametrize('workflow', ['fa_mediated', 'independent'])
def test_closed_book_text_keeps_the_template_and_drops_source_wording(workflow):
    run = {'request': {'output_form': 'needs', 'stakeholder_workflow': workflow, 'requirements_scope': 'find_access_v1'}}
    text = cb.closed_book_system(run)
    assert text.startswith('No source passages are given. The role field names this stakeholder, and the domain field '
                           'names the domain and the base release the work extends. From your knowledge of that domain')
    assert cb.EXTRACTION_GUIDANCE.split('.')[0] in text
    assert 'Use "[Actor] can [know/find/judge/do] [what] [for which resource] [stated condition]".' in text
    assert 'Never put the whole words must, shall or should in the need statement.' in text
    assert 'Do not name RDF vocabulary terms, classes or properties in statements.' in text
    assert 'Leave obligation_hint unknown: no source states an obligation level.' in text
    assert ('This is the single planned pass for this stakeholder.' in text) == (workflow == 'fa_mediated')
    # Kept for parity with PM: the routed RDF-syntax sentence and the F/A sentence on missing formal use cases.
    assert ('General explanations of RDF syntax, document layout and implementation mechanics are not automatically '
            'catalogue metadata needs.' in text) == (workflow == 'fa_mediated')
    assert 'missing formal use cases are uncertainty, not automatic exclusion.' in text
    sent = cb.with_schema(text)
    assert not [w for w in ('supplied', 'excerpt', 'source_span', 'task_id', 'task ID', 'source-supported', 'source text',
                            'rq2_hints', 'NeedSpanElicitationResult', 'NeedSpanObservation', 'use-case', 'use_case',
                            'discussion', 'stakeholder_perspective', 'role descriptions') if w in sent]
    cb.check_closed_book_text(sent)


def test_the_cb_only_template_note_follows_pms_template_once_and_passes_the_checks(pm):
    note = 'Brackets are slots to fill or leave out, not text: never write "for which resource" or "can do".'
    assert cb.TEMPLATE_NOTE == note and note not in cb.pm_extraction_system(pm['run'], [TASK.id])   # CB-only
    for workflow in ('fa_mediated', 'independent'):
        text = cb.closed_book_system({'request': {'output_form': 'needs', 'stakeholder_workflow': workflow,
                                                  'requirements_scope': 'find_access_v1'}})
        assert text.count(note) == 1 and f'{cb.PM_TEMPLATE} {note}' in text
        cb.check_closed_book_text(cb.with_schema(text))
        for _, name in cb.CASE_VALUES.values():
            assert not [form for form in cb.extension_forms(name) if cb.holds(form, note) or cb.holds(form, text)]
    assert cb.plan(pm['inputs'], **OPTIONS)['requests'][0]['system'].count(note) == 1
    assert note in (ROOT / 'docs' / 'CLOSED_BOOK.md').read_text()


def test_a_changed_workbench_text_or_a_forbidden_term_stops_the_runner(pm, monkeypatch):
    for term in ('use-case', 'NeedSpanObservation'):
        with pytest.raises(ValueError, match=term):
            cb.check_closed_book_text(f'A proposal ({term}) without links.')
    with monkeypatch.context() as patch:        # the schema-correction turn is checked like the system text
        patch.setattr(cb, 'SCHEMA_CORRECTION_TURN', cb.SCHEMA_CORRECTION_TURN + 'Quote the supplied excerpt. ')
        with pytest.raises(ValueError, match="schema correction turn contains 'supplied', 'excerpt'"):
            cb.plan(pm['inputs'], **OPTIONS)
    monkeypatch.setattr(cb, 'EXTRACTION_GUIDANCE', cb.EXTRACTION_GUIDANCE.replace('A quoted', 'A cited'))
    with pytest.raises(ValueError, match='no longer matches the workbench text'):
        cb.closed_book_system({'request': {'output_form': 'needs', 'stakeholder_workflow': 'fa_mediated'}})


def test_the_domain_line_names_the_pinned_base_release_or_the_run_is_refused(pm):
    run = pm['run']
    assert cb.base_release(run) == 'DCAT-AP 2.0.1'
    for identifier, name in (('dcat-ap-1.1.0', 'DCAT-AP 1.1.0'), ('dcat-ap-3.0.1', 'DCAT-AP 3.0.1')):
        assert cb.base_release({'base_profile_id': identifier, 'base_profile_sha256': load_profile(identifier)[1]}) == name
    for change, match in (({'base_profile_id': None}, 'pins no base release'),
                          ({'base_profile_sha256': '0' * 64}, 'not the one the PM run pinned'),
                          ({'base_profile_id': 'dcat-ap-9.9.9'}, 'cannot be read')):
        with pytest.raises(ValueError, match=match):
            cb.base_release({**run, **change})
    assert cb.plan(pm['inputs'], **{**OPTIONS, 'domain': '  teaching\n  data '})['domain']['line'] == LINE
    with pytest.raises(ValueError, match='--domain'):
        cb.plan(pm['inputs'], **{**OPTIONS, 'domain': ' \n'})


def test_the_case_values_are_built_in_and_other_values_need_the_override(pm, tmp_path):
    doc = (ROOT / 'docs' / 'CLOSED_BOOK.md').read_text()
    for case, (domain, name) in cb.CASE_VALUES.items():       # the doc's table is the built-in table
        assert f'| `{case}` | `{domain}` | `{name}` |' in doc
        planned = cb.plan(changed(pm, case=case))              # no built-in name in any fixed text sent
        assert planned['domain']['line'] == f'an extension of DCAT-AP 2.0.1 for {domain}'
        assert planned['extension_name'] == name and planned['extension_check']['found'] == []
    stat = changed(pm, case='statdcat')
    planned = cb.plan(stat)
    assert planned['extension_check']['forms'] == ['StatDCAT-AP', 'StatDCAT']
    assert planned['case_values'] == {'benchmark_case_id': 'statdcat', 'sources': {'domain': 'built_in',
        'extension_name': 'built_in'}, 'built_in': {'domain': 'statistical data', 'extension_name': 'StatDCAT-AP'}}
    assert cb.plan(stat, domain=' statistical  data', extension_name='StatDCAT-AP')['cb_run_id'] == planned['cb_run_id']
    for key, value in (('extension_name', 'GeoDCAT-AP'), ('domain', 'statistics')):
        with pytest.raises(ValueError, match=rf"--{key.replace('_', '-')} '{value}' is not the built-in value"):
            cb.plan(stat, **{key: value})
        overridden = cb.plan(stat, override_case_values=True, **{key: value})
        assert overridden['case_values']['sources'][key] == 'override'
    assert cb.plan(stat, override_case_values=True, domain='statistics')['domain']['line'].endswith('for statistics')
    # The synthetic case has no built-in values: both values are needed, with the override.
    for options, match in (({}, '--domain is needed'), ({'domain': DOMAIN, 'extension_name': EXTENSION},
                                                        'needs --override-case-values'),
                           ({'domain': DOMAIN, 'override_case_values': True}, '--extension-name is needed')):
        with pytest.raises(ValueError, match=match):
            cb.plan(pm['inputs'], **options)
    record = cb.prompts_only(stat, tmp_path / 'p.json')
    assert record['case_values'] == planned['case_values'] and record['extension_name'] == 'StatDCAT-AP'
    assert cb.plan(pm['inputs'], **OPTIONS)['case_values'] == {'benchmark_case_id': None, 'built_in': None,
        'sources': {'domain': 'override', 'extension_name': 'override'}}


@pytest.mark.parametrize('name, text, held', [
    ('DCAT-AP-JRC', 'DCAT‑AP‑JRC users', True),           # U+2011 non-breaking hyphen
    ('DCAT-AP-JRC', 'DCAT-AP‑JRC users', True),                # only the outer hyphen
    ('DCAT-AP-JRC', 'DCAT–AP—JRC users', True),           # en and em dash
    ('DCAT-AP-JRC', 'DCAT‐AP−JRC users', True),           # hyphen, minus sign
    ('DCAT-AP-JRC', 'DCAT­AP​JRC users', True),           # soft hyphen, zero-width space
    ('DCAT-AP-JRC', 'DCAT/AP.JRC users', True),
    ('DCAT-AP-JRC', 'dcat_ap_jrc users', True),
    ('DCAT-AP-JRC', 'ＤＣＡＴ－ＡＰ－ＪＲＣ users', True),   # fullwidth
    ('GeoDCAT-AP', 'Geo‑DCAT‑AP implementers', True),
    ('GeoDCAT-AP', 'Geo DCAT AP implementers', True),
    ('GeoDCAT-AP', 'GeoDCAT‑AP Working Group', True),          # as a Mobility run-1 candidate writes it
    ('StatDCAT-AP', 'Stat‑DCAT‑AP adopters', True),
    ('StatDCAT-AP', 'Stat–DCAT–AP adopters', True),
    ('StatDCAT-AP', 'Users of StatDCAT', True),                     # the stem
    ('HealthDCAT-AP', 'Health‑DCAT‑AP adopters', True),
    ('mobilityDCAT-AP', 'Mobility‑DCAT‑AP adopters', True),
    ('StatDCAT-AP', 'Eurostat DCAT-AP working group', False),      # an organisation and the base standard
    ('StatDCAT-AP', 'Eurostat DCAT team', False),
    ('StatDCAT-AP', 'ISTAT DCAT-AP implementers', False),
    ('HealthDCAT-AP', 'eHealth DCAT-AP implementers', False),
    ('DCAT-AP-JRC', 'Joint Research Centre scientists', False),
    ('DCAT-AP-JRC', 'JRC data stewards', False),
    ('DCAT-AP-JRC', 'JRC DCAT-AP adopters', False),                 # by design only the name's own order
])
def test_the_extension_name_is_found_where_a_word_starts_whatever_the_separators(name, text, held):
    forms = cb.extension_forms(name)
    assert any(cb.holds(form, text) for form in forms) is held
    assert (cb.masked(forms, text) != text) is held                # masking finds what the check finds


def test_the_extension_name_or_its_stem_in_any_text_sent_is_refused(pm):
    assert cb.extension_forms('GeoDCAT-AP') == ['GeoDCAT-AP', 'GeoDCAT']
    assert cb.extension_forms('mobilityDCAT-AP') == ['mobilityDCAT-AP', 'mobilityDCAT']
    assert cb.extension_forms('DCAT-AP-JRC') == ['DCAT-AP-JRC'] and cb.extension_forms('GeoMap') == ['GeoMap']
    assert cb.extension_forms('Geo‑DCAT‑AP') == ['Geo‑DCAT‑AP', 'Geo‑DCAT']
    with pytest.raises(ValueError, match='--extension-name'):
        cb.extension_forms(' - ')
    with pytest.raises(ValueError, match=r"The domain line .* contains the extension name 'TeachDCAT'"):
        cb.plan(pm['inputs'], **{**OPTIONS, 'domain': 'teachdcat records'})
    with pytest.raises(ValueError, match=r"The role label 'Teach DCAT stewards' contains the extension name 'TeachDCAT'"):
        cb.plan(changed(pm, label='Teach DCAT stewards'), **OPTIONS)
    with pytest.raises(ValueError, match=r"The stakeholder name 'TEACHDCAT-AP adopters' of role 'Data stewards' contains"
                                         r".*Pass --mask-extension-name"):
        cb.plan(changed(pm, stakeholders=['TEACHDCAT-AP adopters']), **OPTIONS)
    with pytest.raises(ValueError, match='role label'):
        cb.plan(changed(pm, label='Stat‑DCAT‑AP stewards', case='statdcat'))
    # Stakeholder names are given by design: only the extension's own name, where a word starts, is refused.
    jrc = changed(pm, stakeholders=['Joint Research Centre scientists', 'JRC data stewards'], case='jrc-research')
    assert cb.plan(jrc)['extension_check']['forms'] == ['DCAT-AP-JRC']
    stat = changed(pm, stakeholders=['Eurostat DCAT-AP working group'], case='statdcat')
    assert json.loads(cb.plan(stat)['requests'][1]['user'])['role']['stakeholders'] == ['Eurostat DCAT-AP working group']
    for stakeholder in ('DCAT-AP JRC curators', 'DCAT‑AP‑JRC curators', 'DCAT–AP–JRC curators'):
        with pytest.raises(ValueError, match='stakeholder name'):
            cb.plan(changed(pm, stakeholders=[stakeholder], case='jrc-research'))


def test_mask_extension_name_replaces_the_name_in_labels_and_stakeholder_names_and_records_it(pm, tmp_path):
    label, names = 'Geo‑DCAT‑AP stewards', ['GeoDCAT‑AP Working Group',
                                                       "Third‑party users of GeoDCAT-AP's portal", 'Eurostat']
    inputs = changed(pm, label=label, stakeholders=names, case='geodcat')
    with pytest.raises(ValueError, match="role label .* contains the extension name 'GeoDCAT-AP'"):
        cb.plan(inputs)                                          # refused by default
    planned = cb.plan(inputs, mask_extension_name=True)
    stewards = planned['requests'][1]
    assert json.loads(stewards['user'])['role'] == {'label': 'the extension stewards', 'stakeholders': [
        'the extension Working Group', "Third‑party users of the extension's portal", 'Eurostat']}
    assert stewards['extension_name_masked'] == [
        {'field': 'label', 'before': label, 'after': 'the extension stewards'},
        {'field': 'stakeholders[0]', 'before': names[0], 'after': 'the extension Working Group'},
        {'field': 'stakeholders[1]', 'before': names[1], 'after': "Third‑party users of the extension's portal"}]
    assert planned['requests'][0]['extension_name_masked'] == []
    assert planned['extension_check']['masked'] == 3 and planned['extension_check']['mask_extension_name'] is True
    forms = planned['extension_check']['forms']
    assert cb.masked(forms, 'GeoDCAT-AP and GeoDCAT users') == 'the extension and the extension users'
    assert cb.masked(forms, 'Eurostat and GEO DCAT AP, GeoDCAT-APs') == 'Eurostat and the extension, the extensions'
    system, run = planned['requests'][0]['system'], inputs['run']
    replacements = [{'role_id': stewards['role_id'], **change} for change in stewards['extension_name_masked']]
    assert planned['cb_run_id'] == engine.uid('cb', cb.POLICY, run['run_id'], run['role_manifest']['manifest_hash'], 1,
        False, planned['domain']['line'], sha(system), cb.SCHEMA_SHA256, sha(cb.SCHEMA_CORRECTION_TURN), replacements)
    record = cb.prompts_only(inputs, tmp_path / 'p.json', mask_extension_name=True)
    assert record['roles'][1]['extension_name_masked'] == stewards['extension_name_masked']
    assert record['mask_extension_name'] is True and record['roles'][1]['label'] == 'the extension stewards'
    # With nothing to mask, the requests and the ID are those of a run without masking.
    plain = changed(pm, case='geodcat')
    assert cb.plan(plain, mask_extension_name=True)['requests'] == cb.plan(plain)['requests']
    assert cb.plan(plain, mask_extension_name=True)['cb_run_id'] == cb.plan(plain)['cb_run_id']


def test_leak_check_reports_use_cases_source_text_names_and_ids_without_blocking(pm):
    run = deepcopy(pm['run'])
    manifest = run['role_manifest']
    unit = next(e for e in run['evidence_ids'] if SOURCES[1][1] in pm['store'].get('evidence', e)['content'])
    version = pm['sources'][1]['source_version_id']
    manifest['selected_roles'][1]['stakeholders'] = [TASK.statement, SOURCES[1][1], SOURCES[1][0], TASK.id, version]
    reseal(manifest)
    leak = cb.plan(using(pm, run), **OPTIONS)['leak_check']
    stewards = manifest['selected_roles'][1]['role_id']
    found = {(f['kind'], f.get('value', f.get('origin'))) for f in leak['found'] if f['role_id'] == stewards}
    assert {('use_case_statement', TASK.statement), ('use_case_ngram', TASK.id), ('evidence_ngram', unit),
            ('source_name', SOURCES[1][0]), ('task_id', TASK.id), ('source_version_id', version)} <= found
    assert all(f['part'] == 'payload' and f['role_id'] == stewards for f in leak['found'])
    assert leak['scope'] == 'snapshot' and leak['checked']['ngram_words'] == 8
    # From a run document alone: no snapshot, so neither its use cases nor the names no role cites are known.
    document = cb.plan(cb.run_document(run), **OPTIONS)['leak_check']
    assert document['scope'] == 'run_document' and document['not_checked']
    assert not {('use_case_statement', TASK.statement), ('source_name', SOURCES[1][0]), ('evidence_ngram', unit)} & {
        (f['kind'], f.get('value', f.get('origin'))) for f in document['found']}
    cited = deepcopy(pm['run'])
    cited['role_manifest']['selected_roles'][1]['stakeholders'] = [f'Readers of {SOURCES[0][0]}']
    reseal(cited['role_manifest'])
    assert ('source_name', SOURCES[0][0]) in {(f['kind'], f.get('value')) for f in
                                              cb.plan(cb.run_document(cited), **OPTIONS)['leak_check']['found']}


def test_the_leak_check_ignores_separators_case_and_compatibility_forms(pm):
    purpose = pm['roles'][0]['purpose']
    run = deepcopy(pm['run'])
    selected = run['role_manifest']['selected_roles']
    selected[1]['stakeholders'] = ['Readers of synthetic‑access‑note.txt', 'Holders of T–synthetic–7',
                                   purpose.upper().replace('reused', 're­used').replace(' ', ' '),
                                   QUOTE.upper().replace(' ', ' ')]
    # Source names and task IDs only as whole words: these name other files and IDs.
    selected[0]['stakeholders'] = ['Holders of T–synthetic–70', 'XT-synthetic-7 team',
                                   'Readers of synthetic-access-notes']
    reseal(run['role_manifest'])
    leak = cb.plan(using(pm, run), **OPTIONS)['leak_check']
    assert not [f for f in leak['found'] if f['role_id'] == selected[0]['role_id']]
    assert sorted((f['kind'], f['value']) for f in leak['found'] if 'value' in f) == sorted([
        ('source_name', SOURCES[1][0]), ('source_name', 'synthetic-access-note'), ('task_id', TASK.id),
        ('role_text', purpose), ('quotation', QUOTE)])
    assert {f['kind'] for f in leak['found'] if 'value' not in f} == {'quotation_ngram', 'evidence_ngram'}


def test_output_parses_and_ids_are_deterministic(pm, tmp_path):
    run, inputs = pm['run'], pm['inputs']
    first = cb.run_closed_book(inputs, Answering(), tmp_path / 'a.json', **OPTIONS)
    second = cb.run_closed_book(inputs, Answering(), tmp_path / 'b.json', **OPTIONS)
    other = cb.run_closed_book(inputs, Answering(), tmp_path / 'c.json', rep=2, **OPTIONS)
    assert first['kind'] == 'closed_book_run' and first['status'] == 'completed' and first['policy_version'] == cb.POLICY
    system = cb.plan(inputs, **OPTIONS)['requests'][0]['system']
    assert first['cb_run_id'] == second['cb_run_id'] == engine.uid(
        'cb', cb.POLICY, run['run_id'], run['role_manifest']['manifest_hash'], 1, False, LINE, sha(system),
        cb.SCHEMA_SHA256, sha(cb.SCHEMA_CORRECTION_TURN), [])
    assert other['cb_run_id'] != first['cb_run_id']
    assert [n['need_id'] for n in first['needs']] == [n['need_id'] for n in second['needs']]
    assert [c['call_id'] for c in first['calls']] == [c['call_id'] for c in second['calls']]
    assert json.loads((tmp_path / 'a.json').read_text()) == first
    assert len(first['needs']) == len(first['roles']) == 2 and len(first['calls']) == 2
    need = first['needs'][0]
    assert need['obligation'] == 'unknown' and need['condition'] in need['statement'] and need['resource_type'] == 'Dataset'
    assert {first['pm_run_id'], first['manifest_hash'], first['base_profile_id'], first['base_profile_sha256']} == {
        run['run_id'], run['role_manifest']['manifest_hash'], 'dcat-ap-2.0.1', run['base_profile_sha256']}
    assert first['domain'] == {'text': DOMAIN, 'base_release': 'DCAT-AP 2.0.1', 'line': LINE}
    assert first['extension_name'] == EXTENSION and first['runner_sha256'] == cb.RUNNER_SHA256
    assert first['case_values']['sources'] == {'domain': 'override', 'extension_name': 'override'}
    assert first['mask_extension_name'] is False
    assert first['model'] == {'provider': 'openai-compatible', 'model': MODEL, 'reasoning_effort': 'high',
        'copied_from': 'role_runs', 'max_output_tokens': 8000, 'cutoff_retry_output_tokens': 12000, 'schema_repair_attempts': 1}
    assert first['contract']['schema_correction_turn_sha256'] == sha(cb.SCHEMA_CORRECTION_TURN)
    for call in first['calls']:
        assert call['prompt_sha256'] == hashlib.sha256(call['system_prompt'].encode()).hexdigest()
        assert call['payload_sha256'] == hashlib.sha256(call['user_payload'].encode()).hexdigest()
        assert call['token_usage']['total_tokens'] == 1200 and call['latency_seconds'] >= 0 and call['output']
        assert call['max_output_tokens'] == 8000 and call['schema_repair_attempts'] == 1
        assert call['schema_corrections'] == []
    text = (tmp_path / 'a.json').read_text()
    assert 'invalid/v1' not in text and 'base_url' not in text
    diagnostics = first['diagnostics']
    assert diagnostics['endpoint_matches_pm'] is True and diagnostics['parity_check']['status'] == 'passed'
    assert diagnostics['implementation_is_checked'] is True and diagnostics['extension_name_check']['found'] == []
    assert diagnostics['schema_corrections'] == {'turn_sha256': sha(cb.SCHEMA_CORRECTION_TURN), 'sent': 0,
                                                 'forbidden_terms_found': [], 'leak_found': []}


def test_cb_run_id_changes_with_the_system_text_the_schema_and_the_correction_turn(pm, monkeypatch):
    ids = {cb.plan(pm['inputs'], **OPTIONS)['cb_run_id']}
    first, *rest = cb.NEEDS_REPLACEMENTS
    for name, value in (('NEEDS_REPLACEMENTS', ((first[0], first[1] + ' One more sentence.'), *rest)),
                        ('SCHEMA_SHA256', '0' * 64),
                        ('SCHEMA_CORRECTION_TURN', cb.SCHEMA_CORRECTION_TURN + 'One more sentence. ')):
        with monkeypatch.context() as patch:
            patch.setattr(cb, name, value)
            ids.add(cb.plan(pm['inputs'], **OPTIONS)['cb_run_id'])
    assert len(ids) == 4


def reply(content, prompt=500, completion=200, finish='stop'):
    return httpx.Response(200, json={'choices': [{'message': {'content': content}, 'finish_reason': finish}],
        'usage': {'prompt_tokens': prompt, 'completion_tokens': completion, 'total_tokens': prompt + completion}},
        request=httpx.Request('POST', 'https://fake.invalid/v1/chat/completions'))


def openai_client(**options):
    return OpenAICompatibleClient(LLMConfig(provider='openai-compatible', model=MODEL, reasoning_effort='high',
        base_url=f'https://{uuid.uuid4().hex}.invalid/v1', api_key='test-secret', **options))


def real_client(monkeypatch, contents):
    bodies, answers = [], iter(contents)
    def post(url, *, json, headers, timeout):
        bodies.append(json)
        return reply(next(answers))
    monkeypatch.setattr(httpx, 'post', post)
    return openai_client(), bodies


def answer(obligation='unknown', statement='Users can find whom to contact for a restricted table.'):
    return json.dumps({'observations': [{'statement': statement, 'need_condition': '', 'scope': 'Datasets',
                                         'intent': {'resource_type': 'Dataset', 'obligation_hint': obligation}}]})


def test_schema_repair_retry_goes_through_the_workbench_client(pm, tmp_path, monkeypatch):
    client, bodies = real_client(monkeypatch, ['{"observations": [{"scope": "no statement"}]}', answer(),
                                               answer(), answer()])
    record = cb.run_closed_book(pm['inputs'], client, tmp_path / 'r.json', workers=1, allow_other_endpoint=True,
                                **OPTIONS)
    first = next(c for c in record['calls'] if c['sequence'] == 1 and len(c['generations']) == 2)
    assert first['status'] == 'accepted' and [g['purpose'] for g in first['generations']] == ['initial', 'schema_correction']
    assert first['token_usage'] == {'prompt_tokens': 1000, 'completion_tokens': 400, 'total_tokens': 1400}
    sent = bodies[0]
    assert first['system_prompt'] == sent['messages'][0]['content'] and first['user_payload'] == sent['messages'][1]['content']
    assert sent['max_tokens'] == 8000 and sent['reasoning_effort'] == 'high' and sent['model'] == MODEL
    assert len(bodies[1]['messages']) == 4 and 'failed the JSON contract' in bodies[1]['messages'][3]['content']
    assert first['schema_corrections'][0]['text'] == bodies[1]['messages'][3]['content']
    assert 'test-secret' not in (tmp_path / 'r.json').read_text()


def test_the_schema_correction_turn_sent_is_recorded_and_checked(pm, tmp_path, monkeypatch):
    extra = json.dumps({'observations': [{'statement': 'Users can find a licence.', 'evidence_links': []}]})
    client, bodies = real_client(monkeypatch, [extra, answer(), answer()])
    record = cb.run_closed_book(pm['inputs'], client, tmp_path / 'r.json', workers=1, allow_other_endpoint=True,
                                **OPTIONS)
    first, turn = record['calls'][0], bodies[1]['messages'][3]['content']
    # The copy of the client's turn is what the client sends, followed by the validation issues it records.
    assert turn == cb.SCHEMA_CORRECTION_TURN + json.dumps(first['generations'][0]['validation_issues'])
    assert first['schema_corrections'] == [{'generation': 2, 'text': turn, 'sha256': sha(turn)}]
    assert [c['schema_corrections'] for c in record['calls'][1:]] == [[]]
    # Reported, not blocking: the issues name the model's own extra field.
    assert record['diagnostics']['schema_corrections'] == {
        'turn_sha256': sha(cb.SCHEMA_CORRECTION_TURN), 'sent': 1, 'leak_found': [],
        'forbidden_terms_found': [{'call_id': first['call_id'], 'generation': 2, 'terms': ['evidence_links']}]}
    assert record['status'] == 'completed'
    # A PM string in a correction turn would be reported, as in the text sent before an answer.
    with monkeypatch.context() as patch:
        patch.setattr(cb, 'SCHEMA_CORRECTION_TURN', cb.SCHEMA_CORRECTION_TURN + f'See {SOURCES[0][0]}. ')
        planned = cb.plan(pm['inputs'], **OPTIONS)
        assert {(f['part'], f['value']) for f in planned['leak_check']['found']} == {
            ('schema_correction', SOURCES[0][0]), ('schema_correction', 'synthetic-portal-guide')}
        assert {f['part'] for f in cb.correction_check(planned, [{**first, 'schema_corrections': [
            {'generation': 2, 'text': cb.schema_correction_text([])}]}])['leak_found']} == {'schema_correction_sent'}


def test_an_obligation_label_is_reset_to_unknown_after_the_repair(pm, tmp_path, monkeypatch):
    client, _ = real_client(monkeypatch, [answer('mandatory')] * 2 + [answer()] * 2)
    record = cb.run_closed_book(pm['inputs'], client, tmp_path / 'r.json', workers=1, allow_other_endpoint=True,
                                **OPTIONS)
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
    record = cb.run_closed_book(pm['inputs'], CutOnce(), tmp_path / 'r.json', **OPTIONS)
    assert record['status'] == 'completed'
    assert sorted((c['purpose'], c['max_output_tokens'], c['status']) for c in record['calls']) == [
        ('initial', 8000, 'output_cutoff')] * 2 + [('larger_response_after_cutoff', 12000, 'accepted')] * 2


def test_a_role_cut_off_at_both_budgets_fails_after_exactly_two_calls(pm, tmp_path):
    class AlwaysCut(Answering):
        def generate_structured(self, **kwargs):
            self.calls.append(kwargs)
            raise OutputTokenLimitError('finish_reason=length')
    client = AlwaysCut()
    record = cb.run_closed_book(pm['inputs'], client, tmp_path / 'r.json', **OPTIONS)
    assert record['status'] == 'incomplete' and len(client.calls) == 4 and record['needs'] == []
    for role in record['roles']:
        calls = [c for c in record['calls'] if c['role_id'] == role['role_id']]
        assert role['status'] == 'failed' and [(c['max_output_tokens'], c['status']) for c in calls] == [
            (8000, 'output_cutoff'), (12000, 'output_cutoff')]


def test_a_failed_role_is_kept_sanitized_and_resume_calls_only_that_role(pm, tmp_path):
    out = tmp_path / 'r.json'
    record = cb.run_closed_book(pm['inputs'], Answering(fail={'Data stewards'}), out, **OPTIONS)
    assert record['status'] == 'incomplete' and len(record['diagnostics']['failed_roles']) == 1
    failed = next(c for c in record['calls'] if c['status'] == 'failed')
    assert failed['error'] == {'type': 'LLMError', 'message': 'OpenAI-compatible request to <url> failed: 503'}
    assert 'cb-endpoint' not in out.read_text()
    client = Answering()
    resumed = cb.run_closed_book(pm['inputs'], client, out, resume=True, **OPTIONS)
    assert resumed['status'] == 'completed' and len(client.calls) == 1
    assert json.loads(client.calls[0]['user'])['role']['label'] == 'Data stewards'
    stewards = next(r for r in resumed['roles'] if r['label'] == 'Data stewards')
    assert len(stewards['call_ids']) == 2 and resumed['created_at'] == record['created_at']
    # The resumed role continues its sequence: every call ID stays unique.
    assert [c['sequence'] for c in resumed['calls'] if c['role_id'] == stewards['role_id']] == [1, 2]
    assert len({c['call_id'] for c in resumed['calls']}) == len(resumed['calls']) == 3
    assert [n['need_id'] for n in resumed['needs'] if n['role_label'] == 'Teaching librarians'] == [
        n['need_id'] for n in record['needs'] if n['role_label'] == 'Teaching librarians']
    with pytest.raises(ValueError, match='another --with-shared-extractor'):
        cb.run_closed_book(pm['inputs'], Answering(), out, resume=True, with_shared_extractor=True, **OPTIONS)
    # Nothing left to call: the completed record stays as it is.
    saved = out.read_text()
    again = Answering()
    assert cb.run_closed_book(pm['inputs'], again, out, resume=True, **OPTIONS) == json.loads(saved)
    assert again.calls == [] and out.read_text() == saved


def test_resume_refuses_a_record_that_is_not_this_run_or_was_written_otherwise(pm, tmp_path):
    out = tmp_path / 'r.json'
    cb.run_closed_book(pm['inputs'], Answering(fail={'Data stewards'}), out, **OPTIONS)
    saved = json.loads(out.read_text())
    edited_roles = [{**role, 'request_sha256': '0' * 64} for role in saved['roles']]
    for change, match in (({'runner_sha256': '0' * 64}, 'another version of scripts/closed_book.py'),
                          ({'contract': {**saved['contract'], 'schema_sha256': '0' * 64}}, 'another output schema'),
                          ({'domain': {**saved['domain'], 'line': 'an extension of DCAT-AP 2.0.1 for other data'}},
                           'another domain line'),
                          ({'kind': 'closed_book_preview'}, 'another record'),
                          ({'status': 'prompts_only'}, 'prompts-only record'),
                          ({'cb_run_id': 'cb-0'}, 'another record'),
                          ({'model': {**saved['model'], 'reasoning_effort': 'low'}}, 'another model configuration'),
                          ({'roles': edited_roles}, 'The request for .* changed'),
                          ({'workbench_implementation_hash': 'e' * 64}, 'another workbench implementation'),
                          ({'diagnostics': {**saved['diagnostics'], 'endpoint_matches_pm': False}},
                           'endpoint_matches_pm'),
                          ({'diagnostics': {**saved['diagnostics'], 'other_endpoint_allowed': True}},
                           'another --allow-other-endpoint setting')):
        out.write_text(json.dumps({**saved, **change}))
        client = Answering()
        with pytest.raises(ValueError, match=match):
            cb.run_closed_book(pm['inputs'], client, out, resume=True, **OPTIONS)
        assert client.calls == []
    out.write_text(json.dumps(saved))
    for options, match in (({'rep': 2}, 'another record'), ({'allow_other_endpoint': True}, '--allow-other-endpoint')):
        client = Answering()
        with pytest.raises(ValueError, match=match):
            cb.run_closed_book(pm['inputs'], client, out, resume=True, **{**OPTIONS, **options})
        assert client.calls == [] and json.loads(out.read_text()) == saved
    # A run made at another endpoint is not completed at PM's.
    other = tmp_path / 'other.json'
    cb.run_closed_book(pm['inputs'], Answering(fail={'Data stewards'}, endpoint='https://other.invalid/v1'), other,
                       allow_other_endpoint=True, **OPTIONS)
    with pytest.raises(ValueError, match='endpoint_matches_pm'):
        cb.run_closed_book(pm['inputs'], Answering(), other, resume=True, allow_other_endpoint=True, **OPTIONS)


def test_malformed_json_inputs_are_refused_and_never_overwritten(pm, tmp_path, monkeypatch, capsys):
    run_json, out = tmp_path / 'pm.json', tmp_path / 'p.json'
    for text in ('[]', '[1]', '"x"', '3', 'null', '{"run": [1]}', '{not json'):
        run_json.write_text(text)
        assert cb.main(['--run-json', str(run_json), '--out', str(out), '--prompts-only', '--override-case-values',
                        '--domain', DOMAIN, '--extension-name', EXTENSION]) == 2
        assert 'closed_book: error:' in capsys.readouterr().err and not out.exists()
    record = tmp_path / 'r.json'
    for text in ('[]', '[1]', '"x"', 'null', '{}'):
        record.write_text(text)
        client = Answering()
        with pytest.raises(ValueError, match='holds no CB record|holds another record'):
            cb.run_closed_book(pm['inputs'], client, record, resume=True, **OPTIONS)
        assert client.calls == [] and record.read_text() == text
    monkeypatch.setenv('RRS_LLM_PROVIDER', 'openai-compatible')
    monkeypatch.setenv('RRS_LLM_BASE_URL', PM_ENDPOINT)
    monkeypatch.setattr(httpx, 'post', lambda *args, **kwargs: pytest.fail('no call for a malformed record'))
    record.write_text('[]')
    assert cb.main(store_args(pm, record, '--allow-live-provider', '--resume')) == 2 and record.read_text() == '[]'


def test_the_record_is_written_after_each_role(pm, tmp_path):
    out, seen = tmp_path / 'r.json', []

    class Reading(Answering):
        def generate_structured(self, **kwargs):
            if json.loads(kwargs['user'])['role']['label'] == 'Data stewards':
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline and json.loads(out.read_text())['roles'][0]['status'] != 'completed':
                    time.sleep(0.01)
                seen.append([role['status'] for role in json.loads(out.read_text())['roles']])
            return super().generate_structured(**kwargs)
    cb.run_closed_book(pm['inputs'], Reading(), out, workers=1, **OPTIONS)
    assert seen == [['completed', 'not_called']]


def test_roles_run_concurrently_up_to_the_clients_request_limit(pm, tmp_path):
    class Limited(Answering):
        def __init__(self, limit):
            super().__init__()
            self.limit, self.active, self.most, self.lock = limit, 0, 0, threading.Lock()

        def describe(self):
            return {**super().describe(), 'max_concurrency': self.limit}

        def generate_structured(self, **kwargs):
            with self.lock:
                self.active += 1
                self.most = max(self.most, self.active)
            deadline = time.monotonic() + 0.5                  # wait briefly for a second role in flight
            while time.monotonic() < deadline and self.active < 2:
                time.sleep(0.005)
            try:
                return super().generate_structured(**kwargs)
            finally:
                with self.lock:
                    self.active -= 1
    for limit in (2, 1):
        client = Limited(limit)
        record = cb.run_closed_book(pm['inputs'], client, tmp_path / f'{limit}.json', with_shared_extractor=True,
                                    **OPTIONS)
        assert record['status'] == 'completed' and client.most == limit


def test_an_interrupt_cancels_queued_roles_keeps_finished_ones_and_writes_the_record(pm, tmp_path, monkeypatch):
    started, release, ended = threading.Event(), threading.Event(), threading.Event()

    class Blocking(Answering):
        def generate_structured(self, **kwargs):
            if json.loads(kwargs['user'])['role']['label'] != 'Data stewards':
                return super().generate_structured(**kwargs)
            started.set()
            release.wait(10)
            try:
                return super().generate_structured(**kwargs)
            finally:
                ended.set()

    real_as_completed = cb.as_completed

    def interrupted(futures):
        wait(futures, return_when=FIRST_COMPLETED)      # the first role is done, not yet taken by the loop
        started.wait(10)                                 # the second is in flight, the third still queued
        raise KeyboardInterrupt
    monkeypatch.setattr(cb, 'as_completed', interrupted)
    client, out = Blocking(), tmp_path / 'r.json'
    with pytest.raises(KeyboardInterrupt):
        cb.run_closed_book(pm['inputs'], client, out, workers=1, with_shared_extractor=True, **OPTIONS)
    release.set()
    assert ended.wait(10)
    record = json.loads(out.read_text())
    assert record['status'] == 'interrupted'
    assert [(r['label'], r['status']) for r in record['roles']] == [
        ('Teaching librarians', 'completed'), ('Data stewards', 'interrupted'), ('Shared needs', 'not_called')]
    assert [json.loads(c['user'])['role']['label'] for c in client.calls] == ['Teaching librarians', 'Data stewards']
    assert len(record['calls']) == 1 and len(record['needs']) == 1
    assert record['diagnostics']['interrupted_roles'] == [record['roles'][1]['role_id']]
    monkeypatch.setattr(cb, 'as_completed', real_as_completed)
    again = Answering()
    resumed = cb.run_closed_book(pm['inputs'], again, out, resume=True, with_shared_extractor=True, **OPTIONS)
    assert resumed['status'] == 'completed' and len(again.calls) == 2 and len(resumed['calls']) == 3


def test_an_interrupt_keeps_the_earlier_calls_of_the_role_in_flight(pm, tmp_path, monkeypatch):
    out, started, release = tmp_path / 'r.json', threading.Event(), threading.Event()
    cb.run_closed_book(pm['inputs'], Answering(fail={'Data stewards'}), out, **OPTIONS)

    class Blocking(Answering):
        def generate_structured(self, **kwargs):
            started.set()
            release.wait(10)
            return super().generate_structured(**kwargs)

    def interrupted(futures):
        started.wait(10)
        raise KeyboardInterrupt
    monkeypatch.setattr(cb, 'as_completed', interrupted)
    with pytest.raises(KeyboardInterrupt):
        cb.run_closed_book(pm['inputs'], Blocking(), out, resume=True, **OPTIONS)
    release.set()
    record = json.loads(out.read_text())
    stewards = next(r for r in record['roles'] if r['label'] == 'Data stewards')
    assert record['status'] == 'interrupted' and stewards['status'] == 'interrupted'
    assert [c['status'] for c in record['calls'] if c['role_id'] == stewards['role_id']] == ['failed']


def test_an_interrupt_just_after_a_role_finished_records_its_calls_once(pm, tmp_path):
    """Ctrl-C between finishing a role and marking it consumed: the except block finishes it again."""
    source = Path(cb.__file__).read_text().splitlines()
    line = next(number for number, text in enumerate(source, 1) if text.strip() == 'consumed.add(future)')

    def local(frame, event, arg):
        if event == 'line' and frame.f_lineno == line:
            raise KeyboardInterrupt         # an exception from the trace function also ends the tracing
        return local
    out = tmp_path / 'r.json'
    sys.settrace(lambda frame, event, arg: local if frame.f_code.co_name == 'run_closed_book' else None)
    try:
        with pytest.raises(KeyboardInterrupt):
            cb.run_closed_book(pm['inputs'], Answering(), out, workers=1, **OPTIONS)
    finally:
        sys.settrace(None)
    record = json.loads(out.read_text())
    first = record['roles'][0]
    assert record['status'] == 'interrupted' and first['status'] == 'completed' and len(first['call_ids']) == 1
    assert len({c['call_id'] for c in record['calls']}) == len(record['calls'])


def interrupt_with_the_real_client(monkeypatch, post, signal):
    """Patch httpx and the executor for an interrupt raised once signal is set; returns the executors made."""
    executors, real_executor = [], cb.ThreadPoolExecutor

    def executor(max_workers):
        executors.append((max_workers, real_executor(max_workers=max_workers)))
        return executors[-1][1]

    def interrupted(futures):
        assert signal.wait(10)
        raise KeyboardInterrupt
    monkeypatch.setattr(httpx, 'post', post)
    monkeypatch.setattr(cb, 'ThreadPoolExecutor', executor)
    monkeypatch.setattr(cb, 'as_completed', interrupted)
    return executors


def test_an_interrupt_with_the_real_client_sends_no_queued_role_and_starts_no_further_call(pm, tmp_path, monkeypatch):
    """With the endpoint limit 1, the roles not started wait in the queue and are cancelled; the role in flight is
    cut off after the interrupt and starts no 12,000-token call."""
    in_flight, release, posts = threading.Event(), threading.Event(), []

    def post(url, *, json, headers, timeout):
        posts.append(json)
        in_flight.set()
        release.wait(10)
        return reply('{"observations": []}', finish='length')
    executors = interrupt_with_the_real_client(monkeypatch, post, in_flight)
    out = tmp_path / 'r.json'
    with pytest.raises(KeyboardInterrupt):
        cb.run_closed_book(pm['inputs'], openai_client(max_concurrency=1), out, with_shared_extractor=True,
                           allow_other_endpoint=True, **OPTIONS)
    release.set()
    (workers, executor), = executors
    executor.shutdown(wait=True)
    assert workers == 1 and len(posts) == 1 and posts[0]['max_tokens'] == 8000
    record = json.loads(out.read_text())
    assert [r['status'] for r in record['roles']] == ['interrupted', 'not_called', 'not_called']
    assert record['status'] == 'interrupted' and record['calls'] == []


def test_an_interrupt_keeps_the_calls_a_role_finished_and_resume_continues_its_sequence(pm, tmp_path, monkeypatch):
    in_flight, release, posts = threading.Event(), threading.Event(), []

    def post(url, *, json, headers, timeout):
        posts.append(json)
        if json['max_tokens'] == 8000:
            return reply('{"observations": []}', finish='length')     # cut off at once
        in_flight.set()                                                   # the 12,000-token call is in flight
        release.wait(10)
        return reply(answer())
    executors = interrupt_with_the_real_client(monkeypatch, post, in_flight)
    out, client = tmp_path / 'r.json', openai_client(max_concurrency=1)
    with pytest.raises(KeyboardInterrupt):
        cb.run_closed_book(pm['inputs'], client, out, allow_other_endpoint=True, **OPTIONS)
    release.set()
    executors[0][1].shutdown(wait=True)
    assert [p['max_tokens'] for p in posts] == [8000, 12000]
    record = json.loads(out.read_text())
    first = record['roles'][0]
    assert first['status'] == 'interrupted' and record['roles'][1]['status'] == 'not_called'
    assert [(c['sequence'], c['max_output_tokens'], c['status']) for c in record['calls']] == [(1, 8000, 'output_cutoff')]
    monkeypatch.setattr(cb, 'as_completed', as_completed)
    monkeypatch.setattr(cb, 'ThreadPoolExecutor', ThreadPoolExecutor)
    monkeypatch.setattr(httpx, 'post', lambda url, *, json, headers, timeout: reply(answer()))
    resumed = cb.run_closed_book(pm['inputs'], client, out, resume=True, allow_other_endpoint=True, **OPTIONS)
    assert resumed['status'] == 'completed'
    assert [c['sequence'] for c in resumed['calls'] if c['role_id'] == first['role_id']] == [1, 2]
    assert len({c['call_id'] for c in resumed['calls']}) == len(resumed['calls']) == 3


def test_errors_are_recorded_without_the_endpoint_its_host_the_key_a_bearer_token_or_any_url(pm, tmp_path, monkeypatch):
    key, host = 'synthetic-key-0123456789\r', 'private-gateway.invalid'      # a key read from a CRLF file
    client = OpenAICompatibleClient(LLMConfig(provider='openai-compatible', model=MODEL, reasoning_effort='high',
                                              base_url=f'https://{host}/v1', api_key=key, transient_retries=0))
    errors = iter([httpx.ConnectError('[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: Hostname mismatch, '
                                      f"certificate is not valid for '{host}'. (_ssl.c:1000)"),
                   httpx.LocalProtocolError(f"Illegal header value {('Bearer ' + key).encode()!r}")])

    def post(url, *, json, headers, timeout):
        raise next(errors)
    monkeypatch.setattr(httpx, 'post', post)
    record = cb.run_closed_book(pm['inputs'], client, tmp_path / 'r.json', workers=1, allow_other_endpoint=True,
                                **OPTIONS)
    messages = [c['error']['message'] for c in record['calls']]
    assert 'Hostname mismatch' in messages[0] and 'Illegal header value' in messages[1] and len(messages) == 2
    text = (tmp_path / 'r.json').read_text()
    for secret in (host, 'private-gateway', key.strip(), 'Bearer synthetic', 'invalid/v1'):
        assert secret not in text
    assert cb.sanitized(LLMError('token Bearer abc.def-123 was rejected'), object())['message'] == \
        'token Bearer <key> was rejected'
    # A redirect to another host: its Location is removed when scheme-relative and whatever the case of the scheme.
    locations = iter(['//sso.other-host.invalid/login?next=/v1', 'HTTPS://SSO.OTHER-HOST.INVALID/login'])
    monkeypatch.setattr(httpx, 'post', lambda url, *, json, headers, timeout: httpx.Response(
        302, headers={'Location': next(locations)}, request=httpx.Request('POST', url)))
    record = cb.run_closed_book(pm['inputs'], client, tmp_path / 's.json', workers=1, allow_other_endpoint=True,
                                **OPTIONS)
    messages = [c['error']['message'] for c in record['calls']]
    assert len(messages) == 2 and all("Redirect location: '<url>'" in message for message in messages)
    assert 'other-host' not in (tmp_path / 's.json').read_text().casefold() and host not in messages[0]
    assert cb.sanitized(LLMError("to 'Https://Other.invalid/x' and ftp://y.invalid"), object())['message'] == \
        "to '<url>' and <url>"


def test_another_endpoint_is_refused_unless_allowed(pm, tmp_path):
    other = Answering(endpoint='https://other-gateway.invalid/v1')
    with pytest.raises(ValueError, match='--allow-other-endpoint') as refused:
        cb.run_closed_book(pm['inputs'], other, tmp_path / 'r.json', **OPTIONS)
    assert 'invalid' not in str(refused.value) and not (tmp_path / 'r.json').exists() and other.calls == []
    record = cb.run_closed_book(pm['inputs'], other, tmp_path / 'r.json', allow_other_endpoint=True, **OPTIONS)
    assert record['status'] == 'completed' and record['diagnostics']['endpoint_matches_pm'] is False
    assert record['diagnostics']['other_endpoint_allowed'] is True
    assert 'gateway.invalid' not in (tmp_path / 'r.json').read_text()
    same = cb.run_closed_book(pm['inputs'], Answering(endpoint=PM_ENDPOINT + '/'), tmp_path / 's.json', **OPTIONS)
    assert same['diagnostics']['endpoint_matches_pm'] is True


def test_other_workflow_code_only_warns_and_the_parity_check_decides(pm, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cb, 'implementation_identity', lambda: 'f' * 64)
    out = tmp_path / 'p.json'
    assert cb.main(store_args(pm, out, '--prompts-only')) == 0
    assert 'warning' in capsys.readouterr().err
    record = json.loads(out.read_text())
    assert record['workbench_implementation_hash'] == 'f' * 64
    assert record['diagnostics']['implementation_is_checked'] is False
    assert record['diagnostics']['parity_check']['status'] == 'passed'
    assert cb.run_closed_book(pm['inputs'], Answering(), tmp_path / 'r.json', **OPTIONS)['status'] == 'completed'


def test_schema_descriptions_mirror_pms_and_prompts_only_records_the_text_as_sent(pm, tmp_path):
    pm_text = dict(descriptions(NeedSpanElicitationResult.model_json_schema()))
    assert dict(descriptions(cb.ClosedBookNeedResult.model_json_schema())) == {
        '/$defs/ClosedBookIntent': pm_text['/$defs/NormalizedIntent'],
        '/$defs/ClosedBookNeed': 'Current provider contract: needs, never extension solution labels.',
        '/$defs/ClosedBookNeed/properties/need_condition':
            'The stated condition of the need, as an exact phrase of its statement, or empty.'}
    record = cb.prompts_only(pm['inputs'], tmp_path / 'p.json', **OPTIONS)
    client = OpenAICompatibleClient(LLMConfig(provider='openai-compatible', model=MODEL,
                                              base_url='https://schema-only.invalid/v1'))
    for planned, request in zip(record['planned_requests'], cb.plan(pm['inputs'], **OPTIONS)['requests']):
        assert planned['system_prompt'] == cb.system_as_sent(client, request['system'])
        assert 'The JSON object must conform to this JSON Schema' in planned['system_prompt']
        assert planned['system_prompt_sha256'] == hashlib.sha256(planned['system_prompt'].encode()).hexdigest()


def test_cb_run_id_names_the_condition_and_the_shared_extractor_needs_a_routed_run(pm):
    inputs, run = pm['inputs'], pm['run']
    ids = {cb.plan(inputs, **{**OPTIONS, **change})['cb_run_id']
           for change in ({}, {'with_shared_extractor': True}, {'rep': 2}, {'domain': 'library data'})}
    assert len(ids) == 4
    independent = cb.run_document({**run, 'request': {**run['request'], 'stakeholder_workflow': 'independent',
                                                      'requirements_scope': 'find_access_v1'}})
    assert [r['kind'] for r in cb.plan(independent, **OPTIONS)['requests']] == ['panel', 'panel']
    with pytest.raises(ValueError, match='needs a routed PM run'):
        cb.plan(independent, with_shared_extractor=True, **OPTIONS)


def test_roles_pm_routed_no_units_are_recorded_and_the_shared_extractor_is_opt_in(pm):
    planned = cb.plan(pm['inputs'], **OPTIONS)
    stewards = next(r for r in planned['requests'] if r['label'] == 'Data stewards')
    assert [r['kind'] for r in planned['requests']] == ['panel', 'panel']
    assert planned['pm_roles_without_units'] == [stewards['role_id']] and stewards['pm_evidence_unit_count'] == 0
    assert planned['pm_shared_extractor_unit_count'] == 0 and planned['roles_without_stakeholders'] == []
    shared = cb.plan(pm['inputs'], with_shared_extractor=True, **OPTIONS)
    request = shared['requests'][-1]
    assert request['kind'] == 'shared_extractor' and request['role_id'] == 'shared_source_extractor'
    assert json.loads(request['user']) == {'domain': LINE, 'role': {'label': 'Shared needs', 'stakeholders': []}}
    assert request['role_text_changes'] == [{'field': 'label', 'pm': 'Shared source needs', 'cb': 'Shared needs'}]
    assert shared['roles_without_stakeholders'] == ['shared_source_extractor']


def test_model_comes_from_role_runs_else_step_models_and_must_match_the_client(pm):
    run = deepcopy(pm['run'])
    assert cb.plan(using(pm, run), **OPTIONS)['model'] == {'provider': 'openai-compatible', 'model': MODEL,
                                                           'reasoning_effort': 'high', 'source': 'role_runs'}
    with pytest.raises(ValueError, match='not the PM extraction model'):
        cb.client_identity(Answering(effort='low'), cb.plan(using(pm, run), **OPTIONS)['model'], PM_ENDPOINT)
    two = deepcopy(run)
    two['role_runs'][1]['provider'] = {**two['role_runs'][0]['provider'], 'base_url': 'https://second.invalid/v1'}
    with pytest.raises(ValueError, match='different endpoints') as refused:
        cb.plan(using(pm, two), **OPTIONS)
    assert 'invalid' not in str(refused.value)
    for report in run['role_runs']:
        report['provider'] = 'offline-mock'
    assert cb.plan(using(pm, run), **OPTIONS)['model'] == {'provider': None, 'model': MODEL, 'reasoning_effort': 'high',
                                                           'source': 'step_models'}
    run['role_runs'][0]['provider'] = {'provider': 'openai-compatible', 'model': 'another-model'}
    run['role_runs'][1]['provider'] = {'provider': 'openai-compatible', 'model': MODEL}
    with pytest.raises(ValueError, match='different models'):
        cb.plan(using(pm, run), **OPTIONS)


def test_only_needs_form_fa_runs_with_their_extraction_policy_are_accepted(pm):
    for change in ({'request': {**pm['run']['request'], 'output_form': 'candidates'}},
                   {'request': {**pm['run']['request'], 'stakeholder_workflow': 'independent', 'requirements_scope': None}},
                   {'elicitation_policy_version': 'rq1-older-elicitation'},
                   {'stakeholder_audit': {'fa_contract': {'policy_version': 'rq1-find-access-v0'}}}):
        with pytest.raises(ValueError):
            cb.plan(using(pm, {**pm['run'], **change}), **OPTIONS)
    with pytest.raises(ValueError, match='lacks role_runs'):
        cb.plan(using(pm, {k: v for k, v in pm['run'].items() if k != 'role_runs'}), **OPTIONS)


def test_store_is_read_only_and_matches_the_stored_run(pm, monkeypatch):
    path, run_id = pm['path'], pm['run']['run_id']
    before = hashlib.sha256(path.read_bytes()).digest(), path.stat().st_mtime_ns
    opened = []
    real_connect = sqlite3.connect
    monkeypatch.setattr(cb.sqlite3, 'connect', lambda target, **kw: opened.append((target, kw)) or real_connect(target, **kw))
    inputs = cb.read_store(path, run_id)
    run = inputs['run']
    assert opened and all(target.endswith('?mode=ro') and kw.get('uri') for target, kw in opened)
    assert (hashlib.sha256(path.read_bytes()).digest(), path.stat().st_mtime_ns) == before
    assert {k: run[k] for k in ('role_manifest', 'role_runs', 'step_models')} == {
        k: pm['run'][k] for k in ('role_manifest', 'role_runs', 'step_models')}
    assert run['stakeholder_audit'] == {'fa_contract': pm['run']['stakeholder_audit']['fa_contract']}
    assert inputs['snapshot']['user_tasks'] == [TASK.model_dump(mode='json')]
    assert sorted(s['name'] for s in inputs['sources']) == sorted(name for name, _ in SOURCES)
    assert sorted(e['evidence_id'] for e in inputs['evidence']) == sorted(pm['run']['evidence_ids'])
    assert inputs['extraction_calls'] and inputs['scope'] == 'snapshot'
    assert cb.plan(inputs, **OPTIONS)['requests'] == cb.plan(pm['inputs'], **OPTIONS)['requests']
    db = real_connect(opened[0][0], uri=True)
    with pytest.raises(sqlite3.OperationalError, match='readonly'):
        db.execute("UPDATE objects SET body='{}' WHERE kind='run'")
    db.close()
    missing = path.with_name('absent.sqlite3')
    with pytest.raises(ValueError, match='No workbench store'):
        cb.read_store(missing, run_id)
    assert not missing.exists()


def store_args(pm, out, *extra, run_id=None, case_values=True):
    values = ['--domain', DOMAIN, '--extension-name', EXTENSION, '--override-case-values'] if case_values else []
    return ['--store', str(pm['path']), '--run-id', run_id or pm['run']['run_id'], '--out', str(out), *values, *extra]


def test_cli_end_to_end_with_the_workbench_client_and_fake_http(pm, tmp_path, monkeypatch):
    out = tmp_path / 'cb.json'
    monkeypatch.setenv('RRS_LLM_PROVIDER', 'openai-compatible')
    monkeypatch.setenv('RRS_LLM_BASE_URL', PM_ENDPOINT)
    monkeypatch.setenv('RRS_LLM_MODEL', 'some-default-model')
    monkeypatch.setenv('RRS_LLM_API_KEY', 'test-secret')
    assert cb.main(store_args(pm, out)) == 2 and not out.exists()                    # no --allow-live-provider
    bodies = []
    monkeypatch.setattr(httpx, 'post', lambda url, *, json, headers, timeout: bodies.append(json) or reply(answer()))
    assert cb.main(store_args(pm, out, '--allow-live-provider')) == 0
    record = json.loads(out.read_text())
    assert record['status'] == 'completed' and len(bodies) == 2 and len(record['needs']) == 2
    assert {b['model'] for b in bodies} == {MODEL} and {b['reasoning_effort'] for b in bodies} == {'high'}
    assert all(b['max_tokens'] == 8000 for b in bodies)
    assert {b['messages'][1]['content'] for b in bodies} == {r['user'] for r in cb.plan(pm['inputs'], **OPTIONS)['requests']}
    text = out.read_text()
    assert 'test-secret' not in text and 'pm-endpoint' not in text and record['diagnostics']['endpoint_matches_pm'] is True
    assert cb.main(store_args(pm, out, '--allow-live-provider')) == 2             # an existing record needs --resume
    assert cb.main(store_args(pm, out, '--allow-live-provider', '--resume')) == 0 and len(bodies) == 2
    monkeypatch.setenv('RRS_LLM_BASE_URL', 'https://configured-endpoint.invalid/v1')
    assert cb.main(store_args(pm, tmp_path / 'other.json', '--allow-live-provider')) == 2 and len(bodies) == 2
    assert cb.main(store_args(pm, tmp_path / 'other.json', '--allow-live-provider', '--allow-other-endpoint')) == 0


def test_cli_uses_the_built_in_case_values(pm, tmp_path, capsys):
    body = pm['store'].get_run(pm['run']['run_id'], parts=False)
    pm['store'].put('run', 'run-stat-synthetic', {**body, 'run_id': 'run-stat-synthetic',
                                                  'request': {**body['request'], 'benchmark_case_id': 'statdcat'}})
    out = tmp_path / 'p.json'
    assert cb.main(store_args(pm, out, '--prompts-only', run_id='run-stat-synthetic', case_values=False)) == 0
    printed = capsys.readouterr().out
    assert '"an extension of DCAT-AP 2.0.1 for statistical data" (domain built_in, extension name built_in)' in printed
    assert 'Extension-name check: passed, StatDCAT-AP and StatDCAT in none of 7 texts.' in printed
    assert json.loads(out.read_text())['case_values']['sources'] == {'domain': 'built_in', 'extension_name': 'built_in'}
    other = store_args(pm, tmp_path / 'q.json', '--prompts-only', '--extension-name', 'GeoDCAT-AP',
                       run_id='run-stat-synthetic', case_values=False)
    assert cb.main(other) == 2 and 'not the built-in value' in capsys.readouterr().err
    assert cb.main([*other, '--override-case-values']) == 0
    assert json.loads((tmp_path / 'q.json').read_text())['case_values']['sources']['extension_name'] == 'override'


def test_cli_exit_codes_for_refusals_a_failed_role_and_a_record_that_cannot_be_written(pm, tmp_path, monkeypatch,
                                                                                         capsys):
    out = tmp_path / 'cb.json'
    monkeypatch.setenv('RRS_LLM_PROVIDER', 'openai-compatible')
    monkeypatch.delenv('RRS_LLM_BASE_URL', raising=False)
    monkeypatch.setenv('RRS_LLM_API_KEY', 'test-secret')
    assert cb.main(store_args(pm, out, '--allow-live-provider')) == 2                   # no base URL: LLMError
    assert 'RRS_LLM_BASE_URL must be set' in capsys.readouterr().err
    not_a_store = tmp_path / 'not-a-store.sqlite3'
    not_a_store.write_text('This file is not a SQLite database.\n' * 100)
    assert cb.main(['--store', str(not_a_store), '--run-id', 'run-x', '--out', str(out), '--domain', DOMAIN,
                    '--extension-name', EXTENSION, '--prompts-only']) == 2               # sqlite3.DatabaseError
    assert 'not a database' in capsys.readouterr().err
    named = store_args(pm, out, '--prompts-only')
    named[named.index('--domain') + 1] = 'TeachDCAT records'
    assert cb.main(named) == 2 and 'extension name' in capsys.readouterr().err
    assert not out.exists()
    monkeypatch.setenv('RRS_LLM_BASE_URL', PM_ENDPOINT)

    def post(url, *, json, headers, timeout):                   # the provider refuses one role
        if 'Data stewards' in json['messages'][1]['content']:
            return httpx.Response(401, request=httpx.Request('POST', url))
        return reply(answer())
    monkeypatch.setattr(httpx, 'post', post)
    assert cb.main(store_args(pm, out, '--allow-live-provider')) == 1                   # a role failed
    assert json.loads(out.read_text())['status'] == 'incomplete'
    monkeypatch.setattr(httpx, 'post', lambda url, *, json, headers, timeout: reply(answer()))
    real_write = cb.write_json
    for failing, kept in ((lambda written: len(written) > 1, 'running'),                # a write inside the loop
                          (lambda written: written[-1] == 'completed', 'running')):     # the final write
        target, written = tmp_path / f'{uuid.uuid4().hex}.json', []

        def full_disk(path, value):
            written.append(value['status'])
            if failing(written):
                raise OSError(28, 'No space left on device')
            real_write(path, value)
        monkeypatch.setattr(cb, 'write_json', full_disk)
        assert cb.main(store_args(pm, target, '--allow-live-provider')) == 3
        assert 'after model calls were made' in capsys.readouterr().err
        assert json.loads(target.read_text())['status'] == kept
    final = json.loads(target.read_text())          # every role was recorded before the final write failed
    assert [r['status'] for r in final['roles']] == ['completed', 'completed'] and len(final['calls']) == 2


def test_prompts_only_records_the_requests_without_a_client(pm, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cb, 'make_client', lambda model: pytest.fail('no client in prompts-only mode'))
    path = tmp_path / 'pm.json'
    path.write_text(json.dumps(pm['run']))
    out = tmp_path / 'prompts.json'
    args = ['--run-json', str(path), '--out', str(out), '--domain', DOMAIN, '--extension-name', EXTENSION,
            '--override-case-values']
    assert cb.main([*args, '--prompts-only']) == 0
    printed = capsys.readouterr()
    assert LINE in printed.out and 'parity with the PM run is not_checked' in printed.err
    record = json.loads(out.read_text())
    assert record['status'] == 'prompts_only' and record['calls'] == [] and record['needs'] == []
    assert record['domain']['line'] == LINE and record['diagnostics']['parity_check']['status'] == 'not_checked'
    assert [r['user_payload'] for r in record['planned_requests']] == [
        r['user'] for r in cb.plan(cb.run_document(pm['run']), **OPTIONS)['requests']]
    assert [r['status'] for r in record['roles']] == ['not_called', 'not_called']
    # A run document gives no recorded calls to check parity against: model calls need --store.
    assert cb.main([*args[:3], str(tmp_path / 'live.json'), *args[4:], '--allow-live-provider']) == 2
    assert 'parity check' in capsys.readouterr().err and not (tmp_path / 'live.json').exists()
    path.write_text(json.dumps({'export_kind': 'saved_review_state', 'run': pm['run']}))
    assert cb.read_run_json(path) == pm['run']


def test_panel_roles_come_from_the_sealed_manifest(pm):
    run = deepcopy(pm['run'])
    assert [r['role_id'] for r in cb.plan(using(pm, run), **OPTIONS)['requests']] == [r.id for r in panel_roles(run)]
    run['role_manifest']['selected_roles'][0]['label'] = 'Edited after sealing'
    with pytest.raises(ValueError, match='manifest hash'):
        cb.plan(using(pm, run), **OPTIONS)
