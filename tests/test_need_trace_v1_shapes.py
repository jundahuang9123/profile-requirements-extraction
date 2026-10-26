"""rq1-need-trace-v1, review findings (26 Oct): run shapes in which a valid need was set aside as trace_incomplete, and
call links that named the wrong call. Each test builds the shape with scripted clients and checks that the need stays
active and solid, or that the link names the call that made the decision."""
import copy
import json
import pytest
from test_routed_stakeholder_workflow import setup  # noqa: F401  (pytest fixture)
from test_fa_workflow import Dialogue
from test_need_trace_v1 import full_client
from requirement_reuse_service.workflow import engine, need_trace
from requirement_reuse_service.workflow import base_review as br
from requirement_reuse_service.workflow.base_needs import load_catalogue
from requirement_reuse_service.workflow.base_profile import load_profile
from requirement_reuse_service.workflow.models import RestoreRequest, RunRequest
from requirement_reuse_service.workflow.needs import need_integrity, restore_need
from requirement_reuse_service.workflow.engine import verify
from requirement_reuse_service.workflow.models import DeriveRequest, RequirementRecord
from test_base_review import Reviewer
from test_fa_workflow import contract_name


def new_fa_run(store, original, **kw):
    return engine.new_run(store, RunRequest(snapshot_id=original['snapshot_id'], strategy='multi_agent',
        role_ids=['consumer_discovery', 'publisher_feasibility'], stakeholder_workflow='fa_mediated', discussion='automatic',
        scoping='off', base_check=False, **kw))


def solid_and_active(run, revision_id):
    result = run['stage_results']['traceability']
    return (revision_id in run['active_revision_ids'] and result['needs'][revision_id]['solid']
            and revision_id not in result['set_aside_ids'])


class RevisingDialogue(Dialogue):
    def generate_structured(self, *, user, output_model, step=None, **kwargs):
        from test_fa_workflow import contract_name
        data = json.loads(user)
        if contract_name(output_model) == 'Plan':
            self.calls.append((step, 'Plan', data))
            packet = data['packet']; need = packet['needs'][0]; ex = packet['excerpts'][0]
            raw = {'actions': [{'action_id': 'a0', 'action': 'revise', 'parent_revision_ids': [need['revision_id']],
                    'statement': ex['quote'].rstrip('.'),
                    'evidence_links': [{'evidence_id': ex['evidence_id'], 'quote': ex['quote'], 'quote_start': ex.get('quote_start')}],
                    'rationale': 'Restate the need as the source states it.'}],
                   'summary': 'One source-anchored revision.', 'questions': [], 'concerns': []}
            return output_model.model_validate(raw)
        return super().generate_structured(user=user, output_model=output_model, step=step, **kwargs)


def test_a_need_written_by_a_v1_discussion_stays(setup):
    # A run without base review discusses under rq1-fa-dialogue-v1, which runs no scope tests at apply.
    store, original, _, _ = setup
    client = full_client(); client.dialogue = RevisingDialogue()
    run = new_fa_run(store, original)
    engine.execute_run(store, run['run_id'], client)
    saved = store.get_run(run['run_id'])
    outcome = next(o for c in saved['deliberations'] for o in c['mediation']['outcomes'] if o['action'] == 'revise')
    assert outcome['applied'] and outcome['status'] == 'machine_revised'
    made = outcome['result_revision_ids'][0]
    assert solid_and_active(saved, made)
    trace = need_trace.run_traces(store, saved, [made])[made]
    steps = {d['step']: d for d in trace['decisions']}
    # Its own judgements, not its parent's (a revision keeps the requirement ID).
    assert 'classification' not in steps and steps['fa_test']['reason'] == saved_record(saved, made)['fa_scope'].get('rationale')
    own = [v for k, v in saved['stakeholder_audit'].items() if k.startswith('mediation_assessment:')]
    assert steps['assessment']['call_ids'] == own[0]['call_ids'] and steps['assessment']['call_link'] == 'recorded'


def saved_record(run, revision_id):
    return next(r for r in run['requirements'] if r['revision_id'] == revision_id)


