from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from ..llm.client import LLMClient
from .prompts import REVISION_PROMPT_VERSION


class LLMRevisionSuggestion(BaseModel):
    requirement_id: str
    proposed_statement: str
    rationale: str = ''


class LLMRevisionResult(BaseModel):
    suggestions: list[LLMRevisionSuggestion] = Field(default_factory=list)


def propose_revisions(
    feedback_items: list[dict[str, Any]],
    client: LLMClient | None,
) -> tuple[dict[str, str], str]:
    """One bounded revision pass; no approval or mutation occurs here."""
    if client is None:
        return {
            item['requirement_id']: item['proposed_statements'][0]
            for item in feedback_items if item.get('proposed_statements')
        }, 'controlled-human-feedback-selection'
    if client.describe().get('provider') == 'mock':
        return {
            item['requirement_id']: item['proposed_statements'][0]
            for item in feedback_items if item.get('proposed_statements')
        }, f'role-conditioned-agent:{REVISION_PROMPT_VERSION}'
    system = f"""You are a bounded post-evaluation revision role.
Prompt version: {REVISION_PROMPT_VERSION}.
Summative evaluation is closed. Propose at most one clear, atomic statement for each supplied item,
using only the selected human expert feedback. Preserve the original statement in the record layer.
Do not add evidence, approve requirements, or decide consensus."""
    user = 'SELECTED EXPERT FEEDBACK:\n' + json.dumps(feedback_items, indent=2, sort_keys=True)
    output = client.generate_structured(system=system, user=user, output_model=LLMRevisionResult)
    known = {item['requirement_id'] for item in feedback_items}
    suggestions = {
        item.requirement_id: item.proposed_statement.strip()
        for item in output.suggestions
        if item.requirement_id in known and item.proposed_statement.strip()
    }
    return suggestions, f'role-conditioned-agent:{REVISION_PROMPT_VERSION}'
