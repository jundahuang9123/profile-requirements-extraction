"""``scripts/evaluate_workflow.py`` summarizes a downloaded baseline or saved review offline. A published
baseline does not record its run's request, which the summary read unconditionally (KeyError: 'request')."""
import json
import subprocess
import sys
from pathlib import Path

from test_workflow import assess, context, decision, setup_run  # noqa: F401 (fixture)

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'evaluate_workflow.py'
# The summary sections a baseline records in full: the run's identity and its review.
REVIEW = ('run_id', 'snapshot_id', 'strategy', 'implementation_hash', 'machine', 'current_review', 'human_accepted',
          'machine_revision_ids', 'human_added_revision_ids', 'review_actions', 'deliberation', 'needs', 'model_calls')


def evaluate(*args):
    """Run the script as a reviewer does; return what it prints."""
    done = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    return done.stdout


def test_the_script_summarizes_a_downloaded_baseline_and_a_saved_review(context, tmp_path):
    store, client = context
    run = setup_run(context)
    record = run['requirements'][0]
    accepted, _ = decision(client, assess(client, run, record), [record['revision_id']])
    assert accepted.status_code == 200, accepted.text
    run = accepted.json()['run']
    published = client.post(f'/api/rq1/v2/runs/{run["run_id"]}/baselines', json={
        'expected_version': run['version'], 'idempotency_key': 'baseline', 'revision_ids': [record['revision_id']]})
    assert published.status_code == 200, published.text
    base = f'/api/rq1/v2/runs/{run["run_id"]}'
    baseline = client.get(f'{base}/baselines/{published.json()["result"]["baseline_id"]}?download=true')
    (tmp_path / 'baseline.json').write_bytes(baseline.content)
    (tmp_path / 'review.json').write_bytes(client.get(f'{base}/export?download=true').content)
    live = client.get(f'{base}/evaluation').json()

    # The saved review carries the whole run: its summary is the run's own metrics.
    assert json.loads(evaluate(tmp_path / 'review.json')) == live
    # The baseline's summary reports the same review.
    assert evaluate(tmp_path / 'baseline.json', '--out', tmp_path / 'metrics' / 'baseline.json') == ''
    summary = json.loads((tmp_path / 'metrics' / 'baseline.json').read_text(encoding='utf-8'))
    assert {key: summary[key] for key in REVIEW} == {key: live[key] for key in REVIEW}
    assert summary['human_accepted']['count'] == 1 and summary['review_actions'] == {'accept': 1}