def test_restoring_a_set_aside_revision_restores_that_revision(setup):
    store, original, _, _ = setup
    client = full_client(); client.dialogue = RevisingDialogue()
    run = new_fa_run(store, original)
    engine.execute_run(store, run['run_id'], client)
    made = next(o for c in store.get_run(run['run_id'])['deliberations'] for o in c['mediation']['outcomes']
                if o['action'] == 'revise')['result_revision_ids'][0]
    store.mutate(run['run_id'], None, 'fixture_quote', lambda r: saved_record(r, made)['evidence_links'][0].update(quote='Not in any source.'))
    result = need_trace.record_traceability(store, run['run_id'])
    assert result['set_aside_ids'] == [made]
    saved = store.get_run(run['run_id'])
    parent = saved_record(saved, made)['parent_revision_ids'][0]
    aside = next(a for a in saved['set_aside_observations'] if a['reason'] == 'trace_incomplete')
    restore_need(store, run['run_id'], RestoreRequest(expected_version=saved['version'], idempotency_key='k1',
        observation_id=aside['observation_id'], reason='trace_incomplete', rationale='Reviewed the chain.', need_id=aside['need_id']), 'tester')
    after = store.get_run(run['run_id'])
    # The set-aside revision comes back; its superseded parent stays as it was.
    assert made in after['active_revision_ids'] and parent not in after['active_revision_ids']
    assert saved_record(after, parent) == saved_record(saved, parent)


def test_a_need_whose_record_test_gave_no_row_stays(setup):
    store, original, _, _ = setup
    client = full_client()
    bad = {}
    base = client.generate_structured
    def generate(**kw):
        name = kw['output_model'].__name__; data = json.loads(kw['user'])
        if name == 'SemanticGrouping':
            return kw['output_model'].model_validate({'groups': [{'member_ids': [m]} for m in data['candidates']]})
        if name == 'ProfileScope':
            if not bad: bad['id'] = sorted(data['needs'])[0]
            rows = [{'need_id': i, 'record_resource': 'dataset', 'record_statement': '' if i == bad['id'] else 'dataset: its title',
                     'catalogue_level': True, 'serves': 'find', 'example': 'Find datasets by their title.',
                     'rationale': 'Scripted judgement.'} for i in data['needs']]
            return kw['output_model'].model_validate({'decisions': rows})
        if name == 'NeedEquivalence':
            return kw['output_model'].model_validate({'decisions': [{'need_id': i, 'equivalent_to': [], 'rationale': 'Distinct.'} for i in data['needs']]})
        return base(**kw)
    client.generate_structured = generate
    run = new_fa_run(store, original)
    engine.execute_run(store, run['run_id'], client)
    saved = store.get_run(run['run_id'])
    assert saved['status'] == 'awaiting_human', saved['diagnostics']
    rec = next(r for r in saved['requirements'] if r.get('need_statement') and r['requirement_id'] == bad['id'])
    assert 'profile_scope_not_checked' in rec['processing_flags'] and solid_and_active(saved, rec['revision_id'])
    trace = need_trace.run_traces(store, saved, [rec['revision_id']])[rec['revision_id']]
    record_test = next(d for d in trace['decisions'] if d['step'] == 'record_test')
    assert record_test['decision'] == 'not_checked' and record_test['reason']


def test_a_need_too_large_for_base_review_stays(setup, monkeypatch):
    store, original, _, _ = setup
    run = new_fa_run(store, original)
    engine.execute_run(store, run['run_id'], full_client())
    profile, fingerprint = load_profile('dcat-ap-1.1.0'); catalogue = load_catalogue(profile['id'], fingerprint)
    def pin(r):
        r.update(base_profile_id=profile['id'], base_profile_sha256=fingerprint,
                 base_needs_catalogue={k: v for k, v in catalogue.items() if k != 'entries'})
        r['request'].update(base_profile_id=profile['id'])
    store.mutate(run['run_id'], None, 'fixture_pin', pin)
    monkeypatch.setattr(br, 'MAX_PAYLOAD', 1)
    br.review_base(store, store.get('run', run['run_id']), None)
    saved = store.get_run(run['run_id'])
    need = saved['active_revision_ids'][0]
    assert saved_record(saved, need)['base_relation']['reason'] == 'payload_budget'
    trace = need_trace.run_traces(store, saved, [need])[need]
    base = next(d for d in trace['decisions'] if d['step'] == 'base_review')
    assert trace['completeness']['solid'] and base['reason'] == 'not reviewed: payload_budget' and base['call_link'] == 'not_applicable'


