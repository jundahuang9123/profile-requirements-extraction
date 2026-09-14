#!/usr/bin/env python3
"""RQ1 evaluation harness: compare extraction strategies over a corpus.

Examples:
    # Rule-based baseline only (offline)
    python scripts/evaluate_rq1.py examples/requirement-corpus --strategies rules \
        --out evaluation/rq1-results.json

    # Full comparison incl. gold matching (LLM provider configured via env)
    python scripts/evaluate_rq1.py examples/requirement-corpus \
        --strategies rules,llm,hybrid,multi_agent \
        --gold examples/rq1-gold/requirements.yaml \
        --out evaluation/rq1-results.json

    # Review-effort metrics from a reviewed frontend export
    python scripts/evaluate_rq1.py examples/requirement-corpus --strategies rules \
        --reviewed rq1-requirement-dataset.json

Metrics per strategy: extraction counts, traceability (verified evidence,
evidence spans per requirement), validity distribution, downstream readiness,
competency-question coverage, and (optionally) approximate gold recall via
token-overlap statement matching. Review-effort metrics are computed from a
reviewed RQ1 export (the workbench "Export RQ1" download) when provided.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'requirement-reuse-service'))
sys.path.insert(0, str(ROOT / 'scripts'))

import yaml  # noqa: E402

from requirement_reuse_service.evaluation import aggregate_expert_reviews  # noqa: E402
from requirement_reuse_service.models import (  # noqa: E402
    AggregateExpertReviewsRequest,
    AnalysisRequest,
    EvaluationPackage,
    ExpertReviewSubmission,
)
from requirement_reuse_service.service import export_rq1_dataset, normalize_tokens  # noqa: E402

from extract_requirements import TASK_MARKERS, read_artifact, read_user_tasks  # noqa: E402

GOLD_MATCH_THRESHOLD = 0.35


def main() -> int:
    parser = argparse.ArgumentParser(description='Compare RQ1 extraction strategies over a corpus.')
    parser.add_argument('corpus', type=Path)
    parser.add_argument('--strategies', default='rules', help='Comma-separated: rules,llm,hybrid,multi_agent')
    parser.add_argument('--panel-preset', default='full_15', choices=['full_15', 'pilot_core', 'extraction_12'])
    parser.add_argument('--gold', type=Path, default=None, help='Gold requirements YAML (list of {id, statement})')
    parser.add_argument('--reviewed', type=Path, default=None, help='Reviewed RQ1 export JSON for review-effort metrics')
    parser.add_argument('--out', type=Path, default=None, help='Write results JSON to this path')
    parser.add_argument('--evaluation-package', type=Path, default=None, help='Frozen rq1-evaluation-package-v1 JSON')
    parser.add_argument('--review-submissions', type=Path, nargs='*', default=None, help='Independent review submission JSON files')
    parser.add_argument('--aggregation-out', type=Path, default=None, help='Write rq1-review-aggregation-v1 JSON')
    args = parser.parse_args()

    artifacts, user_tasks = load_corpus(args.corpus)
    gold = load_gold(args.gold) if args.gold else []
    results: dict[str, object] = {
        'corpus': str(args.corpus),
        'artifact_count': len(artifacts),
        'user_task_count': len(user_tasks),
        'gold_requirement_count': len(gold),
        'strategies': {},
    }

    for strategy in [item.strip() for item in args.strategies.split(',') if item.strip()]:
        print(f'== strategy: {strategy} ==')
        dataset = export_rq1_dataset(
            AnalysisRequest(
                artifacts=artifacts,
                user_tasks=user_tasks,
                strategy=strategy,  # type: ignore[arg-type]
                panel_preset=args.panel_preset,
                study_mode='summative' if strategy == 'multi_agent' else 'formative',
            )
        )
        entry = strategy_metrics(dataset)
        if gold:
            entry['gold_comparison'] = gold_comparison(dataset, gold)
        if dataset['strategy_used'] != strategy:
            entry['note'] = f"strategy fell back to {dataset['strategy_used']} (provider unavailable?)"
        results['strategies'][strategy] = entry  # type: ignore[index]
        print(json.dumps(entry, indent=2)[:1200])

    if args.reviewed:
        results['review_effort'] = review_effort(json.loads(args.reviewed.read_text(encoding='utf-8')))
        print('== review effort ==')
        print(json.dumps(results['review_effort'], indent=2))

    if args.evaluation_package:
        package = EvaluationPackage.model_validate_json(args.evaluation_package.read_text(encoding='utf-8'))
        submissions = [
            ExpertReviewSubmission.model_validate_json(path.read_text(encoding='utf-8'))
            for path in (args.review_submissions or [])
        ]
        aggregation = aggregate_expert_reviews(AggregateExpertReviewsRequest(
            evaluation_package=package,
            review_submissions=submissions,
        ))
        results['expert_evaluation'] = {
            'evaluation_package_id': package.id,
            'evaluation_package_hash': package.package_hash,
            'machine_requirement_count': len(package.machine_requirements),
            'performance_basis': 'frozen_original_machine_requirements',
            'aggregation': aggregation.model_dump(mode='json'),
            'corrected_final_baseline_metrics': None,
        }
        if args.aggregation_out:
            args.aggregation_out.parent.mkdir(parents=True, exist_ok=True)
            args.aggregation_out.write_text(aggregation.model_dump_json(indent=2), encoding='utf-8')
            print(f'Wrote {args.aggregation_out}')

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(results, indent=2), encoding='utf-8')
        print(f'\nWrote {args.out}')
    return 0


def load_corpus(corpus: Path):
    files = sorted(path for path in ([corpus] if corpus.is_file() else corpus.rglob('*')) if path.is_file())
    artifacts, user_tasks = [], []
    for path in files:
        if any(marker in path.name.lower() for marker in TASK_MARKERS):
            user_tasks.extend(read_user_tasks(path))
        else:
            artifacts.append(read_artifact(path))
    return artifacts, user_tasks


def load_gold(path: Path) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding='utf-8'))
    return data.get('requirements', data) if isinstance(data, dict) else data


def strategy_metrics(dataset: dict) -> dict:
    requirements = dataset['requirements']
    metrics = dataset['summary_metrics']
    total = max(1, len(requirements))
    validity = Counter(requirement.get('validation_status', 'needs_review') for requirement in requirements)

    def has_action_field(requirement: dict, field: str) -> bool:
        return any(action.get(field) for action in requirement.get('candidate_metadata_actions', []))

    verified = sum(
        1
        for requirement in requirements
        if requirement.get('source_evidence') and (requirement.get('provenance') or {}).get('evidence_verified') is not False
    )
    result = {
        'strategy_used': dataset['strategy_used'],
        'extraction': {
            'requirement_count': len(requirements),
            'evidence_unit_count': metrics.get('evidence_unit_count', 0),
            'duplicate_group_count': metrics.get('duplicate_group_count', 0),
            'warning_count': metrics.get('warning_count', len(dataset.get('warnings', []))),
        },
        'traceability': {
            'pct_with_verified_evidence': round(100 * verified / total, 1),
            'avg_evidence_spans_per_requirement': round(
                sum(len(requirement.get('source_evidence', [])) for requirement in requirements) / total, 2
            ),
        },
        'validity': {status: round(100 * count / total, 1) for status, count in sorted(validity.items())},
        'downstream_readiness': {
            'pct_with_candidate_metadata_actions': round(
                100 * sum(1 for requirement in requirements if requirement.get('candidate_metadata_actions')) / total, 1
            ),
            'pct_with_target_class': round(100 * sum(1 for r in requirements if has_action_field(r, 'target_class')) / total, 1),
            'pct_with_candidate_terms': round(100 * sum(1 for r in requirements if has_action_field(r, 'candidate_terms')) / total, 1),
            'pct_with_obligation_hint': round(
                100
                * sum(1 for r in requirements if (r.get('normalized_intent') or {}).get('obligation_hint', 'unknown') != 'unknown')
                / total,
                1,
            ),
            'pct_linked_to_user_tasks': round(
                100 * sum(1 for requirement in requirements if requirement.get('supports_user_tasks')) / total, 1
            ),
        },
        'competency_question_coverage': metrics.get('competency_question_coverage', {}),
    }
    if dataset.get('schema_version') == 'rq1-multi-agent-dataset-v1':
        result['multi_agent_panel'] = multi_agent_metrics(dataset)
    return result


def multi_agent_metrics(dataset: dict) -> dict:
    raw = dataset.get('raw_agent_requirements', [])
    consolidated = dataset.get('machine_requirements', dataset.get('requirements', []))
    runs = dataset.get('agent_runs', [])
    raw_by_role = Counter(item.get('origin_agent_role', 'unknown') for item in raw)
    verified_by_role: dict[str, dict[str, int | float]] = {}
    for role, count in sorted(raw_by_role.items()):
        verified = sum(
            bool((item.get('provenance') or {}).get('evidence_verified'))
            for item in raw if item.get('origin_agent_role') == role
        )
        verified_by_role[role] = {
            'candidate_count': count,
            'verified_count': verified,
            'verified_evidence_rate': round(verified / count, 3) if count else 0.0,
        }
    role_statement_sets = {
        role: {
            ' '.join(normalize_tokens(item.get('normalized_statement') or ''))
            for item in raw if item.get('origin_agent_role') == role
        }
        for role in raw_by_role
    }
    pair_overlap = {}
    roles = sorted(role_statement_sets)
    for index, left in enumerate(roles):
        for right in roles[index + 1:]:
            union = role_statement_sets[left] | role_statement_sets[right]
            pair_overlap[f'{left}__{right}'] = round(
                len(role_statement_sets[left] & role_statement_sets[right]) / len(union), 3
            ) if union else 0.0
    unique_by_role = Counter()
    for item in consolidated:
        contributing = item.get('contributing_agent_roles') or []
        if len(contributing) == 1:
            unique_by_role[contributing[0]] += 1
    support_distribution = Counter(
        len(item.get('contributing_agent_roles') or []) for item in consolidated
    )
    critique = dataset.get('critique_findings', [])
    return {
        'panel_preset': dataset.get('panel_preset'),
        'panel_status': dataset.get('panel_status'),
        'enabled_role_count': len(runs),
        'completed_role_count': sum(run.get('status') == 'completed' for run in runs),
        'failed_roles': [run.get('role_id') for run in runs if run.get('status') == 'failed'],
        'raw_candidate_count_by_role': dict(sorted(raw_by_role.items())),
        'verified_evidence_by_role': verified_by_role,
        'unique_consolidated_candidates_by_role': dict(sorted(unique_by_role.items())),
        'role_pair_candidate_overlap': pair_overlap,
        'raw_candidate_count': len(raw),
        'consolidated_candidate_count': len(consolidated),
        'consolidation_reduction_percentage': round(100 * (len(raw) - len(consolidated)) / max(1, len(raw)), 1),
        'cross_role_support_distribution': dict(sorted(support_distribution.items())),
        'support_level_distribution': dict(Counter(item.get('support_level', 'explicit') for item in raw)),
        'critique_findings_by_category': dict(Counter(item.get('category', 'other') for item in critique)),
        'critique_findings_by_severity': dict(Counter(item.get('severity', 'warning') for item in critique)),
        'duplicate_rate': round(len(dataset.get('duplicate_groups', [])) / max(1, len(raw)), 3),
        'warning_count': len(dataset.get('warnings', [])),
    }


def gold_comparison(dataset: dict, gold: list[dict]) -> dict:
    """Approximate recall: a gold requirement counts as found when some extracted
    statement shares enough normalized tokens (containment over gold tokens)."""
    statements = [
        (
            requirement['id'],
            set(normalize_tokens(requirement.get('normalized_statement') or requirement.get('description') or '')),
        )
        for requirement in dataset['requirements']
    ]
    matched, missed = [], []
    for item in gold:
        gold_tokens = set(normalize_tokens(str(item.get('statement', ''))))
        if not gold_tokens:
            continue
        best = max(statements, key=lambda pair: len(pair[1] & gold_tokens) / len(gold_tokens), default=(None, set()))
        score = len(best[1] & gold_tokens) / len(gold_tokens) if best[0] else 0.0
        (matched if score >= GOLD_MATCH_THRESHOLD else missed).append(
            {
                'gold_id': item.get('id'),
                'matched_requirement_id': best[0] if score >= GOLD_MATCH_THRESHOLD else None,
                'score': round(score, 2),
            }
        )
    total = len(matched) + len(missed)
    return {
        'threshold': GOLD_MATCH_THRESHOLD,
        'approx_recall': round(len(matched) / total, 2) if total else None,
        'matched': matched,
        'missed': missed,
    }


def review_effort(reviewed_export: dict) -> dict:
    requirements = reviewed_export.get('requirements', [])
    history: list[dict] = []
    for entry in reviewed_export.get('review_editor_history', []):
        for event in entry.get('editor_history', []) or []:
            history.append({'requirement_id': entry.get('requirement_id'), **event})
    statuses = Counter(requirement.get('status') for requirement in requirements)
    edits = [entry for entry in history if entry.get('action') == 'edit']
    approved_ids = {requirement.get('id') for requirement in requirements if requirement.get('status') == 'approved'}
    return {
        'accepted': statuses.get('approved', 0),
        'rejected': statuses.get('rejected', 0),
        'merged': statuses.get('merged', 0),
        'edited_requirement_count': len({entry.get('requirement_id') for entry in edits}),
        'total_edit_events': len(edits),
        'avg_edits_per_approved_requirement': round(
            sum(1 for entry in edits if entry.get('requirement_id') in approved_ids) / max(1, len(approved_ids)), 2
        ),
        'fields_most_often_edited': Counter(entry.get('field') for entry in edits).most_common(8),
        'local_merge_events': len(reviewed_export.get('local_merge_events', [])),
        'local_split_events': len(reviewed_export.get('local_split_events', [])),
    }


if __name__ == '__main__':
    sys.exit(main())
