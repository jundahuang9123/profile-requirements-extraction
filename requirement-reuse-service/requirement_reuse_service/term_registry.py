"""Local vocabulary registry for candidate-term validation and RQ2 profile generation.

A curated, offline registry of DCAT / DCAT-AP / DCTERMS / SKOS / PROV / FOAF
terms plus the Construct-DCAT (cx:) extension vocabulary. It supports:

- term lookup by prefixed name (``dcterms:license``);
- URI expansion / compaction;
- simple domain (target class) compatibility checks;
- source-vocabulary annotation and reuse-priority ranking
  (DCAT/DCAT-AP/DCTERMS first, then PROV/SKOS/FOAF, then cx: extensions).

This intentionally stays a small curated catalogue (research prototype), not a
full ontology index. Domains use bare DCAT resource names: Dataset,
Distribution, Catalog, DataService, Agent, Concept. ``domain=None`` means
unrestricted. Ranges use the visual editor's LinkML names (string, anyURI,
SkosConcept, FoafAgent, ...).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

NAMESPACES: dict[str, str] = {
    'dcat': 'http://www.w3.org/ns/dcat#',
    'dcterms': 'http://purl.org/dc/terms/',
    'skos': 'http://www.w3.org/2004/02/skos/core#',
    'prov': 'http://www.w3.org/ns/prov#',
    'foaf': 'http://xmlns.com/foaf/0.1/',
    'cx': 'https://w3id.org/cx#',
}

VOCABULARY_LABELS: dict[str, str] = {
    'dcat': 'DCAT/DCAT-AP',
    'dcterms': 'DCAT-AP / DCTERMS',
    'skos': 'SKOS',
    'prov': 'PROV-O',
    'foaf': 'FOAF',
    'cx': 'Construct-DCAT extension',
}

# Reuse priority: lower rank = prefer first (reuse-first ordering).
PREFIX_PRIORITY: dict[str, int] = {'dcat': 1, 'dcterms': 1, 'prov': 2, 'skos': 2, 'foaf': 2, 'cx': 3}

EXTENSION_PREFIX = 'cx'

# term -> {type, domain (list[str] | None), range}
TERMS: dict[str, dict[str, Any]] = {
    # --- DCAT classes ---
    'dcat:Catalog': {'type': 'class'},
    'dcat:Dataset': {'type': 'class'},
    'dcat:Distribution': {'type': 'class'},
    'dcat:DataService': {'type': 'class'},
    # --- DCAT properties ---
    'dcat:theme': {'type': 'property', 'domain': ['Dataset', 'Catalog'], 'range': 'SkosConcept'},
    'dcat:themeTaxonomy': {'type': 'property', 'domain': ['Catalog'], 'range': 'anyURI'},
    'dcat:keyword': {'type': 'property', 'domain': ['Dataset'], 'range': 'string'},
    'dcat:distribution': {'type': 'property', 'domain': ['Dataset'], 'range': 'DcatDistribution'},
    'dcat:accessURL': {'type': 'property', 'domain': ['Distribution'], 'range': 'anyURI'},
    'dcat:downloadURL': {'type': 'property', 'domain': ['Distribution'], 'range': 'anyURI'},
    'dcat:mediaType': {'type': 'property', 'domain': ['Distribution'], 'range': 'string'},
    'dcat:byteSize': {'type': 'property', 'domain': ['Distribution'], 'range': 'integer'},
    'dcat:compressFormat': {'type': 'property', 'domain': ['Distribution'], 'range': 'string'},
    'dcat:packageFormat': {'type': 'property', 'domain': ['Distribution'], 'range': 'string'},
    'dcat:contactPoint': {'type': 'property', 'domain': ['Dataset', 'Catalog', 'DataService'], 'range': 'string'},
    'dcat:landingPage': {'type': 'property', 'domain': ['Dataset', 'Catalog'], 'range': 'anyURI'},
    'dcat:servesDataset': {'type': 'property', 'domain': ['DataService'], 'range': 'anyURI'},
    'dcat:endpointURL': {'type': 'property', 'domain': ['DataService'], 'range': 'anyURI'},
    'dcat:endpointDescription': {'type': 'property', 'domain': ['DataService'], 'range': 'anyURI'},
    'dcat:temporalResolution': {'type': 'property', 'domain': ['Dataset'], 'range': 'string'},
    'dcat:spatialResolutionInMeters': {'type': 'property', 'domain': ['Dataset'], 'range': 'string'},
    'dcat:dataset': {'type': 'property', 'domain': ['Catalog'], 'range': 'anyURI'},
    'dcat:service': {'type': 'property', 'domain': ['Catalog'], 'range': 'anyURI'},
    # --- DCTERMS properties ---
    'dcterms:title': {'type': 'property', 'domain': ['Catalog', 'Dataset', 'Distribution', 'DataService'], 'range': 'string'},
    'dcterms:description': {'type': 'property', 'domain': ['Catalog', 'Dataset', 'Distribution', 'DataService'], 'range': 'string'},
    'dcterms:publisher': {'type': 'property', 'domain': ['Catalog', 'Dataset', 'DataService'], 'range': 'FoafAgent'},
    'dcterms:creator': {'type': 'property', 'domain': ['Catalog', 'Dataset'], 'range': 'FoafAgent'},
    'dcterms:license': {'type': 'property', 'domain': ['Dataset', 'Distribution', 'Catalog', 'DataService'], 'range': 'anyURI'},
    'dcterms:accessRights': {'type': 'property', 'domain': ['Dataset', 'Distribution', 'DataService'], 'range': 'string'},
    'dcterms:rights': {'type': 'property', 'domain': ['Distribution', 'Catalog'], 'range': 'string'},
    'dcterms:format': {'type': 'property', 'domain': ['Distribution'], 'range': 'string'},
    'dcterms:conformsTo': {'type': 'property', 'domain': None, 'range': 'anyURI'},
    'dcterms:issued': {'type': 'property', 'domain': None, 'range': 'datetime'},
    'dcterms:modified': {'type': 'property', 'domain': None, 'range': 'datetime'},
    'dcterms:language': {'type': 'property', 'domain': ['Catalog', 'Dataset', 'Distribution'], 'range': 'string'},
    'dcterms:identifier': {'type': 'property', 'domain': None, 'range': 'string'},
    'dcterms:spatial': {'type': 'property', 'domain': ['Dataset', 'Catalog'], 'range': 'string'},
    'dcterms:temporal': {'type': 'property', 'domain': ['Dataset'], 'range': 'string'},
    'dcterms:accrualPeriodicity': {'type': 'property', 'domain': ['Dataset'], 'range': 'string'},
    'dcterms:provenance': {'type': 'property', 'domain': ['Dataset'], 'range': 'string'},
    'dcterms:type': {'type': 'property', 'domain': None, 'range': 'string'},
    # --- SKOS ---
    'skos:Concept': {'type': 'class'},
    'skos:ConceptScheme': {'type': 'class'},
    'skos:prefLabel': {'type': 'property', 'domain': ['Concept'], 'range': 'string'},
    'skos:notation': {'type': 'property', 'domain': ['Concept'], 'range': 'string'},
    'skos:inScheme': {'type': 'property', 'domain': ['Concept'], 'range': 'anyURI'},
    # --- PROV ---
    'prov:wasDerivedFrom': {'type': 'property', 'domain': None, 'range': 'anyURI'},
    'prov:wasGeneratedBy': {'type': 'property', 'domain': None, 'range': 'anyURI'},
    'prov:wasAttributedTo': {'type': 'property', 'domain': None, 'range': 'FoafAgent'},
    # --- FOAF ---
    'foaf:Agent': {'type': 'class'},
    'foaf:name': {'type': 'property', 'domain': ['Agent'], 'range': 'string'},
    'foaf:homepage': {'type': 'property', 'domain': ['Agent'], 'range': 'anyURI'},
    'foaf:mbox': {'type': 'property', 'domain': ['Agent'], 'range': 'anyURI'},
    # --- Construct-DCAT extension (cx:) ---
    'cx:semanticAnchor': {'type': 'property', 'domain': ['Dataset'], 'range': 'SemanticAnchor'},
    'cx:usesOntology': {'type': 'property', 'domain': ['Dataset'], 'range': 'anyURI'},
    'cx:hasLifecyclePhase': {'type': 'property', 'domain': ['Dataset'], 'range': 'LifecyclePhaseEnum'},
    'cx:describesAssetType': {'type': 'property', 'domain': ['Dataset'], 'range': 'ConstructionAsset'},
    'cx:hasAASSubmodel': {'type': 'property', 'domain': ['Dataset'], 'range': 'anyURI'},
    'cx:hasIFCEntity': {'type': 'property', 'domain': ['Dataset'], 'range': 'anyURI'},
    'cx:qualityAnnotation': {'type': 'property', 'domain': ['Dataset'], 'range': 'string'},
    'cx:hasDataSourceSystem': {'type': 'property', 'domain': ['Dataset'], 'range': 'string'},
}

# DCAT resource name -> (prefixed base class, editor LinkML base class, profile class name)
BASE_CLASSES: dict[str, tuple[str, str, str]] = {
    'Dataset': ('dcat:Dataset', 'DcatDataset', 'ConstructionDatasetProfile'),
    'Distribution': ('dcat:Distribution', 'DcatDistribution', 'ConstructionDistributionProfile'),
    'Catalog': ('dcat:Catalog', 'DcatCatalog', 'ConstructionCatalogProfile'),
    'DataService': ('dcat:DataService', 'DcatDataService', 'ConstructionDataServiceProfile'),
}


def split_prefixed(term: str) -> tuple[str, str] | None:
    term = (term or '').strip()
    if term.count(':') != 1 or term.startswith(('http:', 'https:', 'urn:')):
        return None
    prefix, local = term.split(':', 1)
    if not prefix or not local:
        return None
    return prefix, local


def is_known_term(term: str) -> bool:
    return term.strip() in TERMS


def is_known_prefix(term: str) -> bool:
    parts = split_prefixed(term)
    return parts is not None and parts[0] in NAMESPACES


def expand(term: str) -> str | None:
    parts = split_prefixed(term)
    if parts is None:
        return term if term.startswith(('http://', 'https://', 'urn:')) else None
    prefix, local = parts
    namespace = NAMESPACES.get(prefix)
    return f'{namespace}{local}' if namespace else None


def compact(uri: str) -> str:
    for prefix, namespace in NAMESPACES.items():
        if uri.startswith(namespace):
            return f'{prefix}:{uri[len(namespace):]}'
    return uri


def term_info(term: str) -> dict[str, Any] | None:
    return TERMS.get(term.strip())


def vocabulary_label(term: str) -> str:
    parts = split_prefixed(term)
    if parts is None:
        return 'unknown'
    return VOCABULARY_LABELS.get(parts[0], parts[0])


def term_priority(term: str) -> int:
    parts = split_prefixed(term)
    if parts is None:
        return 9
    return PREFIX_PRIORITY.get(parts[0], 9)


def is_extension_term(term: str) -> bool:
    parts = split_prefixed(term)
    return parts is not None and parts[0] == EXTENSION_PREFIX


def normalize_resource_type(target_class: str | None) -> str | None:
    """Normalize 'dcat:Dataset', 'Dataset', 'DcatDataset' -> 'Dataset' (etc.)."""
    if not target_class:
        return None
    value = target_class.strip()
    for resource, (prefixed, linkml_name, _) in BASE_CLASSES.items():
        if value in {resource, prefixed, linkml_name, f'dcat:{resource}'}:
            return resource
    if value in {'Agent', 'foaf:Agent', 'FoafAgent'}:
        return 'Agent'
    if value in {'Concept', 'skos:Concept', 'SkosConcept'}:
        return 'Concept'
    return None


def domain_compatible(term: str, resource_type: str | None) -> bool:
    """True when the term's declared domain admits the resource type.

    Unknown terms, unrestricted domains, and unknown resource types are
    treated as compatible (only obvious mismatches are flagged).
    """
    info = term_info(term)
    if info is None or info.get('type') != 'property':
        return True
    domain = info.get('domain')
    if domain is None:
        return True
    normalized = normalize_resource_type(resource_type)
    if normalized is None:
        return True
    return normalized in domain


def range_for(term: str) -> str:
    info = term_info(term)
    if info is None:
        return 'string'
    return str(info.get('range', 'string'))


def slot_name_for(term: str) -> str:
    parts = split_prefixed(term)
    local = parts[1] if parts else term.rsplit('/', 1)[-1].rsplit('#', 1)[-1]
    return local[:1].lower() + local[1:] if local else 'slot'


def sort_terms_by_priority(terms: list[str]) -> list[str]:
    return sorted(terms, key=lambda term: (term_priority(term), term))


@dataclass
class TermValidationResult:
    """Outcome of validating one CandidateMetadataAction's terms."""

    unknown_terms: list[str] = field(default_factory=list)
    mismatched_terms: list[str] = field(default_factory=list)
    bad_extension_terms: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.unknown_terms or self.mismatched_terms or self.bad_extension_terms)


