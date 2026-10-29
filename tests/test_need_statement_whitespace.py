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
    assert need.verification.get('message') != 'Need metadata integrity mismatch.'
    assert verify(store, need, run['evidence_ids']).get('message') != 'Need metadata integrity mismatch.'
    assert event['action'] == 'merge_need' and event['policy_version'] == 'rq1-need-statement-v5'
