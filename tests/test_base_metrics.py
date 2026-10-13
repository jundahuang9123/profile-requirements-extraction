"""Measured comparison counts are distinct from correctness and human acceptance."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'requirement-reuse-service'))
from requirement_reuse_service.workflow.evaluation import base_check_metrics


def test_base_metrics_use_frozen_initial_audit_and_active_merged_source_groups():
    frozen = {'base_check_audit': [
        {'base_check': {'relation': 'inherited', 'resolved_via': 'curie'}},
        {'base_check': {'relation': 'tightened', 'resolved_via': 'metadata_need'}},
        {'base_check': {'relation': 'new', 'resolved_via': 'none'}}],
        'set_aside_observations': [{'reason': 'inherited_from_base'}, {'reason': 'no_source_link'}],
        'active_revision_ids': ['merged', 'other', 'base'], 'requirements': [
            {'revision_id': 'parent', 'base_check': {'evidence_source_groups': ['base_only']}},
            {'revision_id': 'merged', 'base_check': {'evidence_source_groups': ['base_only', 'mobility']}},
            {'revision_id': 'other', 'base_check': {'evidence_source_groups': ['other_generic', 'inspire_geodcat']}},
            {'revision_id': 'base', 'base_check': {'evidence_source_groups': ['base_only']}}]}
    run = {'base_check_policy_version': 'rq1-base-check-v1', 'base_profile_id': 'dcat-ap-2.0.1',
           'base_profile_sha256': 'a' * 64, 'base_check_audit': []}
    metrics = base_check_metrics(run, frozen)
    assert metrics['by_relation'] == {'inherited': 1, 'tightened': 1, 'new': 1}
    assert metrics['by_resolved_via'] == {'curie': 1, 'metadata_need': 1, 'none': 1}
    assert metrics['set_aside_inherited'] == 1
    assert metrics['kept_by_evidence_source_group'] == {'mobility': 1, 'inspire_geodcat': 1, 'base_only': 1}


def test_unmeasured_legacy_records_do_not_get_invented_base_or_source_counts():
    metrics = base_check_metrics({'requirements': [{'revision_id': 'old'}]})
    assert metrics['policy_version'] is None
    assert metrics['by_relation'] == metrics['by_resolved_via'] == metrics['kept_by_evidence_source_group'] == {}
    assert metrics['set_aside_inherited'] == 0


def test_an_explicit_empty_active_set_does_not_count_superseded_records():
    metrics = base_check_metrics({'active_revision_ids': [], 'requirements': [
        {'revision_id': 'superseded', 'base_check': {'evidence_source_groups': ['mobility']}}]})
    assert metrics['kept_by_evidence_source_group'] == {}
