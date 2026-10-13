"""Offline base-profile classification; no references or model calls are used."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'requirement-reuse-service'))

from requirement_reuse_service.workflow import base_profile
from requirement_reuse_service.workflow.base_profile import check_record, constraint_signals, load_profile


@pytest.fixture
def profile():
    def prop(obligation='recommended', **changes):
        return {'obligation': obligation, 'max': None, 'range': None,
                'vocabulary': None, 'labels': [], **changes}
    return {'id': 'dcat-ap-2.0.1', 'source': {'repo': 'SEMICeu/DCAT-AP', 'commit': 'pinned', 'files': {}},
            'classes': {
                'dcat:Dataset': {'dct:title': prop('mandatory'), 'dct:description': prop('mandatory'),
                                 'dct:publisher': prop(range='foaf:Agent', labels=['publisher']), 'dcat:contactPoint': prop(),
                                 'dcat:theme': prop(), 'dcat:distribution': prop(),
                                 'dct:spatial': prop(), 'adms:versionNotes': prop('optional'),
                                 'owl:versionInfo': prop('optional')},
                'dcat:DataService': {'dct:title': prop('mandatory'), 'dct:description': prop('optional'),
                                     'dcat:endpointURL': prop('mandatory'), 'dcat:endpointDescription': prop(),
                                     'dcat:keyword': prop('recommended')},
                'dcat:Distribution': {'dcat:accessURL': prop('mandatory'), 'dcat:downloadURL': prop(),
                                      'dct:description': prop('optional'), 'adms:status': prop('optional'),
                                      'dct:format': prop('optional')},
                'dcat:CatalogRecord': {'dct:modified': prop('mandatory'), 'adms:status': prop('optional')},
                'foaf:Agent': {'foaf:name': prop('mandatory')},
                'dcat:Catalog': {}, 'skos:Concept': {},
            }}


def record(statement, *, resource='Dataset', metadata='', obligation='unknown', scope='Unspecified', **changes):
    return {'raw_statement': statement, 'normalized_intent': {'resource_type': resource,
        'metadata_need': metadata, 'obligation_hint': obligation}, 'scope': scope,
        'evidence_links': [{'evidence_id': 'outside', 'quote': 'Supporting excerpt.', 'relation': 'supports'}],
        **changes}


def checked(row, profile, **kwargs):
    return check_record(row, profile, evidence_by_id={
        'base': {'source_version_id': 'base-spec'},
        'outside': {'source_version_id': 'inspire'},
    }, base_source_version_ids={'base-spec'}, **kwargs)


def test_loader_records_actual_bytes_hash_and_rejects_paths(tmp_path, monkeypatch, profile):
    monkeypatch.setattr(base_profile, 'PROFILE_DIRECTORY', tmp_path)
    raw = json.dumps(profile, indent=2).encode()
    (tmp_path / 'dcat-ap-2.0.1.json').write_bytes(raw)
    registry, digest = load_profile('dcat-ap-2.0.1')
    assert registry == profile and digest == hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError, match='Invalid base profile'):
        load_profile('../dcat-ap-2.0.1')
    changed = dict(profile, id='dcat-ap-2.1.1')
    (tmp_path / 'dcat-ap-2.0.1.json').write_text(json.dumps(changed))
    with pytest.raises(ValueError, match='invalid id'):
        load_profile('dcat-ap-2.0.1')


@pytest.mark.parametrize('statement,obligation', [
    ('Datasets should include a dct:publisher.', 'recommended'),
    ('A consumer must be able to process the Dataset title.', 'mandatory'),
    ('A system must be able to retrieve dct:publisher.', 'mandatory'),
    ('A system shall be able to interpret dct:publisher.', 'mandatory'),
])
def test_inherited_and_system_abilities(profile, statement, obligation):
    result, findings = checked(record(statement, obligation=obligation), profile)
    assert result['relation'] == 'inherited' and not findings


def test_base_specification_cannot_self_tighten(profile):
    row = record('Datasets must include dct:publisher.', obligation='mandatory',
                 evidence_links=[{'evidence_id': 'base', 'relation': 'supports'}])
    result, findings = checked(row, profile)
    assert result['relation'] == 'inherited' and not findings
    assert 'stricter label not supported outside the base specification' in result['notes']


@pytest.mark.parametrize('relation', ['contextualizes', 'contradicts'])
def test_nonbase_context_and_contradiction_do_not_support_tightening(profile, relation):
    row = record('Datasets must include dct:publisher.', obligation='mandatory', evidence_links=[
        {'evidence_id': 'base', 'relation': 'supports'},
        {'evidence_id': 'outside', 'relation': relation}])
    result, _ = checked(row, profile)
    assert result['relation'] == 'inherited'


def test_missing_evidence_is_not_outside_base_support(profile):
    result, _ = checked(record('Datasets must include dct:publisher.', obligation='mandatory',
        evidence_links=[{'evidence_id': 'not-found', 'relation': 'supports'}]), profile)
    assert result['relation'] == 'inherited'


def test_unclassified_base_sources_keep_a_stronger_claim_for_review(profile):
    row = record('Datasets must include dct:publisher.', obligation='mandatory')
    result, findings = check_record(row, profile,
        evidence_by_id={'outside': {'source_version_id':'domain-source'}})
    assert result['relation'] == 'inherited' and result['requires_review']
    assert findings[0]['criterion'] == 'unresolved_base_source_classification'
    assert findings[0]['severity'] == 'review'


@pytest.mark.parametrize('statement,terms', [
    ('Dataset must publish dct:title and ex:roadDirection.', ['dct:title', 'ex:roadDirection']),
    ('Dataset must publish dct:title and dct:description.', ['dct:description', 'dct:title']),
])
def test_compound_property_claim_cannot_be_excluded_by_one_inherited_match(profile, statement, terms):
    result, findings = checked(record(statement, obligation='mandatory'), profile)
    assert result['relation'] == 'inherited' and result['requires_review']
    assert result['statement_property_candidates'] == terms
    assert findings[0]['criterion'] == 'compound_base_check'


def test_class_and_range_curies_are_not_compound_property_claims(profile):
    result, findings = checked(record('dcat:Dataset should publish a dct:publisher that is a foaf:Agent.',
        obligation='recommended'), profile)
    assert result['relation'] == 'inherited' and not result.get('requires_review')
    assert findings == []


def test_compound_cue_does_not_change_an_already_constrained_relation(profile):
    result, _ = checked(record('Dataset must publish dct:title and ex:roadDirection for traffic metadata.',
        obligation='mandatory'), profile)
    assert result['relation'] == 'constrained' and not result.get('requires_review')


@pytest.mark.parametrize('statement', [
    'Datasets must include a title and driving direction.',
    'Datasets must include a title as well as driving direction.',
    'Datasets must include a title; driving direction is published.',
])
def test_natural_language_compound_inherited_match_is_provisional(profile, statement):
    result, findings = checked(record(statement, metadata='title', obligation='mandatory'), profile)
    assert result['relation'] == 'inherited' and result['requires_review']
    assert result['compound_signals']
    assert findings[0]['criterion'] == 'compound_base_check'


@pytest.mark.parametrize('statement,signal', [
    ('Datasets must not include dct:title.', 'not'),
    ('Datasets must never include dct:title.', 'never'),
    ('Datasets must be described without a title.', 'without'),
    ('Datasets must avoid a title.', 'avoid'),
])
def test_negated_base_property_match_needs_review_without_inventing_relation(profile, statement, signal):
    result, findings = checked(record(statement, metadata='title', obligation='mandatory'), profile)
    assert result['relation'] == 'inherited' and result['requires_review']
    assert result['polarity_signals'] == [signal]
    assert findings[0]['criterion'] == 'base_polarity_review' and findings[0]['severity'] == 'review'


def test_tightening_with_nonbase_support(profile):
    result, findings = checked(record('A mandatory contact point must include e-mail.',
        metadata='contact point', obligation='mandatory'), profile)
    assert result['relation'] == 'tightened' and result['property'] == 'dcat:contactPoint' and not findings


def test_constrained_vocabulary_with_equal_or_unknown_obligation(profile):
    row = record('Service metadata must include at least one keyword from the Regulation 1205/2008 vocabulary.',
                 resource='DataService', metadata='keyword')
    result, _ = checked(row, profile)
    assert result['relation'] == 'constrained' and result['property'] == 'dcat:keyword'
    assert any(signal.startswith('controlled_vocabulary:') for signal in result['constraint_signals'])


def test_spatial_quality_is_new_without_a_base_property(profile):
    result, _ = checked(record('Metadata shall contain information on the quality and validity of spatial data sets.',
        metadata='quality and validity of spatial data sets'), profile)
    assert result['relation'] == 'new' and result['property'] is None


def test_relaxing_base_obligation_is_blocking(profile):
    result, findings = checked(record('CatalogRecord should include dct:modified if access is restricted.',
        resource='CatalogRecord', obligation='recommended'), profile)
    assert result['relation'] == 'loosened' and result['base_obligation'] == 'mandatory'
    assert findings[0]['criterion'] == 'conflicts_with_base' and findings[0]['severity'] == 'blocking'


def test_unknown_class_is_kept_for_review(profile):
    result, findings = checked(record('Record must contain a title.', resource='Unknown'), profile)
    assert result['relation'] == 'unresolved_class' and result['class'] is None
    assert findings[0]['severity'] == 'review'


def test_explicit_property_precedes_text_and_lexicon(profile):
    result, _ = checked(record('Publish dct:title and contact point.', metadata='contact point',
        base_property='dcat:Dataset/dct:publisher'), profile)
    assert result['property'] == 'dct:publisher' and result['resolved_via'] == 'base_property'


def test_explicit_property_not_in_candidate_class_resolves_label_noise(profile):
    result, _ = checked(record('Publish a publisher.', resource='Distribution',
        base_property='dcat:Dataset/dct:publisher'), profile)
    assert result['relation'] == 'inherited' and result['property'] == 'dct:publisher'
    assert result['class'] == 'dcat:Dataset' and result['candidate_class'] == 'dcat:Distribution'
    assert result['notes']


def test_prefix_alias_and_case_precede_metadata_lexicon(profile):
    result, _ = checked(record('Publish DCTERMS:title.', metadata='publisher'), profile)
    assert result['property'] == 'dct:title' and result['resolved_via'] == 'statement_curie'


@pytest.mark.parametrize('resource,metadata,expected', [
    ('DataService', 'endpoint description', 'dcat:endpointDescription'),
    ('Distribution', 'access URL', 'dcat:accessURL'),
    ('Distribution', 'download URL', 'dcat:downloadURL'),
    ('Dataset', 'version notes', 'adms:versionNotes'),
    ('Dataset', 'geographic extent', 'dct:spatial'),
    ('Agent', 'name', 'foaf:name'),
])
def test_longest_synonym_and_class_lexicon(profile, resource, metadata, expected):
    result, _ = checked(record('Description is published.', resource=resource, metadata=metadata), profile)
    assert result['property'] == expected and result['resolved_via'] == 'metadata_need_lexicon'


def test_category_is_not_a_theme_synonym(profile):
    result, _ = checked(record('Publish licence or contract category.', metadata='category'), profile)
    assert result['relation'] == 'new' and result['property'] is None


def test_domain_acronyms_are_case_sensitive(profile):
    innocent, _ = checked(record('A dataset publishes its title.', metadata='title'), profile)
    assert innocent['relation'] == 'inherited' and not innocent['constraint_signals']
    acronym, _ = checked(record('An ITS dataset publishes a title.', metadata='title'), profile)
    assert acronym['relation'] == 'constrained' and 'domain_acronym: ITS' in acronym['constraint_signals']


@pytest.mark.parametrize('statement,scope,kind', [
    ('Title is published exactly one time.', 'Unspecified', 'cardinality:'),
    ('Title is required if access is restricted.', 'Unspecified', 'condition:'),
    ('Title is published.', 'transport discovery', 'domain_scope:'),
    ('Title is published for traffic metadata.', 'Dataset', 'domain_term:'),
])
def test_constraint_signals_are_inspectable(profile, statement, scope, kind):
    result, _ = checked(record(statement, scope=scope), profile)
    assert result['relation'] == 'constrained' and any(s.startswith(kind) for s in result['constraint_signals'])


def test_v3_declared_constraint_is_not_proof_and_hidden_scope_still_counts(profile):
    declared, findings = checked(record('Dataset title is published.', metadata='title',
        extension_kind='value_constraint', base_property='dcat:Dataset/dct:title'), profile)
    assert declared['relation'] == 'inherited' and declared['requires_review']
    assert findings[0]['criterion'] == 'unconfirmed_extension_constraint'
    constrained, _ = checked(record('Dataset title is published for ITS discovery.', metadata='title',
        extension_kind='not_an_extension', base_property='dcat:Dataset/dct:title'), profile)
    assert constrained['relation'] == 'constrained'


def test_unknown_statement_property_precedes_base_label(profile):
    result, _ = checked(record('Title records ex:servicePurpose.', metadata='title'), profile)
    assert result['relation'] == 'new' and result['property'] == 'ex:servicePurpose'
    assert result['resolved_via'] == 'statement_curie'


def test_range_curie_does_not_hide_a_known_property_label(profile):
    result, _ = checked(record('Publisher is a foaf:Agent.', metadata='publisher'), profile)
    assert result['property'] == 'dct:publisher' and result['relation'] == 'inherited'


def test_named_regulation_after_from_is_a_value_constraint(profile):
    result, _ = checked(record('Service metadata must include at least one keyword from Regulation 1205/2008.',
        resource='DataService', metadata='keyword'), profile)
    assert result['relation'] == 'constrained'
    assert 'controlled_vocabulary: from Regulation 1205/2008' in result['constraint_signals']


def test_unconfirmed_explicit_mapping_requires_review(profile):
    result, findings = checked(record('The quality of spatial datasets is recorded.',
        base_property='dcat:Dataset/dct:title'), profile)
    assert result['relation'] == 'inherited' and result['requires_review']
    assert findings[0]['criterion'] == 'unconfirmed_base_property'


def test_saved_extraction_names_use_exact_casefolded_basenames(profile):
    row = record('Dataset must include dct:publisher.', obligation='mandatory',
        evidence_links=[{'evidence_id': 'base', 'relation': 'supports'}])
    evidence = {'base': {'source_version_id': 'old-source'}}
    base_names = ['mobilitydcat/input-raw/dcat-ap-2.0.0.pdf']
    result, _ = check_record(row, profile, evidence_by_id=evidence,
        source_name_by_version={'old-source': 'DCAT-AP-2.0.0.PDF'}, base_source_names=base_names)
    assert result['relation'] == 'inherited'
    nonbase, _ = check_record(row, profile, evidence_by_id=evidence,
        source_name_by_version={'old-source': 'inspire-metadata.pdf'}, base_source_names=base_names)
    assert nonbase['relation'] == 'tightened'
    unknown, _ = check_record(row, profile, evidence_by_id=evidence, base_source_names=base_names)
    assert unknown['relation'] == 'inherited'


def test_check_is_read_only(profile):
    row = record('Title is published for mobility data.', metadata='title')
    before = deepcopy((row, profile))
    check_record(row, profile)
    assert (row, profile) == before


@pytest.mark.parametrize('statement', [
    'Datasets may include dcat:contactPoint.',
    'Datasets should be linked to a contact point for enquiries about access or use.',
])
def test_weaker_label_without_added_need_is_inherited(profile, statement):
    result, findings = checked(record(statement, metadata='contact point', obligation='optional'), profile)
    assert result['relation'] == 'inherited' and findings == []
    assert 'weaker label than base' in result['notes']


@pytest.mark.parametrize('statement', [
    'DataService must expose an endpoint URL where clients can access the service.',
    'DataService must expose an endpoint URL where data can be retrieved.',
    'Dataset must provide a title and its text.',
])
def test_relative_clause_and_ordinary_conjunction_do_not_add_constraints(profile, statement):
    row = record(statement, resource='DataService' if 'DataService' in statement else 'Dataset', obligation='mandatory')
    result, findings = checked(row, profile)
    assert result['relation'] == 'inherited' and not result.get('requires_review')
    assert not result['constraint_signals'] and findings == []


@pytest.mark.parametrize('statement', [
    'Dataset title is required where applicable.',
    'Dataset title is required when the dataset is published.',
    'Dataset title is required where access is restricted.',
    'If the dataset is public, its title is required.',
])
def test_applicability_clause_is_a_constraint(profile, statement):
    result, _ = checked(record(statement, metadata='title'), profile)
    assert result['relation'] == 'constrained'
    assert any(s.startswith('condition:') for s in result['constraint_signals'])


def test_when_describes_a_timestamp_not_applicability(profile):
    result, _ = checked(record('Dataset must record the date when it was modified.',
        resource='CatalogRecord', metadata='last modified', obligation='mandatory'), profile)
    assert result['relation'] == 'inherited' and not result['constraint_signals']


def test_generic_vocabulary_is_inherited_but_an_alternative_is_retained(profile):
    profile['classes']['dcat:Dataset']['dcat:theme']['vocabulary'] = 'http://example.org/base-theme'
    generic, _ = checked(record('Dataset theme uses a controlled vocabulary.', metadata='theme'), profile)
    assert generic['relation'] == 'inherited' and not generic['constraint_signals']
    added, _ = checked(record('Dataset theme comes from Regulation 1205/2008.', metadata='theme'), profile)
    assert added['relation'] == 'constrained'


@pytest.mark.parametrize('phrase,prop', [
    ('validity interval', 'dct:temporal'), ('period of time', 'dct:temporal'),
    ('start and end dates', 'dct:temporal'), ('bounding box', 'dct:spatial'),
    ('geographic location', 'dct:spatial'),
])
def test_requested_coverage_synonyms_resolve_to_inherited_property(profile, phrase, prop):
    profile['classes']['dcat:Dataset']['dct:temporal'] = {
        'obligation': 'recommended', 'labels': [], 'range': 'dct:PeriodOfTime'}
    result, findings = checked(record('Dataset should provide its ' + phrase + '.',
        metadata=phrase, obligation='recommended'), profile)
    assert result['property'] == prop and result['relation'] == 'inherited'
    assert not result.get('requires_review') and findings == []


def test_role_and_relationship_resolution_uses_existing_base_classes(profile):
    profile['classes']['dcat:Relationship'] = {
        'dcat:hadRole': {'obligation': 'mandatory', 'labels': ['hadRole'], 'range': 'dcat:Role'},
        'dct:relation': {'obligation': 'mandatory', 'labels': ['relation'], 'range': 'rdfs:Resource'}}
    for need, prop in [('hadRole', 'dcat:hadRole'), ('Relationship', 'dct:relation')]:
        result, _ = checked(record('The ' + need + ' is provided.', metadata=need, obligation='mandatory'), profile)
        assert result['class'] == 'dcat:Relationship' and result['property'] == prop
        assert result['relation'] == 'inherited' and result['candidate_class'] == 'dcat:Dataset'


def test_owner_role_entity_is_qualified_attribution_not_an_unknown_need(profile):
    profile['classes']['dcat:Dataset']['prov:qualifiedAttribution'] = {
        'obligation': 'optional', 'labels': [], 'range': 'prov:Attribution'}
    result, _ = checked(record('Metadata provides a role entity identifying the owner.',
        metadata='role entity for owner', obligation='optional'), profile)
    assert result['property'] == 'prov:qualifiedAttribution' and result['relation'] == 'inherited'


@pytest.mark.parametrize('contrast', ['rather than', 'instead of'])
def test_contrast_preserves_institutional_email_constraint(profile, contrast):
    result, _ = checked(record('The contact point uses an institutional e-mail address ' + contrast + ' a personal one.',
        metadata='contact point', obligation='recommended'), profile)
    assert result['relation'] == 'constrained'
    assert 'value_restriction: ' + contrast in result['constraint_signals']


def test_base_only_stronger_label_does_not_erase_added_contrast(profile):
    result, _ = checked(record('dct:publisher must use an Agent URI rather than a literal string.',
        obligation='mandatory', evidence_links=[{'evidence_id': 'base', 'relation': 'supports'}]), profile)
    assert result['relation'] == 'constrained'
    assert 'stricter label not supported outside the base specification' in result['notes']


def test_multiple_possible_base_classes_with_different_definitions_remain_reviewable(profile):
    profile['classes']['dcat:Catalog']['dct:publisher'] = {
        'obligation': 'mandatory', 'labels': ['publisher'], 'range': 'foaf:Agent'}
    result, findings = checked(record('The publisher is recorded.', resource='Agent', metadata='publisher'), profile)
    assert result['relation'] == 'inherited' and result['requires_review']
    assert result['base_property_classes'] == ['dcat:Catalog', 'dcat:Dataset']
    assert any(f['criterion'] == 'ambiguous_base_property_class' for f in findings)


@pytest.mark.parametrize('statement,need', [
    ('A dataset must provide a concise abstract.', 'abstract'),
    ('Datasets should record their owning entity.', 'ownership'),
    ('Spatial data services should specify their service type.', 'service type'),
    ('The relationship between a dataset and its owner uses the PROV ontology.', 'owning entity'),
])
def test_resource_subject_is_not_a_cross_class_property_match(profile, statement, need):
    profile['classes']['dcat:Catalog']['dcat:dataset'] = {'obligation': 'mandatory', 'labels': ['dataset']}
    profile['classes']['dcat:Catalog']['dcat:service'] = {'obligation': 'optional', 'labels': ['service']}
    profile['classes']['dcat:Dataset']['dct:relation'] = {'obligation': 'optional', 'labels': ['relation']}
    result, _ = checked(record(statement, metadata=need), profile)
    assert result['relation'] == 'new' and result['property'] is None
