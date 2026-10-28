"""rq1-need-semantic-grouping-v3 and rq1-need-statement-v4 (Junda, 28 Oct): a need keeps the resource it is about.
In the three JRC runs on v9 + v14, 5 of the 10 needs lost went with the same information about another resource:
grouping merged a catalogue's title, modification date and release date with a catalogue record's, and the writer
put the catalogue's and the dataset's publisher under a need that names no resource. Grouping now writes each
resource as its own group, and a written need names the resource its members are about."""
import json
import pytest
from test_rq1_need_grouping import NeedsClient, need_inputs
from test_semantic_consolidation import revised
from test_resume_discussions import setup  # noqa: F401  (pytest fixture)
from requirement_reuse_service.workflow import needs
from requirement_reuse_service.workflow.engine import verify


@pytest.mark.parametrize('statement,resource', [
    ('Users can know the title of a Catalog.', 'catalogue'),
    ("Users can know the publisher's identity, such as organization name and type, for a catalog.", 'catalogue'),
    ('Users can know the title, description, and listing date of a catalog record for a dataset.', 'catalogue record'),
    ('Users can know the date of last change of a catalog entry (catalog metadata) for a dataset.', 'catalogue record'),
    ('Users can find metadata about catalog records such as issuance date', 'catalogue record'),
    ('Users can find the download URL of a dataset distribution.', 'distribution'),
    ('Users can know when a dataset’s distribution is only accessible via a landing page.', 'distribution'),
    ('Users can know the entity responsible for making the dataset available (publisher).', 'dataset'),
    ('Users can know the endpoint URL of a data service.', 'data service'),
    ('Users can know the identity of a publisher as a person or organization.', None),
    ('Users can know that a publisher makes the resource available', None),
])
def test_a_need_is_about_the_first_resource_its_statement_names(statement, resource):
    assert needs.need_resource(statement) == resource


def resource_inputs(setup, statements):
    store, run, records = need_inputs(setup)
    base = records[0]
    records = [revised(run, base, statement=s, observation_id=f'obs-resource-{i}') for i, s in enumerate(statements)]
    for r in records: r.verification = verify(store, r, run['evidence_ids'])
    return store, run, records


CATALOGUE_AND_RECORD = ['Users can know the title of a Catalog.', 'Users can know the title of a catalog record for a dataset.',
                        'Users can know the title.']


def test_grouping_writes_each_resource_as_its_own_group(setup, monkeypatch):
    # The grouping model put a catalogue's title, a catalogue record's title and a title naming no resource together,
    # as in JRC run-2f7b8d7a; the writer kept only the record's title, and the catalogue's title was lost.
    store, run, records = resource_inputs(setup, CATALOGUE_AND_RECORD)
    monkeypatch.setattr(needs, 'check_proposal_support', lambda store, run, records, client: records)
    monkeypatch.setattr(needs, 'grouped_block', lambda *args, **kwargs: ([list(records)], []))
    written = {}
    class Written(Exception): pass
    def write(store, run, groups, client, profile):
        written['groups'] = groups; raise Written
    monkeypatch.setattr(needs, 'write_needs', write)
    with pytest.raises(Written):
        needs.process_needs(store, run, records, NeedsClient(), None)
    statements = sorted(sorted(r.normalized_statement for r in group) for group in written['groups'])
    assert statements == [[CATALOGUE_AND_RECORD[0], CATALOGUE_AND_RECORD[2]], [CATALOGUE_AND_RECORD[1]]]
    grouping = store.get_run(run['run_id'])['need_steps']['grouping']
    assert grouping['policy_version'] == 'rq1-need-semantic-grouping-v3' and grouping['group_count'] == 2
    [event] = [a for a in grouping['audit'] if a['action'] == 'kept_apart_by_resource']
    assert event['inputs'] == sorted(r.revision_id for r in records)
    assert [p['resource'] for p in event['parts']] == ['catalogue', 'catalogue record'] and 'different resources' in event['reason']


