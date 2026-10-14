from copy import deepcopy
import pytest
from test_resume_discussions import setup
from requirement_reuse_service.workflow import engine
from requirement_reuse_service.workflow.models import RunRequest,DeriveRequest


@pytest.mark.parametrize('strategy',['rules','mock'])
def test_offline_missing_output_completes_candidates_and_derives_safely(setup,strategy):
    store,source,client=setup
    run=engine.new_run(store,RunRequest(snapshot_id=source['snapshot_id'],strategy=strategy))
    assert run['request']['output_form']=='candidates'
    engine.execute_run(store,run['run_id'])
    saved=store.get('run',run['run_id'])
    assert saved['status']=='awaiting_human' and not saved['needs_policies']
    before=deepcopy(saved)
    trial=engine.derive_run(store,saved['run_id'],DeriveRequest(expected_version=saved['version'],rationale='Check omitted output.'))
    assert trial['request']['output_form']=='candidates'
    engine.execute_run(store,trial['run_id'])
    assert store.get('run',trial['run_id'])['status']=='awaiting_human'
    assert store.get('run',saved['run_id'])==before
    with pytest.raises(ValueError,match='Needs output requires'):
        engine.derive_run(store,saved['run_id'],DeriveRequest(expected_version=saved['version'],output_form='needs',rationale='Invalid offline needs.'))


@pytest.mark.parametrize('strategy',['rules','mock'])
def test_explicit_offline_needs_refused_before_run_creation(setup,strategy):
    store,source,_=setup
    count=len(store.list('run'))
    with pytest.raises(ValueError,match='Needs output requires'):
        engine.new_run(store,RunRequest(snapshot_id=source['snapshot_id'],strategy=strategy,output_form='needs'))
    assert len(store.list('run'))==count


def test_multi_agent_default_stays_needs():
    assert RunRequest(snapshot_id='fixture',strategy='multi_agent').output_form=='needs'
