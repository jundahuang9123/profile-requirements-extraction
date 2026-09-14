# Standards and Normative Conformance knowledge pack

## Role boundary

This role interprets declared standards and source-corpus wording. It does not
decide what the construction sector ought to want. A requirement is a candidate
only when a verified corpus passage supports the need and obligation. Standards
knowledge helps interpret that passage and place it correctly; it is not a
substitute for evidence.

## DCAT conformance model

DCAT is an RDF vocabulary for catalogues, catalogued resources, datasets,
dataset series, distributions, and data services. A `dcat:Dataset` is the
conceptual collection; a `dcat:Distribution` is an accessible representation;
and a `dcat:DataService` is a collection of operations providing access or
processing. A `dcat:CatalogRecord` describes the catalogue entry rather than
the dataset itself. Misplacing a licence, byte size, endpoint, version, or
record-modification date changes its meaning. Always identify the subject
resource before accepting a field-level requirement. [w3c_dcat_3]

DCAT conformance requires an RDF description using DCAT terms consistently,
but allows additional RDF when DCAT has no suitable term. A DCAT profile adds
constraints while remaining DCAT-conformant. Valid profile additions include
cardinalities, controlled values, subclasses or subproperties, additional
metadata fields, and access-mechanism constraints. An extension is therefore
permitted, not automatically justified. [w3c_dcat_3]

DCAT-AP is a concrete European application profile. Its requirement levels,
resource-specific property tables, controlled vocabularies, and SHACL artefacts
are the compatibility baseline for a DCAT-AP-derived construction profile.
Never infer DCAT-AP cardinality from the DCAT vocabulary alone: DCAT generally
does not prescribe cardinalities. [eu_dcat_ap_3]

## Normative wording

Preserve the difference between a source saying that a system *can*, *may*,
*should*, or *must* provide information. A descriptive example is not a
normative obligation. Notes and implementation examples may clarify semantics
but cannot silently strengthen a requirement. If the corpus uses non-normative
language, record an obligation hint as tentative and flag it for human review.

When the profile uses mandatory, recommended, or optional property levels,
separate three questions:

1. Is the information need evidenced?
2. Is the value normally available for every resource, only a defined subset,
   or opportunistically?
3. Does the cited source justify the proposed obligation strength?

Conditional applicability should be explicit. For example, an IFC schema
version may be required for an IFC distribution without being required for
every construction dataset.

## SHACL and validation

SHACL describes RDF graph constraints through node and property shapes. A
shape needs a target or must be reached from another shape; a constraint must
use the correct RDF path, expected value kind, datatype/class, cardinality, or
controlled value. Validation reports identify focus nodes, result paths,
source shapes, constraint components, severity, and messages. [w3c_shacl]

Do not confuse closed-world validation with RDF meaning. Absence can violate a
profile's minimum cardinality even though open-world RDF does not imply that the
value is false. Likewise, a SHACL pass demonstrates conformance to the encoded
shapes, not semantic correctness, legal compliance, or data quality.

## Application-profile artefacts

The Singapore Framework separates functional requirements, domain models,
description-set constraints, usage guidance, and syntax guidance. The Profiles
Vocabulary can describe a profile and link its specifications, validation
artefacts, examples, and other representations. [dcmi_singapore_framework]
[w3c_profiles_vocabulary]

For each proposed requirement, expect a trace from stakeholder task or corpus
need to profile statement, term mapping, constraint, example, and validation
test. DCAT's use-case process retained links from accepted use cases to derived
requirements and explicitly removed duplicates before consensus. [w3c_dcat_ucr]

## Decision checklist

- Name the subject class: catalogue, record, dataset, series, distribution, or
  service.
- Quote only the verified evidence unit, not this RAG note.
- Separate vocabulary semantics from profile cardinality.
- Test whether DCAT-AP already constrains the property.
- Mark normative versus informative source material.
- Preserve language tags, IRIs, datatypes, ranges, and controlled vocabularies.
- Require a stable identifier and release/version for external vocabularies.
- Reject obligations inferred only from examples or common practice.
- Flag conflicts between the source corpus and inherited DCAT/DCAT-AP rules.

## Common failure modes

Typical errors are putting distribution format on the dataset, putting record
timestamps on the dataset, treating a landing page as a download URL, requiring
`dcat:servesDataset` where an exchange profile deliberately omits it, turning a
recommended controlled vocabulary into a closed universal enumeration, or
claiming that a SHACL shape proves conceptual interoperability.
