"""Premise-specific excerpt selection preserves authentic text without asserting entailment."""
import base64
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'requirement-reuse-service'))
from requirement_reuse_service.main import app
from requirement_reuse_service.llm.client import MockLLMClient
from requirement_reuse_service.models import ArtifactPayload
from requirement_reuse_service.workflow.citations import elicitation_batch, materialize_observation
from requirement_reuse_service.workflow.engine import (TrackedClient, elicit, freeze_snapshot, new_run,
    record_from_observation, verify, ensure_elicitation_resumable)
from requirement_reuse_service.workflow.evidence import register_source
from requirement_reuse_service.workflow.models import (RunRequest, SnapshotRequest, SourceRequest,
    SpanObservation, SpanElicitationResult)
from requirement_reuse_service.workflow.storage import Store


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    import pdfplumber
    monkeypatch.setenv('RRS_LLM_PROVIDER', 'mock')
    monkeypatch.setenv('RQ1_WORKFLOW_STORE', str(tmp_path / 'workflow.sqlite3'))
    text = PAGE
    @contextmanager
    def fake_pdf(_):
        yield SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda: text)])
    monkeypatch.setattr(pdfplumber, 'open', fake_pdf)
    store = Store()
    source = register_source(store, SourceRequest(artifact=ArtifactPayload(name='needs.pdf',
        content=base64.b64encode(b'%PDF-original-fixture-bytes').decode(), content_encoding='base64'),
        source_role='stakeholder_need'))
    snapshot = freeze_snapshot(store, SnapshotRequest(source_version_ids=[source['source_version_id']]))
    run = new_run(store, RunRequest(consolidation='exact', snapshot_id=snapshot['snapshot_id'], strategy='multi_agent',
                                   role_ids=['consumer_discovery']))
    return store, run


PAGE = 'Each Na-\ntional Access Point must provide metadata.\nThe same actor. The same actor.'


def payload(data, *, obligation=True, unknown=False, unsupported=False):
    # The page's three short lines form one excerpt; statement and obligation both cite it.
    spans = data['evidence_units'][0]['source_spans']
    links = [] if unsupported else [
        {'source_span_id': 'outside-this-batch' if unknown else spans[0]['span_id'], 'component': 'statement'}]
    if obligation and not unsupported:
        links.append({'source_span_id': spans[0]['span_id'], 'component': 'obligation'})
    return {'observations': [{'observation_id': 'model-id', 'role_id': 'untrusted-role',
        'extension_kind': 'new_information_need', 'base_property': None,
        'statement': 'Describe National Access Point metadata.', 'evidence_links': links,
        'requirement_type': 'descriptive_metadata',
        'intent': {'resource_type': 'DataService', 'metadata_need': 'metadata',
                   'obligation_hint': 'unknown' if unsupported else 'mandatory'},
        'support_level': 'unsupported' if unsupported else 'explicit'}]}


def test_multiline_pdf_citations_and_obligation_are_materialized_and_audited(corpus):
    store, run = corpus
    client = MockLLMClient(lambda system, user: payload(json.loads(user)))
    observations, reports = elicit(store, run, TrackedClient(client, store, run['run_id']))
    assert len(observations) == 1 and reports[0]['status'] == 'completed'
    observation = observations[0]
    # One excerpt spans the hyphenated line break; its text and offset are the source's own.
    assert [(link.component, link.quote, link.quote_start) for link in observation.evidence_links] == [
        ('statement', PAGE, 0), ('obligation', PAGE, 0)]
    assert observation.role_id == 'consumer_discovery'
    record = record_from_observation(run['run_id'], observation)
    assert verify(store, record, run['evidence_ids'])['status'] == 'pass'
    report = reports[0]
    assert report['citation_selections'][0]['status'] == 'materialized'
    assert report['raw_outputs'][0]['observations'][0]['evidence_links'][0] == {
        'source_span_id': 's0', 'relation': 'supports', 'component': 'statement'}
    saved_call = store.get('run', run['run_id'])['model_calls'][0]
    assert saved_call['output_contract'] == 'SpanElicitationResult'
    assert 'quote' not in saved_call['output']['observations'][0]['evidence_links'][0]


