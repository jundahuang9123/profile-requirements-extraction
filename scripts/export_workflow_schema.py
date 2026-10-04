#!/usr/bin/env python3
"""Generate the authoritative v2 JSON Schema from the runtime contracts."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'requirement-reuse-service'))
from pydantic.json_schema import models_json_schema
from requirement_reuse_service.workflow.models import (WorkflowRun, SourceArtifact, EvidenceUnit, CorpusSnapshot,
    AdditionRequest, AssessmentRequest, BaselineRequest, DecisionRequest, RunRequest, SourceRequest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    _, schema = models_json_schema([(model, 'validation') for model in (
        WorkflowRun, SourceArtifact, EvidenceUnit, CorpusSnapshot, AdditionRequest,
        AssessmentRequest, BaselineRequest, DecisionRequest, RunRequest, SourceRequest)],
        title='RQ1 persistent workflow v2 contracts')
    schema['$schema'] = 'https://json-schema.org/draft/2020-12/schema'
    output = json.dumps(schema, indent=2, sort_keys=True) + '\n'
    path = ROOT / 'requirement-reuse-service/schema/rq1_workflow_v2.schema.json'
    if args.check:
        if not path.exists() or path.read_text(encoding='utf-8') != output:
            parser.error('Workflow schema is stale. Run this script without --check.')
    else:
        path.write_text(output, encoding='utf-8')


if __name__ == '__main__':
    main()
