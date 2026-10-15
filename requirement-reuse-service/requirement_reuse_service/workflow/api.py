from __future__ import annotations

import os
import re
import uuid
import time
from copy import deepcopy

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .engine import (HUMAN_REQUEST_PREFIX, UNFINISHED_CASE_STATES, active_records, configured_client, decide,
                     execute_case, execute_run, freeze_snapshot, is_human_request, lexical_relation, make_case, new_run,
                     publish_baseline, ensure_elicitation_resumable, qualify_record, record_from_observation, verify, derive_run,
                     apply_base_check, retain_base_findings)
from .evidence import register_source, resolve_evidence
from .models import (AdditionRequest, AssessmentRequest, BaselineRequest, DecisionRequest, EvidenceUnit,
                     MessageRequest, RestoreRequest, Observation, RunRequest, DeriveRequest, SnapshotRequest, SourceRequest)
from .storage import ConflictError, Store, now, uid
from ..llm.config import runtime_config_status, set_runtime_config
from .role_selection import ensure_selection_resumable

router = APIRouter(prefix='/api/rq1/v2', tags=['Persistent RQ1 workflow'])


class ProviderSettingsRequest(BaseModel):
    provider: str
    model: str = ''
    base_url: str = ''
    api_key: str = ''
    clear_api_key: bool = False


def ollama_default_url() -> str:
    # The service normally runs directly on the Mac. Docker needs the host alias.
    return 'http://host.docker.internal:11434/v1' if os.path.exists('/.dockerenv') else 'http://localhost:11434/v1'


@router.get('/provider-settings')
def get_provider_settings():
    return runtime_config_status()


@router.post('/provider-settings')
def save_provider_settings(request: ProviderSettingsRequest):
    presets = {
        'openai': ('openai-compatible', 'https://api.openai.com/v1'),
        'kiconnect': ('openai-compatible', 'https://chat.kiconnect.nrw/api/v1'),
        'ollama': ('openai-compatible', ollama_default_url()),
        'anthropic': ('anthropic', ''),
        'custom': ('openai-compatible', request.base_url.strip()),
        'disabled': ('disabled', ''),
    }
    preset = request.provider.strip().lower()
    if preset not in presets:
        raise HTTPException(422, 'Choose OpenAI, KI:connect, Ollama, Anthropic, a custom compatible endpoint, or disable live calls.')
    provider, default_url = presets[preset]
    base_url = request.base_url.strip() or default_url
    if provider == 'openai-compatible' and not base_url:
        raise HTTPException(422, 'Enter the compatible endpoint base URL.')
    try:
        set_runtime_config(provider=provider, model=request.model, base_url=base_url,
                           api_key=request.api_key or None, clear_api_key=request.clear_api_key, preset=preset)
        return runtime_config_status()
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post('/provider-models')
def discover_provider_models():
    """Fetch model IDs on explicit user request; never return request headers or keys."""
    from ..llm.config import LLMConfig
    from ..llm.model_catalog import model_rows, text_generation_model

    config = LLMConfig.from_env()
    if config.provider == 'disabled':
        raise HTTPException(422, 'Select and save a model provider first.')
    try:
        rows = model_rows(config)
        return {'connected': True, 'models': sorted({r['id'] for r in rows}),
                'generation_models': sorted({r['id'] for r in rows if text_generation_model(r)}),
                'selected_model': config.resolved_model()}
    except ValueError as exc:
        raise HTTPException(502, str(exc)) from exc


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
    # Saved runs are plain JSON; encoding them directly is much faster than FastAPI's
    # generic encoder for multi-megabyte runs.
    if enabled:
        return JSONResponse(value, headers={'Content-Disposition': f'attachment; filename="{filename}"'})
    return JSONResponse(value)


# Audit parts the workbench does not display; the export always includes them.
AUDIT_PARTS = ('model_calls', 'machine_snapshot', 'catalogues', 'assessment_reuse', 'consolidation_chunks', 'base_check_audit', 'need_chunks')


@router.post('/sources')
def add_source(request: SourceRequest):
    return translate(lambda: register_source(Store(), request))


