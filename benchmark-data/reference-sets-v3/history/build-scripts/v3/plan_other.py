# Stat, Geo and JRC atoms for the v3 merged reference set.
import sys
sys.path.insert(0, '/home/claude/analysis')
from plan_health import A
from completion import GEO as GEO_V2

S = 'StatDCAT-AP 1.0.0 '
G = 'GeoDCAT-AP 1.0 '
J = 'Perego et al. 2016 (SDSVoc paper 27), '

STAT_PARENT_CHANGES = {
 'S-7': dict(note_add='Representation guidance in the source, split into start, end and periodicity atoms; not three new stakeholder requirements.'),
}
STAT = [
 A('S-1.1', 'S-1', 'Describe the dimensions that identify observations in a statistical dataset (e.g. time, sex, age, region), the same way whatever the distribution format.',
   pr45=['SC-006'], rel='beyond_base', loc=S + '§7.2.1', anchor='Dimensions: components that identify observations such as time, sex, age, regions',
   note='SC-006 adds the format independence stated in §7.2.1.'),
 A('S-2.1', 'S-2', 'Describe the attributes needed to qualify and interpret observed values (e.g. units of measure, scaling factors, observation status), the same way whatever the distribution format.',
   pr45=['SC-007'], rel='beyond_base', loc=S + '§7.2.1', overlaps=['S-6.1'],
   anchor='Attributes: components used to qualify and interpret observed values such as units of measure, scaling factors'),
 A('S-3.1', 'S-3', 'Link quality information to the statistical dataset or distribution it describes.', pr45=['SC-009'], rel='beyond_base',
   loc=S + '§7.2.2', anchor='an explicit link to the resource being annotated (oa:hasTarget)'),
 A('S-3.2', 'S-3', 'State the motivation of each quality annotation.', pr45=['SC-008'], rel='beyond_base', loc=S + '§7.2.2',
   anchor='The annotation requires the provision of information about the motivation of the annotation (oa:motivation)'),
 A('S-3.3', 'S-3', 'Provide the quality information as text or as a link to quality information published elsewhere.', pr45=['SC-010'],
   rel='beyond_base', loc=S + '§7.2.2',
   anchor='either through linking to quality information that is already published elsewhere or by including text with quality information'),
 A('S-4.1', 'S-4', 'Link to visualisations of the data (tables, graphs or interactive views), modelled as distributions of type visualisation.',
   rel='extends_base', loc=S + '§7.2.3',
   anchor='One of the requirements raised during discussions was the need to be able to link to a visualisation of the data'),
 A('S-5.1', 'S-5', 'State the actual number of data series in a dataset, as distinct from the number of observations and the theoretical number of combinations.',
   pr45=['SC-011'], rel='beyond_base', loc=S + '§7.2.4',
   anchor='One additional requirement was about expressing the number of data series contained in a dataset.'),
 A('S-6.1', 'S-6', 'State the unit of measurement of the observations in a dataset.', rel='beyond_base', loc=S + '§7.2.5',
   anchor='A requirement was brought forward to allow expression of the unit of measurement.'),
 *[A(f'S-7.{i}', 'S-7', stmt, pr45=[p], status='guidance', rel='restates_base', modality='representation_guidance', loc=S + '§7.2.6',
     anchor='To describe such a time series, a StatDCAT-AP-compliant description would specify:')
   for i, (stmt, p) in enumerate([('State the start of the period a time series covers.', 'SC-012'),
                                  ('State the end of the period a time series covers.', 'SC-013'),
                                  ('State the periodicity of a time series.', 'SC-014')], start=1)],
 A('S-8.1', 'S-8', 'Improve the discoverability of statistical datasets on general open data portals.', v2=['S-8'],
   anchor='an initial focus on discovery of those data sets in a wider context'),
 A('S-9.1', 'S-9', 'Let statistical portals export their metadata in the profile, so general open data portals can take it up.', v2=['S-9'],
   loc=S + '§5.2; §8', anchor='the provision of information based on the StatDCAT-AP specification will involve some form of extraction or mapping process'),
 A('S-9.2', 'S-9', 'Give guidance for mapping and extracting metadata from SDMX-based systems.', v2=['S-9'], loc=S + 'Annexes IV–V',
   anchor='It enables organisations using SDMX to know which metadata structures to use'),
 A('S-10.1', 'S-10', 'Conform fully to DCAT-AP and keep statistical descriptions aligned with DCAT and DCAT-AP.', pr45=['SC-001'], v2=['S-10'],
   loc=S + '§6.2; §7.1', anchor='it meets all obligations of the DCAT-AP Conformance Statement',
   note='SC-001 (§6.2 principle) and S-10 (§7.1 conformance) express the same alignment need.'),
 A('S-11.1', 'S-11', 'Concentrate on the metadata elements that help users discover datasets.', pr45=['SC-002'], v2=['S-11'],
   anchor='focus primarily on metadata elements that contribute to data discovery'),
 A('S-12.1', 'S-12', 'Take terms from existing, well-known and well-maintained vocabularies.', pr45=['SC-003'], v2=['S-12'],
   anchor='use metadata terms from existing, well-known and well-maintained vocabularies'),
 A('S-13.1', 'S-13', 'Prefer common controlled vocabularies, preferably those maintained by the EU Publications Office.', pr45=['SC-004'], v2=['S-13'],
   anchor='encourage the use of common controlled vocabularies, preferably those maintained by the Publications Office'),
 A('S-14.1', 'S-14', 'Balance simplicity and expressiveness for a wide, non-specialist audience.', pr45=['SC-005'], v2=['S-14'],
   anchor='find an appropriate balance between simplicity and complexity'),
 A('S-15.1', 'S-15', 'Make the profile usable for datasets in any format, such as SDMX, Data Cube or CSV.', v2=['S-15'],
   overlaps=['S-1.1', 'S-2.1'], anchor='can be used to describe datasets in any format'),
 A('S-16.1', 'S-16', "Classify statistical datasets by EU data theme, mapping Eurostat's own themes onto it.", v2=['S-16'], rel='restates_base',
   note='StatDCAT-AP "uses the same controlled vocabularies as DCAT-AP" (§7.8); dcat:theme stays recommended. The Eurostat mapping (Table 2) is guidance.',
   anchor='Mappings between the Eurostat theme vocabulary and the MDR data themes'),
 A('S-17.1', 'S-17', 'Link an RDF distribution to the data structure definition it follows.', v2=['S-17'], status='guidance', modality='optional',
   note='The proposal to use dct:conformsTo instead of stat:dimension and stat:attribute was rejected; an RDF distribution "may use" it in addition.',
   anchor='a RDF distribution may use dct:conformsTo in addition'),
 A('S-18.1', 'S-18', 'Record publication and modification times to the time of day when data are published more than once a day.', v2=['S-18'],
   anchor='if a dataset is published more than once per day, more precise information about the actual publication time will be needed'),
 A('S-19.1', 'S-19', 'Identify the measures a statistical dataset contains, as SDMX and Data Cube define them.', v2=['S-19'], status='deferred',
   anchor="Consider adding 'measure' property for future revisions"),
 A('S-20.1', 'S-20', 'Describe the quality of statistical data in more detail, e.g. following the ESS Single Integrated Metadata Structure (SIMS).',
   v2=['S-20'], status='deferred', overlaps=['S-3.1'], anchor='In future work, a more fundamental treatment of quality aspects may be undertaken'),
 A('S-21.1', 'S-21', 'Show how DDI descriptions of datasets can be expressed with the profile.', v2=['S-21'], status='deferred',
   anchor='Contacts have been established with the DDI initiative'),
 A('S-22.1', 'S-22', 'Document, with a full example, how datasets, distributions, Data Cube datasets and data structure definitions relate.', v2=['S-22'],
   anchor='Add full example of a StatDCAT-AP-compliant description of a Data Cube DataSet'),
]

