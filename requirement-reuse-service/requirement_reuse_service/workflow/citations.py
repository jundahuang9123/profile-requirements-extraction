"""Exact source excerpt catalogues shared by selection and elicitation."""
import re


def source_spans_for(batch):
    spans = []
    for unit in batch:
        content = unit['content']
        for line in re.finditer(r'[^\r\n]+', content):
            start = line.start()
            while start < line.end():
                end = min(start + 400, line.end())
                text = content[start:end]
                if text.strip():
                    spans.append({'span_id': f's{len(spans)}', 'evidence_id': unit['evidence_id'],
                                  'quote_start': start, 'quote': text})
                start = end
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
