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

BASE_CHECK_POLICY_VERSION = 'rq1-base-check-v2'
PROFILE_DIRECTORY = Path(__file__).resolve().parents[2] / 'config' / 'base_profiles'
CLASS_NAMES = {
    'Dataset': 'dcat:Dataset', 'Distribution': 'dcat:Distribution',
    'DataService': 'dcat:DataService', 'Catalog': 'dcat:Catalog',
    'CatalogRecord': 'dcat:CatalogRecord', 'Agent': 'foaf:Agent',
    'Concept': 'skos:Concept',
    'Relationship': 'dcat:Relationship', 'PeriodOfTime': 'dct:PeriodOfTime',
    'Location': 'dct:Location',
}
OBLIGATION_RANK = {'mandatory': 3, 'recommended': 2, 'optional': 1}
LABEL_SYNONYMS = {
    'dcat:endpointURL': ['endpoint url', 'endpoint address', 'endpoint uri', 'root location'],
    'dcat:endpointDescription': ['endpoint description', 'api description', 'description of the api or interface'],
    'dcat:servesDataset': ['serves dataset', 'served datasets', 'datasets it serves'],
    'dcat:accessService': ['access service'], 'dcat:accessURL': ['access url'],
    'dcat:downloadURL': ['download url'], 'dcat:mediaType': ['media type', 'mime type'],
    'adms:versionNotes': ['version notes'],
    'dct:spatial': ['spatial coverage', 'geographic coverage', 'geographic extent', 'geographical area',
                    'bounding box', 'geographic location'],
    'dct:temporal': ['temporal coverage', 'temporal extent', 'time period', 'period of time',
                     'validity interval', 'validity intervals', 'start and end dates'],
    'dcat:hadRole': ['hadRole', 'had role'],
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


def _condition_matches(statement: str):
    """Recognize applicability clauses without mistaking a location/time description for one."""
    for match in re.finditer(r'\b(?:if|when|where|in case|unless|provided that)\b', statement, re.I):
        word = match.group(0).casefold()
        tail = statement[match.end():].lstrip()
        if word not in {'when', 'where'}:
            yield match
        elif re.match(r'(?:applicable|available|possible|necessary|required|appropriate|relevant)\b', tail, re.I):
            yield match
        elif word == 'where':
            # "where clients can access" describes the endpoint. The finite
            # applicability patterns below describe circumstances of a rule.
            if re.match(r'(?:(?:a|an|the)\s+)?(?:access|data|datasets?|distributions?|services?|metadata)\b'
                        r'[^.;,\n]{0,65}\b(?:is|are|has|have)\s+(?:not\s+)?'
                        r'(?:restricted|available|provided|published|required|applicable|missing)\b', tail, re.I):
                yield match
        else:
            prefix = statement[:match.start()]
            if not re.search(r'\b(?:date|time|moment|timestamp|instant|indicates?|records?|describes?|captures?)'
                             r'\s*(?:at\s+)?$', prefix, re.I):
                yield match


def _inherited_vocabulary(signal: str, definition: Mapping[str, Any]) -> bool:
    vocabulary = definition.get('vocabulary')
    if not vocabulary:
        return False
    # Generic use of a scheme adds nothing to a property already pinned to one.
    # Explicit alternatives/subsets remain inspectable constraint claims.
    text = signal.split(': ', 1)[-1]
    if re.search(r'\b(?:Regulation|subset|narrower|restricted|specific|only|ISO\s*639|IANA|NUTS)\b', text, re.I):
        return False
    if re.search(r'\bGeoNames\b', text, re.I):
        return any('geonames' in str(v).casefold() for v in
                   (vocabulary if isinstance(vocabulary, list) else [vocabulary]))
    return True


def constraint_signals(record: Any, base_definition: Mapping[str, Any] | None = None) -> list[str]:
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
        ('value_restriction', r'\b(?:rather than|instead of)\b'),
    ]
    for kind, pattern in patterns:
        for match in re.finditer(pattern, statement, re.I):
            signals.append(kind + ': ' + match.group(0))
    signals.extend('condition: ' + match.group(0) for match in _condition_matches(statement))
    if base_definition:
        signals = [s for s in signals if not (s.startswith('controlled_vocabulary:')
                   and _inherited_vocabulary(s, base_definition))]
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


def _property(row: dict, class_id: str, properties: dict, *,
              registry_properties: Mapping[str, Any] | None = None,
              registry_classes: Iterable[str] = ()) -> tuple[str | None, str, list[str]]:
    statement = row.get('raw_statement', row.get('statement', ''))
    intent = _dict(row.get('normalized_intent', row.get('intent', {})))
    notes = []
    explicit = row.get('base_property')
    if explicit:
        parts = str(explicit).split('/', 1)
        property_id = _canonical_curie(parts[-1])
        if CURIE.fullmatch(property_id):
            without_declaration = dict(row, base_property=None)
            text_property, _, _ = _property(without_declaration, class_id,
                dict(registry_properties or properties), registry_classes=registry_classes)
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
    unknown = next((term for term in terms if term not in set(CLASS_NAMES.values()) | set(registry_classes)
                    and term not in ranges and not term.startswith(('xsd:', 'rdfs:'))), None)
    if unknown:
        return unknown, 'statement_curie', notes
    if ('prov:qualifiedAttribution' in properties and re.search(
            r'\brole\s+entity\b[^.;\n]{0,100}\bowner\b',
            str(intent.get('metadata_need', '')) + ' ' + statement, re.I)):
        return 'prov:qualifiedAttribution', 'role_entity_lexicon', notes
    if str(intent.get('metadata_need', '')).strip().casefold() == 'relationship' and 'dct:relation' in properties:
        return 'dct:relation', 'relationship_lexicon', notes
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


