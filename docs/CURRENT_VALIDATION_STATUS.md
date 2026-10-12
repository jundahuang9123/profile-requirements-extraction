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

## Addendum: changes made after this record (offline validation only)

The changes below were made after the trials above. None has been exercised against
a live provider. They change how failures are handled and how source text is offered
for citation; they do not show that a full run now completes.

- **Transport.** Timed-out attempts, dropped connections and HTTP 500/502/503/504 are
  retried up to two more times. Rate-limit patience defaults to five retries inside a
  120-second wait budget shared by both kinds of retry. A local `.env` copied from the
  earlier example still pins the old values (two retries, 30 seconds).
- **Extraction policy v2.10.** An answer with an unknown or repeated excerpt link, and
  a single unit cut off again after its larger retry, no longer stop a role. The unit
  is marked failed, later units are processed, and each role reports processed against
  total evidence units. Transport and authentication errors still stop a role.
- **Extraction policy v2.11, role-selection policy v6.** Consecutive lines of a unit
  form one excerpt of at most 400 characters instead of one excerpt per line. By the
  preflight rule the extraction batches per role fall from 16 to 15 (JRC), from 29 to
  20 (StatDCAT) and from 129 to 81 (GeoDCAT).
- **Role selection.** `RQ1_ROLE_SELECTION_MAX_BATCHES` raises the 32-batch scan limit
  for new runs. HealthDCAT-AP needs 36 batches and mobilityDCAT-AP 61 (63 before the
  webinar deck was removed from its inputs). Since 12 October new runs scan the whole
  corpus without this setting (at most 128 batches); it is now an optional cap.
- **Provenance.** The provider description saved with every call now includes the
  reasoning effort, the transport retry limits and the timeout.
- Offline validation after these changes: 218 tests passed, the exported workflow
  schema matches the runtime contracts, and the frontend build passed.

Still open after these changes:

- No live run has been made with them. How often the new recovery paths fire, and
  whether block excerpts change the quality of the cited evidence, is unmeasured.
- Resolved on 12 October 2026: mobilityDCAT-AP could not be frozen as a corpus,
  because page 19 of `dcat-ap-webinar-1-2021.pdf` is an image without extractable
  text (the DCAT-AP UML figure). The deck was removed from the runtime inputs; its
  figure's content is stated in the DCAT-AP 2.0.0 and 2.1.0 specifications, which
  remain inputs. The corpus now freezes: 16 files, 1,030 evidence units (1,099
  before), 279 extraction batches per role.
- The assessment and discussion workload described above is unchanged. Every
  candidate still gets its own assessment call, exact-only consolidation still keeps
  paraphrases, and every flagged pair still becomes a discussion case.
- Reasoning effort stays at the provider's default unless `RRS_LLM_REASONING_EFFORT`
  is set. For a reasoning model this decides how much of each response cap is left
  for the answer; the trial above spent 1,997 of 2,000 completion tokens on reasoning.

## Addendum: discussion setting, resume and run storage (offline validation only)

These changes followed the addendum above. They were checked with tests and with
scripted runs whose model answers instantly; none has been run against a live
provider.

- **Discussion setting.** A run created with `discussion: on_request` opens no
  discussion by itself. Candidates that would have been discussed go to human review
  with the same reasons, and a reviewer can still open a discussion. `automatic`
  remains the default. This addresses the discussion part of the workload point
  above; every candidate still gets its own assessment call.
- **Resume.** Resume keeps finished discussions whose input is unchanged and runs
  only new, changed or unfinished ones; an unchanged merged candidate keeps its
  assessment. In a scripted JRC run with two roles and one unanswerable unit, resume
  made 4 instead of 68 assessment requests and 3 instead of 196 discussion requests.
- **Run storage.** Model-call logs, stage copies, the machine snapshot, attempt
  history, baselines and excerpt catalogues are stored as rows next to the run, and
  a model call no longer rewrites the run. A scripted four-role JRC run took 66 s
  instead of 403 s, and its run document is 1.4 MB instead of 7.7 MB.
- **Consolidation** parses each source once instead of once per merged candidate.
- On HealthDCAT-AP (511 units, four roles, 2,554 candidates) the scripted run took
  622 s with discussion on request, about 0.2 s of local work per model call. With
  automatic discussion, each of the 2,040 discussion turns took about 1.1 s. For
  comparison, a recent KI:connect trial made 66 provider calls in 462 s, about 7 s each.
- Offline validation after these changes: 247 tests passed, the exported workflow
  schema matches the runtime contracts, and the frontend build passed.

Still open after these changes:

- No live run has been made with them.
- Each assessment and each discussion turn still rewrites the run document, which
  reaches about 13 MB on HealthDCAT-AP. Storing candidates and discussion cases as
  rows would remove this. It was not done: the measured cost is about 0.27 s per
  assessment and 1.1 s per discussion turn, against about 7 s per provider call.
- While a run is active the workbench reloads all stage copies (about 20 MB on
  HealthDCAT-AP) on every refresh, although it shows only the current step's copy.

## Addendum: first live trial after the fixes (12 October 2026, role selection only)

mobilityDCAT-AP with KI:connect `inferenz-gpt-oss-120b`, reasoning effort low, automatic
role selection with four roles, run `run-23e6df696aca4dbe9f5649cc4cbbf855`:

- Role selection stopped seven times at the panel step, the last time in batch 17 of 60.
  The selector was offered each retained role's absorbed candidate IDs and listed those
  instead of the role's own ID (7 of 24 panel calls). Resume repeated the failed round:
  four rounds passed on the second call, batch 17 failed four times. Role-selection
  policy v7 no longer offers those IDs and allows one correction per panel call; it has
  been checked with tests only.
- All 54 calls finished normally (`finish_reason=stop`). With reasoning effort low,
  reasoning used about 280 to 350 tokens per call.
- Calls took 24 to 38 seconds on average by type (discovery 27, citation correction 24,
  panel 38), not the 7 seconds per call of the 10 October JRC tryout. 13 of 17 discovery
  batches needed the single citation correction; all 13 succeeded.
- At this speed a full mobilityDCAT-AP run is long: up to 240 role-selection calls,
  about 1,100 extraction calls and one assessment call per candidate, roughly 20 to 30
  hours of model time, plus several turns per flagged candidate with automatic discussion.
