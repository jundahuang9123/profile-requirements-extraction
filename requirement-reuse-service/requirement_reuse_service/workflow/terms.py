"""Collect observed RQ2 terms without proposing or resolving new vocabulary."""
import re
from .models import RQ2Hint

CURIE = re.compile(r"(?<![\w/:])([A-Za-z][\w.-]*:[A-Za-z_][\w.-]*)(?![\w/])")
CAMEL = re.compile(r"[a-z][A-Z]|[A-Z][a-z]")


def registry_terms(profile):
    values = set()
    for cls, properties in (profile or {}).get('classes', {}).items():
        values.add(cls)
        values.update(properties)
    return values


def detect_terms(text, profile=None):
    found = {m.group(1).rstrip('.,;') for m in CURIE.finditer(text)}
    # URLs and human punctuation such as ISO: 19115 are not CURIEs.
    for term in registry_terms(profile):
        local = term.split(':', 1)[-1]
        if CAMEL.search(local) and re.search(r'(?<![\w:])' + re.escape(local) + r'(?!\w)', text):
            found.add(local)
    return sorted(found)


def collect_hints(statement, links, profile=None, revision_id=None, offered=()):
    hints = [RQ2Hint(term=t, kind='vocabulary_term', origin='proposal', revision_id=revision_id)
             for t in detect_terms(statement, profile)]
    for link in links:
        item = link.model_dump() if hasattr(link, 'model_dump') else link
        hints.extend(RQ2Hint(term=t, kind='vocabulary_term', origin='evidence',
                            evidence_id=item['evidence_id'], revision_id=revision_id)
                     for t in detect_terms(item['quote'], profile))
    # A provider hint is accepted only if its literal spelling occurs in a proposal
    # or an authentic quotation. Its claimed provenance is never trusted.
    for proposed in offered:
        proposed = RQ2Hint.model_validate(proposed)
        if re.search(r'(?<!\w)' + re.escape(proposed.term) + r'(?!\w)', statement):
            hints.append(proposed.model_copy(update={'origin': 'proposal', 'evidence_id': None, 'revision_id': revision_id}))
        for link in links:
            item = link.model_dump() if hasattr(link, 'model_dump') else link
            if re.search(r'(?<!\w)' + re.escape(proposed.term) + r'(?!\w)', item['quote']):
                hints.append(proposed.model_copy(update={'origin': 'evidence', 'evidence_id': item['evidence_id'], 'revision_id': revision_id}))
    return union_hints(hints)


def union_hints(hints):
    unique = {}
    for hint in hints:
        hint = RQ2Hint.model_validate(hint)
        unique[tuple(hint.model_dump().values())] = hint
    return [unique[key] for key in sorted(unique, key=lambda x: tuple(str(v or '') for v in x))]