def test_a_merged_need_whose_writer_left_a_member_out_stays(setup):
    store, original, _, _ = setup
    client = full_client(); client.mode = 'split'
    base = client.generate_structured
    def generate(**kw):
        name = kw['output_model'].__name__; data = json.loads(kw['user'])
        if name == 'NeedSpanElicitationResult':
            rows = []
            for index, unit in enumerate(data['evidence_units']):
                span = unit['source_spans'][0]; text = span['quote']
                for statement in ([text, text.rstrip('.') + ' in a catalogue.'] if index == 0 else [text]):
                    rows.append({'observation_id': 'x', 'role_id': 'x', 'statement': statement,
                                 'intent': {'obligation_hint': 'unknown', 'resource_type': 'Dataset', 'metadata_need': 'title'},
                                 'evidence_links': [{'source_span_id': span['span_id'], 'component': 'statement'}]})
            return kw['output_model'].model_validate({'observations': rows})
        if name == 'NeedEquivalence':
            return kw['output_model'].model_validate({'decisions': [{'need_id': i, 'equivalent_to': [], 'rationale': 'Distinct.'} for i in data['needs']]})
        return base(**kw)
    client.generate_structured = generate
    run = new_fa_run(store, original)
    engine.execute_run(store, run['run_id'], client)
    saved = store.get_run(run['run_id'])
    assert saved['status'] == 'awaiting_human', saved['diagnostics']
    events = saved['need_steps']['need_statement']['events']
    merged = next(e for e in events if e['action'] == 'merge_need' and e['split_member_ids'])
    need = merged['outputs'][0]
    assert merged['written_group_id'] != merged['group_id'] and solid_and_active(saved, need)
    trace = need_trace.run_traces(store, saved, [need])[need]
    assert next(d for d in trace['decisions'] if d['step'] == 'need_statement')['call_link'] == 'recorded'


def test_an_addition_of_a_routed_discussion_stays(setup):
    from test_rq1_need_assessment import FullNeedsClient
    from requirement_reuse_service.workflow.stakeholder_workflow import SHARED
    store, run, _, _ = setup
    class Pipeline(FullNeedsClient):
        def generate_structured(self, *, user, output_model, **kwargs):
            data = json.loads(user); name = output_model.__name__
            if name == 'NeedEquivalence':
                return output_model.model_validate({'decisions': [{'need_id': i, 'equivalent_to': [], 'rationale': 'Distinct.'} for i in data['needs']]})
            if name == 'SourceRouting':
                return output_model.model_validate({'routes': [{'evidence_id': u['evidence_id'], 'kind': 'shared', 'role_ids': [SHARED],
                    'rationale': 'Shared metadata information needs.'} for u in data['sections']]})
            if name == 'SemanticGrouping':
                return output_model.model_validate({'groups': [{'member_ids': [r]} for r in data['candidates']]})
            if name == 'NeedStatements':
                return output_model.model_validate({'needs': [{'group_id': i, 'statement': next(iter(g['members'].values()))['statement'],
                    'condition': '', 'members': [{'member_id': m, 'expresses_need': True} for m in g['members']]} for i, g in data['groups'].items()]})
            if name == 'StakeholderReview':
                return output_model.model_validate({'summary': 'No interference.', 'finished': True, 'concerns': []})
            if name == 'MediationDraft':
                ex = data['context']['excerpts'][0]
                return output_model.model_validate({'summary': 'Retain and add one sourced need.',
                    'actions': [{'action_id': str(i), 'action': 'retain', 'parent_revision_ids': [r['revision_id']],
                                 'rationale': 'Source-supported.'} for i, r in enumerate(data['context']['needs'])],
                    'additions': [{'action_id': 'add1', 'action': 'add', 'statement': 'Users can find for which dataset the access conditions apply',
                                   'evidence_links': [{'evidence_id': ex['evidence_id'], 'quote': ex['quote'], 'quote_start': ex.get('quote_start')}],
                                   'rationale': 'The source states this as a separate need.'}], 'concerns': []})
            if name == 'MediationChecks':
                return output_model.model_validate({'checks': [{'action_id': a['action_id'], 'supported': True, 'preserves_distinctions': True,
                    'priority_supported': False, 'condition_supported': True, 'obligation_preserved': True, 'rationale': 'Checked.'}
                    for a in data['plan']['actions'] if a['action'] in {'revise', 'merge', 'resolve', 'add'}]})
            return super().generate_structured(user=user, output_model=output_model, **kwargs)
    engine.execute_run(store, run['run_id'], Pipeline())
    done = store.get_run(run['run_id'])
    assert done['status'] == 'awaiting_human', done['diagnostics']
    outcomes = [o for c in done['deliberations'] for o in c['mediation'].get('outcomes', [])]
    added = next(o for o in outcomes if o['action'] == 'add' and o.get('applied'))
    assert solid_and_active(done, added['result_revision_id'])


