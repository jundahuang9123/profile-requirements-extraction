"""Base labels for CB needs (scripts/cb_base_labels.py) on a synthetic PM run: scripted clients and fake HTTP only."""
import hashlib
import importlib.util
import json
import sqlite3
import sys
from copy import deepcopy
from pathlib import Path

import httpx
import pytest

from test_fa_workflow import enable
from test_routed_stakeholder_workflow import install_records, make_record, setup  # noqa: F401  (setup is a fixture)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'requirement-reuse-service'))
from requirement_reuse_service.llm.client import LLMError, OpenAICompatibleClient  # noqa: E402
from requirement_reuse_service.workflow import base_review as br  # noqa: E402
from requirement_reuse_service.workflow import engine  # noqa: E402
from requirement_reuse_service.workflow.base_needs import load_catalogue  # noqa: E402
from requirement_reuse_service.workflow.base_profile import load_profile  # noqa: E402
from requirement_reuse_service.workflow.needs import refresh_need  # noqa: E402
from requirement_reuse_service.workflow.storage import digest  # noqa: E402

spec = importlib.util.spec_from_file_location('cb_base_labels', ROOT / 'scripts' / 'cb_base_labels.py')
cbl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cbl)

MODEL = 'gpt-oss-synthetic'           # a name the client sends a reasoning effort for
PM_ENDPOINT = 'https://pm-endpoint.invalid/v1'
KEY = 'sk-synthetic-secret-0123456789'
# Statements steer the scripted reviewer (Scripted.verdict): restated, new, a domain use given up after the correction,
# a domain use kept through every attempt, and a need whose check fails.
NEEDS = [('Users can find the licence of a dataset.', ''),
         ('Users can find the weather on the day a dataset was collected.', ''),
         ('Users can find the licence of a dataset when it is reused for teaching.', 'when it is reused for teaching'),
         ('Users can find the title of a dataset in a stubborn wording.', ''),
         ('Users can find the keywords of a dataset that the checker doubts.', ''),
         ('Users can find the publisher of a dataset.', '')]
CORRECTED = 'Your previous answer was rejected'


class Scripted:
    """A reviewer and checker that answer from the payload and whether a correction was sent, never from the system
    text otherwise, so PM's and CB's texts lead it down the same path."""

    def __init__(self, effort='low', endpoint=PM_ENDPOINT, provider='openai-compatible', fail=(), interrupt=None):
        self.calls, self.effort, self.endpoint, self.provider = [], effort, endpoint, provider
        self.fail, self.interrupt = set(fail), interrupt

    def describe(self):
        return {'provider': self.provider, 'model': MODEL, 'base_url': self.endpoint, 'reasoning_effort': self.effort}

    def last_call_metadata(self):
        return {'token_usage': {'prompt_tokens': 900, 'completion_tokens': 100, 'total_tokens': 1000},
                'finish_reason': 'stop', 'generation_attempts': [{'generation': 1, 'purpose': 'initial'}]}

    @staticmethod
    def entry(payload, prop, need):
        found = [alias for alias, e in payload['base']['index'].items() if e.get('property') == prop]
        return found[:1] or need['offered_entry_ids'][:1]

    def verdict(self, payload, key, need, corrected):
        text = need['statement']
        if 'weather' in text:
            return {'item_id': key, 'verdict': 'new', 'rationale': 'No entry names the weather.'}
        if 'teaching' in text or 'stubborn' in text:
            entry = self.entry(payload, 'dct:license' if 'licence' in text else 'dct:title', need)
            if corrected and 'stubborn' not in text:
                return {'item_id': key, 'verdict': 'uncertain', 'entry_ids': entry, 'addition_kind': 'condition',
                        'addition': 'when it is reused for teaching', 'rationale': 'The licence entry plus a condition.'}
            return {'item_id': key, 'verdict': 'domain_use_of_base', 'entry_ids': entry, 'addition_kind': 'condition',
                    'addition': 'A stated condition.', 'rationale': 'The entry plus a condition.'}
        prop = {'licence': 'dct:license', 'keywords': 'dcat:keyword', 'publisher': 'dct:publisher'}
        word = next((w for w in prop if w in text), None)
        return {'item_id': key, 'verdict': 'restates_base', 'entry_ids': self.entry(payload, prop.get(word), need),
                'rationale': 'The entry states it.'}

    def generate_structured(self, *, system, user, output_model, max_tokens=None, **options):
        self.calls.append({'system': system, 'user': user, 'contract': output_model.__name__, 'max_tokens': max_tokens,
                           'options': options})
        if len(self.calls) in self.fail:
            raise LLMError(f'OpenAI-compatible request to {PM_ENDPOINT}/chat/completions failed: 503 Bearer {KEY}')
        if self.interrupt and len(self.calls) == self.interrupt:
            raise KeyboardInterrupt
        payload, corrected = json.loads(user), CORRECTED in system
        if output_model is br.BaseReview:
            return output_model.model_validate({'verdicts': [self.verdict(payload, key, need, corrected)
                                                             for key, need in payload['needs'].items()]})
        # The publisher's check is left out of every check of more than one need: the batch's check fails twice, its
        # other rows are kept, and that need is checked alone.
        rows = [v for v in payload['verdicts'] if len(payload['verdicts']) == 1
                or 'publisher' not in payload['needs'][v['item_id']]['statement']]
        return output_model.model_validate({'checks': [{
            'item_id': v['item_id'], 'verdict_supported': 'doubts' not in payload['needs'][v['item_id']]['statement'],
            'nothing_lost': True, 'rationale': 'Synthetic check.'} for v in rows]})


