# AAS and IDTA Semantics knowledge pack

## AAS mental model

An Asset Administration Shell (AAS) is a standardized digital representation
associated with an asset. The metamodel distinguishes the shell, asset
information, submodels, submodel elements, concept descriptions, administrative
information, and references. A submodel groups information for an aspect of the
asset. A catalogue description should not flatten every submodel element into
metadata. [idta_aas_part_1_3_1_2]

## Identifiers and semantic references

Identifiables such as AASs, submodels, and concept descriptions have global
identifiers. `idShort` is a local, human-oriented identifier and is not a
substitute for a global identifier. `semanticId` links an element to the concept
that defines its semantics; supplemental semantic identifiers can express
additional compatible semantic references. ConceptDescriptions can carry local
or referenced concept semantics, commonly structured through the IEC 61360 data
specification. [idta_aas_part_1_3_1_2]

For discovery, useful anchors may include an AAS identifier, asset identifier,
submodel identifier, submodel semantic identifier, submodel-template identifier,
or globally governed ConceptDescription/reference. The anchor must say what it
identifies. A raw `idShort`, display name, or copied property label is not an
interoperable semantic anchor.

The IEC 61360-oriented data specification defines structured preferred names,
short names, definitions, units, value formats, data types, and related
attributes. It helps interpret a ConceptDescription but does not mean that all
property-level details belong in DCAT metadata. [idta_aas_part_3a_3_1_1]

## Services, repositories, registries, and discovery

AAS Part 2 defines interfaces and profiles for an individual AAS, submodels,
repositories, concept-description repositories, registries, discovery, AASX
files, serialization, and self-description. API identifiers and paths have
specific encoding rules and profiles. [idta_aas_part_2_3_1_1]

Map these concepts to DCAT carefully:

- An exported AASX/JSON/XML/RDF representation may be a distribution of a
  dataset when it is a transferable representation.
- An AAS repository or submodel service may be described as a data service when
  it provides data access operations.
- A registry or discovery endpoint is not automatically the same thing as the
  dataset it helps locate.
- An API profile or metamodel release may be linked as a standard or conformance
  target; a claim of conformance needs separate evidence.

The IDTA schema repository publishes versioned JSON, XML, RDF, XMI, YAML, and
examples. Record exact release identifiers because the metamodel and
serializations evolve. [idta_aas_schema_releases]

## AAS and RDF

Research on the Semantic AAS demonstrates that an RDF representation can map
AAS structures, support validation and reasoning, and use native URIs, while
also exposing different assumptions between object-oriented AAS and Semantic
Web models. This is an interoperability option, not proof that every AAS dataset
is RDF or should be converted. [semantic_aas_paper]

## Candidate requirement tests

- Is the dataset actually AAS-related, or is AAS only mentioned in the project?
- Is the need dataset-level discovery or submodel-element data modelling?
- Does the anchor identify the shell, asset, submodel, template, concept, or
  service unambiguously?
- Is a globally stable identifier available?
- Does DCAT/DCTERMS already provide the relation?
- Is the property conditional on AAS resources?
- Does an API endpoint describe access, while a download describes a
  distribution?
- Is the exact AAS specification/schema version known?

## Failure modes

Do not require AAS metadata for non-AAS datasets. Do not make a local `idShort`
globally authoritative. Do not copy all AAS element types or property values
into the profile. Do not treat `semanticId` as a guarantee that the referenced
definition is accessible, governed, current, or mutually understood. Do not
conflate asset identity, shell identity, submodel identity, and semantic
identity. Do not claim an RDF mapping is semantically lossless without testing
the chosen mapping and use case.
