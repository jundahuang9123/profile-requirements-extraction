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
    usage_calls = [c for c in calls if isinstance(c.get('token_usage'), dict)]
    recorded_usage = {name: sum(c['token_usage'].get(name, 0) for c in usage_calls)
                      for name in ('prompt_tokens', 'completion_tokens', 'total_tokens')
                      if any(name in c['token_usage'] for c in usage_calls)}
    complete_usage = bool(calls) and all(isinstance(c.get('token_usage'), dict) and
        all(name in c['token_usage'] for name in ('prompt_tokens', 'completion_tokens', 'total_tokens')) for c in calls)
    transport_calls = [c for c in calls if 'http_attempts' in c.get('transport', {})]
    selection_calls = [c for c in calls if c.get('output_contract') in {'RoleCandidates', 'RoleCitationCorrections', 'RolePanel'}]
    manifest = run.get('role_manifest') or {}
    return {'schema_version': 'rq1-workflow-evaluation-v2', 'run_id': run['run_id'],
        'snapshot_id': run['snapshot_id'], 'strategy': run['strategy'], 'implementation_hash': run['implementation_hash'],
        'elicitation_policy_version': run.get('elicitation_policy_version'),
        'machine': _summary(machine), 'current_review': _summary(current), 'human_accepted': _summary(accepted),
        'machine_revision_ids': [r['revision_id'] for r in machine],
        'human_added_revision_ids': [rid for d in run['decisions'] if d['action'] == 'add' for rid in d['result_revision_ids']],
        'role_status': {r['role_id']: r['status'] for r in frozen.get('role_runs', [])},
        'role_selection': {'mode': manifest.get('mode', 'legacy_manual'), 'status': manifest.get('status'),
            'manifest_hash': manifest.get('manifest_hash'), 'selected_count': len(manifest.get('selected_roles', [])),
            'basis_counts': dict(Counter(r['basis'] for r in manifest.get('selected_roles', []))),
            'processed_evidence_count': len(manifest.get('processed_evidence_ids', [])),
            'model_calls': len(selection_calls), 'failures': sum(c['status'] == 'failed' for c in selection_calls),
            'latency_seconds_sum': sum(c['latency_seconds'] for c in selection_calls),
            'max_output_tokens_reserved_sum': sum(c.get('output_tokens_reserved', c.get('max_output_tokens') or 0) for c in selection_calls)},
        'raw_proposals_by_role': dict(Counter(o['role_id'] for o in frozen.get('observations', []))),
        'review_actions': dict(Counter(d['action'] for d in run['decisions'])),
        'deliberation': {'mode': run['request'].get('discussion', 'automatic'),
            'selected': len(run['deliberations']), 'message_count': sum(len(c['messages']) for c in run['deliberations']),
            'stop_reasons': dict(Counter(c.get('stop_reason') or 'pending' for c in run['deliberations']))},
        'model_calls': {'count': len(calls), 'failures': sum(c['status'] == 'failed' for c in calls),
            'http_attempts': sum(len(c['transport']['http_attempts']) for c in transport_calls) if len(transport_calls) == len(calls) else None,
            'recorded_http_attempts': sum(len(c['transport']['http_attempts']) for c in transport_calls),
            'calls_without_transport_audit': len(calls) - len(transport_calls),
            'rate_limit_retries': sum(a.get('action') == 'rate_limit_retry' for c in calls
                                     for a in c.get('transport', {}).get('http_attempts', [])),
            'transient_retries': sum(a.get('action') == 'transient_retry' for c in calls
                                    for a in c.get('transport', {}).get('http_attempts', [])),
            'schema_correction_generations': sum(a.get('purpose') == 'schema_correction' for c in calls
                                                for a in c.get('transport', {}).get('generation_attempts', [])),
            'retry_wait_seconds': sum(c.get('transport', {}).get('retry_wait_seconds', 0) for c in calls),
            'queue_seconds_sum': sum(c.get('transport', {}).get('queue_seconds', 0) for c in calls),
            'latency_seconds_sum': sum(c['latency_seconds'] for c in calls),
            'max_output_tokens_reserved_sum': sum(c.get('output_tokens_reserved', c.get('max_output_tokens') or 0) for c in calls),
            'actual_token_usage': recorded_usage if complete_usage else None,
            'recorded_token_usage': recorded_usage or None,
            'calls_without_token_usage': len(calls) - len(usage_calls),
            'monetary_cost': None},
        'limitations': ['Task-link presence is not expert-assessed competency-question coverage.',
            'No precision/recall without an independently adjudicated reference set and equivalence mapping.',
            'Token caps are reservations. Usage is measured only when the provider reports it; partial recorded totals are not complete run usage. Monetary cost is unavailable.',
            'Sequential call latency sum is not wall-clock duration when perspectives run concurrently.']}
