"""Freeze declared tasks from raw SPRINT paraphrases, never reference answers."""
import hashlib
import json
from pathlib import Path
import pytest
from requirement_reuse_service.workflow import benchmarks
from requirement_reuse_service.workflow.storage import Store


def test_mobility_declared_tasks_match_committed_raw_paraphrases_exactly():
    tasks,metadata=benchmarks.use_case_inputs('mobilitydcat')
    raw=json.loads((benchmarks.BENCHMARK_ROOT/'mobilitydcat/input-raw/sprint-competency-tasks.json').read_text())
    committed=json.loads((benchmarks.BENCHMARK_ROOT/'mobilitydcat/use-cases.json').read_text())
    assert len(tasks)==12 and [t.id for t in tasks]==[f'CQ-{i}' for i in range(1,13)]
    assert [(t.id,t.statement) for t in tasks]==[(r['id'],r['task']) for r in raw['tasks']]
    assert [t.statement for t in tasks]==[r['statement'] for r in committed]
    assert all(t.kind=='competency_question' and t.author=='Junda Huang (benchmark curator; paraphrase of SPRINT D2.3)'
               and t.written_at=='2026-10-09' and t.basis=='SPRINT D2.3 competency tasks (paraphrased); benchmark-data/mobilitydcat/input-raw/sprint-competency-tasks.json' for t in tasks)
    assert all(set(r)=={'id','statement','kind','basis','author','written_at'} for r in committed)
    assert metadata.file=='benchmark-data/mobilitydcat/use-cases.json'


def test_real_mobility_import_freezes_twelve_tasks_and_exact_file_hash(tmp_path,monkeypatch):
    read_bytes=Path.read_bytes
    def raw_only(path):
        assert not {'reference-requirements','input-preconsolidation'} & set(path.parts)
        return read_bytes(path)
    monkeypatch.setattr(Path,'read_bytes',raw_only)
    path=benchmarks.BENCHMARK_ROOT/'mobilitydcat/use-cases.json'
    committed=json.loads(path.read_text());store=Store(str(tmp_path/'mobility.sqlite3'))
    loaded=benchmarks.load_benchmark(store,'mobilitydcat');snapshot=loaded['snapshot']
    assert len(loaded['sources'])==16 and len(snapshot['user_tasks'])==12
    assert snapshot['use_case_input']=={'file':'benchmark-data/mobilitydcat/use-cases.json',
        'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    assert [{k:t[k] for k in committed[0]} for t in snapshot['user_tasks']]==committed
    assert store.get('snapshot',snapshot['snapshot_id'])==snapshot
    assert not store.list('run')


@pytest.mark.parametrize('case_id',['healthdcat','geodcat','statdcat','jrc-research'])
def test_other_real_cases_still_import_without_declared_tasks(tmp_path,case_id,monkeypatch):
    read_bytes=Path.read_bytes
    def raw_only(path):
        assert not {'reference-requirements','input-preconsolidation'} & set(path.parts)
        return read_bytes(path)
    monkeypatch.setattr(Path,'read_bytes',raw_only)
    assert benchmarks.use_case_inputs(case_id)==([],None)
    store=Store(str(tmp_path/'other.sqlite3'))
    snapshot=benchmarks.load_benchmark(store,case_id)['snapshot']
    assert snapshot['user_tasks']==[] and snapshot['use_case_input'] is None
    assert not store.list('run')


def test_empty_epos_case_keeps_its_existing_import_refusal(tmp_path):
    assert benchmarks.use_case_inputs('epos')==([],None)
    with pytest.raises(ValueError,match='no allowlisted raw inputs'):
        benchmarks.load_benchmark(Store(str(tmp_path/'epos.sqlite3')),'epos')
