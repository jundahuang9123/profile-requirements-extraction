#!/usr/bin/env python3
"""Audit every strict benchmark input offline; never read reference answers or call an LLM."""
import argparse
import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'requirement-reuse-service'))
from requirement_reuse_service.models import ArtifactPayload
from requirement_reuse_service.workflow.evidence import register_source, resolve_evidence, PARSER_VERSION
from requirement_reuse_service.workflow.models import SourceRequest, EvidenceUnit, SnapshotRequest
from requirement_reuse_service.workflow.engine import freeze_snapshot
from requirement_reuse_service.workflow.role_selection import batches_for
from requirement_reuse_service.workflow.citations import elicitation_batch
from requirement_reuse_service.workflow.storage import Store, canonical, digest


def audit(output: Path):
    output.mkdir(parents=True, exist_ok=True)
    store = Store(str(output / 'preflight.sqlite3'))
    allow = json.loads((ROOT / 'benchmark-data/runtime-inputs.json').read_text())['benchmarks']
    cache, corpora = {}, {}
    for name, config in allow.items():
        reports, sources, errors = [], [], []
        for relative in config['raw']:
            path = ROOT / 'benchmark-data' / relative
            if relative not in cache:
                try:
                    raw = path.read_bytes()
                    source = register_source(store, SourceRequest(
                        artifact=ArtifactPayload(name=path.name, content=base64.b64encode(raw).decode(),
                                                 content_encoding='base64'),
                        source_id='preflight-' + digest(relative), source_role='normative_spec'))
                    units = [u for u in store.list('evidence') if u['source_version_id'] == source['source_version_id']]
                    resolution_cache = {}
                    bad = sum(resolve_evidence(store, EvidenceUnit.model_validate(u), resolution_cache)['status'] != 'pass'
                              for u in units)
                    cache[relative] = {'path': relative, 'source_version_id': source['source_version_id'],
                        'sha256': source['raw_sha256'], 'kind': source['artifact_kind'],
                        'parse_status': source['parse_status'], 'unit_count': len(units),
                        'characters': sum(len(u['content']) for u in units),
                        'largest_unit': max((len(u['content']) for u in units), default=0),
                        'failed_source_resolutions': bad, 'diagnostics': source['diagnostics']}
                except Exception as exc:
                    cache[relative] = {'path': relative, 'parse_status': 'failed', 'error': str(exc)}
                print(json.dumps({'file': relative, 'status': cache[relative]['parse_status']}), flush=True)
            report = cache[relative]
            reports.append(report)
            if report['parse_status'] != 'parsed' or report.get('failed_source_resolutions'):
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
                selection_batches = batches_for(units)
                # Conservative size estimate reserves 5,000 chars for each selected role/task payload.
                extraction_batches, current = [], []
                for unit in units:
                    single, _ = elicitation_batch([unit])
                    if len(canonical({'evidence_units': single})) + 5000 > 45000:
                        raise ValueError('Single evidence unit exceeds extraction payload allowance.')
                    trial, _ = elicitation_batch([*current, unit])
                    if current and (len(current) >= 4 or len(canonical({'evidence_units': trial})) + 5000 > 16000):
                        if not current:
                            raise ValueError('Single evidence unit exceeds extraction payload allowance.')
                        extraction_batches.append(current)
                        current = [unit]
                        single, _ = elicitation_batch(current)
                        if len(canonical({'evidence_units': single})) + 5000 > 45000:
                            raise ValueError('Single evidence unit exceeds extraction payload allowance.')
                    else:
                        current.append(unit)
                if current:
                    extraction_batches.append(current)
                stats = {'evidence_units': len(units), 'selection_batches': len(selection_batches),
                         'estimated_extraction_batches_per_role': len(extraction_batches),
                         'snapshot_id': snapshot['snapshot_id']}
            except Exception as exc:
                errors.append(str(exc))
        corpora[name] = {'status': 'blocked' if errors else 'ready_with_document_limitations',
                         'sources': reports, 'blockers': errors, **stats}
        (output / 'REPORT.json').write_text(json.dumps({'parser_version': PARSER_VERSION, 'corpora': corpora}, indent=2))
    text = '# Offline benchmark ingestion preflight\n\nNo model calls or reference answers used. Readiness means addressable extraction, not semantic completeness.\n\n'
    for name, report in corpora.items():
        text += f'## {name}\n\nStatus: {report["status"]}. Selection batches: {report.get("selection_batches", "unknown")}; estimated extraction batches per role: {report.get("estimated_extraction_batches_per_role", "unknown")}.\n\n'
        for source in report['sources']:
            text += f'- {source["path"]}: {source["parse_status"]}, {source.get("unit_count", 0)} units, {source.get("characters", 0)} characters.\n'
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
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(ROOT):
        parser.error('Keep preflight databases and reports outside the repository.')
    audit(args.output.resolve())
