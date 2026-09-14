from __future__ import annotations

import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..llm.client import LLMClient
from ..llm.extractor import LLMExtractionResult, convert_requirement
from ..models import (
    AgentContextTrace,
    AgentContribution,
    AgentRoleConfig,
    AgentRunRecord,
    AnalysisRequest,
    AnalysisResponse,
    CandidateRequirement,
    EvidenceUnit,
    ExtractionProvenance,
    WorkflowTraceEvent,
)
from ..service import build_funnel_metrics, detect_duplicate_requirements, stable_id
from .consolidation import consolidate_candidates
from .context import assemble_agent_context
from .critics import critique_candidates
from .prompts import extraction_prompts
from .roles import WORKFLOW_VERSION, load_role_configuration, resolve_panel


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()


def run_multi_agent_workflow(
    payload: AnalysisRequest,
    base_response: AnalysisResponse,
    client: LLMClient,
) -> AnalysisResponse:
    """Run the configured panel once per stage and preserve every completed layer."""
    config = load_role_configuration()
    workflow_version = payload.workflow_version or config['workflow_version']
    if workflow_version != WORKFLOW_VERSION:
        raise ValueError(
            f"Unsupported workflow_version '{workflow_version}'; configured version is {WORKFLOW_VERSION}."
        )
    roles = resolve_panel(payload.panel_preset, payload.agent_role_ids)
    configured_role_ids = {role.id for role in config['roles']}
    unknown_context_roles = sorted({context.role_id for context in payload.agent_contexts} - configured_role_ids)
    if unknown_context_roles:
        raise ValueError(f"Unknown agent context role id(s): {', '.join(unknown_context_roles)}")
    extraction_roles = [role for role in roles if role.phase == 'extraction']
    consolidation_roles = [role for role in roles if role.phase == 'consolidation']
    critic_roles = [role for role in roles if role.phase == 'criticism']
    evidence_units = list(base_response.evidence_units)
    role_contexts = {
        role.id: assemble_agent_context(payload, evidence_units, role)
        for role in roles
    }
    model_configuration = client.describe()
    input_hash = compute_input_hash(payload, roles, model_configuration, workflow_version)
    workflow_id = stable_id('workflow', workflow_version, input_hash, payload.panel_preset)
    run_records: dict[str, AgentRunRecord] = {}
    role_outputs: dict[str, list[CandidateRequirement]] = {}
    warnings: list[str] = list(base_response.warnings)

    defaults = config.get('defaults') or {}
    concurrency = max(1, int(os.environ.get('RRS_AGENT_CONCURRENCY', defaults.get('concurrency_limit', 4))))
    with ThreadPoolExecutor(max_workers=min(concurrency, max(1, len(extraction_roles)))) as executor:
        futures = {
            executor.submit(
                run_extraction_role,
                payload,
                evidence_units,
                role,
                client,
                workflow_id,
                workflow_version,
                input_hash,
                role_contexts[role.id],
                role.id in payload.rerun_role_ids,
                int(role.max_output_tokens or defaults.get('max_output_tokens', 5000)),
            ): role
            for role in extraction_roles
        }
        for future in as_completed(futures):
            role = futures[future]
            try:
                run_record, candidates, role_warnings = future.result()
            except Exception as exc:  # retain other independent role outputs
                now = utc_now()
                run_record = AgentRunRecord(
                    id=stable_id('agent-run', workflow_id, role.id),
                    role_id=role.id,
                    phase=role.phase,
                    status='failed',
                    model_id=model_configuration.get('model'),
                    prompt_version=role.prompt_version,
                    started_at=now,
                    completed_at=now,
                    warnings=[str(exc)],
                    input_artifact_ids=[
                        *[unit.id for unit in evidence_units],
                        *[task.id for task in payload.user_tasks],
                    ],
                    context_trace=role_contexts[role.id],
                )
                candidates = []
                role_warnings = [f'{role.id}: {exc}']
            run_records[role.id] = run_record
            role_outputs[role.id] = candidates
            warnings.extend(role_warnings)

    raw_candidates = [
        candidate
        for role in extraction_roles
        for candidate in sorted(role_outputs.get(role.id, []), key=lambda item: item.id)
    ]

    consolidated: list[CandidateRequirement] = []
    consolidation_events = []
    if consolidation_roles:
        role = consolidation_roles[0]
        run_id = stable_id('agent-run', workflow_id, role.id)
        started_at = utc_now()
        try:
            consolidated, consolidation_events, role_warnings = consolidate_candidates(
                raw_candidates,
                role,
                run_id,
                input_hash,
                workflow_id,
                workflow_version,
                client,
                evidence_units,
                role_contexts[role.id],
            )
            status = 'completed'
        except Exception as exc:
            status = 'failed'
            role_warnings = [f'{role.id}: {exc}']
        run_records[role.id] = AgentRunRecord(
            id=run_id,
            role_id=role.id,
            phase=role.phase,
            status=status,
            model_id=model_configuration.get('model'),
            prompt_version=role.prompt_version,
            started_at=started_at,
            completed_at=utc_now(),
            candidate_requirement_ids=[item.id for item in consolidated],
            warnings=role_warnings,
            dependency_role_ids=[item.id for item in extraction_roles],
            input_artifact_ids=[item.id for item in raw_candidates],
            output_artifact_ids=[
                *[item.id for item in consolidated],
                *[event.id for event in consolidation_events],
            ],
            context_trace=role_contexts[role.id],
        )
        warnings.extend(role_warnings)
    else:
        consolidated = [item.model_copy(deep=True) for item in raw_candidates if item.support_level != 'unsupported']

    critique_findings = []
    for role in critic_roles:
        run_id = stable_id('agent-run', workflow_id, role.id)
        started_at = utc_now()
        if consolidation_roles and run_records[consolidation_roles[0].id].status != 'completed':
            run_records[role.id] = AgentRunRecord(
                id=run_id,
                role_id=role.id,
                phase=role.phase,
                status='skipped',
                model_id=model_configuration.get('model'),
                prompt_version=role.prompt_version,
                started_at=started_at,
                completed_at=utc_now(),
                warnings=['Skipped because the consolidation role did not complete.'],
                dependency_role_ids=[consolidation_roles[0].id],
                input_artifact_ids=[item.id for item in consolidated],
                context_trace=role_contexts[role.id],
            )
            continue
        try:
            findings, role_warnings = critique_candidates(
                consolidated,
                role,
                client,
                role_contexts[role.id],
            )
            critique_findings.extend(findings)
            status = 'completed'
        except Exception as exc:
            findings = []
            role_warnings = [f'{role.id}: {exc}']
            status = 'failed'
        run_records[role.id] = AgentRunRecord(
            id=run_id,
            role_id=role.id,
            phase=role.phase,
            status=status,
            model_id=model_configuration.get('model'),
            prompt_version=role.prompt_version,
            started_at=started_at,
            completed_at=utc_now(),
            candidate_requirement_ids=sorted({finding.requirement_id for finding in findings}),
            warnings=role_warnings,
            dependency_role_ids=(
                [consolidation_roles[0].id]
                if consolidation_roles
                else [extraction_role.id for extraction_role in extraction_roles]
            ),
            input_artifact_ids=[item.id for item in consolidated],
            output_artifact_ids=[finding.id for finding in findings],
            context_trace=role_contexts[role.id],
        )
        warnings.extend(role_warnings)

    findings_by_requirement: dict[str, list] = {}
    for finding in critique_findings:
        findings_by_requirement.setdefault(finding.requirement_id, []).append(finding)
    for requirement in consolidated:
        requirement_findings = findings_by_requirement.get(requirement.id, [])
        requirement.critique_finding_ids = [finding.id for finding in requirement_findings]
        for finding in requirement_findings:
            requirement.agent_contributions.append(
                AgentContribution(
                    agent_run_id=run_records[finding.critic_role_id].id,
                    role_id=finding.critic_role_id,
                    source_candidate_id=requirement.id,
                    contribution_kind='challenged',
                    evidence_unit_ids=finding.evidence_unit_ids,
                    notes=[f'{finding.severity}:{finding.category}: {finding.message}'],
                )
            )

    ordered_runs = [run_records[role.id] for role in roles if role.id in run_records]
    workflow_trace = build_workflow_trace(workflow_id, ordered_runs)
    expected_full = payload.panel_preset == 'full_15' and not payload.agent_role_ids
    all_completed = len(ordered_runs) == len(roles) and all(run.status == 'completed' for run in ordered_runs)
    panel_status = 'completed' if all_completed else 'incomplete_full_panel' if expected_full else 'completed'
    duplicate_groups = detect_duplicate_requirements(consolidated)
    funnel_metrics = build_funnel_metrics(evidence_units, consolidated, duplicate_groups)
    funnel_metrics.update({
        'raw_agent_candidate_count': len(raw_candidates),
        'consolidated_candidate_count': len(consolidated),
        'unsupported_raw_candidate_count': sum(item.support_level == 'unsupported' for item in raw_candidates),
        'blocking_critique_count': sum(finding.severity == 'blocking' for finding in critique_findings),
        'completed_role_count': sum(run.status == 'completed' for run in ordered_runs),
        'configured_role_count': len(roles),
    })
    return base_response.model_copy(update={
        'strategy': 'multi_agent',
        'study_setup': {
            **base_response.study_setup,
            'study_mode': payload.study_mode,
            'study_phase': payload.study_phase,
            'panel_preset': payload.panel_preset,
            'selected_extraction_role_ids': [role.id for role in extraction_roles],
            'research_condition': (
                'multi_agent_full_15'
                if payload.panel_preset == 'full_15' and not payload.agent_role_ids and len(roles) == 15
                else 'multi_agent_pilot'
            ),
            'held_out_notice': (
                'Expert ratings, expert reference requirements, expected answer sets, manually curated gold '
                'requirements, and post-run corrections are held out from extraction.'
            ),
            'agent_context_boundary': (
                'Role background and supplemental RAG are recorded analytical context. Only verified corpus '
                'evidence may substantiate candidate requirements.'
            ),
            'configured_agent_context_count': sum(
                bool(context.background or context.rag_queries or context.retrieved_items)
                for context in role_contexts.values()
            ),
        },
        'requirements': consolidated,
        'duplicate_groups': duplicate_groups,
        'funnel_metrics': funnel_metrics,
        'warnings': warnings,
        'workflow_id': workflow_id,
        'workflow_version': workflow_version,
        'study_mode': payload.study_mode,
        'study_phase': payload.study_phase,
        'input_hash': input_hash,
        'panel_preset': payload.panel_preset,
        'panel_status': panel_status,
        'extraction_agent_count': len(extraction_roles),
        'synthesis_agent_count': len(consolidation_roles) + len(critic_roles),
        'total_agent_count': len(roles),
        'agent_runs': ordered_runs,
        'raw_agent_requirements': raw_candidates,
        'consolidation_events': consolidation_events,
        'critique_findings': critique_findings,
        'agent_contexts': [role_contexts[role.id] for role in roles],
        'workflow_trace': workflow_trace,
    })


