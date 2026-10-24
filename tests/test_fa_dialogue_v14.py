"""Synthetic tests of the rule added in rq1-fa-dialogue-v14: no evaluation answers or live generation.

A stakeholder review sees each need of its case as N1, N2, … and, beside that alias, the need's requirement_id
("req-…"). In the 8 cases of the v8 and v13 runs that stopped for budget, 13 of the 32 review corrections were
for a role naming its need by that requirement ID and nothing else, all in the first round."""
import json
from test_routed_stakeholder_workflow import setup  # noqa: F401  (pytest fixture)
from test_fa_workflow import contract_name
from test_fa_dialogue_v3 import Mediator, opted_in, retain_all, case_of, built  # noqa: F401
from requirement_reuse_service.workflow import fa_discussion as fd


def test_policy_names():
    assert fd.BASE_POLICY=='rq1-fa-dialogue-v14' and 'rq1-fa-dialogue-v13' in fd.BASE_POLICIES


def review(*lists):
    return fd.Review.model_validate({'summary':'Checked.','concerns':[{'revision_ids':ids,'kind':'scope','statement':'Missing.'} for ids in lists]})


def requirement_ids(case):
    by_revision={r['revision_id']:r['requirement_id'] for r in case['frozen_requirements']}
    return [by_revision[r] for r in case['revision_ids']]


def test_a_need_named_by_its_requirement_id_gets_that_need_in_either_round(setup):
    case,(n1,n2),_,_=built(setup);r1,r2=requirement_ids(case)
    for draft in (None,{'actions':[{'action_id':'A1','parent_revision_ids':[n1]}]}):
        fixed,repairs=fd.repair_review(review([r1],[r2,n1],[n2,r2],['A1',r2]),case,draft)
        # A requirement ID beside its own need adds nothing; a draft reference is mapped as before.
        assert [c.revision_ids for c in fixed.concerns]==[[n1],[n2,n1],[n2],[n1,n2] if draft else ['A1',n2]]
        assert repairs[:3]==[{'kind':'concern_need_from_requirement_id','concern_index':0,'from':r1,'to':[n1]},
            {'kind':'concern_need_from_requirement_id','concern_index':1,'from':r2,'to':[n2]},
            {'kind':'concern_need_from_requirement_id','concern_index':2,'from':r2,'to':[n2]}]
        assert repairs[3:]==([{'kind':'concern_need_from_draft','concern_index':3,'from':'A1','to':[n1]},
            {'kind':'concern_need_from_requirement_id','concern_index':3,'from':r2,'to':[n2]}] if draft else
            [{'kind':'concern_need_from_requirement_id','concern_index':3,'from':r2,'to':[n2]}])


def test_a_requirement_id_outside_the_case_or_shared_by_two_of_its_needs_is_not_mapped(setup):
    case,(n1,n2),_,_=built(setup);r1,r2=requirement_ids(case)
    # A requirement ID of no need of the case stays for correction.
    assert fd.repair_review(review(['req-000000000000000000000000']),case,None)==(review(['req-000000000000000000000000']),[])
    # Two revisions of one requirement in a case: its ID could mean either.
    shared={**case,'frozen_requirements':[{**r,'requirement_id':r1} for r in case['frozen_requirements']]}
    assert fd.repair_review(review([r1]),shared,None)==(review([r1]),[])
    # A requirement whose revision is not a need of the case is not mapped.
    narrowed={**case,'revision_ids':[n1]}
    assert fd.repair_review(review([r2]),narrowed,None)==(review([r2]),[])


def test_a_claim_naming_a_need_by_its_requirement_id_gets_that_need(setup):
    # In the budget-stopped cases, most first reviews named the need by its requirement ID in a claim as well.
    case,(n1,n2),_,_=built(setup);r1,r2=requirement_ids(case)
    answer=fd.ExperienceReview(summary='s',concerns=[{'revision_ids':[r1],'kind':'scope','statement':'Missing.'}],
        experience=[{'kind':'drop','revision_ids':[r2],'task':'t','experience':'e','claim':'c'}])
    fixed,repairs=fd.repair_review(answer,case,None)
    assert isinstance(fixed,fd.ExperienceReview) and fixed.concerns[0].revision_ids==[n1] and fixed.experience[0].revision_ids==[n2]
    assert repairs==[{'kind':'concern_need_from_requirement_id','concern_index':0,'from':r1,'to':[n1]},
        {'kind':'experience_need_from_requirement_id','experience_index':0,'from':r2,'to':[n2]}]


class NamesRequirementId(Mediator):
    """In its first review, the first concern names the first need by its requirement ID, the ID the packet shows
    beside the alias N1."""
    def generate_structured(self,*,user,output_model,system='',step=None,**kw):
        answer=super().generate_structured(user=user,output_model=output_model,system=system,step=step,**kw)
        data=json.loads(user)
        if contract_name(output_model)!='Review' or data.get('draft'):return answer
        raw=answer.model_dump(mode='json')
        raw['concerns'][0]['revision_ids']=[data['packet']['needs'][0]['requirement_id']]
        return output_model.model_validate(raw)


def test_a_first_review_naming_a_need_by_its_requirement_id_needs_no_correction(setup):
    store,run=opted_in(setup);fd.deliberate(store,run['run_id'],NamesRequirementId(retain_all))
    saved,case=case_of(store,run);n1=case['revision_ids'][0];r1=requirement_ids(case)[0]
    assert case['stop_reason']=='bounded_fa_dialogue_complete'
    initial=[v for k,v in case['discussion_trace']['phases'].items() if k.startswith('initial:')]
    assert len(initial)==2
    for phase in initial:
        [first]=phase['attempts']
        assert first['errors']==[] and first['model_output']['concerns'][0]['revision_ids']==[r1]
        assert first['output']['concerns'][0]['revision_ids']==[n1]
        assert first['repairs']==[{'kind':'concern_need_from_requirement_id','concern_index':0,'from':r1,'to':[n1]}]
    assert all(m['concerns'][0]['revision_ids']==[n1] for m in case['messages'] if m['round']==1)
