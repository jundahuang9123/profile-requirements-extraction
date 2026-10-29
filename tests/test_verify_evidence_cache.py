"""The source checks of a need step share one parse of each original source, as the verification stage does
(29 Oct scale check: Mobility cites 5 PDFs of 3-15 s each; uncached, writing and assessment re-parsed them for every
link, about 2.5 h of CPU). The checks themselves are unchanged: the same result with or without the cache."""
import json
import pytest
from test_rq1_need_grouping import NeedsClient, need_inputs
from test_rq1_need_assessment import FullNeedsClient
from test_resume_discussions import setup  # noqa: F401  (pytest fixture)
from requirement_reuse_service.workflow import evidence, needs
from requirement_reuse_service.workflow.engine import verify


@pytest.fixture
def parses(monkeypatch):
    counted = []
    original = evidence.decompose
    def counting(source):
        counted.append(source.source_version_id)
        return original(source)
    monkeypatch.setattr(evidence, 'decompose', counting)
    return counted


def same(a, b):
    return {k: v for k, v in a.items() if k != 'checked_at'} == {k: v for k, v in b.items() if k != 'checked_at'}


def test_writing_parses_each_source_once(setup, parses):
    # Two needs, each with two links into the same source: 4 parses uncached, 1 shared.
    store, run, records = need_inputs(setup)
    parses.clear()
    written, _ = needs.write_needs(store, run, [[records[0]], [records[1]]], NeedsClient(), None)
    assert len(written) == 2 and len(parses) == 1
    for need in written:
        assert need.verification['status'] == 'pass'
        assert same(need.verification, verify(store, need, run['evidence_ids']))


class UnstatedObligation(NeedsClient):
    def generate_structured(self, **kwargs):
        if kwargs['output_model'].__name__ != 'ProposalSupport': return super().generate_structured(**kwargs)
        data = json.loads(kwargs['user'])
        return kwargs['output_model'].model_validate({'proposals': [{'proposal_id': i, 'support': 'supported',
            'supporting_evidence_ids': list(row['excerpts']), 'obligation_stated': False,
            'rationale': 'Scripted: the quote does not state the obligation.'} for i, row in data['proposals'].items()]})


def test_the_proposal_support_recheck_parses_each_source_once(setup, parses):
    # An obligation the quote does not state is dropped and the record checked again, sharing one parse.
    store, run, records = need_inputs(setup)
    assert all(r.normalized_intent.obligation_hint != 'unknown' for r in records)
    parses.clear()
    retained = needs.check_proposal_support(store, run, records, UnstatedObligation())
    rechecked = [r for r in retained if r.unbacked_obligation]
    assert len(rechecked) == 2 and len(parses) == 1
    for record in rechecked:
        assert same(record.verification, verify(store, record, run['evidence_ids'], policy_version=needs.POLICIES['source_check']))


def test_assessment_parses_each_source_once(setup, parses):
    store, run, records = need_inputs(setup)
    written, _ = needs.write_needs(store, run, [[records[0]], [records[1]]], NeedsClient(), None)
    parses.clear()
    needs.assess_needs(store, run, written, FullNeedsClient())
    assert len(parses) == 1
    for need in written:
        assert need.verification['status'] == 'pass'
        assert same(need.verification, verify(store, need, run['evidence_ids']))
