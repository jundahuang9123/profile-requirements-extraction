"""Exact source excerpt catalogues shared by selection and elicitation."""
import re

# Longest excerpt, in characters from its first to its last character. Role citations
# accept quotations up to this length, so the two limits have to stay equal.
EXCERPT_MAX_CHARS = 400


def excerpt_bounds(content, limit=EXCERPT_MAX_CHARS):
    """Cut one evidence unit into excerpts of whole neighbouring lines.

    An excerpt is one contiguous slice of ``content``. Consecutive lines are joined,
    line breaks included, for as long as the slice stays within ``limit`` characters;
    the next line then starts a new excerpt. A blank line always ends an excerpt. A
    single line longer than ``limit`` is cut every ``limit`` characters and its last
    piece can still be joined by the lines after it.

    Returns ordered, non-overlapping ``(start, end)`` offsets. Only line breaks and
    blank space lie outside them, so no source text is hidden from citation.
    """
    bounds, start, end = [], None, None

    def close():
        nonlocal start, end
        if start is not None and content[start:end].strip():
            bounds.append((start, end))
        start = end = None

    for line in re.finditer(r'[^\r\n]+', content):
        if not line.group().strip():
            close()
            continue
        if start is not None:
            blank_line_between = len(content[end:line.start()].replace('\r\n', '\n')) > 1
            if blank_line_between or line.end() - start > limit:
                close()
        if start is None:
            start = line.start()
            while line.end() - start > limit:
                if content[start:start + limit].strip():
                    bounds.append((start, start + limit))
                start += limit
        end = line.end()
    close()
    return bounds


def source_spans_for(batch):
    """Number every excerpt of the batch in source order, with its exact text and offset."""
    spans = []
    for unit in batch:
        content = unit['content']
        for start, end in excerpt_bounds(content):
            spans.append({'span_id': f's{len(spans)}', 'evidence_id': unit['evidence_id'],
                          'quote_start': start, 'quote': content[start:end]})
    return spans


def elicitation_batch(units):
    """Expose every excerpt in source order, without duplicate full passage text."""
    catalogue = source_spans_for(units)
    by_unit = {}
    for span in catalogue:
        by_unit.setdefault(span['evidence_id'], []).append(
            {'span_id': span['span_id'], 'quote': span['quote']})
    payload = [{**{key: value for key, value in unit.items() if key != 'content'},
                'source_spans': by_unit.get(unit['evidence_id'], [])} for unit in units]
    return payload, catalogue


def materialize_observation(proposal, catalogue):
    from .models import Observation
    spans = {span['span_id']: span for span in catalogue}
    links, seen = [], set()
    for link in proposal.evidence_links:
        if link.source_span_id not in spans:
            raise ValueError(f'Unknown source excerpt {link.source_span_id!r}; citation is outside this batch.')
        identity = (link.source_span_id, link.relation, link.component)
        if identity in seen:
            raise ValueError('Duplicate source excerpt link for the same relation and component.')
        seen.add(identity)
        span = spans[link.source_span_id]
        links.append({'evidence_id': span['evidence_id'], 'quote': span['quote'],
                      'quote_start': span['quote_start'], 'relation': link.relation,
                      'component': link.component})
    body = proposal.model_dump(mode='json')
    return Observation.model_validate({**body, 'evidence_links': links})
