"""Frozen base-only catalogue loading and conservative retrieval; no benchmark input."""
import json
import re
from .base_profile import PROFILE_DIRECTORY, load_profile
from .storage import digest

POLICY = 'rq1-base-needs-catalogue-v2'


def load_catalogue(profile_id, expected_profile_hash=None):
    _, profile_hash = load_profile(profile_id)
    body=json.loads((PROFILE_DIRECTORY/(profile_id+'.needs.json')).read_text())
    if body['catalogue_hash'] != digest({k:v for k,v in body.items() if k != 'catalogue_hash'}):
        raise ValueError('Base needs catalogue hash mismatch.')
    if body['base_profile_id'] != profile_id or body['base_profile_sha256'] != profile_hash:
        raise ValueError('Base needs catalogue does not match the selected base registry.')
    if expected_profile_hash and expected_profile_hash != profile_hash:
        raise ValueError('Selected base registry changed; derive a new run.')
    if body['policy_version'] != POLICY:
        raise ValueError('Unsupported base needs catalogue policy.')
    return body


_STOP = set('the a an of for to users metadata find identify must should'.split())


def _words(text):
    """Content words; plural and singular rank alike ("keywords" finds the keyword entry)."""
    found = set(re.findall(r'[a-z]+', (text or '').casefold())) - _STOP
    words = {w[:-1] if len(w) > 3 and w.endswith('s') and not w.endswith('ss') else w for w in found}
    # UK/US spelling is common in source material and must not hide an entry.
    if 'license' in words: words.add('licence')
    if 'licence' in words: words.add('license')
    return words


def _need_words(need):
    return _words(' '.join([need.need_statement or '', getattr(need, 'normalized_statement', '') or '',
                            getattr(need, 'need_condition', '') or '']))


def _content(entry):
    return ' '.join([entry.get('class') or '', entry.get('property') or '', entry['need'],
                     entry.get('definition') or '', *entry.get('usage_notes', [])])


def item_picks(need, catalogue):
    """For each word of the need that names an entry, that entry; rarest words first.

    A need that lists several items (the title, keywords and release date of a dataset)
    then has an entry for each item at the front of the search order, so one chunk can
    show that the base covers all of them. Ordering only; every entry is still offered.
    """
    tokens = _need_words(need)
    entries = catalogue['entries']
    score = {e['id']: len(tokens & _words(_content(e))) for e in entries}
    named = {e['id']: _words(' '.join([e.get('property') or '', e['need']])) for e in entries}
    by_word = {t: [e for e in entries if t in named[e['id']]] for t in tokens}
    picks, seen = [], set()
    for word in sorted((t for t in tokens if by_word[t]), key=lambda t: (len(by_word[t]), t)):
        best = min(by_word[word], key=lambda e: (-score[e['id']], e['id']))
        if best['id'] not in seen:
            picks.append(best); seen.add(best['id'])
    return picks


def offer_entries(needs, catalogue):
    """Offer complete per-need catalogue coverage, with likely matches first.

    The former shared cap could spend the 25-entry budget on early needs and leave
    later needs with no relevant entries. Callers now batch one need at a time, so
    all base entries can be compared without a retrieval miss being mistaken for a
    catalogue gap. Ordering is only a reading aid; it does not hide entries. Since
    rq1-base-needs-full-search-v3 the entries a need's words name come first.
    """
    if len(needs) > 1:
        raise ValueError('Base comparison requires one need per complete-catalogue search.')
    if not needs:
        return []
    tokens = _need_words(needs[0])
    picks = item_picks(needs[0], catalogue)
    picked = {e['id'] for e in picks}
    rest = sorted((e for e in catalogue['entries'] if e['id'] not in picked),
                  key=lambda e: (-len(tokens & _words(_content(e))), e['id']))
    return [*picks, *rest]
