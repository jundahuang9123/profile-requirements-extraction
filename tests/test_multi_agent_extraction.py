import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = ROOT / 'requirement-reuse-service'
sys.path.insert(0, str(SERVICE_ROOT))

from requirement_reuse_service.agents.consolidation import deterministic_decisions, materialize_decisions  # noqa: E402
from requirement_reuse_service.agents.orchestrator import compute_input_hash, run_multi_agent_workflow, sha256_json  # noqa: E402
from requirement_reuse_service.agents.roles import WORKFLOW_VERSION, resolve_panel  # noqa: E402
from requirement_reuse_service.llm.client import LLMError, MockLLMClient  # noqa: E402
from requirement_reuse_service.models import AgentContextInput, AnalysisRequest, ArtifactPayload, UserTask  # noqa: E402
from requirement_reuse_service.service import analyze_payload, analyze_payload_rules, extract_evidence_units, stable_id  # noqa: E402


SOURCE = 'Each dataset must carry a license or access rights statement.'


def evidence_id():
    return extract_evidence_units(AnalysisRequest(text=SOURCE))[0].id


def extraction_payload(system: str, _user: str):
    role = system.split('Role id: ', 1)[1].splitlines()[0]
    quote = 'fabricated evidence' if role == 'ifc_bim' else SOURCE
    return {
        'requirements': [{
            'statement': 'A dcat:Dataset must carry a license or access rights statement.',
            'requirement_type': 'access_policy',
            'requirement_scope': 'profile_element',
            'resource_type': 'Dataset',
            'metadata_need': 'describe access and reuse conditions',
            'value_kind': 'uri',
            'obligation': 'mandatory',
            'fair_dimensions': ['A', 'R'],
            'fair_rationale': 'Supports access and reuse decisions.',
            'action': 'reuse_existing_term',
            'candidate_terms': ['dcterms:license'],
            'action_rationale': 'Reuse DCTERMS.',
            'supports_user_tasks': [],
            'evidence': [{'evidence_unit_id': evidence_id(), 'quote': quote}],
            'confidence': 0.8,
            'support_level': 'unsupported' if role == 'minimality_scope' else 'explicit',
        }]
    }


@pytest.fixture
def no_cache(tmp_path, monkeypatch):
    monkeypatch.setenv('RRS_AGENT_CACHE', str(tmp_path / 'cache'))
    monkeypatch.setenv('RRS_AGENT_CONCURRENCY', '3')


def run_panel(client=None, **request_updates):
    request = AnalysisRequest(text=SOURCE, strategy='multi_agent', **request_updates)
    base = analyze_payload_rules(request)
    client = client or MockLLMClient(extraction_payload)
    return run_multi_agent_workflow(request, base, client), client


def test_full_panel_configuration_has_12_independent_and_3_synthesis_roles():
    roles = resolve_panel('full_15')
    assert len(roles) == 15
    assert [role.phase for role in roles].count('extraction') == 12
    assert [role.phase for role in roles].count('consolidation') == 1
    assert [role.phase for role in roles].count('criticism') == 2
    assert len({role.prompt_version for role in roles}) == 15


def test_roles_run_independently_and_raw_provenance_is_preserved(no_cache):
    response, client = run_panel()
    assert response.panel_status == 'completed'
    assert len(response.agent_runs) == 15
    assert len(response.raw_agent_requirements) == 12
    assert len(client.calls) == 12
    for candidate in response.raw_agent_requirements:
        assert candidate.origin_kind == 'agent_extracted'
        assert candidate.origin_agent_role == candidate.provenance.agent_role
        assert candidate.provenance.agent_run_id
        assert candidate.agent_contributions[0].role_id == candidate.origin_agent_role
    extraction_systems = [call['system'] for call in client.calls]
    assert all('cannot see or imitate any other role' in system for system in extraction_systems)
    assert all('SOURCE CANDIDATES' not in call['user'] for call in client.calls)


