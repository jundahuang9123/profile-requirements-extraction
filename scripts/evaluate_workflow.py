#!/usr/bin/env python3
"""Summarize a saved v2 run or baseline offline, without any extraction/model calls."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'requirement-reuse-service'))
from requirement_reuse_service.workflow.evaluation import workflow_metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('export', type=Path)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    data = json.loads(args.export.read_text(encoding='utf-8'))
    if data.get('export_kind') == 'saved_review_state':
        run = data['run']
    elif data.get('schema_version') == 'rq1-validated-requirement-baseline-v2':
        provenance = data['provenance']
        run = {**provenance, 'snapshot_id': data['snapshot']['snapshot_id'],
            'strategy': provenance['strategy'], 'requirements': provenance['all_revisions']}
    else:
        parser.error('Expected a saved v2 workflow export or validated v2 baseline.')
    output = json.dumps(workflow_metrics(run), indent=2, ensure_ascii=False) + '\n'
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output, encoding='utf-8')
    else:
        print(output, end='')


if __name__ == '__main__':
    main()
