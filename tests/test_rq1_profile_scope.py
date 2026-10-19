"""D5 profile scope: a judgement over source-derived needs that can only keep or set aside.

Dataset-level relevance and discovery contribution can set a need aside; representativeness
only labels a kept need common, specialized or for review. Since v6 dataset-level relevance
names the catalogued resource whose record would state the need.
"""
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
    'need-5': 'Users can find parking datasets by the type of parking facility.',
}
VERDICTS = {
    'need-0': {'record_resource': 'dataset', 'record_statement': 'dataset: the area it covers',
               'catalogue_level': True, 'serves': 'find', 'example': 'Find datasets covering Bavaria.',
               'representativeness': 'common'},
    'need-1': {'record_resource': 'dataset', 'record_statement': 'dataset: the providers of its data',
               'catalogue_level': True, 'serves': 'neither', 'example': '', 'representativeness': 'common'},
    'need-2': {'record_resource': 'dataset', 'catalogue_level': False, 'serves': 'access',
               'example': 'Get data with timestamps.', 'representativeness': 'common'},
    'need-3': {'record_resource': 'dataset', 'record_statement': 'dataset: its positional accuracy in metres',
               'catalogue_level': True, 'serves': 'both', 'example': 'Filter datasets by stated accuracy.',
               'representativeness': 'single_case'},
    'need-4': {'record_resource': 'none', 'catalogue_level': False, 'serves': 'neither', 'example': '',
               'representativeness': 'uncertain'},
    'need-5': {'record_resource': 'dataset', 'record_statement': 'dataset: the type of parking facility it covers',
               'catalogue_level': True, 'serves': 'find', 'example': 'Find datasets about multi-storey car parks.',
               'representativeness': 'specialized'},
}


class ScopeJudge(NeedsClient):
    def __init__(self, verdicts=VERDICTS, default=VERDICTS['need-0'], extra=(), omit=(), blank_once=(),
                 blank_record_once=()):
        super().__init__(); self.verdicts, self.default, self.extra, self.omit = verdicts, default, extra, omit
        self.blank_once, self.blank_record_once = set(blank_once), set(blank_record_once)
    def generate_structured(self, **kwargs):
        if kwargs['output_model'].__name__ != 'ProfileScope':
            return super().generate_structured(**kwargs)
        data = json.loads(kwargs['user']); self.calls.append(('ProfileScope', data))
        rows = []
        for i in [*data['needs'], *self.extra]:
            if i in self.omit: continue
            verdict = self.verdicts.get(i, self.default)
            row = {'need_id': i, 'record_resource': 'dataset' if verdict['catalogue_level'] else 'none',
                   'record_statement': 'dataset: as stated' if verdict['catalogue_level'] else '',
                   **{k:v for k,v in verdict.items() if k not in {'representativeness', 'category_links'}},
                   'rationale': 'Scripted scope judgement.'}
            if i in self.blank_once:
                self.blank_once.discard(i); row['example'] = ''
            if i in self.blank_record_once:
                self.blank_record_once.discard(i); row['record_statement'] = ''
            rows.append(row)
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


def test_only_dataset_level_and_discovery_set_aside_and_specialised_needs_stay(setup):
    store, run, _, made = variants(setup); client = ScopeJudge()
    retained = needs.judge_profile_scope(store, run, made, client)
    assert [n.requirement_id for n in retained] == ['need-0', 'need-3', 'need-5']
    assert {n.requirement_id: n.profile_scope['scope_class'] for n in retained} == {
        'need-0': 'review', 'need-3': 'review', 'need-5': 'review'}
    asides = {a['need_id']: a for a in store.get('run', run['run_id'])['set_aside_observations']}
    assert {i: a['reason'] for i, a in asides.items()} == {'need-1': 'not_find_or_access',
        'need-2': 'not_catalogue_level', 'need-4': 'not_catalogue_level'}
    assert asides['need-4']['details']['profile_scope']['failed_tests'] == ['not_catalogue_level', 'not_find_or_access']
    assert all(asides[i]['rationale'] == 'Scripted scope judgement.' for i in asides)
    # The judge sees only the stated need and judges it; it is never asked to write one.
    offered = [data['needs'] for name, data in client.calls if name == 'ProfileScope']
    assert all(set(row) == {'statement', 'condition', 'scope', 'excerpts'} for batch in offered for row in batch.values())
    kept = retained[0]
    assert kept.profile_scope['status'] == 'checked' and kept.profile_scope['example'] == VERDICTS['need-0']['example']
    assert kept.profile_scope['record_statement'] == VERDICTS['need-0']['record_statement']
    assert kept.need_statement == STATEMENTS['need-0']
    assert engine.verify(store, kept, run['evidence_ids'])['status'] == 'pass'  # integrity binds the judgement
    step = store.get('run', run['run_id'])['need_steps']['profile_scope']
    assert step['policy_version'] == 'rq1-profile-scope-v6'
    assert step['retained_count'] == 3 and step['set_aside_count'] == 3
    assert step['set_aside_by_reason'] == {'not_catalogue_level': 2, 'not_find_or_access': 1}
    # Without category evidence, a model's confident common/specialized label remains review.
    assert step['scope_classes'] == {'review': 3}
    before = len(client.calls)
    needs.judge_profile_scope(store, run, made, client)
    assert len(client.calls) == before  # resume reuses the saved judgement


