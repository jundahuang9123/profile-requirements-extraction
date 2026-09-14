#!/usr/bin/env python3
"""Run requirement extraction over a corpus folder and save a YAML requirement set.

Examples:
    # Rule-based baseline over the bundled sample corpus
    python scripts/extract_requirements.py examples/requirement-corpus --strategy rules --name baseline-run

    # LLM-assisted extraction (configure provider via env, see docs/requirement-extraction.md)
    ANTHROPIC_API_KEY=... python scripts/extract_requirements.py examples/requirement-corpus \
        --strategy llm --name llm-pilot

    # Any OpenAI-compatible endpoint, e.g. a local Ollama model
    RRS_LLM_PROVIDER=openai-compatible RRS_LLM_BASE_URL=http://localhost:11434/v1 \
        RRS_LLM_MODEL=qwen3 python scripts/extract_requirements.py corpus/ --strategy llm --name local-run

Competency questions / user tasks are read from any file in the corpus named
*competency* or *tasks* (one statement per line; lines starting with '#' are
ignored). All other files become artifacts.
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'requirement-reuse-service'))

from requirement_reuse_service.models import AnalysisRequest, ArtifactPayload, RequirementSetSaveRequest, UserTask  # noqa: E402
from requirement_reuse_service.registry import save_requirement_set, store_dir  # noqa: E402
from requirement_reuse_service.service import analyze_payload  # noqa: E402

TEXT_SUFFIXES = {'.txt', '.md', '.json', '.jsonld', '.ttl', '.rdf', '.owl', '.ifc', '.ifcspf', '.nt', '.xml', '.yaml', '.yml'}
TASK_MARKERS = ('competency', 'task')


def main() -> int:
    parser = argparse.ArgumentParser(description='Extract profile-design requirements from a corpus of domain artifacts.')
    parser.add_argument('corpus', type=Path, help='Corpus directory or a single artifact file')
    parser.add_argument('--strategy', choices=['rules', 'llm', 'hybrid', 'multi_agent'], default='rules')
    parser.add_argument('--panel-preset', choices=['full_15', 'pilot_core', 'extraction_12'], default='full_15')
    parser.add_argument('--study-mode', choices=['formative', 'summative'], default='formative')
    parser.add_argument('--name', default='extraction-run', help='Name for the saved requirement set')
    parser.add_argument('--model', default=None, help='Override the LLM model id for this run')
    parser.add_argument('--no-save', action='store_true', help='Print results without saving a requirement set')
    args = parser.parse_args()

    files = sorted(path for path in ([args.corpus] if args.corpus.is_file() else args.corpus.rglob('*')) if path.is_file())
    if not files:
        print(f'No files found in {args.corpus}', file=sys.stderr)
        return 1

    artifacts: list[ArtifactPayload] = []
    user_tasks: list[UserTask] = []
    for path in files:
        if any(marker in path.name.lower() for marker in TASK_MARKERS):
            user_tasks.extend(read_user_tasks(path))
            continue
        artifacts.append(read_artifact(path))

    print(f'Corpus: {len(artifacts)} artifact(s), {len(user_tasks)} user task(s); strategy={args.strategy}')
    request = AnalysisRequest(
        artifacts=artifacts,
        user_tasks=user_tasks,
        strategy=args.strategy,
        llm_model=args.model,
        panel_preset=args.panel_preset,
        study_mode=args.study_mode,
    )
    analysis = analyze_payload(request)

    print(f'\nStrategy used: {analysis.strategy}')
    print(f'Requirements:  {len(analysis.requirements)}')
    for requirement in analysis.requirements:
        evidence = len(requirement.source_evidence)
        tasks = ','.join(requirement.supports_user_tasks) or '-'
        verified = requirement.provenance.evidence_verified if requirement.provenance else None
        print(f'  [{requirement.requirement_type:>22}] {requirement.title}')
        print(f'      evidence={evidence} verified={verified} fair={"".join(requirement.fair_dimensions) or "-"} tasks={tasks}')
    if analysis.warnings:
        print('\nWarnings:')
        for warning in analysis.warnings:
            print(f'  - {warning}')

    if not args.no_save:
        info = save_requirement_set(
            RequirementSetSaveRequest(name=args.name, description=f'CLI extraction run over {args.corpus}', analysis=analysis)
        )
        print(f'\nSaved requirement set {info.id} ({info.requirement_count} requirements) to {store_dir()}/')
    return 0


def read_user_tasks(path: Path) -> list[UserTask]:
    tasks: list[UserTask] = []
    for index, line in enumerate(path.read_text(encoding='utf-8', errors='replace').splitlines(), start=1):
        statement = line.strip()
        if not statement or statement.startswith('#'):
            continue
        kind = 'competency_question' if statement.endswith('?') else 'user_task'
        tasks.append(UserTask(id=f'{path.stem}-{index}', statement=statement, kind=kind, source=path.name))
    return tasks


def read_artifact(path: Path) -> ArtifactPayload:
    if path.suffix.lower() in TEXT_SUFFIXES:
        return ArtifactPayload(name=path.name, content=path.read_text(encoding='utf-8', errors='replace'))
    return ArtifactPayload(
        name=path.name,
        content=base64.b64encode(path.read_bytes()).decode('ascii'),
        content_encoding='base64',
    )


if __name__ == '__main__':
    sys.exit(main())