def validate_action_terms(action: str, candidate_terms: list[str], target_class: str | None) -> TermValidationResult:
    """Validate candidate terms for a metadata action against the registry.

    - reuse/specialize actions: every term should be a known catalogue term;
    - create_extension: terms must carry the cx: extension prefix;
    - obvious domain mismatches (e.g. dcat:mediaType on Dataset) are flagged.
    """
    result = TermValidationResult()
    for term in candidate_terms:
        term = term.strip()
        if not term:
            continue
        if action in {'reuse_existing_term', 'specialize_existing_term', 'add_constraint'}:
            if not is_known_term(term):
                result.unknown_terms.append(term)
                result.issues.append(f"Candidate term '{term}' is not in the local vocabulary catalogue.")
                continue
        if action == 'create_extension' and not is_extension_term(term):
            result.bad_extension_terms.append(term)
            result.issues.append(
                f"Extension proposal '{term}' does not use the '{EXTENSION_PREFIX}:' extension prefix"
                + (' (it is an existing standard term - prefer reuse).' if is_known_term(term) else '.')
            )
            continue
        if is_known_term(term) and not domain_compatible(term, target_class):
            info = term_info(term) or {}
            result.mismatched_terms.append(term)
            result.issues.append(
                f"Term '{term}' targets {target_class or 'unknown class'} but its domain is "
                f"{', '.join(info.get('domain') or [])}."
            )
    return result
