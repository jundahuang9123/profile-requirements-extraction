"""rq1-generic-domain-v4: a need without a scope carries the placeholder 'Unspecified' (the model default).
The refinement check counted that placeholder as a word the need adds to its base entry, so a need that
only restates the entry passed as a refinement (domain_use_of_base). Scripted answers, no evaluation data
or live generation."""
import json
from types import SimpleNamespace
from test_resume_discussions import setup  # noqa: F401  (pytest fixture)
from test_rq1_need_grouping import NeedsClient
from test_rq1_need_classification import _three_proposals
from requirement_reuse_service.workflow import needs

TITLE = 'Find the title of a dataset.'
RESTATED = 'Users can identify the title of a dataset.'


def need(scope, condition=''):
    return SimpleNamespace(need_condition=condition, need_statement=RESTATED, scope=scope,
        obligation_alternatives=[], normalized_intent=SimpleNamespace(obligation_hint='unknown'))


def test_the_scope_placeholder_is_not_a_word_the_need_adds():
    entry={'need':TITLE,'definition':'A name given to the dataset.','usage_notes':[],'base_obligation':'mandatory'}
    for placeholder in ('Unspecified','unspecified',' Unspecified '):
        assert not needs._has_additional_base_signal(need(placeholder),[entry])
    assert not needs._has_additional_base_signal(need(''),[entry])
    # A scope the need states is still an addition.
    assert needs._has_additional_base_signal(need('statistical tables'),[entry])


class Refines(NeedsClient):
    """Calls the restated title need a refinement of the title entry. On correction it either repeats
    that (insist) or calls the need generic."""
    def __init__(self, insist):
        super().__init__();self.insist=insist
    def generate_structured(self, **kwargs):
        if kwargs['output_model'].__name__!='NeedClassifications':return super().generate_structured(**kwargs)
        data=json.loads(kwargs['user']);self.calls.append(('NeedClassifications',data))
        ids=[k for k,v in data['base_needs'].items() if v['need']==TITLE]
        correcting='Correct only these failing rows' in kwargs['system']
        label=('domain_use_of_base' if self.insist or not correcting else 'generic') if ids else 'domain'
        return kwargs['output_model'].model_validate({'classifications':[{'need_id':i,'classification':label,
            'base_need_ids':ids,'rationale':'Scripted base comparison.'} for i in data['needs']]})


def test_a_restatement_called_a_refinement_is_corrected_to_generic(setup):
    store,run,proposals=_three_proposals(setup)
    restated=proposals[0]
    assert restated.need_statement==RESTATED and restated.scope=='Unspecified' and not restated.need_condition
    client=Refines(insist=False)
    needs.classify_needs(store,run,[restated],client)
    assert restated.need_class=='generic' and restated.base_gap['status']=='served_by_base'
    # One correction, asked because the refinement adds nothing to the entry.
    chunks=store.get('run',run['run_id'])['need_chunks'].values()
    errors=[e for c in chunks for a in c['attempts'] for e in sum(a['validation_errors'].values(),[])]
    assert errors==[restated.requirement_id+': a refinement needs a concrete added meaning, condition, scope or '
                    'obligation beyond the matched base.']


def test_a_restatement_still_called_a_refinement_is_left_unclassified(setup):
    store,run,proposals=_three_proposals(setup)
    restated=proposals[0]
    needs.classify_needs(store,run,[restated],Refines(insist=True))
    assert restated.need_class=='domain' and restated.base_gap['status']=='not_checked'
    assert 'not_classified' in restated.processing_flags and restated.matched_base_need_ids==[]
    assert any(c['status']=='not_checked' for c in restated.base_gap['search_chunks'])


def test_the_policy_name_changes_so_v3_runs_are_not_continued_under_v4():
    import pytest
    assert needs.POLICIES['classification']=='rq1-generic-domain-v4'
    with pytest.raises(ValueError,match='Needs policies changed'):
        needs.run_needs_policies({'needs_policies':{**needs.POLICIES,'classification':'rq1-generic-domain-v3'}})