GEO_PARENT_CHANGES = {
 'G-44': dict(note_add='Its "reuse existing vocabularies" and "avoid new terms" parts are the same needs as G-3.1 and G-5.1 and are scored there.'),
 'G-41': dict(note_add='Conceptual and domain consistency are separate rows of Annex I Table 5 and become separate atoms (as in PR #45).'),
 'G-30': dict(statement='State the temporal reference system of a dataset.', reason='"where it is not the default one" is not in GeoDCAT-AP 1.0 (independent check).'),
 'G-38': dict(statement='State any limitations on public access to a resource.', reason='"and the reasons for them" is not in GeoDCAT-AP 1.0 (independent check).'),
}
GEO = [
 A('G-1.1', 'G-1', 'Provide a DCAT-AP-conformant representation of geospatial metadata.', loc=G + '§4.1',
   anchor='Provide a DCAT-AP-conformant representation of geospatial metadata.'),
 A('G-1.2', 'G-1', 'Provide an RDF representation of geospatial metadata that is as comprehensive as possible and avoids semantic loss.', loc=G + '§4.1',
   anchor='Provide an as much as possible comprehensive RDF-based representation of geospatial metadata'),
 A('G-1.3', 'G-1', 'Promote the cross-domain reuse of geospatial metadata.', loc=G + '§4.1', overlaps=['G-42.1'],
   anchor='trying, at the same time, to avoid semantic loss and to promote cross-domain re-use.'),
 A('G-2.1', 'G-2', 'Include, at least, all mandatory DCAT-AP elements.', loc=G + '§4.1',
   anchor='GeoDCAT-AP must include, at least, all the mandatory DCAT-AP elements.'),
 A('G-3.1', 'G-3', 'Use vocabularies other than DCAT-AP only for geospatial metadata elements that DCAT-AP does not support.', loc=G + '§4.1',
   anchor='Vocabularies different from DCAT-AP can be used only for those geospatial metadata elements not supported in DCAT-AP.'),
 A('G-4.1', 'G-4', "Base the alignments as far as possible on existing practice, in particular the working group's experience.", loc=G + '§4.1',
   anchor='Another key criterion was to base as much as possible the defined alignments on existing practices'),
 A('G-4.2', 'G-4', 'Avoid a negative impact on existing implementations.', loc=G + '§4.1', overlaps=['G-7.2'],
   anchor='to avoid a negative impact on existing implementations'),
 A('G-5.1', 'G-5', 'Define new terms only when existing vocabularies offer no suitable candidate, and only after careful assessment.', loc=G + '§1.1; §4.1',
   anchor='the possibility of defining new terms was not excluded. However, this option needed to be carefully assessed'),
 A('G-5.2', 'G-5', 'Discard new terms that could conflict with standards under preparation.', loc=G + '§4.1',
   anchor='discarded whenever it might have led to a specification that was conflicting with standards under preparation'),
 A('G-6.1', 'G-6', 'Cover all metadata elements of the core profile of ISO 19115.', loc=G + '§4.2',
   anchor='All the metadata elements in the core profile of ISO 19115.'),
 A('G-6.2', 'G-6', 'Cover the INSPIRE metadata elements, leaving out only those not common to all INSPIRE spatial data themes.', loc=G + '§4.2',
   anchor='All the metadata elements defined in INSPIRE, with the exclusion of those not common to all the INSPIRE spatial data themes.'),
 A('G-6.3', 'G-6', 'Exclude only optional elements.', loc=G + '§4.2', anchor='with the requirement that only optional elements might be excluded'),
 A('G-7.1', 'G-7', 'Offer an RDF syntax binding as an additional way to implement and publish INSPIRE/ISO metadata on DCAT-AP-conformant portals.',
   loc=G + '§1', overlaps=['G-43.1'], anchor='providing the means of an additional implementation through harmonised RDF syntax bindings'),
 A('G-7.2', 'G-7', 'Leave the INSPIRE metadata regulation and technical guidelines, and the collections maintained under them, unchanged.',
   loc=G + '§1', anchor='The GeoDCAT-AP specification does not replace the INSPIRE Metadata Regulation'),
]
# Annex I Table 5 element atoms: one per table row, with the three dates and the two consistency types split (as in PR #45).
_split = {'G-16': [('Give the date of creation of a resource.', 'GC-009', 'beyond_base'),
                   ('Give the date of publication of a resource.', 'GC-010', 'restates_base'),
                   ('Give the date of last revision of a resource.', 'GC-011', 'restates_base')],
          'G-41': [('Report the conceptual consistency of a dataset as a data quality result.', 'GC-036', None),
                   ('Report the domain consistency of a dataset as a data quality result.', 'GC-037', None)]}
