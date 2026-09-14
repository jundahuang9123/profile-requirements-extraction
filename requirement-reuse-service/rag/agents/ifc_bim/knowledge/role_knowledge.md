# IFC and BIM Semantics knowledge pack

## IFC scope

IFC is an open international standard for BIM information exchanged among
construction and facility-management applications. ISO 16739-1 covers buildings
and infrastructure, multiple lifecycle phases and disciplines, the data schema,
property and quantity sets, exchange structures, and Model View Definitions
(MVDs). An MVD selects and constrains a subset of IFC for recognised exchange
workflows. [iso_16739_1_2024]

Catalogue metadata may need to identify the IFC schema release, serialization,
MVD/exchange requirement, discipline or purpose, and validation status. These
concepts are distinct. A file with an `.ifc` extension does not by itself prove
which release, MVD, or information requirements it satisfies.

## IDS and information requirements

buildingSMART IDS 1.0 represents information requirements in a
computer-interpretable form and supports automated checking of IFC objects,
classifications, materials, properties, and values. It specifies what selected
model entities should contain under stated applicability conditions. IDS is not
a general dataset catalogue. [buildingsmart_ids_1]

A profile can link a BIM dataset or distribution to an applicable IDS document,
its identifier/version, or a validation result when the corpus supports that
need. Do not copy every IDS facet into DCAT. Distinguish: the dataset conforms to
an IDS; the dataset is accompanied by an IDS; the dataset was validated against
an IDS; and the dataset is an IDS specification. These are different claims.

## bSDD and semantic classification

bSDD distributes independently governed data dictionaries. It supplies classes,
properties, relations, mappings, owner and version information, status, and
stable URIs. It also exposes IFC terms and supports references from IFC and IDS.
An active definition is intended to remain immutable; new changes produce a new
version while older content remains available. [buildingsmart_bsdd]

For discovery, link to the exact dictionary, class, property set, or concept
needed by the task. Do not use only a local code without its dictionary. Do not
assume that a bSDD mapping makes two concepts logically equivalent: inspect the
mapping relation and publisher governance.

## Information-management context

The ISO 19650 ecosystem emphasizes structured information, roles, requirements,
delivery, common data environments, and lifecycle management. BIM datasets can
be geometric models, schedules, documents, COBie-like tables, requirements,
validation reports, or mixed containers. [uk_bim_guidance_part_b]
[uk_bim_guidance_part_3]

Useful catalogue distinctions may include project or asset, phase, discipline,
information purpose, model federation/segmentation, schema, exchange
requirement, authoring/issuing actor, status, and access method. Each must answer
a pre-access consumer question and use a governed value when possible.

## Linked Building Data

BOT provides a lightweight Web ontology for sites, buildings, storeys, spaces,
elements, interfaces, and links to geometry. It is useful as a semantic anchor
or integration hub precisely because it does not reproduce the IFC schema.
[bot_ontology_paper]

An IFC dataset may link to BOT, bSDD, or another ontology without being converted
to that ontology. Record whether a URI describes a vocabulary used, a concept
covered, a mapping, or an actual RDF representation. These relations should not
be collapsed into a vague `usesOntology` claim without semantics.

## Candidate requirement tests

- Does the requirement support finding or selecting a BIM exchange before
  opening the model?
- Is it about the abstract dataset, one file distribution, or an access service?
- Are schema version, serialization, and MVD/IDS kept distinct?
- Can the value be a stable standard/document/concept IRI?
- Is the requirement conditional on IFC/BIM content?
- Would a link preserve authority better than copying fields?
- Is a validation result accompanied by validator/version/date and target?

## Exclusions

Exclude IFC entity instances, GlobalIds of every object, geometry, coordinates,
quantities, property values, relationship graphs, clash results, and derived
calculations from the catalogue profile. Do not require a single MVD, discipline,
classification, or lifecycle scheme for every construction dataset. Do not call
all construction documents BIM, and do not treat BIM as synonymous with 3D.
