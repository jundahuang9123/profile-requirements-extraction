"""Scope contract v1, option A (rq1-profile-scope-v8, Junda, 23 Oct): a failed catalogue-record test is confirmed by
a second judgement of the need alone before the need is set aside or blocks a change; when the two disagree,
the need stays, flagged profile_scope_disputed.

Live shapes: in JRC run-ea22d18c the record test set aside 21 of 72 needs, judged in batches of up to 25. Judged
alone, "Users can know the permissible uses of data, including reproduction, ..." named the dataset record 3 of 3
times; in the run it had shared a batch of 12 with 7 policy statements and was judged as naming no record. A policy
statement ("acquisition of data from third parties shall be governed by the Open Data principles") failed alone
too. Scripted clients test the plumbing only; the model's judgement shows only live.
"""
import json
import pytest
from test_resume_discussions import setup as needs_setup  # noqa: F401  (pytest fixture)
from test_routed_stakeholder_workflow import setup  # noqa: F401  (pytest fixture)
from test_rq1_profile_scope import variants
from test_scope_contract_v1_normalisation import BothTests, fa_run
from test_scope_contract_v1_discussion import Scoped, DIMENSIONS, NONE_NEITHER, revise_into, change, record_rows
from test_fa_dialogue_v3 import opted_in
from test_fa_quirks import sound
from requirement_reuse_service.workflow import needs, fa_discussion as fd

USES = ('Users can know the permissible uses of data, including reproduction, communication to the public, '
        'adaptation, modification, combination, and distribution')
THIRD_PARTIES = 'Users can know that acquisition of data from third parties shall be governed by the Open Data principles.'
NAMES_DATASET = {'record_resource': 'dataset', 'record_statement': 'dataset: the uses its licence permits',
                 'catalogue_level': True, 'serves': 'access', 'example': 'Select a dataset whose licence permits adaptation.'}


def answer(statement, alone):
    """USES fails in a batch and passes alone; THIRD_PARTIES fails either way; anything else passes."""
    if statement == THIRD_PARTIES or (statement == USES and not alone):
        return NONE_NEITHER
    return NAMES_DATASET


class InContext(BothTests):
    """Normalisation: both tests; the record test answers by the statement and by whether it was asked alone."""
    def __init__(self, statements, omit_alone=()):
        super().__init__(statements); self.omit_alone = set(omit_alone)
    def generate_structured(self, **kwargs):
        if kwargs['output_model'].__name__ != 'ProfileScope':
            return super().generate_structured(**kwargs)
        data = json.loads(kwargs['user']); self.calls.append(('ProfileScope', data))
        alone = len(data['needs']) == 1
        return kwargs['output_model'].model_validate({'decisions': [
            {'need_id': i, **answer(row['statement'], alone), 'rationale': 'Alone.' if alone else 'In a batch.'}
            for i, row in data['needs'].items() if not (alone and row['statement'] in self.omit_alone)]})


def record_calls(client):
    return [sorted(data['needs']) for name, data in client.calls if name == 'ProfileScope']