def test_a_group_about_one_resource_stays_whole():
    class Record:
        def __init__(self, statement, revision_id): self.normalized_statement, self.revision_id = statement, revision_id
    group = [Record('Users can know the download URL of a distribution.', 'rev-1'),
             Record('Users can find the download URL of a dataset distribution.', 'rev-2'),
             Record('Users can know where to download the data.', 'rev-3')]
    assert needs.keep_resources_apart([group]) == ([group], [])


class ResourceWriter(NeedsClient):
    """Writes the publisher need without its resource first, then as asked; or never names it."""
    def __init__(self, keeps_dropping=False):
        super().__init__(); self.keeps_dropping = keeps_dropping
    def generate_structured(self, **kwargs):
        if kwargs['output_model'].__name__ != 'NeedStatements': return super().generate_structured(**kwargs)
        data = json.loads(kwargs['user']); self.calls.append(('NeedStatements', data))
        corrected = 'Correct only these failing rows' in kwargs['system'] and not self.keeps_dropping
        results = []
        for identifier, group in data['groups'].items():
            texts = [m['statement'] for m in group['members'].values()]
            statement = ('Users can know the publisher of a catalogue.' if corrected or (len(texts) == 1 and 'Catalog' in texts[0] and not self.keeps_dropping)
                         else 'Users can know the identity of a publisher.')
            results.append({'group_id': identifier, 'statement': statement, 'condition': '',
                            'members': [{'member_id': m, 'expresses_need': True} for m in group['members']]})
        return kwargs['output_model'].model_validate({'needs': results})


PUBLISHER = ['Users can know the publisher of a Catalog.', 'Users can know the identity of a publisher as a person or organization.']


def test_the_written_need_names_the_resource_its_members_are_about(setup):
    # As in JRC run-f36c8783: the writer put the catalogue's publisher under "the identity of a publisher as a person
    # or organization", which names no resource. Now that rewrite gets one correction.
    store, run, records = resource_inputs(setup, PUBLISHER)
    client = ResourceWriter()
    active, events = needs.write_needs(store, run, [records], client, None)
    assert [n.need_statement for n in active] == ['Users can know the publisher of a catalogue.']
    writes = [d for name, d in client.calls if name == 'NeedStatements']
    assert len(writes) == 2 and [e['action'] for e in events] == ['merge_need'] and events[0]['policy_version'] == 'rq1-need-statement-v4'
    calls = len(client.calls)
    needs.write_needs(store, run, [records], client, None)
    assert len(client.calls) == calls


def test_a_writer_that_keeps_dropping_the_resource_loses_no_need(setup):
    store, run, records = resource_inputs(setup, PUBLISHER)
    active, events = needs.write_needs(store, run, [records], ResourceWriter(keeps_dropping=True), None)
    # The group goes back to the writer member by member; the catalogue's publisher keeps its own statement, flagged,
    # and the need naming no resource is written as before.
    assert events[0]['action'] == 'split_unwritten_group' and 'catalogue' in events[0]['reason']
    by_statement = {n.need_statement: n for n in active}
    assert set(by_statement) == {PUBLISHER[0], 'Users can know the identity of a publisher.'}
    assert 'rewrite_not_applied' in by_statement[PUBLISHER[0]].processing_flags
    assert {r for n in active for r in n.parent_revision_ids} == {r.revision_id for r in records}


def test_members_about_different_resources_cannot_share_a_written_need():
    offered = {'g': {'obligation': 'unknown', 'members': {'a': {'statement': 'Users can know the title of a Catalog.'},
                                                         'b': {'statement': 'Users can know the title of a catalog record.'}}}}
    answer = needs.NeedStatements(needs=[{'group_id': 'g', 'statement': 'Users can know the title of a catalogue.',
        'members': [{'member_id': 'a', 'expresses_need': True}, {'member_id': 'b', 'expresses_need': True}]}])
    [error] = needs.statement_errors(answer, offered, None)
    assert error.startswith('g: members about different resources (catalogue, catalogue record)')
    # The member about the other resource, marked as not expressed, is written separately.
    answer.needs[0].members[1].expresses_need = False
    assert needs.statement_errors(answer, offered, None) == []
    answer.needs[0].statement = 'Users can know the title of a catalog record.'
    assert 'name the resource its members are about (catalogue)' in needs.statement_errors(answer, offered, None)[0]
