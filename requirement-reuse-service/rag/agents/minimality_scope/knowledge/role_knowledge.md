# Minimality and scope-control working knowledge

## Boundary of the role

This role protects a construction-domain DCAT application profile from becoming
an ontology of the entire construction lifecycle. It proposes the smallest set
of dataset-level metadata requirements justified by user tasks and the task
corpus. Background literature suggests tests; it is never requirement evidence.

## Scope model

- Start with stakeholders, use cases, and competency questions, then derive
  requirements and only then select vocabulary terms and constraints
  (`w3c_dcat_ucr`, `lot_methodology`, `ontology_development_101`).
- Treat an application profile as a coordinated package of functional
  requirements, a domain model, constraints, and usage guidance. A new term is
  only one possible response to a requirement (`dcmi_singapore_framework`).
- DCAT profiles may constrain or specialise DCAT while preserving compatibility.
  Existing terms and published profiles are the default reuse surface
  (`w3c_dcat_3`, `eu_dcat_ap_reuse_guidelines`).
- Construction ontologies and schemas are semantic anchors for catalogue
  metadata, not material to reproduce wholesale in a catalog record
  (`bot_ontology_paper`).

## Four-level minimality test

1. **Task necessity:** does the metadata enable an explicit discovery,
   evaluation, access, governance, or interoperability decision?
2. **Corpus support:** does a cited task-corpus passage justify the requirement
   and its obligation strength?
3. **Reuse necessity:** can a registered term, controlled concept, profile, or
   identifier express the intent?
4. **Operational cost:** can typical publishers provide the value and can
   consumers use it reliably?

If any answer is no, weaken, defer, move to guidance, or exclude the proposal.

## Resource and layer discipline

- Catalog and CatalogRecord describe publication and record-management context.
- Dataset describes the conceptual collection; Distribution describes an
  accessible representation; DataService describes a service endpoint.
- IFC entities, AAS submodels, building elements, geometry, property values, and
  document internals normally remain inside the described resource.
- The profile may point to classifications, schemas, model views, or semantic
  identifiers when those anchors materially help discovery or interpretation.
- SHACL constraints are an implementation/validation layer. Do not mistake the
  shape syntax for the underlying functional requirement.

## Extension-admission rule

A construction-specific class or property should be admitted only when all are
true: a repeated and important user task needs it; no suitable reused term
exists; the intended subject and value are clear; publishers can populate it;
consumers can act on it; and compatibility/validation consequences are recorded.
Prefer controlled values or semantic identifiers over parallel custom strings.

## Explicit exclusions to consider

- Full reconstruction of IFC, AAS, GIS, product, or asset graphs in DCAT.
- Workflow orchestration, connector implementation, UI behaviour, or storage
  architecture presented as metadata requirements.
- Requirements justified only by frequency, expert preference, or a background
  source that is absent from the task corpus.
- Mandatory fields that are valuable only to a narrow consumer and cannot be
  supplied consistently.

## Output discipline

Each candidate states one user-visible outcome, one resource level, and one
evidence-backed obligation. Attach an exclusion or design note when a tempting
but out-of-scope interpretation must be prevented.
