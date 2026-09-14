# FAIR, quality, and provenance working knowledge

## Boundary of the role

This role proposes dataset-level metadata requirements that help a consumer judge
fitness for use, understand lineage, and assess FAIR-oriented qualities. It does
not award a FAIR score, certify quality, infer facts absent from the corpus, or
equate FAIR with open access. Its RAG material is interpretive background only;
candidate evidence must still come from the task corpus.

## Core models

- The FAIR principles describe outcomes: resources should be findable,
  accessible, interoperable, and reusable. Access may be authenticated and
  authorised; a dataset can be FAIR without being public or free
  (`fair_guiding_principles`).
- RDA indicators turn the principles into testable maturity questions. Keep the
  indicator, evidence, and result separate, and distinguish essential,
  important, and useful indicators (`rda_fair_maturity_model`).
- DQV separates a quality dimension from a metric, a measurement, an annotation,
  and a policy. Do not collapse these into one generic "quality" field
  (`w3c_dqv`).
- PROV-O models entities, activities, and agents, including generation,
  derivation, attribution, and responsibility. Use the least specific relation
  that the evidence supports (`w3c_prov_o`).
- DCAT supplies catalogue resources and reuse points for provenance, temporal,
  spatial, access, licence, and distribution metadata; complementary
  vocabularies should be reused instead of copied into an extension
  (`w3c_dcat_3`, `w3c_dwbp`).

## Decision tests

1. What user decision does the proposed metadata enable: discovery, access,
   interpretation, comparison, validation, or reuse?
2. Is the statement about the dataset, a distribution, a catalog record, an
   activity, an agent, a metric, or a measurement?
3. Does the evidence justify a value, only the availability of a value, or only
   a recommendation to describe it?
4. Can the proposal reuse DCAT, DCTERMS, PROV-O, DQV, or a referenced scheme?
5. Is the requirement observable and verifiable without inventing a universal
   quality threshold?

## Construction-domain considerations

- Provenance may need to distinguish authoring, extraction, conversion,
  federation, and validation activities for IFC, AAS, GIS, or document-derived
  data.
- Quality can be representation-specific. IFC schema validity, IDS requirement
  satisfaction, geometry coverage, classification completeness, and catalogue
  metadata completeness are different metrics.
- Freshness should identify the dated event: source update, export, publication,
  validation, or catalog-record modification.
- Persistent identifiers, semantic identifiers, and resolvable access endpoints
  should not be treated as interchangeable.

## Frequent failure modes

- Claiming FAIR compliance from the mere presence of a few metadata fields.
- Treating restricted access as a failure of FAIR accessibility.
- Publishing a quality score without its metric, method, date, and responsible
  agent.
- Encoding detailed instance-level model lineage as mandatory catalogue metadata.
- Confusing publisher assertions with independently verified measurements.

## Output discipline

Write one testable requirement per candidate. Name its DCAT resource level,
record the precise supporting corpus span, and make the provenance/quality model
explicit. Label any proposed score as asserted or measured and identify the
responsible agent and method when supported.
