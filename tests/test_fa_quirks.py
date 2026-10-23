"""Whole discussion cases against the answer habits gpt-oss showed in live runs, not ideal answers.

Each scripted step below copies a shape seen in a saved live run (JRC run-a89957db, run-0ebfaffd,
run-4d980b17, run-efc543e4, run-12a2c91a, run-0834b623, run-36730b38; Stat run-6455e495, run-c4cbca44,
run-1428af21, run-d069be4d, run-289823d2). Every case
must end in a defined state, keep or
account for every need, apply only what the rules allow, and leave a record that validates. No
evaluation answers or live generation.
"""
import json
import pytest
from test_routed_stakeholder_workflow import setup  # noqa: F401  (pytest fixture)
from test_fa_workflow import contract_name
from test_fa_dialogue_v3 import Assessing, opted_in, ids, case_of, sourced
from requirement_reuse_service.models import ArtifactPayload
from requirement_reuse_service.workflow import engine, fa_discussion as fd
from requirement_reuse_service.workflow.evidence import register_source
from requirement_reuse_service.workflow.models import WorkflowRun, SourceRequest, SnapshotRequest, RunRequest
from requirement_reuse_service.workflow.storage import Store

STOPS={'bounded_fa_dialogue_complete','bounded_fa_dialogue_salvaged','invalid_output_pending_human_review','budget_pending_human_review'}
LICENCE,HOLDER='Users can find the licence of a dataset.','Users can find the rights holder of a dataset.'


def sound(store,run):
    """The invariants every discussion case keeps, whatever the models answered."""
    saved,case=case_of(store,run)
    assert case['status']=='mediated' and case['stop_reason'] in STOPS
    WorkflowRun.model_validate(saved)
    active=set(saved['active_revision_ids']);records={r['revision_id']:r for r in saved['requirements']}
    outcomes=case['mediation'].get('outcomes',[])
    for rid in case['revision_ids']:
        if rid in active:continue
        state=records[rid]['lifecycle_state']
        if state=='superseded':
            assert any(o.get('applied') and rid in o['parent_revision_ids'] and set(o.get('result_revision_ids',[]))<=active for o in outcomes)
        else:
            assert state=='set_aside' and any(a['revision_id']==rid for a in saved['set_aside_observations'])
    for o in outcomes:
        if o.get('applied') and o['action']=='set_aside':assert o.get('reason') in fd.SET_ASIDE_REASONS and not o.get('scope_conflict')
        if o.get('status')=='machine_revised':assert set(o['result_revision_ids'])<=active
    assert saved['metrics']['mediated_changes']==sum(o.get('applied',False) for c in saved['deliberations']
        for o in c.get('mediation',{}).get('outcomes',[]))
    return saved,case


# Plans as the mediator wrote them live, for a case of two needs N1, N2.
def named_split(data,*_):
    needs,_=ids(data);cited=sourced(data)
    return {'actions':[{'action_id':'A1','action':'retain','parent_revision_ids':[needs[0]],'rationale':'Kept.'},
        {'action_id':'A2','action':'split','parent_revision_ids':[needs[1]],'rationale':'Two needs.','children':[
            {'action_id':'A2c1','statement':LICENCE,'evidence_links':cited,'rationale':'One.'},
            {'action_id':'A2c2','statement':HOLDER,'evidence_links':cited,'rationale':'Two.'}]}],'concerns':[],'questions':[],'summary':'s'}


def unnamed_split(data,*_):
    plan=named_split(data)
    for c in plan['actions'][1]['children']:c.pop('action_id')
    return plan


def two_retains(data,*_):
    needs,_=ids(data);cited=sourced(data)
    return {'actions':[{'action_id':'A1','action':'retain','parent_revision_ids':[needs[0]],'rationale':'Kept.'},
        {'action_id':'A2','action':'retain','parent_revision_ids':[needs[1]],'statement':LICENCE,'evidence_links':cited,'rationale':'One.'},
        {'action_id':'A3','action':'retain','parent_revision_ids':[needs[1]],'statement':HOLDER,'evidence_links':cited,'rationale':'Two.'}],
        'concerns':[],'questions':[],'summary':'s'}


def split_and_broken_revise(data,*_):
    """N1 split, N2 revised without a source: salvage keeps the split and defers N2."""
    needs,_=ids(data);cited=sourced(data)
    return {'actions':[{'action_id':'A1','action':'split','parent_revision_ids':[needs[0]],'rationale':'Two needs.','children':[
            {'statement':LICENCE,'evidence_links':cited,'rationale':'One.'},{'statement':HOLDER,'evidence_links':cited,'rationale':'Two.'}]},
        {'action_id':'A2','action':'revise','parent_revision_ids':[needs[1]],'rationale':'Narrow it.'}],'concerns':[],'questions':[],'summary':'s'}