def pm_store(setup, needs=NEEDS, client=None):
    """A PM run under the F/A contract with the given active needs and no evidence links, pinned to dcat-ap-1.1.0 and
    reviewed by the workbench's review_base() through its call recording (TrackedClient)."""
    store, run, units, _ = setup
    run = enable(store, run)
    records = []
    for i, (statement, condition) in enumerate(needs):
        record = make_record(store, run, units[i % len(units)], i)
        record.need_statement = record.normalized_statement = statement
        record.need_condition, record.evidence_links = condition, []
        refresh_need(record)
        records.append(record)
    run = install_records(store, run, records)
    profile, fingerprint = load_profile('dcat-ap-1.1.0')
    catalogue = load_catalogue(profile['id'], fingerprint)

    def pin(r):
        r.update(base_profile_id=profile['id'], base_profile_sha256=fingerprint,
                 base_needs_catalogue={k: v for k, v in catalogue.items() if k != 'entries'})
        r['request'].update(base_profile_id=profile['id'], base_check=False, base_review='expert_v1')
    store.mutate(run['run_id'], None, 'fixture_pin', pin)
    run = store.get('run', run['run_id'])
    client = client or Scripted()
    br.review_base(store, run, engine.TrackedClient(client, store, run['run_id']))
    return store, store.get('run', run['run_id']), client


@pytest.fixture
def pm(setup, tmp_path):
    store, run, client = pm_store(setup)
    path = Path(store.path) if hasattr(store, 'path') else tmp_path / 'workflow.sqlite3'
    record = cb_record(run)
    cb_path = tmp_path / 'cb-run1.json'
    cb_path.write_text(json.dumps(record))
    return {'store': store, 'path': path, 'run': run, 'client': client, 'cb_path': cb_path,
            'cb': {'record': record, 'sha256': hashlib.sha256(cb_path.read_bytes()).hexdigest()},
            'inputs': cbl.read_store(path, run['run_id'])}


def cb_record(run, needs=None):
    """A completed CB record paired with the run, one CB need per active PM need (same ID, statement, condition)."""
    rows = [r for r in run['requirements'] if r['revision_id'] in run['active_revision_ids']]
    return {'kind': 'closed_book_run', 'policy_version': 'rq1-closed-book-v3-note', 'cb_run_id': 'cb-synthetic-1',
            'rep': 1, 'status': 'completed', 'pm_run_id': run['run_id'], 'benchmark_case_id': 'synthetic',
            'base_profile_id': run['base_profile_id'], 'base_profile_sha256': run['base_profile_sha256'],
            'needs': needs if needs is not None else [{
                'need_id': r['revision_id'], 'role_id': 'stakeholder-synthetic', 'statement': r['need_statement'],
                'condition': r['need_condition'], 'scope': r['scope'], 'obligation': 'unknown'} for r in rows]}


def labeller(pm, client, texts=None, validate=None):
    planned = cbl.plan(pm['cb'], pm['inputs'], texts=texts, validate=validate)
    return cbl.Labeller(planned, lambda step, system, user, contract, call: client.generate_structured(
        system=system, user=user, output_model=contract, max_tokens=cbl.MAX_TOKENS),
        lambda step: cbl.identity(client.describe()), sent_as=lambda step, system, contract: system)


def scrub(relation):
    return {k: v for k, v in relation.items() if k not in {'model', 'review_call_ids', 'check_call_ids'}}


def label_by_statement(record):
    return {label['statement']: label for label in record['labels']}


def test_workflow_code_is_unchanged():
    assert engine.implementation_identity().startswith('fd154ddc52eb2d87') and cbl.CHECKED_IMPLEMENTATION == 'fd154ddc52eb2d87'


