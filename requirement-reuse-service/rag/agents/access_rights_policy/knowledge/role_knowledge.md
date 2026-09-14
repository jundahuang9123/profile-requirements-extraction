# Access, Rights, Policy, and Usage knowledge pack

## Role boundary

This role extracts and models declared access, licence, policy, sensitivity, and
usage conditions. It does not decide whether a condition is lawful, give legal
advice, or invent policy text. Preserve the authoritative document, issuer,
jurisdiction, and exact relation whenever possible.

## Rights and licence placement

DCAT and DCTERMS distinguish general rights, access rights, and licences.
Dataset-level access rights describe who can access the dataset or its access
classification. A distribution licence governs use of that representation;
different distributions can have different licences. Catalogue or dataset
rights statements must not silently replace distribution-specific licences.
[w3c_dcat_3] [dcmi_metadata_terms] [eu_dcat_ap_3]

Prefer a recognised licence URI or document. Keep a human-readable statement as
additional information rather than parsing it into invented permissions. A
missing licence is not the same as public-domain permission.

## ODRL model

ODRL represents policies containing permissions, prohibitions, and duties over
assets. Rules can identify actions, assigners, assignees, targets, constraints,
and consequences. Policy subclasses include sets, offers, and agreements; an
ODRL profile can add community-specific terms. [w3c_odrl]

An offer is not an agreement. A permission is not access itself. A duty attached
to a permission is a condition that must be fulfilled. Constraints refine a
rule; they need explicit operands, operators, values, and data types. Policy
evaluation and enforcement lie outside basic metadata publication.

## Dataspace policy

DSP catalogue datasets carry ODRL offers associated with potential use. A data
service identifies the endpoint for negotiation and transfer. Contract
negotiation produces an agreement between provider and consumer. Catalogue
visibility can be restricted independently of final data access. [idsa_catalog_protocol]
[idsa_dataspace_protocol]

Record whether metadata describes public discovery, eligibility to view an
offer, an access class, a negotiable policy, a signed agreement, or a technical
authentication requirement. These are not interchangeable.

## Privacy and regulation context

DPV provides concepts for data categories, purposes, processing, controllers,
processors, recipients, legal bases, risks, measures, technologies, and laws.
It can describe declared privacy context but does not establish legal compliance.
A legal basis must be scoped to the applicable law and jurisdiction.
[w3c_dpv_2]

The EU Data Act Article 33 explicitly includes use restrictions, licences,
content, collection method, quality/uncertainty, vocabularies, access means, and
terms of use among interoperability descriptions. Model these when applicable;
do not turn the regulation into a universal field list without legal and domain
analysis. [eu_data_act]

Gaia-X trust descriptions can associate data products with licence, policy,
authorization, conformity, and verifiable claims. Preserve the issuer and proof
context rather than converting a claim into an unqualified boolean.
[gaia_x_trust_framework]

## Candidate requirement tests

- What resource is governed: dataset, distribution, service, catalogue, or
  negotiated transfer?
- Is the object a licence document, rights statement, access category, ODRL
  offer/agreement, privacy descriptor, or endpoint requirement?
- Who issued it and which jurisdiction/profile applies?
- Is the value a stable IRI with resolvable human-readable terms?
- Does the policy target match the associated resource?
- Can a consumer understand discovery visibility separately from access and use?
- Does the corpus justify machine-readable policy or only a document link?

## Failure modes

Do not infer permission from public discoverability. Do not state that
restricted metadata is confidential by definition. Do not turn an access-rights
category into a licence. Do not attach one policy indiscriminately to catalogue,
dataset, and every distribution. Do not set ODRL targets in conflict with the
exchange profile. Do not treat a policy syntax as proof of enforceability. Do
not expose sensitive details merely to improve discovery. Escalate legal
interpretation and privacy-risk decisions to qualified humans.
