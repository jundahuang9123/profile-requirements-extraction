"""Synthetic tests of the task cases added in rq1-fa-dialogue-v5 (kept in v6): no evaluation answers or live generation."""
import json
import pytest
from test_routed_stakeholder_workflow import setup  # noqa: F401  (pytest fixture)
from test_base_review import prepared
from test_fa_dialogue_v3 import Mediator, opted_in, retain_all, case_of
from requirement_reuse_service.workflow import fa_discussion as fd
from requirement_reuse_service.llm.client import LLMError, OutputValidationError


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
    assert cases[0]['discussion_trace']['group_rationale']=='Same task label (rq1-fa-task-labels-v2).'
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
        f'Same task label (rq1-fa-task-labels-v2); part {i} of 3.' for i in (1,2,3)]
    assert sorted(r for c in cases for r in c['revision_ids'])==sorted(r['revision_id'] for r in run['requirements'])


def test_needs_still_unlabelled_after_the_correction_are_discussed_alone(setup):
    store,run=opted_in(setup,3);client=Labeller(lambda data:[('N1','Know the licence')])
    cases=fd.build_cases(store,run,[],client)
    # One correction names the needs without a label; the label given is kept.
    assert len(client.payloads)==2
    assert [len(c['revision_ids']) for c in cases]==[1,1,1]
    assert sorted(c['discussion_trace']['group_rationale'] for c in cases)==['Isolated for review after a labelling failure.']*2+[
        'No other need has this task label (rq1-fa-task-labels-v2).']
    saved=store.get('run',run['run_id'])['stakeholder_audit']['fa_task_labels:0']
    assert saved['fallback']=='2 of 3 needs stayed unlabelled after correction and are discussed alone.'
    assert [p['need'] for p in saved['attempts'][0]['problems']]==['N2','N3'] and saved['kept_attempt']==2


class Recorded(Labeller):
    """Also records the system prompt of every labelling call."""
    def __init__(self,label):super().__init__(label);self.systems=[]
    def generate_structured(self,*,user,output_model,system='',step=None,**kw):
        if output_model.__name__=='TaskLabels':self.systems.append(system)
        return super().generate_structured(user=user,output_model=output_model,system=system,step=step,**kw)


def test_repeated_and_stray_labels_are_repaired_without_a_correction(setup):
    store,run=opted_in(setup,3)
    client=Recorded(lambda data:[('N1','Know the licence'),('N1','know the  licence'),('N2','Know the access conditions'),
        ('N3','Know the licence'),('N9','A need that is not in this chunk')])
    cases=fd.build_cases(store,run,[],client)
    assert len(client.payloads)==1
    ordered=sorted(r['revision_id'] for r in run['requirements'])
    assert [c['revision_ids'] for c in cases]==[[ordered[0],ordered[2]],[ordered[1]]]
    saved=store.get('run',run['run_id'])['stakeholder_audit']['fa_task_labels:0']
    assert saved['fallback'] is None and saved['attempts'][0]['problems']==[]
    assert [r['kind'] for r in saved['attempts'][0]['repairs']]==['repeated_label_dropped','label_outside_chunk_dropped']


def test_different_labels_for_one_need_get_one_correction(setup):
    store,run=opted_in(setup,2)
    answers=iter([[('N1','Know the licence'),('N1','Know the rights'),('N2','Know the licence')],
        [('N1','Know the licence'),('N2','Know the licence')]])
    client=Recorded(lambda data:next(answers))
    cases=fd.build_cases(store,run,[],client)
    assert len(cases)==1 and len(cases[0]['revision_ids'])==2
    assert 'N1 has different labels (Know the licence; Know the rights): give it one.' in client.systems[1]
    assert 'Your previous answer was rejected: {' in client.systems[1]


class Rejecting(Labeller):
    """Answers the first `bad` labelling calls with an OutputValidationError carrying raw(wire) as its JSON."""
    def __init__(self,label,raw,bad):super().__init__(label);self.raw=raw;self.bad=bad
    def generate_structured(self,*,user,output_model,system='',step=None,**kw):
        if output_model.__name__=='TaskLabels' and self.bad:
            self.bad-=1;data=json.loads(user);self.payloads.append(data)
            raise OutputValidationError('TaskLabels',[{'loc':['labels'],'type':'too_long'}],'stop',parsed_payload=self.raw(data))
        return super().generate_structured(user=user,output_model=output_model,system=system,step=step,**kw)


def test_a_rejected_answer_is_checked_from_its_json_and_never_fails_the_stage(setup):
    # JRC run-a89957db: both generations of a 60-need chunk gave more labels than the contract allowed.
    store,run=opted_in(setup,3)
    raw=lambda data:{'labels':[{'need':a,'task':'Know the licence'} for a in data['needs']]+[{'need':'N1','task':'Know the licence'},
        {'need':'N2','task':'x'*200}]}
    client=Rejecting(lambda data:[(a,'Know the licence') for a in data['needs']],raw,bad=2)
    cases=fd.build_cases(store,run,[],client)
    assert len(client.payloads)==2 and len(cases)==1 and len(cases[0]['revision_ids'])==3
    saved=store.get('run',run['run_id'])['stakeholder_audit']['fa_task_labels:0']
    first=saved['attempts'][0]
    assert first['error'].startswith('OutputValidationError') and first['problems']==[] and saved['fallback'] is None
    assert [r['kind'] for r in first['repairs']]==['invalid_label_dropped','repeated_label_dropped']


def test_a_chunk_with_nothing_parseable_gets_one_correction_then_single_cases(setup):
    store,run=opted_in(setup,2)
    cases=fd.build_cases(store,run,[],Rejecting(lambda data:[],lambda data:None,bad=4))
    assert [len(c['revision_ids']) for c in cases]==[1,1]
    assert store.get('run',run['run_id'])['stakeholder_audit']['fa_task_labels:0']['fallback']=='2 of 2 needs stayed unlabelled after correction and are discussed alone.'


def test_a_provider_failure_still_stops_the_labelling_for_resume(setup):
    store,run=opted_in(setup,2)
    class Down(Labeller):
        def generate_structured(self,*,user,output_model,**kw):
            if output_model.__name__=='TaskLabels':raise LLMError('scripted connection failure')
            return super().generate_structured(user=user,output_model=output_model,**kw)
    with pytest.raises(LLMError,match='scripted connection failure'):fd.build_cases(store,run,[],Down(lambda data:[]))
    assert 'fa_task_labels:0' not in store.get('run',run['run_id'])['stakeholder_audit']


def test_labels_saved_under_v1_are_refused_by_name(setup):
    store,run=opted_in(setup,2)
    from requirement_reuse_service.workflow import stakeholder_workflow as old
    old.save(store,run['run_id'],'fa_task_labels:0',{'input_hash':'x','policy_version':'rq1-fa-task-labels-v1','labels':{}})
    with pytest.raises(ValueError,match='Task labels were saved under rq1-fa-task-labels-v1'):
        fd.build_cases(store,store.get('run',run['run_id']),[],Labeller(lambda data:[]))


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
