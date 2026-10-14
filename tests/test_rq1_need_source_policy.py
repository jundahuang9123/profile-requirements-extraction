from test_resume_discussions import setup
from test_rq1_need_grouping import need_inputs
from requirement_reuse_service.workflow import engine, needs
from requirement_reuse_service.workflow.models import Observation


def without_obligation(run, record, quote=None):
    links=[l.model_copy(deep=True) for l in record.evidence_links if l.component=='statement']
    if quote is not None: links[0].quote=quote
    return engine.record_from_observation(run['run_id'], Observation(observation_id='unquoted',role_id='test',
        statement=record.raw_statement,intent=record.normalized_intent,evidence_links=links))


def test_needs_unquoted_obligation_is_unknown_but_candidate_policy_still_fails(setup):
    store,run,records=need_inputs(setup)
    candidate=without_obligation(run,records[0])
    assert engine.verify(store,candidate,run['evidence_ids'])['status']=='fail'
    candidate.verification=engine.verify(store,candidate,run['evidence_ids'],policy_version='rq1-original-source-v2.2')
    assert candidate.verification['status']=='pass'
    assert candidate.normalized_intent.obligation_hint=='unknown'
    assert candidate.unbacked_obligation.model_dump()=={'label':'mandatory','reason':'no_quote'}
    assert needs.obligation_summary([candidate])[0]=='unknown'
    assert engine.verify(store,candidate,run['evidence_ids'])['status']=='pass'


def test_needs_policy_never_repairs_a_missing_or_invented_quote(setup):
    store,run,records=need_inputs(setup)
    candidate=without_obligation(run,records[0],quote='This quotation was never in the source.')
    check=engine.verify(store,candidate,run['evidence_ids'],policy_version='rq1-original-source-v2.2')
    assert check['status']=='fail' and not check['component_checks']['statement_premise']
    assert any(l['status']=='fail' for l in check['links'])
