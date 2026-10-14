#!/usr/bin/env python3
"""Compare v3.2 and v3.3 packing on a saved input export, without model calls.

Reads only the frozen run configuration, snapshot tasks and evidence units.
Generated/reference requirements, qualifications and model outputs are unused.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'requirement-reuse-service'))
from requirement_reuse_service.workflow.engine import (
    EXTRACTION_BATCH_CHARS, EXTRACTION_BATCH_UNITS, EXTRACTION_UNIT_CHARS,
    extraction_batches, extraction_role_context, run_extraction_base_context)
from requirement_reuse_service.workflow.citations import elicitation_batch
from requirement_reuse_service.workflow.role_selection import panel_roles
from requirement_reuse_service.workflow.storage import canonical, digest


def legacy_batches(units, context):
    batches = []
    for unit in units:
        single, _ = elicitation_batch([unit])
        if len(canonical({**context, 'evidence_units': single})) > EXTRACTION_UNIT_CHARS:
            raise ValueError('Legacy singleton exceeds the complete-input budget.')
        trial, _ = elicitation_batch([*batches[-1], unit] if batches else [unit])
        if batches and (len(batches[-1]) >= EXTRACTION_BATCH_UNITS or
                        len(canonical({**context, 'evidence_units': trial})) > EXTRACTION_BATCH_CHARS):
            batches.append([unit])
        elif batches:
            batches[-1].append(unit)
        else:
            batches.append([unit])
    return batches


def count_batches(data):
    run, snapshot = data['run'], data['snapshot']
    by_id = {unit['evidence_id']: unit for unit in data['evidence_units']}
    units = [by_id[eid] for eid in run['evidence_ids']]
    base = run_extraction_base_context(run)
    rows = []
    for role in panel_roles(run):
        before = {'role': role.model_dump(mode='json'), 'user_tasks': snapshot['user_tasks']}
        if base:
            before['base_profile'] = base
        selected = next((item for item in run['role_manifest'].get('selected_roles', [])
                         if item['role_id'] == role.id), None)
        if selected:
            before['stakeholder_perspective'] = selected
        after = extraction_role_context(run, role, snapshot, base)
        old, new = legacy_batches(units, before), extraction_batches(units, after)
        rows.append({'role_id': role.id, 'label': role.label, 'evidence_units': len(units),
                     'before_fixed_context_chars': len(canonical(before)),
                     'after_fixed_context_chars': len(canonical(after)),
                     'before_batches': len(old), 'after_batches': len(new),
                     'before_singleton_batches': sum(len(batch) == 1 for batch in old),
                     'after_singleton_batches': sum(len(batch) == 1 for batch in new)})
    return {'run_id': run['run_id'], 'snapshot_id': snapshot['snapshot_id'],
            'input_hash': digest({'units': units, 'tasks': snapshot['user_tasks'],
                                  'manifest': run['role_manifest']}),
            'comparison': 'v3.2 full-context target versus v3.3 items 1–3',
            'planned_initial_batches_only': True, 'model_calls': 0,
            'evidence_units': len(units), 'roles': rows,
            'before_total': sum(row['before_batches'] for row in rows),
            'after_total': sum(row['after_batches'] for row in rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path, help='Saved run export or input-only JSON snapshot')
    args = parser.parse_args()
    print(json.dumps(count_batches(json.loads(args.input.read_text())), indent=2))


if __name__ == '__main__':
    main()
