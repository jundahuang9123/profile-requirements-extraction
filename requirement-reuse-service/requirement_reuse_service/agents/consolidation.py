from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from ..llm.client import LLMClient
from ..llm.extractor import locate_quote
from ..models import (
    AgentContextTrace,
    AgentContribution,
    AgentRoleConfig,
    CandidateRequirement,
    ConsolidationEvent,
    EvidenceUnit,
    ExtractionProvenance,
)
from ..service import (
    detect_duplicate_requirements,
    merge_metadata_actions,
    merge_source_evidence,
    stable_id,
    validate_requirement,
)
from .prompts import consolidation_prompts


class LLMConsolidationDecision(BaseModel):
    source_candidate_ids: list[str]
    action: str
    canonical_statement: str | None = None
    rationale: str
    support_level: str | None = None


class LLMConsolidationResult(BaseModel):
    decisions: list[LLMConsolidationDecision] = Field(default_factory=list)


def consolidate_candidates(
    raw_candidates: list[CandidateRequirement],
    role: AgentRoleConfig,
    agent_run_id: str,
    input_hash: str,
    workflow_id: str,
    workflow_version: str,
    client: LLMClient,
    evidence_units: list[EvidenceUnit],
    context: AgentContextTrace | None = None,
) -> tuple[list[CandidateRequirement], list[ConsolidationEvent], list[str]]:
    """Perform exactly one bounded consolidation pass over preserved raw output."""
    description = client.describe()
    if description.get('provider') == 'mock':
        decisions = deterministic_decisions(raw_candidates)
    else:
        system, user = consolidation_prompts(role, raw_candidates, context)
        generated = client.generate_structured(system=system, user=user, output_model=LLMConsolidationResult)
        decisions = generated.decisions
    candidates, events, warnings = materialize_decisions(
        raw_candidates,
        decisions,
        role,
        agent_run_id,
        input_hash,
        workflow_id,
        workflow_version,
        description.get('model'),
    )
    evidence_by_id = {unit.id: unit for unit in evidence_units}
    for candidate in candidates:
        verified = []
        for evidence in candidate.source_evidence:
            unit = evidence_by_id.get(evidence.evidence_unit_id)
            located = locate_quote(evidence.evidence_text, unit) if unit is not None else None
            if located is None:
                warnings.append(
                    f'consolidated_evidence_discarded:{candidate.id}:{evidence.evidence_unit_id}'
                )
                continue
            start, end, quote = located
            evidence.evidence_text = quote
            evidence.locator = f'{unit.locator or "content"};chars:{start}-{end}'
            verified.append(evidence)
        candidate.source_evidence = verified
        candidate.evidence = [evidence.evidence_text for evidence in verified]
        if candidate.provenance:
            candidate.provenance.evidence_verified = bool(verified)
        validate_requirement(candidate)
    return candidates, events, warnings


def deterministic_decisions(raw_candidates: list[CandidateRequirement]) -> list[LLMConsolidationDecision]:
    decisions: list[LLMConsolidationDecision] = []
    supported = [item for item in raw_candidates if item.support_level != 'unsupported']
    unsupported = [item for item in raw_candidates if item.support_level == 'unsupported']
    duplicate_groups = detect_duplicate_requirements(supported)
    grouped_ids = {requirement_id for group in duplicate_groups for requirement_id in group.requirement_ids}
    for group in duplicate_groups:
        decisions.append(
            LLMConsolidationDecision(
                source_candidate_ids=group.requirement_ids,
                action='merge',
                canonical_statement=group.suggested_merged_statement,
                rationale=group.reason,
            )
        )
    for item in supported:
        if item.id not in grouped_ids:
            decisions.append(
                LLMConsolidationDecision(
                    source_candidate_ids=[item.id],
                    action='keep_separate',
                    canonical_statement=item.normalized_statement,
                    rationale='No deterministic duplicate group was identified; retain as a distinct candidate.',
                )
            )
    for item in unsupported:
        decisions.append(
            LLMConsolidationDecision(
                source_candidate_ids=[item.id],
                action='discard_unsupported',
                rationale='The extraction role classified this auditable raw proposal as unsupported.',
            )
        )
    return decisions


