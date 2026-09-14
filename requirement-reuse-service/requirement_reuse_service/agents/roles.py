from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from ..models import AgentRoleConfig


CONFIG_PATH = Path(__file__).resolve().parents[2] / 'config' / 'agent_roles.yaml'
WORKFLOW_VERSION = 'rrs-multi-agent-v1'


class RoleConfigurationError(ValueError):
    """Raised when the versioned role configuration is missing or inconsistent."""


@lru_cache(maxsize=1)
def load_role_configuration() -> dict[str, Any]:
    try:
        data = yaml.safe_load(CONFIG_PATH.read_text(encoding='utf-8'))
    except Exception as exc:
        raise RoleConfigurationError(f'Unable to load agent role configuration at {CONFIG_PATH}: {exc}') from exc
    if not isinstance(data, dict):
        raise RoleConfigurationError('Agent role configuration must be a YAML mapping.')
    roles = [AgentRoleConfig.model_validate(item) for item in data.get('roles', [])]
    ids = [role.id for role in roles]
    if len(ids) != len(set(ids)):
        raise RoleConfigurationError('Agent role ids must be unique.')
    if data.get('workflow_version') != WORKFLOW_VERSION:
        raise RoleConfigurationError(
            f"Expected workflow_version={WORKFLOW_VERSION}, found {data.get('workflow_version')!r}."
        )
    presets = data.get('presets') or {}
    for name, preset in presets.items():
        unknown = sorted(set(preset.get('role_ids') or []) - set(ids))
        if unknown:
            raise RoleConfigurationError(f"Preset '{name}' references unknown role ids: {', '.join(unknown)}")
    full_roles = [role for role in roles if role.id in (presets.get('full_15') or {}).get('role_ids', [])]
    phase_counts = {
        phase: sum(role.phase == phase for role in full_roles)
        for phase in ('extraction', 'consolidation', 'criticism')
    }
    if len(full_roles) != 15 or phase_counts != {'extraction': 12, 'consolidation': 1, 'criticism': 2}:
        raise RoleConfigurationError(
            'full_15 must contain exactly 12 extraction, 1 consolidation, and 2 criticism roles.'
        )
    return {**data, 'roles': roles}


def resolve_panel(preset_name: str, extraction_role_ids: list[str] | None = None) -> list[AgentRoleConfig]:
    config = load_role_configuration()
    presets = config.get('presets') or {}
    if preset_name not in presets:
        raise RoleConfigurationError(
            f"Unknown panel preset '{preset_name}'. Available presets: {', '.join(sorted(presets))}"
        )
    by_id = {role.id: role for role in config['roles']}
    preset_ids = list(presets[preset_name].get('role_ids') or [])
    if extraction_role_ids:
        unknown = sorted(set(extraction_role_ids) - set(by_id))
        if unknown:
            raise RoleConfigurationError(f"Unknown agent role id(s): {', '.join(unknown)}")
        wrong_phase = sorted(role_id for role_id in extraction_role_ids if by_id[role_id].phase != 'extraction')
        if wrong_phase:
            raise RoleConfigurationError(
                f"agent_role_ids may select extraction roles only: {', '.join(wrong_phase)}"
            )
        preset_ids = [
            *extraction_role_ids,
            *(role_id for role_id in preset_ids if by_id[role_id].phase != 'extraction'),
        ]
    return sorted((by_id[role_id] for role_id in preset_ids if by_id[role_id].enabled), key=lambda role: role.panel_order)


def role_health() -> dict[str, Any]:
    try:
        config = load_role_configuration()
        return {
            'workflow_version': config['workflow_version'],
            'configured_role_ids': [role.id for role in config['roles']],
            'presets': sorted((config.get('presets') or {}).keys()),
            'load_errors': [],
        }
    except RoleConfigurationError as exc:
        return {
            'workflow_version': WORKFLOW_VERSION,
            'configured_role_ids': [],
            'presets': [],
            'load_errors': [str(exc)],
        }
