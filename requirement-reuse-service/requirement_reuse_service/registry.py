from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .models import (
    RequirementSet,
    RequirementSetInfo,
    RequirementSetSaveRequest,
)


def store_dir() -> Path:
    """Directory for persisted requirement sets (git-friendly YAML files)."""
    return Path(os.environ.get('RRS_REQUIREMENT_STORE', 'requirement-sets'))


def save_requirement_set(request: RequirementSetSaveRequest) -> RequirementSetInfo:
    requirements = list(request.requirements)
    user_tasks = list(request.user_tasks)
    strategy = None
    if request.analysis is not None:
        strategy = request.analysis.strategy
        if not requirements:
            requirements = list(request.analysis.requirements)
        if not user_tasks:
            user_tasks = list(request.analysis.user_tasks)

    created_at = datetime.now(timezone.utc).isoformat(timespec='seconds')
    set_id = f"{created_at[:19].replace(':', '').replace('-', '')}-{slugify(request.name)}"
    requirement_set = RequirementSet(
        id=set_id,
        name=request.name,
        description=request.description,
        created_at=created_at,
        strategy=strategy,
        requirements=requirements,
        user_tasks=user_tasks,
        analysis=request.analysis,
    )

    directory = store_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f'{set_id}.yaml'
    with path.open('w', encoding='utf-8') as handle:
        yaml.safe_dump(
            requirement_set.model_dump(mode='json', exclude_none=True),
            handle,
            sort_keys=False,
            allow_unicode=True,
            width=120,
        )
    return RequirementSetInfo(
        id=set_id,
        name=request.name,
        description=request.description,
        created_at=created_at,
        strategy=strategy,
        requirement_count=len(requirements),
    )


def list_requirement_sets() -> list[RequirementSetInfo]:
    directory = store_dir()
    if not directory.exists():
        return []
    infos: list[RequirementSetInfo] = []
    for path in sorted(directory.glob('*.yaml')):
        try:
            requirement_set = load_yaml(path)
        except Exception:
            continue
        infos.append(
            RequirementSetInfo(
                id=requirement_set.id,
                name=requirement_set.name,
                description=requirement_set.description,
                created_at=requirement_set.created_at,
                strategy=requirement_set.strategy,
                requirement_count=len(requirement_set.requirements),
            )
        )
    return infos


def load_requirement_set(set_id: str) -> RequirementSet | None:
    path = store_dir() / f'{slug_path(set_id)}.yaml'
    if not path.exists():
        return None
    return load_yaml(path)


def load_yaml(path: Path) -> RequirementSet:
    with path.open('r', encoding='utf-8') as handle:
        data = yaml.safe_load(handle)
    return RequirementSet.model_validate(data)


def slugify(value: str) -> str:
    slug = re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')
    return slug[:60] or 'requirement-set'


def slug_path(set_id: str) -> str:
    # Defensive: ids are generated server-side, but never allow path traversal.
    return re.sub(r'[^A-Za-z0-9_-]', '', set_id)