def test_missing_obligation_premise_is_still_blocked(corpus):
    store, run = corpus
    client = MockLLMClient(lambda system, user: payload(json.loads(user), obligation=False))
    observations, _ = elicit(store, run, client)
    verification = verify(store, record_from_observation(run['run_id'], observations[0]), run['evidence_ids'])
    assert verification['status'] == 'fail'
    assert verification['component_checks'] == {'statement_premise': True, 'obligation_premise': False}


def test_unknown_excerpt_gets_one_retry_then_fails_unit_and_preserves_raw_responses(corpus):
    from requirement_reuse_service.workflow.engine import CITATION_RETRY_NOTE
    store, run = corpus
    client = MockLLMClient(lambda system, user: payload(json.loads(user), unknown=True))
    observations, reports = elicit(store, run, client)
    assert observations == []
    assert reports[0]['status'] == 'failed'
    assert 'outside this batch' in reports[0]['error']
    # Both rejected answers stay in the audit; neither becomes an observation or a fallback.
    assert len(reports[0]['raw_outputs']) == 2 and all(o['observations'] for o in reports[0]['raw_outputs'])
    selections = reports[0]['citation_selections']
    assert [s['status'] for s in selections] == ['invalid', 'invalid']
    assert [s['recovery'] for s in selections] == ['single_unit_citation_retry_once', 'exhausted_continue_remaining']
    assert 'citation_retry' not in selections[0] and selections[1]['citation_retry'] is True
    assert [CITATION_RETRY_NOTE in call['system'] for call in client.calls] == [False, True]
    assert reports[0]['failed_batches'] == [{'batch_index': '0:0', 'kind': 'citation_invalid',
        'error': selections[1]['error'], 'evidence_ids': run['evidence_ids']}]
    assert (reports[0]['processed_unit_count'], reports[0]['evidence_unit_count']) == (0, 1)


@pytest.mark.parametrize('slip', ['unknown', 'duplicate'])
def test_citation_slip_recovers_on_the_single_retry_without_accepting_the_first_answer(corpus, slip):
    store, run = corpus
    def respond(system, user):
        result = payload(json.loads(user), unknown=slip == 'unknown' and len(client.calls) == 1)
        if slip == 'duplicate' and len(client.calls) == 1:
            links = result['observations'][0]['evidence_links']
            links.append(dict(links[0]))
        return result
    client = MockLLMClient(respond)
    observations, reports = elicit(store, run, client)
    assert len(client.calls) == 2 and reports[0]['status'] == 'completed'
    assert len(observations) == 1 and len(observations[0].evidence_links) == 2
    assert [s['status'] for s in reports[0]['citation_selections']] == ['invalid', 'materialized']
    expected = 'outside this batch' if slip == 'unknown' else 'Duplicate source excerpt link'
    assert expected in reports[0]['citation_selections'][0]['error']
    assert (reports[0]['processed_unit_count'], reports[0]['evidence_unit_count']) == (1, 1)
    assert verify(store, record_from_observation(run['run_id'], observations[0]), run['evidence_ids'])['status'] == 'pass'


def test_unsupported_hypothesis_retains_empty_evidence_and_fails_gate(corpus):
    store, run = corpus
    observations, reports = elicit(store, run, MockLLMClient(
        lambda system, user: payload(json.loads(user), unsupported=True)))
    assert reports[0]['status'] == 'completed' and observations[0].support_level == 'unsupported'
    assert observations[0].evidence_links == []
    assert verify(store, record_from_observation(run['run_id'], observations[0]), run['evidence_ids'])['status'] == 'fail'


def test_generated_quote_is_not_accepted_by_new_provider_contract():
    with pytest.raises(ValueError):
        SpanElicitationResult.model_validate({'observations': [{'observation_id': 'x', 'role_id': 'x',
            'extension_kind': 'new_information_need', 'base_property': None,
            'statement': 'A need.', 'evidence_links': [{'evidence_id': 'x', 'quote': 'A fabricated quotation.'}]}]})


def test_old_extraction_resume_rejected_before_provider_and_preserves_history(corpus, monkeypatch):
    from requirement_reuse_service.workflow import api
    store, run = corpus
    def legacy(r):
        r['status'] = 'failed'
        r['elicitation_policy_version'] = 'rq1-independent-elicitation-v2.4'
    store.mutate(run['run_id'], None, 'legacy_fixture', legacy)
    before = store.get('run', run['run_id'])
    monkeypatch.setattr(api, 'configured_client', lambda _: pytest.fail('No provider may be configured for this rejected resume'))
    result = TestClient(app).post(f'/api/rq1/v2/runs/{run["run_id"]}/resume', json={'expected_version': before['version']})
    assert result.status_code == 422 and 'new run' in result.text
    assert store.get('run', run['run_id']) == before


