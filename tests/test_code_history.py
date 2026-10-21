"""implementation_hash names the code that created a run; code_history lists each start under other code."""
from test_workflow import context  # noqa: F401  (pytest fixture)
from test_routed_stakeholder_workflow import setup  # noqa: F401  (pytest fixture)
from requirement_reuse_service.models import ArtifactPayload
from requirement_reuse_service.workflow import engine, base_review as br, fa_discussion as fd
from requirement_reuse_service.workflow.evidence import register_source
from requirement_reuse_service.workflow.models import DeriveRequest, RunRequest, SnapshotRequest, SourceRequest

HISTORY=[{'implementation_hash':'later-code','claimed_at':'2026-10-21T00:00:00Z','stages':{'deliberation':'running'}}]


def created(context):
    store,_=context
    source=register_source(store,SourceRequest(artifact=ArtifactPayload(name='needs.md',
        content='Each dataset must describe the represented asset.'),source_role='stakeholder_need'))
    snapshot=engine.freeze_snapshot(store,SnapshotRequest(source_version_ids=[source['source_version_id']]))
    return store,engine.new_run(store,RunRequest(output_form='candidates',consolidation='exact',
        snapshot_id=snapshot['snapshot_id'],strategy='rules'))


def test_a_run_started_by_the_code_that_created_it_records_no_change(context):
    store,run=created(context);engine.execute_run(store,run['run_id'])
    saved=store.get('run',run['run_id'])
    assert saved['status']=='awaiting_human' and saved['implementation_hash']==engine.implementation_identity()
    assert saved['code_history']==[]


def test_a_run_started_under_other_code_records_it_once(context,monkeypatch):
    store,run=created(context)
    monkeypatch.setattr(engine,'implementation_identity',lambda:'other-code')
    engine.execute_run(store,run['run_id'])
    saved=store.get('run',run['run_id'])
    assert saved['implementation_hash']==run['implementation_hash']!='other-code'
    [entry]=saved['code_history']
    assert entry['implementation_hash']=='other-code' and entry['claimed_at']
    assert entry['stages']['acquisition']=='completed' and entry['stages']['elicitation']=='pending'
    # Starting again under the same code adds nothing.
    store.mutate(run['run_id'],None,'fixture_interrupted',lambda r:r.update(status='interrupted'))
    engine.execute_run(store,run['run_id'])
    assert store.get('run',run['run_id'])['code_history']==[entry]


def test_a_base_review_trial_starts_its_own_code_history(setup):
    from test_base_review import derivable
    store,source=derivable(setup)
    store.mutate(source['run_id'],None,'fixture_history',lambda r:r.update(code_history=HISTORY))
    source=store.get('run',source['run_id'])
    child=br.derive_base_review_run(store,source,DeriveRequest(start_from='base_review',
        expected_version=source['version'],rationale='Independent base trial.'),'fixture')
    assert child['code_history']==[] and child['derived_from']['parent_code_history']==HISTORY


def test_a_discussion_continuation_starts_its_own_code_history(setup):
    from test_mediation_timeout_fallback import prepare, RoutedDialogue
    store,run=prepare(setup);fd.deliberate(store,run['run_id'],RoutedDialogue())
    def interrupted(r):
        r.update(status='failed',code_history=HISTORY)
        for stage in ('acquisition','decomposition','role_selection','elicitation','normalization','verification','consolidation'):
            r['stages'][stage]='completed'
    store.mutate(run['run_id'],None,'fixture_interrupted',interrupted)
    source=store.get('run',run['run_id'])
    child=fd.derive_discussion_run(store,source,DeriveRequest(start_from='deliberation',
        expected_version=source['version'],rationale='Continue the discussion.'),'fixture')
    assert child['code_history']==[] and child['derived_from']['parent_code_history']==HISTORY