def run_extraction_role(
    payload: AnalysisRequest,
    evidence_units: list[EvidenceUnit],
    role: AgentRoleConfig,
    client: LLMClient,
    workflow_id: str,
    workflow_version: str,
    input_hash: str,
    context: AgentContextTrace,
    force_rerun: bool,
    max_output_tokens: int,
) -> tuple[AgentRunRecord, list[CandidateRequirement], list[str]]:
    run_id = stable_id('agent-run', workflow_id, role.id)
    started_at = utc_now()
    model_id = client.describe().get('model')
    cache_key = sha256_json({
        'input_hash': input_hash,
        'model': client.describe(),
        'role': role.model_dump(mode='json'),
        'prompt_version': role.prompt_version,
        'workflow_version': workflow_version,
    })
    if not force_rerun:
        cached = read_cache(cache_key)
        if cached is not None:
            candidates = [CandidateRequirement.model_validate(item) for item in cached.get('candidates', [])]
            warnings = list(cached.get('warnings', []))
            return AgentRunRecord(
                id=run_id,
                role_id=role.id,
                phase=role.phase,
                status='completed',
                model_id=model_id,
                prompt_version=role.prompt_version,
                started_at=started_at,
                completed_at=utc_now(),
                candidate_requirement_ids=[item.id for item in candidates],
                warnings=warnings,
                cache_hit=True,
                input_artifact_ids=[
                    *context.shared_evidence_unit_ids,
                    *[task.id for task in payload.user_tasks],
                ],
                output_artifact_ids=[item.id for item in candidates],
                context_trace=context,
            ), candidates, warnings

    system, user, prompt_warnings = extraction_prompts(role, evidence_units, payload.user_tasks, context)
    result = client.generate_structured(
        system=system,
        user=user,
        output_model=LLMExtractionResult,
        max_tokens=max_output_tokens,
    )
    evidence_by_id = {unit.id: unit for unit in evidence_units}
    task_ids = {task.id for task in payload.user_tasks}
    warnings = list(prompt_warnings)
    candidates: list[CandidateRequirement] = []
    created_at = utc_now()
    for item in result.requirements:
        provenance = ExtractionProvenance(
            strategy='multi_agent',
            extractor=f'role-conditioned-agent/{role.prompt_version}',
            model_id=model_id,
            prompt_version=role.prompt_version,
            created_at=created_at,
            workflow_id=workflow_id,
            workflow_version=workflow_version,
            agent_run_id=run_id,
            agent_role=role.id,
            agent_phase=role.phase,
            input_hash=input_hash,
        )
        candidate = convert_requirement(item, evidence_by_id, task_ids, warnings, provenance)
        if candidate is None:
            continue
        candidate.id = stable_id(
            'req', 'agent', role.id, candidate.normalized_statement or candidate.id,
            *(e.evidence_unit_id for e in candidate.source_evidence[:4]),
        )
        candidate.origin_kind = 'agent_extracted'
        candidate.origin_agent_role = role.id
        candidate.contributing_agent_roles = [role.id]
        candidate.agent_contributions = [AgentContribution(
            agent_run_id=run_id,
            role_id=role.id,
            source_candidate_id=candidate.id,
            contribution_kind='originated',
            statement=candidate.normalized_statement,
            evidence_unit_ids=[e.evidence_unit_id for e in candidate.source_evidence],
        )]
        candidates.append(candidate)
    candidates.sort(key=lambda item: item.id)
    write_cache(cache_key, candidates, warnings)
    run_record = AgentRunRecord(
        id=run_id,
        role_id=role.id,
        phase=role.phase,
        status='completed',
        model_id=model_id,
        prompt_version=role.prompt_version,
        started_at=started_at,
        completed_at=utc_now(),
        candidate_requirement_ids=[item.id for item in candidates],
        warnings=warnings,
        input_artifact_ids=[
            *context.shared_evidence_unit_ids,
            *[task.id for task in payload.user_tasks],
        ],
        output_artifact_ids=[item.id for item in candidates],
        context_trace=context,
    )
    return run_record, candidates, warnings