def test_fabricated_evidence_is_discarded_and_unsupported_remains_auditable(no_cache):
    response, _ = run_panel()
    fabricated = next(item for item in response.raw_agent_requirements if item.origin_agent_role == 'ifc_bim')
    unsupported = next(item for item in response.raw_agent_requirements if item.origin_agent_role == 'minimality_scope')
    assert fabricated.source_evidence == []
    assert fabricated.validation_status == 'missing_evidence'
    assert unsupported.support_level == 'unsupported'
    assert unsupported.id not in {source for event in response.consolidation_events if event.action != 'discard_unsupported' for source in event.source_candidate_ids}
    assert unsupported.id not in {source for item in response.requirements for source in item.consolidated_from}
    assert any('Discarded unverifiable evidence' in warning for warning in response.warnings)


def test_consolidation_retains_sources_and_critics_do_not_mutate_statements(no_cache):
    response, _ = run_panel()
    assert response.requirements
    before = [item.normalized_statement for item in response.requirements]
    assert all(item.consolidated_from for item in response.requirements)
    raw_ids = {item.id for item in response.raw_agent_requirements}
    evidence_ids = {unit.id for unit in response.evidence_units}
    assert all(set(item.consolidated_from) <= raw_ids for item in response.requirements)
    assert all({e.evidence_unit_id for e in item.source_evidence} <= evidence_ids for item in response.requirements)
    assert [item.normalized_statement for item in response.requirements] == before
    assert all(finding.requirement_id in {item.id for item in response.requirements} for finding in response.critique_findings)


def test_failed_role_preserves_successful_outputs_and_marks_full_panel_incomplete(no_cache):
    def fails_one(system, user):
        if 'Role id: aas_idta' in system:
            raise LLMError('simulated role failure')
        return extraction_payload(system, user)

    response, _ = run_panel(MockLLMClient(fails_one))
    assert response.panel_status == 'incomplete_full_panel'
    assert next(run for run in response.agent_runs if run.role_id == 'aas_idta').status == 'failed'
    assert len(response.raw_agent_requirements) == 11
    assert {item.origin_agent_role for item in response.raw_agent_requirements} == {
        role.id for role in resolve_panel('full_15') if role.phase == 'extraction' and role.id != 'aas_idta'
    }


def test_output_order_is_deterministic_and_cache_supports_one_role_rerun(no_cache):
    response, client = run_panel()
    ids = [item.id for item in response.raw_agent_requirements]
    assert ids == [
        item.id
        for role in resolve_panel('full_15') if role.phase == 'extraction'
        for item in sorted([candidate for candidate in response.raw_agent_requirements if candidate.origin_agent_role == role.id], key=lambda candidate: candidate.id)
    ]
    cached, _ = run_panel(client)
    assert len(client.calls) == 12
    assert all(run.cache_hit for run in cached.agent_runs if run.phase == 'extraction')
    rerun, _ = run_panel(client, rerun_role_ids=['dcat_reuse'])
    assert len(client.calls) == 13
    assert [item.id for item in rerun.raw_agent_requirements] == ids
    assert next(run for run in rerun.agent_runs if run.role_id == 'dcat_reuse').cache_hit is False


def test_hashes_change_for_corpus_task_model_prompt_and_workflow():
    roles = resolve_panel('pilot_core')
    base = AnalysisRequest(text=SOURCE, strategy='multi_agent', panel_preset='pilot_core')
    base_hash = compute_input_hash(base, roles, {'provider': 'mock', 'model': 'm1'}, WORKFLOW_VERSION)
    assert base_hash != compute_input_hash(base.model_copy(update={'text': SOURCE + ' changed'}), roles, {'provider': 'mock', 'model': 'm1'}, WORKFLOW_VERSION)
    assert base_hash != compute_input_hash(base.model_copy(update={'user_tasks': [UserTask(id='t1', statement='Find licensed data?')]}), roles, {'provider': 'mock', 'model': 'm1'}, WORKFLOW_VERSION)
    assert base_hash != compute_input_hash(base, roles, {'provider': 'mock', 'model': 'm2'}, WORKFLOW_VERSION)
    changed_role = roles[0].model_copy(update={'prompt_version': roles[0].prompt_version + '-changed'})
    assert sha256_json({'role': roles[0].model_dump()}) != sha256_json({'role': changed_role.model_dump()})
    assert base_hash != compute_input_hash(base, roles, {'provider': 'mock', 'model': 'm1'}, WORKFLOW_VERSION + '-changed')
    context_payload = base.model_copy(update={
        'agent_contexts': [AgentContextInput(
            role_id='standards_conformance',
            background='Treat normative verbs as obligation signals.',
        )],
    })
    assert base_hash != compute_input_hash(context_payload, roles, {'provider': 'mock', 'model': 'm1'}, WORKFLOW_VERSION)