_anchor = {'G-16': 'By contrast, date of publication, last revision, and creation are mapped, respectively, to dct:issued, dct:modified',
           'GC-036': 'Conceptual consistency', 'GC-037': 'Domain consistency'}
_gc = iter(range(1, 38))
for r in GEO_V2:
    n = int(r['id'][2:])
    if not 8 <= n <= 41:
        continue
    extra = r.get('extra', {})
    base = dict(v2=[r['id']], rel=r['relation'], loc=r['locator'], app='Use the dataset, series or service applicability and conditions of Annex II; not every element is mandatory for every resource.')
    if r['id'] in _split:
        for i, (stmt, p, rel) in enumerate(_split[r['id']], start=1):
            next(_gc)
            GEO.append(A(f"{r['id']}.{i}", r['id'], stmt, pr45=[p], **{**base, 'rel': rel or r['relation']},
                         anchor=_anchor.get(r['id']) or _anchor[p], note='', added=False))
    else:
        GEO.append(A(f"{r['id']}.1", r['id'], r['statement'], pr45=[f'GC-{next(_gc):03d}'], **base, anchor=r['anchor'], note=r['note']))
    for a in GEO[-1:] if r['id'] not in _split else GEO[-len(_split[r['id']]):]:
        a['geo'] = dict(inspire_obligation=extra.get('inspire_obligation'), iso19115_core_obligation=extra.get('iso19115_core_obligation'),
                        dcat_ap_coverage=extra.get('dcat_ap_coverage'))
