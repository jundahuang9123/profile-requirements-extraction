# Source-routed extraction and stakeholder mediation

Protocol `rq1-routed-mediated-v1` is selected with
`stakeholder_workflow: "routed_mediated"`, `output_form: "needs"` and
`discussion: "automatic"`. Historical runs retain the independent protocol.
New automatic multi-agent runs in the workbench select this protocol.

## What each step does

1. Acquisition/decomposition freeze the source versions, locations, text and
   evidence IDs. Role selection supplies the stakeholder panel and its basis.
2. At step 3b the extraction model assigns each evidence section to the concerns
   it actually documents. Author identity is not an assignment rule. Specific
   sections have one stakeholder, shared sections can name several perspectives
   with a reason, and uncertain sections use a neutral shared extractor. Every
   section must be accounted for. Invalid routing accounting receives one
   correction; a still-invalid answer uses an explicit, audited shared fallback.
   A transport/schema failure stops safely rather than inventing assignments.
3. Each assigned role reads its assigned sections in bounded batches. This is
   one planned extraction pass, not a sequence of completeness searches.
   Recovery reuses accepted batches and processes only unfinished assignments.
   The extraction policy is `rq1-routed-elicitation-v1`; old extraction is not
   relabelled as routed extraction.
4. Existing normalization, strict source verification, base comparison, scoping
   and semantic consolidation produce a common pool. Deduplication retains
   parent IDs and evidence; related but distinct conditions, actors, scopes and
   obligations must remain distinct. Rejected and uncertain proposals remain
   inspectable. Base-only material is still set aside by the configured base
   check. Scoping is off when explicitly requested; no use cases are invented.
5. The pre-discussion machine result is frozen. Every active need enters a
   bounded discussion case, grouping overlapping source passages where possible
   (at most four needs). All selected stakeholders review the common list; the
   shared extractor is procedural and is not a stakeholder voter. Later turns
   see previous contributions. The task is to identify compatibility, overlap,
   interference, source disputes and evidence gaps, not rank stakeholder status.
6. A separate mediator accounts for every parent need and saved concern exactly
   once. It may retain, revise, merge, propose an evidenced addition, provisionally
   resolve an explicitly prioritized conflict, or defer with alternatives and a
   precise human question. Neither majority vote nor silence establishes consent.
   Cross-case conflicts cannot be automatically resolved.
7. Changed proposals receive an independent semantic check, exact original-span
   validation, obligation checks and semantic assessment. Unsupported changes
   are blocked with their drafts/questions preserved; the original needs stay
   current. Accepted machine changes create linked revisions, never human
   acceptance. New wording has its stale base/scope classification cleared and
   is marked `base_and_scope_recheck_required` for review. This protocol does not
   automatically rerun all downstream classifications after mediation.
8. The run stops at human review. Approvals, rejections, edits and trade-offs are
   separate human decisions. There is no automatic publication or approval.

## Bounds and recovery

Cases allow two rounds, at most `2 × panel size + 6` generation attempts, 4,000
initial / 8,000 retry output tokens, a recorded total reservation, and 1,800
seconds of cumulative discussion generation time checked before another
generation. The time bound is cooperative, not a process-kill deadline; an
in-flight request is governed by the provider timeout. Payloads over 45,000
characters stop without truncating evidence or discussion. Source contexts are
bounded when cases are planned; exceptionally large transcripts can still
require preparation rather than silent loss. Rejected generations consume the
recorded budget. Exhausted budgets do not reset on resume.

Routing plans bind source contents, snapshot, roles, policy and actual model.
Discussion binds the frozen requirements/evidence and participant/model identity.
Saved contributions, mediator plans, critic decisions and revision assessments
are reused at compatible checkpoints. The worker lease prevents concurrent
execution. A protocol change requires a separate extraction trial from step 3b;
the parent run remains unchanged. A failed assignment is partial coverage, not
an empty successful extraction.

## Traceability in the run

`stakeholder_audit` stores routing attempts, accepted assignments/fallbacks,
stage input/output hashes, the discussion plan, mediator and independent-check
checkpoints, revision assessments and final outcomes. Existing model-call logs
record contract, model/options, input/output hashes, returned structured output,
usage where available, elapsed time and failure. Exact source links, observation
IDs and revision parents connect the generated needs to the original material.

The **Run trace** panel on each step shows assignments, stage outputs and a
need's genealogy, source excerpts, checks, concerns and human decisions. The
discussion page shows mediator outcomes, alternatives and review questions.
`GET /api/rq1/v2/runs/{id}/trace?download=true` downloads the complete trace.
Stage exports and `needs.json` include the stakeholder audit and deliberations;
the full run export also preserves all saved parts. Credentials and private
reasoning are not exported.

The main `needs` list follows current revisions. Compact selection and family
views remain explicitly frozen pre-discussion machine views, so they must not be
reported as the mediated list. Evidence passage coverage measures processing,
not semantic completeness. Simulated stakeholders, source support and successful
execution do not establish accuracy, effort savings or real stakeholder consent.

