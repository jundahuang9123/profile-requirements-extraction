from requirement_reuse_service.workflow.models import NeedSpanObservation, RunRequest, RequirementRecord
from requirement_reuse_service.workflow.terms import detect_terms, collect_hints
from requirement_reuse_service.workflow.base_profile import load_profile


def test_terms_and_literal_hint_provenance():
    profile, _ = load_profile('dcat-ap-3.0.0')
    assert detect_terms('dataset title dct:publisher DataService accessURL https://example.org', profile) == ['DataService', 'accessURL', 'dct:publisher']
    hints = collect_hints('dct:publisher', [{'evidence_id':'e1', 'quote':'DataService uses ISO 19115'}], profile, 'r1',
        [{'term':'invented:thing','kind':'vocabulary_term','origin':'proposal'},
         {'term':'ISO 19115','kind':'standard','origin':'proposal'}])
    assert {h.term for h in hints} == {'dct:publisher','DataService','ISO 19115'}
    assert next(h for h in hints if h.term == 'ISO 19115').origin == 'evidence'
    assert all(h.revision_id == 'r1' for h in hints)


def test_new_provider_contract_separates_solutions():
    properties = NeedSpanObservation.model_json_schema()['properties']
    assert 'rq2_hints' in properties and 'task_justifications' in properties
    assert 'extension_kind' not in properties and 'base_property' not in properties
    assert RunRequest(snapshot_id='x', strategy='multi_agent').output_form == 'needs'
    assert RequirementRecord.model_fields['need_statement'].default is None


def test_single_capitalised_words_are_not_local_vocabulary_names():
    from requirement_reuse_service.workflow.base_profile import load_profile
    from requirement_reuse_service.workflow.terms import detect_terms
    profile,_=load_profile('dcat-ap-2.0.1')
    assert detect_terms('Dataset owners. Location Referencing. Distribution formats.',profile)==[]
    assert detect_terms('accessURL DataService PeriodOfTime dcat:Dataset',profile)==['DataService','PeriodOfTime','accessURL','dcat:Dataset']