F_T5 = 'Source inconsistency: '
GEO_OVERRIDES = {
 'G-8.1': dict(rel='extends_base', note='dcat:contactPoint, a DCAT-AP 1.1 dataset property, used on the catalogue record (Table 3).'),
 'G-9.1': dict(flags=[F_T5 + 'Table 5 marks metadata date as covered by DCAT-AP, but Annex II.11 says "DCAT-AP does not foresee a property equivalent to the INSPIRE metadata element metadata date" and maps it to dct:modified.']),
 'G-11.1': dict(statement='State the character set of a metadata record.'),
 'G-12.1': dict(statement='Give a metadata record a file identifier.', rel='extends_base', note='dct:identifier, a DCAT-AP 1.1 dataset property, used on the catalogue record (Annex II.17).'),
 'G-13.1': dict(rel='restates_base', flags=[F_T5 + 'Table 5 leaves the DCAT-AP column empty, but Annex II.18 says "Following DCAT-AP, GeoDCAT-AP uses dct:conformsTo" on the catalogue record (recommended in DCAT-AP 1.1).']),
 'G-14.1': dict(rel='extends_base', flags=[F_T5 + 'Table 5 leaves the DCAT-AP column empty, but Annex II.18 encodes the version with the standard referenced through dct:conformsTo.']),
 'G-16.1': dict(anchor='By contrast, date of publication, last revision, and creation are mapped, respectively, to dct:issued, dct:modified (both core and extended GeoDCAT-AP profiles), and dct:created (only for the extended profile of GeoDCAT-AP).'),
 'G-20.1': dict(note='Annex II.10 adds encoding constraints (at least GML or WKT; the CRS must be specified); restates_base holds for the statement as worded.'),
 'G-22.1': dict(rel='restates_base', note='DCAT-AP maps temporal extent to dct:temporal; the ISO element also includes vertical extent, which GeoDCAT-AP 1.0 does not cover.'),
 'G-27.1': dict(flags=[F_T5 + 'Table 5 says DCAT-AP supports 3 of the 11 responsible-party roles; Table 2 says "DCAT-AP foresees only 2 of the 11".']),
 'G-29.1': dict(rel='extends_base', note='The source says no equivalent DCAT-AP term is foreseen and maps reference systems provisionally to dct:conformsTo (Annex II.23).'),
 'G-30.1': dict(statement='State the temporal reference system of a dataset.', rel='extends_base',
                note='The source says no equivalent DCAT-AP term is foreseen and maps reference systems provisionally to dct:conformsTo (Annex II.23).'),
 'G-31.1': dict(rel='partly_base', flags=[F_T5 + 'Table 5 marks conformity as covered by DCAT-AP, but Annex II.14 says dct:conformsTo "can be used to map only a conformity of degree \'conformant\'".']),
 'G-38.1': dict(statement='State any limitations on public access to a resource.',
                flags=['Obligation inconsistency: limitations on public access are M in Table 5 and (C) in Table 2.']),
 'G-39.1': dict(flags=['Obligation inconsistency: maintenance information is O in Table 5 and (R) in Table 2.']),
 'G-41.1': dict(flags=['Obligation inconsistency: conceptual and domain consistency are O in Table 5 and (R) in Table 3.']),
 'G-41.2': dict(flags=['Obligation inconsistency: conceptual and domain consistency are O in Table 5 and (R) in Table 3.']),
}
for a in GEO:
    o = GEO_OVERRIDES.get(a['id'])
    if o:
        for k, v in o.items():
            a[k] = v