@router.get('/sources')
def list_sources():
    return [{k: v for k, v in item.items() if k not in {'raw_base64', 'representation'}} for item in Store().list('source')]


@router.get('/sources/{source_version_id}')
def get_source(source_version_id: str):
    return translate(lambda: Store().get('source', source_version_id))


@router.get('/sources/{source_version_id}/evidence')
def source_evidence(source_version_id: str):
    def read():
        store = Store()
        source = store.get('source', source_version_id)
        identifiers = {source_version_id, *source.get('child_source_version_ids', [])}
        return [{'evidence_id': unit['evidence_id'], 'kind': unit['kind'],
                 'source_version_id': unit['source_version_id'], 'preview': unit['content'][:240]}
                for unit in store.list('evidence') if unit['source_version_id'] in identifiers]
    return translate(read)


@router.get('/snapshots/{snapshot_id}')
def read_snapshot(snapshot_id: str):
    return translate(lambda: Store().get('snapshot', snapshot_id))


@router.post('/snapshots')
def add_snapshot(request: SnapshotRequest):
    return translate(lambda: freeze_snapshot(Store(), request))


class BenchmarkLoadRequest(BaseModel):
    treat_base_as_background: bool = True


@router.get('/base-profiles')
def list_base_profiles():
    from .base_profile import PROFILE_DIRECTORY, PROFILE_ID_PATTERN, load_profile
    return [{'id': profile['id'], 'version': profile['version'], 'sha256': fingerprint,
             'family': profile.get('family', 'DCAT-AP'),
             'label': profile.get('label', 'DCAT-AP ' + profile['version']),
             'description': profile.get('description', 'Application-profile properties and obligations.')}
            for path in sorted(PROFILE_DIRECTORY.glob('dcat-*.json'))
            if re.fullmatch(PROFILE_ID_PATTERN, path.stem)
            for profile, fingerprint in [load_profile(path.stem)]]


@router.get('/benchmarks')
def list_benchmarks():
    from .benchmarks import benchmark_cases, benchmark_settings
    from pathlib import Path
    return [{'case_id': case, 'base_profile_id': settings['base_profile_id'],
             'background_source_names': [Path(p).name for p in settings['background']],
             'raw_file_count': len(settings['raw'])}
            for case in benchmark_cases() for settings in [benchmark_settings(case)]]


@router.post('/benchmarks/{case_id}/load')
def import_benchmark(case_id: str, request: BenchmarkLoadRequest):
    from .benchmarks import load_benchmark
    def load():
        try:
            result = load_benchmark(Store(), case_id, request.treat_base_as_background)
        except FileNotFoundError as exc:
            raise ValueError('An allowlisted raw document is missing; restore the benchmark inputs before loading.') from exc
        result['sources'] = [{k: v for k, v in source.items() if k not in {'raw_base64', 'representation'}}
                             for source in result['sources']]
        return result
    return translate(load)


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
    if request.benchmark_case_id:
        from .benchmarks import validate_case_snapshot
        translate(lambda: validate_case_snapshot(store, request.benchmark_case_id, request.snapshot_id))
    run = translate(lambda: new_run(store, request, actor()))
    background.add_task(execute_run, store, run['run_id'])
    return run


@router.get('/runs/{run_id}')
def get_run(run_id: str, audit: bool = True):
    """The saved run. ``audit=false`` leaves out the model-call log, the frozen machine
    snapshot and the excerpt catalogues, which the workbench does not display."""
    return translate(lambda: JSONResponse(Store().get_run(run_id, omit=() if audit else AUDIT_PARTS)))


