"""Human-review mechanics only; synthetic corrections never touch real catalogues."""
from copy import deepcopy
import csv
import hashlib
import json
import sys
from pathlib import Path
import pytest
from test_resume_discussions import setup
from requirement_reuse_service.workflow import base_needs, base_profile, engine, needs
from requirement_reuse_service.workflow.models import RunRequest, DeriveRequest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import build_base_needs as builder
import base_needs_review as worksheet

PROFILE='dcat-ap-2.0.1'


@pytest.fixture
def review_fixture(tmp_path,monkeypatch):
    directory=tmp_path/'profiles';directory.mkdir()
    path=directory/(PROFILE+'.json')
    path.write_bytes((builder.DIRECTORY/path.name).read_bytes())
    draft=json.loads(builder.build(path,with_review=False))
    target=directory/(PROFILE+'.needs.json');target.write_text(builder.build(path,with_review=False))
    entry=next(e for e in draft['entries'] if e['property']=='dct:issued')
    review={'base_profile_id':PROFILE,'draft_catalogue_hash':draft['catalogue_hash'],
        'status':'reviewed','reviewer':'Synthetic fixture reviewer','reviewed_at':'2026-10-14',
        'phrase_corrections':{entry['id']:{'need':'Users can identify the test fixture publication date.','note':'Synthetic round-trip fixture.'}}}
    review_path=directory/(PROFILE+'.needs-review.json')
    monkeypatch.setattr(builder,'DIRECTORY',directory)
    monkeypatch.setattr(base_profile,'PROFILE_DIRECTORY',directory)
    monkeypatch.setattr(base_needs,'PROFILE_DIRECTORY',directory)
    return path,target,draft,review_path,review


def test_absent_review_preserves_every_committed_draft_byte(monkeypatch):
    for path in sorted(builder.DIRECTORY.glob('*.needs.json')):
        registry=path.with_name(path.name.replace('.needs',''))
        assert builder.build(registry).encode()==path.read_bytes()
        if not registry.with_name(registry.stem+'.needs-review.json').exists():
            assert builder.build(registry,with_review=False).encode()==path.read_bytes()
    monkeypatch.setattr(sys,'argv',['build_base_needs.py','--check']);builder.main()


@pytest.mark.parametrize('fault,match',[
    ('stale','draft_catalogue_hash is stale'),('unknown','Unknown catalogue review entry ID'),
    ('empty','must not be empty'),('curie','contains vocabulary terms'),
    ('camel','contains vocabulary terms'),('duplicate','Duplicate reviewed phrase'),
    ('reviewer','nonempty reviewer'),('date','valid YYYY-MM-DD'),
    ('changed_definition','exactly need and note')])
def test_invalid_review_is_refused_clearly(review_fixture,fault,match):
    path,_,draft,review_path,review=review_fixture
    identifier=next(iter(review['phrase_corrections']));correction=review['phrase_corrections'][identifier]
    if fault=='stale':review['draft_catalogue_hash']='0'*64
    elif fault=='unknown':review['phrase_corrections']={'not-an-entry':correction}
    elif fault=='empty':correction['need']='  '
    elif fault=='curie':correction['need']='Users can identify dct:issued.'
    elif fault=='camel':correction['need']='Users can identify accessURL.'
    elif fault=='duplicate':
        chosen=next(e for e in draft['entries'] if e['id']==identifier)
        correction['need']=next(e['need'] for e in draft['entries'] if e['class']==chosen['class'] and e['id']!=identifier)
    elif fault=='reviewer':review['reviewer']=' '
    elif fault=='date':review['reviewed_at']='2026-02-30'
    else:correction['definition']='An impermissible definition change.'
    review_path.write_text(json.dumps(review))
    with pytest.raises(ValueError,match=match):builder.build(path)


def test_valid_review_changes_only_phrase_and_preserves_provenance(review_fixture,monkeypatch):
    path,target,draft,review_path,review=review_fixture
    review_path.write_text(json.dumps(review,indent=2)+'\n')
    value=builder.build(path);reviewed=json.loads(value)
    identifier=next(iter(review['phrase_corrections']))
    for original,row in zip(draft['entries'],reviewed['entries']):
        if row['id']==identifier:
            assert row['need']==review['phrase_corrections'][identifier]['need']
            assert row['need_draft']==original['need'] and row['review_note']==review['phrase_corrections'][identifier]['note']
            assert {k:v for k,v in row.items() if k not in {'need','need_draft','review_note'}}=={k:v for k,v in original.items() if k!='need'}
        else:assert row==original
    assert reviewed['catalogue_hash']!=draft['catalogue_hash']
    assert reviewed['review']=={'status':'reviewed','reviewer':review['reviewer'],'reviewed_at':review['reviewed_at'],
        'review_file':review_path.name,'review_file_sha256':hashlib.sha256(review_path.read_bytes()).hexdigest(),'corrected_count':1}
    target.write_text(value)
    assert base_needs.load_catalogue(PROFILE)==reviewed
    monkeypatch.setattr(sys,'argv',['build_base_needs.py','--check'])
    builder.main()  # reviewed files reproduce and review JSON is not a registry