def test_role_context_rag_and_handoffs_are_traceable(no_cache):
    context = AgentContextInput(
        role_id='standards_conformance',
        background='Use the supplied DCAT-AP background to interpret obligations, never as evidence.',
        rag_queries=['dataset license obligation'],
        rag_artifact_names=['dcat-guidance.md'],
        rag_material=(
            'Coordinator note: distinguish a mandatory licence obligation from optional guidance.\n\n'
            'Second note: keep the requirement at dcat:Dataset level.'
        ),
        rag_top_k=3,
    )
    response, client = run_panel(
        artifacts=[ArtifactPayload(
            name='dcat-guidance.md',
            media_type='text/markdown',
            content='DCAT guidance says dataset license metadata supports reuse decisions.',
        )],
        agent_contexts=[context],
    )

    assert len(response.agent_contexts) == 15
    standards_context = next(item for item in response.agent_contexts if item.role_id == 'standards_conformance')
    assert standards_context.background == context.background
    assert standards_context.context_hash
    assert standards_context.rag_queries == context.rag_queries
    assert standards_context.retrieved_items
    assert any(item.source_kind == 'corpus_artifact' and item.eligible_as_evidence for item in standards_context.retrieved_items)
    assert any(item.source_kind == 'supplemental_material' and not item.eligible_as_evidence for item in standards_context.retrieved_items)

    standards_call = next(call for call in client.calls if 'Role id: standards_conformance' in call['system'])
    assert context.background in standards_call['system']
    assert 'MUST NOT be cited as evidence' in standards_call['system']
    assert standards_context.context_hash in standards_call['system']

    assert len(response.workflow_trace) == 30
    assert [event.sequence for event in response.workflow_trace] == list(range(1, 31))
    assert all(event.context_hash for event in response.workflow_trace)
    consolidation = next(run for run in response.agent_runs if run.role_id == 'consolidation_conflict')
    assert len(consolidation.dependency_role_ids) == 12
    assert set(consolidation.input_artifact_ids) == {item.id for item in response.raw_agent_requirements}
    for role_id in ['grounding_scope_critic', 'reuse_minimality_critic']:
        critic = next(run for run in response.agent_runs if run.role_id == role_id)
        assert critic.dependency_role_ids == ['consolidation_conflict']
        assert set(critic.input_artifact_ids) == {item.id for item in response.requirements}


def test_strategy_used_is_truthful_when_multi_agent_provider_is_missing(monkeypatch):
    for variable in ['RRS_LLM_PROVIDER', 'RRS_LLM_BASE_URL', 'RRS_LLM_MODEL', 'ANTHROPIC_API_KEY']:
        monkeypatch.delenv(variable, raising=False)
    response = analyze_payload(AnalysisRequest(text=SOURCE, strategy='multi_agent'))
    assert response.strategy == 'rules'
    assert response.panel_status == 'incomplete_full_panel'
    assert any('strategy_used=rules' in warning for warning in response.warnings)


def test_unknown_role_configuration_is_a_clear_validation_error(no_cache):
    with pytest.raises(ValueError, match='Unknown agent role'):
        analyze_payload(AnalysisRequest(
            text=SOURCE,
            strategy='multi_agent',
            agent_role_ids=['not-a-configured-role'],
        ))
