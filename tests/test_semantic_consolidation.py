"""Offline grouping contracts, provenance boundaries and checkpoint recovery."""
import json
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from test_resume_discussions import setup, ScriptedClient
from requirement_reuse_service.main import app
from requirement_reuse_service.llm.client import LLMError, OutputValidationError
from requirement_reuse_service.workflow import engine
from requirement_reuse_service.workflow.models import Observation, RequirementRecord, RunRequest
from requirement_reuse_service.workflow.semantic_consolidation import (
    SEMANTIC_POLICY, LEGACY_SEMANTIC_POLICY, MAX_PAYLOAD, block_key, grouped_block, semantic_consolidate)
from requirement_reuse_service.workflow.storage import canonical
from requirement_reuse_service.workflow.evaluation import workflow_metrics


class GroupClient(ScriptedClient):
    def __init__(self, mode='merge'):
        super().__init__()
        self.mode = mode
        self.transport_failure_at = None
        self.group_requests = []

    def generate_structured(self, **kwargs):
        if kwargs['output_model'].__name__ != 'SemanticGrouping':
            return super().generate_structured(**kwargs)
        data = json.loads(kwargs['user'])
        self.calls.append(('SemanticGrouping', data))
        self.group_requests.append((data, kwargs['max_tokens']))
        if len(self.group_requests) == self.transport_failure_at:
            raise LLMError('Offline simulated transport failure')
        if self.mode == 'invalid':
            raise OutputValidationError('SemanticGrouping', [{'loc':['groups'], 'type':'missing'}])
        ids = list(data['candidates'])
        if self.mode == 'missing' or (self.mode == 'correct' and 'accounting_errors' not in data):
            ids = ids[:-1]
        if self.mode == 'separate':
            groups = [{'member_ids':[i]} for i in ids]
        else:
            groups = [{'member_ids':ids, 'join_group_id':next(iter(data['offered_groups']), None),
                       'rationale':'Offline duplicate annotation.'}] if ids else []
        return kwargs['output_model'].model_validate({'groups':groups})


def inputs(setup, count=2):
    store, run, source_client = setup
    engine.execute_run(store, run['run_id'], source_client)
    run = store.get('run', run['run_id'])
    original = next(r for r in run['requirements'] if not r['parent_revision_ids'] and
                    r['normalized_intent']['obligation_hint'] == 'mandatory')
    records = []
    for i in range(count):
        observation = Observation(observation_id=f'obs-test-{i}', role_id=f'role-{i}',
            statement=f'Dataset title must be published (wording {i}).',
            requirement_type=original['requirement_type'], intent=original['normalized_intent'],
            scope=original['scope'], evidence_links=original['evidence_links'], rationale='Original rationale.')
        record = engine.record_from_observation(run['run_id'], observation)
        engine.qualify_record(store, record, run['evidence_ids'], source_client)
        records.append(record)
    run.update(consolidation_policy_version=SEMANTIC_POLICY, consolidation_chunks={}, requirements=[],
               machine_snapshot={}, consolidation_events=[], active_revision_ids=[], conflicts=[])
    run['request']['consolidation'] = 'semantic'
    run['strategy'] = 'multi_agent'
    store.mutate(run['run_id'], None, 'test_grouping_inputs', lambda saved: saved.update(run))
    return store, run, records


def revised(run, record, **changes):
    fields = dict(observation_id='obs-' + str(changes), role_id=record.contributing_roles[0],
        statement=record.raw_statement, requirement_type=record.requirement_type,
        intent=record.normalized_intent.model_dump(), scope=record.scope,
        evidence_links=[link.model_dump() for link in record.evidence_links], rationale=record.rationale)
    fields.update(changes)
    return engine.record_from_observation(run['run_id'], Observation(**fields))


