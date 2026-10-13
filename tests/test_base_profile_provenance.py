"""Base registry selection and exact-byte provenance are part of a trial."""
from test_resume_discussions import setup
from requirement_reuse_service.workflow import engine
from requirement_reuse_service.workflow.models import RunRequest, DeriveRequest
from pathlib import Path
from hashlib import sha256


def profile_hash(identifier):
    path=Path(__file__).resolve().parents[1]/'requirement-reuse-service/config/base_profiles'/f'{identifier}.json'
    return sha256(path.read_bytes()).hexdigest()


def test_case_defaults_are_explicit_and_other_versions_remain_unset(setup):
    _,run,_=setup
    request,metadata=engine.selected_base(RunRequest(snapshot_id=run['snapshot_id'],benchmark_case_id='mobilitydcat'))
    assert request.base_profile_id==metadata['base_profile_id']=='dcat-ap-2.0.1'
    assert metadata['base_profile_sha256']==profile_hash(request.base_profile_id)
    for case in ['healthdcat','geodcat','statdcat','jrc-research','epos']:
        selected,metadata=engine.selected_base(RunRequest(snapshot_id=run['snapshot_id'],benchmark_case_id=case))
        assert selected.base_profile_id is None and metadata=={}


def test_new_run_and_completed_stage_record_selected_base_hash(setup):
    store,source,_=setup
    run=engine.new_run(store,RunRequest(snapshot_id=source['snapshot_id'],base_profile_id='dcat-ap-2.0.1'))
    engine.execute_run(store,run['run_id'])
    saved=store.get('run',run['run_id'])
    assert saved['base_profile_sha256']==profile_hash('dcat-ap-2.0.1')
    assert saved['stage_results']['normalization']['base_profile_id']=='dcat-ap-2.0.1'
    assert saved['stage_results']['normalization']['base_profile_sha256']==saved['base_profile_sha256']


def test_derived_trial_adds_base_metadata_without_rewriting_older_extraction(setup):
    store,source,client=setup
    engine.execute_run(store,source['run_id'],client)
    before=store.get('run',source['run_id'])
    trial=engine.derive_run(store,source['run_id'],DeriveRequest(expected_version=before['version'],
        base_profile_id='dcat-ap-2.0.1',rationale='Offline base trial.'))
    assert trial['base_profile_id']=='dcat-ap-2.0.1'
    assert trial['elicitation_policy_version']==before['elicitation_policy_version']
    assert trial['stage_results']['elicitation']==before['stage_results']['elicitation']
    assert store.get('run',source['run_id'])==before
