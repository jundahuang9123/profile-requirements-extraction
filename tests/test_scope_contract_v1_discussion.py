"""Scope contract v1 at apply (rq1-profile-scope-v7 and rq1-fa-dialogue-v13, Junda, 23 Oct): every need, wherever
it is written, passes the F/A test and the catalogue-record test.

Live shapes: the F/A test sets a need aside only when it serves neither or is unsupported, so JRC and Stat
v12 kept statements about the source documents ("Users can know that DCAT is a W3C Recommendation."), their
administration (the W3C patent-disclosure list) and rules the discussion wrote ("Publishers must use all DCAT
classes and properties consistently ..."). The record test was never run in F/A runs, and needs the
discussion wrote were judged by neither test (fa_scope status checked_mediation). Scripted clients test the
plumbing only; the model's judgement shows only live.
"""
import json
import pytest
from test_routed_stakeholder_workflow import setup  # noqa: F401  (pytest fixture)
from test_fa_dialogue_v3 import Assessing, opted_in, ids, case_of, sourced, retain_all
from test_fa_quirks import sound
from requirement_reuse_service.workflow import fa_discussion as fd

DOCUMENT = 'Users can know that DCAT is a W3C Recommendation.'
PATENTS = 'Users can know which patent disclosures were made for the DCAT specification.'
DIMENSIONS = 'Users can find the dimensions and units of measure that a dataset uses.'
ACCESS = 'Users can find the landing page and download URL of a dataset.'
RULE = 'Publishers must use all DCAT classes and properties consistently across their catalogues.'

# Record-test answers in the shapes gpt-oss gives: a rule or a document fact names no record, often while
# still claiming that it serves finding data.
NONE_FIND = {'record_resource': 'none', 'record_statement': '', 'catalogue_level': False, 'serves': 'find',
             'example': 'Find catalogues that follow DCAT.'}
NONE_NEITHER = {'record_resource': 'none', 'record_statement': '', 'catalogue_level': False, 'serves': 'neither', 'example': ''}
RECORDS = {
    DOCUMENT: NONE_FIND,
    PATENTS: NONE_NEITHER,
    RULE: NONE_FIND,
    DIMENSIONS: {'record_resource': 'dataset', 'record_statement': 'dataset: the dimensions and units of measure it uses',
                 'catalogue_level': True, 'serves': 'find', 'example': 'Filter datasets by the region dimension.'},
    ACCESS: {'record_resource': 'distribution', 'record_statement': 'distribution: its landing page and download URL',
             'catalogue_level': True, 'serves': 'access', 'example': 'Download the data from its URL.'},
}
# The F/A test keeps all of them: an information requirement that serves find, or an obligation it only flags.
FA = {RULE: {'nature': 'operational_obligation'}}


def fa_rows(data, statements=None):
    rows = []
    for i, row in data['needs'].items():
        stated = (statements or {}).get(i, row['statement'])
        rows.append({'need_id': i, 'support': 'explicit', 'serves': 'find', 'nature': 'information_requirement',
                     'actor': 'Data users', 'task': 'Select a dataset', 'example': 'Select a dataset by this information.',
                     'rationale': 'Scripted F/A judgement.', 'evidence_ids': list(row['excerpts'])[:1],
                     **FA.get(stated, {})})
    return {'decisions': rows}


def record_rows(data, omit=()):
    return {'decisions': [{'need_id': i, **RECORDS.get(row['statement'], RECORDS[DIMENSIONS]),
                           'rationale': 'Scripted record judgement.'}
                          for i, row in data['needs'].items() if row['statement'] not in omit]}