def test_paraphrases_copy_verbatim_union_provenance_and_assess_once(setup):
    store, run, records = inputs(setup)
    client = GroupClient()
    active, events, conflicts = semantic_consolidate(store, run, records, client)
    assert len(active) == 1 and not conflicts
    merged = active[0]
    assert merged.raw_statement in {r.raw_statement for r in records}
    assert merged.parent_revision_ids == sorted(r.revision_id for r in records)
    assert {canonical(l.model_dump()) for l in merged.evidence_links} == {
        canonical(l.model_dump()) for r in records for l in r.evidence_links}
    assert merged.observation_ids == [o for r in sorted(records,key=lambda r:r.revision_id) for o in r.observation_ids]
    assert set(merged.contributing_roles) == {'role-0','role-1'}
    assert merged.verification['status'] == 'pass'
    assert client.count('Qualification') == client.count('SemanticGrouping') == 1
    assert events[0]['representative'] in merged.parent_revision_ids
    assert all(r.group_id == merged.group_id for r in records)
    previous = {merged.revision_id: merged.model_dump(mode='json')}
    mark = len(client.calls)
    semantic_consolidate(store, run, records, client, previous)
    assert client.count('Qualification', mark) == client.count('SemanticGrouping', mark) == 0


def test_obligation_variants_have_one_multi_record_conflict(setup):
    store, run, records = inputs(setup, 4)
    for label, record in zip(['mandatory','recommended','optional','unknown'], records):
        record.normalized_intent.obligation_hint = label
    active, events, conflicts = semantic_consolidate(store, run, records, GroupClient())
    assert len(active) == 4 and len({r.group_id for r in active}) == 1
    assert len(conflicts) == 1 and conflicts[0]['kind'] == 'obligation'
    assert set(conflicts[0]['revision_ids']) == {r.revision_id for r in active}
    assert all(r.conflict_ids == [conflicts[0]['conflict_id']] for r in active)


def test_failed_links_attach_without_contaminating_passing_merge(setup):
    store, run, records = inputs(setup, 3)
    bad_links = [l.model_dump() for l in records[-1].evidence_links]
    bad_links[0]['quote'] = 'Invented passage'
    failed = revised(run, records[-1], evidence_links=bad_links)
    engine.qualify_record(store, failed, run['evidence_ids'])
    records[-1] = failed
    active, events, _ = semantic_consolidate(store, run, records, GroupClient())
    assert len(active) == 1 and active[0].verification['status'] == 'pass'
    assert failed.revision_id not in active[0].parent_revision_ids
    assert events[0]['attached_failed'] == [failed.revision_id]
    assert all(l.quote != 'Invented passage' for l in active[0].evidence_links)


def test_complementary_failed_premises_stay_blocked_after_union(setup):
    store, run, records = inputs(setup)
    records = [revised(run,r,evidence_links=[l.model_dump() for l in r.evidence_links if l.component==component])
               for r,component in zip(records,['statement','obligation'])]
    for record in records:
        engine.qualify_record(store, record, run['evidence_ids'])
        assert record.verification['status'] == 'fail'
    client = GroupClient()
    active, _, _ = semantic_consolidate(store, run, records, client)
    assert len(active) == 1 and active[0].lifecycle_state == 'blocked_evidence'
    assert active[0].verification['parent_source_gate'] is False
    assert client.count('Qualification') == 0


@pytest.mark.parametrize('mode,fallback,calls', [('correct',False,2),('missing',True,2),('invalid',True,2)])
def test_bounded_accounting_correction_and_exact_fallback(setup, mode, fallback, calls):
    store, run, records = inputs(setup)
    client = GroupClient(mode)
    active, events, _ = semantic_consolidate(store, run, records, client)
    assert client.count('SemanticGrouping') == calls
    assert bool([e for e in events if e['action']=='semantic_grouping_unavailable']) == fallback
    assert len(active) == (2 if fallback else 1)
    assert [cap for _,cap in client.group_requests] == [4000,8000]


def test_large_block_chunks_resume_after_transport_failure_and_record_calls(setup):
    store, run, records = inputs(setup, 81)
    client = GroupClient()
    tracked = engine.TrackedClient(client,store,run['run_id'])
    client.transport_failure_at = 2
    with pytest.raises(LLMError):
        grouped_block(store,run,block_key(records[0]),records,tracked,{})
    saved = store.get('run',run['run_id'])['consolidation_chunks']
    assert len(saved) == 1
    client.transport_failure_at = None
    groups, audit = grouped_block(store,run,block_key(records[0]),records,tracked,saved)
    assert len(groups) == 1 and len(groups[0]) == 81
    assert client.count('SemanticGrouping') == 4  # first chunk is reused
    assert all(len(data['candidates']) <= 40 and len(canonical(data)) <= MAX_PAYLOAD for data,_ in client.group_requests)
    assert all('evidence_links' not in r for data,_ in client.group_requests for r in data['candidates'].values())
    assert all(data['offered_groups'] for data,_ in client.group_requests[1:])
    assert len({c for e in audit for c in e['model_call_ids']}) == 3
    api = TestClient(app)
    response = api.get(f'/api/rq1/v2/runs/{run["run_id"]}/export').json()
    assert len(response['run']['consolidation_chunks']) == 3
    assert 'consolidation_chunks' not in api.get(f'/api/rq1/v2/runs/{run["run_id"]}?audit=false').json()


