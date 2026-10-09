#!/usr/bin/env python3
"""Offline integrity/readability checks for this benchmark snapshot; no app imports."""
import argparse
import csv
import hashlib
from html.parser import HTMLParser
import json
import logging
from pathlib import Path
import sys

class PDFWarnings(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages = []
    def emit(self, record):
        self.messages.append(record.getMessage())

ROOT = Path(__file__).resolve().parent
CASES = ('mobilitydcat', 'healthdcat', 'statdcat', 'geodcat', 'jrc-research', 'epos')
ROLES = {'raw_input', 'preconsolidation_input', 'reference_requirement',
         'final_profile_reference', 'context_only'}

class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.parts = []
    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.skip += 1
    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.skip = max(0, self.skip - 1)
    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def validate(deep_pdf=False):
    errors, checked, registered, stats = [], [], {}, {}
    allowlist = json.loads((ROOT / 'runtime-inputs.json').read_text())['benchmarks']
    pdf_reader = None
    if deep_pdf:
        try:
            from pypdf import PdfReader
            pdf_reader = PdfReader
        except ImportError:
            raise SystemExit('--deep-pdf requires pypdf; no PDF parsing claimed.')
    for case in CASES:
        base = ROOT / case
        manifest = json.loads((base / 'provenance/manifest.json').read_text())
        assert manifest['benchmark'] == case
        assert manifest['corpus_completeness'] == 'partial'
        ids = set()
        stats[case] = {'artifacts_and_citations': len(manifest['artifacts']),
                       'original_copies': 0, 'citation_only': 0,
                       'raw_documents': len(allowlist[case]['raw']),
                       'consolidation_documents': len(allowlist[case]['consolidation'])}
        for item in manifest['artifacts']:
            label = case + '/' + item['local_filename']
            p = (base / item['local_filename']).resolve()
            try:
                assert item['id'] not in ids, 'duplicate artifact ID'
                ids.add(item['id'])
                assert p.is_relative_to(base.resolve()), 'path escapes benchmark'
                assert label not in registered, 'duplicate local filename'
                registered[label] = item
                assert item['role'] in ROLES, 'invalid source role'
                assert isinstance(item['explicitly_documented_as_input'], bool)
                assert item['original_url'].startswith('https://'), 'missing original URL'
                for field in ('title', 'confidence', 'completeness', 'representation',
                              'license', 'sha256', 'retrieved_on'):
                    assert item[field], 'missing ' + field
                data = p.read_bytes()
                assert data, 'empty artifact'
                assert len(data) == item['bytes'], 'size differs from frozen manifest'
                assert hashlib.sha256(data).hexdigest() == item['sha256'], 'hash mismatch'
                result = {'path': label, 'bytes': len(data), 'status': 'readable',
                          'representation': item['representation']}
                if p.suffix == '.pdf':
                    assert data.startswith(b'%PDF-') and b'%%EOF' in data[-2048:], 'invalid PDF envelope'
                    result['readability_check'] = 'signature_and_trailer'
                    if pdf_reader:
                        audit = PDFWarnings()
                        logger = logging.getLogger('pypdf')
                        prior_propagate = logger.propagate
                        logger.addHandler(audit)
                        logger.propagate = False
                        try:
                            reader = pdf_reader(p)
                            assert not reader.is_encrypted, 'encrypted PDF'
                            texts = [page.extract_text() or '' for page in reader.pages]
                        finally:
                            logger.removeHandler(audit)
                            logger.propagate = prior_propagate
                        if audit.messages:
                            result['original_pdf_parser_warnings'] = audit.messages
                        assert len(reader.pages) > 0 and sum(map(len, texts)) > 100, 'no readable PDF text'
                        result.update(readability_check='all_pages_parsed',
                                      pages=len(reader.pages), extracted_characters=sum(map(len, texts)))
                else:
                    text = data.decode('utf-8')
                    if p.suffix == '.json':
                        json.loads(text)
                        result['readability_check'] = 'json_parsed'
                    elif p.suffix == '.html':
                        parser = VisibleText()
                        parser.feed(text)
                        visible = ' '.join(parser.parts)
                        assert len(visible.strip()) > 100, 'no readable HTML content'
                        assert 'Just a moment...' not in visible[:500], 'challenge page instead of source'
                        result.update(readability_check='html_text_parsed',
                                      visible_characters=len(visible))
                    else:
                        assert text.strip(), 'empty text'
                        result['readability_check'] = 'utf8_text'
                stats[case]['original_copies'] += item['representation'] == 'original_copy'
                stats[case]['citation_only'] += item['representation'] == 'citation_only'
                checked.append(result)
                for mode in item['runtime_modes']:
                    assert mode in ('raw', 'consolidation'), 'invalid runtime mode'
                    assert label in allowlist[case][mode], 'manifest mode absent from allowlist'
            except (AssertionError, OSError, UnicodeError, ValueError) as exc:
                errors.append(label + ': ' + str(exc))
    for case, modes in allowlist.items():
        for mode, files in modes.items():
            expected_role = 'raw_input' if mode == 'raw' else 'preconsolidation_input'
            for f in files:
                try:
                    assert len(files) == len(set(files)), 'duplicate runtime path'
                    assert f in registered, 'unregistered runtime input'
                    item = registered[f]
                    assert item['role'] == expected_role, 'reference/context leakage into runtime'
                    assert item['representation'] not in ('citation_only', 'retrospective_reconstruction'), 'ineligible source representation'
                    expected_dir = case + '/input-raw/' if mode == 'raw' else case + '/input-preconsolidation/'
                    assert f.startswith(expected_dir), 'input outside eligible directory'
                    assert mode in item['runtime_modes'], 'allowlist mode absent from manifest'
                except AssertionError as exc:
                    errors.append(f + ': ' + str(exc))
    for p in ROOT.rglob('*'):
        if not p.is_file():
            continue
        relative = p.relative_to(ROOT).as_posix()
        if relative.split('/')[0] in CASES and relative not in registered:
            if p.name not in ('README.md', 'GAPS.md', 'manifest.json'):
                errors.append(relative + ': unregistered source artifact')
        if p.suffix in ('.json', '.md', '.py', '.txt', '.html', '.csv'):
            try:
                text = p.read_text(encoding='utf-8')
                if p.suffix == '.json':
                    json.loads(text)
                elif p.suffix == '.csv':
                    rows = list(csv.reader(text.splitlines()))
                    if not rows or any(len(row) != len(rows[0]) for row in rows):
                        raise ValueError('invalid CSV rows')
            except (UnicodeError, ValueError) as exc:
                errors.append(relative + ': unreadable ' + str(exc))
    # Published/scoped reference counts are checked independently of the inventory.
    expected_counts = {'mobilitydcat/reference-requirements/consolidated-requirements.json': 40,
                       'healthdcat/reference-requirements/curated-requirements.json': 16,
                       'statdcat/reference-requirements/requirements-and-resolutions.json': 7,
                       'geodcat/reference-requirements/alignment-requirements.json': 7,
                       'jrc-research/reference-requirements/core-requirements.json': 5}
    for f, count in expected_counts.items():
        rows = json.loads((ROOT / f).read_text())['requirements']
        if len(rows) != count or len({r['id'] for r in rows}) != count:
            errors.append(f + ': wrong requirement count or duplicate ID')
    mob = json.loads((ROOT / 'mobilitydcat/reference-requirements/consolidated-requirements.json').read_text())['requirements']
    if sum(r['importance'] == 'mandatory' for r in mob) != 32:
        errors.append('mobility reference mandatory count must be 32')
    partners = json.loads((ROOT / 'mobilitydcat/input-preconsolidation/partner-requirements.json').read_text())
    if len(partners['candidates']) != 60 or len({r['id'] for r in partners['candidates']}) != 60:
        errors.append('mobility partner annex must preserve 60 unique labelled rows')
    if allowlist['epos']['raw'] or allowlist['epos']['consolidation']:
        errors.append('EPOS must remain exploratory, with scored allowlists empty')
    return {'snapshot_date': '2026-10-07', 'status': 'passed' if not errors else 'failed',
            'deep_pdf_parsing': deep_pdf, 'artifact_records_checked': len(checked),
            'total_artifact_bytes': sum(x['bytes'] for x in checked), 'by_benchmark': stats,
            'reference_counts': expected_counts, 'artifacts': checked, 'errors': errors,
            'limitations': ['Integrity/readability is not semantic adjudication.',
                           'Citation-only URLs are not full local source artifacts.',
                           'No claim of complete historical reconstruction or evaluation performance.',
                           'External resources required by ReSpec HTML are not bundled.',
                           'Some original PDFs have recoverable cross-reference warnings, retained per artifact; source bytes were not repaired.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deep-pdf', action='store_true')
    parser.add_argument('--report', type=Path, help='Optional JSON audit report path')
    args = parser.parse_args()
    report = validate(args.deep_pdf)
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('artifacts', 'reference_counts')}, indent=2))
    sys.exit(0 if report['status'] == 'passed' else 1)

if __name__ == '__main__':
    main()
