import json
from test_resume_discussions import setup
from test_rq1_need_grouping import need_inputs, NeedsClient
from requirement_reuse_service.workflow import engine, needs
from requirement_reuse_service.workflow.models import Observation, EvidenceLink


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
