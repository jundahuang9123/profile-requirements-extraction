"""Addressable evidence resolved from immutable source bytes, never model summaries."""
from __future__ import annotations

import base64
import io
import json
import re
import uuid
import zipfile
from importlib.metadata import version as package_version
from typing import Any
from html.parser import HTMLParser

from .models import EvidenceUnit, SourceArtifact, SourceRequest
from .storage import Store, canonical, digest, now, uid

PARSER_VERSION = 'rq1-adapters-v2.4'
SUPPORTED_PARSER_VERSIONS = {'rq1-adapters-v2.2', 'rq1-adapters-v2.3', PARSER_VERSION}
MAX_BYTES = 20_000_000
MAX_UNITS = 10000
PDF_PASSAGE_MAX_CHARS = 2400


def html_representation(raw: bytes) -> str:
    """Deterministic body-text view regenerated from retained original HTML bytes."""
    class BodyText(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.parts, self.hidden = [], []

        def handle_starttag(self, tag, attrs):
            if tag in {'head', 'script', 'style', 'template'}:
                self.hidden.append(tag)
            if self.hidden:
                return
            if tag in {'p', 'div', 'section', 'article', 'li', 'tr', 'dt', 'dd', 'pre',
                       'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'br'}:
                self.parts.append('\n')
            if tag in {'th', 'td'}:
                self.parts.append(' | ')

        def handle_endtag(self, tag):
            if self.hidden:
                if tag == self.hidden[-1]:
                    self.hidden.pop()
                return
            if tag in {'p', 'div', 'section', 'article', 'li', 'tr', 'dt', 'dd', 'pre',
                       'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}:
                self.parts.append('\n')

        def handle_data(self, text):
            if not self.hidden:
                self.parts.append(text)

    parser = BodyText()
    parser.feed(raw.decode('utf-8-sig'))
    parser.close()
    return '\n'.join(line for part in ''.join(parser.parts).split('\n')
                     if (line := ' '.join(part.split())))


def pdf_passage_spans(page: str):
    """Yield bounded, contiguous spans without rewriting extracted PDF text.

    PDF physical lines are layout artifacts, often splitting sentences and even
    words. Keep adjacent lines together, but never cross an explicit blank-line
    block. Prefer sentence boundaries near the size limit, then a line/word
    boundary. An unusually long token is split only to enforce the hard cap.
    """
    block_start = 0
    boundaries = [match.start() for match in re.finditer(r'\n[ \t]*\n', page)] + [len(page)]
    for block_end in boundaries:
        start = block_start
        while start < block_end:
            while start < block_end and page[start].isspace():
                start += 1
            if start >= block_end:
                break
            end = min(start + PDF_PASSAGE_MAX_CHARS, block_end)
            if end < block_end:
                # Avoid tiny passages merely because an early sentence ended.
                lower = start + PDF_PASSAGE_MAX_CHARS // 2
                sentences = list(re.finditer(r'[.!?][\"\u201d\u2019\)\]]*(?=\s|$)', page[lower:end]))
                if sentences:
                    end = lower + sentences[-1].end()
                else:
                    newline = page.rfind('\n', lower, end)
                    if newline >= lower:
                        end = newline
                    else:
                        whitespace = list(re.finditer(r'\s+', page[lower:end]))
                        if whitespace:
                            end = lower + whitespace[-1].start()
            trimmed_end = end
            while trimmed_end > start and page[trimmed_end - 1].isspace():
                trimmed_end -= 1
            if trimmed_end > start:
                yield start, trimmed_end
            start = end
        block_start = block_end


def kind_for(name: str, media_type: str | None, raw: bytes) -> str:
    suffix = name.lower().rsplit('.', 1)[-1]
    if suffix in {'html', 'htm'} or (media_type or '').split(';')[0] == 'text/html':
        return 'html'
    if suffix == 'aasx':
        return 'aasx'
    if suffix == 'pdf':
        return 'pdf'
    if suffix in {'ifc', 'ifcspf'}:
        return 'ifc'
    if suffix in {'ttl', 'trig', 'nq', 'nt', 'rdf', 'jsonld'} or media_type in {'application/ld+json', 'application/rdf+xml'}:
        return 'rdf'
    if suffix in {'json', 'aas'}:
        return 'aas-json'
    if suffix == 'xml':
        return 'aas-xml'
    if suffix in {'txt', 'md', 'csv', 'tsv', 'rst'} or (media_type or '').startswith('text/'):
        return 'text'
    return 'unsupported'


def dependencies(kind: str) -> dict[str, str]:
    packages = {'aas-xml': ['defusedxml'], 'aasx': [], 'aas-json': [],
                'rdf': ['rdflib', 'PyLD'], 'ifc': ['ifcopenshell'], 'pdf': ['pdfplumber', 'pdfminer.six']}.get(kind, [])
    return {package: package_version(package) for package in packages}


def register_source(store: Store, request: SourceRequest, *, parent: SourceArtifact | None = None,
                    entry_path: str | None = None) -> dict:
    artifact = request.artifact
    try:
        raw = base64.b64decode(artifact.content, validate=True) if artifact.content_encoding == 'base64' else artifact.content.encode('utf-8')
    except ValueError as exc:
        raise ValueError('Artifact is not valid base64.') from exc
    if len(raw) > MAX_BYTES:
        raise ValueError('Source exceeds the 20 MB limit.')
    source_id = request.source_id or f'src-{uuid.uuid4().hex}'
    metadata = {'name': artifact.name, 'role': request.source_role, 'authority': request.authority,
                'origin': request.origin_uri, 'media_type': artifact.media_type}
    kind = kind_for(artifact.name, artifact.media_type, raw)
    parser_dependencies = dependencies(kind)
    version_id = uid('srcv', source_id, digest(raw), metadata, PARSER_VERSION, parser_dependencies,
                     parent.source_version_id if parent else None, entry_path)
    try:
        return store.get('source', version_id)
    except KeyError:
        pass
    source = SourceArtifact(source_id=source_id, source_version_id=version_id, name=artifact.name,
                            media_type=artifact.media_type, source_role=request.source_role,
                            authority=request.authority, origin_uri=request.origin_uri,
                            raw_sha256=digest(raw), byte_length=len(raw), raw_base64=base64.b64encode(raw).decode(),
                            artifact_kind=kind, parser_dependencies=parser_dependencies,
                            parent_source_version_id=parent.source_version_id if parent else None,
                            package_entry_path=entry_path,
                            parser_version=PARSER_VERSION, parse_status='parsed', acquired_at=now())
    children: list[str] = []
    if source.artifact_kind == 'aasx':
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as package:
                entries = [entry for entry in package.infolist() if not entry.is_dir()]
                if len(entries) > 1000 or sum(entry.file_size for entry in entries) > MAX_BYTES:
                    raise ValueError('Package expansion exceeds its limits.')
                if len({entry.filename for entry in entries}) != len(entries):
                    raise ValueError('Package contains ambiguous duplicate entry names.')
                for entry in entries:
                    if not entry.filename.lower().endswith(('.json', '.xml', '.aas')):
                        source.diagnostics.append(f'Non-model package entry retained in original bytes: {entry.filename}')
                        continue
                    data = package.read(entry)
                    child_request = request.model_copy(deep=True)
                    child_request.source_id = uid('src', source_id, entry.filename)
                    child_request.artifact = artifact.model_copy(update={'name': entry.filename,
                        'content': base64.b64encode(data).decode(), 'content_encoding': 'base64'})
                    child = register_source(store, child_request, parent=source, entry_path=entry.filename)
                    if child['parse_status'] != 'parsed':
                        raise ValueError(f'Embedded model {entry.filename} failed: {child["diagnostics"]}')
                    children.append(child['source_version_id'])
                if not children:
                    raise ValueError('No supported model entries found in the AASX package.')
        except (ValueError, zipfile.BadZipFile, RuntimeError) as exc:
            source.parse_status = 'failed'
            source.diagnostics.append(str(exc))
        units = []
    else:
        try:
            units, representation, diagnostics = decompose(source)
            source.representation = representation
            source.representation_hash = digest(representation.encode())
            source.diagnostics.extend(diagnostics)
            if source.artifact_kind == 'unsupported':
                source.parse_status = 'unsupported'
            elif not units:
                source.parse_status = 'failed'
                source.diagnostics.append('No addressable evidence extracted; this source cannot enter a run.')
        except Exception as exc:
            units = []
            source.parse_status = 'failed'
            source.diagnostics.append(f'{type(exc).__name__}: {exc}')
    body = source.model_dump(mode='json')
    body['child_source_version_ids'] = children
    store.put('source', source.source_version_id, body)
    for unit in units:
        store.put('evidence', unit.evidence_id, unit.model_dump(mode='json'))
    return body


def source_model(body: dict) -> SourceArtifact:
    return SourceArtifact.model_validate(body)


def decompose(source: SourceArtifact) -> tuple[list[EvidenceUnit], str, list[str]]:
    if source.parser_version not in SUPPORTED_PARSER_VERSIONS:
        raise ValueError('Parser version mismatch; redecompose explicitly.')
    raw = base64.b64decode(source.raw_base64, validate=True)
    if digest(raw) != source.raw_sha256:
        raise ValueError('Original source hash mismatch.')
    units: list[EvidenceUnit] = []
    diagnostics: list[str] = []

    def emit(kind: str, selector: dict, content: str, context: dict | None = None):
        if len(units) >= MAX_UNITS:
            raise ValueError('Evidence decomposition limit exceeded; no partial corpus will be reported as complete.')
        unit = EvidenceUnit(evidence_id=uid('eu', source.source_version_id, selector, source.parser_version, content),
                            source_id=source.source_id, source_version_id=source.source_version_id,
                            kind=kind, selector=selector, content=content, content_hash=digest(content.encode()),
                            structural_context=context or {}, source_claim_kind=source.source_role,
                            parser_version=source.parser_version)
        units.append(unit)

    kind = source.artifact_kind
    if kind == 'unsupported':
        return [], '', ['Unsupported source format; original bytes retained.']
    if kind == 'aasx':
        return [], '', []
    if kind == 'html':
        representation = html_representation(raw)
        rep_hash = digest(representation.encode())
        for start, end in pdf_passage_spans(representation):
            emit('text_span', {'kind': 'text', 'start': start, 'end': end,
                 'representation_hash': rep_hash}, representation[start:end],
                 {'segmentation': 'html-body-passages', 'headings': []})
        diagnostics.append('HTML body text is derived from retained original bytes: entities decoded, '
                           'whitespace normalized, block/table boundaries preserved as text; head, script, '
                           'style and template content excluded. No linked documents fetched. '
                           'CSS visibility, complex table layout and images require human assessment.')
        return units, representation, diagnostics
    if kind in {'text', 'pdf'}:
        if kind == 'pdf':
            import pdfplumber
            with pdfplumber.open(io.BytesIO(raw)) as pdf:
                pages = [page.extract_text() or '' for page in pdf.pages]
                image_only = [i + 1 for i, page in enumerate(pdf.pages)
                              if not pages[i].strip() and page.images]
                empty = [i + 1 for i, text in enumerate(pages) if not text.strip()]
            if not any(pages):
                raise ValueError('PDF has no extractable text; supply an OCR transcript as a separately attributed source.')
            representation = '\n\f\n'.join(pages)
            diagnostics.append('PDF text extraction: visual fidelity and table structure require human assessment; no OCR performed.')
            if image_only:
                diagnostics.append('INCOMPLETE_SOURCE: PDF pages with images but no extracted text: '
                                   + ', '.join(map(str, image_only)) + '. Supply an attributed OCR transcript or assess these pages before a full-corpus run.')
            elif empty:
                diagnostics.append('PDF pages with no extracted text: ' + ', '.join(map(str, empty))
                                   + '; check whether these are blank or contain non-text content.')
        else:
            representation = raw.decode('utf-8-sig')
        rep_hash = digest(representation.encode())
        if kind == 'pdf' and source.parser_version != 'rq1-adapters-v2.2':
            page_offset = 0
            for page_number, page_text in enumerate(pages, start=1):
                for start_in_page, end_in_page in pdf_passage_spans(page_text):
                    start, end = page_offset + start_in_page, page_offset + end_in_page
                    emit('text_span', {'kind': 'text', 'start': start, 'end': end,
                         'representation_hash': rep_hash, 'page': page_number}, representation[start:end],
                         {'line': representation[:start].count('\n') + 1,
                          'line_end': representation[:end].count('\n') + 1,
                          'segmentation': 'page-block-passages', 'headings': []})
                page_offset += len(page_text) + len('\n\f\n')
            diagnostics.append('PDF passages preserve extracted newlines, spaces and hyphenation; '
                               f'each passage stays within one page and is at most {PDF_PASSAGE_MAX_CHARS} characters. '
                               'Page reading order and tables still depend on PDF text extraction.')
            return units, representation, diagnostics
        # Preserve offsets and all nonempty spans, without keyword-based exclusion.
        # Keep v2.2 PDF segmentation available to resolve existing immutable runs.
        heading_context = []
        table_header = None
        for match in re.finditer(r'[^\n\f]+', representation):
            line = match.group()
            if line.lstrip().startswith('#'):
                heading_context = [line.strip()]
            is_table = '|' in line or '\t' in line or (source.name.lower().endswith('.csv') and ',' in line)
            if is_table and table_header is None:
                table_header = line
            if not is_table:
                table_header = None
            for span in re.finditer(r'.+?(?:[.!?](?=\s|$)|$)', line):
                text = span.group()
                start = match.start() + span.start() + len(text) - len(text.lstrip())
                end = match.start() + span.end() - (len(text) - len(text.rstrip()))
                if end <= start:
                    continue
                page = representation[:start].count('\f') + 1 if kind == 'pdf' else None
                emit('table_region' if is_table else 'text_span', {'kind': 'text', 'start': start, 'end': end,
                     'representation_hash': rep_hash, 'page': page}, representation[start:end],
                     {'line': representation[:start].count('\n') + 1,
                      'table_context': line if is_table else None, 'table_header': table_header,
                      'headings': heading_context})
        return units, representation, diagnostics
    text = raw.decode('utf-8-sig')
    if kind == 'aas-json':
        data = json.loads(text)

        def walk(value: Any, pointer: str, context: dict):
            if isinstance(value, dict):
                context = {**context, **{key: value[key] for key in ('id', 'idShort', 'modelType', 'semanticId', 'valueType') if key in value}}
                if 'modelType' in value:
                    emit('aas_element', {'kind': 'json', 'pointer': pointer, 'value_hash': digest(value)}, canonical(value), context)
                for key, child in value.items():
                    walk(child, pointer + '/' + str(key).replace('~', '~0').replace('/', '~1'), context)
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    walk(child, f'{pointer}/{index}', context)
            else:
                emit('aas_element', {'kind': 'json', 'pointer': pointer, 'value_hash': digest(value)}, canonical(value), {**context, 'pointer': pointer})

        walk(data, '', {})
        return units, canonical(data), diagnostics
    if kind == 'aas-xml':
        from defusedxml.ElementTree import fromstring
        root = fromstring(text, forbid_dtd=True)

        def walk_xml(element, indices: list[int], parents: list[str]):
            value = {'text': element.text or '', 'attributes': dict(element.attrib)}
            if not list(element) or element.attrib:
                emit('aas_element', {'kind': 'xml', 'child_indices': indices, 'tag': element.tag,
                     'value_hash': digest(value)}, canonical(value), {'parents': parents, 'tag': element.tag})
            for index, child in enumerate(element):
                walk_xml(child, [*indices, index], [*parents, element.tag])

        walk_xml(root, [], [])
        return units, text, diagnostics
    if kind == 'rdf':
        from rdflib import Dataset
        from pyld import jsonld
        suffix = source.name.lower().rsplit('.', 1)[-1]
        fmt = {'ttl': 'turtle', 'trig': 'trig', 'nq': 'nquads', 'nt': 'nt', 'rdf': 'xml', 'jsonld': 'json-ld'}.get(suffix)
        if source.media_type == 'application/ld+json':
            fmt = 'json-ld'
        if source.media_type == 'application/rdf+xml':
            fmt = 'xml'
        if fmt == 'json-ld':
            data = json.loads(text)
            # Freeze external contexts separately instead of permitting network retrieval.
            def check_context(value):
                if isinstance(value, dict):
                    if '@import' in value:
                        raise ValueError('External JSON-LD context imports must be embedded in the frozen source.')
                    context = value.get('@context')
                    if isinstance(context, str) or (isinstance(context, list) and any(isinstance(x, str) for x in context)):
                        raise ValueError('External JSON-LD contexts must be embedded in the frozen source.')
                    for child in value.values():
                        check_context(child)
                elif isinstance(value, list):
                    for child in value:
                        check_context(child)
            check_context(data)
        if fmt == 'xml':
            from defusedxml.ElementTree import fromstring
            fromstring(text, forbid_dtd=True)
        dataset = Dataset()
        dataset.parse(data=text, format=fmt or 'turtle', publicID=source.origin_uri or 'urn:rq1:source:')
        serialized = dataset.serialize(format='nquads')
        representation = jsonld.normalize(serialized, {'algorithm': 'URDNA2015',
            'inputFormat': 'application/n-quads', 'format': 'application/n-quads'})
        for quad in representation.splitlines():
            if quad.strip():
                emit('rdf_subgraph', {'kind': 'rdf', 'quads': [quad], 'canonicalization': 'URDNA2015'}, quad)
        diagnostics.append('Blank-node canonicalization uses pinned PyLD URDNA2015; not claimed as RDFC-1.0.')
        return units, representation, diagnostics
    if kind == 'ifc':
        import ifcopenshell
        model = ifcopenshell.file.from_string(text)

        def info(entity):
            def value(v):
                if isinstance(v, ifcopenshell.entity_instance):
                    return {'step_id': v.id(), 'type': v.is_a()} if v.id() else {'type': v.is_a(), 'value': v.wrappedValue}
                if isinstance(v, (list, tuple)):
                    return [value(x) for x in v]
                return v
            return {key: value(v) for key, v in entity.get_info().items()}

        seen_guids: set[str] = set()
        for entity in model:
            value = info(entity)
            guid = getattr(entity, 'GlobalId', None)
            if guid and guid in seen_guids:
                raise ValueError('IFC contains duplicate GlobalId identities.')
            if guid:
                seen_guids.add(guid)
            emit('ifc_entity', {'kind': 'ifc', 'step_id': entity.id(), 'global_id': guid,
                 'entity_type': entity.is_a(), 'value_hash': digest(value)}, canonical(value), {'schema': model.schema})
        for relation in model.by_type('IfcRelDefinesByProperties'):
            pset = relation.RelatingPropertyDefinition
            properties = getattr(pset, 'HasProperties', None) or getattr(pset, 'Quantities', ())
            for owner in relation.RelatedObjects:
                for prop in properties:
                    value = {'owner': info(owner), 'relationship': info(relation), 'pset': info(pset), 'property': info(prop),
                             'unit': info(prop.Unit) if getattr(prop, 'Unit', None) else None}
                    emit('ifc_property', {'kind': 'ifc', 'step_id': owner.id(),
                         'global_id': getattr(owner, 'GlobalId', None), 'entity_type': owner.is_a(),
                         'property_step_id': prop.id(), 'relationship_ids': [relation.id(), pset.id()],
                         'value_hash': digest(value)}, canonical(value), {'schema': model.schema,
                         'property_set': pset.Name, 'property_name': prop.Name, 'inheritance': 'occurrence'})
        for relation in model.by_type('IfcRelDefinesByType'):
            owner_type = relation.RelatingType
            for pset in getattr(owner_type, 'HasPropertySets', ()) or ():
                for owner in relation.RelatedObjects:
                    for prop in getattr(pset, 'HasProperties', ()) or ():
                        value = {'owner': info(owner), 'relationship': info(relation), 'type': info(owner_type),
                                 'pset': info(pset), 'property': info(prop),
                                 'unit': info(prop.Unit) if getattr(prop, 'Unit', None) else None}
                        emit('ifc_property', {'kind': 'ifc', 'step_id': owner.id(),
                             'global_id': getattr(owner, 'GlobalId', None), 'entity_type': owner.is_a(),
                             'property_step_id': prop.id(), 'relationship_ids': [relation.id(), owner_type.id(), pset.id()],
                             'value_hash': digest(value)}, canonical(value), {'schema': model.schema,
                             'property_set': pset.Name, 'property_name': prop.Name, 'inheritance': 'type'})
        return units, text, diagnostics
    raise ValueError(f'Unsupported adapter: {kind}')


def resolve_evidence(store: Store, unit: EvidenceUnit, cache: dict | None = None) -> dict:
    """Regenerate the selected structured fact from the pinned original artifact."""
    cache = cache if cache is not None else {}
    try:
        source = source_model(store.get('source', unit.source_version_id))
        if source.parser_version != unit.parser_version or unit.parser_version not in SUPPORTED_PARSER_VERSIONS:
            raise ValueError('Parser version mismatch; redecompose explicitly.')
        if source.parser_dependencies != dependencies(source.artifact_kind):
            raise ValueError('Parser dependency versions changed; redecompose explicitly.')
        if source.source_id != unit.source_id:
            raise ValueError('Evidence source identity mismatch.')
        raw = base64.b64decode(source.raw_base64, validate=True)
        if digest(raw) != source.raw_sha256:
            raise ValueError('Original source hash mismatch.')
        if source.parent_source_version_id:
            parent = source_model(store.get('source', source.parent_source_version_id))
            parent_raw = base64.b64decode(parent.raw_base64, validate=True)
            if digest(parent_raw) != parent.raw_sha256:
                raise ValueError('Package hash mismatch.')
            with zipfile.ZipFile(io.BytesIO(parent_raw)) as package:
                if package.namelist().count(source.package_entry_path) != 1:
                    raise ValueError('Package member is absent or ambiguous.')
                if digest(package.read(source.package_entry_path)) != source.raw_sha256:
                    raise ValueError('Package member hash mismatch.')
        if source.source_version_id not in cache:
            regenerated, representation, _ = decompose(source)
            if source.representation_hash and digest(representation.encode()) != source.representation_hash:
                raise ValueError('Source representation hash mismatch.')
            cache[source.source_version_id] = {item.evidence_id: item for item in regenerated}
        original = cache[source.source_version_id].get(unit.evidence_id)
        if original is None or original.model_dump() != unit.model_dump():
            raise ValueError('Selector or cited structured fact does not match the original source.')
        return {'status': 'pass', 'method': unit.selector.kind, 'source_hash': source.raw_sha256,
                'parser_version': source.parser_version, 'content': original.content}
    except Exception as exc:
        return {'status': 'fail', 'method': unit.selector.kind, 'message': str(exc)}