class Habits(Assessing):
    """Scripted roles and mediator; the checker answers in one of the habits seen live."""
    def __init__(self,plans,checker):super().__init__(plans);self.checker=checker;self.check_calls=0
    def generate_structured(self,*,user,output_model,system='',step=None,**kw):
        answer=super().generate_structured(user=user,output_model=output_model,system=system,step=step,**kw)
        if contract_name(output_model)!='Checks':return answer
        self.check_calls+=1;rows=answer.model_dump(mode='json')['checks'];plan=json.loads(user)['plan']
        kids=[c['action_id'] for a in plan['actions'] for c in a.get('children') or []]
        one=lambda i:{**rows[0],'action_id':i}
        if self.checker=='children':rows=rows+[one(i) for i in kids]
        elif self.checker=='children_only_first' and self.check_calls==1:
            splits={a['action_id'] for a in plan['actions'] if a.get('children')}
            rows=[r for r in rows if r['action_id'] not in splits]+[one(i) for i in kids]
        elif self.checker=='action_types':rows=[{**r,'action_id':a['action']} for r,a in zip(rows,plan['actions'])]
        return output_model.model_validate({'checks':rows})


@pytest.mark.parametrize('checker',['ideal','children','children_only_first'])
@pytest.mark.parametrize('plans',[named_split,unnamed_split,two_retains,split_and_broken_revise])
def test_a_split_survives_the_checker_habits(setup,plans,checker):
    store,run=opted_in(setup);fd.deliberate(store,run['run_id'],Habits(plans,checker))
    saved,case=sound(store,run)
    assert case['stop_reason']==('bounded_fa_dialogue_salvaged' if plans is split_and_broken_revise else 'bounded_fa_dialogue_complete')
    split=next(o for o in case['mediation']['outcomes'] if o['action']=='split')
    assert split['status']=='machine_revised' and len(split['result_revision_ids'])==2


def test_checks_named_after_action_types_leave_the_needs_as_they_were(setup):
    store,run=opted_in(setup);before=list(run['active_revision_ids'])
    fd.deliberate(store,run['run_id'],Habits(named_split,'action_types'))
    saved,case=sound(store,run)
    assert case['stop_reason']=='invalid_output_pending_human_review' and saved['active_revision_ids']==before


# Mediator habits from the saved v6-v9 plans, each repeated in both attempts (the worst case).
def per_concern(data,*_):
    needs,concerns=ids(data)
    return {'actions':[{'action_id':f'A{i+1}','action':'retain','parent_revision_ids':[],'rationale':'Answers a concern.'} for i in range(3)],
        'concerns':[{'concern_id':c,'status':'addressed','action_ids':['A1'],'rationale':'r'} for c in concerns],'questions':[],'summary':'s'}


def invented_ids(data,*_):
    needs,_=ids(data)
    return {'actions':[{'action_id':'A1','action':'retain','parent_revision_ids':['N_access'],'rationale':'r'},
        {'action_id':'A2','action':'retain','parent_revision_ids':[needs[1]],'rationale':'r'}],'concerns':[],'questions':[
        {'question_id':'Q1','revision_ids':['N_download'],'concern_ids':[],'question':'?','alternatives':[],'rationale':'r'}],'summary':'s'}


def adds_naming_the_need(data,*_):
    needs,_=ids(data);cited=sourced(data)
    return {'actions':[{'action_id':'A1','action':'retain','parent_revision_ids':[needs[0]],'rationale':'r'},
        {'action_id':'A2','action':'add','parent_revision_ids':[needs[1]],'statement':LICENCE,'evidence_links':cited,'rationale':'r'},
        {'action_id':'A3','action':'add','parent_revision_ids':[needs[1]],'statement':HOLDER,'evidence_links':cited,'rationale':'r'}],
        'concerns':[],'questions':[],'summary':'s'}


def retain_and_set_aside(data,*_):
    needs,_=ids(data)
    return {'actions':[{'action_id':'A1','action':'retain','parent_revision_ids':[needs[0]],'rationale':'r'},
        {'action_id':'A2','action':'retain','parent_revision_ids':[needs[1]],'rationale':'r'},
        {'action_id':'A3','action':'set_aside','parent_revision_ids':[needs[1]],'rationale':'No obligation.','human_question':'Restore?',
         'reason':'not_find_or_access'}],'concerns':[],'questions':[],'summary':'s'}


