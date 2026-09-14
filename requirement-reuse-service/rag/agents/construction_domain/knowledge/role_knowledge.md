# Construction Domain Semantics knowledge pack

## Domain frame

Construction information spans temporary project organisations and long-lived
assets. It crosses briefing, design, procurement, fabrication, construction,
commissioning, operation, maintenance, renovation, and demolition. It also
crosses architectural, structural, civil, building-services, geospatial,
commercial, sustainability, safety, and facility-management disciplines.
Discovery metadata should expose distinctions that let a consumer choose a
relevant dataset without reproducing the internal model.

Construct-X targets open federated data spaces for heterogeneous construction
value networks, secure collaboration, data sovereignty, cloud-edge use, and
building lifecycle applications. This makes portable, participant-neutral
catalogue semantics more important than platform-specific fields.
[construct_x_official]

## Construction classification and terminology

ISO 12006-2 provides a framework for classifying construction information by
different views and object classes across the whole lifecycle. It does not
impose a single global classification system. A catalogue should therefore
identify the concept and its scheme, version, publisher, and status rather than
copying a local notation as an unexplained string. [iso_12006_2_2015]

ISO 23386 addresses definition, authoring, maintenance, expert roles, mapping,
and governance of construction properties in interconnected dictionaries.
ISO 23387 defines data-template structures for machine-interpretable properties
of objects and links to classifications. bSDD operationalizes interconnected
dictionaries with organisation ownership, versions, statuses, stable URIs,
classes, properties, relations, and mappings. [iso_23386_2020]
[iso_23387_2025] [buildingsmart_bsdd]

Catalogue implications include semantic anchors for an asset type,
classification concept, data dictionary, template, or standard. Do not copy all
dictionary classes and properties into the catalogue. Record only the anchors
needed to understand or retrieve the dataset and preserve the original
authority's URI.

## Lifecycle and information management

The ISO 19650 ecosystem treats BIM as information management, not merely 3D
geometry. The UK BIM Framework guidance covers structured information, openBIM,
organisational responsibilities, information requirements, common data
environments, delivery, and operation. Dataset discovery may need lifecycle
phase, information purpose, status/suitability, project/asset context, discipline,
or responsible actor. The exact vocabulary and obligation must come from the
study corpus. [uk_bim_guidance_part_b] [uk_bim_guidance_part_3]

Distinguish a project information model from an asset information model, but do
not assume every repository uses those labels uniformly. A dataset may cross
phases or contain mixed information. Prefer stable controlled concepts and
allow multiple values where the discovery task requires them.

## Spatial and topological context

BOT deliberately models a small core: sites, buildings, storeys, spaces,
elements, and interfaces, with links to geometry and other vocabularies. Its
minimality shows that useful building anchors need not mirror IFC. A dataset can
refer to a building, zone, storey, space, or element concept without embedding
their full internal graph. [bot_ontology_paper]

Construction data can also be geospatial. GeoDCAT-AP maps ISO/INSPIRE metadata
into DCAT-AP and includes reference-system and service context. GeoSPARQL
formalizes spatial objects, geometries, coordinate reference systems, and
relations. Before inventing construction spatial properties, check DCAT spatial
coverage/resolution, GeoDCAT-AP, and GeoSPARQL. [eu_geodcat_ap_3]
[ogc_geosparql_1_1] [inspire_metadata_guidance]

## Discovery distinction test

A construction distinction belongs in the profile only when all are true:

1. A consumer task requires it before opening or processing the data.
2. The source corpus supports the distinction.
3. It can be maintained at dataset, distribution, or service level.
4. The value has stable semantics or a documented controlled scheme.
5. Existing DCAT/DCAT-AP/geospatial terms do not already represent it.

Promising categories are asset or facility context, project context, lifecycle
phase, discipline, representation family, schema or standard conformance,
classification/dictionary anchor, spatial coverage or reference system, and
information purpose. Treat level of detail/information need, status, and
suitability carefully because their definitions vary by framework.

## Exclusions

Exclude geometry, coordinates of individual objects, element property values,
quantities, schedules, sensor observations, clash results, model calculations,
and project-specific object instances unless the catalogue is actually
cataloguing those resources and the evidence requires a summary. Exclude the
assumption that IFC, AAS, documents, point clouds, GIS, and time series share one
internal model. The profile is a discovery bridge across heterogeneity, not a
replacement for domain standards.