@pytest.mark.parametrize('find_access', [True, False])
def test_a_record_test_failure_that_passes_alone_keeps_the_need_flagged(needs_setup, find_access):
    statements = {'need-uses': USES, 'need-third': THIRD_PARTIES, 'need-dimensions': DIMENSIONS}
    store, run, _, made = variants(needs_setup, statements)
    if find_access: run = fa_run(store, run)
    client = InContext(statements)
    retained = needs.judge_profile_scope(store, run, made, client)
    assert [n.requirement_id for n in retained] == ['need-uses', 'need-dimensions']
    kept = {n.requirement_id: n for n in retained}
    uses = kept['need-uses']
    # Kept with the second judgement, flagged, and the first judgement kept beside it.
    assert 'profile_scope_disputed' in uses.processing_flags
    assert uses.profile_scope['record_resource'] == 'dataset' and uses.profile_scope['failed_tests'] == []
    assert uses.profile_scope['rationale'] == 'Alone.'
    confirmation = uses.profile_scope['confirmation']
    assert confirmation['outcome'] == 'disputed' and confirmation['verdict']['record_resource'] == 'none'
    assert confirmation['verdict']['failed_tests'] == ['not_catalogue_level', 'not_find_or_access']
    assert 'profile_scope_disputed' not in kept['need-dimensions'].processing_flags
    # Failed both times: set aside, with both judgements.
    aside, = store.get('run', run['run_id'])['set_aside_observations']
    assert aside['need_id'] == 'need-third' and aside['reason'] == 'not_catalogue_level' and aside['rationale'] == 'In a batch.'
    assert aside['details']['profile_scope']['confirmation']['outcome'] == 'confirmed'
    assert aside['details']['profile_scope']['confirmation']['verdict']['rationale'] == 'Alone.'
    step = store.get('run', run['run_id'])['need_steps']['profile_scope']
    assert step['policy_version'] == 'rq1-profile-scope-v9'
    assert step['confirmation_counts'] == {'confirmed': 1, 'disputed': 1}
    assert step['confirmation_ids'] == {'confirmed': ['need-third'], 'disputed': ['need-uses']}
    decisions = step['record_decisions'] if find_access else step['decisions']
    assert {d['need_id']: d.get('confirmation', {}).get('outcome') for d in decisions} == {
        'need-uses': 'disputed', 'need-third': 'confirmed', 'need-dimensions': None}
    # One batch, then each failure alone; resume reuses all three.
    assert record_calls(client) == [sorted(statements), ['need-uses'], ['need-third']]
    before = len(client.calls)
    needs.judge_profile_scope(store, run, made, client)
    assert len(client.calls) == before


def test_a_need_first_judged_alone_is_judged_again(needs_setup):
    # One need is a batch of one: the second judgement has its own cache step, or it would be the first one again.
    statements = {'need-uses': USES}
    store, run, _, made = variants(needs_setup, statements)
    # A real run names its needs policies from creation, so both judgements carry the same policy in their keys.
    store.mutate(run['run_id'], None, 'fixture_policies', lambda r: r.update(needs_policies=dict(needs.POLICIES)))
    run = fa_run(store, run)
    class FirstFails(InContext):
        def generate_structured(self, **kwargs):
            if kwargs['output_model'].__name__ == 'ProfileScope':
                data = json.loads(kwargs['user']); self.calls.append(('ProfileScope', data))
                first = sum(name == 'ProfileScope' for name, _ in self.calls) == 1
                return kwargs['output_model'].model_validate({'decisions': [
                    {'need_id': i, **(NONE_NEITHER if first else NAMES_DATASET), 'rationale': 'Scripted.'} for i in data['needs']]})
            return super().generate_structured(**kwargs)
    client = FirstFails(statements)
    retained = needs.judge_profile_scope(store, run, made, client)
    assert [n.requirement_id for n in retained] == ['need-uses']
    assert retained[0].profile_scope['confirmation']['outcome'] == 'disputed'
    assert record_calls(client) == [['need-uses'], ['need-uses']]
    assert store.get('run', run['run_id'])['set_aside_observations'] == []


def test_a_missing_second_judgement_keeps_the_need_flagged(needs_setup):
    statements = {'need-uses': USES, 'need-dimensions': DIMENSIONS}
    store, run, _, made = variants(needs_setup, statements)
    run = fa_run(store, run)
    client = InContext(statements, omit_alone={USES})
    retained = needs.judge_profile_scope(store, run, made, client)
    assert [n.requirement_id for n in retained] == ['need-uses', 'need-dimensions']
    uses = retained[0]
    assert 'profile_scope_disputed' in uses.processing_flags
    confirmation = uses.profile_scope['confirmation']
    assert confirmation['outcome'] == 'not_checked' and confirmation['first_failed_tests'] == ['not_catalogue_level', 'not_find_or_access']
    assert uses.profile_scope['failed_tests'] == [] and uses.profile_scope['record_resource'] == 'none'
    step = store.get('run', run['run_id'])['need_steps']['profile_scope']
    assert step['confirmation_counts'] == {'not_checked': 1} and step['set_aside_count'] == 0
    # Asked alone twice (the correction), then kept.
    assert record_calls(client) == [sorted(statements), ['need-uses'], ['need-uses']]


