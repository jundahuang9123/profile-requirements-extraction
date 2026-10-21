"""Synthetic tests of the task cases added in rq1-fa-dialogue-v5 (kept in v6): no evaluation answers or live generation."""
import json
import pytest
from test_routed_stakeholder_workflow import setup  # noqa: F401  (pytest fixture)
from test_base_review import prepared
from test_fa_dialogue_v3 import Mediator, opted_in, retain_all, case_of
from requirement_reuse_service.workflow import fa_discussion as fd


class Labeller(Mediator):
    """Scripted roles and plans; task labels from label(payload) -> [(alias, task)]."""
    def __init__(self,label):super().__init__(retain_all);self.label=label;self.payloads=[]
    def generate_structured(self,*,user,output_model,system='',step=None,**kw):
        if output_model.__name__=='TaskLabels':
            data=json.loads(user);self.payloads.append(data)
            return output_model.model_validate({'labels':[{'need':a,'task':t} for a,t in self.label(data)]})
        return super().generate_structured(user=user,output_model=output_model,system=system,step=step,**kw)


def by_parity(data):
    # Alternating tasks; later chunks write the known labels in other case and spacing, as models do.
    names=['know the licence','KNOW THE ACCESS CONDITIONS'] if data['known_tasks'] else ['Know the  licence','Know the access conditions']
    return [(a,names[i%2]) for i,a in enumerate(data['needs'])]


def test_needs_with_one_task_share_a_case_across_label_chunks(setup,monkeypatch):
    monkeypatch.setattr(fd,'TASK_LABEL_CHUNK',2)
    store,run=opted_in(setup,5);client=Labeller(by_parity)
    cases=fd.build_cases(store,run,[],client)
    # Three chunks; each later chunk sees the labels given so far, once each.
    assert [sorted(p['needs']) for p in client.payloads]==[['N1','N2'],['N1','N2'],['N1']]
    known=['Know the licence','Know the access conditions']
    assert [p['known_tasks'] for p in client.payloads]==[[],known,known]
    ordered=sorted(r['revision_id'] for r in run['requirements'])
    assert [c['revision_ids'] for c in cases]==[[ordered[0],ordered[2],ordered[4]],[ordered[1],ordered[3]]]
    assert [c['discussion_trace']['packet']['task'] for c in cases]==['Know the licence','Know the access conditions']
    assert cases[0]['discussion_trace']['group_rationale']=='Same task label (rq1-fa-task-labels-v1).'
    # Each extra need adds its share to the case limits.
    assert (cases[0]['max_calls'],cases[0]['total_output_budget'],cases[0]['max_seconds'])==(18,144000,2400)
    audit=store.get('run',run['run_id'])['stakeholder_audit']
    assert [audit[f'fa_task_labels:{i}']['fallback'] for i in range(3)]==[None,None,None]
    # Resuming reuses the saved labels; a changed labelling prompt is refused.
    calls=len(client.payloads);fd.build_cases(store,store.get('run',run['run_id']),[],client);assert len(client.payloads)==calls
    monkeypatch.setattr(fd,'TASK_LABEL_SYSTEM',fd.TASK_LABEL_SYSTEM+' changed')
    with pytest.raises(ValueError,match='Task labelling checkpoint mismatch'):fd.build_cases(store,store.get('run',run['run_id']),[],client)


def test_a_task_group_over_the_case_size_is_split_in_parts(setup,monkeypatch):
    monkeypatch.setattr(fd,'MAX_TASK_CASE',2)
    store,run=opted_in(setup,5)
    cases=fd.build_cases(store,run,[],Labeller(lambda data:[(a,'Know the licence') for a in data['needs']]))
    assert [len(c['revision_ids']) for c in cases]==[2,2,1]
    assert [c['discussion_trace']['group_rationale'] for c in cases]==[
        f'Same task label (rq1-fa-task-labels-v1); part {i} of 3.' for i in (1,2,3)]
    assert sorted(r for c in cases for r in c['revision_ids'])==sorted(r['revision_id'] for r in run['requirements'])


def test_an_invalid_labelling_leaves_its_needs_in_single_cases(setup):
    store,run=opted_in(setup,3)
    cases=fd.build_cases(store,run,[],Labeller(lambda data:[('N1','Know the licence')]))
    assert [len(c['revision_ids']) for c in cases]==[1,1,1]
    assert {c['discussion_trace']['group_rationale'] for c in cases}=={'Isolated for review after a labelling failure.'}
    assert store.get('run',run['run_id'])['stakeholder_audit']['fa_task_labels:0']['fallback']=='Task labelling did not label each need exactly once.'


def test_a_task_case_is_discussed_with_its_task(setup):
    store,run=opted_in(setup,3);client=Labeller(lambda data:[(a,'Know the licence') for a in data['needs']])
    fd.deliberate(store,run['run_id'],client)
    saved,case=case_of(store,run)
    assert len(saved['deliberations'])==1 and len(case['revision_ids'])==3
    assert case['stop_reason']=='bounded_fa_dialogue_complete'
    assert all('The needs of a case share the task in packet.task' in s for s in client.plan_systems)
    assert case['discussion_trace']['packet']['task']=='Know the licence'


def test_v5_packets_use_short_source_windows():
    # The quote with 300 characters on each side, within the unit.
    assert fd.excerpt_window(1000,50,5000,True)==(700,1350)
    assert fd.excerpt_window(100,50,260,True)==(0,260)
    # Earlier protocols keep 1,000 characters before and 4,000 in all.
    assert fd.excerpt_window(1000,50,5000,False)==(0,4000)
    assert fd.excerpt_window(2000,50,9000,False)==(1000,5000)


def test_a_legacy_v1_discussion_keeps_its_grouping_and_windows(setup):
    store,run,_=prepared(setup,2);client=Labeller(by_parity)
    cases=fd.build_cases(store,run,[],client)
    assert client.payloads==[] and 'TaskGroups' in [c for c in client.calls_by_model]
    assert all('task' not in c['discussion_trace']['packet'] for c in cases)
    assert all((c['max_calls'],c['total_output_budget'])==(14,112000) for c in cases)