def test_the_scope_tests_link_to_their_own_calls(setup):
    store, original, _, _ = setup
    run = new_fa_run(store, original)
    engine.execute_run(store, run['run_id'], full_client())
    saved = store.get_run(run['run_id'])
    need = saved['active_revision_ids'][0]
    steps = {d['step']: d for d in need_trace.run_traces(store, saved, [need])[need]['decisions']}
    contract = {c['call_id']: c['output_contract'] for c in saved['model_calls']}
    assert [contract[c] for c in steps['fa_test']['call_ids']] == ['FAScopeResult']
    assert [contract[c] for c in steps['record_test']['call_ids']] == ['ProfileScope']
    assert {contract[c] for c in steps['need_statement']['call_ids']} == {'NeedStatements'}


def test_a_rejected_salvage_row_does_not_break_the_kept_need(setup):
    store, original, _, _ = setup
    run = new_fa_run(store, original)
    engine.execute_run(store, run['run_id'], full_client())
    saved = copy.deepcopy(store.get_run(run['run_id']))
    need = saved['active_revision_ids'][0]
    saved['deliberations'][0]['mediation']['outcomes'].append({'action_id': 'A2', 'action': 'merge', 'parent_revision_ids': [need, 'N2'],
        'statement': 'x', 'rationale': 'Merge with N2.', 'status': 'human_review', 'applied': False, 'human_accepted': False,
        'salvage_rejected': True, 'validation_errors': ['Names a need outside this case.']})
    index = need_trace.TraceIndex(store, saved)
    assert need_trace.need_trace(index, need)['completeness']['solid']
    assert [i['action_id'] for i in need_trace.review_items(index)] == ['A2']


def test_a_need_whose_source_check_failed_is_set_aside_for_that_reason(setup):
    store, original, _, _ = setup
    run = new_fa_run(store, original)
    engine.execute_run(store, run['run_id'], full_client())
    saved = copy.deepcopy(store.get_run(run['run_id']))
    need = saved['active_revision_ids'][0]
    saved_record(saved, need)['verification'] = {**saved_record(saved, need)['verification'], 'status': 'fail', 'message': 'Quote moved.'}
    trace = need_trace.need_trace(need_trace.TraceIndex(store, saved), need)
    assert trace['completeness']['missing'] == [{'link': 'sources', 'detail': 'The source check failed: Quote moved.'}]


def test_many_broken_chains_at_once_set_nothing_aside(setup, monkeypatch):
    store, original, _, _ = setup
    run = new_fa_run(store, original)
    engine.execute_run(store, run['run_id'], full_client())
    before = store.get_run(run['run_id'])
    monkeypatch.setattr(need_trace, 'MAX_SET_ASIDE_COUNT', 0); monkeypatch.setattr(need_trace, 'MAX_SET_ASIDE_SHARE', 0)
    store.mutate(run['run_id'], None, 'fixture_quote', lambda r: saved_record(r, r['active_revision_ids'][0])['evidence_links'][0].update(quote='Gone.'))
    result = need_trace.record_traceability(store, run['run_id'])
    after = store.get_run(run['run_id'])
    assert result['set_aside_ids'] == [] and result['held_ids'] == before['active_revision_ids']
    assert after['active_revision_ids'] == before['active_revision_ids'] and 'Traceability:' in after['diagnostics'][-1]


# Second review (26 Oct).