def _compound_signals(row: dict, check: dict, properties: Mapping[str, Any],
                      registry_classes: Iterable[str]) -> tuple[list[str], list[str]]:
    statement = row.get('raw_statement', row.get('statement', ''))
    ranges = {str(term) for definition in properties.values()
              for term in (definition.get('range') if isinstance(definition.get('range'), list)
                           else [definition.get('range')])}
    terms = {_canonical_curie(match.group(0)) for match in CURIE.finditer(statement)}
    terms -= set(CLASS_NAMES.values()) | set(registry_classes) | ranges
    terms = {term for term in terms if not term.startswith(('xsd:', 'rdfs:'))}
    signals = ['multiple_property_curies'] if len(terms) > 1 else []
    for match in re.finditer(r'\b(?:and|as well as)\b|;', statement, re.I):
        tail = statement[match.end():].strip().rstrip('.')
        if check['property'] == 'dct:temporal' and re.match(r'^(?:end(?:ing)?|begin(?:ning)?|start)\b', tail, re.I):
            continue
        other, _, _ = _property({'statement': tail, 'intent': {}}, check['class'], dict(properties),
                                registry_classes=registry_classes)
        if other and other != check['property']:
            signals.append('different_property: ' + other)
        elif not other:
            # Keep an independently named need, not a bare conjunction joining
            # components of one need ("start and end dates", "title and its text").
            first = re.split(r'[;,]|\b(?:is|are|must|shall|should|may)\b', tail, maxsplit=1, flags=re.I)[0].strip()
            component = re.match(r'^(?:end(?:ing)?|begin(?:ning)?|start)\b', first, re.I)
            qualifier = re.match(r'^(?:its|their|the same|to|be|can|using|with|without|that|which|in|on|for)\b', first, re.I)
            words = re.findall(r'[A-Za-z][\w-]*', first)
            if (2 <= len(words) <= 6 and not component and not qualifier
                    and not re.search(r'\b(?:and|as well as)\b', first, re.I)):
                before, _, _ = _property({'statement': statement[:match.start()], 'intent': {}},
                                         check['class'], dict(properties), registry_classes=registry_classes)
                if before == check['property']:
                    signals.append('different_need: ' + first)
    return sorted(set(signals)), sorted(terms)