def test_csv_cli_round_trip_creates_exactly_one_synthetic_correction(review_fixture,tmp_path,monkeypatch):
    path,target,draft,review_path,review=review_fixture
    csv_path=tmp_path/'worksheet.csv'
    worksheet.main(['export',PROFILE,'--output',str(csv_path)])
    with csv_path.open(newline='') as stream:
        reader=csv.DictReader(stream);assert reader.fieldnames==worksheet.COLUMNS;rows=list(reader)
    assert len(rows)==len(draft['entries']) and all(not r['corrected phrase'] and not r['note'] for r in rows)
    rows[0]['corrected phrase']='Readers can identify the test fixture resource.';rows[0]['note']='Synthetic correction.'
    with csv_path.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=worksheet.COLUMNS);writer.writeheader();writer.writerows(rows)
    worksheet.main(['import',PROFILE,str(csv_path),'--reviewer','Fixture reviewer','--reviewed-at','2026-10-14'])
    saved=json.loads(review_path.read_text())
    assert list(saved['phrase_corrections'])==[rows[0]['entry id']]
    target.write_text(builder.build(path));updated=base_needs.load_catalogue(PROFILE)
    assert updated['review']['corrected_count']==1
    assert sum(a!=b for a,b in zip(draft['entries'],updated['entries']))==1
    monkeypatch.setattr(sys,'argv',['build_base_needs.py','--check']);builder.main()


def test_stale_or_modified_worksheet_does_not_overwrite_review(review_fixture,tmp_path):
    path,_,_,review_path,review=review_fixture
    review_path.write_text(json.dumps(review));before=review_path.read_bytes()
    csv_path=tmp_path/'worksheet.csv';worksheet.export_worksheet(PROFILE,csv_path)
    with csv_path.open(newline='') as stream:rows=list(csv.DictReader(stream))
    rows[0]['definition']='Changed read-only prose.'
    with csv_path.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=worksheet.COLUMNS);writer.writeheader();writer.writerows(rows)
    with pytest.raises(ValueError,match='draft fields changed or are stale'):
        worksheet.import_review(PROFILE,csv_path,'Fixture reviewer','2026-10-14')
    assert review_path.read_bytes()==before


def test_new_and_derived_runs_pin_review_but_old_draft_refuses_drift(setup,review_fixture):
    store,source,client=setup
    path,target,draft,review_path,review=review_fixture
    old=engine.new_run(store,RunRequest(snapshot_id=source['snapshot_id'],strategy='multi_agent',
        base_profile_id=PROFILE,role_ids=['consumer_discovery'],discussion='on_request'))
    assert old['base_needs_catalogue']['catalogue_hash']==draft['catalogue_hash']
    before=deepcopy(store.get('run',old['run_id']))
    review_path.write_text(json.dumps(review));target.write_text(builder.build(path))
    reviewed=base_needs.load_catalogue(PROFILE)
    with pytest.raises(ValueError,match='catalogue changed'):
        needs.classify_needs(store,old,[],None)
    assert store.get('run',old['run_id'])==before
    fresh=engine.new_run(store,RunRequest(snapshot_id=source['snapshot_id'],strategy='multi_agent',
        base_profile_id=PROFILE,role_ids=['consumer_discovery'],discussion='on_request'))
    assert fresh['base_needs_catalogue']['catalogue_hash']==reviewed['catalogue_hash']
    assert fresh['base_needs_catalogue']['review']['reviewer']==review['reviewer']
    engine.execute_run(store,source['run_id'],client)
    parent=store.get('run',source['run_id']);parent_before=deepcopy(parent)
    derived=engine.derive_run(store,parent['run_id'],DeriveRequest(expected_version=parent['version'],
        base_profile_id=PROFILE,scoping='off',discussion='on_request',rationale='Synthetic review-pin test.'))
    assert derived['base_needs_catalogue']['catalogue_hash']==reviewed['catalogue_hash']
    assert store.get('run',parent['run_id'])==parent_before