def materialize_decisions(
    raw_candidates: list[CandidateRequirement],
    decisions: list[LLMConsolidationDecision],
    role: AgentRoleConfig,
    agent_run_id: str,
    input_hash: str,
    workflow_id: str,
    workflow_version: str,
    model_id: str | None,
) -> tuple[list[CandidateRequirement], list[ConsolidationEvent], list[str]]:
    by_id = {item.id: item for item in raw_candidates}
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    consolidated: list[CandidateRequirement] = []
    events: list[ConsolidationEvent] = []
    warnings: list[str] = []
    accounted: set[str] = set()

    for index, decision in enumerate(decisions):
        source_ids = list(dict.fromkeys(decision.source_candidate_ids))
        unknown = [source_id for source_id in source_ids if source_id not in by_id]
        if unknown or not source_ids:
            warnings.append(
                f"consolidation_decision_{index + 1}_discarded: unknown or empty source candidate ids: {', '.join(unknown) or 'none supplied'}"
            )
            continue
        if any(source_id in accounted for source_id in source_ids):
            warnings.append(f'consolidation_decision_{index + 1}_discarded: source candidates were already accounted for')
            continue
        sources = [by_id[source_id] for source_id in source_ids]
        action = decision.action if decision.action in {'merge', 'keep_separate', 'discard_unsupported', 'flag_conflict'} else 'flag_conflict'
        if action == 'discard_unsupported' and any(item.support_level != 'unsupported' for item in sources):
            warnings.append(
                f'consolidation_decision_{index + 1}_discarded: supported candidates cannot be discarded as unsupported'
            )
            continue
        accounted.update(source_ids)

        consolidated_id: str | None = None
        if action != 'discard_unsupported':
            representative = max(sources, key=lambda item: (item.confidence, bool(item.source_evidence), item.id))
            statement = (decision.canonical_statement or representative.normalized_statement or representative.description or '').strip()
            if not statement:
                warnings.append(f'consolidation_decision_{index + 1}_discarded: canonical statement is empty')
                accounted.difference_update(source_ids)
                continue
            consolidated_id = stable_id('req', 'agent-consolidated', statement, *sorted(source_ids))
            item = representative.model_copy(deep=True)
            item.id = consolidated_id
            item.raw_statement = statement
            item.normalized_statement = statement
            item.description = statement
            item.origin_kind = 'agent_consolidated'
            item.origin_agent_role = role.id
            item.consolidated_from = source_ids
            item.merged_from = list(representative.merged_from)
            item.contributing_agent_roles = sorted(
                {source.origin_agent_role for source in sources if source.origin_agent_role}
            )
            item.agent_contributions = [
                AgentContribution(
                    agent_run_id=source.provenance.agent_run_id if source.provenance and source.provenance.agent_run_id else agent_run_id,
                    role_id=source.origin_agent_role or 'unknown',
                    source_candidate_id=source.id,
                    contribution_kind='merged' if len(sources) > 1 else 'supported',
                    statement=source.normalized_statement,
                    evidence_unit_ids=[evidence.evidence_unit_id for evidence in source.source_evidence],
                )
                for source in sources
            ]
            item.source_evidence = []
            item.candidate_metadata_actions = []
            for source in sources:
                item.source_evidence = merge_source_evidence(item.source_evidence, source.source_evidence)
                item.candidate_metadata_actions = merge_metadata_actions(
                    item.candidate_metadata_actions, source.candidate_metadata_actions
                )
            item.evidence = [evidence.evidence_text for evidence in item.source_evidence]
            item.support_level = (
                decision.support_level
                if decision.support_level in {'explicit', 'evidence_supported_inference'}
                else 'explicit' if any(source.support_level == 'explicit' for source in sources)
                else 'evidence_supported_inference'
            )
            item.status = 'candidate'
            item.machine_output_frozen = False
            item.machine_original_statement = None
            item.provenance = ExtractionProvenance(
                strategy='multi_agent',
                extractor=f'agent-consolidator/{role.prompt_version}',
                model_id=model_id,
                prompt_version=role.prompt_version,
                created_at=now,
                evidence_verified=bool(item.source_evidence),
                workflow_id=workflow_id,
                workflow_version=workflow_version,
                agent_run_id=agent_run_id,
                agent_role=role.id,
                agent_phase=role.phase,
                input_hash=input_hash,
                source_candidate_ids=source_ids,
            )
            consolidated.append(validate_requirement(item))

        events.append(
            ConsolidationEvent(
                id=stable_id('con', workflow_id, str(index), action, *source_ids),
                source_candidate_ids=source_ids,
                consolidated_requirement_id=consolidated_id,
                action=action,
                rationale=decision.rationale,
                performed_by=role.id,
                created_at=now,
            )
        )

    # Never let a model omission silently erase a raw output. Supported omissions
    # are retained separately; unsupported omissions remain audit-only.
    missing = [item for item in raw_candidates if item.id not in accounted]
    if missing:
        warnings.append(f'consolidation_incomplete: {len(missing)} source candidate(s) were not covered; deterministic retention applied')
        fallback = deterministic_decisions(missing)
        fallback_candidates, fallback_events, fallback_warnings = materialize_decisions(
            missing,
            fallback,
            role,
            agent_run_id,
            input_hash,
            workflow_id,
            workflow_version,
            model_id,
        )
        consolidated.extend(fallback_candidates)
        events.extend(fallback_events)
        warnings.extend(fallback_warnings)

    consolidated.sort(key=lambda item: item.id)
    events.sort(key=lambda item: item.id)
    return consolidated, events, warnings
