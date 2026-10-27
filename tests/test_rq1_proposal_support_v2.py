"""rq1-proposal-support-v2 (Junda, 24 Oct, decision 7 A): a proposal the support check rejects is judged again alone
and set aside only when both judgements reject it; when the second passes it, the proposal stays, flagged
proposal_support_disputed. Scripted clients test the plumbing only: in five runs repeated offline, judged alone the check
rejected more proposals than in a batch, not fewer."""
import json
import pytest
from test_resume_discussions import setup  # noqa: F401  (pytest fixture)
from test_rq1_need_grouping import need_inputs, NeedsClient
from requirement_reuse_service.workflow import needs


class SupportClient(NeedsClient):
    """Rejects every proposal in a batch of two or more; alone: 'pass' supports it, 'reject' rejects it again, 'omit'
    returns no row, so the correction runs and the judgement stays missing."""
    def __init__(self, alone, batch='reject'):
        super().__init__(); self.alone = alone; self.batch = batch
    def generate_structured(self, **kwargs):
        if kwargs['output_model'].__name__ != 'ProposalSupport': return super().generate_structured(**kwargs)
        data = json.loads(kwargs['user']); self.calls.append(('ProposalSupport', data))
        mode = self.alone if len(data['proposals']) == 1 else self.batch
        if mode == 'omit': return kwargs['output_model'].model_validate({'proposals': []})
        return kwargs['output_model'].model_validate({'proposals': [{'proposal_id': identifier,
            'support': 'supported' if mode == 'pass' else 'not_supported',
            'supporting_evidence_ids': list(row['excerpts'])[:1] if mode == 'pass' else [],
            'obligation_stated': False, 'rationale': f'Scripted: {mode}.'} for identifier, row in data['proposals'].items()]})


def support_calls(client):
    return [sorted(data['proposals']) for name, data in client.calls if name == 'ProposalSupport']


def test_a_rejection_that_passes_alone_keeps_the_proposal_flagged(setup):
    store, run, records = need_inputs(setup)
    client = SupportClient('pass')
    # Judging a stated obligation the quote does not state re-hashes the revision, so offered IDs are taken first.
    offered = [r.revision_id for r in records]; ids = sorted(offered)
    fresh = [r.model_copy(deep=True) for r in records]
    kept = needs.check_proposal_support(store, run, records, client)
    assert len(kept) == 2
    for record in kept:
        support = record.proposal_support
        assert support['support'] == 'supported' and support['policy_version'] == 'rq1-proposal-support-v2'
        assert support['confirmation']['outcome'] == 'disputed' and support['confirmation']['verdict']['support'] == 'not_supported'
        assert 'proposal_support_disputed' in record.processing_flags
        assert support['supporting_evidence_ids']
    step = store.get('run', run['run_id'])['need_steps']['proposal_support']
    assert step['confirmation_counts'] == {'disputed': 2} and step['set_aside_count'] == 0
    # One batch, then each rejection alone; a resume reuses every judgement.
    assert support_calls(client) == [ids, [offered[0]], [offered[1]]]
    before = len(client.calls)
    needs.check_proposal_support(store, run, fresh, client)
    assert len(client.calls) == before


def test_a_rejection_confirmed_alone_is_set_aside(setup):
    store, run, records = need_inputs(setup)
    kept = needs.check_proposal_support(store, run, records, SupportClient('reject'))
    assert kept == []
    asides = store.get('run', run['run_id'])['set_aside_observations']
    assert sorted(a['revision_id'] for a in asides) == sorted(r.revision_id for r in records)
    assert all(a['reason'] == 'not_supported_by_quote' for a in asides)
    assert all(r.proposal_support['confirmation']['outcome'] == 'confirmed' for r in records)
    assert store.get('run', run['run_id'])['need_steps']['proposal_support']['confirmation_counts'] == {'confirmed': 2}