def test_oversized_input_falls_back_without_call_or_lost_records(setup):
    store, run, records = inputs(setup)
    records[0].normalized_statement = 'title ' * MAX_PAYLOAD
    client = GroupClient()
    groups, audit = grouped_block(store,run,block_key(records[0]),records,client,{})
    assert sum(map(len,groups)) == 2
    assert any(e['action']=='semantic_grouping_unavailable' for e in audit)
    assert all(len(canonical(data)) <= MAX_PAYLOAD for data,_ in client.group_requests)


def test_negation_cannot_be_grouped_by_bad_model_answer(setup):
    store, run, records = inputs(setup)
    records[1].normalized_statement = 'Dataset title must not be published.'
    _, events, conflicts = semantic_consolidate(store,run,records,GroupClient())
    assert any(e['action']=='semantic_grouping_unavailable' for e in events)
    assert any(c['kind']=='potential_contradiction' for c in conflicts)


def test_default_semantic_rules_exact_and_legacy_exact(setup):
    store, run, records = inputs(setup)
    assert RunRequest(snapshot_id=run['snapshot_id'],strategy='multi_agent').consolidation == 'semantic'
    assert RunRequest(snapshot_id=run['snapshot_id'],strategy='rules').consolidation == 'exact'
    run['consolidation_policy_version'] = None
    client = GroupClient()
    active, _, _ = engine.consolidate(store,run,records,client)
    assert len(active) == 2 and client.count('SemanticGrouping') == 0


def test_grouping_metrics_from_frozen_machine(setup):
    store, run, records = inputs(setup)
    active, events, conflicts = semantic_consolidate(store,run,records,GroupClient())
    run['machine_snapshot'] = {'requirements':[r.model_dump(mode='json') for r in records + active],
        'active_revision_ids':[r.revision_id for r in active], 'consolidation_events':events,'conflicts':conflicts}
    metrics = workflow_metrics(run)['consolidation']
    assert metrics['mode']=='semantic' and metrics['input_records']==2
    assert metrics['review_items']==1 and metrics['merged_groups']==1


def test_mock_grouping_no_model_and_deterministic_block_keys(setup):
    store, run, records = inputs(setup)
    run['strategy'] = 'mock'
    records[0].normalized_statement = 'Dataset must publish dct:title.'
    records[1].normalized_statement = 'Dataset should publish dcterms:title.'
    active, _, _ = semantic_consolidate(store,run,records)
    assert len(active)==1
    for need in ['publisher','publisher identifier','publisher identification','the dataset publishers']:
        records[0].normalized_intent.metadata_need=need
        assert block_key(records[0])=='Dataset|publisher'
    records[0].normalized_intent.metadata_need='metadata'
    assert block_key(records[0])=='Dataset|title'


def test_pipeline_resume_keeps_finished_groups_and_merged_assessments(setup):
    store, run, source_client = setup
    engine.execute_run(store,run['run_id'],source_client)
    source = store.get('run',run['run_id'])
    from requirement_reuse_service.workflow.models import DeriveRequest
    derived = engine.derive_run(store,source['run_id'],DeriveRequest(expected_version=source['version'],
        discussion='on_request',reuse_assessments=False,rationale='Offline resume check.'))
    client = GroupClient()
    client.transport_failure_at = 2  # coverage block is complete; title block stops
    engine.execute_run(store,derived['run_id'],client)
    failed = store.get('run',derived['run_id'])
    assert failed['status']=='failed' and failed['stages']['verification']=='completed'
    assert len(failed['consolidation_chunks'])==1
    assert sum(bool(r['parent_revision_ids']) for r in failed['requirements'])==1
    assessed = client.count('Qualification')
    client.transport_failure_at=None
    store.mutate(derived['run_id'],None,'test_resume',lambda r:r.update(status='created'))
    engine.execute_run(store,derived['run_id'],client)
    resumed = store.get('run',derived['run_id'])
    assert resumed['status']=='awaiting_human'
    assert client.count('SpanElicitationResult')==0
    assert client.count('SemanticGrouping')==3
    # Title merges are content-identical to already assessed original records;
    # the completed coverage merge is also retained across the interruption.
    assert client.count('Qualification')-assessed==0
    assert len(resumed['active_revision_ids'])==3 and len(resumed['conflicts'])==1
    assert store.get('run',source['run_id'])==source
    assert workflow_metrics(resumed)['consolidation']['merged_assessments_reused']==3


