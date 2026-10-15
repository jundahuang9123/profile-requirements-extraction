"""The single-analyst comparison condition: one neutral extraction role, unchanged later steps.

All generation is scripted and offline.
"""
from test_resume_discussions import setup  # noqa: F401  (pytest fixture)
from test_rq1_need_assessment import FullNeedsClient
from requirement_reuse_service.agents.roles import load_role_configuration
from requirement_reuse_service.workflow import engine
from requirement_reuse_service.workflow.models import RunRequest


def test_single_analyst_is_a_neutral_extraction_role_outside_every_preset():
    config = load_role_configuration()
    role = next(r for r in config['roles'] if r.id == 'single_analyst')
    assert role.phase == 'extraction' and role.enabled
    assert all('single_analyst' not in (preset.get('role_ids') or []) for preset in config['presets'].values())


def test_single_analyst_run_extracts_with_one_perspective(setup):
    store, original, _ = setup
    client = FullNeedsClient()
    run = engine.new_run(store, RunRequest(snapshot_id=original['snapshot_id'], strategy='multi_agent',
        role_selection='manual', role_ids=['single_analyst'], discussion='on_request', scoping='off'))
    assert [r['role_id'] for r in run['role_manifest']['selected_roles']] == ['single_analyst']
    engine.execute_run(store, run['run_id'], client)
    saved = store.get('run', run['run_id'])
    assert saved['status'] == 'awaiting_human', saved['diagnostics']
    assert [r['role_id'] for r in saved['role_runs']] == ['single_analyst']
    extraction = [data for name, data in client.calls if name == 'NeedSpanElicitationResult']
    assert extraction and all(data['role']['id'] == 'single_analyst' for data in extraction)
    assert all(data['stakeholder_perspective']['label'] == 'Single Analyst (comparison baseline)' for data in extraction)
    assert saved['active_revision_ids']
