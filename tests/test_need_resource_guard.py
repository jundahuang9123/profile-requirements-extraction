"""rq1-need-semantic-grouping-v3 and rq1-need-statement-v4 (Junda, 28 Oct): a need keeps the resource it is about.
In the three JRC runs on v9 + v14, 5 of the 10 needs lost went with the same information about another resource:
grouping merged a catalogue's title, modification date and release date with a catalogue record's, and the writer
put the catalogue's and the dataset's publisher under a need that names no resource. Grouping now writes each
resource as its own group, and a written need names a resource of each member it expresses."""
import json
import pytest
from test_rq1_need_grouping import NeedsClient, need_inputs
from test_semantic_consolidation import revised
from test_resume_discussions import setup  # noqa: F401  (pytest fixture)
from requirement_reuse_service.workflow import needs
from requirement_reuse_service.workflow.engine import verify


@pytest.mark.parametrize('statement,resources', [
    ('Users can know the title of a Catalog.', {'catalogue'}),
    ("Users can know the publisher's identity, such as organization name and type, for a catalog.", {'catalogue'}),
    ('Users can know the title, description, and listing date of a catalog record for a dataset.', {'catalogue record', 'dataset'}),
    # "catalog metadata" may mean the catalogue's own metadata or its records: it names neither.
    ('Users can know the date of last change of a catalog entry (catalog metadata) for a dataset.', {'catalogue record', 'dataset'}),
    ('Users can find metadata about catalog records such as issuance date', {'catalogue record'}),
    ('Users can know the modification date of a metadata record.', {'catalogue record'}),
    ('Find the catalog records that are part of a catalog.', {'catalogue record', 'catalogue'}),
    ('Users can know the modification date of a catalogue record when it changes.', {'catalogue record'}),
    ('A catalogue record which describes a dataset has a language.', {'catalogue record', 'dataset'}),
    # A resource word right before another one only qualifies it.
    ('Users can find the download URL of a dataset distribution.', {'distribution'}),
    ('Users can know when a dataset’s distribution is only accessible via a landing page.', {'distribution'}),
    ("Users can know the language of a dataset's catalogue record.", {'catalogue record'}),
    ("Users can know the licences of the datasets' distributions.", {'distribution'}),
    ('Users can browse the dataset catalogue by theme.', {'catalogue'}),
    ('Users can know the entity responsible for making the dataset available (publisher).', {'dataset'}),
    ('Users can know the endpoint URL of a data service.', {'data service'}),
    ('Users can know the title of a dataset series.', {'dataset series'}),
    # A possessive qualifies the resource after it, so a catalogue's datasets are the datasets alone (a known limit).
    ("Users can know a catalogue's datasets.", {'dataset'}),
    # Word order does not decide: both phrasings of a relationship name the same two resources.
    ('Users can know which datasets a catalogue lists.', {'dataset', 'catalogue'}),
    ('A dcat:Catalog lists dcat:Dataset entries.', {'catalogue', 'dataset'}),
    # A class name in a vocabulary term counts, a property name does not.
    ('The dct:modified of a dcat:CatalogRecord is given.', {'catalogue record'}),
    ('A dcat:DataService has an endpoint URL.', {'data service'}),
    ('A dcat:DatasetSeries groups datasets.', {'dataset series', 'dataset'}),
    ('The dcat:distribution property links to files.', set()),
    # Words that mean no DCAT resource here.
    ('Users can know the age distribution of the population covered.', set()),
    ('Users can know the restrictions on distribution of the data.', set()),
    ('Users can know the rights of the distribution.', {'distribution'}),
    ('Users can know the permissible uses of data, including reproduction, adaptation, modification, combination, and distribution.', set()),
    ('Users can know the distri\u00adbution format.', {'distribution'}),
    ('Users can know the intended use and distribution format of a dataset.', {'dataset', 'distribution'}),
    ('Users can know the catalogue entry point of the portal.', {'catalogue'}),
    ('Users can know when the catalogue records the change.', {'catalogue'}),
    ('Users can know the catalog‑record language.', {'catalogue record'}),
    ('Users can know the identity of a publisher as a person or organization.', set()),
    ('Users can know that a publisher makes the resource available', set()),
])
def test_the_resources_a_need_names(statement, resources):
    assert needs.need_resources(statement) == resources


def resource_inputs(setup, statements):
    store, run, records = need_inputs(setup)
    base = records[0]
    records = [revised(run, base, statement=s, observation_id=f'obs-resource-{i}') for i, s in enumerate(statements)]
    for r in records: r.verification = verify(store, r, run['evidence_ids'])
    return store, run, records