def test_excerpt_batch_includes_all_units_without_silent_truncation():
    units = [{'evidence_id': f'unit-{i}', 'content': 'x' * 805 + '\nlast line',
              'kind': 'text_span'} for i in range(3)]
    payload_units, catalogue = elicitation_batch(units)
    assert len(payload_units) == 3
    assert [s['span_id'] for s in catalogue] == [f's{i}' for i in range(9)]
    for unit in units:
        spans = [s for s in catalogue if s['evidence_id'] == unit['evidence_id']]
        # The over-long line is cut at 400 characters; its last piece joins the next line.
        assert [len(s['quote']) for s in spans] == [400, 400, len('xxxxx\nlast line')]
        assert ''.join(s['quote'] for s in spans) == unit['content']
        proposal = SpanObservation(observation_id='x', role_id='x', statement='Need.',
            extension_kind='new_information_need', base_property=None,
            evidence_links=[{'source_span_id': spans[-1]['span_id']}])
        link = materialize_observation(proposal, catalogue).evidence_links[0]
        assert link.evidence_id == unit['evidence_id'] and link.quote == 'xxxxx\nlast line'
        assert link.quote_start == 800


def test_excerpts_join_neighbouring_lines_up_to_the_limit_and_stop_at_blank_lines():
    from requirement_reuse_service.workflow.citations import EXCERPT_MAX_CHARS, excerpt_bounds
    definition = ('Property: language\n| RDF Property: | dct:language\n| Definition: | The language of the dataset.\n'
                  '| Range: | dct:LinguisticSystem')
    def quotes(content):
        return [content[start:end] for start, end in excerpt_bounds(content)]
    # A property definition of four short lines is one citable block instead of four fragments.
    assert quotes(definition) == [definition]
    # A blank line, or one holding only spaces, always starts a new excerpt.
    assert quotes('First paragraph.\n\nSecond paragraph.\n   \nThird.') == [
        'First paragraph.', 'Second paragraph.', 'Third.']
    assert quotes('Windows line one.\r\nWindows line two.') == ['Windows line one.\r\nWindows line two.']
    # Lines are added only while the whole excerpt stays within the limit.
    lines = [f'{i:02d} ' + 'word ' * 19 for i in range(12)]          # 98 characters each
    content = '\n'.join(lines)
    parts = quotes(content)
    assert [part.count('\n') + 1 for part in parts] == [4, 4, 4]
    assert all(len(part) <= EXCERPT_MAX_CHARS for part in parts)
    assert '\n'.join(parts) == content
    assert quotes('') == [] and quotes(' \n\t\n') == []
    # Units keep separate excerpts and one running numbering in source order.
    _, catalogue = elicitation_batch([{'evidence_id': 'a', 'content': 'one\ntwo'}, {'evidence_id': 'b', 'content': 'three'}])
    assert [(s['span_id'], s['evidence_id'], s['quote'], s['quote_start']) for s in catalogue] == [
        ('s0', 'a', 'one\ntwo', 0), ('s1', 'b', 'three', 0)]


