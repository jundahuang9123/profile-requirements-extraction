# Data Consumer and Discovery knowledge pack

## Task-oriented discovery

Dataset discovery is not document search. Users need to determine whether data
can answer a task, whether they can access it, and whether they can interpret and
process it. A study of 79 discovery scenarios derived functional requirements
for repositories from actual user cases. Dataset-search research also shows the
importance of task context, provenance, quality, and interfaces. Requirements
should therefore trace to predefined discovery tasks, not to a generic desire
for "richer metadata." [data_discovery_paradigms] [dataset_search_survey]

## Discovery stages

Evaluate what information supports each stage:

1. **Find:** match terms, concepts, asset/location/lifecycle context, identifiers,
   and related resources.
2. **Filter:** narrow by format, schema, discipline, spatial/temporal coverage,
   access class, licence, publisher, version, quality, or service type.
3. **Compare:** distinguish similar datasets, versions, distributions, and
   access options using consistent values.
4. **Select:** judge task fit, authority, scope, granularity, provenance,
   completeness, freshness, restrictions, and interoperability.
5. **Access:** locate a download, landing page, service endpoint, negotiation
   route, authentication requirements, and policy.
6. **Understand/reuse:** identify schema, vocabulary, documentation, examples,
   provenance, licence/policy, and tools.

Not every field supports every stage. Record the task and decision it enables.

## Structured semantic metadata

Google Dataset Search aggregates, normalizes, and reconciles publisher-supplied
structured metadata. Its experience shows both the value of open semantic
metadata and the reality of missing, inconsistent, or inaccessible records.
[google_dataset_search]

DCAT provides a standard model for federated catalogue search. SKOS concepts,
construction classifications, multilingual labels, and mappings can improve
recall and faceting, but only when scheme identity is retained. Keywords are
useful for recall but do not replace stable concept identifiers.

## Construction-specific selection

Before opening construction data, a consumer may need to know:

- project, asset/facility, or spatial coverage;
- lifecycle phase, discipline, and information purpose;
- representation family and exact schema/release;
- applicable classification, ontology, data dictionary, or submodel template;
- dataset/version/series relations;
- distribution format, packaging, size, checksum, and access method;
- licence, access rights, usage policy, and negotiation endpoint;
- publisher/steward, provenance, dates, status, and quality evidence.

These are candidate categories, not automatic requirements. Keep only those
backed by the corpus and a declared user task.

## Quality and provenance for fitness

Provenance helps users judge authority, context, original purpose, and
transformation history. Quality metadata is meaningful when it names a
dimension, method/metric, measured value or annotation, target resource, and
date. A generic "high quality" label is not a selection signal. [w3c_prov_o]
[w3c_dqv]

DUV can represent usage guidance, tools, citations, ratings, and feedback.
Consumer experience can improve discovery, but feedback must remain distinct
from publisher assertions and formal validation. [w3c_duv]

## Evaluation questions

- Can a user answer the task without downloading every candidate?
- Does the field enable a query, filter, comparison, or interpretation?
- Are values normalized enough to compare across publishers?
- Can users distinguish missing from not applicable?
- Are dataset, distribution, and service results presented separately?
- Do semantic anchors resolve to definitions and retain scheme/version context?
- Does access information match the actual route and policy?
- Does the profile reduce false positives without excluding valid datasets?

## Failure modes

Avoid collecting fields because they are available in a source system. Avoid
interfaces that display URIs without labels or labels without identifiers.
Avoid indexing only free text when controlled concepts exist. Avoid treating
completeness as task fitness. Avoid hiding access restrictions until after
selection. Avoid forcing users to know the exact IFC/AAS/classification term;
support labels, synonyms, broader concepts, and scheme-aware search. Avoid
claiming improved discovery without a baseline, tasks, relevance judgements,
and measurable outcomes.
