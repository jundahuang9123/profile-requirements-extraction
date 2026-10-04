from __future__ import annotations

import os
import uuid
import time

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .engine import (active_records, configured_client, decide, execute_case, execute_run,
                     freeze_snapshot, lexical_relation, make_case, new_run, publish_baseline,
                     qualify_record, record_from_observation, verify)
from .evidence import register_source, resolve_evidence
from .models import (AdditionRequest, AssessmentRequest, BaselineRequest, DecisionRequest, EvidenceUnit,
                     MessageRequest, Observation, RunRequest, SnapshotRequest, SourceRequest)
from .storage import ConflictError, Store, now, uid

router = APIRouter(prefix='/api/rq1/v2', tags=['Persistent RQ1 workflow'])


def actor() -> str:
    # This server binds to loopback by default. Shared deployment requires authentication.
    return os.environ.get('RQ1_LOCAL_REVIEWER', 'local-reviewer')


def translate(call):
    try:
        return call()
    except ConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def downloadable(value, enabled: bool, filename: str):
    if enabled:
        return JSONResponse(value, headers={'Content-Disposition': f'attachment; filename="{filename}"'})
    return value


@router.post('/sources')
def add_source(request: SourceRequest):
    return translate(lambda: register_source(Store(), request))


@router.get('/sources')
def list_sources():
    return [{k: v for k, v in item.items() if k not in {'raw_base64', 'representation'}} for item in Store().list('source')]


@router.get('/sources/{source_version_id}')
def get_source(source_version_id: str):
    return translate(lambda: Store().get('source', source_version_id))


@router.post('/snapshots')
def add_snapshot(request: SnapshotRequest):
    return translate(lambda: freeze_snapshot(Store(), request))


@router.get('/evidence/{evidence_id}')
def get_evidence(evidence_id: str):
    def read():
        store = Store()
        unit = EvidenceUnit.model_validate(store.get('evidence', evidence_id))
        return {'unit': unit.model_dump(mode='json'), 'resolution': resolve_evidence(store, unit)}
    return translate(read)


@router.get('/runs')
def list_runs():
    return [{key: value for key, value in run.items() if key in {'run_id', 'name', 'status', 'created_at', 'strategy', 'version'}} for run in Store().list('run')]


@router.post('/runs', status_code=202)
def create_run(request: RunRequest, background: BackgroundTasks):
    store = Store()
    run = translate(lambda: new_run(store, request))
    background.add_task(execute_run, store, run['run_id'])
    return run


@router.get('/runs/{run_id}')
def get_run(run_id: str):
    return translate(lambda: Store().get('run', run_id))


@router.get('/runs/{run_id}/events')
def get_events(run_id: str):
    return translate(lambda: Store().events(run_id))


@router.get('/runs/{run_id}/evaluation')
def evaluate_run(run_id: str, download: bool = False):
    from .evaluation import workflow_metrics
    return downloadable(translate(lambda: workflow_metrics(Store().get('run', run_id))), download, 'rq1-workflow-metrics.json')


@router.get('/runs/{run_id}/export')
def export_run(run_id: str, download: bool = False):
    def export():
        store = Store()
        run = store.get('run', run_id)
        snapshot = store.get('snapshot', run['snapshot_id'])
        return {'schema_version': run['schema_version'], 'export_kind': 'saved_review_state', 'run': run,
                'snapshot': snapshot, 'sources': [store.get('source', sid) for sid in snapshot['source_version_ids']],
                'evidence_units': [store.get('evidence', eid) for eid in run['evidence_ids']],
                'events': store.events(run_id)}
    return downloadable(translate(export), download, 'rq1-saved-workflow.json')


class VersionRequest(BaseModel):
    expected_version: int


@router.post('/runs/{run_id}/cancel')
def cancel_run(run_id: str, request: VersionRequest):
    def cancel(run):
        # Cancelling discussion after review must not strand already saved human decisions.
        run['status'] = 'awaiting_human' if run['decisions'] else 'cancelled'
        for case in run['deliberations']:
            if case['status'] in {'queued', 'running'}:
                case.update(status='cancelled', stop_reason='human_cancelled')
        if run['deliberations']:
            run['stages']['deliberation'] = 'completed'
    return translate(lambda: Store().mutate(run_id, request.expected_version, 'run_cancelled', cancel))