def test_later_excerpt_of_a_long_page_keeps_its_offset_and_passes_source_verification(tmp_path, monkeypatch):
    import pdfplumber
    monkeypatch.setenv('RRS_LLM_PROVIDER', 'mock')
    monkeypatch.setenv('RQ1_WORKFLOW_STORE', str(tmp_path / 'workflow.sqlite3'))
    background = [f'Background line {i} describes the catalogue in general terms only.' for i in range(7)]
    need = 'Each access point must publish a contact\npoint for every dataset.'
    text = '\n'.join(background) + '\n' + need
    assert len(text) > 400
    @contextmanager
    def fake_pdf(_):
        yield SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda: text)])
    monkeypatch.setattr(pdfplumber, 'open', fake_pdf)
    store = Store()
    source = register_source(store, SourceRequest(artifact=ArtifactPayload(name='long.pdf',
        content=base64.b64encode(b'%PDF-long-fixture-bytes').decode(), content_encoding='base64'),
        source_role='stakeholder_need'))
    snapshot = freeze_snapshot(store, SnapshotRequest(source_version_ids=[source['source_version_id']]))
    run = new_run(store, RunRequest(consolidation='exact', snapshot_id=snapshot['snapshot_id'], strategy='multi_agent',
                                   role_ids=['consumer_discovery']))
    assert len(run['evidence_ids']) == 1
    def respond(system, user):
        spans = json.loads(user)['evidence_units'][0]['source_spans']
        assert len(spans) == 2 and all(len(span['quote']) <= 400 for span in spans)
        cited = next(span for span in spans if 'must publish' in span['quote'])
        assert cited['span_id'] == 's1'
        return {'observations': [{'observation_id': 'x', 'role_id': 'x', 'statement': 'Publish a contact point.',
            'extension_kind': 'new_information_need', 'base_property': None,
            'requirement_type': 'descriptive_metadata',
            'intent': {'resource_type': 'Dataset', 'metadata_need': 'contact point', 'obligation_hint': 'mandatory'},
            'evidence_links': [{'source_span_id': cited['span_id'], 'component': 'statement'},
                               {'source_span_id': cited['span_id'], 'component': 'obligation'}],
            'support_level': 'explicit'}]}
    observations, reports = elicit(store, run, MockLLMClient(respond))
    assert reports[0]['status'] == 'completed'
    link = observations[0].evidence_links[0]
    unit = store.get('evidence', run['evidence_ids'][0])
    assert link.quote.endswith(need) and link.quote_start > 0
    assert unit['content'][link.quote_start:link.quote_start + len(link.quote)] == link.quote
    verification = verify(store, record_from_observation(run['run_id'], observations[0]), run['evidence_ids'])
    assert verification['status'] == 'pass'
    assert verification['links'][0]['quote_start'] == link.quote_start


def test_catalog_record_survives_extraction_and_materialization(corpus):
    """A valid DCAT class must not reject its batch or become Dataset."""
    from copy import deepcopy
    from requirement_reuse_service.models import NormalizedIntent as RecordIntent
    store, run = corpus
    def response(system, user):
        result = payload(json.loads(user))
        catalog = result['observations'][0]
        catalog['intent']['resource_type'] = 'CatalogRecord'
        dataset = deepcopy(catalog)
        dataset['observation_id'] = 'dataset-id'
        dataset['intent']['resource_type'] = 'Dataset'
        result['observations'].append(dataset)
        return result
    observations, reports = elicit(store, run, TrackedClient(MockLLMClient(response), store, run['run_id']))
    assert reports[0]['status'] == 'completed'
    assert [o.intent.resource_type for o in observations] == ['CatalogRecord', 'Dataset']
    for observation in observations:
        record = record_from_observation(run['run_id'], observation)
        assert record.normalized_intent.resource_type == observation.intent.resource_type
        assert RecordIntent(resource_type=observation.intent.resource_type).resource_type == observation.intent.resource_type
        assert record.evidence_links == observation.evidence_links
        assert verify(store, record, run['evidence_ids'])['status'] == 'pass'


def multiunit_run(corpus, count=5):
    store, _ = corpus
    source = register_source(store, SourceRequest(artifact=ArtifactPayload(name='batch-needs.txt',
        content='\n'.join(f'Each dataset needs field {i}.' for i in range(count))), source_role='stakeholder_need'))
    snapshot = freeze_snapshot(store, SnapshotRequest(source_version_ids=[source['source_version_id']]))
    run = new_run(store, RunRequest(consolidation='exact', snapshot_id=snapshot['snapshot_id'], strategy='multi_agent',
                                  role_ids=['consumer_discovery']))
    assert len(run['evidence_ids']) == count
    return store, run


def unit_response(data):
    return {'observations': [{'observation_id': unit['evidence_id'], 'role_id': 'x',
        'extension_kind': 'new_information_need', 'base_property': None,
        'statement': unit['source_spans'][0]['quote'], 'evidence_links': [
            {'source_span_id': unit['source_spans'][0]['span_id'], 'component': 'statement'}],
        'intent': {'resource_type': 'Dataset', 'metadata_need': 'field'},
        'support_level': 'explicit'} for unit in data['evidence_units']]}