## Verification

Synthetic offline tests in `tests/test_routed_stakeholder_workflow.py` exercise
exhaustive routing/fallback/overlap rules, assigned-only extraction and checkpoint
reuse, contradictory accounting, explicit priority requirements, unsupported
changes, source quotations, revision lineage, immutable pre-discussion output,
legacy compatibility, UI-export audit contracts and the complete machine flow.
No evaluator reference answers or mock evaluation findings are inputs to these
contracts or prompts.

## Mediator handoff recovery: `rq1-evidence-mediation-v2`

The first live trial exposed a handoff failure: the mediator treated responses to
concerns as additional need actions, repeating parents, leaving explicit links
empty and mistyping a long concern ID. No invalid revisions were applied.

The v2 handoff separates final need dispositions from concern dispositions. It
uses exact, field-scoped `N1`/`C1`/`E1` references and a required-accounting
manifest. A saved alias map restores the original run IDs; source quotations,
need wording and rationale are never rewritten by aliasing. Unknown IDs still
fail validation. The correction receives the actual rejected answer and specific
missing/unknown/repeated IDs. Findings of *no* interference link to retained
needs; they are not conflict-resolution actions. A retained need can carry an
unresolved human question without being duplicated in another action.

Only an invalid v1 mediator checkpoint is eligible for this versioned recovery.
Its original answer and audit are preserved, and v2 uses a new checkpoint key.
Accepted v1 plans remain usable without another generation. Completed extraction
and stakeholder contributions are reused, and cumulative attempt, output and time
budgets do not reset. Each v2 plan has at most one accounting correction; exhausted
invalid v2 checkpoints cannot trigger repeated corrections by pressing Resume.
Transport interruption before a pending correction completes can resume that
unfinished correction. Source/priority/obligation checks remain unchanged.
## Separate human questions (`rq1-evidence-mediation-v3`)

The v2 live trial completed four cases, then exposed a further structural ambiguity: a mediator retained a need but also produced two defer actions for its separate obligation and scope questions. Its bounded correction removed the repeated parents, leaving invalid parentless defer actions. Neither answer was applied.

V3 uses a wire contract with three distinct collections. Existing-need actions require nonempty current parents and exclude `add`; source-backed additions have no parents; human-review questions have their own IDs, current need IDs, saved concern IDs, alternatives and rationale. Several questions may refer to the same retained need without creating extra dispositions. Concern/question links must be reciprocal, unknown links remain errors, and unresolved concerns require a linked question. Questions never create, revise, discard or approve a requirement. The final action partition, citation/entailment/obligation gates, explicit-source priority rule and independent critic are unchanged.

The saved internal plan and case outcome keep all questions separately; UI and trace exports expose them next to the related need and concern IDs. The run's final question count includes these records. Legacy action-attached questions remain readable. Historical v1/v2 accepted plans and critic hashes remain reusable; completed cases are skipped. A rejected earlier plan may recover under v3 only after its exact frozen context, messages, aliases and model match. The archived earlier answer, errors, implementation hash and counters remain in the run. No per-case budget is reset, and v3 itself permits only one semantic correction. A failed v3 plan is not blindly retried.


### Exact stakeholder references (review policy v2)

Stakeholder contributions now use short, field-scoped need/evidence aliases, translated losslessly back to the frozen case IDs. Unknown IDs are rejected; no approximate identifier repair or source substitution is performed. Each contribution has a context/model/alias-bound checkpoint with the actual rejected answer and validation errors, allowing at most one semantic correction within the existing case call/output/time budgets. An interrupted correction resumes only its unfinished attempt. Validated contributions are reused without regeneration.

For a failed legacy contribution, only an exact context-hash and provider/model match permits archiving its rejected answer as a versioned recovery record. Original call logs and completed messages/cases remain unchanged. The new contribution records its review policy in the saved run and exports. This recovery changes reference handling, not evidence, stakeholders or extraction coverage.

### Mediator v5 linked-question recovery

One HealthDCAT deliberation checkpoint exposed a response-shape mismatch: a deferred
action omitted its action-level question and alternatives even though the same saved
plan contained one question covering that exact need and the reciprocally linked
concerns. The bounded correction then omitted the question while retaining its
question IDs, so the case stopped before applying any outcome.

Mediator v5 copies the exact question and alternatives into a deferred action only
when one unique plan question covers exactly the action's parent needs and every
question concern links back to both that question and action. Missing, ambiguous or
non-reciprocal links are left invalid. New outputs record this structural repair in
the attempt audit. For an unchanged v4 context/model/grouping, migration checks the
saved v4 plan and attempts in order; the first fully valid answer after this
data-preserving repair is checkpointed under v5 without another model request. The
entire v4 checkpoint, original validation failures, selected attempt and repair
fields remain in the versioned history. No source text, concern, alternative,
stakeholder message, budget, requirement or human decision is created or discarded.