@router.post('/runs/{run_id}/resume', status_code=202)
def resume_run(run_id: str, request: VersionRequest, background: BackgroundTasks):
    store = Store()
    def resume(run):
        if run.get('worker_id') and run.get('job_lease_until', 0) > time.time():
            raise ConflictError('A worker lease is active. Retry after it finishes or after the 15-minute restart lease expires.')
        if run['status'] not in {'failed', 'cancelled', 'awaiting_human', 'created', 'eliciting', 'normalizing', 'verifying', 'consolidating', 'routing'} or run['decisions']:
            raise ValueError('Resume only an interrupted/partial unreviewed run; create a new run after adjudication.')
        if run['status'] == 'awaiting_human' and not run['metrics'].get('failed_role_count'):
            raise ValueError('This run completed. Create a new run for another trial.')
        configured_client(RunRequest.model_validate(run['request']))
        run.setdefault('attempt_history', []).append({key: run[key] for key in ('status', 'requirements', 'observations', 'role_runs', 'diagnostics')})
        run['status'] = 'created'
        run['worker_id'] = None
        run['job_lease_until'] = 0
        if any(r['status'] == 'failed' for r in run['role_runs']):
            run['stages']['elicitation'] = 'pending'
    result = translate(lambda: store.mutate(run_id, request.expected_version, 'run_resumed', resume))
    background.add_task(execute_run, store, run_id)
    return result


@router.post('/runs/{run_id}/assessments')
def assess_revision(run_id: str, request: AssessmentRequest):
    def apply(run):
        if run['status'] != 'awaiting_human':
            raise ValueError('Assessments require an awaiting-human run.')
        record = active_records(run, [request.revision_id])[0]
        if record.lifecycle_state in {'accepted', 'rejected', 'out_of_scope'}:
            raise ValueError('Create a new revision before reassessing a decided record.')
        if request.qualification.revision_hash != record.content_hash:
            raise ConflictError('Assessment targets a different revision hash.')
        report = verify(Store(), record, run['evidence_ids'])
        if report['status'] != 'pass':
            raise ValueError('Source verification failed; repair evidence before semantic assessment.')
        q = request.qualification.model_copy(update={'assessor': actor()})
        target = next(r for r in run['requirements'] if r['revision_id'] == request.revision_id)
        run.setdefault('assessment_history', []).append({'revision_id': request.revision_id, 'previous': target['qualification'],
                                                       'assessment': q.model_dump(mode='json'), 'created_at': now()})
        target.update(qualification=q.model_dump(mode='json'), verification=report)
        return {'revision_id': request.revision_id, 'assessor': actor()}
    return translate(lambda: Store().mutate(run_id, request.expected_version, 'human_assessment', apply,
        key=request.idempotency_key, payload=request.model_dump(mode='json')))


@router.post('/runs/{run_id}/decisions')
def human_decision(run_id: str, request: DecisionRequest):
    return translate(lambda: decide(Store(), run_id, request, actor()))


@router.post('/runs/{run_id}/requirements')
def add_requirement(run_id: str, request: AdditionRequest):
    store = Store()
    def apply(run):
        if run['status'] not in {'awaiting_human', 'completed'}:
            raise ValueError('Add a human proposal only after machine extraction finishes.')
        decision_id = uid('decision', run_id, request.idempotency_key)
        draft = request.draft
        observation = Observation(observation_id=uid('obs', decision_id), role_id=actor(),
            statement=draft.statement, requirement_type=draft.requirement_type, intent=draft.intent,
            evidence_links=draft.evidence_links, scope=draft.scope, rationale=draft.rationale)
        record = record_from_observation(run_id, observation)
        qualify_record(store, record, run['evidence_ids'])
        for other in active_records(run, run['active_revision_ids']):
            relation = lexical_relation(record, other)
            if relation:
                run['conflicts'].append({'conflict_id': uid('conflict', record.revision_id, other.revision_id, relation),
                    'revision_ids': [record.revision_id, other.revision_id], 'kind': relation,
                    'rationale': 'Potential conflict introduced by human-added requirement.', 'status': 'open', 'decision_id': None})
        run['requirements'].append(record.model_dump(mode='json'))
        run['active_revision_ids'].append(record.revision_id)
        run['decisions'].append({'decision_id': decision_id, 'actor': actor(), 'action': 'add',
            'revision_ids': [], 'revision_hashes': [], 'result_revision_ids': [record.revision_id],
            'rationale': request.rationale, 'created_at': now()})
        run['status'] = 'awaiting_human'
        run['stages']['adjudication'] = 'running'
        return {'revision_id': record.revision_id}
    return translate(lambda: store.mutate(run_id, request.expected_version, 'human_requirement_added', apply,
        key=request.idempotency_key, payload=request.model_dump(mode='json')))


