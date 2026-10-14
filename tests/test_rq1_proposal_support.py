import json
from test_resume_discussions import setup
from test_rq1_need_grouping import need_inputs, NeedsClient
from requirement_reuse_service.workflow import engine, needs
from requirement_reuse_service.workflow.models import Observation, EvidenceLink
from requirement_reuse_service.workflow.models import RestoreRequest
from requirement_reuse_service.workflow.models import RunRequest
from requirement_reuse_service.llm.client import validate_json_payload
from test_rq1_need_assessment import FullNeedsClient


class QuoteClient(NeedsClient):
    def generate_structured(self, **kwargs):
        if kwargs['output_model'].__name__ != 'ProposalSupport': return super().generate_structured(**kwargs)
        data=json.loads(kwargs['user']);self.calls.append(('ProposalSupport',data))
        return kwargs['output_model'].model_validate({'proposals':[{'proposal_id':identifier,
            'support':'not_supported' if self.mode=='unrelated' else 'supported',
            'supporting_evidence_ids':[] if self.mode=='unrelated' else list(row['excerpts'])[:1],
            'obligation_stated':False,'rationale':'Offline controlled support judgement.'}
            for identifier,row in data['proposals'].items()]})


def test_unrelated_quote_is_set_aside_and_unstated_label_becomes_unknown(setup):
    store,run,records=need_inputs(setup)
    kept=needs.check_proposal_support(store,run,records,QuoteClient('unrelated'))
    assert kept==[]
    assert all(r.normalized_intent.obligation_hint=='unknown' for r in records)
    assert all(r.unbacked_obligation.reason=='quote_does_not_state_it' for r in records)
    assert all(a['reason']=='not_supported_by_quote' for a in store.get('run',run['run_id'])['set_aside_observations'])


def test_unchecked_support_preserves_authentic_quotes_source_gate_and_review_flag(setup):
    store,original,_=setup
    class InvalidSupport(FullNeedsClient):
        def generate_structured(self, **kw):
            answer=super().generate_structured(**kw)
            if kw['output_model'].__name__=='ProposalSupport':
                raw=answer.model_dump(mode='json')
                for row in raw['proposals']: row['proposal_id']=None
                return validate_json_payload(json.dumps(raw),kw['output_model'])
            return answer
    client=InvalidSupport()
    run=engine.new_run(store,RunRequest(snapshot_id=original['snapshot_id'],strategy='multi_agent',
        base_check=False,scoping='off',discussion='on_request',
        role_ids=['consumer_discovery','publisher_feasibility']))
    engine.execute_run(store,run['run_id'],client)
    saved=store.get('run',run['run_id'])
    assert saved['status']=='awaiting_human',saved['diagnostics']
    assert sum(name=='ProposalSupport' for name,_ in client.calls)==2
    [need]=[r for r in saved['requirements'] if r['revision_id'] in saved['active_revision_ids']]
    members=[r for r in saved['requirements'] if r['revision_id'] in need['parent_revision_ids']]
    assert len(members)==6 and all(r['proposal_support']['support']=='not_checked' for r in members)
    authentic={l['quote'] for r in members for l in r['evidence_links'] if l['relation']=='supports'}
    assert authentic and {l['quote'] for l in need['evidence_links']}==authentic
    assert need['verification']['status']=='pass'
    assert all(l['status']=='pass' for l in need['verification']['links'])
    assert 'support_not_checked' in need['processing_flags']
    assert need['rank_keys']['supporting_documents']==1 and need['rank']==1
    assert need['lifecycle_state']=='awaiting_human'
    assert saved['decisions']==[]


def test_unchecked_support_never_promotes_contradicting_links(setup):
    _,_,records=need_inputs(setup)
    record=records[0]; original=list(record.evidence_links)
    record.evidence_links.append(original[0].model_copy(update={'relation':'contradicts'}))
    record.proposal_support={'support':'not_checked','supporting_evidence_ids':[]}
    assert needs.supporting_links(record)==[l for l in original if l.relation=='supports']


def test_union_contains_selected_quotes_only_and_batch_size_is_25(setup):
    store,run,originals=need_inputs(setup);records=[]
    for i in range(51):
        row=engine.record_from_observation(run['run_id'],Observation(observation_id=f'quote-{i}',role_id='test',
            statement='Users can identify the title.',evidence_links=originals[i%2].evidence_links,
            intent={**originals[0].normalized_intent.model_dump(),'obligation_hint':'unknown'}))
        row.verification=engine.verify(store,row,run['evidence_ids']);records.append(row)
    client=QuoteClient();kept=needs.check_proposal_support(store,run,records,client)
    assert len(kept)==51 and [len(data['proposals']) for name,data in client.calls]==[25,25,1]
    # Two authentic, different quotes are on this member. Only the selected one
    # enters its rewritten need; the original member keeps both for the audit.
    member=records[0];extra=next(store.get('evidence',i) for i in run['evidence_ids'] if store.get('evidence',i)['content'] != member.evidence_links[0].quote)
    member.evidence_links.append(EvidenceLink(evidence_id=extra['evidence_id'],quote=extra['content']))
    member.proposal_support['supporting_evidence_ids']=[needs.excerpt_id(member.evidence_links[0])]
    needs.refresh_need(member);member.verification=engine.verify(store,member,run['evidence_ids'])
    output,_=needs.write_needs(store,run,[[member]],NeedsClient(),None)
    assert {l.quote for l in output[0].evidence_links}=={member.evidence_links[0].quote}
    assert len({l.quote for l in member.evidence_links})==2


def test_unsupported_proposals_receive_no_writer_or_rank_and_restore_unaccepted(setup):
    store,run,records=need_inputs(setup);client=QuoteClient('unrelated')
    active,_,_=needs.process_needs(store,run,records,client,None)
    assert active==[] and all(r.rank is None for r in records)
    assert all(name=='ProposalSupport' for name,_ in client.calls)
    store.mutate(run['run_id'],None,'offline-terminal',lambda r:r.update(status='awaiting_human'))
    saved=store.get('run',run['run_id']);item=saved['set_aside_observations'][0]
    restored=needs.restore_need(store,run['run_id'],RestoreRequest(expected_version=saved['version'],
        idempotency_key='restore-unsupported',observation_id=item['observation_id'],need_id=item['need_id'],
        reason=item['reason'],rationale='Offline reviewer needs to repair the support.'),'offline-reviewer')['run']
    row=next(r for r in restored['requirements'] if r['revision_id'] in restored['active_revision_ids'])
    assert row['lifecycle_state']=='blocked_support' and row['qualification'] is None
