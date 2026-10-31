"""A run whose worker stops during base review can be resumed; reviewed batches are not sent again."""
import re
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from test_routed_stakeholder_workflow import setup  # noqa: F401 (fixture)
from test_base_review import Reviewer, prepared
from requirement_reuse_service.main import app
from requirement_reuse_service.workflow import api, engine
from requirement_reuse_service.workflow import base_review as br
from requirement_reuse_service.workflow.models import DeriveRequest, RequirementRecord


class ServerStopped(BaseException):
    """Ends the worker as a stopped server does: the run's failure handler never runs."""


class StopsAtSecondBatch(Reviewer):
    def generate_structured(self, *, user, output_model, **kwargs):
        if output_model == br.BaseReview and any(kind == 'BaseReview' for kind, _ in self.calls):
            raise ServerStopped()
        return super().generate_structured(user=user, output_model=output_model, **kwargs)


def reviewed(client):
    return [key for kind, payload in client.calls if kind == 'BaseReview' for key in payload['needs']]


def resume(store, run_id):
    saved = store.get('run', run_id)
    return TestClient(app).post(f'/api/rq1/v2/runs/{run_id}/resume', json={'expected_version': saved['version']})


@pytest.fixture
def stopped_in_base_review(setup, monkeypatch):
    store, run, cat = prepared(setup, 4)
    records = [RequirementRecord.model_validate(r) for r in run['requirements']]
    payload, aliases = br.make_payload(store, run, records, cat, 'before_discussion')
    # Four needs no longer fit one review, so base review runs in several batches.
    monkeypatch.setattr(br, 'MAX_PAYLOAD', len(br.canonical(br.translate_ids(payload, {v: k for k, v in aliases.items()}))) - 1)
    def ready(r):
        r.update(status='failed')
        for stage in ('acquisition', 'decomposition', 'role_selection', 'elicitation', 'normalization', 'verification', 'consolidation'):
            r['stages'][stage] = 'completed'
        r['machine_snapshot'].update(set_aside_observations=[], conflicts=[], consolidation_events=[])
    store.mutate(run['run_id'], None, 'ready', ready, parts=True)
    source = store.get('run', run['run_id'])
    child = engine.derive_run(store, source['run_id'], DeriveRequest(start_from='base_review', expected_version=source['version'],
        rationale='Server stops during base review.', execution_mode='stepwise'))
    first = StopsAtSecondBatch()
    with pytest.raises(ServerStopped):
        engine.execute_run(store, child['run_id'], first)
    return store, child['run_id'], first


def test_a_run_stopped_during_base_review_resumes_and_keeps_reviewed_batches(stopped_in_base_review, monkeypatch):
    store, run_id, first = stopped_in_base_review
    stopped = store.get('run', run_id)
    assert stopped['status'] == 'reviewing_base' and stopped['stages']['base_review'] == 'running'
    assert 0 < len(reviewed(first)) < 4
    client = Reviewer()
    monkeypatch.setattr(api, 'execute_run', lambda store, run_id: engine.execute_run(store, run_id, client))
    monkeypatch.setattr(api, 'configured_client', lambda request: client)
    response = resume(store, run_id)
    assert response.status_code == 202, response.text
    done = store.get('run', run_id)
    assert done['status'] == 'paused', done['diagnostics']
    assert done['stages']['base_review'] == 'completed'
    active = [r for r in done['requirements'] if r['revision_id'] in done['active_revision_ids']]
    assert len(active) == 4 and all(r['base_relation']['status'] == 'checked' for r in active)
    # Each need is reviewed once across both workers: the batch saved before the stop is reused.
    assert len(reviewed(first)) + len(reviewed(client)) == 4
    assert done['attempt_history'][-1]['status'] == 'reviewing_base'


def test_resume_during_base_review_still_waits_for_an_active_lease(stopped_in_base_review, monkeypatch):
    store, run_id, _ = stopped_in_base_review
    store.mutate(run_id, None, 'fixture_lease', lambda r: r.update(worker_id='other-worker', job_lease_until=time.time() + 900))
    monkeypatch.setattr(api, 'execute_run', lambda store, run_id: None)
    monkeypatch.setattr(api, 'configured_client', lambda request: Reviewer())
    response = resume(store, run_id)
    assert response.status_code == 409, response.text
    assert store.get('run', run_id)['status'] == 'reviewing_base'


def test_every_status_a_stage_starts_with_can_be_resumed():
    started = set(re.findall(r"start_stage\('[a-z_]+', '([a-z_]+)'\)", Path(engine.__file__).read_text()))
    assert 'reviewing_base' in started
    assert started <= api.RESUMABLE_STATUSES
