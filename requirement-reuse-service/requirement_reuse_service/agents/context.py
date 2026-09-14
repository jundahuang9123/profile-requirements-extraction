from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from ..models import (
    AgentContextInput,
    AgentContextTrace,
    AgentRoleConfig,
    AnalysisRequest,
    EvidenceUnit,
    RetrievedContextItem,
)


TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_:\-]{2,}")
STOP_WORDS = {
    'and', 'are', 'for', 'from', 'has', 'have', 'into', 'should', 'that', 'the',
    'their', 'this', 'was', 'what', 'when', 'which', 'with', 'would',
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def context_id(prefix: str, *parts: str) -> str:
    digest = sha256_text('|'.join(parts))[:20]
    return f'{prefix}-{digest}'


def assemble_agent_context(
    payload: AnalysisRequest,
    evidence_units: list[EvidenceUnit],
    role: AgentRoleConfig,
) -> AgentContextTrace:
    """Build the exact role context that will be injected into one agent call."""
    declared = next(
        (item for item in payload.agent_contexts if item.role_id == role.id),
        AgentContextInput(role_id=role.id),
    )
    requested_names = list(dict.fromkeys(name.strip() for name in declared.rag_artifact_names if name.strip()))
    requested_set = set(requested_names)
    candidates: list[RetrievedContextItem] = []

    for unit in evidence_units:
        if unit.artifact_name not in requested_set:
            continue
        candidates.append(RetrievedContextItem(
            id=context_id('rag-corpus', role.id, unit.id),
            source_kind='corpus_artifact',
            source_ref=unit.artifact_name,
            content=unit.content,
            content_hash=sha256_text(unit.content),
            evidence_unit_id=unit.id,
            eligible_as_evidence=True,
        ))

    for index, chunk in enumerate(chunk_material(declared.rag_material), start=1):
        source_ref = f'{role.id}:supplemental:{index}'
        candidates.append(RetrievedContextItem(
            id=context_id('rag-supplemental', source_ref, chunk),
            source_kind='supplemental_material',
            source_ref=source_ref,
            content=chunk,
            content_hash=sha256_text(chunk),
            eligible_as_evidence=False,
        ))

    query_tokens = tokens(' '.join(declared.rag_queries))
    for index, candidate in enumerate(candidates):
        candidate_tokens = tokens(candidate.content)
        candidate.score = (
            round(len(query_tokens & candidate_tokens) / max(1, len(query_tokens)), 4)
            if query_tokens
            else round(1 / (index + 1), 4)
        )
    candidates.sort(key=lambda item: (-item.score, item.source_kind, item.source_ref, item.id))
    retrieved = candidates[:declared.rag_top_k]
    background = declared.background.strip()
    trace_payload = {
        'role_id': role.id,
        'background': background,
        'rag_queries': declared.rag_queries,
        'requested_rag_artifact_names': requested_names,
        'shared_evidence_unit_ids': [unit.id for unit in evidence_units],
        'retrieved_items': [item.model_dump(mode='json') for item in retrieved],
    }
    return AgentContextTrace(
        role_id=role.id,
        context_hash=sha256_text(canonical_json(trace_payload)),
        background=background,
        background_hash=sha256_text(background) if background else None,
        rag_queries=list(declared.rag_queries),
        requested_rag_artifact_names=requested_names,
        shared_evidence_unit_ids=[unit.id for unit in evidence_units],
        retrieved_items=retrieved,
    )


def context_prompt_block(context: AgentContextTrace | None) -> str:
    if context is None or not (context.background or context.retrieved_items or context.rag_queries):
        return ''
    retrieved = []
    for item in context.retrieved_items:
        evidence_label = (
            f'corpus evidence id {item.evidence_unit_id}'
            if item.eligible_as_evidence and item.evidence_unit_id
            else 'supplemental only; MUST NOT be cited as evidence'
        )
        retrieved.append(
            f'[RAG {item.id} | {item.source_kind} | {item.source_ref} | {evidence_label}]\n{item.content}'
        )
    return f"""

ROLE-SPECIFIC CONTEXT PACKAGE (hash {context.context_hash})
Background supplied by the coordinator:
{context.background or '[none]'}

Retrieval queries:
{chr(10).join(f'- {query}' for query in context.rag_queries) or '- none'}

Retrieved context:
{chr(10).join(retrieved) or '[none]'}

CONTEXT BOUNDARY
{context.boundary_notice}
Do not convert supplemental material into a requirement unless the same claim is supported by a verified
SOURCE CORPUS evidence unit. Preserve the distinction between analytical background and evidence.
"""


def chunk_material(value: str, chunk_size: int = 1_600) -> list[str]:
    chunks: list[str] = []
    for paragraph in re.split(r'\n\s*\n+', value.strip()):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        for start in range(0, len(paragraph), chunk_size):
            chunk = paragraph[start:start + chunk_size].strip()
            if chunk:
                chunks.append(chunk)
    return chunks


def tokens(value: str) -> set[str]:
    return {token for token in TOKEN_RE.findall(value.lower()) if token not in STOP_WORDS}