def test_pm_texts_are_what_review_base_sends_and_the_parity_check_passes(pm):
    sent = pm['client'].calls
    first = [c for c in sent if CORRECTED not in c['system']]
    assert {c['system'] for c in first if c['contract'] == 'BaseReview'} == {cbl.pm_texts()['base_review']}
    assert {c['system'] for c in first if c['contract'] == 'BaseReviewChecks'} == {cbl.pm_texts()['base_review_check']}
    assert all(c['max_tokens'] == cbl.MAX_TOKENS and not c['options'] for c in sent)
    parity = cbl.plan(pm['cb'], pm['inputs'])['parity_check']
    assert parity['status'] == 'passed' and parity['calls_checked'] == parity['calls_matching'] == len(first)
    assert parity['correction_calls_excluded'] == len(sent) - len(first) > 0
    assert parity['expected_system_hash'] == {'base_review': digest(br.REVIEW_SYSTEM),
                                              'base_review_check': digest(br.CHECK_SYSTEM)}
    assert parity['runs'] == [{'run_id': pm['run']['run_id'], 'base_review_calls': len(sent)}]


def test_the_parity_check_refuses_another_text_and_leaves_out_corrections_and_failed_calls(pm, tmp_path):
    inputs = pm['inputs']
    other = deepcopy(inputs)
    first = next(c for c in other['calls'] if other['attempts'][c['call_id']][1] == 0)
    first['system_hash'] = digest('Another review text.')
    with pytest.raises(ValueError, match='not what PM sent'):
        cbl.plan(pm['cb'], other)
    failed = deepcopy(inputs)
    failed['calls'].append({**failed['calls'][0], 'call_id': 'synthetic-failed', 'status': 'failed',
                            'system_hash': digest('A correction that failed in transport.')})
    parity = cbl.plan(pm['cb'], failed)['parity_check']
    assert parity['status'] == 'passed' and parity['failed_calls_excluded'] == 1
    run = deepcopy(inputs['run'])
    run['step_models'] = {step: MODEL for step in cbl.STEPS}
    unchecked = {**inputs, 'run': run, 'calls': [], 'endpoints': []}
    planned = cbl.plan(pm['cb'], unchecked)
    assert planned['parity_check']['status'] == 'not_checked'
    with pytest.raises(ValueError, match='parity check'):
        cbl.run_labels(pm['cb'], unchecked, {s: Scripted() for s in cbl.STEPS}, tmp_path / 'l.json', planned)
    assert not (tmp_path / 'l.json').exists()
    # A run derived after the base review makes no review call of its own: the calls of its source are read.
    body = pm['store'].get_run(pm['run']['run_id'], parts=False)
    pm['store'].put('run', 'run-derived-synthetic', {**body, 'run_id': 'run-derived-synthetic',
                                                     'derived_from': {'run_id': body['run_id'], 'stage': 'deliberation'}})
    derived = cbl.read_store(pm['path'], 'run-derived-synthetic')
    assert derived['lineage'] == [{'run_id': 'run-derived-synthetic', 'base_review_calls': 0},
                                  {'run_id': body['run_id'], 'base_review_calls': len(inputs['calls'])}]
    assert cbl.parity_check(derived)['status'] == 'passed'