def test_a_need_set_aside_for_its_chain_passes_its_source_check_when_restored(setup):
    # The trace_incomplete flag is part of the need's integrity hash; a stale hash failed verification on restore.
    store, original, _, _ = setup
    run = new_fa_run(store, original)
    engine.execute_run(store, run['run_id'], full_client())
    need = store.get_run(run['run_id'])['active_revision_ids'][0]
    def drop(r):
        step = copy.deepcopy(r['need_steps']['profile_scope'])
        for row in step['record_decisions']: row['need_id'] = 'req-another'
        r['need_steps']['profile_scope'] = step
    store.mutate(run['run_id'], None, 'fixture_drop_record_test', drop, parts=True)
    assert need_trace.record_traceability(store, run['run_id'])['set_aside_ids'] == [need]
    saved = store.get_run(run['run_id'])
    record = RequirementRecord.model_validate(saved_record(saved, need))
    assert 'trace_incomplete' in record.processing_flags and record.need_integrity_hash == need_integrity(record)
    assert verify(store, record, saved['evidence_ids'])['status'] == 'pass'
    aside = next(a for a in saved['set_aside_observations'] if a['reason'] == 'trace_incomplete')
    restore_need(store, run['run_id'], RestoreRequest(expected_version=saved['version'], idempotency_key='k1',
        observation_id=aside['observation_id'], reason='trace_incomplete', rationale='Reviewed the chain.', need_id=aside['need_id']), 'tester')
    restored = saved_record(store.get_run(run['run_id']), need)
    assert restored['lifecycle_state'] == 'awaiting_human' and restored['verification']['status'] == 'pass'


def card_of(decisions, flags=()):
    trace = {'revision_id': 'r1', 'requirement_id': 'q1', 'statement': 'Users can find X.', 'flags': list(flags),
             'sources': [{'source': 's.txt', 'quote': 'Users can find X.'}], 'origin': [], 'discussion': [],
             'completeness': {'missing': []}, 'decisions': decisions}
    return need_trace.need_summary(trace), need_trace.need_summary(trace, 'exceptions')


def test_the_card_never_reports_an_unmade_check_as_passed():
    card, note = card_of([{'step': 'proposal_support', 'decision': 'not_checked'}, {'step': 'fa_test', 'decision': 'unresolved'},
                          {'step': 'record_test', 'decision': 'not_checked'},
                          {'step': 'record_test_confirmation', 'decision': 'not_checked'}])
    assert 'quote supports it' not in card and 'helps users' not in card and 'record test not_checked' not in card
    assert 'the quote check could not judge it' in card and 'the find/access test could not judge it' in card
    assert 'a second judgement is missing at the record test' in card and 'overruled' not in card
    assert 'Standard path' not in note and 'could not judge' in note
    card, note = card_of([{'step': 'proposal_support', 'decision': 'supported'}, {'step': 'fa_test', 'decision': 'both'},
                          {'step': 'record_test', 'decision': 'passed'}])
    assert 'the quote supports it; it helps users find and access data; record test passed' in card
    assert 'Standard path' in note


SPLIT_SECOND = 'Users can find for which dataset the access conditions apply'


def link(ex):
    return [{'evidence_id': ex['evidence_id'], 'quote': ex['quote'], 'quote_start': ex.get('quote_start')}]


class Scripted(Dialogue):
    """mode: revise (first need), split (first need into two), add (one new need), revise_keep (statement unchanged
    but for punctuation)."""
    def __init__(self, mode):
        super().__init__(); self.mode = mode
    def generate_structured(self, *, user, output_model, step=None, **kwargs):
        if output_model in (br.BaseReview, br.BaseReviewChecks):
            return Reviewer('new').generate_structured(user=user, output_model=output_model)
        data = json.loads(user)
        if contract_name(output_model) == 'Plan':
            self.calls.append((step, 'Plan', data))
            packet = data['packet']; ids = [n['revision_id'] for n in packet['needs']]; ex = packet['excerpts']
            first = ex[0]
            actions = []
            if self.mode == 'revise':
                actions.append({'action_id': 'a0', 'action': 'revise', 'parent_revision_ids': [ids[0]],
                    'statement': first['quote'].rstrip('.'), 'evidence_links': link(first),
                    'rationale': 'Restate the need as the source states it.'})
                rest = ids[1:]
            elif self.mode == 'split':
                second = ex[1] if len(ex) > 1 else ex[0]
                actions.append({'action_id': 'a0', 'action': 'split', 'parent_revision_ids': [ids[0]],
                    'rationale': 'Two distinct needs.', 'statement': first['quote'].rstrip('.'), 'evidence_links': link(first),
                    'children': [
                        {'action_id': 'a0c1', 'action': 'add', 'parent_revision_ids': [], 'statement': first['quote'].rstrip('.'),
                         'evidence_links': link(first), 'rationale': 'First part.'},
                        {'action_id': 'a0c2', 'action': 'add', 'parent_revision_ids': [], 'statement': SPLIT_SECOND,
                         'evidence_links': link(second), 'rationale': 'Second part.'}]})
                rest = ids[1:]
            else:
                rest = ids
            actions += [{'action_id': f'r{i}', 'action': 'retain', 'parent_revision_ids': [r], 'rationale': 'Kept as written.'}
                        for i, r in enumerate(rest)]
            if self.mode == 'add':
                actions.append({'action_id': 'add1', 'action': 'add', 'parent_revision_ids': [],
                    'statement': 'Users can find for which dataset the access conditions apply',
                    'evidence_links': link(first), 'rationale': 'The source states this as a separate need.'})
            raw = {'actions': actions, 'summary': 'Scripted plan.', 'questions': [],
                   'concerns': [{'concern_id': c['concern_id'], 'status': 'satisfied', 'action_ids': [actions[0]['action_id']],
                                 'rationale': 'Kept.'} for m in data['messages'] for c in m['concerns']]}
            return output_model.model_validate(raw)
        return super().generate_structured(user=user, output_model=output_model, step=step, **kwargs)


