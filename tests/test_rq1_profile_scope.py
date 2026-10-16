"""D5 profile scope: a judgement over source-derived needs that can only keep or set aside."""
import json
from test_resume_discussions import setup
from test_rq1_need_grouping import need_inputs, NeedsClient
from requirement_reuse_service.workflow import engine, needs
from requirement_reuse_service.workflow.models import RestoreRequest

STATEMENTS = {
    'need-0': 'Users can find datasets by the area they cover.',
    'need-1': 'Users can combine datasets from several providers in one analysis.',
    'need-2': 'Users can rely on every record in the data having a timestamp.',
    'need-3': 'Users can see the positional accuracy of every dataset in metres.',
    'need-4': 'Users can compute travel times from each road segment.',
}
VERDICTS = {
    'need-0': {'serves': 'find', 'catalogue_level': True, 'commonly_agreed': True},
    'need-1': {'serves': 'neither', 'catalogue_level': True, 'commonly_agreed': True},
    'need-2': {'serves': 'access', 'catalogue_level': False, 'commonly_agreed': True},
    'need-3': {'serves': 'both', 'catalogue_level': True, 'commonly_agreed': False},
    'need-4': {'serves': 'neither', 'catalogue_level': False, 'commonly_agreed': False},
}


class ScopeJudge(NeedsClient):
    def __init__(self, verdicts=VERDICTS, default=VERDICTS['need-0'], extra=(), omit=()):
        super().__init__(); self.verdicts, self.default, self.extra, self.omit = verdicts, default, extra, omit
    def generate_structured(self, **kwargs):
        if kwargs['output_model'].__name__ != 'ProfileScope':
            return super().generate_structured(**kwargs)
        data = json.loads(kwargs['user']); self.calls.append(('ProfileScope', data))
        rows = [{'need_id': i, **self.verdicts.get(i, self.default), 'rationale': 'Scripted scope judgement.'}
                for i in [*data['needs'], *self.extra] if i not in self.omit]
        return kwargs['output_model'].model_validate({'decisions': rows})


def variants(setup, statements=STATEMENTS):
    store, run, candidates = need_inputs(setup)
    output, _ = needs.write_needs(store, run, [candidates], NeedsClient(), None)
    made = []
    for identifier, statement in statements.items():
        need = output[0].model_copy(deep=True); need.requirement_id = identifier
        need.need_statement = need.normalized_statement = statement
        needs.refresh_need(need); need.verification = engine.verify(store, need, run['evidence_ids'])
        assert need.verification['status'] == 'pass'
        made.append(need)
    return store, run, candidates, made


def judged(client):
    return [i for name, data in client.calls if name == 'ProfileScope' for i in data['needs']]


def test_failed_tests_set_aside_with_first_failure_and_no_need_added(setup):
    store, run, _, made = variants(setup); client = ScopeJudge()
    retained = needs.judge_profile_scope(store, run, made, client)
    assert [n.requirement_id for n in retained] == ['need-0']
    asides = {a['need_id']: a for a in store.get('run', run['run_id'])['set_aside_observations']}
    assert {i: a['reason'] for i, a in asides.items()} == {'need-1': 'not_find_or_access',
        'need-2': 'not_catalogue_level', 'need-3': 'not_commonly_agreed', 'need-4': 'not_find_or_access'}
    assert asides['need-4']['details']['profile_scope']['failed_tests'] == [
        'not_find_or_access', 'not_catalogue_level', 'not_commonly_agreed']
    assert all(asides[i]['rationale'] == 'Scripted scope judgement.' for i in asides)
    # The judge sees only the stated need and judges it; it is never asked to write one.
    offered = [data['needs'] for name, data in client.calls if name == 'ProfileScope']
    assert all(set(row) == {'statement', 'condition', 'scope'} for batch in offered for row in batch.values())
    kept = retained[0]
    assert kept.profile_scope['status'] == 'checked' and kept.profile_scope['failed_tests'] == []
    assert kept.need_statement == STATEMENTS['need-0']
    assert engine.verify(store, kept, run['evidence_ids'])['status'] == 'pass'  # integrity binds the judgement
    step = store.get('run', run['run_id'])['need_steps']['profile_scope']
    assert step['retained_count'] == 1 and step['set_aside_count'] == 4
    assert step['set_aside_by_reason'] == {'not_find_or_access': 2, 'not_catalogue_level': 1, 'not_commonly_agreed': 1}
    before = len(client.calls)
    needs.judge_profile_scope(store, run, made, client)
    assert len(client.calls) == before  # resume reuses the saved judgement