def test_output_cutoff_splits_without_losing_units_or_accepting_partial_json(corpus):
    from requirement_reuse_service.llm.client import OutputTokenLimitError
    store, run = multiunit_run(corpus)
    class Cutoff(MockLLMClient):
        def generate_structured(self, **kwargs):
            data = json.loads(kwargs['user'])
            assert len(data['evidence_units']) <= 4
            if len(data['evidence_units']) > 1:
                raise OutputTokenLimitError('simulated provider length cutoff')
            return kwargs['output_model'].model_validate(unit_response(data))
    observations, reports = elicit(store, run, TrackedClient(Cutoff(), store, run['run_id']))
    assert reports[0]['status'] == 'completed'
    assert len(observations) == 5
    assert {o.evidence_links[0].evidence_id for o in observations} == set(run['evidence_ids'])
    selections = reports[0]['citation_selections']
    assert any(s.get('recovery') == 'split_into_smaller_batches' for s in selections)
    assert sum(s.get('observation_count', 0) for s in selections) == 5
    calls = store.get('run', run['run_id'])['model_calls']
    assert len(calls) == 8  # Seven nodes for four units, plus one final singleton.
    assert sum(c['status'] == 'failed' for c in calls) == 3


def test_single_unit_output_cutoff_has_one_bounded_larger_retry(corpus):
    from requirement_reuse_service.llm.client import OutputTokenLimitError
    store, run = corpus
    budgets = []
    class Cutoff(MockLLMClient):
        def generate_structured(self, **kwargs):
            budgets.append(kwargs['max_tokens'])
            raise OutputTokenLimitError('simulated length cutoff')
    observations, reports = elicit(store, run, Cutoff())
    assert budgets == [8000, 12000]
    assert observations == [] and reports[0]['status'] == 'failed'
    assert [s['recovery'] for s in reports[0]['citation_selections']] == [
        'single_unit_larger_response_once', 'exhausted_continue_remaining']
    assert reports[0]['failed_batches'][0]['kind'] == 'output_cutoff'
    assert 'output_cutoff' in reports[0]['error'] and 'simulated length cutoff' in reports[0]['error']


def test_schema_failure_does_not_trigger_token_recovery(corpus):
    from requirement_reuse_service.llm.client import LLMError
    store, run = corpus
    budgets = []
    class Invalid(MockLLMClient):
        def generate_structured(self, **kwargs):
            budgets.append(kwargs['max_tokens'])
            raise LLMError('normal stop but invalid schema')
    observations, reports = elicit(store, run, Invalid())
    assert budgets == [8000]
    assert observations == [] and reports[0]['status'] == 'failed'


def test_recovery_retains_completed_split_when_later_leaf_fails(corpus):
    from requirement_reuse_service.llm.client import OutputTokenLimitError
    store, run = multiunit_run(corpus, count=2)
    class Cutoff(MockLLMClient):
        def generate_structured(self, **kwargs):
            data = json.loads(kwargs['user'])
            if len(data['evidence_units']) > 1 or data['evidence_units'][0]['evidence_id'] == run['evidence_ids'][1]:
                raise OutputTokenLimitError('simulated length cutoff')
            return kwargs['output_model'].model_validate(unit_response(data))
    observations, reports = elicit(store, run, Cutoff())
    assert reports[0]['status'] == 'failed'
    assert len(observations) == 1 and observations[0].evidence_links[0].evidence_id == run['evidence_ids'][0]
    assert reports[0]['observation_ids'] == [observations[0].observation_id]


