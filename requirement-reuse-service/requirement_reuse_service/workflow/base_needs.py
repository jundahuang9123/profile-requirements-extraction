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


def offer_entries(needs, catalogue):
    """Offer complete per-need catalogue coverage, with likely matches first.

    The former shared cap could spend the 25-entry budget on early needs and leave
    later needs with no relevant entries. Callers now batch one need at a time, so
    all base entries can be compared without a retrieval miss being mistaken for a
    catalogue gap. Ordering is only a reading aid; it does not hide entries.
    """
    if len(needs) > 1:
        raise ValueError('Base comparison requires one need per complete-catalogue search.')
    if not needs:
        return []
    words=lambda text:set(re.findall(r'[a-z]+',text.casefold()))-set('the a an of for to users metadata find identify must should'.split())
    def content(entry):
        return ' '.join([entry.get('class') or '', entry.get('property') or '', entry['need'],
                         entry.get('definition') or '', *entry.get('usage_notes',[])])
    text=' '.join([needs[0].need_statement or '', needs[0].normalized_statement or '',
                   getattr(needs[0], 'need_condition', '') or ''])
    tokens=words(text)
    # UK/US spelling is common in source material and must not hide an entry.
    if 'license' in tokens: tokens.add('licence')
    if 'licence' in tokens: tokens.add('license')
    return sorted(catalogue['entries'], key=lambda e:(-len(tokens & words(content(e))),e['id']))