def loose_set_asides(data,*_):
    needs,_=ids(data)
    return {'actions':[{'action_id':'A1','action':'retain','parent_revision_ids':[needs[0]],'rationale':'r','reason':'duplicate'},
        {'action_id':'A2','action':'set_aside','parent_revision_ids':[needs[1]],'rationale':'The source states no obligation.',
         'reason':'duplicate','duplicate_of':'rev-elsewhere'}],'concerns':[],'questions':[],'summary':'s'}


def oversized_split(data,*_):
    needs,_=ids(data);cited=sourced(data)
    return {'actions':[{'action_id':'A1','action':'retain','parent_revision_ids':[needs[0]],'rationale':'r'},
        {'action_id':'A2','action':'split','parent_revision_ids':[needs[1]],'rationale':'r','children':[
            {'statement':f'Users can find part {k} of the access conditions.','evidence_links':cited,'rationale':'r'} for k in range(5)]}],
        'concerns':[],'questions':[{'question_id':'Q1','revision_ids':[needs[1]],'concern_ids':[],'question':'?','alternatives':[],'rationale':'r'}],
        'summary':'s'}


MEDIATOR_HABITS=[per_concern,invented_ids,adds_naming_the_need,retain_and_set_aside,loose_set_asides,oversized_split,
    two_retains,unnamed_split,split_and_broken_revise]


@pytest.mark.parametrize('checker',['ideal','children'])
@pytest.mark.parametrize('plans',MEDIATOR_HABITS)
def test_every_case_ends_sound_under_the_mediator_habits(setup,plans,checker):
    store,run=opted_in(setup);fd.deliberate(store,run['run_id'],Habits(plans,checker));sound(store,run)


def test_a_set_aside_against_the_scope_stays_with_a_person_under_every_checker_habit(setup):
    store,run=opted_in(setup)
    rid=sorted(r['revision_id'] for r in run['requirements'])[1]
    def scope(r):
        next(x for x in r['requirements'] if x['revision_id']==rid)['fa_scope']={'policy_version':'rq1-find-access-v1','status':'checked',
            'serves':'find','nature':'information_requirement','support':'explicit'}
    store.mutate(run['run_id'],None,'fixture_scope',scope)
    def plans(data,*_):
        needs,_=ids(data)
        return {'actions':[{'action_id':'A1','action':'retain','parent_revision_ids':[needs[0]],'rationale':'r'},
            {'action_id':'A2','action':'set_aside','parent_revision_ids':[needs[1]],'rationale':'Only one word in the source.',
             'human_question':'Restore?','reason':'not_find_or_access'}],'concerns':[],'questions':[],'summary':'s'}
    fd.deliberate(store,run['run_id'],Habits(plans,'children'))
    saved,case=sound(store,run)
    assert rid in saved['active_revision_ids'] and next(o for o in case['mediation']['outcomes'] if o['action_id']=='A2')['status']=='human_review'


class RoleHabits(Habits):
    """Roles that write a claim kind as a concern kind, one evidence ID as a string, a keep claim and a second claim."""
    def generate_structured(self,*,user,output_model,system='',step=None,**kw):
        answer=super().generate_structured(user=user,output_model=output_model,system=system,step=step,**kw)
        if contract_name(output_model)!='Review':return answer
        data=json.loads(user);need=data['packet']['needs'][0]['revision_id'];source=data['packet']['excerpts'][0]['evidence_id']
        claim={'revision_ids':[need],'task':'Find data','experience':'When I search, I filter by each part.','claim':'Change it.'}
        return output_model.model_validate({**answer.model_dump(mode='json'),
            'concerns':[{'revision_ids':[need],'kind':'split','statement':'Two needs.','evidence_ids':source},
                {'revision_ids':[need],'kind':'scope','statement':'A condition is missing.','evidence_ids':source}],
            'experience':[{**claim,'kind':'keep'},{**claim,'kind':'split'}]})


@pytest.mark.parametrize('plans',[named_split,two_retains,per_concern])
def test_every_case_ends_sound_under_the_role_habits(setup,plans):
    store,run=opted_in(setup);client=RoleHabits(plans,'children');fd.deliberate(store,run['run_id'],client)
    saved,case=sound(store,run)
    # The reviews are kept without the broken parts; nothing invalid is saved.
    for m in case['messages']:
        assert all(c['kind'] in fd.CONCERN_KINDS for c in m['concerns']) and all(x['kind'] in fd.CLAIM_KINDS for x in m.get('experience',[]))
        assert len(m.get('experience',[]))<=1


# Quotations as the mediator wrote them in JRC run-efc543e4 (v10): a line break of the source written as a
# space, and 'platform-independent' written with U+2011 where the PDF text breaks the line after the hyphen.
WRAPPED=('<p>Users can find the access conditions\nfor a dataset in an accepted, platform-\n   independent format.</p>'
    '<p>Publishers can find the contact details\nfor a dataset.</p>')