# At apply (rq1-fa-dialogue-v13): a need a change writes is judged in a batch of the change's needs.
class FailsFirstTime(Scoped):
    """The record test fails USES the first time it is asked and passes it after that."""
    def generate_structured(self, *, user, output_model, system='', step=None, **kw):
        if output_model.__name__ == 'ProfileScope':
            data = json.loads(user); statements = [r['statement'] for r in data['needs'].values()]
            self.scope_calls.append((step, 'ProfileScope', statements))
            first = sum(USES in s for _, name, s in self.scope_calls if name == 'ProfileScope') == 1
            rows = record_rows(data)['decisions']
            for row in rows:
                if data['needs'][row['need_id']]['statement'] == USES:
                    row.update(NONE_NEITHER if first else NAMES_DATASET)
            return output_model.model_validate({'decisions': rows})
        return super().generate_structured(user=user, output_model=output_model, system=system, step=step, **kw)


def test_a_need_the_discussion_writes_that_passes_alone_is_applied_flagged(setup):
    store, run = opted_in(setup)
    client = FailsFirstTime(revise_into(USES)); fd.deliberate(store, run['run_id'], client)
    saved, case = sound(store, run)
    outcome = change(case); parent, = outcome['parent_revision_ids']
    assert outcome['status'] == 'machine_revised' and outcome['applied'] and 'scope_block' not in outcome
    record, = [r for r in saved['requirements'] if r['revision_id'] in outcome['result_revision_ids']]
    assert record['revision_id'] in saved['active_revision_ids'] and parent not in saved['active_revision_ids']
    assert 'profile_scope_disputed' in record['processing_flags']
    assert record['profile_scope']['confirmation']['outcome'] == 'disputed'
    tested, = outcome['scope_tests']
    assert tested['failed_tests'] == [] and tested['profile_scope']['confirmation']['verdict']['record_resource'] == 'none'
    assert [c[1] for c in client.scope_calls] == ['FAScopeResult', 'ProfileScope', 'ProfileScope']


def test_a_run_under_an_earlier_scope_policy_keeps_one_judgement(setup):
    # A v7 run resumed under this code blocks as it did: its record test is not judged again.
    store, run = opted_in(setup)
    store.mutate(run['run_id'], None, 'fixture_v7', lambda r: r['needs_policies'].update(profile_scope='rq1-profile-scope-v7'))
    client = FailsFirstTime(revise_into(USES)); fd.deliberate(store, run['run_id'], client)
    saved, case = sound(store, run)
    outcome = change(case)
    assert outcome['status'] == 'blocked_change' and [b['statement'] for b in outcome['scope_block']] == [USES]
    assert 'confirmation' not in outcome['scope_tests'][0]['profile_scope']
    assert outcome['scope_tests'][0]['profile_scope']['policy_version'] == 'rq1-profile-scope-v7'
    assert [c[1] for c in client.scope_calls] == ['FAScopeResult', 'ProfileScope']


@pytest.mark.parametrize('model_fails', [False, True])
def test_a_need_the_processing_guard_catches_is_not_judged_again(needs_setup, model_fails):
    # The guard reads the statement, so a second judgement cannot change it: the need is set aside whatever the
    # model says, also when the model failed it too and a second judgement would have come back missing.
    process = "Users can verify that each observation's value is included in the code list."
    statements = {'need-process': process, 'need-dimensions': DIMENSIONS}
    store, run, _, made = variants(needs_setup, statements)
    run = fa_run(store, run)
    class Guarded(InContext):
        def generate_structured(self, **kwargs):
            answer = super().generate_structured(**kwargs)
            if kwargs['output_model'].__name__ == 'ProfileScope' and model_fails:
                for d in answer.decisions:
                    if d.need_id == 'need-process': d.record_resource, d.catalogue_level, d.serves, d.example = 'none', False, 'neither', ''
            return answer
    client = Guarded(statements, omit_alone={process})
    retained = needs.judge_profile_scope(store, run, made, client)
    assert [n.requirement_id for n in retained] == ['need-dimensions']
    aside, = store.get('run', run['run_id'])['set_aside_observations']
    assert aside['need_id'] == 'need-process' and 'confirmation' not in aside['details']['profile_scope']
    assert 'operational_data_processing' in aside['details']['profile_scope']['failed_tests']
    assert aside['reason'] == ('not_catalogue_level' if model_fails else 'operational_data_processing')
    assert record_calls(client) == [sorted(statements)]
