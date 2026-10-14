import pytest
from test_resume_discussions import setup
from requirement_reuse_service.workflow.needs import conditions

@pytest.mark.parametrize('verb',['tell','see','know','check','find out','determine','show','indicate','state','record','describe','specify','document','understand','judge'])
@pytest.mark.parametrize('marker',['when','if','whether'])
def test_indirect_questions_are_not_restricting_conditions(verb,marker):
    assert conditions(f'Users can {verb} {marker} the data were updated.')==[]

@pytest.mark.parametrize('text',['If a dataset is real-time, users can identify updates.', 'Users can find a licence when access is restricted.', 'Users can check licences if the dataset is restricted.'])
def test_restricting_clauses_stay_conditions(text):
    assert conditions(text)


def test_modification_question_can_be_classified_as_generic(setup,monkeypatch):
    import json
    from test_rq1_need_grouping import need_inputs, NeedsClient
    from requirement_reuse_service.workflow import needs, base_needs
    from requirement_reuse_service.workflow.base_profile import load_profile
    store,run,records=need_inputs(setup)
    written,_=needs.write_needs(store,run,[records],NeedsClient(),None)
    need=written[0];need.need_statement=need.normalized_statement='Users can see when a dataset was last modified.'
    need.obligation_alternatives=[];need.normalized_intent.obligation_hint='unknown'
    needs.refresh_need(need)
    profile,fingerprint=load_profile('dcat-ap-2.0.1')
    run.update(base_profile_id=profile['id'],base_profile_sha256=fingerprint)
    monkeypatch.setattr(base_needs,'offer_entries',lambda records,catalogue:[e for e in catalogue['entries'] if e['class']=='dcat:Dataset' and e['property']=='dct:modified'])
    class Generic:
        def generate_structured(self,**kw):
            data=json.loads(kw['user'])
            return kw['output_model'].model_validate({'classifications':[{'need_id':need.requirement_id,
                'classification':'generic','base_need_ids':list(data['base_needs']), 'rationale':'Controlled base match.'}]})
    assert needs.classify_needs(store,run,[need],Generic())==[]
    assert need.need_class=='generic'
