# Literature-backed expert panel

## Why these 15 roles

DCAT defines profiles as DCAT-conformant specifications that may add
cardinalities, controlled vocabularies, subclasses, properties, or access
requirements. DCAT's own use-case process began with stakeholder problems,
retained links from requirements to use cases, removed duplicates, and reached
consensus. LOT likewise separates domain experts and users from ontology
developers and requires them to validate requirements. Construction adds
multiple lifecycle representations and governed vocabularies rather than one
canonical data model.

The resulting panel therefore needs four kinds of expertise:

1. **Metadata and semantic-web standards:** DCAT/DCAT-AP conformance, term
   reuse, profile design, SHACL, and controlled vocabularies.
2. **Construction representations:** lifecycle/spatial/classification context,
   IFC/BIM/IDS/bSDD, and AAS semantic identifiers and submodel templates.
3. **Data-space stakeholders and controls:** connector/catalog portability,
   publisher burden, consumer discovery, stewardship, rights/policies, and
   FAIR/quality/provenance.
4. **Method control:** minimality, provenance-preserving consolidation, and two
   independent critics for evidence/scope and reuse/representability.

This maps directly to the current 12 extraction roles, one consolidation role,
and two critic roles. The final three are methodological roles, not additional
domain-extraction votes.

## Role-to-expertise map

| Role | Required expert competence | Literature basis |
|---|---|---|
| `standards_conformance` | DCAT 3, DCAT-AP, RDF/SHACL, normative language | W3C DCAT and SHACL; SEMIC DCAT-AP |
| `dcat_reuse` | DCAT resource model and adjacent vocabularies | DCAT 3, DCTERMS, PROV-O, DQV, SKOS, ODRL |
| `construction_domain` | Built-asset lifecycle, classification, spatial and discipline context | ISO 12006, ISO 23386/23387, ISO 19650 guidance, BOT, GeoDCAT-AP |
| `aas_idta` | AAS metamodel, semanticId, ConceptDescription, submodels and APIs | IDTA AAS Parts 1, 2 and 3a; Semantic AAS research |
| `ifc_bim` | IFC schema/version/MVD, IDS, bSDD and openBIM exchange | ISO 16739, buildingSMART IDS and bSDD |
| `dataspace_interoperability` | DSP catalogue mapping, connectors, federation and portable identifiers | Dataspace Protocol, DSSC Blueprint, EDC, Gaia-X, Construct-X |
| `publisher_feasibility` | Metadata production, validation, maintenance and onboarding cost | DCAT-AP guidance, SHACL, metadata-quality studies, ISO 19650 |
| `consumer_discovery` | Dataset-search tasks, facets, comparison and fitness assessment | Dataset-search survey, discovery use cases, Google Dataset Search |
| `stewardship_governance` | Responsibility, provenance, versioning and vocabulary governance | PROV-O, DCAT 3, ISO 23386, bSDD, LOT |
| `access_rights_policy` | Licences, access categories, ODRL and dataspace policy placement | DCAT/DCAT-AP, ODRL, DSP, DPV, EU Data Act |
| `fair_quality_provenance` | FAIR indicators, DQV, PROV and quality-measure limits | FAIR principles, RDA maturity model, DQV, PROV-O |
| `minimality_scope` | Application-profile scope, competency questions and extension restraint | DCAT profiles, DCMI profile framework, LOT, Ontology 101 |
| `consolidation_conflict` | Deduplication, conflict preservation and traceability | W3C DCAT UCR method, ISO 29148, PROV-O |
| `grounding_scope_critic` | Evidence fidelity, atomicity, obligation and resource scope | ISO 29148, SHACL, DCAT conformance, requirements-quality research |
| `reuse_minimality_critic` | Existing-term audit, representability and downstream validation | DCAT/DCAT-AP reuse guidance, DCTERMS/SKOS/PROV/DQV/ODRL, SHACL |

## Coverage risks deliberately handled inside the stores

- **Geospatial/BIM-GIS context** is explicit in `construction_domain`, using
  GeoDCAT-AP, INSPIRE, and GeoSPARQL rather than creating a sixteenth role.
- **Construction terminology and classification** is covered by ISO 12006,
  ISO 23386/23387, and bSDD across `construction_domain`, `ifc_bim`, and
  `stewardship_governance`.
- **Lifecycle and information-management practice** is covered through the UK
  BIM Framework's ISO 19650 guidance and IFC lifecycle scope.
- **Legal interpretation** remains outside agent authority. The policy role can
  model declared licences, access rights, ODRL policies, privacy descriptors,
  and jurisdiction references, but cannot give legal advice.
- **Human validation** is outside the 15-agent machine panel and remains a
  separate study stage, preventing an agent from treating its own synthesis as
  expert consensus.