def test_a_proposal_first_judged_alone_is_judged_again(setup):
    # A batch of one: the second judgement has its own cache step, or it would be the first one again.
    store, run, records = need_inputs(setup)
    store.mutate(run['run_id'], None, 'fixture_policies', lambda r: r.update(needs_policies=dict(needs.POLICIES)))
    run = store.get('run', run['run_id'])
    class FirstRejects(SupportClient):
        def generate_structured(self, **kwargs):
            if kwargs['output_model'].__name__ == 'ProposalSupport' and not any(n == 'ProposalSupport' for n, _ in self.calls):
                self.alone = 'reject'
            elif kwargs['output_model'].__name__ == 'ProposalSupport':
                self.alone = 'pass'
            return super().generate_structured(**kwargs)
    client = FirstRejects('reject'); offered = records[0].revision_id
    kept = needs.check_proposal_support(store, run, records[:1], client)
    assert len(kept) == 1 and kept[0].proposal_support['confirmation']['outcome'] == 'disputed'
    assert support_calls(client) == [[offered], [offered]]
    steps = {c.get('step') for c in store.get_run(run['run_id'])['need_chunks'].values() if isinstance(c, dict)}
    assert {'proposal_support', 'proposal_support_confirmation'} <= steps


def test_a_missing_second_judgement_keeps_the_proposal_unchecked(setup):
    store, run, records = need_inputs(setup)
    kept = needs.check_proposal_support(store, run, records, SupportClient('omit'))
    assert len(kept) == 2
    for record in kept:
        support = record.proposal_support
        assert support['support'] == 'not_checked' and 'support_not_checked' in record.processing_flags
        assert support['confirmation'] == {'outcome': 'not_checked', 'verdict': support['confirmation']['verdict']}
        assert support['confirmation']['verdict']['support'] == 'not_supported' and support['fallback']['reason']
        # As for a missing first judgement: the need keeps its authentic quotes.
        assert needs.supporting_links(record) == [l for l in record.evidence_links if l.relation == 'supports']
    assert store.get('run', run['run_id'])['need_steps']['proposal_support']['confirmation_counts'] == {'not_checked': 2}
    assert store.get('run', run['run_id'])['set_aside_observations'] == []


def test_a_supported_proposal_is_not_judged_again(setup):
    store, run, records = need_inputs(setup)
    client = SupportClient('reject', batch='pass')
    kept = needs.check_proposal_support(store, run, records, client)
    assert len(kept) == 2 and all('confirmation' not in r.proposal_support for r in kept)
    assert len(support_calls(client)) == 1


class OneRejected(SupportClient):
    """Supports the first offered proposal in a batch and rejects the second; alone, as SupportClient."""
    def generate_structured(self, **kwargs):
        if kwargs['output_model'].__name__ != 'ProposalSupport': return super().generate_structured(**kwargs)
        data = json.loads(kwargs['user'])
        if len(data['proposals']) == 1: return super().generate_structured(**kwargs)
        self.calls.append(('ProposalSupport', data)); first, second = list(data['proposals'])
        row = lambda i, ok: {'proposal_id': i, 'support': 'supported' if ok else 'not_supported',
            'supporting_evidence_ids': list(data['proposals'][i]['excerpts'])[:1] if ok else [], 'obligation_stated': False,
            'rationale': 'Scripted batch.'}
        return kwargs['output_model'].model_validate({'proposals': [row(first, True), row(second, False)]})


@pytest.mark.parametrize('alone,counts,asides', [('reject', {'confirmed': 1}, 1), ('pass', {'disputed': 1}, 0),
                                                   ('omit', {'not_checked': 1}, 0)])
def test_a_batch_with_one_rejection_counts_only_the_judged_again(setup, alone, counts, asides):
    # The usual shape of a run: most proposals pass in their batch and a few are judged again.
    store, run, records = need_inputs(setup)
    kept = needs.check_proposal_support(store, run, records, OneRejected(alone))
    step = store.get('run', run['run_id'])['need_steps']['proposal_support']
    assert step['confirmation_counts'] == counts and step['set_aside_count'] == asides
    assert len(kept) == 2 - asides