def test_explicit_processing_actions_do_not_become_catalogue_needs_from_hypothetical_filters(setup):
    store, run, _, made = variants(setup, {
        'need-process':'The system must validate observation-level integrity constraints.',
        'need-structure':'Users can identify the data structure definition associated with a dataset.'})
    client=ScopeJudge(verdicts={
        'need-process':{'catalogue_level':True,'serves':'find','example':'Filter datasets by validation result.',
                        'representativeness':'common'},
        'need-structure':{'catalogue_level':True,'serves':'find','example':'Find datasets with a stated structure definition.',
                          'representativeness':'specialized'}})
    retained=needs.judge_profile_scope(store,run,made,client)
    assert [item.requirement_id for item in retained]==['need-structure']
    aside=next(item for item in store.get('run',run['run_id'])['set_aside_observations']
               if item['need_id']=='need-process')
    assert aside['reason']=='operational_data_processing'
    assert aside['details']['profile_scope']['guardrail_flags']==['operational_data_processing']


def test_contract_can_only_judge_offered_needs():
    assert set(needs.ProfileScope.model_fields) == {'decisions'}
    assert set(needs.ScopeDecision.model_fields) == {
        'need_id', 'record_resource', 'record_statement', 'catalogue_level', 'serves', 'example', 'rationale'}
    assert 'never add, merge, broaden or rewrite a need' in needs.SCOPE_SYSTEM
    # Representativeness is a label, never a set-aside test.
    assert [reason for reason, _ in needs.SCOPE_TESTS] == ['not_catalogue_level', 'not_find_or_access']
    assert set(needs.SCOPE_CLASSES.values()) == {'common', 'specialized', 'review'}


def test_a_missing_example_gets_one_correction_for_that_need_only(setup):
    store, run, _, made = variants(setup, {'need-0': STATEMENTS['need-0'], 'need-5': STATEMENTS['need-5']})
    client = ScopeJudge(blank_once=('need-0',))
    retained = needs.judge_profile_scope(store, run, made, client)
    assert [n.requirement_id for n in retained] == ['need-0', 'need-5']
    assert judged(client) == ['need-0', 'need-5', 'need-0']
    assert retained[0].profile_scope['example'] == VERDICTS['need-0']['example']


def test_invented_row_is_ignored_and_unjudged_need_stays_for_review(setup):
    store, run, _, made = variants(setup, {'need-0': STATEMENTS['need-0'], 'need-1': STATEMENTS['need-1']})
    client = ScopeJudge(extra=('invented-need',), omit=('need-1',))
    retained = needs.judge_profile_scope(store, run, made, client)
    assert [n.requirement_id for n in retained] == ['need-0', 'need-1']
    unchecked = retained[1]
    assert 'profile_scope_not_checked' in unchecked.processing_flags
    assert unchecked.profile_scope['status'] == 'not_checked' and unchecked.profile_scope['scope_class'] == 'review'
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
    assert row['record']['base_gap']['status'] == 'not_checked'  # no base selected
    assert export['families'] == [] and saved['need_steps']['families']['family_count'] == 0
    restored = needs.restore_need(store, run['run_id'], RestoreRequest(expected_version=saved['version'],
        idempotency_key='restore-scope', observation_id=item['observation_id'], need_id=item['need_id'],
        reason=item['reason'], rationale='Reviewer judges this catalogue level.'), 'offline-reviewer')['run']
    need = next(r for r in restored['requirements'] if r['revision_id'] in restored['active_revision_ids'])
    assert need['lifecycle_state'] == 'awaiting_human' and need['requirement_id'] == item['need_id']
    assert restored['decisions'][-1]['reason'] == 'not_catalogue_level'


