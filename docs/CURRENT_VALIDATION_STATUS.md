# Validation status and known issues — updated 12 October 2026

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

## Addendum: full Mobility trial and role-selection recovery — 12 October 2026

The full MobilityDCAT trial used 16 files, 1,030 evidence units and 12 declared
competency questions, with KI:connect `inferenz-gpt-oss-120b`, automatic role
selection and automatic discussion enabled. It stopped during role selection:
31 of 60 batches and 583 evidence units were checkpointed. The 97 recorded model
calls returned successfully as provider requests; local output validation stopped
the workflow. Extraction and discussion never began, and no requirement candidates
or human-accepted requirements were produced. This is an incomplete workflow trial,
not a requirements benchmark or evidence of effort saving.

Three failure paths motivated the role-selection changes in this commit:

- Historical candidate lineage was confused with the current panel IDs. Lineage
  now stays internal to saved state, and invalid panel accounting receives one
  bounded, recorded correction. Failed/interrupted corrections cannot be silently
  repeated; a saved valid correction is reusable.
- A citation repair explicitly returned no supporting excerpt. Such a candidate
  is retained as a **proposed** perspective without source citations and with a
  human-review disclaimer. Its original claim and the repair explanation remain
  visible. Invalid span IDs and source integrity failures still stop selection.
- In batch 32, “Competent Authority” cited `CQ-13`, which was absent from the
  frozen task registry. Automatic discovery now removes undeclared task links,
  preserves valid ones and audits the disposition. If that removes an inferred
  role's only support, its basis becomes **proposed**. Human overrides remain strict.

Policy v9 allows narrowly defined recovery from these saved v6/v7/v8 failures.
Migration notes record the changed conditions; resume history preserves the original
failed policy/manifest before migration, and original discoveries and completed
rounds are reused. New runs use v9 throughout. The UI exposes task-link and
unsupported-role dispositions, panel corrections, and the four-call-per-batch
logical scan bound. See [ROLE_SELECTION.md](ROLE_SELECTION.md) for the exact bounds
and recovery rules.

Validation for this change:

- 276 offline RQ1 tests passed (`python -m pytest tests -q`), with five existing
  dependency deprecation warnings. TypeScript and the production frontend build passed.
- A read-only backup of the real failed Mobility database was replayed in a
  disposable copy with inference blocked. `CQ-13` was removed while `CQ-8` and
  `CQ-9` were retained; all 31 rounds, 583 processed units, prior candidates and
  the original failed discovery were preserved. The next operation was citation
  correction for the three other invalid quotations, rather than another discovery.
  No provider generation occurred and the production run was unchanged.
- The documented RQ1 test suite is under `tests/`. Unrestricted repository-wide
  pytest collection also picks up an inherited Blackboard evaluation script that
  needs `matplotlib`, which is not installed in this RQ1 environment.

Still unvalidated: live completion under v9, semantic correctness of the selected
roles, downstream extraction coverage/quality, and full-workflow latency. Remaining
quotation errors still need the bounded repair to return valid excerpts or explicit
no-support dispositions; malformed responses, exhausted correction budgets, source
integrity errors and provider failures can still stop a run. Exact quotations do
not prove that a stakeholder classification or a generated requirement is correct.
The live benchmark remains paused. No credentials, source exports or run databases
are included in the code commit.

## Mobility role discovery: exact excerpt IDs (12 October 2026, later recovery)

After the v9 restart, the same KI:connect GPT-OSS run reached 40/60 completed
role-selection batches and 719/1,030 processed evidence units. Discovery for batch
41 failed its schema: one quotation exceeded 400 characters in both the initial
generation and its one allowed schema correction. Both provider responses finished
with `stop`; this was neither output truncation nor a reported context-window error.
The audit records hashes, character counts and validation paths, but does not store
the invalid response bodies, so their exact quotation lengths cannot be inspected.
The run has 125 logical model calls; extraction and discussion still have not begun.

Policy v10 removes model-written quotations and offsets from discovery. The model
selects source excerpt IDs, restricted by a batch-specific enum. The application
attaches exact text and offsets from the existing 400-character source catalogue.
No quote is arbitrarily shortened, no invalid candidate is partially accepted, and
source integrity and task-link checks remain in place. Authentic excerpts still
require assessment of whether they support the proposed role's meaning.

The v9-to-v10 migration is limited to this complete, too-long-quotation discovery
failure before any result was accepted for the unfinished batch. It retains completed
rounds, candidates, coverage and earlier audits. Batch 41 needs a new generation
under the new contract. Resume history and migration notes distinguish the mixed
experimental conditions; this is not a fresh uniform-v10 benchmark.