for a in GEO:
    if a['parent'] == 'G-16' and a['id'] != 'G-16.1':
        a['anchor'] = GEO_OVERRIDES['G-16.1']['anchor']
GEO += [
 A('G-42.1', 'G-42', 'Make spatial datasets, dataset series and services searchable on general data portals.', v2=['G-42'], overlaps=['G-1.3'],
   anchor='Its basic use case is to make spatial datasets, dataset series, and services searchable'),
 A('G-43.1', 'G-43', 'Support the conversion of ISO 19115/INSPIRE metadata records into the RDF representation; conversion back is not required.',
   v2=['G-43'], overlaps=['G-7.1'],
   anchor='The defined syntax binding must enable the conversion of metadata records from ISO 19115 / INSPIRE to a harmonised RDF representation'),
 A('G-44.1', 'G-44', 'Keep the RDF syntax binding as simple as possible.', v2=['G-44'], overlaps=['G-3.1', 'G-5.1'],
   anchor='principle is to make the resulting RDF syntax as simple as possible'),
 A('G-45.1', 'G-45', 'Reuse the published alignments between EuroVoc, GEMET and the INSPIRE themes.', v2=['G-45'],
   anchor='To take into account and refer to alignment of relevant controlled vocabularies'),
 A('G-46.1', 'G-46', 'Feed recommendations into the DCAT-AP revision so that DCAT-AP and GeoDCAT-AP stay aligned.', v2=['G-46'],
   anchor='To formulate recommendations to the Working Group dealing with the revision'),
]