def test_runs_saved_under_earlier_policies_need_a_derived_trial():
    import pytest
    earlier = {**needs.POLICIES, 'profile_scope': 'rq1-profile-scope-v1', 'scoping': 'rq1-use-case-necessity-v1',
               'scope_critic': 'rq1-use-case-critic-v1'}
    earlier.pop('base_gap')
    with pytest.raises(ValueError, match='derive a separate trial'):
        needs.run_needs_policies({'needs_policies': earlier})
    assert needs.run_needs_policies({'needs_policies': dict(needs.POLICIES)}) == needs.POLICIES


def test_a_need_no_catalogue_record_would_state_is_not_catalogue_level(setup):
    """v6: a fact about the source document has no record; a dataset's structure has one."""
    store, run, _, made = variants(setup, {
        'need-document': 'Users can know that the document is a W3C Recommendation.',
        'need-structure': 'Users can find which dimensions a statistical dataset uses.'})
    client = ScopeJudge(verdicts={
        # The judge still calls the first one catalogue level, but can name no record for it.
        'need-document': {'record_resource': 'none', 'catalogue_level': True, 'serves': 'find',
                          'example': 'Find W3C Recommendations.'},
        'need-structure': {'record_resource': 'dataset',
                           'record_statement': 'dataset: the dimensions its observations use, such as time period and region',
                           'catalogue_level': True, 'serves': 'find',
                           'example': 'Find datasets broken down by region.'}})
    retained = needs.judge_profile_scope(store, run, made, client)
    assert [n.requirement_id for n in retained] == ['need-structure']
    assert retained[0].profile_scope['record_resource'] == 'dataset'
    assert retained[0].profile_scope['record_statement'].startswith('dataset: the dimensions')
    aside = next(a for a in store.get('run', run['run_id'])['set_aside_observations'] if a['need_id'] == 'need-document')
    assert aside['reason'] == 'not_catalogue_level'
    assert aside['details']['profile_scope']['record_resource'] == 'none'
    assert aside['details']['profile_scope']['failed_tests'] == ['not_catalogue_level']
    assert len(client.calls) == 1  # a named-none record is judged, not retried


def test_a_missing_record_statement_gets_one_correction_for_that_need_only(setup):
    store, run, _, made = variants(setup, {'need-0': STATEMENTS['need-0'], 'need-5': STATEMENTS['need-5']})
    client = ScopeJudge(blank_record_once=('need-5',))
    retained = needs.judge_profile_scope(store, run, made, client)
    assert [n.requirement_id for n in retained] == ['need-0', 'need-5']
    assert judged(client) == ['need-0', 'need-5', 'need-5']
    assert retained[1].profile_scope['record_statement'] == VERDICTS['need-5']['record_statement']


def test_the_scope_prompt_asks_for_the_record_and_names_what_has_none():
    prompt = ' '.join(needs.SCOPE_SYSTEM.split())
    assert 'record_resource' in prompt and 'record_statement' in prompt
    assert 'a statement about the source document itself' in prompt
    assert 'how data must be processed, for a legal or administrative procedure' in prompt
    # A dataset's properties about processing stay: they are what a record can state.
    assert "the legal basis or purpose under which a dataset's personal data are processed" in prompt
    assert 'such as a facility, equipment or software' in prompt
    assert 'its dimensions, attributes, units of measure or code lists' in prompt


def test_another_catalogued_resource_kind_is_kept_when_its_record_is_named(setup):
    """Profiles such as EPOS catalogue more than datasets (facilities, equipment, software)."""
    store, run, _, made = variants(setup, {
        'need-facility': 'Users can find which instruments a research facility hosts.',
        'need-unnamed': 'Users can find the software a laboratory provides.'})
    client = ScopeJudge(verdicts={
        'need-facility': {'record_resource': 'other', 'record_statement': 'facility: the instruments it hosts',
                          'catalogue_level': True, 'serves': 'find', 'example': 'Find facilities hosting seismometers.'},
        'need-unnamed': {'record_resource': 'other', 'record_statement': 'the software it provides',
                         'catalogue_level': True, 'serves': 'find', 'example': 'Find laboratories providing software.'}})
    retained = needs.judge_profile_scope(store, run, made, client)
    assert [n.requirement_id for n in retained] == ['need-facility', 'need-unnamed']
    assert retained[0].profile_scope['record_resource'] == 'other'
    # An 'other' record without its kind gets one correction, then stays for review.
    assert judged(client) == ['need-facility', 'need-unnamed', 'need-unnamed']
    assert retained[1].profile_scope['status'] == 'not_checked'
    assert needs.other_record_kind('facility: the instruments it hosts') == 'facility'
    assert needs.other_record_kind('the software it provides') is None