@router.post('/runs/{run_id}/derive', status_code=202)
def derive_saved_run(run_id: str, request: DeriveRequest, background: BackgroundTasks):
    store = Store()
    run = translate(lambda: derive_run(store, run_id, request, actor()))
    background.add_task(execute_run, store, run['run_id'])
    return run


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
                'background_sources': [store.get('source', item['source_version_id'])
                    for item in snapshot.get('exclusions', []) if item['reason'] == 'background_not_evidence'],
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
        manifest = run.get('role_manifest')
        if manifest and manifest.get('status') not in {'completed', 'not_applicable'}:
            manifest['status'] = 'cancelled'
            run['stages']['role_selection'] = 'cancelled'
        for case in run['deliberations']:
            if case['status'] in {'queued', 'running'}:
                case.update(status='cancelled', stop_reason='human_cancelled')
        if run['deliberations']:
            run['stages']['deliberation'] = 'completed'
    return translate(lambda: Store().mutate(run_id, request.expected_version, 'run_cancelled', cancel, hydrate=True))


@router.get('/runs/{run_id}/stages/{stage}')
def export_stage(run_id: str, stage: str, download: bool = False):
    def read():
        store = Store()
        run = store.get('run', run_id)
        from .engine import STAGE_RESULT_FIELDS
        fields = STAGE_RESULT_FIELDS
        if stage not in fields:
            raise ValueError('Unknown workflow step.')
        checkpoint = run.get('stage_results', {}).get(stage) if stage not in {'adjudication', 'baseline'} else None
        results = checkpoint if checkpoint is not None else {key: run.get(key) for key in fields[stage]}
        snapshot_kind = 'stage_checkpoint' if checkpoint is not None else 'current_saved_state'
        if stage in {'acquisition', 'decomposition'}:
            results['snapshot'] = store.get('snapshot', run['snapshot_id'])
        if stage == 'elicitation':
            # The excerpt catalogues that the role reports reference by hash.
            hashes = {s.get('catalogue_hash') for report in results.get('role_runs') or []
                      for s in report.get('citation_selections', [])}
            results['catalogues'] = {h: c for h, c in run.get('catalogues', {}).items() if h in hashes}
        status = run['stages'][stage]
        if stage == 'elicitation' and status == 'completed' and any(r['status'] == 'failed' for r in run['role_runs']):
            status = 'partial'
        return downloadable({'run_id': run_id, 'snapshot_id': run['snapshot_id'], 'stage': stage,
                             'status': status, 'snapshot_kind': snapshot_kind, 'saved_version': run['version'], 'results': results},
                            download, f'{run_id}-{stage}.json')
    return translate(read)


@router.post('/runs/{run_id}/continue', status_code=202)
def continue_run(run_id: str, request: VersionRequest, background: BackgroundTasks):
    store = Store()
    def proceed(run):
        if run['status'] != 'paused' or run['request'].get('execution_mode') != 'stepwise':
            raise ValueError('Continue is only available at a saved stepwise pause.')
        if run.get('worker_id') and run.get('job_lease_until', 0) > time.time():
            raise ConflictError('The previous worker is still finishing. Refresh and retry.')
        ensure_elicitation_resumable(run)
        if run.get('role_manifest') and run['stages'].get('role_selection') != 'completed':
            ensure_selection_resumable(run['role_manifest'])
        configured_client(RunRequest.model_validate(run['request']))
        run.update(status='created', worker_id=None, job_lease_until=0)
    result = translate(lambda: store.mutate(run_id, request.expected_version, 'run_continued', proceed, hydrate=True))
    background.add_task(execute_run, store, run_id)
    return result


