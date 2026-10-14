"""Frozen base-only catalogue loading and conservative retrieval; no benchmark input."""
import json
import re
from .base_profile import PROFILE_DIRECTORY, load_profile
from .storage import digest

POLICY = 'rq1-base-needs-catalogue-v2'
MAX_OFFERED = 25


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
    """Offer at most 25 entries, with round-robin coverage of the needs in a batch.

    Lexical retrieval is only a context bound: it does not decide coverage. A match
    missed by retrieval remains a domain proposal rather than being discarded.
    """
    words=lambda text:set(re.findall(r'[a-z]+',text.casefold()))-set('the a an of for to users metadata find identify must should'.split())
    def content(entry):
        return ' '.join([entry['need'], entry.get('definition') or '', *entry.get('usage_notes',[])])
    rows=[]
    for need in needs:
        tokens=words(need.need_statement or need.normalized_statement)
        ranked=sorted(catalogue['entries'],key=lambda e:(-len(tokens & words(content(e))),e['id']))
        rows.append([e for e in ranked if tokens & words(content(e))][:5])
    offered={}
    for index in range(5):
        for row in rows:
            if index<len(row): offered.setdefault(row[index]['id'],row[index])
            if len(offered)>=MAX_OFFERED: return list(offered.values())
    return list(offered.values())