# Discussion (rq1-fa-dialogue-v13): every need a change writes passes both tests before it is applied.
class Scoped(Assessing):
    """Scripted roles, mediator and checker; both scope tests answer by the statement."""
    def __init__(self, plans, omit=(), on_assess=None):
        super().__init__(plans); self.omit, self.on_assess, self.scope_calls = set(omit), on_assess, []
    def generate_structured(self, *, user, output_model, system='', step=None, **kw):
        name = output_model.__name__
        if name == 'FAScopeResult':
            data = json.loads(user); self.scope_calls.append((step, name, [r['statement'] for r in data['needs'].values()]))
            return output_model.model_validate(fa_rows(data))
        if name == 'ProfileScope':
            data = json.loads(user); self.scope_calls.append((step, name, [r['statement'] for r in data['needs'].values()]))
            return output_model.model_validate(record_rows(data, self.omit))
        if name == 'Qualification' and self.on_assess: self.on_assess()
        return super().generate_structured(user=user, output_model=output_model, system=system, step=step, **kw)


def revise_into(statement):
    def plans(data, *_):
        needs_, concerns = ids(data); cited = sourced(data)
        return {'actions': [{'action_id': 'A1', 'action': 'retain', 'parent_revision_ids': [needs_[0]], 'rationale': 'Kept.'},
                            {'action_id': 'A2', 'action': 'revise', 'parent_revision_ids': [needs_[1]], 'statement': statement,
                             'evidence_links': cited, 'rationale': 'Reworded from the source.'}],
                'concerns': [{'concern_id': c, 'status': 'satisfied', 'action_ids': ['A1'], 'rationale': 'Kept.'} for c in concerns],
                'questions': [], 'summary': 'One revision.'}
    return plans


def split_into(*statements):
    def plans(data, *_):
        needs_, concerns = ids(data); cited = sourced(data)
        return {'actions': [{'action_id': 'A1', 'action': 'retain', 'parent_revision_ids': [needs_[0]], 'rationale': 'Kept.'},
                            {'action_id': 'A2', 'action': 'split', 'parent_revision_ids': [needs_[1]], 'rationale': 'Two needs.',
                             'children': [{'action_id': f'A2c{i+1}', 'statement': s, 'evidence_links': cited, 'rationale': 'Part.'}
                                          for i, s in enumerate(statements)]}],
                'concerns': [{'concern_id': c, 'status': 'satisfied', 'action_ids': ['A1'], 'rationale': 'Kept.'} for c in concerns],
                'questions': [], 'summary': 'One split.'}
    return plans


def change(case):
    return next(o for o in case['mediation']['outcomes'] if o['action_id'] == 'A2')


def test_a_rule_the_discussion_writes_is_blocked_and_its_need_stays(setup):
    store, run = opted_in(setup)
    client = Scoped(revise_into(RULE)); fd.deliberate(store, run['run_id'], client)
    saved, case = sound(store, run)
    outcome = change(case); parent, = outcome['parent_revision_ids']
    assert outcome['status'] == 'blocked_change' and not outcome['applied']
    assert outcome['scope_block'] == [{'revision_id': outcome['scope_tests'][0]['revision_id'], 'statement': RULE,
        'test': 'not_catalogue_level', 'record_resource': 'none', 'rationale': 'Scripted record judgement.'}]
    assert outcome['validation_error'].startswith('Scope contract v1: "' + RULE + '" failed not_catalogue_level')
    # The F/A test kept the rule (an obligation only gets a review flag); the record test blocked it.
    tested, = outcome['scope_tests']
    assert tested['fa_scope']['nature'] == 'operational_obligation' and tested['failed_tests'] == ['not_catalogue_level']
    assert parent in saved['active_revision_ids'] and not any(r.get('need_statement') == RULE for r in saved['requirements'])
    assert case['stop_reason'] == 'bounded_fa_dialogue_complete' and saved['metrics']['mediated_changes'] == 0


def test_a_split_with_one_part_that_fails_is_blocked_whole(setup):
    store, run = opted_in(setup)
    client = Scoped(split_into(DIMENSIONS, RULE)); fd.deliberate(store, run['run_id'], client)
    saved, case = sound(store, run)
    outcome = change(case); parent, = outcome['parent_revision_ids']
    assert outcome['status'] == 'blocked_change' and [b['statement'] for b in outcome['scope_block']] == [RULE]
    assert [t['failed_tests'] for t in outcome['scope_tests']] == [[], ['not_catalogue_level']]
    # Nothing of the split is applied; its need stays.
    assert parent in saved['active_revision_ids']
    assert not any(r.get('need_statement') in {DIMENSIONS, RULE} for r in saved['requirements'])
    # Both parts went to each test in one call.
    assert [(name, sorted(statements)) for _, name, statements in client.scope_calls] == [('FAScopeResult', sorted([DIMENSIONS, RULE])), ('ProfileScope', sorted([DIMENSIONS, RULE]))]


