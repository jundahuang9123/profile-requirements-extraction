# Dataspace and Connector Interoperability knowledge pack

## Dataspace frame

A data space connects autonomous participants that retain control of their data
while publishing offers, negotiating agreements, and transferring data under
governed conditions. Catalogue portability is distinct from data-model
interoperability and from transfer-protocol compatibility. Keep those layers
separate when extracting requirements.

Construct-X applies this frame to heterogeneous and temporary construction
value networks, with open-source federation, secure collaboration, data
sovereignty, cloud-edge processing, and lifecycle use cases. A profile should
therefore avoid dependence on one connector product or central catalogue.
[construct_x_official]

## Dataspace Protocol catalogue semantics

The Dataspace Protocol (DSP) uses DCAT catalogues for dataset offers and ODRL
for usage control. It specifies catalogue request/response, contract negotiation,
and transfer-process control while leaving the data payload and transport
details to other agreements. [idsa_dataspace_protocol]

The catalogue mapping constrains DCAT resources. A dataset can carry one or more
ODRL offers. Distributions refer to data services that identify where contract
negotiation and transfer can be initiated. Participant identifiers and endpoint
types have protocol-specific positions. A catalogue itself should not inherit a
dataset's negotiable offer merely because both are RDF resources. Catalogue
visibility may be access-controlled and brokers must respect upstream controls.
[idsa_catalog_protocol]

Do not copy an EDC internal asset JSON structure into a DCAT profile. Model the
portable semantics: offered dataset, distribution/access representation, data
service endpoint, participant, policy offer, standard/profile, and lifecycle.

## DSSC building blocks

The DSSC Blueprint separates data interoperability, data exchange, semantic
models, data/service/offering descriptions, publication/discovery, identity,
trust, and governance. It notes that data models can themselves be catalogued
and exchanged using DCAT and DSP. It also treats data-model governance and
semantic annotation as explicit capabilities, not automatic outcomes of a
connector. [dssc_blueprint]

A construction profile can reference the model, vocabulary, classification,
schema, or profile that explains a dataset. It should not require all
participants to transform their data to a single model unless the data-space
rulebook explicitly does so.

## EDC implementation concepts

Eclipse Dataspace Components implements assets, policy definitions, contract
definitions, catalogues, contract negotiations, transfer processes, federated
catalogues, participant context, identity, a control plane, and data planes.
[eclipse_edc_autodoc]

These are implementation concepts. Use them to test feasibility and mapping,
not to define vendor-specific metadata. A connector asset may be transformed
into DSP/DCAT output; not every internal field belongs in the interchange
profile. A management API endpoint is not necessarily the public data service
endpoint advertised to consumers.

## Trust and compliance

Gaia-X descriptions include trust and compliance claims about participants,
services, and data products and can require machine-readable licences or usage
policies. A claim, its issuer, proof, validation status, and the data offering
are separate resources. [gaia_x_trust_framework]

The EU Data Act requires data-space participants to describe content,
restrictions, licences, collection methods, quality and uncertainty, structures,
formats, vocabularies/classifications, access means, terms, and quality of
service sufficiently for finding, accessing, and using data. This motivates
metadata categories but does not determine a single DCAT property or make every
field mandatory in every construction profile. [eu_data_act]

## Candidate requirement tests

- Is the item portable across connector implementations?
- Does it describe the offering, dataset, distribution, service, participant,
  policy, agreement, or transfer process?
- Is it needed during discovery, negotiation, or transfer—and at which stage?
- Can DSP/DCAT/ODRL already represent it?
- Does the profile expose a public semantic identifier rather than an internal
  database key?
- Does catalogue visibility differ from data access permission?
- Is the requirement about semantic interpretation or transport mechanics?

## Failure modes

Avoid conflating catalogue discovery with data transfer, a policy offer with a
signed agreement, an access URL with a management endpoint, participant identity
with publisher attribution, and a connector asset with a DCAT dataset. Do not
assume a central broker, EDC, Gaia-X credentials, or a specific JSON-LD context
unless the declared infrastructure requires it. Do not claim semantic
interoperability merely because two connectors complete a transfer.