def client_for(mode):
    client = full_client(); client.dialogue = Scripted(mode)
    base = client.generate_structured
    def generate(**kw):
        if kw['output_model'] in (br.BaseReview, br.BaseReviewChecks):
            return Reviewer('new').generate_structured(user=kw['user'], output_model=kw['output_model'])
        if kw['output_model'].__name__ in {'TaskLabels', 'ExperienceReview', 'ExperiencePlan', 'DefinedChecks'}:
            return client.dialogue.generate_structured(**kw)
        if kw['output_model'].__name__ == 'NeedClassifications':
            data = json.loads(kw['user'])
            return kw['output_model'].model_validate({'classifications': [{'need_id': i, 'classification': 'domain', 'base_need_ids': [],
                'rationale': 'Scripted coverage classification.'} for i in data['needs']]})
        return base(**kw)
    client.generate_structured = generate
    return client




def test_a_superseded_parent_links_its_own_scope_calls_and_its_revision_its_own(setup):
    # A v14 revise keeps the requirement ID; the scope tests at apply cache their rows under it.
    store, original, _, _ = setup
    run = new_fa_run(store, original, base_profile_id='dcat-ap-1.1.0', base_review='expert_v1')
    client = client_for('revise'); inner = client.generate_structured
    def judged(**kw):
        if kw['output_model'].__name__ == 'FAScopeResult':
            data = json.loads(kw['user'])
            return kw['output_model'].model_validate({'decisions': [{'need_id': i, 'support': 'explicit', 'serves': 'find',
                'nature': 'information_requirement', 'actor': 'Users', 'task': 'Find a dataset', 'example': 'Select a dataset by title.',
                'rationale': 'Judged: ' + row['statement'], 'evidence_ids': list(row['excerpts'])} for i, row in data['needs'].items()]})
        return inner(**kw)
    client.generate_structured = judged
    engine.execute_run(store, run['run_id'], client)
    saved = store.get_run(run['run_id'])
    made = next(r for o in [o for c in saved['deliberations'] for o in c['mediation']['outcomes']] if o.get('applied')
                for r in need_trace.result_ids(o))
    child = saved_record(saved, made); parent = saved_record(saved, child['parent_revision_ids'][0])
    assert child['requirement_id'] == parent['requirement_id'] and child['need_statement'] != parent['need_statement']
    index = need_trace.TraceIndex(store, saved); calls = {c['call_id']: c for c in saved['model_calls']}
    def judged_statements(revision):
        fa = next(d for d in need_trace.need_trace(index, revision)['decisions'] if d['step'] == 'fa_test')
        return fa['call_link'], {r['rationale'] for c in fa['call_ids'] for r in calls[c]['output']['decisions'] if r['need_id'] == parent['requirement_id']}
    assert judged_statements(parent['revision_id']) == ('recorded', {'Judged: ' + parent['need_statement']})
    assert judged_statements(made) == ('recorded', {'Judged: ' + child['need_statement']})