@pytest.mark.parametrize('budget', [None, 'split', 'two needs'])
def test_with_pm_texts_the_script_sends_what_review_base_sends_and_labels_alike(setup, tmp_path, monkeypatch, budget):
    needs = [NEEDS[0], NEEDS[5]] if budget == 'two needs' else NEEDS
    if budget == 'split':
        # Over the budget, batches of four are halved (and so are their checks) in both.
        catalogue = load_catalogue('dcat-ap-1.1.0')
        records = [cbl.record_of({'need_id': f'n{i}', 'statement': s, 'condition': c, 'scope': 'Dataset'})
                   for i, (s, c) in enumerate(NEEDS)]

        def size(batch):
            payload, aliases = br.make_payload(None, {'base_profile_id': 'dcat-ap-1.1.0', 'evidence_ids': []}, batch,
                                               catalogue, cbl.PHASE)
            return len(cbl.canonical(br.translate_ids(payload, {v: k for k, v in aliases.items()})))
        monkeypatch.setattr(br, 'MAX_PAYLOAD', (size(records[:2]) + size(records[:4])) // 2)
    store, run, workbench = pm_store(setup, needs)
    inputs = cbl.read_store(Path(store.path), run['run_id'])
    pm = {'cb': {'record': cb_record(run), 'sha256': 'x'}, 'inputs': inputs}
    client = Scripted()
    done = labeller(pm, client, texts=cbl.pm_texts(), validate=br.verdict_errors).run()
    assert [(c['contract'], c['system'], c['user']) for c in client.calls] == \
        [(c['contract'], c['system'], c['user']) for c in workbench.calls]
    if budget == 'split':
        assert {len(json.loads(c['user'])['needs']) for c in client.calls} <= {1, 2}
    # The publisher's need was checked with another need unless the order of the IDs left it alone; then its batch's
    # check was isolated. With two restated needs it always is.
    shared = any(len(p['verdicts']) > 1 and any('publisher' in n['statement'] for n in p['needs'].values())
                 for p in (json.loads(c['user']) for c in workbench.calls if c['contract'] == 'BaseReviewChecks'))
    assert shared == any((r['base_relation'].get('isolated_from_failed_batch') or {}).get('check')
                         for r in run['requirements']) and (shared or budget != 'two needs')
    saved = {r['revision_id']: r for r in run['requirements']}
    assert set(done) == set(run['active_revision_ids'])
    for rid, record in done.items():
        assert scrub(record.base_relation) == scrub(saved[rid]['base_relation'])
        assert record.processing_flags == saved[rid]['processing_flags']


def test_with_cb_texts_only_the_listed_adaptations_differ(pm):
    client = Scripted()
    labeller(pm, client).run()
    texts, pm_text = cbl.cb_texts(), cbl.pm_texts()
    workbench = pm['client'].calls
    assert [(c['contract'], c['user']) for c in client.calls] == [(c['contract'], c['user']) for c in workbench]
    step = {'BaseReview': 'base_review', 'BaseReviewChecks': 'base_review_check'}
    for ours, theirs in zip(client.calls, workbench):
        name = step[ours['contract']]
        assert ours['system'].startswith(texts[name]) and theirs['system'].startswith(pm_text[name])
        expected = theirs['system'][len(pm_text[name]):]
        for old, new in cbl.FEEDBACK_REPLACEMENTS:
            expected = expected.replace(old, new)
        assert ours['system'][len(texts[name]):] == expected
    assert any(new in c['system'] for c in client.calls for _, new in cbl.FEEDBACK_REPLACEMENTS)
    # Each CB text is PM's text with each listed change made once, and nothing else.
    for name, pairs in (('base_review', cbl.REVIEW_REPLACEMENTS), ('base_review_check', cbl.CHECK_REPLACEMENTS)):
        text = pm_text[name]
        for old, new in pairs:
            assert text.count(old) == 1
            text = text.replace(old, new)
        assert text == texts[name]


def test_the_cb_texts_drop_the_passage_wording_and_state_the_rule():
    review, check = cbl.cb_texts()['base_review'], cbl.cb_texts()['base_review_check']
    for gone in ('its cited passages', 'Cite the passage stating the addition.', 'the verdict is domain_use_of_base.',
                 'and the source passages.'):
        assert gone not in review and gone not in check
    assert review.count('No source passages are given.') == check.count('No source passages are given.') == 1
    assert 'so it cannot be given here' in review and 'the verdict is uncertain.' in review
    assert 'cite the entry and give the addition and its kind' in review
    assert 'or a cited entry names the information and the need indeed adds the stated addition' in check
    # Kept for parity: no domain-use verdict reaches the check.
    assert 'for domain_use_of_base the addition is real and stated in a cited passage' in check


@pytest.mark.parametrize('change', ['missing', 'twice'])
def test_a_changed_workbench_text_or_problem_stops_the_script(pm, monkeypatch, change):
    old = cbl.REVIEW_REPLACEMENTS[1][0]
    text = br.REVIEW_SYSTEM.replace(old, '') if change == 'missing' else br.REVIEW_SYSTEM + ' ' + old
    monkeypatch.setattr(br, 'REVIEW_SYSTEM', text)
    with pytest.raises(ValueError, match='no longer matches the workbench text'):
        cbl.cb_texts()
    monkeypatch.undo()
    original = br.verdict_errors
    monkeypatch.setattr(br, 'verdict_errors', lambda *a: [e.replace('source-cited', 'cited') for e in original(*a)])
    with pytest.raises(ValueError, match='no longer reports'):
        cbl.plan(pm['cb'], pm['inputs'])
    assert cbl.feedback_check.__doc__ and cbl.cb_feedback(['N1: other problem.']) == ['N1: other problem.']


def test_a_domain_use_is_refused_counted_and_its_case_labelled_uncertain_or_not_reviewed(pm, tmp_path):
    client = Scripted()
    record = cbl.run_labels(pm['cb'], pm['inputs'], {s: client for s in cbl.STEPS}, tmp_path / 'l.json',
                            cbl.plan(pm['cb'], pm['inputs']))
    labels = label_by_statement(record)
    teaching, stubborn = labels[NEEDS[2][0]], labels[NEEDS[3][0]]
    # Refused in the batch's first answer; uncertain after the correction.
    assert teaching['label_class'] == 'addition_without_passage' and teaching['domain_use_refused'] == 1
    assert teaching['base_relation']['verdict'] == 'uncertain' and teaching['base_relation']['status'] == 'checked'
    assert teaching['base_label'] == 'working' and teaching['base_relation']['entry_ids']
    # The batch's two attempts, then the need alone twice: refused every time, not reviewed.
    assert stubborn['label_class'] == 'not_reviewed' and stubborn['domain_use_refused'] == 4
    assert stubborn['base_relation']['reason'] == 'invalid_output' and 'base_review_pending' in stubborn['processing_flags']
    assert any(e.endswith(cbl.FEEDBACK_REPLACEMENTS[2][1]) for e in stubborn['base_relation']['errors'])
    corrections = [c['system'] for c in client.calls if CORRECTED in c['system']]
    assert corrections and not any(old in s for s in corrections for old, _ in cbl.FEEDBACK_REPLACEMENTS)
    assert record['counts']['domain_use_refused'] == 5 and record['counts']['needs_with_domain_use_refused'] == 2
    assert 'domain_use_of_base' not in record['counts']['by_class']


def test_labels_have_the_scorers_shape_and_follow_the_checked_verdict(pm, tmp_path):
    record = cbl.run_labels(pm['cb'], pm['inputs'], {s: Scripted() for s in cbl.STEPS}, tmp_path / 'l.json',
                            cbl.plan(pm['cb'], pm['inputs']))
    labels = label_by_statement(record)
    assert labels[NEEDS[0][0]]['covered_by_base'] is True and labels[NEEDS[0][0]]['label_class'] == 'restates_base'
    assert labels[NEEDS[0][0]]['base_relation']['entries'][0]['property'] == 'dct:license'
    assert labels[NEEDS[1][0]]['base_label'] == 'working' and labels[NEEDS[1][0]]['label_class'] == 'new'
    doubted = labels[NEEDS[4][0]]
    assert doubted['label_class'] == 'check_failed' and doubted['covered_by_base'] is False
    assert 'base_relation_review' in doubted['processing_flags']
    assert record['counts'] == {**record['counts'], 'needs': 6, 'covered': 2, 'working': 4, 'not_labelled': 0}
    info = record['revision_info']
    assert set(info) == {'run_id', 'revisions', 'set_aside_without_need_statement'}
    assert info['revisions'] == {l['need_id']: {'lifecycle': 'active', 'covered_by_base': l['covered_by_base'],
                                                'parents': []} for l in record['labels']}
    relation = labels[NEEDS[0][0]]['base_relation']
    pm_relation = next(r for r in pm['run']['requirements'] if r['need_statement'] == NEEDS[0][0])['base_relation']
    assert set(relation) == set(pm_relation) and relation['model'] == {'provider': 'openai-compatible', 'model': MODEL,
                                                                        'reasoning_effort': 'low'}
    assert [l['need_id'] for l in record['labels']] == [n['need_id'] for n in pm['cb']['record']['needs']]


def test_calls_are_recorded_like_closed_book_and_hold_no_endpoint_or_key(pm, tmp_path):
    out = tmp_path / 'l.json'
    failing = Scripted(fail={3})
    record = cbl.run_labels(pm['cb'], pm['inputs'], {s: failing for s in cbl.STEPS}, out,
                            cbl.plan(pm['cb'], pm['inputs']))
    assert record['status'] == 'incomplete' and record['counts']['not_labelled'] > 0
    failed = record['calls'][-1]
    assert failed['status'] == 'failed' and failed['error']['type'] == 'LLMError'
    assert 'Bearer <key>' in failed['error']['message'] and '<url>' in failed['error']['message']
    text = out.read_text()
    assert 'pm-endpoint' not in text and KEY not in text and 'base_url' not in text
    first = record['calls'][0]
    assert {'call_id', 'sequence', 'step', 'batch_key', 'attempt', 'purpose', 'contract', 'max_output_tokens',
            'system_prompt', 'user_payload', 'prompt_sha256', 'payload_sha256', 'system_hash', 'context_hash',
            'started_at', 'latency_seconds', 'status', 'output', 'token_usage', 'finish_reason', 'generations'} <= set(first)
    assert first['prompt_sha256'] == hashlib.sha256(first['system_prompt'].encode()).hexdigest()
    assert first['system_hash'] == digest(cbl.cb_texts()['base_review'])
    assert first['token_usage']['total_tokens'] == 1000 and record['diagnostics']['failed_calls'] == [failed['call_id']]


def test_resume_keeps_saved_answers_continues_the_sequence_and_refuses_other_records(pm, tmp_path):
    out, planned = tmp_path / 'l.json', cbl.plan(pm['cb'], pm['inputs'])
    failing = Scripted(fail={4})
    first = cbl.run_labels(pm['cb'], pm['inputs'], {s: failing for s in cbl.STEPS}, out, planned)
    assert first['status'] == 'incomplete' and len(first['calls']) == 4
    client = Scripted()
    done = cbl.run_labels(pm['cb'], pm['inputs'], {s: client for s in cbl.STEPS}, out, planned, resume=True)
    assert done['status'] == 'completed' and done['created_at'] == first['created_at']
    assert done['calls'][:4] == first['calls'] and [c['sequence'] for c in done['calls']] == \
        list(range(1, len(done['calls']) + 1))
    assert len(client.calls) == len(done['calls']) - 4      # the three answered calls are not repeated; the failed one is
    fresh = cbl.run_labels(pm['cb'], pm['inputs'], {s: Scripted() for s in cbl.STEPS}, tmp_path / 'fresh.json', planned)
    assert [l['base_relation'] | {'review_call_ids': None, 'check_call_ids': None} for l in done['labels']] == \
        [l['base_relation'] | {'review_call_ids': None, 'check_call_ids': None} for l in fresh['labels']]
    again = Scripted()
    assert cbl.run_labels(pm['cb'], pm['inputs'], {s: again for s in cbl.STEPS}, out, planned, resume=True) == \
        json.loads(out.read_text()) and not again.calls
    for edit, match in (({'kind': 'closed_book_run'}, 'another record'), ({'status': 'prompts_only'}, 'prompts-only'),
                        ({'label_run_id': 'cbbl-other'}, 'another CB record'),
                        ({'runner_sha256': 'e' * 64}, 'another version'),
                        ({'workbench_implementation_hash': 'e' * 64}, 'another workbench'),
                        ({'models': {s: {'provider': 'openai-compatible', 'model': MODEL, 'reasoning_effort': 'high'}
                                     for s in cbl.STEPS}}, 'another model')):
        edited = tmp_path / 'edited.json'
        edited.write_text(json.dumps({**first, **edit}))
        with pytest.raises(ValueError, match=match):
            cbl.run_labels(pm['cb'], pm['inputs'], {s: Scripted() for s in cbl.STEPS}, edited, planned, resume=True)


def test_an_interrupt_writes_an_interrupted_record_and_resume_completes_it(pm, tmp_path):
    out, planned = tmp_path / 'l.json', cbl.plan(pm['cb'], pm['inputs'])
    with pytest.raises(KeyboardInterrupt):
        interrupting = Scripted(interrupt=3)
        cbl.run_labels(pm['cb'], pm['inputs'], {s: interrupting for s in cbl.STEPS}, out, planned)
    saved = json.loads(out.read_text())
    assert saved['status'] == 'interrupted' and [c['status'] for c in saved['calls']] == ['accepted', 'accepted',
                                                                                          'interrupted']
    record = cbl.run_labels(pm['cb'], pm['inputs'], {s: Scripted() for s in cbl.STEPS}, out, planned, resume=True)
    assert record['status'] == 'completed' and record['calls'][:3] == saved['calls']


def test_model_comes_from_the_recorded_calls_and_must_match_the_client(pm, tmp_path):
    planned = cbl.plan(pm['cb'], pm['inputs'])
    assert planned['models'] == {s: {'provider': 'openai-compatible', 'model': MODEL, 'reasoning_effort': 'low',
                                     'source': 'model_calls'} for s in cbl.STEPS}
    assert planned['pm_endpoints'] == {s: PM_ENDPOINT for s in cbl.STEPS}
    with pytest.raises(ValueError, match='not the PM model'):
        cbl.run_labels(pm['cb'], pm['inputs'], {s: Scripted(effort='high') for s in cbl.STEPS}, tmp_path / 'a.json',
                       planned)
    other = {s: Scripted(endpoint='https://other.invalid/v1') for s in cbl.STEPS}
    with pytest.raises(ValueError, match='allow-other-endpoint'):
        cbl.run_labels(pm['cb'], pm['inputs'], other, tmp_path / 'b.json', planned)
    record = cbl.run_labels(pm['cb'], pm['inputs'], other, tmp_path / 'c.json', planned, allow_other_endpoint=True)
    assert record['diagnostics']['endpoint_matches_pm'] is False and record['diagnostics']['other_endpoint_allowed']
    assert 'other.invalid' not in (tmp_path / 'c.json').read_text()
    fallback = {**pm['inputs'], 'calls': [], 'endpoints': []}
    run = deepcopy(fallback['run'])
    run['step_models'] = {'base_review': 'model-a', 'base_review_check': 'model-b'}
    run['step_model_options'] = {'base_review': {'reasoning_effort': 'medium'}}
    models, _ = cbl.pm_models({**fallback, 'run': run})
    assert models['base_review'] == {'provider': None, 'model': 'model-a', 'reasoning_effort': 'medium',
                                     'source': 'step_models'}
    assert models['base_review_check']['model'] == 'model-b' and models['base_review_check']['reasoning_effort'] is None
    mixed = deepcopy(pm['inputs'])
    mixed['calls'][0]['reasoning_effort'] = 'high'
    with pytest.raises(ValueError, match='different models'):
        cbl.pm_models(mixed)


def test_the_cb_record_and_its_base_are_checked(pm, tmp_path):
    for edit, match in (({'kind': 'other'}, 'no CB record'), ({'status': 'incomplete'}, 'label a completed'),
                        ({'needs': [{'need_id': 'a', 'statement': ' ', 'condition': '', 'scope': ''}]}, 'lacks'),
                        ({'needs': [{'need_id': 'a', 'statement': 'x', 'condition': '', 'scope': ''}] * 2}, 'distinct')):
        path = tmp_path / 'bad.json'
        path.write_text(json.dumps({**pm['cb']['record'], **edit}))
        with pytest.raises(ValueError, match=match):
            cbl.read_cb_record(path)
    for edit, match in (({'pm_run_id': 'run-other'}, 'paired with'), ({'base_profile_sha256': 'f' * 64}, 'another base')):
        with pytest.raises(ValueError, match=match):
            cbl.plan({**pm['cb'], 'record': {**pm['cb']['record'], **edit}}, pm['inputs'])
    run = deepcopy(pm['inputs']['run'])
    run['base_needs_catalogue']['catalogue_hash'] = 'changed'
    with pytest.raises(ValueError, match='catalogue changed'):
        cbl.plan(pm['cb'], {**pm['inputs'], 'run': run})
    run = deepcopy(pm['inputs']['run'])
    run['request']['base_review'] = 'none'
    with pytest.raises(ValueError, match='expert_v1'):
        cbl.plan(pm['cb'], {**pm['inputs'], 'run': run})


def test_the_store_is_read_only_and_immutable_on_request(pm, monkeypatch):
    before = hashlib.sha256(pm['path'].read_bytes()).hexdigest()
    uris, connect = [], sqlite3.connect
    monkeypatch.setattr(sqlite3, 'connect', lambda database, **kw: uris.append(database) or connect(database, **kw))
    cbl.read_store(pm['path'], pm['run']['run_id'])
    cbl.read_store(pm['path'], pm['run']['run_id'], immutable=True)
    assert uris[0].endswith('?mode=ro') and uris[1].endswith('?mode=ro&immutable=1')
    with cbl.read_only(pm['path']) as db:
        with pytest.raises(sqlite3.OperationalError):
            db.execute("DELETE FROM objects WHERE kind='run'")
    assert hashlib.sha256(pm['path'].read_bytes()).hexdigest() == before
    with pytest.raises(ValueError, match='not in the store'):
        cbl.read_store(pm['path'], 'run-missing')


def test_prompts_only_records_the_first_requests_without_a_client(pm, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cbl, 'make_client', lambda model: pytest.fail('no client for a preview'))
    out = tmp_path / 'preview.json'
    args = ['--cb-record', str(pm['cb_path']), '--store', str(pm['path']), '--out', str(out)]
    assert cbl.main([*args, '--prompts-only']) == 0
    assert 'no model called' in capsys.readouterr().out
    preview = json.loads(out.read_text())
    assert preview['status'] == 'prompts_only' and not preview['calls'] and preview['counts']['not_labelled'] == 6
    planned = preview['planned_requests']
    assert [len(r['need_ids']) for r in planned] == [4, 2]
    review = cbl.cb_texts()['base_review']
    assert all(r['system_prompt'] == cbl.with_schema(review, br.BaseReview) for r in planned)
    assert preview['planned_check']['system_prompt'].startswith(cbl.cb_texts()['base_review_check'])
    # The first review request of each batch is what a run sends first.
    client = Scripted()
    labeller(pm, client).run()
    firsts = [c['user'] for c in client.calls if c['contract'] == 'BaseReview' and CORRECTED not in c['system']]
    assert planned[0]['user_payload'] == client.calls[0]['user'] and all(r['user_payload'] in firsts for r in planned)
    assert cbl.main([*args, '--prompts-only']) == 2         # never overwritten
    assert 'exists' in capsys.readouterr().err


def test_the_system_text_as_sent_is_what_the_real_client_posts(pm, tmp_path, monkeypatch):
    monkeypatch.setenv('RRS_LLM_PROVIDER', 'openai-compatible')
    monkeypatch.setenv('RRS_LLM_BASE_URL', PM_ENDPOINT)
    monkeypatch.setenv('RRS_LLM_API_KEY', KEY)
    script, bodies = Scripted(), []

    def post(url, *, json, headers, timeout):
        bodies.append(json)
        system = json['messages'][0]['content'].split('\n\nRespond with a single JSON object only')[0]
        contract = br.BaseReview if 'Return BaseReview JSON' in system else br.BaseReviewChecks
        answer = script.generate_structured(system=system, user=json['messages'][1]['content'], output_model=contract)
        return httpx.Response(200, json={'choices': [{'message': {'content': answer.model_dump_json()},
                                                      'finish_reason': 'stop'}],
                                         'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}},
                              request=httpx.Request('POST', url))
    monkeypatch.setattr(httpx, 'post', post)
    out = tmp_path / 'l.json'
    args = ['--cb-record', str(pm['cb_path']), '--store', str(pm['path']), '--out', str(out), '--allow-live-provider']
    assert cbl.main(args) == 0
    record = json.loads(out.read_text())
    assert len(bodies) == len(record['calls']) and record['status'] == 'completed'
    for body, call in zip(bodies, record['calls']):
        assert body['messages'][0]['content'] == call['system_prompt'] and body['messages'][1]['content'] == call['user_payload']
        assert body['max_tokens'] == cbl.MAX_TOKENS and body['model'] == MODEL and body['reasoning_effort'] == 'low'
    assert record['calls'][0]['system_prompt'] == cbl.with_schema(cbl.cb_texts()['base_review'], br.BaseReview)
    assert isinstance(cbl.clients_for(cbl.plan(pm['cb'], pm['inputs'])['models'])['base_review'], OpenAICompatibleClient)
    text = out.read_text()
    assert 'pm-endpoint' not in text and KEY not in text
    assert record['calls'][0]['token_usage']['total_tokens'] == 15


def test_cli_exit_codes(pm, tmp_path, monkeypatch, capsys):
    base = ['--cb-record', str(pm['cb_path']), '--store', str(pm['path'])]
    assert cbl.main([*base, '--out', str(tmp_path / 'a.json')]) == 2              # no --allow-live-provider
    assert 'allow-live-provider' in capsys.readouterr().err
    assert cbl.main([*base, '--run-id', 'run-other', '--out', str(tmp_path / 'b.json'), '--prompts-only']) == 2
    failing = Scripted(fail={2})
    monkeypatch.setattr(cbl, 'clients_for', lambda models: {s: failing for s in cbl.STEPS})
    assert cbl.main([*base, '--out', str(tmp_path / 'c.json'), '--allow-live-provider']) == 1
    monkeypatch.setattr(cbl, 'clients_for', lambda models: {s: Scripted() for s in cbl.STEPS})
    assert cbl.main([*base, '--out', str(tmp_path / 'c.json'), '--allow-live-provider', '--resume']) == 0
    written, original = [], cbl.write_json

    def full_disk(path, value):
        written.append(value['status'])
        if len(written) > 3:
            raise OSError('No space left on device')
        original(path, value)
    monkeypatch.setattr(cbl, 'write_json', full_disk)
    assert cbl.main([*base, '--out', str(tmp_path / 'd.json'), '--allow-live-provider']) == 3
    assert 'after model calls were made' in capsys.readouterr().err
    assert json.loads((tmp_path / 'd.json').read_text())['status'] == 'running'


def test_the_doc_lists_every_adaptation_and_the_rule():
    doc = ' '.join((ROOT / 'docs' / 'CB_BASE_LABELS.md').read_text().split())
    for old, new in (*cbl.REVIEW_REPLACEMENTS, *cbl.CHECK_REPLACEMENTS, *cbl.FEEDBACK_REPLACEMENTS):
        assert ' '.join(new.split()).strip(': ') in doc, new
    assert 'addition_without_passage' in doc and 'domain_use_refused' in doc
