"""PDF layout line breaks must not become artificial evidence boundaries."""
import base64
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'requirement-reuse-service'))
from requirement_reuse_service.models import ArtifactPayload
from requirement_reuse_service.workflow.evidence import (
    PARSER_VERSION, PDF_PASSAGE_MAX_CHARS, decompose, pdf_passage_spans,
    register_source, resolve_evidence, source_model,
)
from requirement_reuse_service.workflow.models import EvidenceUnit, SourceRequest
from requirement_reuse_service.workflow.storage import Store, digest


@pytest.fixture
def pdf_source(tmp_path, monkeypatch):
    store = Store(str(tmp_path / 'workflow.sqlite3'))

    def register(pages):
        import pdfplumber

        @contextmanager
        def open_pdf(_):
            yield SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda text=text: text, images=[]) for text in pages])

        monkeypatch.setattr(pdfplumber, 'open', open_pdf)
        source = register_source(store, SourceRequest(artifact=ArtifactPayload(
            name='source.pdf', content=base64.b64encode(b'%PDF-deterministic-test').decode(),
            content_encoding='base64')))
        assert source['parse_status'] == 'parsed', source['diagnostics']
        units = [EvidenceUnit.model_validate(item) for item in store.list('evidence')
                 if item['source_version_id'] == source['source_version_id']]
        return store, source, sorted(units, key=lambda unit: unit.selector.start)

    return register


def test_multiline_sentence_preserves_hyphenation_offsets_and_page_boundaries(pdf_source):
    pages = ['The legislation requires a Na-\ntional Access Point (NAP) in each state.\nOperators supply metadata.\n\n'
             '  Separate block retains its  internal spaces.  ', '', 'Second page: users discover datasets.']
    store, source, units = pdf_source(pages)
    assert len(units) == 3
    assert units[0].content == pages[0].split('\n\n')[0]
    assert 'Na-\ntional' in units[0].content
    assert [unit.selector.page for unit in units] == [1, 1, 3]
    assert all('\f' not in unit.content for unit in units)
    assert source['representation'] == '\n\f\n'.join(pages)
    cache = {}
    for unit in units:
        assert source['representation'][unit.selector.start:unit.selector.end] == unit.content
        assert unit.selector.representation_hash == digest(source['representation'].encode())
        assert resolve_evidence(store, unit, cache)['status'] == 'pass'
    assert units[0].structural_context['line_end'] > units[0].structural_context['line']


@pytest.mark.parametrize('text', [
    ('Transport operators publish timetable metadata.\n' * 300),
    ('A' * (PDF_PASSAGE_MAX_CHARS * 3 + 71)),
    ('word ' * 2000) + '\n\n  Last block.\n',
    '  \n\nFirst sentence.\n\n\n\tNext paragraph.\n\n  ',
])
def test_bounded_passages_cover_every_nonblank_character_exactly_once(text):
    spans = list(pdf_passage_spans(text))
    assert all(0 < end - start <= PDF_PASSAGE_MAX_CHARS for start, end in spans)
    assert all(end <= next_start for (_, end), (next_start, _) in zip(spans, spans[1:]))
    covered = {index for start, end in spans for index in range(start, end)}
    assert all(index in covered for index, char in enumerate(text) if not char.isspace())
    assert ''.join(char for start, end in spans for char in text[start:end] if not char.isspace()) == ''.join(text.split())


def test_legacy_pdf_snapshot_still_resolves_with_its_original_segmentation(pdf_source):
    store, current, _ = pdf_source(['First physical line\nSecond physical line.'])
    legacy = source_model(current).model_copy(update={
        'source_version_id': 'srcv-legacy-pdf', 'parser_version': 'rq1-adapters-v2.2'})
    legacy_units, representation, _ = decompose(legacy)
    assert len(legacy_units) == 2
    assert all(unit.parser_version == 'rq1-adapters-v2.2' for unit in legacy_units)
    assert representation == legacy.representation
    store.put('source', legacy.source_version_id, legacy.model_dump(mode='json'))
    for unit in legacy_units:
        result = resolve_evidence(store, unit)
        assert result['status'] == 'pass'
        assert result['parser_version'] == 'rq1-adapters-v2.2'
    tampered = legacy_units[0].model_copy(update={'content': 'Invented evidence'})
    assert resolve_evidence(store, tampered)['status'] == 'fail'
    mismatched = legacy_units[0].model_copy(update={'parser_version': PARSER_VERSION})
    assert resolve_evidence(store, mismatched)['status'] == 'fail'


def test_new_pdf_snapshot_uses_distinct_parser_and_passages(pdf_source):
    _, source, units = pdf_source(['One sentence crosses\nphysical lines.'])
    assert source['parser_version'] == PARSER_VERSION == 'rq1-adapters-v2.4'
    assert len(units) == 1
    legacy = source_model(source).model_copy(update={'parser_version': 'rq1-adapters-v2.2'})
    old_units, _, _ = decompose(legacy)
    assert len(old_units) == 2
    assert {unit.evidence_id for unit in units}.isdisjoint(unit.evidence_id for unit in old_units)


def test_image_only_page_blocks_complete_snapshot(tmp_path, monkeypatch):
    import pdfplumber
    from requirement_reuse_service.workflow.engine import freeze_snapshot
    from requirement_reuse_service.workflow.models import SnapshotRequest
    store = Store(str(tmp_path / 'scan.sqlite3'))
    @contextmanager
    def scanned_pdf(_):
        yield SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda: 'Readable policy.', images=[]),
                                    SimpleNamespace(extract_text=lambda: '', images=[{'name': 'scan'}])])
    monkeypatch.setattr(pdfplumber, 'open', scanned_pdf)
    source = register_source(store, SourceRequest(artifact=ArtifactPayload(
        name='mixed.pdf', content=base64.b64encode(b'%PDF-test').decode(), content_encoding='base64')))
    assert any('INCOMPLETE_SOURCE:' in message for message in source['diagnostics'])
    with pytest.raises(ValueError, match='incomplete extraction'):
        freeze_snapshot(store, SnapshotRequest(source_version_ids=[source['source_version_id']]))