ACCESS='Users can find the access conditions for a dataset in an accepted, platform\u2011independent format.'


@pytest.fixture
def wrapped(tmp_path,monkeypatch):
    """The setup fixture with one HTML source whose lines wrap, as the PDF and HTML units of the live runs do."""
    monkeypatch.setenv('RQ1_WORKFLOW_STORE',str(tmp_path/'workflow.sqlite3'));monkeypatch.setenv('RRS_LLM_PROVIDER','disabled')
    monkeypatch.setattr(engine,'freeze_step_models',lambda request:request)
    store=Store()
    source=register_source(store,SourceRequest(artifact=ArtifactPayload(name='wrapped.html',content=WRAPPED),source_role='stakeholder_need'))
    snap=engine.freeze_snapshot(store,SnapshotRequest(source_version_ids=[source['source_version_id']]))
    run=engine.new_run(store,RunRequest(snapshot_id=snap['snapshot_id'],strategy='multi_agent',output_form='needs',
        role_ids=['consumer_discovery','publisher_feasibility'],stakeholder_workflow='routed_mediated',
        base_check=False,discussion='automatic',scoping='off'))
    units=[store.get('evidence',e) for e in run['evidence_ids']]
    assert len(units)==1 and 'platform-\nindependent' in units[0]['content']
    return store,run,units,engine.roles_for(RunRequest.model_validate(run['request']))


def quoting(*quotes):
    """A revise of N1 and a split of N2 whose sources are the given quotations of the one unit."""
    def plans(data,*_):
        needs,_=ids(data);ev=data['packet']['excerpts'][0]['evidence_id'];link=lambda q:[{'evidence_id':ev,'quote':q}]
        return {'actions':[{'action_id':'A1','action':'revise','parent_revision_ids':[needs[0]],
                'statement':'Users can find the access conditions of a dataset.','evidence_links':link(quotes[0]),'rationale':'Narrower.'},
            {'action_id':'A2','action':'split','parent_revision_ids':[needs[1]],'rationale':'Two needs.','children':[
                {'action_id':'A2.1','statement':LICENCE,'evidence_links':link(quotes[1]),'rationale':'One.'},
                {'action_id':'A2.2','statement':HOLDER,'evidence_links':link(quotes[2]),'rationale':'Two.'}]}],
            'concerns':[],'questions':[],'summary':'s'}
    return plans


@pytest.mark.parametrize('access',[ACCESS,ACCESS.replace('platform\u2011independent','platform- independent')])
@pytest.mark.parametrize('checker',['ideal','children'])
def test_quotations_that_differ_only_in_whitespace_or_hyphenation_are_applied_with_the_exact_text(wrapped,checker,access):
    store,run=opted_in(wrapped)
    plans=quoting(access,'Users can find the access conditions for a dataset','Publishers can find the contact details for a dataset.')
    fd.deliberate(store,run['run_id'],Habits(plans,checker))
    saved,case=sound(store,run)
    assert case['stop_reason']=='bounded_fa_dialogue_complete'
    rows={o['action_id']:o for o in case['mediation']['outcomes']}
    assert rows['A1']['status']==rows['A2']['status']=='machine_revised' and len(rows['A2']['result_revision_ids'])==2
    assert {r['method'] for o in rows.values() for r in o['citation_repairs']}=={fd.QUOTE_MATCH_POLICY}
    content=store.get('evidence',run['evidence_ids'][0])['content'];records={r['revision_id']:r for r in saved['requirements']}
    new=[records[i] for o in rows.values() for i in o['result_revision_ids']]
    assert len(new)==3 and all(r['verification']['status']=='pass' for r in new)
    for r in new:
        link=r['evidence_links'][0];assert '\n' in link['quote'] and content[link['quote_start']:link['quote_start']+len(link['quote'])]==link['quote']
    assert sorted(r['action_id'] for o in rows.values() for r in o['citation_repairs'])==['A1','A2.1','A2.2']
    # The outcome rows keep the quotations as the mediator wrote them.
    assert rows['A1']['evidence_links'][0]['quote']==access


def test_a_split_with_one_new_need_whose_quotation_leaves_text_out_stays_blocked(wrapped):
    store,run=opted_in(wrapped)
    plans=quoting(ACCESS,'Users can find the access conditions for a dataset','Publishers can find ... for a dataset.')
    fd.deliberate(store,run['run_id'],Habits(plans,'children'))
    saved,case=sound(store,run)
    rows={o['action_id']:o for o in case['mediation']['outcomes']}
    assert rows['A1']['status']=='machine_revised' and rows['A2']['status']=='blocked_change'
    assert rows['A2']['validation_error']=='Ambiguous or unmatched source quotation.' and not rows['A2'].get('result_revision_ids')
    assert set(rows['A2']['parent_revision_ids'])<=set(saved['active_revision_ids']) and saved['metrics']['mediated_changes']==1


