"""Deterministic DCAT-AP inheritance checks before evidence verification.

The checker describes an extension claim; it does not validate quotations or infer
requirements from evaluation references. Evidence verification remains a later step.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

BASE_CHECK_POLICY_VERSION = 'rq1-base-check-v1'
PROFILE_DIRECTORY = Path(__file__).resolve().parents[2] / 'config' / 'base_profiles'
CLASS_NAMES = {
    'Dataset': 'dcat:Dataset', 'Distribution': 'dcat:Distribution',
    'DataService': 'dcat:DataService', 'Catalog': 'dcat:Catalog',
    'CatalogRecord': 'dcat:CatalogRecord', 'Agent': 'foaf:Agent',
    'Concept': 'skos:Concept',
}
OBLIGATION_RANK = {'mandatory': 3, 'recommended': 2, 'optional': 1}
LABEL_SYNONYMS = {
    'dcat:endpointURL': ['endpoint url', 'endpoint address', 'endpoint uri', 'root location'],
    'dcat:endpointDescription': ['endpoint description', 'api description', 'description of the api or interface'],
    'dcat:servesDataset': ['serves dataset', 'served datasets', 'datasets it serves'],
    'dcat:accessService': ['access service'], 'dcat:accessURL': ['access url'],
    'dcat:downloadURL': ['download url'], 'dcat:mediaType': ['media type', 'mime type'],
    'adms:versionNotes': ['version notes'],
    'dct:spatial': ['spatial coverage', 'geographic coverage', 'geographic extent', 'geographical area'],
    'dct:temporal': ['temporal coverage', 'time period'],
    'dcat:contactPoint': ['contact', 'contact point', 'point of contact'],
    'dcat:keyword': ['keyword', 'tag'], 'dcat:theme': ['theme'],
    'dcat:themeTaxonomy': ['theme taxonomy'], 'dct:license': ['licence', 'license'],
    'dct:accessRights': ['access rights', 'access restrictions'],
    'dct:conformsTo': ['conforms to', 'conformance'], 'foaf:page': ['documentation'],
    'dct:accrualPeriodicity': ['update frequency', 'accrual periodicity'],
    'dct:issued': ['release date', 'publication date', 'issued'],
    'dct:modified': ['modification date', 'last modified', 'last updated'],
    'dcat:byteSize': ['byte size', 'file size'], 'spdx:checksum': ['checksum'],
    'dcatap:availability': ['availability'], 'adms:status': ['status'],
    'dct:provenance': ['provenance', 'lineage'], 'dct:identifier': ['identifier'],
    'dct:language': ['language'], 'owl:versionInfo': ['version'],
    'dcat:distribution': ['distribution'], 'dct:format': ['format', 'file format'],
    'dct:title': ['title'], 'dct:description': ['description'], 'foaf:name': ['name'],
}
CURIE = re.compile(r'\b([A-Za-z][\w-]*):([A-Za-z_](?:[\w.-]*[\w-])?)')
# Acronyms are deliberately not included in a case-insensitive pattern: ITS must
# never match the possessive pronoun "its".
DOMAIN_ACRONYMS = ['ITS', 'NAP', 'CRS', 'SIRI', 'NeTEx', 'DATEX', 'GTFS', 'TN-ITS', 'EPSG']
DOMAIN_WORDS = ['transport', 'traffic', 'road', 'parking', 'transit', 'mobility',
                'national access point', 'real-time', 'georeferencing',
                'location referencing', 'coordinate reference system', 'WGS84']


def _dict(value: Any) -> dict:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, 'model_dump'):
        return value.model_dump(mode='json')
    raise TypeError('A mapping or workflow contract is required.')


def load_profile(profile_id: str) -> tuple[dict, str]:
    """Load a checked-in registry and fingerprint its exact saved bytes."""
    if not re.fullmatch(r'dcat-ap-\d+\.\d+\.\d+', profile_id):
        raise ValueError('Invalid base profile id.')
    raw = (PROFILE_DIRECTORY / (profile_id + '.json')).read_bytes()
    profile = json.loads(raw)
    if profile.get('id') != profile_id or not isinstance(profile.get('classes'), dict):
        raise ValueError('Base profile registry has an invalid id or class table.')
    return profile, hashlib.sha256(raw).hexdigest()


def _canonical_curie(value: str) -> str:
    if ':' not in value:
        return value
    prefix, local = value.split(':', 1)
    prefix = prefix.lower()
    return ('dct' if prefix == 'dcterms' else prefix) + ':' + local


def _class(resource: str) -> str | None:
    for label, class_id in CLASS_NAMES.items():
        if resource.casefold() in {label.casefold(), class_id.casefold()}:
            return class_id
    return None


def _phrase_pattern(phrase: str) -> re.Pattern:
    parts = re.split(r'\s+', phrase.strip())
    return re.compile(r'(?<!\w)' + r'\s+'.join(re.escape(p) for p in parts) + r'(?!\w)', re.I)


def constraint_signals(record: Any) -> list[str]:
    """Return inspectable text/scope cues; declared v3 kinds are not proof."""
    row = _dict(record)
    intent = _dict(row.get('normalized_intent', row.get('intent', {})))
    statement = row.get('raw_statement', row.get('statement', ''))
    signals: list[str] = []
    patterns = [
        ('controlled_vocabulary', r'\b(?:controlled vocabular(?:y|ies)|code lists?|authority (?:lists?|tables?)|taxonomy|thesaurus|EU Vocabularies|NUTS|GeoNames|ISO\s*639(?:-\d+)?|IANA)\b'),
        ('controlled_vocabulary', r'\bfrom\s+(?:the\s+)?[^.;\n]{0,100}\b(?:list|vocabulary|scheme)\b'),
        ('controlled_vocabulary', r'\bfrom\b[^.;\n]{0,100}\bRegulation\s+\d{1,4}/\d{2,4}\b'),
        ('cardinality', r'\b(?:exactly one|at most (?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|N)|one per language|for each)\b'),
        ('condition', r'\b(?:if|when|where|in case|unless|provided that)\b'),
    ]
    for kind, pattern in patterns:
        for match in re.finditer(pattern, statement, re.I):
            signals.append(kind + ': ' + match.group(0))
    for phrase in DOMAIN_WORDS:
        for match in _phrase_pattern(phrase).finditer(statement):
            signals.append('domain_term: ' + match.group(0))
    for acronym in DOMAIN_ACRONYMS:
        for match in re.finditer(r'(?<!\w)' + re.escape(acronym) + r'(?!\w)', statement):
            signals.append('domain_acronym: ' + match.group(0))
    scope = str(row.get('scope', '')).strip()
    resource = str(intent.get('resource_type', 'Unknown'))
    generic = {'', 'unspecified', 'unknown', 'none', 'n/a', resource.casefold(),
               resource.casefold() + 's'}
    class_id = _class(resource)
    if class_id:
        generic.add(class_id.casefold())
    if scope.casefold() not in generic:
        signals.append('domain_scope: ' + scope)
    return sorted(set(signals))


def _property(row: dict, class_id: str, properties: dict) -> tuple[str | None, str, list[str]]:
    statement = row.get('raw_statement', row.get('statement', ''))
    intent = _dict(row.get('normalized_intent', row.get('intent', {})))
    notes = []
    explicit = row.get('base_property')
    if explicit:
        parts = str(explicit).split('/', 1)
        property_id = _canonical_curie(parts[-1])
        if CURIE.fullmatch(property_id):
            if len(parts) == 2 and _canonical_curie(parts[0]) != class_id:
                notes.append('Declared base property names a different class; checked against the candidate class.')
            without_declaration = dict(row, base_property=None)
            text_property, _, _ = _property(without_declaration, class_id, properties)
            if text_property != property_id:
                notes.append('Declared base property is not corroborated by the statement or metadata need; review its mapping.')
            return property_id, 'base_property', notes
        notes.append('Declared base property is not a valid prefixed property name; used text matching.')
    terms = [_canonical_curie(match.group(0)) for match in CURIE.finditer(statement)]
    for term in terms:
        if term in properties:
            return term, 'statement_curie', notes
    ranges = {str(term) for definition in properties.values()
              for term in (definition.get('range') if isinstance(definition.get('range'), list)
                           else [definition.get('range')])}
    unknown = next((term for term in terms if term not in CLASS_NAMES.values() and term not in ranges), None)
    if unknown:
        return unknown, 'statement_curie', notes
    labels = []
    for property_id, definition in properties.items():
        synonyms = list(definition.get('labels', [])) + LABEL_SYNONYMS.get(property_id, [])
        if property_id == 'adms:status' and class_id not in {'dcat:Distribution', 'dcat:CatalogRecord'}:
            synonyms = [s for s in synonyms if s.casefold() != 'status']
        if property_id == 'dcat:distribution' and class_id != 'dcat:Dataset':
            synonyms = [s for s in synonyms if s.casefold() != 'distribution']
        if property_id == 'foaf:name' and class_id != 'foaf:Agent':
            synonyms = [s for s in synonyms if s.casefold() != 'name']
        for label in synonyms:
            if label:
                labels.append((len(label), property_id, label))
    # Specific phrases precede generic ones; ties have a stable property order.
    labels.sort(key=lambda item: (-item[0], item[1], item[2]))
    for via, text in [('metadata_need_lexicon', intent.get('metadata_need', '')), ('statement_lexicon', statement)]:
        for _, property_id, label in labels:
            if _phrase_pattern(label).search(text):
                return property_id, via, notes
    return None, 'no_match', notes


def _source_basename(name: str) -> str:
    return str(name).replace('\\', '/').rsplit('/', 1)[-1].casefold()


def _outside_base_support(row: dict, evidence_by_id: Mapping[str, Any],
                          base_source_version_ids: Iterable[str],
                          source_name_by_version: Mapping[str, str],
                          base_source_names: Iterable[str]) -> bool:
    base_ids = set(base_source_version_ids)
    base_names = {_source_basename(name) for name in base_source_names}
    for value in row.get('evidence_links', []):
        link = _dict(value)
        if link.get('relation', 'supports') != 'supports':
            continue
        unit = evidence_by_id.get(link.get('evidence_id'))
        if unit is None:
            continue
        source_id = _dict(unit).get('source_version_id')
        if not source_id or source_id in base_ids:
            continue
        source_name = source_name_by_version.get(source_id)
        if source_name and _source_basename(source_name) in base_names:
            continue
        # A configured ID classification knows every other source is nonbase.
        # Name-only classification needs a known name; absence is not proof.
        if base_ids or (base_names and source_name):
            return True
    return False


def _provisional_constraint(row: dict, check: dict, findings: list[dict]) -> None:
    if (check['relation'] == 'inherited' and not check['constraint_signals']
            and row.get('extension_kind') == 'value_constraint'):
        check['requires_review'] = True
        check.setdefault('notes', []).append('Declared extension has no recognized added constraint; inheritance is provisional pending review.')
        findings.append({'criterion': 'unconfirmed_extension_constraint', 'severity': 'review',
                         'message': 'The model declares a value constraint but the deterministic checker found no added-constraint cue; retain it for review.'})


def check_record(record: Any, profile: Mapping[str, Any], *,
                 evidence_by_id: Mapping[str, Any] | None = None,
                 base_source_version_ids: Iterable[str] = (),
                 source_name_by_version: Mapping[str, str] | None = None,
                 base_source_names: Iterable[str] = ()) -> tuple[dict, list[dict]]:
    """Describe inherited versus added content and return required findings.

    Source IDs should be the corpus's configured background/base specification
    sources. For saved extractions, exact basenames from the same case setting
    may instead classify source names. Unknown evidence is never outside-base
    support. Findings are plain dicts accepted by the workflow Finding contract.
    """
    row = _dict(record)
    profile = _dict(profile)
    intent = _dict(row.get('normalized_intent', row.get('intent', {})))
    class_id = _class(str(intent.get('resource_type', 'Unknown')))
    obligation = str(intent.get('obligation_hint', 'unknown')).lower()
    signals = constraint_signals(row)
    check = {'base_profile': profile['id'], 'class': class_id, 'property': None,
             'base_obligation': None, 'candidate_obligation': obligation,
             'relation': 'unresolved_class', 'resolved_via': 'unresolved_class',
             'constraint_signals': signals}
    findings: list[dict] = []
    if class_id is None or class_id not in profile.get('classes', {}):
        findings.append({'criterion': 'unresolved_base_class', 'severity': 'review',
                         'message': 'The candidate class could not be resolved in the selected base profile.'})
        return check, findings
    properties = profile['classes'][class_id]
    property_id, via, notes = _property(row, class_id, properties)
    check.update(property=property_id, resolved_via=via, relation='new')
    if notes:
        check['notes'] = notes
    if any('not corroborated' in note or 'different class' in note for note in notes):
        check['requires_review'] = True
        findings.append({'criterion': 'unconfirmed_base_property', 'severity': 'review',
                         'message': 'The declared base-property mapping needs review against the candidate statement and class.'})
    if property_id not in properties:
        return check, findings
    base_obligation = properties[property_id]['obligation']
    check['base_obligation'] = base_obligation
    candidate_rank = OBLIGATION_RANK.get(obligation)
    base_rank = OBLIGATION_RANK.get(base_obligation)
    statement = row.get('raw_statement', row.get('statement', ''))
    ability = bool(re.search(r'\b(?:consumer|system)\b[^.;\n]{0,120}\b(?:must|shall|should|may)\s+be\s+able\s+to\s+(?:process|retrieve|interpret)\b', statement, re.I))
    if ability and not signals:
        check['relation'] = 'inherited'
        _provisional_constraint(row, check, findings)
        return check, findings
    if candidate_rank is not None and base_rank is not None and candidate_rank > base_rank:
        base_ids, base_names = set(base_source_version_ids), list(base_source_names)
        if _outside_base_support(row, evidence_by_id or {}, base_ids,
                                 source_name_by_version or {}, base_names):
            check['relation'] = 'tightened'
        else:
            check['relation'] = 'inherited'
            check.setdefault('notes', []).append('stricter label not supported outside the base specification')
            if not base_ids and not base_names:
                check['requires_review'] = True
                check.setdefault('notes', []).append('Base specification sources were not classified; inheritance is provisional pending review.')
                findings.append({'criterion': 'unresolved_base_source_classification', 'severity': 'review',
                                 'message': 'The selected base has no configured base-source classification; retain this stronger obligation for review.'})
        _provisional_constraint(row, check, findings)
        return check, findings
    if candidate_rank is not None and base_rank is not None and candidate_rank < base_rank:
        check['relation'] = 'loosened'
        findings.append({'criterion': 'conflicts_with_base', 'severity': 'blocking',
                         'message': f'{property_id} is {base_obligation} in {profile["id"]}; an extension cannot relax it to {obligation}.'})
        return check, findings
    check['relation'] = 'constrained' if signals else 'inherited'
    _provisional_constraint(row, check, findings)
    return check, findings
