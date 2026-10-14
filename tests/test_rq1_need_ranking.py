from test_resume_discussions import setup
from test_rq1_need_grouping import need_inputs, NeedsClient
from requirement_reuse_service.workflow import needs
from requirement_reuse_service.workflow.models import Qualification


def test_deterministic_rank_and_id_tie_break(setup):
    store,run,candidates=need_inputs(setup)
    originals,_=needs.write_needs(store,run,[candidates],NeedsClient(),None)
    records=[]
    for identifier,support,roles,links in [('z','inferred',4,5),('b','explicit',1,0),('a','explicit',1,0),('c','explicit',2,0)]:
        n=originals[0].model_copy(deep=True);n.requirement_id=identifier
        n.qualification=Qualification(support=support,rationale='Scripted',assessor='scripted')
        n.contributing_roles=[str(i) for i in range(roles)];n.supports_user_tasks=[str(i) for i in range(links)]
        records.append(n)
    ordered=needs.rank_needs(store,run,records)
    assert [n.requirement_id for n in ordered]==['c','a','b','z']
    assert [n.rank for n in ordered]==[1,2,3,4]
    assert [n.requirement_id for n in needs.rank_needs(store,run,list(reversed(records)))]==['c','a','b','z']