@pytest.mark.parametrize('quote',['Users can find the access conditions ... independent format.',
    'Users can find the access rules for a dataset.','for a dataset'])
def test_quotations_with_text_left_out_changed_or_repeated_stay_blocked(wrapped,quote):
    store,run=opted_in(wrapped);before=list(run['active_revision_ids'])
    fd.deliberate(store,run['run_id'],Habits(quoting(quote,quote,quote),'children'))
    saved,case=sound(store,run)
    assert all(o['status']=='blocked_change' and o['validation_error']=='Ambiguous or unmatched source quotation.'
        for o in case['mediation']['outcomes'])
    assert saved['active_revision_ids']==before and saved['metrics']['mediated_changes']==0


# v12: single-need plans as the mediator wrote them in both tries, from the cases that were lost because no
# need kept a valid disposition (10 of the 12 lost cases in JRC run-0834b623, JRC run-12a2c91a and Stat
# run-1428af21, all with one need). Each plan answers the first try and its correction; the final mediation
# answers the same way. Wire IDs: the case's need is N1.
def corrected(system):
    return 'Your previous answer was rejected' in system


def child(statement,cited,i):
    return {'action_id':f'A1.{i}','statement':statement,'evidence_links':cited,'rationale':'One part.'}


def labelled_split(data,number,system):
    """JRC run-0834b623 case-361cc0f79: a need labelled as covered by the base, split; corrected by
    keeping it covered_by_base beside the split."""
    (n,),_=ids(data);cited=sourced(data)
    split={'action_id':'A1','action':'split','parent_revision_ids':[n],'rationale':'Two kinds of rights information.',
        'children':[child(LICENCE,cited,1),child(HOLDER,cited,2)]}
    if corrected(system):
        return {'actions':[{'action_id':'A0','action':'covered_by_base','parent_revision_ids':[n],'rationale':'The base covers it.'},split],
            'concerns':[],'questions':[],'summary':'s'}
    return {'actions':[split,{'action_id':'A2','action':'add','statement':'Users can retrieve the rights statement of a dataset.',
        'evidence_links':cited,'rationale':'A further need.','human_question':'Which URL should be given?'}],'concerns':[],'questions':[],'summary':'s'}


def parts_set_aside(data,number,system):
    """Stat run-1428af21 case-0182df950: a split into five unsourced parts; corrected by splitting off the two
    parts with a source and setting the other three aside, each as an action on the need, without a question."""
    (n,),_=ids(data);cited=sourced(data)
    parts=[f'Users can know the prefix and namespace of resource kind {k}.' for k in range(5)]
    if not corrected(system):
        return {'actions':[{'action_id':'A1','action':'split','parent_revision_ids':[n],'rationale':'One need per part.',
            'children':[child(t,[],i+1) for i,t in enumerate(parts)]}],'concerns':[],'questions':[],'summary':'s'}
    return {'actions':[{'action_id':'A1','action':'split','parent_revision_ids':[n],'rationale':'The parts with a source.',
            'children':[child(t,cited,i+1) for i,t in enumerate(parts[:2])]},
        *[{'action_id':f'A{i+2}','action':'set_aside','reason':'not_find_or_access','parent_revision_ids':[n],'statement':t,
           'rationale':'No source for this part.'} for i,t in enumerate(parts[2:])]],'concerns':[],'questions':[],'summary':'s'}


def parts_deferred(data,number,system):
    """Stat run-1428af21 case-259460907: a split into three unsourced parts with two parentless deferrals;
    corrected by splitting off the one part with a source and deferring the other two on the need."""
    (n,),_=ids(data);cited=sourced(data)
    parts=['Users can know the meaning of the modification date.','Users can know the meaning of the release date.',
        'Users can know the meaning of the listing date.']
    if not corrected(system):
        return {'actions':[{'action_id':'A1','action':'split','parent_revision_ids':[n],'rationale':'One need per date.',
            'children':[child(t,[],i+1) for i,t in enumerate(parts)]},
            *[{'action_id':f'A{i+2}','action':'defer','statement':t,'rationale':'No source defines it.','human_question':'Q1'}
              for i,t in enumerate(parts[1:])]],'concerns':[],'questions':[],'summary':'s'}
    return {'actions':[{'action_id':'A1','action':'split','parent_revision_ids':[n],'rationale':'The part with a source.',
            'children':[child(parts[0],cited,1)]},
        *[{'action_id':f'A{i+2}','action':'defer','parent_revision_ids':[n],'statement':t,'rationale':'No source defines it.',
           'human_question':'Which source defines this date?','alternatives':['Keep it','Leave it out']} for i,t in enumerate(parts[1:])]],
        'concerns':[],'questions':[],'summary':'s'}


