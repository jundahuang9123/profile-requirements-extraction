#!/usr/bin/env python3
"""Build DCAT/DCAT-AP registries from locally supplied, pinned official files.

This script performs no downloads and never follows RDF imports. Supply a local
checkout (releases/<version>/) and dated W3C specs (w3c/dcat-<major>.html) with
--input-dir. Every input is checked against the pinned release checksum.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from rdflib import Graph, Literal, RDF, RDFS, URIRef
from rdflib.namespace import SH, SKOS

PINNED_COMMIT = '4470b8ea907b7eb9ec55ab22befd1ecd2210ff32'
BUILDER_VERSION = 'rq1-base-registry-v1'
SUPPORTED_PROFILES = ('dcat-ap-2.0.1', 'dcat-ap-2.1.1', 'dcat-ap-3.0.0', 'dcat-ap-3.0.1',
                      'dcat-2.0.0', 'dcat-3.0.0')
W3C_SOURCES = {
    '2': 'https://www.w3.org/TR/2020/REC-vocab-dcat-2-20200204/',
    '3': 'https://www.w3.org/TR/2024/REC-vocab-dcat-3-20240822/',
}
PINNED_HASHES = {
    'releases/3.0.0/index.html': 'faf607042f641ed3c022fc8cb5bb36d450991eca9202107d3aa49dc78a9bbff2',
    'releases/3.0.0/shacl/dcat-ap-SHACL.ttl': '92f76609d78d257123e75bc6b7155df5cc0a63f14c29fbc12b0ac95c56af2059',
    'releases/3.0.1/index.html': 'cfa6c5e3bd05bfa731e6a8b4848062d9dfb56303ed40b12efa467847a9171e12',
    'releases/3.0.1/shacl/dcat-ap-SHACL.ttl': '990d3e42721de6a4be8cc338a7171559f195e62dea89c0b56531356b78cc026f',
    'releases/3.0.1/shacl/ranges.ttl': 'a6eed0fae8d0f5ca977fe2098ca12081ac60b0efe1ddce802d5c08e49505ebcc',
    'w3c/dcat-2.html': '6f3904e1be0ef21684c3c1e5871a361a631648cf72bd06082a24084b400b54c6',
    'w3c/dcat-3.html': '068b43f7814525ea784b7d565ada8de2b4538f5377517c4f0ec9b162a34dedfb',
    'releases/2.0.1/dcat-ap_2.0.1_shacl_shapes.ttl': '864501811f0e599500ba02fd2f15027a6b82728343af3bd8a273d141a6a089da',
    'releases/2.0.1/DCAT_AP_2.0.1.docx': '6d1e0db4eb1890fa373436bdc0da3f578c5b58f6cf4b5e447ce45f958a6e8d3f',
    'releases/2.0.1/dcat-ap_2.0.1_shacl_mdr-vocabularies.shape.ttl': '10d9194cf8db767ab0d0e99ae0b5c4f21542f0aa2a2066ff8e75a3f8cdda645d',
    'releases/2.0.1/dcat-ap_2.0.1.rdf': 'd939611b553dde9b080ccdd33941c2161ddf47bd68ec09039d60145de8a8642a',
    'releases/2.1.1/dcat-ap_2.1.1_shacl_shapes.ttl': '467ace005196e261b9299422e921aba079c279a9e914e3a2d499e048cbc7cd0b',
    'releases/2.1.1/dcat-ap_2.1.1_shacl_shapes_recommended.ttl': '1b46e232e79d1d7875146b6f9b3722b0a53131b6810387bd653175e865f71742',
    'releases/2.1.1/dcat-ap_2.1.1_shacl_range.ttl': '36f01df2b8cd0f51bda7c12a64e16868430caebb39dabd998071795f99bfe353',
    'releases/2.1.1/dcat-ap_2.1.1_shacl_mdr-vocabularies.shape.ttl': '510cd30b2dd410cf5c2ea11b3c9e523ef07c2bf19036d48cb2d2ca64a6dc9a3b',
    'releases/2.1.1/dcat-ap_2.1.1.rdf': '1213214797a8a8c50a7e5240b470fe1cd6f97746b3698078e6bdaebbd4a69e61',
}
PREFIXES = {
    'dcat': 'http://www.w3.org/ns/dcat#',
    'dct': 'http://purl.org/dc/terms/',
    'dc': 'http://purl.org/dc/elements/1.1/',
    'foaf': 'http://xmlns.com/foaf/0.1/',
    'skos': 'http://www.w3.org/2004/02/skos/core#',
    'adms': 'http://www.w3.org/ns/adms#',
    'vcard': 'http://www.w3.org/2006/vcard/ns#',
    'spdx': 'http://spdx.org/rdf/terms#',
    'dcatap': 'http://data.europa.eu/r5r/',
    'locn': 'http://www.w3.org/ns/locn#',
    'owl': 'http://www.w3.org/2002/07/owl#',
    'prov': 'http://www.w3.org/ns/prov#',
    'odrl': 'http://www.w3.org/ns/odrl/2/',
    'time': 'http://www.w3.org/2006/time#',
    'rdfs': str(RDFS),
    'rdf': str(RDF),
    'dctype': 'http://purl.org/dc/dcmitype/',
    'dqv': 'http://www.w3.org/ns/dqv#',
    'xsd': 'http://www.w3.org/2001/XMLSchema#',
}
TYPO_URIS = {
    'http://data.europa.eu/r5ravailability': PREFIXES['dcatap'] + 'availability',
    PREFIXES['dct'] + 'licence': PREFIXES['dct'] + 'license',
}
SYNONYMS = {
    'dcat:endpointURL': ['endpoint url', 'endpoint address', 'endpoint uri', 'root location'],
    'dcat:endpointDescription': ['endpoint description', 'api description', 'description of the api or interface'],
    'dcat:servesDataset': ['serves dataset', 'served datasets', 'datasets it serves'],
    'dcat:accessService': ['access service'],
    'dcat:accessURL': ['access url'],
    'dcat:downloadURL': ['download url'],
    'dcat:mediaType': ['media type', 'mime type'],
    'adms:versionNotes': ['version notes'],
    'dct:spatial': ['spatial coverage', 'geographic coverage', 'geographic extent', 'geographical area'],
    'dct:temporal': ['temporal coverage', 'time period'],
    'dcat:contactPoint': ['contact', 'contact point', 'point of contact'],
    'dcat:keyword': ['keyword', 'tag'],
    'dcat:theme': ['theme'],
    'dcat:themeTaxonomy': ['theme taxonomy'],
    'dct:license': ['licence', 'license'],
    'dct:accessRights': ['access rights', 'access restrictions'],
    'dct:conformsTo': ['conforms to', 'conformance'],
    'foaf:page': ['documentation'],
    'dct:accrualPeriodicity': ['update frequency', 'accrual periodicity'],
    'dct:issued': ['release date', 'publication date', 'issued'],
    'dct:modified': ['modification date', 'last modified', 'last updated'],
    'dcat:byteSize': ['byte size', 'file size'],
    'spdx:checksum': ['checksum'],
    'dcatap:availability': ['availability'],
    'adms:status': ['status'],
    'dct:provenance': ['provenance', 'lineage'],
    'dct:identifier': ['identifier'],
    'dct:language': ['language'],
    'owl:versionInfo': ['version'],
    'dcat:distribution': ['distribution'],
    'dct:format': ['format', 'file format'],
    'dct:title': ['title'],
    'dct:description': ['description'],
    'foaf:name': ['name'],
}
CLASS_NAMES = {
    'catalogue': 'dcat:Catalog', 'catalogue record': 'dcat:CatalogRecord',
    'data service': 'dcat:DataService', 'dataset': 'dcat:Dataset',
    'distribution': 'dcat:Distribution', 'agent': 'foaf:Agent',
    'category scheme': 'skos:ConceptScheme', 'category': 'skos:Concept',
    'checksum': 'spdx:Checksum', 'identifier': 'adms:Identifier',
    'licence document': 'dct:LicenseDocument', 'location': 'dct:Location',
    'period of time': 'dct:PeriodOfTime', 'relationship': 'dcat:Relationship',
}


def compact(value: Any) -> str:
    text = str(value)
    text = TYPO_URIS.get(text, text)
    if text.startswith('dcterms:'):
        text = 'dct:' + text.split(':', 1)[1]
    if text == 'dct:licence':
        text = 'dct:license'
    for prefix, namespace in PREFIXES.items():
        if text.startswith(namespace):
            return prefix + ':' + text[len(namespace):]
    return text


def scalar_or_list(values: set[str]) -> str | list[str] | None:
    ordered = sorted(values)
    return ordered[0] if len(ordered) == 1 else ordered or None


def shape_properties(graph: Graph):
    for shape, class_uri in graph.subject_objects(SH.targetClass):
        for prop in graph.objects(shape, SH.property):
            path = graph.value(prop, SH.path)
            if isinstance(path, URIRef):
                yield compact(class_uri), compact(path), prop


def range_values(graph: Graph, node, seen=None) -> set[str]:
    seen = set() if seen is None else seen
    if node in seen:
        return set()
    seen.add(node)
    values = {compact(x) for p in (SH['class'], SH.datatype) for x in graph.objects(node, p)}
    for child in graph.objects(node, SH.node):
        values |= range_values(graph, child, seen)
    for head in graph.objects(node, SH['or']):
        for child in graph.items(head):
            values |= range_values(graph, child, seen)
    if not values:
        kinds = set(graph.objects(node, SH.nodeKind))
        if SH.Literal in kinds:
            values.add('rdfs:Literal')
        elif SH.IRI in kinds or SH.BlankNodeOrIRI in kinds:
            values.add('rdfs:Resource')
    return values


def vocabulary_values(graph: Graph, node, seen=None) -> set[str]:
    """Read value scheme restrictions, without treating nested agent types as schemes."""
    seen = set() if seen is None else seen
    if node in seen:
        return set()
    seen.add(node)
    values = {str(x) for x in graph.objects(node, SH.hasValue) if isinstance(x, URIRef)}
    for child in graph.objects(node, SH.node):
        values |= vocabulary_values(graph, child, seen)
    for head in graph.objects(node, SH['or']):
        for child in graph.items(head):
            values |= vocabulary_values(graph, child, seen)
    for prop in graph.objects(node, SH.property):
        if graph.value(prop, SH.path) == SKOS.inScheme:
            values |= vocabulary_values(graph, prop, seen)
    return values


def parse_docx_properties(path: Path) -> dict[str, dict[str, dict]]:
    """Read section headings and their property tables in document order."""
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    document = Document(path)
    result: dict[str, dict[str, dict]] = {}
    current = None
    seen_sections = set()
    for block in document.iter_inner_content():
        if isinstance(block, Paragraph):
            heading = ' '.join(block.text.split())
            match = re.fullmatch(r'(Mandatory|Recommended|Optional) propert(?:y|ies)\s+for\s+(.+)', heading, re.I)
            if match:
                name = match[2].strip().lower()
                if name not in CLASS_NAMES:
                    raise ValueError(f'Unrecognised DOCX class section: {name}')
                current = CLASS_NAMES[name], match[1].lower()
            elif block.style.name.startswith('Heading'):
                current = None
        elif isinstance(block, Table) and current:
            header = [cell.text.strip().lower() for cell in block.rows[0].cells]
            if 'uri' not in header or 'property' not in header:
                raise ValueError(f'Missing property table after DOCX section {current}')
            uri_col, label_col = header.index('uri'), header.index('property')
            range_col = header.index('range') if 'range' in header else None
            count = 0
            for row in block.rows[1:]:
                # Some tables end in a merged explanatory row; it is not a property.
                raw = row.cells[uri_col].text.strip()
                match = re.match(r'^([A-Za-z][A-Za-z0-9_-]*\s*:\s*[A-Za-z][A-Za-z0-9_-]*)', raw)
                if not match:
                    continue
                prop = compact(re.sub(r'\s+', '', match[1]))
                ranges = set()
                if range_col is not None:
                    range_text = row.cells[range_col].text
                    ranges = {compact(x) for x in re.findall(r'\b[A-Za-z][A-Za-z0-9_-]*:[A-Za-z][A-Za-z0-9_-]*', range_text)}
                    if 'dcat:Dataservice' in ranges:
                        ranges.remove('dcat:Dataservice')
                        ranges.add('dcat:DataService')
                result.setdefault(current[0], {})[prop] = {
                    'obligation': current[1],
                    'range': scalar_or_list(ranges),
                    'label': ' '.join(row.cells[label_col].text.split()),
                }
                count += 1
            if not count:
                raise ValueError(f'Empty DOCX property table for {current}')
            seen_sections.add(current)
            current = None
    essential = {'dcat:Catalog', 'dcat:CatalogRecord', 'dcat:DataService', 'dcat:Dataset', 'dcat:Distribution', 'foaf:Agent'}
    if not essential.issubset(result):
        raise ValueError('DOCX properties section is incomplete: ' + ', '.join(sorted(essential - result.keys())))
    for cls in essential:
        if (cls, 'recommended') not in seen_sections:
            raise ValueError(f'DOCX recommended section missing for {cls}')
    return result


def property_labels(class_id: str, property_id: str, graphs: list[Graph], docx_label=None) -> list[str]:
    labels = set()
    raw_uris = [URIRef(ns + property_id.split(':', 1)[1]) for prefix, ns in PREFIXES.items() if property_id.startswith(prefix + ':')]
    raw_uris += [URIRef(typo) for typo, normalized in TYPO_URIS.items() if compact(normalized) == property_id]
    for graph in graphs:
        for uri in raw_uris:
            for label in graph.objects(uri, RDFS.label):
                if isinstance(label, Literal) and label.language in (None, 'en'):
                    labels.add(str(label).strip())
        for cls, prop, shape in shape_properties(graph):
            if cls == class_id and prop == property_id:
                for name in graph.objects(shape, SH.name):
                    if isinstance(name, Literal) and name.language in (None, 'en'):
                        labels.add(str(name).strip())
    if docx_label:
        labels.add(docx_label)
    # Official RDF labels sometimes include the class, e.g. "Dataset - publisher".
    for label in list(labels):
        if ' - ' in label:
            labels.add(label.split(' - ', 1)[1].strip())
    labels.add(property_id.rsplit(':', 1)[-1])
    synonyms = SYNONYMS.get(property_id, [])
    if property_id == 'adms:status' and class_id not in ('dcat:Distribution', 'dcat:CatalogRecord'):
        synonyms = []
    if property_id == 'dcat:distribution' and class_id != 'dcat:Dataset':
        synonyms = []
    if property_id == 'foaf:name' and class_id != 'foaf:Agent':
        synonyms = []
    labels.update(synonyms)
    return sorted(label for label in labels if label)


def registry_classes(shapes: Graph, *, recommended: Graph | None = None, ranges: Graph | None = None,
                     vocabularies: Graph | None = None, labels: Graph | None = None,
                     docx_properties: dict | None = None) -> dict[str, dict]:
    result: dict[str, dict] = {}
    label_graphs = [g for g in (shapes, recommended, ranges, vocabularies, labels) if g is not None]
    recommended_set = {(c, p) for c, p, _ in shape_properties(recommended)} if recommended is not None else set()
    if docx_properties is not None:
        recommended_set = {(c, p) for c, props in docx_properties.items() for p, info in props.items() if info['obligation'] == 'recommended'}
    for cls, prop, shape in shape_properties(shapes):
        minimum = shapes.value(shape, SH.minCount)
        maximum = shapes.value(shape, SH.maxCount)
        obligation = 'mandatory' if minimum is not None and int(minimum) >= 1 else 'recommended' if (cls, prop) in recommended_set else 'optional'
        docx_info = (docx_properties or {}).get(cls, {}).get(prop, {})
        range_info = scalar_or_list(range_values(shapes, shape))
        if range_info is None:
            range_info = docx_info.get('range')
        result.setdefault(cls, {})[prop] = {
            'obligation': obligation, 'max': int(maximum) if maximum is not None else None,
            'range': range_info, 'vocabulary': None,
            'labels': property_labels(cls, prop, label_graphs, docx_info.get('label')),
        }
    # Supplemental files refine existing members. They do not add class/property
    # memberships (important when an upstream shape has a mistaken targetClass).
    if ranges is not None:
        for cls, prop, shape in shape_properties(ranges):
            if prop in result.get(cls, {}):
                supplied = scalar_or_list(range_values(ranges, shape))
                if supplied is not None:
                    result[cls][prop]['range'] = supplied
    if vocabularies is not None:
        for cls, prop, shape in shape_properties(vocabularies):
            if prop in result.get(cls, {}):
                result[cls][prop]['vocabulary'] = scalar_or_list(vocabulary_values(vocabularies, shape))
    return {cls: dict(sorted(props.items())) for cls, props in sorted(result.items())}


def read_pinned(input_dir: Path, relative: str, used: dict) -> Path:
    path = input_dir / relative
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != PINNED_HASHES[relative]:
        raise ValueError(f'Pinned source checksum mismatch: {relative}')
    used[relative] = digest
    return path


def _html(path: Path):
    from lxml import html
    return html.parse(str(path), parser=html.HTMLParser(no_network=True))


def _terms(element) -> set[str]:
    """Read explicit CURIEs in a definition cell, never inferred usage prose."""
    return {compact(term) for term in re.findall(r'\b[A-Za-z][\w-]*:[A-Za-z][\w-]*', element.text_content())
            if term.split(':', 1)[0] in {*PREFIXES, 'dcterms'}}


def build_dcat_profile(profile_id: str, input_dir: Path) -> dict:
    version = profile_id.split('-')[1].split('.')[0]
    used: dict[str, str] = {}
    document = _html(read_pinned(input_dir, f'w3c/dcat-{version}.html', used))
    classes, parents = {}, {}
    for section in document.xpath('//section[starts-with(@id, "Class:")]'):
        tables = section.xpath('./table')
        if not tables:
            continue
        cls = None
        inherited = set()
        for row in tables[0].xpath('.//tr'):
            cells = row.xpath('./th | ./td')
            if len(cells) < 2:
                continue
            heading = cells[0].text_content().strip().rstrip(':').casefold()
            if heading == 'rdf class':
                terms = _terms(cells[1])
                if len(terms) != 1:
                    raise ValueError('Ambiguous W3C class definition.')
                cls = next(iter(terms))
            elif heading == 'sub-class of':
                inherited |= _terms(cells[1])
        if cls is None:
            continue
        properties = {}
        for prop_section in section.xpath('./section[starts-with(@id, "Property:")]'):
            prop, ranges = None, set()
            for row in prop_section.xpath('./table//tr'):
                cells = row.xpath('./th | ./td')
                if len(cells) < 2:
                    continue
                heading = cells[0].text_content().strip().rstrip(':').casefold()
                if heading == 'rdf property':
                    terms = _terms(cells[1])
                    if len(terms) != 1:
                        raise ValueError('Ambiguous W3C property definition.')
                    prop = next(iter(terms))
                elif heading == 'range':
                    ranges |= _terms(cells[1])
            if prop:
                properties[prop] = {'obligation': None, 'max': None, 'range': scalar_or_list(ranges),
                                    'vocabulary': None, 'labels': property_labels(cls, prop, [])}
        classes[cls], parents[cls] = properties, inherited
    def expand(cls, seen):
        if cls in seen:
            raise ValueError('Cycle in W3C class inheritance.')
        result = {}
        for parent in sorted(parents[cls] & classes.keys()):
            result.update(expand(parent, seen | {cls}))
        return {**result, **classes[cls]}
    result = {cls: dict(sorted(expand(cls, set()).items())) for cls in sorted(classes)}
    essential = {'dcat:Catalog', 'dcat:CatalogRecord', 'dcat:Dataset', 'dcat:DataService', 'dcat:Distribution'}
    if not essential <= result.keys() or not result['dcat:Dataset'].get('dct:title'):
        raise ValueError('Incomplete W3C vocabulary tables.')
    return {'id': profile_id, 'version': version, 'family': 'DCAT',
            'label': f'W3C DCAT {version}', 'registry_policy': 'rq1-base-vocabulary-v1',
            'source': {'url': W3C_SOURCES[version], 'files': used},
            'recommended_source': 'not_applicable',
            'description': 'Vocabulary membership and ranges. No DCAT-AP mandatory/recommended obligations.',
            'classes': result}


def build_ap3_profile(profile_id: str, input_dir: Path) -> dict:
    version = profile_id.removeprefix('dcat-ap-')
    used: dict[str, str] = {}
    document = _html(read_pinned(input_dir, f'releases/{version}/index.html', used))
    shapes = Graph().parse(read_pinned(input_dir, f'releases/{version}/shacl/dcat-ap-SHACL.ttl', used), format='turtle')
    graphs = [shapes]
    if version == '3.0.1':
        graphs.append(Graph().parse(read_pinned(input_dir, f'releases/{version}/shacl/ranges.ttl', used), format='turtle'))
    # 3.x publishes separate shapes for each constraint on the same property.
    # Aggregate them; last-shape-wins would lose mandatory counts or ranges.
    nodes: dict[tuple[str, str], list[tuple[Graph, Any]]] = {}
    for graph in graphs:
        for cls, prop, node in shape_properties(graph):
            nodes.setdefault((cls, prop), []).append((graph, node))
    result, class_anchors, property_anchors = {}, {}, {}
    for row in document.xpath('//tr'):
        cells = row.xpath('./td')
        if len(cells) != 5:
            continue
        obligation = cells[2].text_content().strip().lower()
        if obligation not in {'mandatory', 'recommended', 'optional'}:
            continue
        cls, prop = compact(cells[1].text_content().strip()), compact(cells[4].text_content().strip())
        links = cells[3].xpath('.//a/@href')
        if len(links) != 1:
            raise ValueError('Missing DCAT-AP 3 conformance-table property link.')
        anchor = links[0].lstrip('#')
        class_anchors[anchor.split('.', 1)[0]] = cls
        property_anchors[anchor] = prop
        details = document.xpath('//*[@id=$id]', id=links[0].lstrip('#'))
        if len(details) != 1:
            raise ValueError('Missing DCAT-AP 3 property definition.')
        definition = details[0].xpath('./td')
        cardinality = definition[2].text_content().strip()
        match = re.fullmatch(r'(\d+)(?:\.\.(\d+|\*|n))?', cardinality)
        if not match:
            raise ValueError(f'Unrecognised cardinality {cardinality} for {cls}/{prop}.')
        minimum = int(match[1])
        maximum = match[2] if match[2] is not None else match[1]
        maximum = '*' if maximum == 'n' else maximum
        if (minimum >= 1) != (obligation == 'mandatory'):
            raise ValueError(f'Conformance-table/cardinality disagreement for {cls}/{prop}.')
        ranges, fallback_ranges, vocabularies = set(), set(), set()
        for graph, node in nodes.get((cls, prop), []):
            values = range_values(graph, node)
            if any(graph.value(node, predicate) is not None for predicate in
                   (SH['class'], SH.datatype, SH.node, SH['or'])):
                ranges |= values
            else:
                fallback_ranges |= values
            vocabularies |= vocabulary_values(graph, node)
            shape_min, shape_max = graph.value(node, SH.minCount), graph.value(node, SH.maxCount)
            if shape_min is not None and int(shape_min) > minimum:
                raise ValueError(f'SHACL/specification minimum disagreement for {cls}/{prop}.')
            if shape_max is not None and maximum != '*' and int(shape_max) != int(maximum):
                raise ValueError(f'SHACL/specification maximum disagreement for {cls}/{prop}.')
        result.setdefault(cls, {})[prop] = {
            'obligation': obligation, 'max': None if maximum == '*' else int(maximum),
            'range': scalar_or_list(ranges or fallback_ranges), 'vocabulary': scalar_or_list(vocabularies),
            'labels': property_labels(cls, prop, graphs, cells[3].text_content().strip())}
    # The HTML, unlike the generated shapes, describes the vocabulary schemes
    # and distinguishes compulsory use from recommendations/conditional use.
    for table in document.xpath('//table[@id="table-cv"]'):
        headings = table.xpath('preceding-sibling::*[self::h4 or self::p][1]')
        heading = headings[0].text_content() if headings else ''
        qualification = ('must' if 'MUST' in heading else 'at_least_one' if 'AT LEAST' in heading
                         else 'recommended' if 'RECOMMENDED' in heading else 'may' if 'MAY' in heading else None)
        if qualification is None:
            raise ValueError('Missing vocabulary-table qualification.')
        for row in table.xpath('.//tr'):
            cells = row.xpath('./td')
            if len(cells) != 4:
                continue
            terms = _terms(cells[0])
            anchors = cells[0].xpath('.//a/@href')
            prop = next(iter(terms)) if len(terms) == 1 else property_anchors.get(anchors[0].lstrip('#')) if len(anchors) == 1 else None
            schemes = set(cells[2].xpath('.//a/@href'))
            if not prop or not schemes:
                raise ValueError('Unresolved controlled-vocabulary table entry.')
            for anchor in cells[1].xpath('.//a/@href'):
                cls = class_anchors.get(anchor.lstrip('#'))
                if prop not in result.get(cls, {}):
                    continue  # A prose table cannot add unlisted base properties.
                entry = result[cls][prop]
                usage_note = ' '.join(cells[3].text_content().split())
                effective = 'conditional' if re.search(r'\bin case\b|\bif a particular\b', usage_note, re.I) else qualification
                entry['vocabulary_guidance'] = {'schemes': sorted(schemes), 'qualification': effective,
                                               'usage_note': usage_note}
                if effective in {'must', 'at_least_one'}:
                    entry['vocabulary'] = scalar_or_list(schemes)
    essential = {'dcat:Catalog', 'dcat:CatalogRecord', 'dcat:Dataset', 'dcat:DatasetSeries', 'dcat:DataService', 'dcat:Distribution'}
    if not essential <= result.keys():
        raise ValueError('Incomplete DCAT-AP 3 conformance table.')
    return {'id': profile_id, 'version': version, 'family': 'DCAT-AP', 'label': f'DCAT-AP {version}',
            'registry_policy': 'rq1-base-registry-v2',
            'source': {'repo': 'SEMICeu/DCAT-AP', 'commit': PINNED_COMMIT, 'files': dict(sorted(used.items()))},
            'recommended_source': f'{version}-html-conformance-table',
            'classes': {cls: dict(sorted(props.items())) for cls, props in sorted(result.items())}}


def build_profile(profile_id: str, input_dir: Path, *, allow_recommended_fallback=False) -> dict:
    if profile_id not in SUPPORTED_PROFILES:
        raise ValueError(f'Unsupported base profile {profile_id}')
    if profile_id.startswith('dcat-ap-3.'):
        return build_ap3_profile(profile_id, input_dir)
    if profile_id.startswith('dcat-') and not profile_id.startswith('dcat-ap-'):
        return build_dcat_profile(profile_id, input_dir)
    version = profile_id.removeprefix('dcat-ap-')
    used: dict[str, str] = {}
    prefix = f'releases/{version}/dcat-ap_{version}'
    def graph(relative):
        path = read_pinned(input_dir, relative, used)
        # A local file with RDF imports remains a local graph; imports are not fetched.
        return Graph().parse(path, format='xml' if path.suffix == '.rdf' else 'turtle')
    shapes = graph(prefix + '_shacl_shapes.ttl')
    vocabularies = graph(prefix + '_shacl_mdr-vocabularies.shape.ttl')
    labels = graph(prefix + '.rdf')
    ranges = recommended = docx_properties = None
    fallback_note = None
    if version == '2.1.1':
        recommended = graph(prefix + '_shacl_shapes_recommended.ttl')
        ranges = graph(prefix + '_shacl_range.ttl')
        recommended_source = '2.1.1-shacl'
    else:
        path = read_pinned(input_dir, 'releases/2.0.1/DCAT_AP_2.0.1.docx', used)
        try:
            docx_properties = parse_docx_properties(path)
            recommended_source = '2.0.1-docx'
        except (ImportError, ValueError, KeyError) as error:
            if not allow_recommended_fallback:
                raise ValueError('DOCX recommendation parse failed; no fallback taken. ' + str(error)) from error
            recommended = graph('releases/2.1.1/dcat-ap_2.1.1_shacl_shapes_recommended.ttl')
            recommended_source = '2.1.1'
            fallback_note = f'2.0.1 DOCX recommended parse failed: {type(error).__name__}: {error}'
    result = {
        'id': profile_id, 'version': version, 'registry_policy': BUILDER_VERSION,
        'source': {'repo': 'SEMICeu/DCAT-AP', 'commit': PINNED_COMMIT, 'files': dict(sorted(used.items()))},
        'recommended_source': recommended_source,
        'normalizations': {'http://data.europa.eu/r5ravailability': 'dcatap:availability', 'dct:licence': 'dct:license'},
        'classes': registry_classes(shapes, recommended=recommended, ranges=ranges, vocabularies=vocabularies, labels=labels, docx_properties=docx_properties),
    }
    if fallback_note:
        result['fallback_note'] = fallback_note
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', type=Path, required=True, help='Local pinned checkout containing releases/<version>/')
    parser.add_argument('--profile', choices=SUPPORTED_PROFILES, action='append')
    parser.add_argument('--output-dir', type=Path, default=Path(__file__).resolve().parents[1] / 'requirement-reuse-service/config/base_profiles')
    parser.add_argument('--allow-recommended-fallback', action='store_true', help='Explicitly permit a documented 2.1.1 recommended-set fallback if the 2.0.1 DOCX parse fails')
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for profile_id in args.profile or SUPPORTED_PROFILES:
        profile = build_profile(profile_id, args.input_dir, allow_recommended_fallback=args.allow_recommended_fallback)
        output = args.output_dir / (profile_id + '.json')
        output.write_text(json.dumps(profile, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        count = sum(len(properties) for properties in profile['classes'].values())
        print(f'{output.name}: {len(profile["classes"])} classes, {count} properties; recommended_source={profile["recommended_source"]}; sha256={hashlib.sha256(output.read_bytes()).hexdigest()}')
        if 'fallback_note' in profile:
            print('FALLBACK: ' + profile['fallback_note'])


if __name__ == '__main__':
    main()
