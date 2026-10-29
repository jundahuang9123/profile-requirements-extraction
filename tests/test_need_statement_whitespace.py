"""rq1-need-statement-v5 (Junda, 29 Oct): a written need is stated with its whitespace folded. A rewrite the writer
returned with a leading space ('" Users can know the size of a distribution of a dataset"', Stat run-327cb53a; the
same in run-49298834) was stored as written, while its normalised statement was folded, so its integrity check
failed, the source check failed with it, and the trace set the need aside as trace_incomplete."""
import json
import pytest
from test_rq1_need_grouping import NeedsClient, need_inputs
from test_semantic_consolidation import revised
from test_resume_discussions import setup  # noqa: F401  (pytest fixture)
from requirement_reuse_service.workflow import needs
from requirement_reuse_service.workflow.engine import verify


class SpacedWriter(NeedsClient):
    def __init__(self, written):
        super().__init__(); self.written = written
    def generate_structured(self, **kwargs):
        if kwargs['output_model'].__name__ != 'NeedStatements': return super().generate_structured(**kwargs)
        data = json.loads(kwargs['user']); self.calls.append(('NeedStatements', data))
        return kwargs['output_model'].model_validate({'needs': [{'group_id': g, 'statement': self.written, 'condition': '',
            'members': [{'member_id': m, 'expresses_need': True} for m in group['members']]} for g, group in data['groups'].items()]})


@pytest.mark.parametrize('written', [' Users can know the size of a distribution of a dataset',
                                     'Users can know the size of a distribution of a dataset.\n',
                                     'Users can know the  size of a distribution\nof a dataset.'])
def test_a_rewrite_with_stray_whitespace_keeps_its_integrity(setup, written):
    store, run, records = need_inputs(setup)
    member = revised(run, records[0], statement='Users can know the size of a Distribution via dcat:byteSize.', observation_id='obs-space')
    member.verification = verify(store, member, run['evidence_ids'])
    [need], [event] = needs.write_needs(store, run, [[member]], SpacedWriter(written), None)
    assert need.need_statement == need.normalized_statement == ' '.join(written.split())
    assert need.verification['status'] == 'pass' and need.lifecycle_state == 'need_assessment_pending'
    assert verify(store, need, run['evidence_ids'])['status'] == 'pass'
    assert event['action'] == 'merge_need' and event['policy_version'] == 'rq1-need-statement-v5'


@pytest.mark.parametrize('written', [' ', '\n'])
def test_a_blank_rewrite_is_not_a_need(setup, written):
    # Folded, a blank rewrite would be an empty need that passes its integrity check; the writer check rejects it.
    # The member names no resource, so the resource rule does not reject the blank rewrite first.
    store, run, records = need_inputs(setup)
    member = revised(run, records[0], statement='Users can know the licence under which they may reuse the data.', observation_id='obs-blank')
    member.verification = verify(store, member, run['evidence_ids'])
    [need], [event] = needs.write_needs(store, run, [[member]], SpacedWriter(written), None)
    assert event['action'] != 'merge_need'
    assert need.need_statement == 'Users can know the licence under which they may reuse the data.'


@pytest.mark.parametrize('written', ['Users can know the size of a distribution of a dataset provided\nthat it is published',
                                     'Users can know the size of a distribution of a dataset where  applicable'])
def test_a_condition_split_by_whitespace_is_still_an_added_condition(setup, written):
    # The added-condition check reads the statement as it is stored, folded; 'provided\nthat' is 'provided that'.
    store, run, records = need_inputs(setup)
    member = revised(run, records[0], statement='Users can know the size of a Distribution via dcat:byteSize.', observation_id='obs-cond')
    member.verification = verify(store, member, run['evidence_ids'])
    [need], [event] = needs.write_needs(store, run, [[member]], SpacedWriter(written), None)
    assert event['action'] != 'merge_need'
    assert need.need_statement == 'Users can know the size of a Distribution via dcat:byteSize.'
