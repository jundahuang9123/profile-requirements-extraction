"""Single-LLM baseline over every evidence unit (llm_cover_all_evidence): the same prompt once per pass."""
import math
import re
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = ROOT / 'requirement-reuse-service'
sys.path.insert(0, str(SERVICE_ROOT))

from requirement_reuse_service.llm.client import LLMError  # noqa: E402
from requirement_reuse_service.llm.extractor import (  # noqa: E402
    MAX_CHARS_PER_EVIDENCE_UNIT,
    MAX_TOTAL_CHARS,
    MAX_UNITS_PER_PASS,
    PROMPT_VERSION,
    build_user_prompt,
    chunk_evidence_units,
    extract_with_llm,
)
from requirement_reuse_service.models import AnalysisRequest, EvidenceUnit  # noqa: E402
from requirement_reuse_service.service import analyze_payload, extract_evidence_units  # noqa: E402

UNIT_MARK = re.compile(r'^--- evidence_unit_id: (\S+)$', re.M)


def long_text(sentences: int) -> str:
    # Every sentence names a title, so each one becomes its own evidence unit.
    return ' '.join(f'Record {i} of each dataset must state its title {i}.' for i in range(sentences))


def payload(sentences: int, **extra) -> AnalysisRequest:
    return AnalysisRequest(text=long_text(sentences), strategy='llm', **extra)


class RecordingClient:
    """Answers each pass with one requirement quoting the first unit it was shown; can fail chosen passes."""

    def __init__(self, units: list[EvidenceUnit], fail_on: tuple[int, ...] = ()):
        self.content = {unit.id: unit.content for unit in units}
        self.fail_on = set(fail_on)
        self.prompts: list[str] = []

    def describe(self) -> dict:
        return {'provider': 'test', 'model': 'test-model'}

    def generate_structured(self, *, system, user, output_model, max_tokens=None, **kwargs):
        self.prompts.append(user)
        if len(self.prompts) in self.fail_on:
            raise LLMError(f'pass {len(self.prompts)} returned an answer that failed schema validation')
        first = UNIT_MARK.search(user).group(1)
        return output_model.model_validate({'requirements': [{
            'statement': f'A dcat:Dataset must have a title (pass {len(self.prompts)}).',
            'requirement_type': 'descriptive_metadata', 'requirement_scope': 'profile_element', 'resource_type': 'Dataset',
            'metadata_need': 'title', 'value_kind': 'literal', 'obligation': 'mandatory', 'action': 'reuse_existing_term',
            'candidate_terms': ['dcterms:title'],
            'evidence': [{'evidence_unit_id': first, 'quote': self.content[first][:20]}],
        }]})


def prompt_unit_ids(prompt: str) -> list[str]:
    return UNIT_MARK.findall(prompt)


def test_default_single_pass_is_unchanged_and_reads_at_most_400_units():
    request = payload(950)
    every_unit = extract_evidence_units(request, limit=None)
    assert len(every_unit) == 950
    assert extract_evidence_units(request) == every_unit[:400]   # the default keeps the first 400, as before
    client = RecordingClient(every_unit)
    requirements, _ = extract_with_llm(request, client)
    assert len(client.prompts) == 1
    assert len(prompt_unit_ids(client.prompts[0])) == 400
    assert requirements[0].provenance.extractor == f'llm-extractor/{PROMPT_VERSION}'


def test_cover_all_evidence_reads_every_unit_exactly_once_within_the_budgets():
    request = payload(950, llm_cover_all_evidence=True)
    every_unit = extract_evidence_units(request, limit=None)
    client = RecordingClient(every_unit)
    requirements, warnings = extract_with_llm(request, client)
    seen = [unit_id for prompt in client.prompts for unit_id in prompt_unit_ids(prompt)]
    assert sorted(seen) == sorted(unit.id for unit in every_unit) and len(seen) == len(set(seen))
    assert len(client.prompts) == math.ceil(950 / MAX_UNITS_PER_PASS)
    for prompt in client.prompts:
        assert len(prompt_unit_ids(prompt)) <= MAX_UNITS_PER_PASS
        assert 'omitted: input budget exhausted' not in prompt
    assert len(requirements) == len(client.prompts)
    assert all(r.provenance.extractor == f'llm-extractor/{PROMPT_VERSION}+all-evidence' for r in requirements)
    assert all(r.validation_status == 'valid' for r in requirements)
    assert warnings[0] == f'llm_cover_all_evidence: 950 evidence unit(s) read in {len(client.prompts)} pass(es)'


def test_passes_split_on_the_character_budget_and_keep_the_order():
    units = [EvidenceUnit(id=f'ev-{i:04d}', source_id='s', artifact_name='a.txt', content='x' * 5000) for i in range(130)]
    chunks = chunk_evidence_units(units)
    per_pass = MAX_TOTAL_CHARS // MAX_CHARS_PER_EVIDENCE_UNIT   # each unit counts 1,200 characters in the prompt
    assert [len(chunk) for chunk in chunks] == [per_pass, per_pass, 130 - 2 * per_pass]
    assert [unit.id for chunk in chunks for unit in chunk] == [unit.id for unit in units]
    for chunk in chunks:
        _, prompt_warnings = build_user_prompt(chunk, [])
        assert not any(w.startswith('input_budget_omission') for w in prompt_warnings)


def test_a_failed_pass_is_skipped_and_reported():
    request = payload(950, llm_cover_all_evidence=True)
    client = RecordingClient(extract_evidence_units(request, limit=None), fail_on=(2,))
    requirements, warnings = extract_with_llm(request, client)
    assert len(client.prompts) == 3 and len(requirements) == 2
    assert any(w.startswith('pass 2/3 failed and was skipped') for w in warnings)
    assert warnings[-1] == 'llm_cover_all_evidence: 1 of 3 pass(es) failed: [2]'


def test_every_pass_failing_raises_so_the_request_falls_back_like_a_failed_single_pass():
    request = payload(950, llm_cover_all_evidence=True)
    client = RecordingClient(extract_evidence_units(request, limit=None), fail_on=(1, 2, 3))
    with pytest.raises(LLMError):
        extract_with_llm(request, client)


def test_the_flag_applies_only_to_the_llm_extractor():
    with pytest.raises(ValidationError):
        AnalysisRequest(text='x', strategy='rules', llm_cover_all_evidence=True)
    with pytest.raises(ValidationError):
        AnalysisRequest(text='x', strategy='multi_agent', llm_cover_all_evidence=True)
    assert AnalysisRequest(text='x', strategy='hybrid', llm_cover_all_evidence=True).llm_cover_all_evidence


def test_the_analysis_reports_every_evidence_unit_when_every_unit_was_read(monkeypatch):
    import requirement_reuse_service.llm as llm
    request = payload(950, llm_cover_all_evidence=True)
    every_unit = extract_evidence_units(request, limit=None)
    monkeypatch.setattr(llm, 'create_client', lambda config: RecordingClient(every_unit))
    response = analyze_payload(request)
    assert response.strategy == 'llm'
    assert len(response.evidence_units) == 950
    assert len(response.requirements) == 3
    single = analyze_payload(payload(950))   # the single pass, same client: still reports the first 400 units
    assert single.strategy == 'llm' and len(single.evidence_units) == 400
