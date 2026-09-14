from __future__ import annotations

import re

from pydantic import BaseModel, Field

from ..llm.client import LLMClient
from ..models import AgentContextTrace, AgentRoleConfig, CandidateRequirement, CritiqueFinding
from ..service import stable_id, term_matches_resource
from .prompts import critic_prompts


class LLMCritiqueFinding(BaseModel):
    requirement_id: str
    category: str
    severity: str
    message: str
    evidence_unit_ids: list[str] = Field(default_factory=list)
    suggested_action: str | None = None


class LLMCritiqueResult(BaseModel):
    findings: list[LLMCritiqueFinding] = Field(default_factory=list)


ALLOWED_CATEGORIES = {
    'grounding', 'scope', 'atomicity', 'obligation', 'duplicate', 'conflict',
    'reuse', 'minimality', 'resource_compatibility', 'other',
}
ALLOWED_SEVERITIES = {'info', 'warning', 'blocking'}


def critique_candidates(
    candidates: list[CandidateRequirement],
    role: AgentRoleConfig,
    client: LLMClient,
    context: AgentContextTrace | None = None,
) -> tuple[list[CritiqueFinding], list[str]]:
    if client.describe().get('provider') == 'mock':
        generated = deterministic_findings(candidates, role)
    else:
        system, user = critic_prompts(role, candidates, context)
        generated = client.generate_structured(system=system, user=user, output_model=LLMCritiqueResult).findings
    return validate_findings(candidates, role, generated)


def deterministic_findings(
    candidates: list[CandidateRequirement],
    role: AgentRoleConfig,
) -> list[LLMCritiqueFinding]:
    findings: list[LLMCritiqueFinding] = []
    for item in candidates:
        evidence_ids = [evidence.evidence_unit_id for evidence in item.source_evidence]
        statement = item.normalized_statement or ''
        if role.id == 'grounding_scope_critic':
            if not item.source_evidence:
                findings.append(LLMCritiqueFinding(
                    requirement_id=item.id,
                    category='grounding',
                    severity='blocking',
                    message='No verified evidence remains for this consolidated candidate.',
                    suggested_action='Exclude from the default expert evaluation queue unless a coordinator explicitly includes it.',
                ))
            if item.support_level == 'evidence_supported_inference':
                findings.append(LLMCritiqueFinding(
                    requirement_id=item.id,
                    category='grounding',
                    severity='info',
                    message='The candidate is a bounded evidence-supported inference rather than an explicit obligation.',
                    evidence_unit_ids=evidence_ids,
                ))
            evidence_text = ' '.join(e.evidence_text.lower() for e in item.source_evidence)
            if item.normalized_intent.obligation_hint == 'mandatory' and not re.search(r'\b(must|shall|required|mandatory)\b', evidence_text):
                findings.append(LLMCritiqueFinding(
                    requirement_id=item.id,
                    category='obligation',
                    severity='warning',
                    message='Mandatory wording is not directly visible in the verified evidence.',
                    evidence_unit_ids=evidence_ids,
                    suggested_action='Ask reviewers to assess the obligation level separately.',
                ))
            if statement.lower().count(' and ') >= 2:
                findings.append(LLMCritiqueFinding(
                    requirement_id=item.id,
                    category='atomicity',
                    severity='warning',
                    message='The statement may combine multiple independently testable obligations.',
                    suggested_action='Consider a controlled split after summative evaluation.',
                ))
        elif role.id == 'reuse_minimality_critic':
            for action in item.candidate_metadata_actions:
                for term in action.candidate_terms:
                    if not term_matches_resource(term, item.normalized_intent.resource_type):
                        findings.append(LLMCritiqueFinding(
                            requirement_id=item.id,
                            category='resource_compatibility',
                            severity='blocking',
                            message=f'{term} may not apply to {item.normalized_intent.resource_type}.',
                            suggested_action='Review the target resource or choose an in-domain reusable term.',
                        ))
                if action.action == 'create_extension' and any(not term.startswith('cx:') for term in action.candidate_terms):
                    findings.append(LLMCritiqueFinding(
                        requirement_id=item.id,
                        category='reuse',
                        severity='warning',
                        message='The extension action includes a non-extension candidate term.',
                        suggested_action='Check registered-term reuse before proposing an extension.',
                    ))
                if len(action.candidate_terms) > 1 and not item.requires_multiple_elements:
                    findings.append(LLMCritiqueFinding(
                        requirement_id=item.id,
                        category='minimality',
                        severity='info',
                        message='Candidate terms are alternatives unless the requirement explicitly needs multiple profile elements.',
                    ))
    return findings


def validate_findings(
    candidates: list[CandidateRequirement],
    role: AgentRoleConfig,
    generated: list[LLMCritiqueFinding],
) -> tuple[list[CritiqueFinding], list[str]]:
    by_id = {item.id: item for item in candidates}
    findings: list[CritiqueFinding] = []
    warnings: list[str] = []
    for index, finding in enumerate(generated):
        requirement = by_id.get(finding.requirement_id)
        if requirement is None:
            warnings.append(f'{role.id}_finding_{index + 1}_discarded: unknown requirement id')
            continue
        known_evidence = {evidence.evidence_unit_id for evidence in requirement.source_evidence}
        evidence_ids = [evidence_id for evidence_id in finding.evidence_unit_ids if evidence_id in known_evidence]
        if len(evidence_ids) != len(finding.evidence_unit_ids):
            warnings.append(f'{role.id}_finding_{index + 1}: unknown evidence ids were removed')
        category = finding.category if finding.category in ALLOWED_CATEGORIES else 'other'
        severity = finding.severity if finding.severity in ALLOWED_SEVERITIES else 'warning'
        findings.append(CritiqueFinding(
            id=stable_id('crit', role.id, requirement.id, category, finding.message),
            requirement_id=requirement.id,
            critic_role_id=role.id,
            category=category,
            severity=severity,
            message=finding.message,
            evidence_unit_ids=evidence_ids,
            suggested_action=finding.suggested_action,
        ))
    findings.sort(key=lambda item: (item.requirement_id, item.category, item.id))
    return findings, warnings
