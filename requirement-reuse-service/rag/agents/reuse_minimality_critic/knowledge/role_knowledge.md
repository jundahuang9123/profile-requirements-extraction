# Reuse, minimality, and validation critic knowledge

## Boundary of the role

This critic looks for avoidable extensions, redundant requirements, invalid
resource placement, publisher burden, and validation designs that exceed the
functional need. It reports findings only. It cannot add vocabulary terms or
convert background literature into evidence.

## Reuse audit order

Before accepting a custom term, check:

1. DCAT/DCAT-AP for catalogue, dataset, distribution, data-service, and record
   semantics (`w3c_dcat_3`, `eu_dcat_ap_3`).
2. DCMI terms for identification, description, relation, provenance, rights,
   spatial, temporal, format, and conformance semantics (`dcmi_metadata_terms`).
3. SKOS for concepts, concept schemes, labels, mappings, and classification
   references (`w3c_skos`).
4. PROV-O for lineage and responsibility (`w3c_prov_o`).
5. DQV for quality dimensions, metrics, measurements, annotations, and policies
   (`w3c_dqv`).
6. ODRL for machine-readable permission, prohibition, duty, constraint, party,
   and asset policy structures (`w3c_odrl`).
7. Domain identifiers and controlled schemes for IFC, AAS, bSDD, geography, and
   construction classifications rather than copied labels.

Similarity is not enough: domain, range, value type, cardinality, and intended
meaning must fit. Conversely, small naming differences do not justify a new term.

## Extension-necessity test

Flag a custom class/property unless the proposal identifies a stable unmet
concept, recurring user task, precise subject and value, implementable publisher
path, consumer behaviour, compatibility story, and validation approach. Profile
reuse guidance favours constraints and usage rules over vocabulary forks
(`eu_dcat_ap_reuse_guidelines`, `dcmi_singapore_framework`).

## Minimality checks

- Duplicate intent expressed through several properties or resource levels.
- Mandatory metadata whose cost exceeds its discovery/reuse benefit.
- Catalogue-level copies of internal BIM, AAS, GIS, product, or asset content.
- Multiple custom booleans where a controlled concept or conformance reference
  would remain extensible.
- Requirements that encode a particular connector, database, UI, or workflow.
- Cardinality stronger than corpus evidence or realistic publisher availability.

## Validation audit

SHACL can express structural and value constraints and return validation results,
but a shape does not create the policy it tests (`w3c_shacl`). For every proposed
constraint, review target class, path, cardinality, value type, node kind,
controlled scheme, severity, message, and treatment of missing/unknown values.
Flag closed-world assumptions and hard failures that would reject useful legacy
catalogue records without evidence.

## Construction-specific review

Prefer references to schemas, model views, classifications, IDS specifications,
semantic IDs, or geospatial systems when they enable discovery. Flag attempts to
duplicate IFC class hierarchies, AAS submodel content, building topology, or full
classification systems inside the DCAT extension.

## Output discipline

Each finding names the candidate, the likely reused alternative or minimality
problem, the semantic/validation consequence, and the check needed. A suggested
term is an audit lead, not an automatic replacement.