@pytest.mark.parametrize('failure', ['output_cutoff', 'citation_invalid', 'duplicate_link'])
def test_unprocessable_unit_is_skipped_while_remaining_units_continue_then_resume_retries_only_it(corpus, failure):
    from requirement_reuse_service.llm.client import OutputTokenLimitError
    store, run = multiunit_run(corpus)
    failed_id = run['evidence_ids'][1]          # inside the first batch, so later units must still be reached
    seen = []
    class OneBadUnit(MockLLMClient):
        def generate_structured(self, **kwargs):
            data = json.loads(kwargs['user'])
            ids = [unit['evidence_id'] for unit in data['evidence_units']]
            seen.append((ids, kwargs['max_tokens']))
            response = unit_response(data)
            if failed_id in ids:
                if failure == 'output_cutoff':
                    raise OutputTokenLimitError('simulated length cutoff')
                bad = response['observations'][ids.index(failed_id)]['evidence_links']
                if failure == 'citation_invalid':
                    bad[0]['source_span_id'] = 's999'
                else:
                    bad.append(dict(bad[0]))
            return kwargs['output_model'].model_validate(response)
    partial, reports = elicit(store, run, TrackedClient(OneBadUnit(), store, run['run_id']))
    report = reports[0]
    assert report['status'] == 'failed'
    assert {o.evidence_links[0].evidence_id for o in partial} == set(run['evidence_ids']) - {failed_id}
    assert (report['processed_unit_count'], report['evidence_unit_count']) == (4, 5)
    expected_kind = 'output_cutoff' if failure == 'output_cutoff' else 'citation_invalid'
    assert [(f['kind'], f['evidence_ids']) for f in report['failed_batches']] == [(expected_kind, [failed_id])]
    assert '1 evidence unit(s) could not be processed' in report['error'] and expected_kind in report['error']
    # Four-unit batch, two halves, the failing half's two leaves, one bounded retry of the bad leaf, the last unit.
    assert [len(ids) for ids, _ in seen] == [4, 2, 1, 1, 1, 2, 1]
    retry_budgets = [budget for ids, budget in seen if ids == [failed_id]]
    assert retry_budgets == ([8000, 12000] if failure == 'output_cutoff' else [8000, 8000])
    assert seen[-1][0] == [run['evidence_ids'][4]]          # the role went on after the failed unit
    # Nothing from a rejected answer was accepted, and the saved state matches the returned one.
    restored = Store(store.path).get('run', run['run_id'])
    assert restored['role_runs'][0]['status'] == 'failed' and len(restored['observations']) == 4
    replayed = []
    def recover(system, user):
        data = json.loads(user)
        replayed.extend(unit['evidence_id'] for unit in data['evidence_units'])
        return unit_response(data)
    completed, reports = elicit(store, restored, MockLLMClient(recover))
    assert reports[0]['status'] == 'completed' and len(completed) == 5
    assert replayed == [failed_id]
    assert (reports[0]['processed_unit_count'], reports[0]['evidence_unit_count']) == (5, 5)
    assert {o.observation_id for o in partial} <= {o.observation_id for o in completed}


def test_transport_failure_still_stops_the_role_and_keeps_saved_batches(corpus):
    """A provider that cannot be reached is not asked again for every remaining unit."""
    from requirement_reuse_service.llm.client import LLMError
    store, run = multiunit_run(corpus, count=9)
    seen = []
    class Unreachable(MockLLMClient):
        def generate_structured(self, **kwargs):
            seen.append(len(json.loads(kwargs['user'])['evidence_units']))
            if len(seen) == 2:
                raise LLMError('OpenAI-compatible request failed after 3 attempt(s): ReadTimeout')
            return kwargs['output_model'].model_validate(unit_response(json.loads(kwargs['user'])))
    observations, reports = elicit(store, run, Unreachable())
    assert seen == [4, 4]          # the third batch is not requested
    assert reports[0]['status'] == 'failed' and 'ReadTimeout' in reports[0]['error']
    assert len(observations) == 4
    assert (reports[0]['processed_unit_count'], reports[0]['evidence_unit_count']) == (4, 9)
    assert 'failed_batches' not in reports[0] and reports[0]['citation_selections'][-1]['status'] == 'failed'


def test_restart_only_calls_unfinished_evidence_batches(corpus):
    from requirement_reuse_service.llm.client import LLMError
    store, run = multiunit_run(corpus)
    seen = []
    class InterruptSecondBatch(MockLLMClient):
        def generate_structured(self, **kwargs):
            data = json.loads(kwargs['user'])
            seen.append([unit['evidence_id'] for unit in data['evidence_units']])
            if len(seen) == 2:
                raise LLMError('Simulated process/provider interruption')
            return kwargs['output_model'].model_validate(unit_response(data))
    client = InterruptSecondBatch()
    partial, reports = elicit(store, run, client)
    assert len(partial) == 4 and reports[0]['status'] == 'failed'
    # Restore directly from the checkpoint without relying on the caller saving its return value.
    restored = Store(store.path).get('run', run['run_id'])
    assert len(restored['observations']) == 4
    completed, reports = elicit(store, restored, client)
    assert reports[0]['status'] == 'completed' and len(completed) == 5
    assert len(seen) == 3 and seen[2] == seen[1]
    assert set(seen[0]).isdisjoint(seen[2])
    assert {o.observation_id for o in partial} <= {o.observation_id for o in completed}