def final_set_asides(data,number,system):
    """JRC run-0834b623 case-ad71d6aea: a valid draft (an unchanged revise, after unsourced adds were
    corrected); the final adds three set-asides of rejected ideas, first without a need, then on the need."""
    (n,),_=ids(data);cited=sourced(data)
    revise={'action_id':'A1','action':'revise','parent_revision_ids':[n],'statement':data['packet']['needs'][0]['need_statement'],
        'evidence_links':cited,'rationale':'Kept as the source permits it.'}
    ideas=['Users can access the additional fields.','Users can know the obligation status of the fields.',
        'Contributors can record rights information.']
    if 'draft' not in data:
        if corrected(system):return {'actions':[revise],'concerns':[],'questions':[],'summary':'s'}
        return {'actions':[revise,*[{'action_id':f'A{i+2}','action':'add','statement':t,'rationale':'Proposed.'} for i,t in enumerate(ideas)]],
            'concerns':[],'questions':[],'summary':'s'}
    return {'actions':[revise,*[{'action_id':f'A{i+2}','action':'set_aside','reason':'not_find_or_access','statement':t,
        'parent_revision_ids':[n] if corrected(system) else [],'rationale':'No source supports it.',
        **({'human_question':'Should this need be added?'} if corrected(system) else {})} for i,t in enumerate(ideas)]],
        'concerns':[],'questions':[],'summary':'s'}


def label(store,run):
    store.mutate(run['run_id'],None,'fixture_label',lambda r:r['requirements'][0].update(processing_flags=['covered_by_base']))
    return store.get('run',run['run_id'])


ALL_DEFERRED=[(labelled_split,True),(parts_set_aside,False),(parts_deferred,False),(final_set_asides,False)]


@pytest.mark.parametrize('checker',['ideal','children'])
@pytest.mark.parametrize('plans,labelled',ALL_DEFERRED)
def test_a_single_need_plan_that_keeps_no_action_is_salvaged_and_shown_to_a_person(setup,plans,labelled,checker):
    store,run=opted_in(setup,1)
    if labelled:run=label(store,run)
    before=list(run['active_revision_ids'])
    fd.deliberate(store,run['run_id'],Habits(plans,checker))
    saved,case=sound(store,run)
    # Up to v11 the case stopped as invalid output, and its proposals were not shown.
    assert case['stop_reason']=='bounded_fa_dialogue_salvaged'
    assert saved['active_revision_ids']==before and saved['metrics']['mediated_changes']==0
    assert not any(o.get('applied') for o in case['mediation']['outcomes'])
    salvage=case['mediation']['salvage']
    assert set(salvage)==({'final'} if plans is final_set_asides else {'draft','final'})
    audit=salvage['final']
    assert audit['policy_version']=='rq1-fa-salvage-v2' and audit['nothing_kept'] and audit['kept_action_ids']==[]
    assert audit['deferred_revision_ids']==before
    rows={o['action_id']:o for o in case['mediation']['outcomes']}
    assert rows['salvage-1']['action']=='defer' and rows['salvage-1']['status']=='human_review'
    assert rows['salvage-1']['parent_revision_ids']==before
    assert rows['salvage-1']['alternatives']==['Keep the original need','Apply a rejected mediator action after review']
    # Every dropped action is a review row carrying its full proposal, children and sources included.
    assert audit['dropped_actions'] and {d['action_id'] for d in audit['dropped_actions']}=={k for k,o in rows.items() if o.get('salvage_rejected')}
    for d in audit['dropped_actions']:
        row=rows[d['action_id']]
        assert row['status']=='human_review' and not row['applied'] and row['validation_errors']==d['problems']
        assert {k:v for k,v in row.items() if k in d['proposal'] and k!='human_question'}=={k:v for k,v in d['proposal'].items() if k!='human_question'}
    assert case['mediation']['salvage_nothing_kept'] and saved['metrics']['salvaged_nothing_kept']==saved['metrics']['salvaged_cases']==1
    assert saved['metrics']['lost_after_salvage_nothing_kept']==0


