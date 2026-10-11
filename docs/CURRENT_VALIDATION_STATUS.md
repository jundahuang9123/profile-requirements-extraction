# Validation status and known issues — 11 October 2026

This records the evidence available when committing the workflow and provider
fixes. Local live-run data and credentials are not included in the repository.

## Confirmed results and failures

- Offline validation: 185 tests passed; the exported workflow schema matches the
  runtime contracts; the TypeScript and production frontend build passed.
  Five dependency deprecation warnings remain. These checks do not establish
  research quality or successful live end-to-end execution.
- Latest saved full StatDCAT-named trial, `run-aaefcda5744841f39b3f589521a580d8`:
  all four extraction roles completed and produced 712 candidates. Verification
  stopped after 286 saved assessments, leaving 426 pending. The failing GPT-OSS
  response reported `finish_reason=length` at a 2,000-token completion cap,
  including 1,997 reasoning tokens, with 4,133 prompt tokens. This demonstrates
  output-budget exhaustion; it does not demonstrate input-context overflow.
- The revised assessor uses bounded 4,000/8,000-token attempts and retains an
  uncertain, blocked draft if both attempts fail. A same-candidate diagnostic
  succeeded on the first generation for both KI:connect GPT-OSS and Qwen. Neither
  diagnostic exercised live retry recovery or the full workflow.
- No fresh full run has completed under the latest assessment/discussion policies.
  Historical failed runs stay unchanged. No human-accepted research baseline,
  precision/recall result, or measured effort saving has been established by
  these trials.
- The StatDCAT-named input snapshot contained only W3C DCAT 2014 and W3C Data Cube
  2014 (60 evidence units), with no saved competency questions. It cannot establish
  coverage of StatDCAT-specific stakeholder requirements. Reference requirements
  were excluded from the extraction input.

## Remaining limitations and hypotheses to test

- Repeated malformed or truncated output, provider timeouts and exhausted rate
  limits can still prevent completion. Bounded retries prevent indefinite work;
  they do not guarantee valid model output. Output allowances apply to individual
  generation requests and can include reasoning tokens, separately from provider
  account quotas.
- The 712-candidate count is not a count of distinct, relevant requirements.
  Per-role extraction can repeat proposals, and conservative exact consolidation
  may retain paraphrases. The resulting assessment/discussion workload is a
  plausible design concern; its effect has not been isolated or quantified.
- Source-address checks establish citation fidelity, not semantic correctness.
  Selected stakeholder perspectives and agent agreement do not establish real
  stakeholder endorsement. Human review still has to resolve support, scope,
  obligation, quality findings and conflicting alternatives.
- Resuming the failed trial would reuse completed v2.1 assessments and apply v2.2
  to unfinished records. Report that as a recovery trial with mixed conditions;
  use a fresh run for a consistent-policy comparison. Interrupted remote calls
  may be repeated, and some consolidation/discussion work can need follow-up.
- The small successful diagnostic does not establish that Qwen is better than
  GPT-OSS, or that switching models resolves the broader workflow issues. Full
  completion, requirement quality, latency and cost remain to be measured.

The next useful validation is a bounded end-to-end run with an explicitly checked
source manifest and scope, followed by review of the resulting requirements.
Preserve machine proposals, human decisions and final baseline as separate outputs.
