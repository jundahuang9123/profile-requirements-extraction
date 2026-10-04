"""Offline descriptive metrics. Expert judgements are never inferred from token overlap."""
from collections import Counter


def _summary(records):
    n = len(records)
    grounded = sum(r.get('verification', {}).get('status') == 'pass' for r in records)
    return {'count': n, 'grounded_count': grounded, 'grounded_rate': grounded / n if n else None,
        'support_distribution': dict(Counter((r.get('qualification') or {}).get('support', 'pending') for r in records)),
        'state_distribution': dict(Counter(r['lifecycle_state'] for r in records)),
        'quality_findings': dict(Counter(f['criterion'] for r in records for f in (r.get('qualification') or {}).get('findings', []))),
        'task_links': sorted({task for r in records for task in r.get('supports_user_tasks', [])})}


def workflow_metrics(run: dict) -> dict:
    frozen = run.get('machine_snapshot', {})
    raw = frozen.get('requirements', [])
    machine = [r for r in raw if r['revision_id'] in frozen.get('active_revision_ids', [])]
    current = [r for r in run['requirements'] if r['revision_id'] in run['active_revision_ids']]
    accepted = [r for r in current if r['lifecycle_state'] == 'accepted']
    calls = run.get('model_calls', [])
    return {'schema_version': 'rq1-workflow-evaluation-v2', 'run_id': run['run_id'],
        'snapshot_id': run['snapshot_id'], 'strategy': run['strategy'], 'implementation_hash': run['implementation_hash'],
        'machine': _summary(machine), 'current_review': _summary(current), 'human_accepted': _summary(accepted),
        'machine_revision_ids': [r['revision_id'] for r in machine],
        'human_added_revision_ids': [rid for d in run['decisions'] if d['action'] == 'add' for rid in d['result_revision_ids']],
        'role_status': {r['role_id']: r['status'] for r in frozen.get('role_runs', [])},
        'raw_proposals_by_role': dict(Counter(o['role_id'] for o in frozen.get('observations', []))),
        'review_actions': dict(Counter(d['action'] for d in run['decisions'])),
        'deliberation': {'selected': len(run['deliberations']), 'message_count': sum(len(c['messages']) for c in run['deliberations']),
            'stop_reasons': dict(Counter(c.get('stop_reason') or 'pending' for c in run['deliberations']))},
        'model_calls': {'count': len(calls), 'failures': sum(c['status'] == 'failed' for c in calls),
            'latency_seconds_sum': sum(c['latency_seconds'] for c in calls),
            'max_output_tokens_reserved_sum': sum(c.get('max_output_tokens') or 0 for c in calls),
            'actual_token_usage': None, 'monetary_cost': None},
        'limitations': ['Task-link presence is not expert-assessed competency-question coverage.',
            'No precision/recall without an independently adjudicated reference set and equivalence mapping.',
            'Token caps are reservations; actual provider usage and monetary cost are unavailable.',
            'Sequential call latency sum is not wall-clock duration when perspectives run concurrently.']}