def test_a_valid_final_plan_after_a_draft_that_kept_nothing_is_applied(setup):
    # The second chance: the draft kept no action (Stat case-0182df950 in both tries); the stakeholders review
    # the system deferral and the final splits the need validly.
    store,run=opted_in(setup,1);before=list(run['active_revision_ids'])
    def plans(data,number,system):
        if 'draft' not in data:return parts_set_aside(data,number,system)
        (n,),_=ids(data);cited=sourced(data)
        return {'actions':[{'action_id':'A1','action':'split','parent_revision_ids':[n],'rationale':'Two needs.',
            'children':[child(LICENCE,cited,1),child(HOLDER,cited,2)]}],'concerns':[],'questions':[],'summary':'s'}
    client=Habits(plans,'children');fd.deliberate(store,run['run_id'],client)
    saved,case=sound(store,run)
    assert case['stop_reason']=='bounded_fa_dialogue_complete' and set(case['mediation']['salvage'])=={'draft'}
    assert case['mediation']['salvage']['draft']['nothing_kept'] and 'salvage_nothing_kept' not in case['mediation']
    # The salvaged draft re-engaged both roles.
    assert len(case['discussion_trace']['targeted_roles'])==2
    [split]=[o for o in case['mediation']['outcomes'] if o['action']=='split']
    assert split['status']=='machine_revised' and len(split['result_revision_ids'])==2
    assert before[0] not in saved['active_revision_ids'] and saved['metrics']['mediated_changes']==1
    assert saved['metrics']['salvaged_cases']==saved['metrics']['salvaged_nothing_kept']==0


# v13: checker answers that check every action of the plan once and also an ID that is not an action of the
# plan, in both tries. Each shape copies a lost case: JRC run-efc543e4 case-3df2504bc (the experience proposal
# P1), Stat run-d069be4d case-24df0812f (A2, a parentless defer the salvage had dropped; both plans were salvaged
# to their retain A1), JRC run-36730b38 case-c04026b6a (an invented S1 beside the two retains of the final plan)
# and Stat run-289823d2 case-ee9443c2a (the experience claims X1, X2, ... checked as actions; three there). In JRC
# run-efc543e4 (SA1, SA2) and JRC run-12a2c91a (S1) the checker left such an ID out on its second try.
CLAIM={'kind':'missing_need','task':'Find data','experience':'When I search for data, I first check under which licence it is offered.',
    'claim':'The case lacks a need for the licence.','proposed_statement':LICENCE}


def claims_of(data):
    return [x['claim_id'] for m in data['messages'] for x in m.get('experience',[])]


def retains_excluding_claims(data,*_):
    needs,_=ids(data)
    return {'actions':[{'action_id':f'A{i+1}','action':'retain','parent_revision_ids':[n],'rationale':'Kept as stated.'}
        for i,n in enumerate(needs)],'concerns':[],'questions':[],'summary':'s',
        'experience':[{'claim_id':x,'decision':'exclude','rationale':'No source of the case supports it.'} for x in claims_of(data)]}


def retains_and_proposal(data,*_):
    needs,_=ids(data);plan=retains_excluding_claims(data);first=plan['experience'][0]
    first.update(decision='admit',rationale='The roles search by licence.')
    plan['proposals']=[{'proposal_id':'P1','statement':LICENCE,'experience_ids':[first['claim_id']],'revision_ids':[needs[0]],
        'rationale':'Proposed from the roles\' practice.'}]
    return plan


def retain_and_parentless_defer(data,*_):
    (n,),_=ids(data)
    return {'actions':[{'action_id':'A1','action':'retain','parent_revision_ids':[n],'rationale':'Kept as stated.'},
        {'action_id':'A2','action':'defer','parent_revision_ids':[],'statement':HOLDER,'rationale':'No source names it.',
         'human_question':'Should this need be added?','alternatives':['Add it','Leave it out']}],'concerns':[],'questions':[],'summary':'s'}


class Beyond(Habits):
    """Roles that may make one experience claim per review; the checker checks every action of the plan once and
    also the IDs extra(payload) names, in every try or only in the first."""
    def __init__(self,plans,extra,claims=False,first_only=False):
        super().__init__(plans,'ideal');self.extra=extra;self.claims=claims;self.first_only=first_only
    def generate_structured(self,*,user,output_model,system='',step=None,**kw):
        answer=super().generate_structured(user=user,output_model=output_model,system=system,step=step,**kw)
        name=contract_name(output_model);data=json.loads(user)
        if name=='Review' and self.claims:
            claim={**CLAIM,'revision_ids':[data['packet']['needs'][0]['revision_id']]}
            return output_model.model_validate({**answer.model_dump(mode='json'),'experience':[claim]})
        if name!='Checks' or (self.first_only and self.check_calls>1):return answer
        rows=answer.model_dump(mode='json')['checks']
        return output_model.model_validate({'checks':rows+[{**rows[0],'action_id':i} for i in self.extra(data)]})


