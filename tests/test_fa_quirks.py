"""Whole discussion cases against the answer habits gpt-oss showed in live runs, not ideal answers.

Each scripted step below copies a shape seen in a saved live run (JRC run-a89957db, run-0ebfaffd,
run-4d980b17, run-efc543e4; Stat run-6455e495, run-c4cbca44). Every case must end in a defined state, keep or
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


@pytest.mark.parametrize('checker',['ideal','children'])
def test_quotations_that_differ_only_in_whitespace_or_hyphenation_are_applied_with_the_exact_text(wrapped,checker):
    store,run=opted_in(wrapped)
    plans=quoting(ACCESS,'Users can find the access conditions for a dataset','Publishers can find the contact details for a dataset.')
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
    # The outcome rows keep the quotations as the mediator wrote them.
    assert rows['A1']['evidence_links'][0]['quote']==ACCESS


@pytest.mark.parametrize('quote',['Users can find the access conditions ... independent format.',
    'Users can find the access rules for a dataset.','for a dataset'])
def test_quotations_with_text_left_out_changed_or_repeated_stay_blocked(wrapped,quote):
    store,run=opted_in(wrapped);before=list(run['active_revision_ids'])
    fd.deliberate(store,run['run_id'],Habits(quoting(quote,quote,quote),'children'))
    saved,case=sound(store,run)
    assert all(o['status']=='blocked_change' and o['validation_error']=='Ambiguous or unmatched source quotation.'
        for o in case['mediation']['outcomes'])
    assert saved['active_revision_ids']==before and saved['metrics']['mediated_changes']==0