@pytest.mark.parametrize('plans', [revise_into(DIMENSIONS), split_into(DIMENSIONS, ACCESS)])
def test_catalogue_level_needs_the_discussion_writes_are_applied_with_both_verdicts(setup, plans):
    store, run = opted_in(setup)
    client = Scoped(plans); fd.deliberate(store, run['run_id'], client)
    saved, case = sound(store, run)
    outcome = change(case); parent, = outcome['parent_revision_ids']
    assert outcome['status'] == 'machine_revised' and outcome['applied'] and parent not in saved['active_revision_ids']
    written = [r for r in saved['requirements'] if r['revision_id'] in outcome['result_revision_ids']]
    assert written and all(r['revision_id'] in saved['active_revision_ids'] for r in written)
    for record in written:
        # Both verdicts instead of checked_mediation.
        assert record['fa_scope']['status'] == 'checked' and record['fa_scope']['policy_version'] == 'rq1-find-access-v1'
        assert record['profile_scope']['status'] == 'checked' and record['profile_scope']['record_resource'] in {'dataset', 'distribution'}
        assert not record['profile_scope']['failed_tests'] and 'profile_scope_not_checked' not in record['processing_flags']
    # The calls go to the profile_scope model.
    assert {c[0] for c in client.scope_calls} == {'profile_scope'}


def test_a_missing_record_judgement_applies_the_change_flagged(setup):
    store, run = opted_in(setup)
    client = Scoped(revise_into(DIMENSIONS), omit={DIMENSIONS}); fd.deliberate(store, run['run_id'], client)
    saved, case = sound(store, run)
    outcome = change(case); parent, = outcome['parent_revision_ids']
    assert outcome['status'] == 'machine_revised'
    record, = [r for r in saved['requirements'] if r['revision_id'] in outcome['result_revision_ids']]
    assert record['profile_scope']['status'] == 'not_checked' and 'profile_scope_not_checked' in record['processing_flags']
    # Asked twice (the correction), then kept.
    assert [c[1] for c in client.scope_calls] == ['FAScopeResult', 'ProfileScope', 'ProfileScope']


def test_the_scope_tests_never_stop_a_case_on_its_budget(setup, monkeypatch):
    # The assessment call before them uses up the case's time budget: the change is blocked, the case completes.
    store, run = opted_in(setup)
    clock = {'offset': 0.0}; real = fd.monotonic
    monkeypatch.setattr(fd, 'monotonic', lambda: real() + clock['offset'])
    client = Scoped(revise_into(DIMENSIONS), on_assess=lambda: clock.update(offset=clock['offset'] + 10**6))
    fd.deliberate(store, run['run_id'], client)
    saved, case = sound(store, run)
    outcome = change(case); parent, = outcome['parent_revision_ids']
    assert outcome['status'] == 'blocked_change' and outcome['validation_error'] == 'F/A scope test budget exhausted; original needs retained.'
    assert case['stop_reason'] == 'bounded_fa_dialogue_complete' and parent in saved['active_revision_ids']
    assert client.scope_calls == []


def test_a_kept_or_set_aside_need_is_not_judged_again(setup):
    store, run = opted_in(setup)
    client = Scoped(retain_all); fd.deliberate(store, run['run_id'], client)
    sound(store, run)
    assert client.scope_calls == []


def test_the_discussion_plan_records_the_scope_test_model(setup):
    store, run = opted_in(setup)
    fd.deliberate(store, run['run_id'], Scoped(retain_all))
    from requirement_reuse_service.workflow import stakeholder_workflow as old
    plan = old.audit(store, run['run_id'])['fa_discussion_plan']
    assert plan['policy_version'] == fd.BASE_POLICY and plan['models']['profile_scope']['model'] == 'model-profile_scope'