JRC_PARENT_CHANGES = {
 'JRC-8': dict(statement='Indicate when a distribution gives access through a service or API rather than to the data itself, and describe the service interface with the query parameters needed to select data.',
               reason='The paper\'s second API requirement asks for the interface description with its query parameters (found by PR #45, JC-004).'),
 'JRC-9': dict(note_add='Reproducibility and usage tracking are two purposes of one provenance need, so one atom.'),
}
JRC = [
 A('JRC-1.1', 'JRC-1', 'Identify the authors of a dataset.', loc=J + '"Metadata elements relevant for scientific data", item 1',
   anchor='Ability to indicate dataset authors.'),
 A('JRC-2.1', 'JRC-2', 'Describe the lineage of a dataset.', loc=J + '"Metadata elements relevant for scientific data", item 2', overlaps=['JRC-9.1'],
   anchor='Ability to describe data lineage.', note='The paper: "Points (2) (data lineage) and (5) (input data) are already supported by DCAT-AP".'),
 A('JRC-3.1', 'JRC-3', 'Give potential data consumers information on how to use the data (usage notes).', loc=J + '"Metadata elements relevant for scientific data", item 3',
   anchor='Ability to give potential data consumers information on how to use the data'),
 A('JRC-4.1', 'JRC-4', 'Link a dataset to scientific publications about it.', loc=J + '"Metadata elements relevant for scientific data", item 4',
   anchor='Ability to link to scientific publications about a dataset.'),
 A('JRC-5.1', 'JRC-5', 'Link a dataset to its input data (the data used to create it).', loc=J + '"Metadata elements relevant for scientific data", item 5',
   anchor='Ability to link to input data (i.e., data used to create a dataset).',
   note='The paper: "Points (2) (data lineage) and (5) (input data) are already supported by DCAT-AP".'),
 A('JRC-6.1', 'JRC-6', 'Use persistent identifiers for dataset authors and input data, so datasets can be reliably filtered and linked by them.',
   pr45=['JC-008'], v2=['JRC-6'], status='requirement', modality='explicit_requirement', loc=J + '"Metadata elements relevant for scientific data"',
   anchor='a key requirement is the ability to rely on persistent identifiers',
   note='Context: filtering datasets by authors or input data; JRC datasets already have persistent URIs and ORCIDs are used for authors.'),
 A('JRC-6.2', 'JRC-6', 'Encode identifiers as HTTP URIs wherever possible.', pr45=['JC-011'], v2=['JRC-6'], modality='recommendation',
   loc=J + '"Data citation", "Identifiers"', anchor='it would be desirable to promote the encoding of identifiers as HTTP URIs, whenever possible'),
 A('JRC-6.3', 'JRC-6', 'Distinguish primary identifiers (e.g. DOIs) from alternative ones.', pr45=['JC-010'], v2=['JRC-6'],
   status='requirement', rel='restates_base', modality='explicit_requirement', loc=J + '"Data citation", "Identifiers"',
   anchor='DCAT-AP already provides a mechanism to model primary and secondary identifiers, as well as the identifier type.',
   note='Met by the base: dct:identifier for primary and adms:identifier for alternative identifiers.'),
 A('JRC-6.4', 'JRC-6', 'Use a DOI as the dataset identifier when generating DataCite citations.', pr45=['JC-009'], modality='datacite_condition',
   loc=J + '"Data citation", "Identifiers"', overlaps=['JRC-6.3'], anchor='DataCite requires the dataset identifier to be a DOI.',
   note='A DataCite rule the paper reports for citation generation.'),
 A('JRC-6.5', 'JRC-6', 'Qualify each identifier with its scheme or type.', pr45=['JC-001'], status='requirement', rel='restates_base', modality='issue',
   loc=J + '"Data citation", "Identifiers"', anchor='DCAT-AP already provides a mechanism to model primary and secondary identifiers, as well as the identifier type.',
   note='Met by the base (adms:Identifier carries the scheme); the paper questions this modelling because such identifiers are of little use for linking.'),
 A('JRC-7.1', 'JRC-7', 'Use a minimal, consistent set of unambiguous agent roles beyond publisher and contact point.', pr45=['JC-002'], v2=['JRC-7'],
   modality='issue', overlaps=['JRC-1.1'],
   anchor='identifying a minimal set of unambiguous roles and promote their use would be preferable'),
 A('JRC-8.1', 'JRC-8', 'Indicate when a distribution points to a service or API rather than directly to the data.', pr45=['JC-003'], v2=['JRC-8'],
   modality='explicit_requirement', rel='extends_base', note='dct:type, not a distribution property in DCAT-AP 1.1, used on the distribution.', anchor='Denote distributions as pointing to a service / API, and not directly to the actual data.'),
 A('JRC-8.2', 'JRC-8', 'Describe the API or service interface, with the query parameters needed to select data, so software agents can use it directly.',
   pr45=['JC-004'], v2=['JRC-8'], modality='explicit_requirement',
   anchor='Provide a description of the API / service interface, along with the relevant query parameters',
   note='Claude v2 had only "which service standard it follows"; completed from PR #45.'),
 A('JRC-9.1', 'JRC-9', 'Describe provenance in enough detail to support reproducibility and to track how data are used.', pr45=['JC-005'],
   v2=['JRC-9'], modality='under_investigation', overlaps=['JRC-2.1'],
   anchor='The objectives include (a) data reproducibility and (b) ability to track the usage of data'),
 A('JRC-10.1', 'JRC-10', 'Describe data quality assessments of a dataset.', pr45=['JC-006'], v2=['JRC-10'], modality='under_investigation',
   loc=J + '"Additional requirements" (modelling and using data quality assessments)'),
 A('JRC-10.2', 'JRC-10', "Include users' feedback on the data as quality information.", pr45=['JC-006'], v2=['JRC-10'], modality='under_investigation',
   anchor="it potentially includes the integration of users' feedback as part of the meta/data management life-cycle."),
 A('JRC-11.1', 'JRC-11', 'Publish metadata on the Web so that the data are visible and discoverable through search engines.', pr45=['JC-007'],
   v2=['JRC-11'], modality='under_investigation',
   anchor='increasing visibility and discoverability of JRC data on the Web, also via search engines.'),
]
