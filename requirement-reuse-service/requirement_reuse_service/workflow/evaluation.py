"""Offline descriptive metrics. Expert judgements are never inferred from token overlap."""
from collections import Counter


def base_check_metrics(run: dict, frozen: dict | None = None) -> dict:
    """Descriptive counts; a base classification is not an expert judgement."""
    frozen = frozen or {}
    audits = frozen.get('base_check_audit', run.get('base_check_audit', []))
    checks = [entry['base_check'] for entry in audits if entry.get('base_check')]
    aside = frozen.get('set_aside_observations', run.get('set_aside_observations', []))
    records = frozen.get('requirements', run.get('requirements', []))
    active = frozen.get('active_revision_ids', run.get('active_revision_ids'))
    kept = ([r for r in records if r['revision_id'] in active] if active is not None
            else [r for r in records if not r.get('parent_revision_ids')])
    source_groups = Counter()
    for record in kept:
        check = record.get('base_check') or {}
        groups = set(check.get('evidence_source_groups', []))
        if not groups:
            continue  # Legacy records have no measured source grouping.
        group = ('mobility' if 'mobility' in groups else 'inspire_geodcat' if 'inspire_geodcat' in groups
                 else 'base_only' if groups == {'base_only'} else 'other_generic')
        source_groups[group] += 1
    return {'policy_version': run.get('base_check_policy_version'),
        'registry_policy_version': run.get('base_registry_policy_version'),
        'base_profile_id': run.get('base_profile_id'), 'base_profile_sha256': run.get('base_profile_sha256'),
        'by_relation': dict(Counter(c['relation'] for c in checks)),
        'by_resolved_via': dict(Counter(c['resolved_via'] for c in checks)),
        'set_aside_inherited': sum(item['reason'] == 'inherited_from_base' for item in aside),
        'kept_by_evidence_source_group': dict(source_groups)}


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
    aside = frozen.get('set_aside_observations', run.get('set_aside_observations', []))
    observations = {o['observation_id']: o for o in frozen.get('observations', run.get('observations', []))}
    consolidation_events = frozen.get('consolidation_events', run.get('consolidation_events', []))
    grouping_calls = [c for c in calls if c.get('output_contract') == 'SemanticGrouping']
    semantic_events = [e for e in consolidation_events if e.get('action') == 'semantic_merge']
    return {'schema_version': 'rq1-workflow-evaluation-v2', 'run_id': run['run_id'],
        'snapshot_id': run['snapshot_id'], 'strategy': run['strategy'], 'implementation_hash': run['implementation_hash'],
        'elicitation_policy_version': run.get('elicitation_policy_version'),
        'derived_from': run.get('derived_from'),
        'extraction_reused': bool(run.get('derived_from')),
        'assessments_reused': run.get('metrics', {}).get('assessments_reused', 0),
        'normalization_policy_version': run.get('normalization_policy_version'),
        'base_check': base_check_metrics(run, frozen),
        'needs': needs_metrics(run, frozen),
        'set_aside': {'count': len(aside), 'by_role': dict(Counter(o['role_id'] for o in aside)),
            'by_reason': dict(Counter(o['reason'] for o in aside)),
            'by_support_label': dict(Counter(observations.get(o['observation_id'], {}).get('support_level', 'unknown') for o in aside))},
        'consolidation': {
            'mode': 'semantic' if (run.get('consolidation_policy_version') or '').startswith('rq1-semantic-consolidation-') else 'exact',
            'policy_version': run.get('consolidation_policy_version') or 'legacy-exact',
            'input_records': sum(not r.get('parent_revision_ids') for r in raw), 'review_items': len(machine),
            'merged_groups': len({e['group_id'] for e in semantic_events}) + sum(
                e.get('action') == 'equivalent_merge' for e in consolidation_events),
            'obligation_conflicts': sum(c['kind'] == 'obligation' for c in frozen.get('conflicts', [])),
            'attached_failed_duplicates': len({rid for e in semantic_events for rid in e.get('attached_failed', [])}),
            'fallback_chunks': sum(e.get('action') == 'semantic_grouping_unavailable' for e in consolidation_events),
            'grouping_calls': len(grouping_calls), 'grouping_failures': sum(c['status'] == 'failed' for c in grouping_calls),
            'merged_assessments_reused': sum(e.get('assessment_reused', False) for e in semantic_events),
            'grouping_latency_seconds_sum': sum(c.get('latency_seconds', 0) for c in grouping_calls)},
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
            'Semantic grouping is a model judgment; report consolidation quality only against independently annotated duplicate groups.',
            'No precision/recall without an independently adjudicated reference set and equivalence mapping.',
            'Token caps are reservations. Usage is measured only when the provider reports it; partial recorded totals are not complete run usage. Monetary cost is unavailable.',
            'Sequential call latency sum is not wall-clock duration when perspectives run concurrently.']}



def needs_metrics(run, frozen=None):
    if run['request'].get('output_form')!='needs': return {'enabled':False}
    frozen=frozen or {};records=frozen.get('requirements',run['requirements'])
    steps=frozen.get('need_steps',run.get('need_steps',{}))
    asides=frozen.get('set_aside_observations',run.get('set_aside_observations',[]))
    mapping={'SemanticGrouping':'grouping','NeedStatements':'need_statement','NeedGrounding':'rewrite_critic',
             'NeedMembership':'need_membership','NeedClassifications':'classification','NeedUseCaseLinks':'scoping','UseCaseCritic':'scope_critic',
             'Qualification':'assessment','NeedSpanElicitationResult':'extraction','Turn':'discussion',
             'RoleCandidates':'role_selection','RolePanel':'role_selection','RoleCitationCorrections':'role_selection'}
    calls_by_step={}
    for call in run.get('model_calls',[]):
        step=mapping.get(call['output_contract'],'other')
        entry=calls_by_step.setdefault(step,{'calls':0,'failures':0,'latency_seconds_sum':0})
        entry['calls']+=1;entry['failures']+=call['status']=='failed';entry['latency_seconds_sum']+=call.get('latency_seconds',0)
    validations=Counter()
    for chunk in run.get('need_chunks',{}).values():
        for attempt in chunk.get('attempts',[]):
            if attempt.get('validation_errors') or attempt.get('error'): validations[chunk['step']]+=1
    return {'enabled':True,'policies':run.get('needs_policies',{}),'scoping':run['request'].get('scoping'),
        'counts':{'proposals':len(frozen.get('observations',run['observations'])),
                  'set_aside_by_reason':dict(Counter(a['reason'] for a in asides)),
                  'candidates':sum(not r.get('parent_revision_ids') for r in records),
                  'source_passed_candidates':steps.get('source_check',{}).get('passed_count'),
                  'needs':steps.get('need_statement',{}).get('need_count'),
                  'after_classification':steps.get('classification',{}).get('retained_count'),
                  'after_scoping':steps.get('scoping',{}).get('retained_count'),
                  'kept_needs':len(frozen.get('active_revision_ids',run['active_revision_ids']))},
        'steps':steps,'calls_by_step':calls_by_step,'rejected_generation_outputs_by_step':dict(validations),
        'base_catalogue_review':(run.get('base_needs_catalogue') or {}).get('review'),
        'limitations':['Counts describe processing, not accuracy, recall or measured human effort.',
                       'One support assessment may use up to two bounded generations for schema/cutoff recovery.',
                       'Source checks are deterministic and do not establish semantic entailment.']}