CATALOGUE_AND_RECORD = ['Users can know the title of a Catalog.', 'Users can know the title of a catalog record.',
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
    # One group per resource, and the title naming no resource as a group of its own, last.
    groups = [[r.normalized_statement for r in group] for group in written['groups']]
    assert sorted(groups) == sorted([s] for s in CATALOGUE_AND_RECORD) and groups[-1] == [CATALOGUE_AND_RECORD[2]]
    grouping = store.get_run(run['run_id'])['need_steps']['grouping']
    assert grouping['policy_version'] == 'rq1-need-semantic-grouping-v3' and grouping['group_count'] == 3
    [event] = [a for a in grouping['audit'] if a['action'] == 'kept_apart_by_resource']
    assert event['inputs'] == sorted(r.revision_id for r in records)
    assert {tuple(p['resources']): p['revision_ids'] for p in event['parts']} == {
        ('catalogue',): [records[0].revision_id], ('catalogue record',): [records[1].revision_id], (): [records[2].revision_id]}
    assert event['parts'][-1]['resources'] == []
    assert 'their own group' in event['reason'] and ('(catalogue; catalogue record)' in event['reason'] or '(catalogue record; catalogue)' in event['reason'])


class Record:
    def __init__(self, statement, revision_id): self.normalized_statement, self.revision_id = statement, revision_id


def test_needs_linked_through_a_shared_resource_stay_together():
    # Two phrasings of one relationship, a group about one resource, and a chain of needs sharing resources pairwise.
    for statements in (['Users can know which datasets a catalogue lists.', 'A dcat:Catalog lists dcat:Dataset entries.'],
                       ['Users can know the download URL of a distribution.', 'Users can find the download URL of a dataset distribution.',
                        'Users can know where to download the data.'],
                       ['Users can know the title of a catalogue.', 'Users can know the datasets of a catalogue.',
                        'Users can know the title of a dataset.']):
        group = [Record(s, f'rev-{i}') for i, s in enumerate(statements)]
        assert needs.keep_resources_apart([group]) == ([group], [])


def test_the_same_split_whatever_the_order_of_members():
    group = [Record('Users can know the title.', 'rev-a'), Record('Users can know the title of a catalog record.', 'rev-c'),
             Record('Users can know the title of a Catalog.', 'rev-b')]
    (first, [one]), (second, [other]) = (needs.keep_resources_apart([order]) for order in (group, group[::-1]))
    # Parts in the order of their lowest revision ID, the needs naming no resource last.
    assert [[r.revision_id for r in part] for part in first] == [[r.revision_id for r in part] for part in second] == [['rev-b'], ['rev-c'], ['rev-a']]
    assert one == other and [p['resources'] for p in one['parts']] == [['catalogue'], ['catalogue record'], []]


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
    assert events[0]['action'] == 'split_unwritten_group' and '(catalogue)' in events[0]['reason']
    by_statement = {n.need_statement: n for n in active}
    assert set(by_statement) == {PUBLISHER[0], 'Users can know the identity of a publisher.'}
    assert 'rewrite_not_applied' in by_statement[PUBLISHER[0]].processing_flags
    assert {r for n in active for r in n.parent_revision_ids} == {r.revision_id for r in records}


def offered(*statements):
    return {'g': {'obligation': 'unknown', 'members': {f'm{i}': {'statement': s} for i, s in enumerate(statements)}}}


def written(statement, *expressed):
    return needs.NeedStatements(needs=[{'group_id': 'g', 'statement': statement,
        'members': [{'member_id': f'm{i}', 'expresses_need': e} for i, e in enumerate(expressed)]}])


def test_members_about_unrelated_resources_cannot_share_a_written_need():
    group = offered('Users can know the title of a Catalog.', 'Users can know the title of a catalog record.')
    [error] = needs.statement_errors(written('Users can know the title of a catalogue.', True, True), group, None)
    assert error.startswith('g: members about different resources (catalogue; catalogue record)')
    # The member about the other resource, marked as not expressed, is written separately.
    assert needs.statement_errors(written('Users can know the title of a catalogue.', True, False), group, None) == []
    [error] = needs.statement_errors(written('Users can know the title of a catalog record.', True, False), group, None)
    assert 'name the resource its members are about (catalogue) in the need' in error


def test_each_expressed_member_keeps_a_resource_even_when_another_member_links_them():
    # The dataset member names both a dataset and its catalogue record, so the three stay one group; a rewrite about
    # the dataset alone would drop the record's own member.
    group = offered('Users can know the modification date of a catalogue record.',
                    'Users can know the modification date of a dataset and of its catalogue record.',
                    'Users can know the modification date of a dataset.')
    [error] = needs.statement_errors(written('Users can know the modification date of a dataset.', True, True, True), group, None)
    assert 'name the resource its members are about (catalogue record)' in error
    assert needs.statement_errors(written('Users can know the modification date of a dataset and of its catalogue record.',
                                          True, True, True), group, None) == []


def test_a_rewrite_that_names_the_resource_anywhere_passes():
    # The writer's template puts the information first; when that information is itself a resource, the members'
    # resource comes second.
    group = offered('A dcat:Catalog lists dcat:Dataset entries.')
    assert needs.statement_errors(written('Users can know the datasets listed in a catalogue.', True), group, None) == []
    group = offered('Users can know the distributions of a dataset.')
    assert needs.statement_errors(written("Users can know a dataset's distributions.", True), group, None) == []
    [error] = needs.statement_errors(written('Users can know the available files.', True), group, None)
    assert 'name the resource its members are about (dataset or distribution)' in error