def compute_input_hash(
    payload: AnalysisRequest,
    roles: list[AgentRoleConfig],
    model_configuration: dict[str, str],
    workflow_version: str,
) -> str:
    active_role_ids = {role.id for role in roles}
    return sha256_json({
        'source_corpus_id': payload.source_corpus_id,
        'text': payload.text,
        'artifacts': [artifact.model_dump(mode='json') for artifact in payload.artifacts],
        'user_tasks': [task.model_dump(mode='json') for task in payload.user_tasks],
        'role_configuration': [role.model_dump(mode='json') for role in roles],
        'model_configuration': model_configuration,
        'workflow_version': workflow_version,
        'panel_preset': payload.panel_preset,
        'agent_contexts': [
            context.model_dump(mode='json')
            for context in sorted(payload.agent_contexts, key=lambda item: item.role_id)
            if context.role_id in active_role_ids
        ],
    })


def build_workflow_trace(
    workflow_id: str,
    runs: list[AgentRunRecord],
) -> list[WorkflowTraceEvent]:
    """Create a deterministic, exportable trace of context assembly and each bounded handoff."""
    events: list[WorkflowTraceEvent] = []
    sequence = 1
    for run in runs:
        context = run.context_trace
        events.append(WorkflowTraceEvent(
            id=stable_id('trace', workflow_id, run.role_id, 'context'),
            sequence=sequence,
            event_type='context_assembled',
            phase=run.phase,
            role_id=run.role_id,
            agent_run_id=run.id,
            timestamp=run.started_at,
            dependency_role_ids=run.dependency_role_ids,
            input_artifact_ids=run.input_artifact_ids,
            context_hash=context.context_hash if context else None,
            details={
                'shared_evidence_count': len(context.shared_evidence_unit_ids) if context else 0,
                'retrieved_context_count': len(context.retrieved_items) if context else 0,
                'background_supplied': bool(context and context.background),
                'retrieval_queries': list(context.rag_queries) if context else [],
            },
        ))
        sequence += 1
        event_type = (
            'cache_reused' if run.cache_hit
            else 'run_completed' if run.status == 'completed'
            else 'run_failed' if run.status == 'failed'
            else 'run_skipped'
        )
        events.append(WorkflowTraceEvent(
            id=stable_id('trace', workflow_id, run.role_id, event_type),
            sequence=sequence,
            event_type=event_type,
            phase=run.phase,
            role_id=run.role_id,
            agent_run_id=run.id,
            timestamp=run.completed_at,
            dependency_role_ids=run.dependency_role_ids,
            input_artifact_ids=run.input_artifact_ids,
            output_artifact_ids=run.output_artifact_ids,
            context_hash=context.context_hash if context else None,
            details={
                'status': run.status,
                'model_id': run.model_id,
                'prompt_version': run.prompt_version,
                'candidate_requirement_count': len(run.candidate_requirement_ids),
                'warning_count': len(run.warnings),
            },
        ))
        sequence += 1
    return events


def cache_dir() -> Path:
    return Path(os.environ.get('RRS_AGENT_CACHE', '.rrs-agent-cache'))


def read_cache(cache_key: str) -> dict[str, Any] | None:
    path = cache_dir() / f'{cache_key}.json'
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return None


def write_cache(cache_key: str, candidates: list[CandidateRequirement], warnings: list[str]) -> None:
    directory = cache_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f'{cache_key}.json'
        temporary = directory / f'.{cache_key}.tmp'
        temporary.write_text(canonical_json({
            'candidates': [item.model_dump(mode='json', exclude_none=True) for item in candidates],
            'warnings': warnings,
        }), encoding='utf-8')
        temporary.replace(path)
    except OSError:
        # Cache failures must never invalidate a successful role output.
        return


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')
