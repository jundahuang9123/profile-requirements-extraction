#!/usr/bin/env python3
"""Audit every strict benchmark input offline; never read reference answers or call an LLM."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'requirement-reuse-service'))
from requirement_reuse_service.workflow.evidence import register_source, resolve_evidence, PARSER_VERSION
from requirement_reuse_service.workflow.models import EvidenceUnit, SnapshotRequest
from requirement_reuse_service.workflow.benchmarks import benchmark_cases, benchmark_settings, source_request
from requirement_reuse_service.workflow.engine import (freeze_snapshot, EXTRACTION_BATCH_CHARS,
    EXTRACTION_BATCH_UNITS, EXTRACTION_UNIT_CHARS)
from requirement_reuse_service.workflow.role_selection import scan_batches
from requirement_reuse_service.workflow.citations import elicitation_batch
from requirement_reuse_service.workflow.storage import Store, canonical


def base_profile_context_chars(base_profile_id: str | None) -> int:
    if not base_profile_id:
        return 0
    from requirement_reuse_service.workflow.engine import extraction_role_context_chars
    return extraction_role_context_chars(base_profile_id)


def audit(output: Path, treat_base_as_background: bool = True):
    output.mkdir(parents=True, exist_ok=True)
    store = Store(str(output / 'preflight.sqlite3'))
    allow = benchmark_cases()
    cache, corpora = {}, {}
    for name in allow:
        reports, sources, errors = [], [], []
        settings = benchmark_settings(name)
        background = set(settings['background']) if treat_base_as_background else set()
        for relative in settings['raw']:
            role = 'background' if relative in background else 'normative_spec'
            cache_key = (relative, role)
            if cache_key not in cache:
                try:
                    source = register_source(store, source_request(relative, role))
                    units = [u for u in store.list('evidence') if u['source_version_id'] == source['source_version_id']]
                    resolution_cache = {}
                    bad = sum(resolve_evidence(store, EvidenceUnit.model_validate(u), resolution_cache)['status'] != 'pass'
                              for u in units)
                    cache[cache_key] = {'path': relative, 'source_role': role,
                        'source_version_id': source['source_version_id'],
                        'sha256': source['raw_sha256'], 'kind': source['artifact_kind'],
                        'parse_status': source['parse_status'], 'unit_count': len(units),
                        'characters': sum(len(u['content']) for u in units),
                        'largest_unit': max((len(u['content']) for u in units), default=0),
                        'failed_source_resolutions': bad, 'diagnostics': source['diagnostics']}
                except Exception as exc:
                    cache[cache_key] = {'path': relative, 'source_role': role,
                                        'parse_status': 'failed', 'error': str(exc)}
                print(json.dumps({'file': relative, 'role': role,
                                  'status': cache[cache_key]['parse_status']}), flush=True)
            report = cache[cache_key]
            reports.append(report)
            if (report.get('error') or (role != 'background' and
                    (report['parse_status'] != 'parsed' or report.get('failed_source_resolutions')))):
                errors.append(relative + ': failed parsing or source resolution')
            if report.get('source_version_id'):
                sources.append(report['source_version_id'])
        stats = {}
        if not sources:
            errors.append('No allowlisted raw inputs; this corpus is unavailable for a raw run.')
        elif not errors:
            try:
                snapshot = freeze_snapshot(store, SnapshotRequest(source_version_ids=sources, name='Preflight ' + name))
                units = [store.get('evidence', i) for i in snapshot['evidence_ids']]
                # As a new run: the whole corpus in scan order, refused beyond the ceiling or cap.
                selection_batches = scan_batches(store, snapshot)
                # Same bounds as the extractor. The size estimate conservatively reserves
                # 5,000 chars for each selected role/task payload plus the selected base
                # table, so a run can need fewer batches.
                base_context_chars = base_profile_context_chars(settings['base_profile_id'])
                reserve = 5000 + base_context_chars
                extraction_batches, current = [], []
                for unit in units:
                    single, _ = elicitation_batch([unit])
                    if len(canonical({'evidence_units': single})) + reserve > EXTRACTION_UNIT_CHARS:
                        raise ValueError('Single evidence unit exceeds extraction payload allowance.')
                    trial, _ = elicitation_batch([*current, unit])
                    if current and (len(current) >= EXTRACTION_BATCH_UNITS or
                                    len(canonical({'evidence_units': trial})) + reserve > EXTRACTION_BATCH_CHARS):
                        extraction_batches.append(current)
                        current = [unit]
                    else:
                        current.append(unit)
                if current:
                    extraction_batches.append(current)
                stats = {'evidence_units': len(units), 'selection_batches': selection_batches,
                         'estimated_extraction_batches_per_role': len(extraction_batches),
                         'base_profile_context_chars': base_context_chars,
                         'extraction_role_reserve_chars': reserve,
                         'background_excluded_units': sum(report.get('unit_count', 0)
                                                          for report in reports if report['source_role'] == 'background'),
                         'snapshot_exclusions': snapshot['exclusions'],
                         'snapshot_id': snapshot['snapshot_id']}
            except Exception as exc:
                errors.append(str(exc))
        corpora[name] = {'status': 'blocked' if errors else 'ready_with_document_limitations',
                         'sources': reports, 'blockers': errors,
                         'base_profile_id': settings['base_profile_id'],
                         'treat_base_as_background': treat_base_as_background, **stats}
        (output / 'REPORT.json').write_text(json.dumps({'parser_version': PARSER_VERSION, 'corpora': corpora}, indent=2))
    text = '# Offline benchmark ingestion preflight\n\nNo model calls or reference answers used. Readiness means addressable extraction, not semantic completeness.\n\n'
    for name, report in corpora.items():
        text += f'## {name}\n\nStatus: {report["status"]}. Selection batches: {report.get("selection_batches", "unknown")}; estimated extraction batches per role: {report.get("estimated_extraction_batches_per_role", "unknown")}.\n\n'
        text += f'Base profile: {report["base_profile_id"] or "not selected"}. Background units excluded: {report.get("background_excluded_units", 0)}; base-table payload overhead: {report.get("base_profile_context_chars", 0)} characters.\n\n'
        for source in report['sources']:
            text += f'- {source["path"]} ({source["source_role"]}): {source["parse_status"]}, {source.get("unit_count", 0)} units, {source.get("characters", 0)} characters.\n'
            for diagnostic in source.get('diagnostics', []):
                text += f'  - {diagnostic}\n'
        for error in report['blockers']:
            text += f'- BLOCKER: {error}\n'
        text += '\n'
    (output / 'REPORT.md').write_text(text)
    return corpora


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--keep-base-as-evidence', action='store_true',
                        help='Explicit comparison only: retain background-listed specifications as evidence.')
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(ROOT):
        parser.error('Keep preflight databases and reports outside the repository.')
    audit(args.output.resolve(), treat_base_as_background=not args.keep_base_as_evidence)
