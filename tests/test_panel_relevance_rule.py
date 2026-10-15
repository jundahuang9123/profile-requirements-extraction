"""Both panel prompts judge relevance by what a stakeholder does with the data, on either side."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'requirement-reuse-service'))

from requirement_reuse_service.workflow.stakeholder_registry import PANEL_PROMPT, RELEVANCE_PROMPT, RELEVANCE_RULE  # noqa: E402


def test_both_prompts_carry_the_same_two_sided_relevance_rule():
    for prompt in (PANEL_PROMPT, RELEVANCE_PROMPT):
        assert RELEVANCE_RULE in prompt and 'RELEVANCE_RULE' not in prompt
    assert 'finding, judging or using the data' in RELEVANCE_RULE
    assert 'publish or maintain the data' in RELEVANCE_RULE
    assert 'not by whether a use case mentions it' in RELEVANCE_RULE


def test_the_panel_keeps_both_sides_within_the_basis_priority():
    rule = PANEL_PROMPT.split('\n3. ', 1)[1].split('\n4. ', 1)[0]
    assert 'Within rule 1' in rule
    assert 'keep at least one that finds or uses the data and at least one that publishes or maintains it' in ' '.join(rule.split())