class CaseRequest(BaseModel):
    expected_version: int
    revision_ids: list[str]
    question: str


@router.post('/runs/{run_id}/deliberations')
def open_case(run_id: str, request: CaseRequest, background: BackgroundTasks):
    def apply(run):
        if not request.question.strip() or not request.revision_ids:
            raise ValueError('Specify a question and at least one current revision.')
        records = active_records(run, request.revision_ids)
        if any(r.verification['status'] != 'pass' for r in records):
            raise ValueError('Repair source evidence before deliberation.')
        if any(c['status'] in {'queued', 'running'} and set(c['revision_ids']) & set(request.revision_ids) for c in run['deliberations']):
            raise ValueError('A case is already pending for this revision.')
        if sum(bool(set(c['revision_ids']) & set(request.revision_ids)) for c in run['deliberations']) >= 2:
            raise ValueError('The bounded discussion allowance is exhausted; adjudicate the remaining issue directly.')
        case = make_case(run, records, ['human_request: ' + request.question])
        case['case_id'] = uid('case', case['case_id'], uuid.uuid4().hex)
        run['deliberations'].append(case)
        run['stages']['deliberation'] = 'running'
        return case
    store = Store()
    response = translate(lambda: store.mutate(run_id, request.expected_version, 'case_opened', apply))
    if response['run']['strategy'] == 'multi_agent':
        client = translate(lambda: configured_client(RunRequest.model_validate(response['run']['request'])))
        if client:
            background.add_task(execute_case, store, run_id, response['result']['case_id'], client)
    return response


@router.post('/runs/{run_id}/deliberations/{case_id}/messages')
def post_message(run_id: str, case_id: str, request: MessageRequest):
    def apply(run):
        case = next((c for c in run['deliberations'] if c['case_id'] == case_id), None)
        if case is None:
            raise KeyError(case_id)
        if set(request.evidence_ids) - set(run['evidence_ids']):
            raise ValueError('Message cites evidence outside the corpus.')
        message = {'message_id': uid('message', case_id, request.idempotency_key), 'role_id': actor(),
                   'body': request.body, 'evidence_ids': request.evidence_ids, 'created_at': now()}
        case['messages'].append(message)
        return message
    return translate(lambda: Store().mutate(run_id, request.expected_version, 'human_message', apply,
        key=request.idempotency_key, payload=request.model_dump(mode='json')))


@router.post('/runs/{run_id}/deliberations/{case_id}/close')
def close_case(run_id: str, case_id: str, request: MessageRequest):
    def apply(run):
        case = next((c for c in run['deliberations'] if c['case_id'] == case_id), None)
        if case is None:
            raise KeyError(case_id)
        if case['status'] == 'running':
            raise ConflictError('Cancel the run before closing an active case.')
        case.update(status='unresolved', stop_reason='human_closed: ' + request.body)
        if all(c['status'] not in {'queued', 'running'} for c in run['deliberations']):
            run['stages']['deliberation'] = 'completed'
        return {'case_id': case_id, 'actor': actor()}
    return translate(lambda: Store().mutate(run_id, request.expected_version, 'case_closed', apply,
        key=request.idempotency_key, payload=request.model_dump(mode='json')))


@router.post('/runs/{run_id}/baselines')
def create_baseline(run_id: str, request: BaselineRequest):
    return translate(lambda: publish_baseline(Store(), run_id, request, actor()))


@router.get('/runs/{run_id}/baselines/{baseline_id}')
def get_baseline(run_id: str, baseline_id: str, download: bool = False):
    def read():
        baseline = next((b for b in Store().get('run', run_id).get('baselines', []) if b['baseline_id'] == baseline_id), None)
        if baseline is None:
            raise KeyError(baseline_id)
        return baseline
    return downloadable(translate(read), download, 'rq1-validated-baseline-v2.json')
