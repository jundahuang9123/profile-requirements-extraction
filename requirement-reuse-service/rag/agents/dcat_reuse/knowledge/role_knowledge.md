# DCAT and DCAT-AP Reuse knowledge pack

## Reuse-first principle

The goal is not to eliminate all construction-specific terms. It is to avoid a
new term when an existing, correctly scoped term already expresses the intended
meaning. Evaluate semantic fit, subject class, range, expected value type,
cardinality, and downstream use. Similar labels are not enough; conversely, a
generic term can be sufficient when the construction distinction belongs in a
controlled concept rather than a new property.

## Resource ownership

Start from the DCAT resource model. Dataset-level content and coverage belong on
`dcat:Dataset` or its supertype. File/media format, byte size, checksum, download
URL, and distribution-specific licence normally belong on `dcat:Distribution`.
Service endpoint details belong on `dcat:DataService`. Record issue and
modification information can describe `dcat:CatalogRecord`. Version relations,
qualified relationships, and dataset series should be considered before
inventing construction-specific structures. [w3c_dcat_3]

## Complementary vocabularies

DCAT intentionally reuses DCMI Metadata Terms. Check `dcterms:type`, `subject`,
`spatial`, `temporal`, `conformsTo`, `relation`, `isPartOf`, `hasPart`,
`provenance`, `source`, `rights`, `license`, `accessRights`, `format`, creator,
publisher, and dates before creating equivalents. [dcmi_metadata_terms]

Use SKOS concepts and concept schemes when the value is a construction
classification, lifecycle vocabulary, discipline list, asset type taxonomy, or
other knowledge-organization system. SKOS supports multilingual preferred,
alternative, and hidden labels; broader/narrower and related links; scheme
membership; and mapping relations across schemes. A classification concept is
not automatically an OWL class. [w3c_skos]

Use PROV-O for detailed lineage and responsibility: entity, activity, agent,
generation, derivation, attribution, association, and qualified relations.
Prefer simple DCTERMS/DCAT provenance links when they answer the task; introduce
PROV detail only when the evidence and use case require it. [w3c_prov_o]

Use DQV for a quality framework, dimension, metric, measurement, annotation,
certificate, or quality policy. Do not create a generic construction quality
score without a defined metric, measured value, applicable resource, method,
and interpretation. [w3c_dqv]

Use DUV for usage guidance, tools, citations, ratings, and user feedback when
consumer experience itself is relevant. Use ODRL when the need is a
machine-readable permission, prohibition, duty, constraint, offer, or agreement;
do not replace a simple licence URI with an elaborate policy unless required.
[w3c_duv] [w3c_odrl]

## Reuse decision procedure

1. Normalize the candidate's intent without choosing a term.
2. Identify the DCAT subject resource and value category: literal, IRI,
   controlled concept, agent, document, policy, service, standard, or dataset.
3. Search DCAT and DCAT-AP, then DCTERMS and the registered complementary
   vocabularies.
4. Check formal definition, domain/range guidance, usage notes, expected
   cardinality, and examples.
5. Test whether a qualified relation, concept scheme, or profile constraint
   represents the need without a new property.
6. If reuse is partial, state precisely what semantic distinction remains.
7. Propose an extension only when the remaining distinction affects a declared
   discovery task and cannot be represented faithfully through existing terms.

## Extension patterns

A profile may restrict values, add a construction controlled vocabulary, define
a subclass, add a subproperty, or define a genuinely new property. Prefer the
least semantically invasive pattern. An asset-type concept generally needs a
stable IRI and concept scheme, not a subclass for every asset. A dataset's
conformance to an IFC release or IDS specification may use `dcterms:conformsTo`
if that relation matches the intended claim. A dataset related to a project or
asset may use a generic or qualified relation if the required role can be
identified. Create a new property only when the relation itself has stable,
task-relevant semantics that existing vocabularies lack.

## Compatibility checks

DCAT-AP-derived profiles must not redefine inherited terms incompatibly. New
constraints should be documented and represented in SHACL. Profile artefacts
should have persistent identifiers, human-readable definitions, machine-readable
serializations, examples, and versioning. [eu_dcat_ap_3]
[eu_dcat_ap_reuse_guidelines]

## Common failure modes

- Mirroring a source-system field merely because it exists.
- Treating keywords as equivalent to controlled semantic anchors.
- Creating a property for what should be a SKOS concept value.
- Reusing a term whose range or subject changes the intended meaning.
- Treating `dcterms:conformsTo` as proof of actual validation.
- Replacing a basic licence with an ODRL policy that nobody can maintain.
- Adding detailed PROV structures when a source/provenance link answers the
  competency question.
- Declaring extension necessity without recording rejected reuse candidates.
