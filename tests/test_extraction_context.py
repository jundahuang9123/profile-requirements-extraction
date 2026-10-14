"""Extraction input contracts, using scripted output and no provider requests."""
import json
from copy import deepcopy

import pytest

from test_workflow_span_extraction import corpus, payload
from requirement_reuse_service.llm.client import MockLLMClient
from requirement_reuse_service.workflow import engine
from requirement_reuse_service.workflow.models import RunRequest
from requirement_reuse_service.workflow.storage import digest


def extraction_run(corpus, output_form='needs'):
    store, initial = corpus
    run = engine.new_run(store, RunRequest(snapshot_id=initial['snapshot_id'], strategy='multi_agent',
        output_form=output_form, role_ids=['consumer_discovery'], base_profile_id='dcat-ap-2.0.1'))
    return store, run


def answer(data, output_form):
    result = payload(data)
    if output_form == 'needs':
        for row in result['observations']:
            row.pop('extension_kind')
            row.pop('base_property')
    return result


@pytest.mark.parametrize('output_form', ['needs', 'candidates'])
def test_extraction_uses_role_description_without_discovery_citations_or_history(corpus, output_form):
    store, run = extraction_run(corpus, output_form)
    description = dict(role_id='consumer_discovery', label='Consumers', stakeholders=['Consumers'],
        basis='documented', purpose='Discover data.', focus_questions=['Can users find data?'],
        rationale='Consumers discover datasets.', evidence_links=[{'evidence_id': 'eu-discovery-only'}],
        citations=['eu-other-discovery'], candidate_ids=['historic-candidate'],
        lineage_candidate_ids=['historic-lineage'], task_ids=['old-task'], future_audit='audit-only')
    run['role_manifest']['selected_roles'] = [description]
    run['role_manifest']['manifest_hash'] = digest({k: v for k, v in run['role_manifest'].items()
                                                  if k != 'manifest_hash'})
    frozen_manifest = deepcopy(run['role_manifest'])
    client = MockLLMClient(lambda system, user: answer(json.loads(user), output_form))
    observations, reports = engine.elicit(store, run, client)
    assert observations and reports[0]['status'] == 'completed'
    data = json.loads(client.calls[0]['user'])
    assert data['stakeholder_perspective'] == {key: description[key] for key in (
        'label', 'stakeholders', 'basis', 'purpose', 'focus_questions', 'rationale')}
    assert all(marker not in client.calls[0]['user'] for marker in (
        'eu-discovery-only', 'eu-other-discovery', 'historic-candidate', 'historic-lineage', 'audit-only'))
    assert run['role_manifest'] == frozen_manifest
    assert reports[0]['prompt_version'] == 'rq1-independent-elicitation-v3.3'
