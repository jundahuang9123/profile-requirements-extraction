# Data Stewardship and Governance knowledge pack

## Governance scope

Stewardship keeps metadata trustworthy after initial publication. It covers who
is responsible, which source and process produced the dataset, what version and
status it has, how changes are recorded, which vocabularies are authoritative,
and how consumers report problems. Governance metadata should describe real
responsibilities and processes, not invent an organisation chart.

## DCAT responsibility and versioning

DCAT distinguishes creator, publisher, contact point, qualified attribution,
catalogue record, resource version, version notes, version relations, issued and
modified dates, and dataset series. Choose the relation that matches the role.
A publisher makes a resource available; a creator is primarily responsible for
creating it; a contact point handles questions; a catalogue record has its own
metadata lifecycle. [w3c_dcat_3] [dcmi_metadata_terms]

Version identifiers need scope. Dataset version, distribution revision,
metadata-record update, schema release, vocabulary release, and profile release
are different. A record modification date should not imply that the dataset
content changed. Dataset series can group evolving releases when that model fits
the domain.

## Provenance

PROV-O models entities, activities, and agents and relations such as generation,
derivation, use, attribution, association, and delegation. Use the starting-point
terms for simple lineage; use qualified relations when role, time, plan, or other
context matters. [w3c_prov_o]

Provenance granularity should match the decision. A consumer may need the
authoritative source, generating process, transformation, responsible party, or
validation activity. Do not require a complete workflow graph for every dataset
when a stable source relation answers the task.

## Construction information governance

ISO 19650 guidance connects information requirements, delivery, common data
environments, roles, review, authorization, and lifecycle operation. Operational
datasets can outlive project organisations, making handover and ongoing asset
responsibility critical. [uk_bim_guidance_part_3]

ISO 23386 defines governance and expert roles for construction-property
dictionaries. bSDD assigns dictionaries to publishing organisations and tracks
status and version. Active content is kept stable while changes produce new
versions; mappings and verification require governance. [iso_23386_2020]
[buildingsmart_bsdd]

These practices suggest metadata for vocabulary owner, scheme/version/status,
source authority, and maintenance contact when a construction semantic anchor
affects interpretation.

## Profile and ontology maintenance

LOT treats requirements, implementation, publication, and maintenance as an
iterative lifecycle. A published vocabulary needs stable IRIs, human and
machine-readable documentation, licence, release version, tests, and an issue
process. Domain experts and users validate requirements and updates.
[lot_methodology]

The Profiles Vocabulary can identify the profile and link to its specification,
constraints, guidance, and representations. This makes profile dependencies and
versions discoverable. [w3c_profiles_vocabulary]

## Governance checklist

- Identify creator, publisher, steward/contact, and any qualified role.
- Separate dataset, distribution, record, vocabulary, and profile versions.
- Record status using a governed scheme with clear transitions.
- Preserve previous identifiers and version relations.
- Name the provenance source or activity needed for fitness assessment.
- Record vocabulary/profile owner, release, licence, and persistence policy.
- Provide a feedback and correction route.
- Avoid orphan semantic anchors whose authority or definition cannot be found.
- Treat governance assertions as claims with responsible agents and dates.

## Failure modes

Do not use `publisher`, `creator`, and `contactPoint` interchangeably. Do not
overwrite previous metadata without version/change history. Do not treat an
organisation name string as a stable identity when a governed identifier is
available. Do not copy a classification into the profile and assume ownership.
Do not reference mutable preview terms in contractual metadata without status.
Do not require exhaustive provenance that publishers cannot maintain. Do not
declare a profile stable without release and deprecation rules.