def test_a_needs_run_without_the_fa_test_traces_its_record_test(setup):
    store, original, _, _ = setup
    run = engine.new_run(store, RunRequest(snapshot_id=original['snapshot_id'], strategy='multi_agent',
        role_ids=['consumer_discovery', 'publisher_feasibility'], discussion='on_request', scoping='off', base_check=False))
    engine.execute_run(store, run['run_id'], full_client())
    saved = store.get_run(run['run_id'])
    assert not need_trace.fa_run(saved)
    need = saved['active_revision_ids'][0]
    steps = {d['step']: d for d in need_trace.run_traces(store, saved, [need])[need]['decisions']}
    contract = {c['call_id']: c['output_contract'] for c in saved['model_calls']}
    assert 'fa_test' not in steps and [contract[c] for c in steps['record_test']['call_ids']] == ['ProfileScope']
    assert solid_and_active(saved, need)


def split_client():
    client = full_client(); client.mode = 'split'
    base = client.generate_structured; reviewer = Reviewer()
    def generate(**kw):
        name = kw['output_model'].__name__; data = json.loads(kw['user'])
        if name == 'NeedSpanElicitationResult':
            rows = []
            for index, unit in enumerate(data['evidence_units']):
                span = unit['source_spans'][0]; text = span['quote']
                for statement in ([text, text.rstrip('.') + ' in a catalogue.'] if index == 0 else [text]):
                    rows.append({'observation_id': 'x', 'role_id': 'x', 'statement': statement,
                                 'intent': {'obligation_hint': 'unknown', 'resource_type': 'Dataset', 'metadata_need': 'title'},
                                 'evidence_links': [{'source_span_id': span['span_id'], 'component': 'statement'}]})
            return kw['output_model'].model_validate({'observations': rows})
        if name == 'NeedEquivalence':
            return kw['output_model'].model_validate({'decisions': [{'need_id': i, 'equivalent_to': [], 'rationale': 'Distinct.'} for i in data['needs']]})
        if name in {'TaskLabels', 'ExperienceReview', 'ExperiencePlan', 'DefinedChecks'}:
            return client.dialogue.generate_structured(**kw)
        if name in {'BaseReview', 'BaseReviewChecks'}:
            return reviewer.generate_structured(user=kw['user'], output_model=kw['output_model'])
        return base(**kw)
    client.generate_structured = generate
    return client


def build_source(store, original, strip):
    run = new_fa_run(store, original)
    engine.execute_run(store, run['run_id'], split_client())
    saved = store.get_run(run['run_id'])
    assert saved['status'] == 'awaiting_human', saved['diagnostics']
    profile, fingerprint = load_profile('dcat-ap-1.1.0'); catalogue = load_catalogue(profile['id'], fingerprint)
    def pin(r):
        r.update(base_profile_id=profile['id'], base_profile_sha256=fingerprint,
                 base_needs_catalogue={k: v for k, v in catalogue.items() if k != 'entries'})
        r['request'].update(base_profile_id=profile['id'])
        if strip:  # a run saved before v1: its merge events name no written group
            for e in r['need_steps']['need_statement']['events']: e.pop('written_group_id', None)
    store.mutate(run['run_id'], None, 'fixture_pin', pin, parts=True)
    return store.get_run(run['run_id'])


def merged_event(run):
    return next(e for e in run['need_steps']['need_statement']['events'] if e['action'] == 'merge_need' and e['split_member_ids'])


def trial(store, source):
    child = engine.derive_run(store, source['run_id'], DeriveRequest(start_from='base_review', expected_version=source['version'],
                              rationale='Base trial of an older run.'))
    engine.execute_run(store, child['run_id'], split_client())
    return store.get_run(child['run_id'])


def test_a_base_review_trial_of_an_older_run_keeps_its_merged_need(setup):
    # The trial copies merge events written before written_group_id, under its source run's ID.
    store, original, _, _ = setup
    source = build_source(store, original, strip=True)
    event = next(e for e in source['need_steps']['need_statement']['events'] if e['action'] == 'merge_need' and e['split_member_ids'])
    assert 'written_group_id' not in event
    child = engine.derive_run(store, source['run_id'], DeriveRequest(start_from='base_review', expected_version=source['version'],
                              rationale='Base trial of an older run.'))
    engine.execute_run(store, child['run_id'], split_client())
    trial = store.get_run(child['run_id'])
    assert trial['status'] == 'awaiting_human', trial['diagnostics']
    group = saved_record(trial, event['outputs'][0]).get('group_id')
    merged = [r['revision_id'] for r in trial['requirements'] if r.get('group_id') == group and r['revision_id'] in trial['active_revision_ids']]
    assert merged and all(solid_and_active(trial, r) for r in merged)