def test_contract_can_only_judge_offered_needs():
    assert set(needs.ProfileScope.model_fields) == {'decisions'}
    assert set(needs.ScopeDecision.model_fields) == {'need_id', 'serves', 'catalogue_level', 'commonly_agreed', 'rationale'}
    assert 'never add, merge, broaden or rewrite a need' in needs.SCOPE_SYSTEM


def test_invented_row_is_ignored_and_unjudged_need_stays_flagged(setup):
    store, run, _, made = variants(setup, {'need-0': STATEMENTS['need-0'], 'need-1': STATEMENTS['need-1']})
    client = ScopeJudge(extra=('invented-need',), omit=('need-1',))
    retained = needs.judge_profile_scope(store, run, made, client)
    assert [n.requirement_id for n in retained] == ['need-0', 'need-1']
    unchecked = retained[1]
    assert 'profile_scope_not_checked' in unchecked.processing_flags
    assert unchecked.profile_scope['status'] == 'not_checked'
    assert engine.verify(store, unchecked, run['evidence_ids'])['status'] == 'pass'
    saved = store.get('run', run['run_id'])
    assert saved['set_aside_observations'] == []
    assert saved['need_steps']['profile_scope']['not_checked_ids'] == ['need-1']
    chunk = next(c for c in saved['need_chunks'].values() if c['step'] == 'profile_scope')
    assert chunk['attempts'][0]['unexpected_ids'] == ['invented-need']
    assert judged(client) == ['need-0', 'need-1', 'need-1']  # one correction, for the missing row only


def test_source_failed_need_is_not_judged_and_stays_blocked(setup):
    store, run, _, made = variants(setup, {'need-0': STATEMENTS['need-0'], 'need-4': STATEMENTS['need-4']})
    made[1].verification = {'status': 'fail', 'links': [], 'message': 'Offline source failure.'}
    client = ScopeJudge()
    retained = needs.judge_profile_scope(store, run, made, client)
    assert [n.requirement_id for n in retained] == ['need-0', 'need-4']
    assert judged(client) == ['need-0'] and made[1].profile_scope is None
    assert store.get('run', run['run_id'])['need_steps']['profile_scope']['blocked_count'] == 1


def test_scope_set_aside_is_visible_in_export_and_restorable(setup):
    store, run, records = need_inputs(setup)
    run['request']['base_profile_id'] = None; run['base_profile_id'] = None; run['request']['scoping'] = 'off'
    client = ScopeJudge(verdicts={}, default=VERDICTS['need-2'])
    active, _, _ = needs.process_needs(store, run, records, client, None)
    assert active == []
    store.mutate(run['run_id'], None, 'offline-terminal', lambda r: r.update(status='awaiting_human'))
    saved = store.get('run', run['run_id'])
    item = next(a for a in saved['set_aside_observations'] if a['reason'] == 'not_catalogue_level')
    export = needs.needs_export(store, run['run_id'])
    row = next(a for a in export['set_aside'] if a['audit']['reason'] == 'not_catalogue_level')
    assert row['record']['profile_scope']['failed_tests'] == ['not_catalogue_level']
    assert export['families'] == [] and saved['need_steps']['families']['family_count'] == 0
    restored = needs.restore_need(store, run['run_id'], RestoreRequest(expected_version=saved['version'],
        idempotency_key='restore-scope', observation_id=item['observation_id'], need_id=item['need_id'],
        reason=item['reason'], rationale='Reviewer judges this catalogue level.'), 'offline-reviewer')['run']
    need = next(r for r in restored['requirements'] if r['revision_id'] in restored['active_revision_ids'])
    assert need['lifecycle_state'] == 'awaiting_human' and need['requirement_id'] == item['need_id']
    assert restored['decisions'][-1]['reason'] == 'not_catalogue_level'


def test_runs_saved_before_d5_need_a_derived_trial():
    import pytest
    earlier = {k: v for k, v in needs.POLICIES.items() if k not in {'profile_scope', 'families'}}
    with pytest.raises(ValueError, match='derive a separate trial'):
        needs.run_needs_policies({'needs_policies': earlier})
    assert needs.run_needs_policies({'needs_policies': dict(needs.POLICIES)}) == needs.POLICIES
