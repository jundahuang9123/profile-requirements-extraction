"""F/A failures confirmed alone (rq1-profile-scope-v9, Junda, 24 Oct): a failed F/A test is confirmed by a second
judgement of the need alone before the need is set aside or blocks a change; when the two disagree, the need stays,
flagged fa_scope_disputed. The F/A texts and contract() are unchanged.

Live shapes: between two v8 runs of the same version almost every F/A set-aside differed (JRC 3 of 4, Stat 4 of 4).
In Stat run-ec6d1c79, 8 of its 11 F/A set-asides came from one batch of 8 in which every row was judged to serve
neither, "Users can know release date for a Catalog" among them; the first run had judged the same statement with the
same evidence to serve find. A statement about the source document ("Users can know that DCAT is a W3C
Recommendation.") is set aside by the F/A test in both judgements. Scripted clients test the plumbing only.
"""
import json
from test_resume_discussions import setup as needs_setup  # noqa: F401  (pytest fixture)
from test_routed_stakeholder_workflow import setup  # noqa: F401  (pytest fixture)
from test_rq1_profile_scope import variants
from test_scope_contract_v1_normalisation import BothTests, fa_run
from test_scope_contract_v1_discussion import Scoped, DIMENSIONS, DOCUMENT, revise_into, change, fa_rows
from test_fa_dialogue_v3 import opted_in
from test_fa_quirks import sound
from requirement_reuse_service.workflow import needs, fa_discussion as fd

RELEASE = 'Users can know release date for a Catalog'
NEITHER = {'serves': 'neither', 'nature': 'background', 'rationale': 'In a batch.'}


def fa_answer(data, alone, omit_alone=()):
    """RELEASE serves neither in a batch and find alone; DOCUMENT serves neither either way."""
    rows = fa_rows(data)['decisions']
    for row in rows:
        statement = data['needs'][row['need_id']]['statement']
        if statement == DOCUMENT or (statement == RELEASE and not alone):
            row.update(NEITHER)
        elif alone:
            row['rationale'] = 'Alone.'
    return {'decisions': [r for r in rows if not (alone and data['needs'][r['need_id']]['statement'] in omit_alone)]}


class FAInContext(BothTests):
    def __init__(self, statements, omit_alone=()):
        super().__init__(statements); self.omit_alone = set(omit_alone)
    def generate_structured(self, **kwargs):
        if kwargs['output_model'].__name__ != 'FAScopeResult':
            return super().generate_structured(**kwargs)
        data = json.loads(kwargs['user']); self.calls.append(('FAScopeResult', data))
        return kwargs['output_model'].model_validate(fa_answer(data, len(data['needs']) == 1, self.omit_alone))


def fa_calls(client):
    return [sorted(data['needs']) for name, data in client.calls if name == 'FAScopeResult']


def test_an_fa_failure_that_passes_alone_keeps_the_need_flagged(needs_setup):
    statements = {'need-release': RELEASE, 'need-doc': DOCUMENT, 'need-dimensions': DIMENSIONS}
    store, run, _, made = variants(needs_setup, statements)
    run = fa_run(store, run); client = FAInContext(statements)
    retained = needs.judge_profile_scope(store, run, made, client)
    kept = {n.requirement_id: n for n in retained}
    # The record test still judges what the F/A test keeps; DOCUMENT failed both F/A judgements.
    assert sorted(kept) == ['need-dimensions', 'need-release']
    release = kept['need-release']
    assert 'fa_scope_disputed' in release.processing_flags
    assert release.fa_scope['serves'] == 'find' and release.fa_scope['rationale'] == 'Alone.'
    assert release.fa_scope['confirmation']['outcome'] == 'disputed'
    assert release.fa_scope['confirmation']['verdict']['serves'] == 'neither'
    assert 'fa_scope_disputed' not in kept['need-dimensions'].processing_flags
    aside, = store.get('run', run['run_id'])['set_aside_observations']
    assert aside['need_id'] == 'need-doc' and aside['reason'] == 'fa_scope_set_aside'
    assert aside['details']['fa_scope']['confirmation']['outcome'] == 'confirmed'
    step = store.get('run', run['run_id'])['need_steps']['profile_scope']
    assert step['policy_version'] == 'rq1-profile-scope-v9' and step['fa_confirmation_counts'] == {'confirmed': 1, 'disputed': 1}
    assert step['fa_set_aside_count'] == 1
    # One batch, then each F/A failure alone in needs order; a resume reuses all three.
    assert fa_calls(client) == [sorted(statements), ['need-release'], ['need-doc']]
    before = len(client.calls)
    needs.judge_profile_scope(store, run, made, client)
    assert len(client.calls) == before