def _provisional_constraint(row: dict, check: dict, findings: list[dict], properties: Mapping[str, Any],
                            registry_classes: Iterable[str] = ()) -> None:
    if (check['relation'] == 'inherited' and not check['constraint_signals']
            and row.get('extension_kind') == 'value_constraint'):
        check['requires_review'] = True
        check.setdefault('notes', []).append('Declared extension has no recognized added constraint; inheritance is provisional pending review.')
        findings.append({'criterion': 'unconfirmed_extension_constraint', 'severity': 'review',
                         'message': 'The model declares a value constraint but the deterministic checker found no added-constraint cue; retain it for review.'})
    if check['relation'] == 'inherited':
        statement = row.get('raw_statement', row.get('statement', ''))
        compound, property_terms = _compound_signals(row, check, properties, registry_classes)
        if compound:
            check['requires_review'] = True
            if len(property_terms) > 1:
                check['statement_property_candidates'] = sorted(property_terms)
            check['compound_signals'] = compound
            check.setdefault('notes', []).append('The statement may cover multiple clauses; a single inherited match cannot exclude the whole candidate.')
            findings.append({'criterion': 'compound_base_check', 'severity': 'review',
                             'message': 'Inspect or split this potentially compound statement before classifying every clause as inherited.'})
        negations = list(re.finditer(r'\b(?:not|never|without|avoid)\b', statement, re.I))
        if negations:
            check['requires_review'] = True
            check['polarity_signals'] = sorted({match.group(0) for match in negations})
            check.setdefault('notes', []).append('Negated wording needs review before treating the candidate as a restatement of the base.')
            findings.append({'criterion': 'base_polarity_review', 'severity': 'review',
                             'message': 'Review the candidate polarity against the base; a matching property alone does not establish inheritance.'})


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
    classes = profile['classes']
    properties = classes[class_id]
    registry_properties = {p: definition for cls in sorted(classes, reverse=True)
                           for p, definition in classes[cls].items()}
    # Do not mistake a resource subject ("a dataset needs ownership metadata")
    # for the Catalog's dcat:dataset property. Cross-class text fallback uses
    # property names/specific synonyms, not whole registry table headings.
    cross_class_lexicon = {p: dict(definition, labels=[label for label in definition.get('labels', [])
        if label.casefold() == p.split(':')[-1].casefold()])
        for p, definition in registry_properties.items()
        if p not in {'dcat:dataset', 'dcat:catalog', 'dcat:service', 'dcat:record', 'dcat:distribution'}}
    property_id, via, notes = _property(row, class_id, properties,
        registry_properties=cross_class_lexicon, registry_classes=classes)
    if property_id is None:
        property_id, via, notes = _property(row, class_id, cross_class_lexicon, registry_classes=classes)
    check.update(property=property_id, resolved_via=via, relation='new')
    need_class = _class(str(intent.get('metadata_need', '')).strip())
    class_hint = need_class if need_class == 'dcat:Relationship' and property_id in classes.get(need_class, {}) else None
    if (property_id not in properties or class_hint) and property_id in registry_properties:
        candidates = sorted(cls for cls, props in classes.items() if property_id in props)
        explicit_class = _canonical_curie(str(row.get('base_property') or '').split('/', 1)[0])
        statement = row.get('raw_statement', row.get('statement', ''))
        mentioned = [cls for cls in candidates if _phrase_pattern(cls).search(statement)
                     or _phrase_pattern(cls.split(':')[-1]).search(statement)]
        resolved = class_hint or (explicit_class if explicit_class in candidates else (
            mentioned[0] if len(mentioned) == 1 else 'dcat:Dataset' if 'dcat:Dataset' in candidates else candidates[0])
        )
        check.update({'candidate_class': class_id, 'class': resolved, 'base_property_classes': candidates})
        notes.append('Property exists in the base under another class; treated as class label noise.')
        if not class_hint and explicit_class not in candidates and len(mentioned) != 1:
            # Matching a known property prevents a false "new" claim. A class
            # choice affecting its obligations/constraints still needs review.
            definitions = {json.dumps({k: classes[cls][property_id].get(k)
                           for k in ('obligation', 'max', 'range', 'vocabulary')}, sort_keys=True) for cls in candidates}
            if len(definitions) > 1:
                check['requires_review'] = True
                findings.append({'criterion': 'ambiguous_base_property_class', 'severity': 'review',
                    'message': 'The property occurs under multiple base classes with different definitions; review the candidate class.'})
        class_id, properties = resolved, classes[resolved]
    if notes:
        check['notes'] = notes
    if any('not corroborated' in note for note in notes):
        check['requires_review'] = True
        findings.append({'criterion': 'unconfirmed_base_property', 'severity': 'review',
                         'message': 'The declared base-property mapping needs review against the candidate statement and class.'})
    if property_id not in properties:
        return check, findings
    compound_properties = {**cross_class_lexicon, **properties}
    base_obligation = properties[property_id]['obligation']
    signals = constraint_signals(row, properties[property_id])
    check['constraint_signals'] = signals
    check['base_obligation'] = base_obligation
    candidate_rank = OBLIGATION_RANK.get(obligation)
    base_rank = OBLIGATION_RANK.get(base_obligation)
    statement = row.get('raw_statement', row.get('statement', ''))
    ability = bool(re.search(r'\b(?:consumer|system)\b[^.;\n]{0,120}\b(?:must|shall|should|may)\s+be\s+able\s+to\s+(?:process|retrieve|interpret)\b', statement, re.I))
    if ability and not signals:
        check['relation'] = 'inherited'
        _provisional_constraint(row, check, findings, compound_properties, classes)
        return check, findings
    if candidate_rank is not None and base_rank is not None and candidate_rank > base_rank:
        base_ids, base_names = set(base_source_version_ids), list(base_source_names)
        if _outside_base_support(row, evidence_by_id or {}, base_ids,
                                 source_name_by_version or {}, base_names):
            check['relation'] = 'tightened'
        else:
            check['relation'] = 'constrained' if signals else 'inherited'
            check.setdefault('notes', []).append('stricter label not supported outside the base specification')
            if not base_ids and not base_names:
                check['requires_review'] = True
                check.setdefault('notes', []).append('Base specification sources were not classified; inheritance is provisional pending review.')
                findings.append({'criterion': 'unresolved_base_source_classification', 'severity': 'review',
                                 'message': 'The selected base has no configured base-source classification; retain this stronger obligation for review.'})
        _provisional_constraint(row, check, findings, compound_properties, classes)
        return check, findings
    if candidate_rank is not None and base_rank is not None and candidate_rank < base_rank:
        if signals:
            check['relation'] = 'loosened'
            findings.append({'criterion': 'conflicts_with_base', 'severity': 'blocking',
                             'message': f'{property_id} is {base_obligation} in {profile["id"]}; an extension cannot relax it to {obligation}.'})
        else:
            check['relation'] = 'inherited'
            check.setdefault('notes', []).append('weaker label than base')
            _provisional_constraint(row, check, findings, compound_properties, classes)
        return check, findings
    check['relation'] = 'constrained' if signals else 'inherited'
    _provisional_constraint(row, check, findings, compound_properties, classes)
    return check, findings