# (plans, needs, roles make claims, the IDs the checker adds, stop reason)
OUTSIDE={'proposal':(retains_and_proposal,2,True,lambda data:['P1'],'bounded_fa_dialogue_complete'),
    'dropped_by_salvage':(retain_and_parentless_defer,1,False,lambda data:['A2'],'bounded_fa_dialogue_salvaged'),
    'invented':(retains_excluding_claims,2,False,lambda data:['S1'],'bounded_fa_dialogue_complete'),
    'claims':(retains_excluding_claims,2,True,claims_of,'bounded_fa_dialogue_complete')}


@pytest.mark.parametrize('first_only',[False,True])
@pytest.mark.parametrize('shape',sorted(OUTSIDE))
def test_a_check_of_an_id_that_is_not_an_action_of_the_plan_is_ignored(setup,shape,first_only):
    plans,count,claims,extra,stop=OUTSIDE[shape]
    store,run=opted_in(setup,count);client=Beyond(plans,extra,claims,first_only)
    fd.deliberate(store,run['run_id'],client)
    saved,case=sound(store,run)
    # Up to v12 the answer was refused: given in both tries it lost the case, given once it cost a second check.
    assert case['stop_reason']==stop and client.check_calls==1
    [attempt]=case['discussion_trace']['phases']['check']['attempts']
    assert attempt['errors']==[]
    expected=['P1'] if shape=='proposal' else ['A2'] if shape=='dropped_by_salvage' else ['S1'] if shape=='invented' else [
        x['claim_id'] for m in case['messages'] for x in m.get('experience',[])]
    assert len(expected)==(4 if shape=='claims' else 1)
    assert case['mediation']['ignored_check_ids']==case['discussion_trace']['ignored_check_ids']==expected
    assert saved['metrics']['ignored_checks']==len(expected)
    # Every action of the plan is applied on its own check; no other row carries one.
    final=case['discussion_trace']['final']['actions'];rows={o['action_id']:o for o in case['mediation']['outcomes']}
    assert {k for k,o in rows.items() if 'independent_check' in o}=={a['action_id'] for a in final}
    assert all(o['independent_check']['action_id']==k for k,o in rows.items() if 'independent_check' in o)
    assert not set(expected)&{a['action_id'] for a in final}
    if shape=='proposal':
        assert rows['P1']['status']=='experience_proposal' and not rows['P1']['applied']
    if shape=='dropped_by_salvage':
        assert [a['action_id'] for a in final]==['A1'] and rows['A1']['status']!='human_review'
        assert rows['A2']['salvage_rejected'] and rows['A2']['status']=='human_review' and not rows['A2']['applied']
        assert saved['active_revision_ids']==run['active_revision_ids']


# A check filed under another ID still leaves its action unchecked, and a repeated check still fails: the
# checker gives the answer in both tries, and the case keeps its needs as they were.
class Misfiled(Habits):
    """The checker files A2's check under S1, leaves it out beside a check of P1, or checks A1 twice beside S1."""
    def __init__(self,plans,habit):super().__init__(plans,'ideal');self.habit=habit
    def generate_structured(self,*,user,output_model,system='',step=None,**kw):
        answer=super().generate_structured(user=user,output_model=output_model,system=system,step=step,**kw)
        if contract_name(output_model)!='Checks':return answer
        rows=answer.model_dump(mode='json')['checks'];one=lambda i:{**rows[0],'action_id':i}
        rows={'misfiled':[one('S1' if r['action_id']=='A2' else r['action_id']) for r in rows],
            'missing':[r for r in rows if r['action_id']!='A2']+[one('P1')],
            'repeated':rows+[one('A1'),one('S1')]}[self.habit]
        return output_model.model_validate({'checks':rows})


@pytest.mark.parametrize('habit',['misfiled','missing','repeated'])
def test_a_misfiled_missing_or_repeated_check_of_an_action_still_stops_the_case(setup,habit):
    store,run=opted_in(setup);before=list(run['active_revision_ids']);client=Misfiled(retains_excluding_claims,habit)
    fd.deliberate(store,run['run_id'],client)
    saved,case=sound(store,run)
    assert case['stop_reason']=='invalid_output_pending_human_review' and client.check_calls==2
    assert saved['active_revision_ids']==before and saved['metrics']['mediated_changes']==0
    errors=[a['errors'] for a in case['discussion_trace']['phases']['check']['attempts']]
    wanted={'misfiled':{'missing':['A2'],'repeated':[],'unknown':['S1']},'missing':{'missing':['A2'],'repeated':[],'unknown':['P1']},
        'repeated':{'missing':[],'repeated':['A1'],'unknown':['S1']}}[habit]
    assert errors==[['Check every action exactly once: '+json.dumps(wanted,separators=(',',':'))]]*2
    # As up to v12 (which had no count of ignored checks).
    assert 'ignored_check_ids' not in case['mediation'] and not saved['metrics'].get('ignored_checks')