def test_a_need_first_judged_alone_by_the_fa_test_is_judged_again(needs_setup):
    # One need is a batch of one: the second judgement has its own cache step, or it would be the first one again.
    statements = {'need-release': RELEASE}
    store, run, _, made = variants(needs_setup, statements)
    run = fa_run(store, run)
    class FirstFails(FAInContext):
        def generate_structured(self, **kwargs):
            if kwargs['output_model'].__name__ == 'FAScopeResult':
                data = json.loads(kwargs['user']); self.calls.append(('FAScopeResult', data))
                rows = fa_rows(data)['decisions']
                if sum(name == 'FAScopeResult' for name, _ in self.calls) == 1:
                    for row in rows: row.update(NEITHER)
                return kwargs['output_model'].model_validate({'decisions': rows})
            return super().generate_structured(**kwargs)
    client = FirstFails(statements)
    retained = needs.judge_profile_scope(store, run, made, client)
    assert [n.requirement_id for n in retained] == ['need-release']
    assert retained[0].fa_scope['confirmation']['outcome'] == 'disputed'
    assert fa_calls(client) == [['need-release'], ['need-release']]


def test_a_missing_second_fa_judgement_keeps_the_need_for_review(needs_setup):
    statements = {'need-release': RELEASE, 'need-dimensions': DIMENSIONS}
    store, run, _, made = variants(needs_setup, statements)
    run = fa_run(store, run)
    client = FAInContext(statements, omit_alone={RELEASE})
    retained = needs.judge_profile_scope(store, run, made, client)
    assert sorted(n.requirement_id for n in retained) == ['need-dimensions', 'need-release']
    release = next(n for n in retained if n.requirement_id == 'need-release')
    assert {'fa_scope_disputed', 'fa_scope_review_required'} <= set(release.processing_flags)
    confirmation = release.fa_scope['confirmation']
    assert confirmation['outcome'] == 'not_checked' and confirmation['first_serves'] == 'neither'
    assert store.get('run', run['run_id'])['need_steps']['profile_scope']['fa_confirmation_counts'] == {'not_checked': 1}
    # Asked alone twice (the correction), then kept.
    assert fa_calls(client) == [sorted(statements), ['need-release'], ['need-release']]


# At apply (rq1-fa-dialogue-v13): a need a change writes is judged in a batch of the change's needs.
class FAFailsFirstTime(Scoped):
    """The F/A test fails RELEASE the first time it is asked and passes it after that."""
    def generate_structured(self, *, user, output_model, system='', step=None, **kw):
        if output_model.__name__ == 'FAScopeResult':
            data = json.loads(user); statements = [r['statement'] for r in data['needs'].values()]
            self.scope_calls.append((step, 'FAScopeResult', statements))
            first = sum(RELEASE in s for _, name, s in self.scope_calls if name == 'FAScopeResult') == 1
            rows = fa_rows(data)['decisions']
            for row in rows:
                if data['needs'][row['need_id']]['statement'] == RELEASE and first:
                    row.update(NEITHER)
            return output_model.model_validate({'decisions': rows})
        return super().generate_structured(user=user, output_model=output_model, system=system, step=step, **kw)


def test_a_need_the_discussion_writes_that_passes_the_fa_test_alone_is_applied_flagged(setup):
    store, run = opted_in(setup)
    client = FAFailsFirstTime(revise_into(RELEASE)); fd.deliberate(store, run['run_id'], client)
    saved, case = sound(store, run)
    outcome = change(case); parent, = outcome['parent_revision_ids']
    assert outcome['status'] == 'machine_revised' and outcome['applied'] and 'scope_block' not in outcome
    record, = [r for r in saved['requirements'] if r['revision_id'] in outcome['result_revision_ids']]
    assert record['revision_id'] in saved['active_revision_ids'] and parent not in saved['active_revision_ids']
    assert 'fa_scope_disputed' in record['processing_flags']
    tested, = outcome['scope_tests']
    assert tested['failed_tests'] == [] and tested['fa_scope']['confirmation']['outcome'] == 'disputed'
    assert [c[1] for c in client.scope_calls] == ['FAScopeResult', 'FAScopeResult', 'ProfileScope']


def test_a_run_under_v8_keeps_one_fa_judgement(setup):
    # A v8 run continued under this code blocks as it did: its F/A test is not judged again.
    store, run = opted_in(setup)
    store.mutate(run['run_id'], None, 'fixture_v8', lambda r: r['needs_policies'].update(profile_scope='rq1-profile-scope-v8'))
    client = FAFailsFirstTime(revise_into(RELEASE)); fd.deliberate(store, run['run_id'], client)
    saved, case = sound(store, run)
    outcome = change(case)
    assert outcome['status'] == 'blocked_change' and [b['test'] for b in outcome['scope_block']] == ['fa_scope_set_aside']
    assert 'confirmation' not in outcome['scope_tests'][0]['fa_scope']
    assert [c[1] for c in client.scope_calls] == ['FAScopeResult', 'ProfileScope']
