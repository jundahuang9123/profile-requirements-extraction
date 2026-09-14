# Data Publisher Feasibility knowledge pack

## Feasibility lens

A useful metadata requirement fails in practice when publishers cannot obtain,
understand, validate, or maintain the value. Evaluate feasibility separately
from importance. Do not delete an evidenced need because it is burdensome;
instead recommend conditionality, a weaker obligation, tooling, controlled
defaults, derivation, or staged adoption and preserve the trade-off for humans.

## Metadata production cost

For each candidate ask who knows the value, when it becomes known, whether it is
stable, where it is already recorded, and who owns updates. Construction values
may originate with a client, designer, BIM coordinator, contractor, product
manufacturer, CDE administrator, asset operator, data steward, or connector
operator. A profile should not require a publisher to assert information owned
by another actor without a governance path.

ISO 19650 guidance distributes information-management responsibilities across
roles and lifecycle processes. Design/construction and operational information
have different owners, triggers, and handovers. This makes lifecycle-aware
conditionality important. [uk_bim_guidance_part_b] [uk_bim_guidance_part_3]

## Validation and obligation levels

DCAT-AP combines human-readable rules, controlled vocabularies, and SHACL.
SHACL can test presence, value kind, datatype, class, pattern, cardinality, and
approved values. It cannot determine whether a description is factually true,
whether a classification was chosen competently, or whether a policy is lawful.
[eu_dcat_ap_3] [w3c_shacl]

Obligation should reflect evidence and supply conditions:

- **Mandatory:** every in-scope resource can and must supply it.
- **Conditional mandatory:** required when a stated condition holds, such as an
  IFC distribution having an IFC schema version.
- **Recommended:** high discovery value, but unavailable or uncertain in a
  meaningful portion of cases.
- **Optional:** useful when present, with no expectation of complete coverage.

Avoid a default that fabricates knowledge. `unknown`, not-applicable, missing,
and not-yet-provided have different meanings and may need different treatment.

## Quality evidence

Empirical portal studies show recurring problems with completeness, accuracy,
retrievability, timeliness, and licence information. Mapping heterogeneous
portal metadata into DCAT enables automated checks, but field presence alone is
not quality. [metadata_quality_neumaier]

Production DCAT-AP quality assessment uses scalable validation and reporting to
help publishers improve large catalogues. A feasible profile should provide
clear messages, examples, stable shapes, and a route to correct errors rather
than only failing ingestion. [dcat_ap_quality_framework]

Different stakeholders weight quality dimensions differently. Avoid one
unexplained overall score; expose actionable dimensions or validation results.
[metadata_catalogue_quality_comparison]

## Controlled vocabularies

Controlled IRIs improve interoperability but introduce dependencies: scheme
governance, URI persistence, release/version, multilingual labels, mappings,
deprecation, and publisher lookup tools. bSDD illustrates owner-governed
dictionaries, preview/active/inactive status, immutable active definitions,
versions, and mappings. [buildingsmart_bsdd]

Before making a semantic anchor mandatory, verify that the scheme covers the
domain, permits reference, remains resolvable, and has a value-selection
workflow. A free-text fallback can help onboarding but should not be presented
as semantically equivalent.

## Feasibility record

For each requirement capture:

- responsible actor and lifecycle moment;
- source system or manual process;
- expected availability and update frequency;
- validation method and limits;
- vocabulary/version dependency;
- conditional applicability;
- burden and likely error modes;
- recommended obligation with rationale.

## Failure modes

Do not equate automatically extractable with semantically reliable. Do not make
all desirable fields mandatory. Do not ask publishers to maintain copies of
external taxonomies. Do not require expensive model inspection for metadata
that should be declared at publication. Do not assume a CDE, IFC file, AAS, or
connector contains every catalogue value. Do not hide onboarding cost inside a
generic statement such as "publishers shall provide complete metadata."
