"""Profile discovery ignores auxiliary catalogue files, but validates registries."""
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from requirement_reuse_service.main import app
from requirement_reuse_service.workflow import base_profile


def test_profile_endpoint_lists_only_supported_profile_filenames(tmp_path, monkeypatch):
    monkeypatch.setattr(base_profile, 'PROFILE_DIRECTORY', tmp_path)
    expected = {}
    for profile_id, family in [('dcat-3.0.0', 'DCAT'), ('dcat-ap-2.0.1', 'DCAT-AP')]:
        profile = {'id': profile_id, 'version': profile_id.rsplit('-', 1)[-1],
                   'family': family, 'label': profile_id, 'classes': {}}
        raw = json.dumps(profile).encode()
        (tmp_path / (profile_id + '.json')).write_bytes(raw)
        expected[profile_id] = hashlib.sha256(raw).hexdigest()
    # These are not profile registries and must never be parsed by the endpoint.
    for filename in ('dcat-ap-2.0.1.needs.json', 'dcat-ap-2.0.1.needs-review.json',
                     'dcat-3.0.0.needs-review.json', 'dcat-ap-not-a-version.json'):
        (tmp_path / filename).write_text('not registry JSON', encoding='utf-8')

    response = TestClient(app).get('/api/rq1/v2/base-profiles')

    assert response.status_code == 200
    profiles = response.json()
    assert [profile['id'] for profile in profiles] == sorted(expected)
    assert {profile['id']: profile['sha256'] for profile in profiles} == expected
    assert {profile['family'] for profile in profiles} == {'DCAT', 'DCAT-AP'}


def test_profile_endpoint_does_not_hide_a_broken_supported_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(base_profile, 'PROFILE_DIRECTORY', tmp_path)
    (tmp_path / 'dcat-ap-2.0.1.json').write_text(json.dumps(
        {'id': 'dcat-ap-2.0.1', 'version': '2.0.1', 'classes': []}), encoding='utf-8')

    with pytest.raises(ValueError, match='invalid id or class table'):
        TestClient(app).get('/api/rq1/v2/base-profiles')