Validation:

- All 286 offline RQ1 tests passed, with five existing dependency deprecation
  warnings. No frontend contract changed; stored role citations and the UI retain
  their existing text/offset format.
- Offline tests cover literal excerpt materialization, repeated text with exact
  offsets, unknown/duplicate IDs, forbidden generated text, empty catalogues,
  bounded schema correction, legacy citation repairs, and narrowly scoped recovery.
- A read-only backup of the actual failed database was replayed in a disposable
  copy with inference blocked. All 40 rounds and 719 processed units were preserved;
  the first requested operation was new excerpt-ID discovery for batch 41.
- All 60 original source batches were catalogued offline: all 1,030 units remain
  covered, with no nonblank text omitted. The largest discovery user payload was
  45,234 characters, below the existing 60,000-character limit. The schema adds its
  own prompt text; this character check is not a measurement of provider tokens.

No model inference was performed while implementing or checking this fix. Live
completion, role semantic quality, extraction coverage and discussion outcomes
remain unvalidated. This fix prevents the quotation-generation failure class; other
malformed model fields, provider failures and invalid panel accounting can still
stop a run visibly. The full workflow remains incomplete with zero requirements.

## Saved-extraction downstream trials

A separate derived run can now reuse completed extraction and identical current-policy assessments. Original-source checks are recomputed; the source run is never rewritten. Offline scripted-client tests cover lineage, stale/partial source rejection, stage exports, no extraction calls and reset prevention. No live acceptance trial has been run.

New/derived normalization now keeps uncited observations solely in a set-aside audit, with export and UI access; legacy runs remain unchanged. This is an offline-tested filter, not a semantic rejection or acceptance decision. The elicitation prompt and policy have not changed.

## Grouped review candidates (13 October 2026)

Semantic consolidation is implemented with bounded ID-only model output, deterministic verbatim representatives, separate obligation variants, failed-member attachments and durable chunk/assessment checkpoints. Exact mode and historical runs retain their earlier behavior. New tests cover passing and failed provenance unions, all-failed complementary premises, accounting correction, visible fallback, negation, oversized inputs, chunk reuse and interrupted derived-stage recovery. Earlier regression fixtures explicitly choose exact mode to preserve their baseline condition.

Validation is offline only: 310 tests pass, the generated workflow schema matches runtime contracts, and the frontend builds. No live KI:connect acceptance trial, new benchmark, semantic grouping accuracy measurement or effort-savings measurement was performed. The original completed MobilityDCAT run remains unchanged. Its results should be interpreted independently of this new consolidation condition. Browser interaction was unavailable to this session, so the new UI has build verification but no visual browser check yet. See [CONSOLIDATION.md](CONSOLIDATION.md) for the pending acceptance and independent annotation checks.

## Extending DCAT-AP rather than rebuilding it — 13 October 2026

The new base-profile condition compares proposals against a pinned DCAT-AP registry
before source verification and assessment. Ordinary inherited restatements are kept
in the set-aside audit; new, tightened, constrained, loosened and unresolved claims
continue to review. Tightening requires a supporting link from outside the configured
base specifications; weakening a base obligation creates a blocking finding.
Uncorroborated model declarations and unrecognized declared constraints remain
provisional, visible review cases. These deterministic classifications are not
semantic correctness or stakeholder endorsement.

The recorded policies are `rq1-normalization-v3`, `rq1-base-check-v1`,
`rq1-independent-elicitation-v3.0` and `rq1-semantic-consolidation-v2` (registry
`rq1-base-registry-v1`). Grouping v2 compares statement text, offers at most the
25 most similar previous groups by word overlap, and separates metadata-presence
claims from consumer/system capabilities. Historical runs retain their earlier
policies; derived runs retain their original extraction policy.

Potentially compound or negated statements, an unconfirmed declared constraint,
an uncorroborated property mapping, and an unclassified base-source distinction
can retain a provisional `inherited` relation while staying active for review.
The relation-label count and actual inherited set-aside count are therefore
different metrics. These guards avoid silently excluding every clause of a
compound claim on the strength of one base match.

Both registry JSONs were built from official SEMIC release files at commit
`4470b8ea907b7eb9ec55ab22befd1ecd2210ff32`. Full input and JSON hashes are documented
in [BASE_PROFILE.md](BASE_PROFILE.md). The 2.0.1 recommended sections were parsed
from the official DOCX; no fallback was taken. Rebuilds were byte-identical, and
eight offline registry tests passed. The official SHACL supplements have source
limitations described there; this comparison registry is not a complete validator
of all profile constraints.

