from __future__ import annotations

import json

from ..llm.extractor import SYSTEM_PROMPT, build_user_prompt
from ..models import AgentContextTrace, AgentRoleConfig, CandidateRequirement, EvidenceUnit, UserTask
from .context import context_prompt_block


CONSOLIDATION_PROMPT_VERSION = 'rrs-consolidation-conflict-v1'
GROUNDING_CRITIC_PROMPT_VERSION = 'rrs-grounding-scope-critic-v1'
REUSE_CRITIC_PROMPT_VERSION = 'rrs-reuse-minimality-critic-v1'
REVISION_PROMPT_VERSION = 'rrs-revision-v1'


def extraction_prompts(
    role: AgentRoleConfig,
    evidence_units: list[EvidenceUnit],
    user_tasks: list[UserTask],
    context: AgentContextTrace | None = None,
) -> tuple[str, str, list[str]]:
    user_prompt, warnings = build_user_prompt(evidence_units, user_tasks)
    role_prompt = f"""

ANALYTICAL ROLE (prompt version {role.prompt_version})
Role id: {role.id}
Role label: {role.label}
Purpose: {role.purpose}
Focus questions:
{_bullets(role.focus_questions)}
Include:
{_bullets(role.include)}
Exclude:
{_bullets(role.exclude)}

This role is one independent extraction perspective. You cannot see or imitate any other role's output.
Do not claim expertise or decision authority. Return candidate requirements only.
"""
    return SYSTEM_PROMPT + role_prompt + context_prompt_block(context), user_prompt, warnings


def consolidation_prompts(
    role: AgentRoleConfig,
    candidates: list[CandidateRequirement],
    context: AgentContextTrace | None = None,
) -> tuple[str, str]:
    system = f"""You are the bounded consolidation role in a role-conditioned agent panel.
Prompt version: {role.prompt_version}.
Use only the supplied source candidates and their evidence ids. Frequency is not proof.
Every decision must name source_candidate_ids. Never approve a requirement, invent evidence,
erase raw candidates, or conceal a conflict. Output one pass only."""
    payload = [
        {
            'id': item.id,
            'statement': item.normalized_statement,
            'support_level': item.support_level,
            'role_id': item.origin_agent_role,
            'evidence_unit_ids': [e.evidence_unit_id for e in item.source_evidence],
            'requirement_type': item.requirement_type,
            'resource_type': item.normalized_intent.resource_type,
        }
        for item in candidates
    ]
    return system + context_prompt_block(context), 'SOURCE CANDIDATES:\n' + json.dumps(payload, indent=2, sort_keys=True)


def critic_prompts(
    role: AgentRoleConfig,
    candidates: list[CandidateRequirement],
    context: AgentContextTrace | None = None,
) -> tuple[str, str]:
    system = f"""You are an independent bounded critic in a role-conditioned agent panel.
Prompt version: {role.prompt_version}. Purpose: {role.purpose}
Focus: {'; '.join(role.focus_questions)}
Return structured findings only. Never mutate, delete, reject, or approve a candidate.
Reference only supplied requirement ids and evidence ids."""
    payload = [
        {
            'id': item.id,
            'statement': item.normalized_statement,
            'support_level': item.support_level,
            'requirement_type': item.requirement_type,
            'resource_type': item.normalized_intent.resource_type,
            'obligation': item.normalized_intent.obligation_hint,
            'candidate_actions': [action.model_dump(mode='json') for action in item.candidate_metadata_actions],
            'evidence': [
                {'evidence_unit_id': evidence.evidence_unit_id, 'quote': evidence.evidence_text}
                for evidence in item.source_evidence
            ],
        }
        for item in candidates
    ]
    return system + context_prompt_block(context), 'CONSOLIDATED CANDIDATES:\n' + json.dumps(payload, indent=2, sort_keys=True)


def _bullets(items: list[str]) -> str:
    return '\n'.join(f'- {item}' for item in items) or '- none'