def test_schema_exhaustion_splits_and_continues_then_resumes_only_failed_units(corpus):
    from requirement_reuse_service.llm.client import OutputValidationError
    store, run = multiunit_run(corpus)
    seen = []
    failed_id = run['evidence_ids'][0]
    class InvalidBatch(MockLLMClient):
        def generate_structured(self, **kwargs):
            data = json.loads(kwargs['user'])
            assert kwargs['schema_repair_attempts'] == 1
            ids = [unit['evidence_id'] for unit in data['evidence_units']]
            seen.append(ids)
            if len(ids) > 1 or failed_id in ids:
                raise OutputValidationError('SpanElicitationResult', [{'loc': ['observations', 0], 'type': 'too_long'}])
            return kwargs['output_model'].model_validate(unit_response(data))
    partial, reports = elicit(store, run, TrackedClient(InvalidBatch(), store, run['run_id']))
    assert len(seen) == 8  # Four-unit binary split tree, plus the last source.
    assert len(partial) == 4 and reports[0]['status'] == 'failed'
    assert reports[0]['failed_batches'][0]['evidence_ids'] == [failed_id]
    assert {o.evidence_links[0].evidence_id for o in partial} == set(run['evidence_ids']) - {failed_id}
    restored = Store(store.path).get('run', run['run_id'])
    assert restored['role_runs'][0]['status'] == 'failed'
    assert len(restored['observations']) == 4
    replayed = []
    def recover(system, user):
        data = json.loads(user)
        replayed.extend(unit['evidence_id'] for unit in data['evidence_units'])
        return unit_response(data)
    completed, reports = elicit(store, restored, MockLLMClient(recover))
    assert reports[0]['status'] == 'completed' and len(completed) == 5
    assert replayed == [failed_id]
    assert {o.observation_id for o in partial} <= {o.observation_id for o in completed}


@pytest.mark.parametrize('invented_span', [False, True])
def test_real_client_correction_is_audited_and_still_passes_source_gate(corpus, monkeypatch, invented_span):
    import httpx
    import uuid
    from requirement_reuse_service.llm.client import OpenAICompatibleClient
    from requirement_reuse_service.llm.config import LLMConfig
    from requirement_reuse_service.workflow.engine import CITATION_RETRY_NOTE
    from requirement_reuse_service.workflow.evaluation import workflow_metrics
    store, run = corpus
    sent = []
    def post(*args, **kwargs):
        body = kwargs['json']
        sent.append(body)
        data = json.loads(body['messages'][1]['content'])
        proposal = payload(data, unknown=invented_span and len(sent) >= 2)
        proposal['observations'][0]['intent']['value_kind'] = 'mixed' if len(sent) == 1 else 'unknown'
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(proposal)}}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 20, 'total_tokens': 30}},
            request=httpx.Request('POST', 'https://provider.invalid/v1/chat/completions'))
    monkeypatch.setattr(httpx, 'post', post)
    client = OpenAICompatibleClient(LLMConfig(provider='openai-compatible', model='test',
        base_url=f'https://{uuid.uuid4().hex}.invalid/v1'))
    observations, reports = elicit(store, run, TrackedClient(client, store, run['run_id']))
    # An invented excerpt after schema correction gets the one citation retry as a second logical call.
    assert len(sent) == (3 if invented_span else 2)
    assert reports[0]['status'] == ('failed' if invented_span else 'completed')
    if invented_span:
        assert observations == []
        assert 'outside this batch' in reports[0]['error']
        assert CITATION_RETRY_NOTE in sent[2]['messages'][0]['content']
        assert CITATION_RETRY_NOTE not in sent[0]['messages'][0]['content']
    else:
        assert len(observations) == 1
        record = record_from_observation(run['run_id'], observations[0])
        assert verify(store, record, run['evidence_ids'])['status'] == 'pass'
    saved = store.get('run', run['run_id'])
    call = saved['model_calls'][0]
    assert call['status'] == 'completed'  # JSON success is distinct from evidence validity.
    assert call['token_usage']['total_tokens'] == 60
    assert call['output_tokens_reserved'] == 16000
    metrics = workflow_metrics(saved)['model_calls']
    assert metrics['count'] == (2 if invented_span else 1) and metrics['http_attempts'] == (3 if invented_span else 2)
    assert metrics['schema_correction_generations'] == 1
    assert metrics['actual_token_usage']['total_tokens'] == (90 if invented_span else 60)
    assert metrics['max_output_tokens_reserved_sum'] == (24000 if invented_span else 16000)