def test_invalid_grouping_fallback_completes_derived_pipeline(setup):
    store, run, source_client = setup
    engine.execute_run(store,run['run_id'],source_client)
    source=store.get('run',run['run_id'])
    from requirement_reuse_service.workflow.models import DeriveRequest
    derived=engine.derive_run(store,source['run_id'],DeriveRequest(expected_version=source['version'],
        discussion='on_request',rationale='Offline fallback check.'))
    engine.execute_run(store,derived['run_id'],GroupClient('missing'))
    saved=store.get('run',derived['run_id'])
    assert saved['status']=='awaiting_human' and saved['stages']['consolidation']=='completed'
    assert workflow_metrics(saved)['consolidation']['fallback_chunks']==2


def test_derived_assessment_snapshot_survives_source_changes(setup):
    store, run, source_client = setup
    engine.execute_run(store,run['run_id'],source_client)
    source=store.get('run',run['run_id'])
    from requirement_reuse_service.workflow.models import DeriveRequest
    derived=engine.derive_run(store,source['run_id'],DeriveRequest(expected_version=source['version'],
        consolidation='exact',rationale='Offline frozen assessment check.'))
    def change(r):
        for record in r['requirements']:
            record['qualification']['assessor']='human-reviewer'
    store.mutate(source['run_id'],None,'test_source_review',change)
    mark=len(source_client.calls)
    engine.execute_run(store,derived['run_id'],source_client)
    assert source_client.count('Qualification',mark)==0
    assert store.get('run',derived['run_id'])['status']=='awaiting_human'


def test_statement_only_payload_ignores_inconsistent_model_labels(setup):
    store, run, records = inputs(setup)
    intent=records[1].normalized_intent.model_dump()
    intent['value_kind']='uri'
    records[1]=revised(run,records[1],intent=intent,scope='Unspecified',requirement_type='validation_constraint')
    engine.qualify_record(store,records[1],run['evidence_ids'])
    client=GroupClient()
    active,_,_=semantic_consolidate(store,run,records,client)
    assert len(active)==1
    assert all(set(payload)=={'statement'} for data,_ in client.group_requests for payload in data['candidates'].values())


def test_later_chunks_offer_only_25_relevant_groups_and_keep_every_record(setup):
    store,run,records=inputs(setup,90)
    client=GroupClient('separate')
    groups,audit=grouped_block(store,run,block_key(records[0]),records,client,{})
    assert len(groups)==90 and client.count('SemanticGrouping')==3
    assert len(client.group_requests[1][0]['offered_groups'])==25
    assert len(client.group_requests[2][0]['offered_groups'])==25
    assert not any(e['action']=='semantic_grouping_unavailable' for e in audit)


def test_consumer_capability_and_metadata_content_cannot_merge(setup):
    store,run,records=inputs(setup)
    records[1].normalized_statement='A consumer must be able to process the Dataset title.'
    active,events,_=semantic_consolidate(store,run,records,GroupClient())
    assert len(active)==2
    assert any('consumer/system capabilities' in e.get('reason','') for e in events)


def test_legacy_semantic_policy_retains_typed_payload_and_existing_checkpoints(setup):
    store,run,records=inputs(setup)
    run['consolidation_policy_version']=LEGACY_SEMANTIC_POLICY
    client=GroupClient()
    groups,_=grouped_block(store,run,block_key(records[0]),records,client,{})
    assert len(groups)==1
    assert 'value_kind' in client.group_requests[0][0]['candidates']['c1']
    saved=store.get('run',run['run_id'])['consolidation_chunks']
    grouped_block(store,run,block_key(records[0]),records,client,saved)
    assert client.count('SemanticGrouping')==1
