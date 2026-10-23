"""Scope contract v1 at normalisation (rq1-profile-scope-v7 and rq1-fa-dialogue-v13, Junda, 23 Oct): every need, wherever
it is written, passes the F/A test and the catalogue-record test.

Live shapes: the F/A test sets a need aside only when it serves neither or is unsupported, so JRC and Stat
v12 kept statements about the source documents ("Users can know that DCAT is a W3C Recommendation."), their
administration (the W3C patent-disclosure list) and rules the discussion wrote ("Publishers must use all DCAT
classes and properties consistently ..."). The record test was never run in F/A runs, and needs the
discussion wrote were judged by neither test (fa_scope status checked_mediation). Scripted clients test the
plumbing only; the model's judgement shows only live.
"""
import json
from test_resume_discussions import setup  # noqa: F401  (pytest fixture)
from test_rq1_profile_scope import variants, ScopeJudge
from test_scope_contract_v1_discussion import DOCUMENT, PATENTS, DIMENSIONS, ACCESS, fa_rows, record_rows
from requirement_reuse_service.workflow import needs


# Normalisation (rq1-profile-scope-v7): the record test runs on the needs the F/A test keeps.
class BothTests(ScopeJudge):
    def __init__(self, statements, omit=()):
        super().__init__(); self.statements, self.omit_statements = statements, set(omit)
    def generate_structured(self, **kwargs):
        name, data = kwargs['output_model'].__name__, json.loads(kwargs['user'])
        if name == 'FAScopeResult':
            self.calls.append((name, data))
            return kwargs['output_model'].model_validate(fa_rows(data, self.statements))
        if name == 'ProfileScope':
            self.calls.append((name, data))
            return kwargs['output_model'].model_validate(record_rows(data, self.omit_statements))
        return super().generate_structured(**kwargs)


def fa_run(store, run):
    store.mutate(run['run_id'], None, 'fixture_fa', lambda r: r['request'].update(requirements_scope='find_access_v1'))
    return store.get('run', run['run_id'])


def test_in_fa_runs_needs_about_the_sources_are_set_aside_by_the_record_test(setup):
    statements = {'need-doc': DOCUMENT, 'need-patents': PATENTS, 'need-dimensions': DIMENSIONS, 'need-access': ACCESS}
    store, run, _, made = variants(setup, statements)
    run = fa_run(store, run); client = BothTests(statements)
    retained = needs.judge_profile_scope(store, run, made, client)
    assert [n.requirement_id for n in retained] == ['need-dimensions', 'need-access']
    saved = store.get('run', run['run_id'])
    asides = {a['need_id']: a for a in saved['set_aside_observations']}
    assert {i: a['reason'] for i, a in asides.items()} == {'need-doc': 'not_catalogue_level', 'need-patents': 'not_catalogue_level'}
    # Set aside visibly, with both verdicts, like the other set-asides.
    for aside in asides.values():
        assert aside['restored'] is False and aside['rationale'] == 'Scripted record judgement.'
        assert aside['details']['profile_scope']['record_resource'] == 'none'
        assert aside['details']['fa_scope']['status'] == 'checked' and aside['details']['fa_scope']['serves'] == 'find'
    assert asides['need-patents']['details']['profile_scope']['failed_tests'] == ['not_catalogue_level', 'not_find_or_access']
    # Kept needs carry both verdicts.
    for need in retained:
        assert need.fa_scope['status'] == 'checked' and need.profile_scope['status'] == 'checked'
        assert need.profile_scope['policy_version'] == 'rq1-profile-scope-v7' and not need.profile_scope['failed_tests']
    assert {n.requirement_id: n.profile_scope['record_resource'] for n in retained} == {'need-dimensions': 'dataset', 'need-access': 'distribution'}
    step = saved['need_steps']['profile_scope']
    assert step['policy_version'] == 'rq1-profile-scope-v7' and step['fa_policy_version'] == 'rq1-find-access-v1'
    assert step['fa_set_aside_count'] == 0 and step['record_set_aside_count'] == 2 and step['set_aside_count'] == 2
    assert step['set_aside_by_reason'] == {'not_catalogue_level': 2}
    # The record test sees only the needs the F/A test kept.
    assert sorted(i for name, data in client.calls if name == 'ProfileScope' for i in data['needs']) == sorted(statements)
    before = len(client.calls)
    needs.judge_profile_scope(store, run, made, client)
    assert len(client.calls) == before  # resume reuses both saved judgements


def test_the_record_test_judges_only_what_the_fa_test_keeps_and_a_missing_judgement_keeps_the_need(setup):
    statements = {'need-doc': DOCUMENT, 'need-dimensions': DIMENSIONS, 'need-neither': ACCESS}
    store, run, _, made = variants(setup, statements)
    run = fa_run(store, run)
    class NeitherForOne(BothTests):
        def generate_structured(self, **kwargs):
            answer = super().generate_structured(**kwargs)
            if kwargs['output_model'].__name__ == 'FAScopeResult':
                for d in answer.decisions:
                    if d.need_id == 'need-neither': d.serves = 'neither'
            return answer
    client = NeitherForOne(statements, omit={DOCUMENT})
    retained = needs.judge_profile_scope(store, run, made, client)
    # The F/A test set one aside; the record test answered nothing for DOCUMENT on both tries: kept, flagged.
    assert [n.requirement_id for n in retained] == ['need-doc', 'need-dimensions']
    reasons = {a['need_id']: a['reason'] for a in store.get('run', run['run_id'])['set_aside_observations']}
    assert reasons == {'need-neither': 'fa_scope_set_aside'}
    assert not any(i == 'need-neither' for name, data in client.calls if name == 'ProfileScope' for i in data['needs'])
    kept = {n.requirement_id: n for n in retained}
    assert kept['need-doc'].profile_scope['status'] == 'not_checked' and 'profile_scope_not_checked' in kept['need-doc'].processing_flags
    assert 'profile_scope_not_checked' not in kept['need-dimensions'].processing_flags
    # As in other runs, only needs the record test judged get an applicability label.
    assert 'applicability_status' not in kept['need-doc'].profile_scope and kept['need-dimensions'].profile_scope['applicability_status']
    step = store.get('run', run['run_id'])['need_steps']['profile_scope']
    assert step['not_checked_ids'] == ['need-doc'] and step['fa_set_aside_count'] == 1 and step['record_set_aside_count'] == 0
    assert step['set_aside_count'] == 1 and step['set_aside_by_reason'] == {'fa_scope_set_aside': 1}


def test_a_set_aside_for_explicit_data_processing_is_a_valid_run_record(setup):
    # The record test's guard on processing actions in the need gives operational_data_processing; the run
    # record must accept it, or 6a derives and discussion continuations of the run fail validation.
    from requirement_reuse_service.workflow.models import WorkflowRun
    statements = {'need-process': "Users can verify that each observation's value is included in the code list.",
                  'need-dimensions': DIMENSIONS}
    store, run, _, made = variants(setup, statements)
    run = fa_run(store, run)
    retained = needs.judge_profile_scope(store, run, made, BothTests(statements))
    assert [n.requirement_id for n in retained] == ['need-dimensions']
    saved = store.get('run', run['run_id'])
    aside, = saved['set_aside_observations']
    assert aside['reason'] == 'operational_data_processing' and aside['details']['profile_scope']['failed_tests'] == ['operational_data_processing']
    WorkflowRun.model_validate(saved)
