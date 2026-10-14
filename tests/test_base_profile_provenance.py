"""Base registry selection and exact-byte provenance are part of a trial."""
from test_resume_discussions import setup
from requirement_reuse_service.workflow import engine
from requirement_reuse_service.workflow.models import RunRequest, DeriveRequest
from pathlib import Path
from hashlib import sha256
import pytest


def profile_hash(identifier):
    path=Path(__file__).resolve().parents[1]/'requirement-reuse-service/config/base_profiles'/f'{identifier}.json'
    return sha256(path.read_bytes()).hexdigest()


def test_case_defaults_are_explicit_and_other_versions_remain_unset(setup):
    _,run,_=setup
    request,metadata=engine.selected_base(RunRequest(output_form='candidates', snapshot_id=run['snapshot_id'],benchmark_case_id='mobilitydcat'))
    assert request.base_profile_id==metadata['base_profile_id']=='dcat-ap-2.0.1'
    assert metadata['base_profile_sha256']==profile_hash(request.base_profile_id)
    for case in ['healthdcat','geodcat','statdcat','jrc-research','epos']:
        selected,metadata=engine.selected_base(RunRequest(output_form='candidates', snapshot_id=run['snapshot_id'],benchmark_case_id=case))
        assert selected.base_profile_id is None and metadata=={}


@pytest.mark.parametrize('identifier', ['dcat-ap-3.0.0', 'dcat-ap-3.0.1', 'dcat-2.0.0', 'dcat-3.0.0'])
def test_explicit_version_overrides_mobility_default_and_is_pinned(setup, identifier):
    _, source, _ = setup
    selected, metadata = engine.selected_base(RunRequest(output_form='candidates', snapshot_id=source['snapshot_id'],
        benchmark_case_id='mobilitydcat', base_profile_id=identifier))
    assert selected.base_profile_id == metadata['base_profile_id'] == identifier
    assert metadata['base_profile_sha256'] == profile_hash(identifier)
    context = engine.extraction_base_context(identifier, metadata['base_profile_sha256'])
    assert context['id'] == identifier and context['sha256'] == profile_hash(identifier)
    if identifier.startswith('dcat-ap-'):
        assert 'obligation_policy' not in context and 'dct:title (mandatory)' in context['table']
    else:
        assert 'vocabulary' in context['obligation_policy'] and '(mandatory)' not in context['table']


@pytest.mark.parametrize('identifier', ['dcat-ap-3.0.1', 'dcat-3.0.0'])
def test_derived_version_change_preserves_saved_extraction_and_source_run(setup, identifier):
    store, source, client = setup
    engine.execute_run(store, source['run_id'], client)
    before = store.get('run', source['run_id'])
    trial = engine.derive_run(store, source['run_id'], DeriveRequest(output_form='candidates', expected_version=before['version'],
        base_profile_id=identifier, rationale='Compare a different pinned starting version.'))
    assert trial['base_profile_id'] == identifier
    assert trial['base_profile_sha256'] == profile_hash(identifier)
    assert trial['stage_results']['elicitation'] == before['stage_results']['elicitation']
    assert store.get('run', source['run_id']) == before


def test_new_run_and_completed_stage_record_selected_base_hash(setup):
    store,source,_=setup
    run=engine.new_run(store,RunRequest(output_form='candidates', snapshot_id=source['snapshot_id'],base_profile_id='dcat-ap-2.0.1'))
    engine.execute_run(store,run['run_id'])
    saved=store.get('run',run['run_id'])
    assert saved['base_profile_sha256']==profile_hash('dcat-ap-2.0.1')
    assert saved['stage_results']['normalization']['base_profile_id']=='dcat-ap-2.0.1'
    assert saved['stage_results']['normalization']['base_profile_sha256']==saved['base_profile_sha256']


def test_derived_trial_adds_base_metadata_without_rewriting_older_extraction(setup):
    store,source,client=setup
    engine.execute_run(store,source['run_id'],client)
    before=store.get('run',source['run_id'])
    trial=engine.derive_run(store,source['run_id'],DeriveRequest(output_form='candidates', expected_version=before['version'],
        base_profile_id='dcat-ap-2.0.1',rationale='Offline base trial.'))
    assert trial['base_profile_id']=='dcat-ap-2.0.1'
    assert trial['elicitation_policy_version']==before['elicitation_policy_version']
    assert trial['stage_results']['elicitation']==before['stage_results']['elicitation']
    assert store.get('run',source['run_id'])==before


def test_explicit_no_base_is_not_replaced_by_a_case_default(setup):
    _, source, _ = setup
    selected, metadata = engine.selected_base(RunRequest(output_form='candidates', snapshot_id=source['snapshot_id'],
        benchmark_case_id='mobilitydcat', base_profile_id=None))
    assert selected.base_profile_id is None and metadata == {}


def test_derived_ui_can_clear_the_source_base_and_case_without_rewriting_it(setup):
    store, initial, client = setup
    source = engine.new_run(store, RunRequest(output_form='candidates', snapshot_id=initial['snapshot_id'], strategy='multi_agent',
        role_ids=initial['request']['role_ids'], consolidation='exact', discussion='on_request',
        base_profile_id='dcat-ap-2.0.1'))
    engine.execute_run(store, source['run_id'], client)
    before = store.get('run', source['run_id'])
    trial = engine.derive_run(store, source['run_id'], DeriveRequest(output_form='candidates', expected_version=before['version'],
        base_profile_id=None, benchmark_case_id=None, rationale='Explicit custom trial without a base.'))
    assert trial['base_profile_id'] is None and trial['base_check_policy_version'] is None
    assert trial['request']['benchmark_case_id'] is None
    assert store.get('run', source['run_id']) == before


def test_new_case_on_a_derived_trial_uses_its_default_when_base_is_omitted(setup):
    store, source, client = setup
    engine.execute_run(store, source['run_id'], client)
    saved = store.get('run', source['run_id'])
    trial = engine.derive_run(store, source['run_id'], DeriveRequest(output_form='candidates', expected_version=saved['version'],
        benchmark_case_id='mobilitydcat', rationale='Explicit Mobility source context.'))
    assert trial['base_profile_id'] == 'dcat-ap-2.0.1'
    assert trial['request']['background_source_names'] == [
        'w3c-dcat-2-2020.html', 'dcat-ap-2.0.0.pdf', 'dcat-ap-2.1.0.pdf']