Mobility alone defaults to DCAT-AP 2.0.1. New benchmark-loading operations can
register W3C DCAT 2, DCAT-AP 2.0.0 and 2.1.0 as background and freeze a new snapshot
that excludes their evidence units. Existing source versions, snapshots and saved
runs are unchanged. Derived trials can apply the base check to saved extraction
without repeating it. Fresh extension extraction uses v3 and supplies a compact
base table within the request's input bounds; an unfinished v2.11 extraction cannot
mix in v3 calls.
Only configured base-specification names classify authoritative base sources;
an arbitrary background role alone does not. Exported background provenance is
preserved separately from the snapshot's extraction evidence.

Completed before/after preflight sizing: Mobility changes from 1,030 to 822
evidence units and 61 to 48 selector batches, excluding 208 background units.
Its selected base adds 3,391 characters to the request reserve, and conservative
extraction batches per role rise from 279 to 315. Health stays at 511 units/36
selector batches but changes 158 → 156 extraction batches; GeoDCAT stays 271/19
but changes 81 → 80. These small boundary differences follow stable source-ID/hash
sorting changes rather than an optimization. StatDCAT stays 60/5/20 and JRC stays
59/3/15; EPOS remains unavailable. Character sizing and batch estimates do not
establish provider token use, throughput or latency, and Mobility's combined
corpus/context changes do not isolate a single cause.

No live inference or visual UI check was performed for this change. The full
offline suite passes (422 tests), the exported schema matches the runtime
contracts, and the frontend builds. These checks are not acceptance-run results.

This new condition remains offline-tested only until Junda runs the derived Run A
and fresh Run B and reviews retained and inherited samples. There is no measured
accuracy, effort saving, false-exclusion rate or successful live full-workflow result
under these new policies yet. The model's extension labels and lexical property
matches still need independent review. Corpus coverage, INSPIRE scope, GeoDCAT's
evidence/background role, nonmetadata relevance and other cases' base versions
remain Junda's open decisions.

## 13 October 2026: needs workflow, review branch

The default branch is now `main`. The seven-phase needs implementation is proposed
on `codex/rq1-needs`; it is not automatically merged into the research baseline.
See [RQ1 needs](RQ1_NEEDS.md) for the new definitions, stage order, policies, bounds,
review controls and `needs.json` export.

New agent extractions use v3.1. Derived trials reuse complete legacy extractions
without modifying their wording or source run. Candidates receive deterministic
source checks only; grouped, term-free needs receive classification, optional
necessity linking with a separate critic, one support assessment per retained need
and deterministic ranking. Generic/unlinked/source-only/uncited items remain visible.
Human restoration and revision preserve frozen machine output and require review.
New need acceptance does not require selecting RDF classes/properties or value kinds.

The base catalogues are generated offline from pinned registries and explicitly
**unreviewed**. Their label-based wording must be reviewed before research evaluation;
missing prose definitions have not been fabricated. Catalogue matching has a bounded
retrieval step and can miss generic matches. Classification, rewriting, necessity
and semantic support remain fallible machine judgements. A valid negative critic
verdict is kept, and exhausted corrections do not replay on Resume. Oversized input
fails visibly or requires splitting/human review; selected evidence is not truncated.

Validation: **488 offline tests pass**, with five existing dependency deprecation
warnings. The regenerated schema, reproducible catalogue checks and production
frontend build pass. An isolated
browser fixture checks the need cards, obligation alternatives, source/member
panels, RQ2 hints, export links, scoping form and set-aside controls. Its name clearly
identifies synthetic data; no model provider is called and nothing is accepted.
Historical regression fixtures explicitly select their original candidate pipeline.
This is implementation validation, not a live success/accuracy/effort-saving claim.
The repository-root test discovery also encounters Sebastian's unrelated inherited
plotting script, which needs its separate plotting dependencies; the documented
RQ1 test command targets `tests/`.

No live run, reference scoring, freeze tag or human review has been performed for
this condition. Junda's revised decisions (14 October, replacing the earlier choices): D1 needs use
"[Actor] can …" without obligation words; obligation counts only when quoted,
otherwise it is "not stated by sources". D2 Junda authors dated use cases from each
development case's stated purpose before running; scoping off is a reported
comparison. D3 needs with no verified use case stay visible/restorable asides;
evaluation reports recall with and without these needs. D4 proposal quotes must
support their information/capability before merging. The fixes implementing these
decisions are recorded separately on this review branch.
Mobility remains held out. Prior heuristics were adjusted while reading Mobility
candidates, never reference rows; disclose this in the paper. Test development
cases first, review base catalogues, then authorise a functional Mobility derived
check using counts/calls/errors only. Freeze before reference-based evaluation.