@router.post('/runs/{run_id}/resume', status_code=202)
def resume_run(run_id: str, request: VersionRequest, background: BackgroundTasks):
    store = Store()
    def resume(run):
        if run.get('worker_id') and run.get('job_lease_until', 0) > time.time():
            raise ConflictError('A worker lease is active. Retry after it finishes or after the 15-minute restart lease expires.')
        if run['status'] not in {'failed', 'cancelled', 'awaiting_human', 'created', 'selecting_roles', 'eliciting', 'normalizing', 'verifying', 'consolidating', 'routing'} or run['decisions']:
            raise ValueError('Resume only an interrupted/partial unreviewed run; create a new run after adjudication.')
        # A run awaiting review can be resumed for failed roles or unfinished routed discussions.
        unfinished_discussion = any(case['status'] in UNFINISHED_CASE_STATES and not is_human_request(case)
                                    for case in run['deliberations'])
        if run['status'] == 'awaiting_human' and not run['metrics'].get('failed_role_count') and not unfinished_discussion:
            raise ValueError('This run completed. Create a new run for another trial.')
        # Compatibility checks can migrate the working manifest. Preserve the
        # actual failed attempt and its original policy before those changes.
        previous_attempt = deepcopy({key: run.get(key) for key in
            ('status', 'requirements', 'observations', 'role_runs', 'diagnostics', 'role_manifest', 'stages',
             'deliberations')})
        if run.get('role_manifest') and run['stages'].get('role_selection') != 'completed':
            ensure_selection_resumable(run['role_manifest'])
        ensure_elicitation_resumable(run)
        configured_client(RunRequest.model_validate(run['request']))
        run.setdefault('attempt_history', []).append(previous_attempt)
        run['diagnostics'] = []
        run['status'] = 'created'
        run['worker_id'] = None
        run['job_lease_until'] = 0
        manifest = run.get('role_manifest')
        if manifest and manifest.get('status') not in {'completed', 'not_applicable'}:
            manifest['status'] = 'pending'
            manifest.pop('last_error', None)
            run['stages']['role_selection'] = 'pending'
        if any(r['status'] == 'failed' for r in run['role_runs']):
            run['stages']['elicitation'] = 'pending'
            for stage in ('normalization', 'verification', 'consolidation', 'deliberation'):
                run['stages'][stage] = 'pending'
            run['machine_snapshot'] = {}
            for stage in ('elicitation', 'normalization', 'verification', 'consolidation', 'deliberation'):
                run.get('stage_results', {}).pop(stage, None)
    result = translate(lambda: store.mutate(run_id, request.expected_version, 'run_resumed', resume, hydrate=True))
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
        record.qualification = q
        retain_base_findings(record)
        q = record.qualification
        target = next(r for r in run['requirements'] if r['revision_id'] == request.revision_id)
        run.setdefault('assessment_history', []).append({'revision_id': request.revision_id, 'previous': target['qualification'],
                                                       'assessment': q.model_dump(mode='json'), 'created_at': now()})
        target.update(qualification=q.model_dump(mode='json'), verification=report)
        return {'revision_id': request.revision_id, 'assessor': actor()}
    return translate(lambda: Store().mutate(run_id, request.expected_version, 'human_assessment', apply, hydrate=True,
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
        if run['request'].get('output_form') == 'needs':
            from .needs import prepare_human_need
            prepare_human_need(store, run, record, [])
        else:
            apply_base_check(store, run, record)
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
    return translate(lambda: store.mutate(run_id, request.expected_version, 'human_requirement_added', apply, hydrate=True,
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
        case = make_case(run, records, [HUMAN_REQUEST_PREFIX + request.question])
        case['case_id'] = uid('case', case['case_id'], uuid.uuid4().hex)
        run['deliberations'].append(case)
        run['stages']['deliberation'] = 'running'
        return case
    store = Store()
    response = translate(lambda: store.mutate(run_id, request.expected_version, 'case_opened', apply, hydrate=True))
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
    return translate(lambda: Store().mutate(run_id, request.expected_version, 'human_message', apply, hydrate=True,
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
    return translate(lambda: Store().mutate(run_id, request.expected_version, 'case_closed', apply, hydrate=True,
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


@router.get('/base-profiles/{profile_id}/needs')
def base_needs_catalogue(profile_id: str, download: bool = False):
    from .base_needs import load_catalogue
    return downloadable(translate(lambda: load_catalogue(profile_id)), download, profile_id+'.needs.json')


@router.get('/runs/{run_id}/needs')
def export_needs(run_id: str, download: bool = False):
    from .needs import needs_export
    return downloadable(translate(lambda: needs_export(Store(), run_id)), download, 'needs.json')


@router.post('/runs/{run_id}/restore')
def restore_aside(run_id: str, request: RestoreRequest):
    from .needs import restore_need
    return translate(lambda: restore_need(Store(), run_id, request, actor()))
