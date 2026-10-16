# Source-grounded stakeholder role selection

The persistent RQ1 workflow can select a stakeholder panel automatically from a
frozen source corpus and its declared competency questions. This is stage **3a**,
inside elicitation; stage **3b** runs the selected extraction perspectives.
Construction, AAS and IFC perspectives are no longer the default panel in the UI.
The nine research stages and existing manual-panel API remain compatible.

## Use in the UI

1. Save and select eligible sources, then enter the CQs/tasks. Label held-out answers
   **evaluation reference**; these and **background** sources are excluded from snapshots.
2. Choose **Independent agents · configured provider** and **Select roles from
   sources and CQs**. Set a maximum panel size (default 4, range 1–8).
3. Explicitly allow the configured provider and start the saved workflow. In automatic mode selection proceeds into extraction. Step-by-step mode saves the
   panel and pauses before extraction for review.
4. Inspect **Stakeholders and role selection** for stakeholders, basis, remit, focus
   questions, selection rationale and exact source quotations. The evidence inspector
   resolves citations against original source bytes.
5. Download the role manifest or open its selection audit to inspect candidates,
   grouping decisions and omissions. Review/baseline exports preserve the manifest too.
6. To change a panel, finish or stop the active run, then choose **Override panel in
   a new run**. Edit/remove/add perspectives and supply a rationale. A new run uses the
   same source/CQ snapshot and records the original run, parent manifest hash and local
   reviewer identity. Extraction runs again. Original outputs and human decisions stay
   intact. Overrides never silently rewrite a completed experiment.

**Perspective demo · offline mock** exercises this path without any model service.
It deliberately proposes generic consumer/publisher roles and labels them as a demo;
it does not claim to identify stakeholders. **Rules baseline · offline** skips panel
selection. **Use a fixed panel** retains the original configured perspectives for
controlled comparisons. Dynamic roles and manual overrides do not replace procedural
source verification, support/quality assessment or the grounding/scope critic.

## Role contracts and authority

Each role records:

- Stakeholder group names, a role label, a purpose and up to three focus questions.
- `documented`: the selector claims that an actor/responsibility is explicit in a
  source; at least one authentic exact quotation is required.
- `inferred`: a perspective inferred from source activities or declared CQs; at least
  one source citation or valid task ID is required.
- `proposed`: a possible useful perspective with an explicit rationale. It carries
  no claim of actual stakeholder consultation.
- Source citations, task IDs, selection rationale and candidate lineage.

All supplied role citations must resolve inside the permitted corpus. From policy v10,
discovery selects up to two `source_span_ids` from an ordered excerpt catalogue; it
does not generate quotation text or character offsets. Each excerpt is at most 400
characters. All nonblank source text is exposed in order, with unit metadata and
without a duplicate full-content copy. Only this batch's excerpt IDs are accepted:
the discovery schema lists those IDs as an enum, rejects duplicates and forbids
generated quotation fields. The software attaches the original evidence ID, text
and offset, then performs the usual source-byte and task-link checks. Raw selected
IDs, materialized candidates, catalogue hash/count and validation reports are saved.
The same catalogue can be reconstructed from the frozen batch.

Each stored quotation must be one literal,
contiguous substring of the cited evidence unit's `content`, preserving spaces,
line breaks and hyphens. A short actor/responsibility phrase is sufficient; agents
must use separate links for separate passages rather than reconstruct a sentence.
For historical responses and manual overrides, the validator derives a character
offset when the quote is unique. A repeated quote
requires its zero-based offset within that unit or a longer unique quote. An absent
quote requires corrected text or a corrected evidence ID; an offset cannot fix it.

Each discovery response is preserved before validation. The audit distinguishes
`quote_absent`, `quote_ambiguous`, `invalid_offset`, `outside_batch`, `unknown_task`
and `source_unresolved` per candidate and citation. Citation errors get at most one
targeted correction call per batch. In policy v3 and later, that call selects numbered source
excerpts instead of generating quotation text or offsets. Up to policy v5 each
excerpt was a raw physical line (split at 400 characters when needed). From v6 an
excerpt is a block of consecutive lines of one unit, at most 400 characters long and
never crossing a blank line, as described in
[EXTRACTION_CITATIONS.md](EXTRACTION_CITATIONS.md). Its original unit and offset are
saved in the audit. The software materializes the chosen exact quotation;
it does not fuzzy-match a paraphrase. An empty selection with a nonblank explanation
retains the candidate as **proposed**, removes its source citations and replaces its
documentary rationale with an explicit human-review disclaimer. The original proposal
and the model's explanation remain in the audit; no source support is invented.
Since `rq1-citation-repair-fallback-v1`, a candidate the single correction leaves
unsupported is retained the same way, instead of stopping selection: a correction
that is missing, names an unknown or repeated span ID, or still fails validation. Its
disposition reads `retained_as_proposed_after_failed_repair`; corrections for other
or repeated candidate indices are ignored and listed in the repair's `fallback` audit.
A correction call that returned no answer (provider failure or interruption) is asked
again on Resume, with the failed attempt kept in `retries`
(`rq1-citation-repair-retry-v1`). Choosing an authentic excerpt
does not establish semantic support: the excerpt may still be irrelevant.
For nonempty excerpt selections the correction changes only invalid candidates'
citations: their labels, basis, stakeholder identities and remit stay unchanged.
Valid candidates cannot be replaced. Original responses, corrections and both
validation reports remain in `role_manifest.validation_attempts`. A correction never
silently drops candidates or triggers generic fallback. The UI exposes proposed
dispositions and panel correction attempts.
Source resolution errors and unrelated provider errors do not trigger citation repair.

In automatic discovery, an undeclared task ID is discarded rather than guessed or
remapped. Valid task IDs and all source citations are retained. If an inferred role
loses its only support, it becomes an explicitly **proposed** perspective for human
review. `task_reference_normalization` records removed/retained IDs and any basis
change, alongside the unchanged raw response and its original validation errors.
This deterministic operation uses no model call. It does not repair quotations,
certify semantic relevance or bypass source integrity. Human panel overrides still
reject undeclared task IDs instead of correcting them automatically.

Quote authenticity is deterministic; semantic correctness of a documented/inferred
classification is still a model or author judgement. The UI states this distinction.

A stakeholder role is task context, not a requirement premise. Extraction and discussion
receive its full remit and basis, but still have to justify each requirement separately.
Agreement among simulated roles is not stakeholder endorsement. The discussion panel
reserves a slot for the grounding/scope critic even when many roles contributed.

## Whole-corpus selection and restart (v12)

The policy is `rq1-stakeholder-selection-v12`. It separates discovery, registry
construction and panel selection. Previously the retained panel was chosen again
after every batch, so an omitted stakeholder could not return in a later decision.
V12 retains every discovered candidate until the final whole-registry decision.
It removes that incremental elimination, without claiming that model judgements
or the bounded grouping procedure are semantically perfect.

1. **Discovery reads the complete frozen corpus.** The prompt, excerpt-ID contract,
   candidate limit, source checks and single citation correction are unchanged from
   v11. Each batch contributes candidates and a saved validation audit; it does not
   select a panel. Source batches have at most 40,000 serialized characters. The
   run counts its required batches at creation and keeps that size on resume, with
   a ceiling of 128. `RQ1_ROLE_SELECTION_MAX_BATCHES` remains an optional smaller
   cap. An oversized corpus or unit is refused rather than scanned partially.
   Candidate IDs derive from their complete content, without a batch-order suffix.
2. **A lossless registry groups equivalent perspectives.** Bounded per-source calls
   are followed by cross-source grouping. Every candidate must occur in exactly one
   entry; omissions are forbidden. Registry contracts permit up to 1,024 groups and
   1,024 members per group, independently of the eight-role panel limit. Exact
   repeated IDs within the same group are collapsed and audited, preserving their
   first occurrence. Unknown or missing IDs, conflicting groups and invalid
   representatives get one saved accounting correction per call; an answer still
   invalid after it is completed by the accounting repair described below.
   The representative's label, purpose, focus questions and basis remain unchanged.
   Any entry containing a documented member must choose a documented representative.
   All member citations remain in the registry. Source names and batch counts are
   computed from those citations and batch records, never supplied by the model.
3. **One final panel decision sees every registry entry and the actual declared
   tasks.** Every entry receives a relevance verdict and reason. Each verdict first
   copies its entry's exact label, then the entry ID, so that a verdict which drifted
   to a neighbouring ID is detectable (see the label check below). Discovery task
   links are hints. Relevance is judged by what a stakeholder does with the data, on
   either side of a use case: people who ask the questions or carry out the tasks
   (finding, judging or using the data), and people who publish or maintain the data
   the use cases are about. Being mentioned in a use case is not the criterion: people
   asking which datasets an organisation provides are relevant users, and that
   organisation is relevant as a publisher. Within the basis priority below, when
   relevant entries exist on both sides, the panel keeps at least one of each. (A
   functional Mobility run judged every user-side entry irrelevant, documented ones
   such as Business & SME Re-users and Data User included, because its competency
   questions ask about providers and owners. The rule was made explicit after that
   run; no reference requirement was consulted.)
   More documenting sources break ties; a single source is not a
   reason to exclude an otherwise relevant perspective. Program checks enforce
   documented/relevant entries first, inferred/relevant entries next, then proposed/
   relevant entries, filling available places up to `max_roles`. One accounting
   correction is permitted; a still-invalid answer is completed by the accounting
   repair described below. Selected roles record `filled_via` as `documented`,
   `fallback_inferred` or `fallback_proposed`. Their page shows basis, source names
   and this fill reason. All unselected entries and verdicts remain saved.
4. **Defaults apply only to a complete scan with no candidates.** These remain
   proposed and uncited, with `filled_via: default`. A failed provider or a
   nonempty registry judged entirely irrelevant does not invoke defaults: selection
   stops for review.
5. **Resume preserves completed work and correction budgets.** Discovery batches,
   registry decisions and the final panel decision are checkpointed. Corrections
   are claimed before calling the provider. An answered correction is never
   repeated; one that returned no answer (provider failure or interruption) is
   issued again on Resume, with the failed attempt kept in `correction_retries`
   (`rq1-stakeholder-correction-retry-v1`). Completed manifests are sealed immutable artifacts.
   Completed older panels remain readable and usable. Unfinished pre-v12 scans are
   refused; the older narrow v6–v10 failure migrations are not used to enter v12.
   Create a new run, or use a compatible completed scan as described below.


### Documented registry representatives

`rq1-registry-documented-representative-v1` applies a deterministic rule after
registry membership passes every accounting check. If the model chooses an inferred
or proposed representative for a group containing documented members, the service
uses an existing documented member of that same group. Ties use the smallest entry
ID. A valid documented choice is left alone. The chosen member's existing label,
purpose, questions and basis are copied unchanged; an inferred candidate is never
relabeled as documented. Group membership, rationale and all citations are preserved.
This does not verify the model's judgement that those members are equivalent.

Raw responses remain in `registry_calls.original` / `correction.original`. Changes
are recorded separately in `representative_normalizations`, with policy, phase,
old/new representative IDs and group membership. This rule cannot fill gaps or
decide conflicting memberships; those go to the accounting repair below. Diagnostic messages name
the actual validation codes rather than calling every failure an accounting error.

A v12 registry decision whose saved correction failed **only** this documented
representative check can be recovered on Resume without a new call for that
checkpoint. The service reconstructs the same request/key, checks its input hash,
and revalidates the raw correction and its saved normalization/errors before
applying the rule. The original invalid correction and its audit stay unchanged;
a `recovery` record and manifest migration note describe the changed condition.
Completed discovery and valid registry decisions are reused without changing their
prompt, schema, model or checkpoint keys. Unfinished downstream decisions still
need their normal calls. Other invalid saved corrections go to the accounting repair.
A saved valid correction is reused even if interruption prevented its completion
marker from being saved.

Registry prompts use stable ID ordering; candidate and batch report order does not
change the registry inputs or final panel prompt. Each merge payload is bounded to
18,000 characters, leaving room for its answer and correction within the 60,000
character request limit. Cross-source rounds alternate two content-based block
orders: by the label's head noun, singular (so 'Data Owner' and 'Data Owners' from
different sources, or all '…provider' entries, share a block), then by entry ID. Each
request still lists its entries in ID order. Rounds stop when one bounded block
remains or neither order reduces the registry any further. Per-source rounds are
unchanged. (Blocks formed only in entry-ID order left five labels duplicated in the
functional Mobility registry.) Equivalent perspectives that never share a bounded
block can still remain separate; no forced merge or silent truncation makes them fit.
The final panel decision receives the whole registry when its request fits 32,000
characters, so that the request plus its invalid answer still fits one correction
within the 60,000-character limit. A larger registry is decided in two parts.
First, stable blocks in entry-ID order each give every entry exactly one relevance
verdict and keep none (`relevance_block` rounds). Then one decision chooses the
panel among every entry judged relevant (`relevant_entries` round), with the same
priority checks and fill labels as above. That choice sees a compact view: label,
stakeholders, basis, purpose, source names, source count and task hints, without
focus questions. Entries judged not relevant in a block are saved as omissions with
their reasons. If the compact object view still exceeds the budget, the final choice
uses a lossless table: `entry_fields` names the shared columns and every `entries`
row retains that entry's exact field values (`entry_encoding: rows_in_entry_fields_order`).
This avoids repeating JSON field names; it does not shorten descriptions, change IDs,
remove sources/tasks or select a smaller shortlist. `panel_input_compactions` records
`rq1-panel-choice-table-v1`, entry count, columns, both character counts and payload hash.
Only an oversized final choice uses this representation; existing object requests and
completed relevance checkpoints keep their keys. If no block finds a relevant entry,
selection fails explicitly.

If even the table exceeds the budget (`rq1-panel-choice-reduction-v1`, recorded in
`panel_choice_reduction`), the choice first offers only the bases that can still hold
a place under the program-checked rule: with at least `max_roles` relevant documented
entries, inferred and proposed entries could never be kept, so they are not offered;
they stay saved as relevant omissions. If that is still too large, stable blocks in
entry-ID order each nominate up to `max_roles` entries under the same rules
(`nomination_block` rounds, a nomination prompt that names the later choice), and one
decision chooses the panel among all nominees (`nominated_entries` round). Every
entry keeps a verdict: the final one, its nomination block's, or its relevance
block's. A block applies the documented-first rule to its own entries, so the final
choice still fills places documented first. Entries are never dropped to fit. These
are character bounds, not guarantees about a provider's token context window.

### Exact missing-verdict corrections

`rq1-stakeholder-missing-verdict-patch-v1` handles one narrowly defined response
shape: an initial relevance/panel answer omitted some verdicts, and its single
correction returned exactly those missing verdicts instead of repeating the whole
list. The original must fail only `verdict_accounting`, with missing IDs but no
unknown or repeated IDs. The correction must contain each missing ID exactly once
and no other verdict. The service preserves the original verdicts and reasons,
appends the correction's verdicts and reasons, and uses the correction's explicit
`kept_ids` unchanged. The combined object must pass every existing check, including
full coverage, relevance, role limit, basis priority and filling available places.
This rule never invents a verdict or selects a stakeholder itself.

Raw responses stay in `original` and `correction.original`. A separate
`verdict_compositions` audit records the policy and phase, which verdict IDs came
from each answer, both kept-ID lists and the combined result hash. A newly composed
correction stores the fully validated result. For an already failed saved correction,
Resume first reconstructs and checks both saved validation reports and the correction's
normalized result against its raw answer, as well as the frozen request hash. Recovery
leaves that invalid correction and its audit unchanged, stores the combined result
separately and adds a zero-call `recovery` record and migration note. Completed discovery,
registry and relevance calls keep their keys and results. No new correction budget
is granted. Other shapes (overlapping, contradictory, extra or still missing verdicts,
invalid panel choices) go to the accounting repair; inconsistent saved audits still stop.
This establishes response completeness, not semantic correctness or stakeholder endorsement.

### Accounting repair after the single correction

`rq1-stakeholder-accounting-repair-v1` completes a registry, relevance-block or
final-panel decision whose single correction is still invalid, by program rules and
without a model call, instead of stopping the run. It was added after a functional
Mobility re-selection stopped at its 11th registry decision: the first answer placed
one entry in two groups and chose an inferred representative; the correction fixed
both but miscopied one 24-digit entry ID by a single hex digit.

- **Miscopied IDs.** An unknown ID is restored to an offered ID only when exactly one
  offered ID lies within two character edits, that ID is the one the answer left
  out, and no other unknown ID maps to it. Entry IDs end in 24 random hex digits, so
  different entries are never this close by chance; anything ambiguous stays unknown.
- **Registry.** Starting from the correction (the model's latest complete answer),
  other unknown IDs are dropped, and an entry the answer leaves out or places in
  several groups becomes its own entry. No merge is inferred; every repaired group
  is a group the model formed, or part of one. Representatives follow the
  documented-first rule above. Every candidate still occurs exactly once.
- **Relevance blocks.** The correction's verdicts supersede the first answer's, and
  the first answer supplies entries the correction left out. Unknown IDs are dropped.
  An entry given both verdicts in one answer counts as relevant, so that the final
  choice judges it again. Entries still without a verdict are judged in a follow-up
  block (`relevance_follow_up` round, a new request). A block that keeps no usable
  verdict at all passes its entries to the final choice, which judges them.
- **Labels.** A verdict whose label is a different offered entry's label judges that
  entry (`verdict_label_mismatch`). It moves to that entry when exactly one entry has
  the label, and is dropped when several share it; the entry it vacated is then judged
  in a follow-up. Labels are compared ignoring case, spacing and dash variants. A
  paraphrased label that names no offered entry is not an error: the ID stands. This
  was added because, in the functional Mobility run, 3 of 107 relevance reasons
  described a neighbouring entry (the Regulator's verdict carried the reason written
  for Businesses and SMEs, and vice versa).
- **Final choice.** Verdicts are merged the same way. An entry the answer does not
  judge keeps its relevance-block verdict; one with no verdict at all gets a
  follow-up block, and is recorded as not judged (not relevant, with that reason)
  only if that also returns nothing. Kept IDs are restored when miscopied and
  reduced to distinct relevant entries. The places are then filled by the program-
  checked rule: documented, then inferred, then proposed; within each basis the
  model's own picks first, then more documenting sources, then entry ID.

Raw answers and the invalid correction stay unchanged. Each decision records a
`repair` audit (policy, phase, every change, `model_calls: 0`); a completed final
choice adds `panel_composition` with the model's kept IDs and the filled ones. A
saved failure recovers on Resume with zero calls after the same frozen checks as the
other recoveries. The repair establishes complete accounting, not that the model's
groupings or relevance judgements are correct. Selection still stops when no entry
is relevant, the provider fails, or saved audits are inconsistent.

### Answers that fail their output contract

Before `rq1-role-selection-output-recovery-v1`, one invalid row stopped the run: for
example a discovery candidate that breaks the basis rule (a documented role without a
citation, or an inferred one with neither a citation nor a declared task). A development
run stopped on such a `value_error` on 16 Oct 2026. The provider client still makes its
single schema correction. When that answer also fails:

- **Discovery.** Every usable candidate of the complete answer is kept. Unknown or
  repeated excerpt IDs, undeclared task IDs and unexpected fields are removed. A
  documented role left without a citation, or an inferred one without support, is kept
  as proposed and uncited, with the human-review rationale. Each row is then checked
  against the stored role contract; a row that still fails is dropped and reported.
  The batch's validation attempt keeps the raw answer and every row's disposition under
  `output_recovery`. A cut-off answer is asked once more with 16,000 output tokens.
- **Citation repair.** Usable corrections are kept. A candidate left without one is kept
  as proposed and uncited, as in the fallback above.
- **Registry, relevance and panel decisions.** Rows that pass their own contract are
  kept; a failing `kept_ids` falls back to empty. The decision then continues through
  its accounting correction and repair, which treat a dropped row like an entry the
  answer left out. A correction with nothing usable leaves the first answer for the
  repair to complete. Each decision records `output_recoveries`.

A run still stops when an answer has nothing usable in it: no JSON object, a second
cut-off, or a first registry or panel answer in which no row passes. Resume asks again.
Provider failures stop as before. A scan with recovered batches can still seed a new
panel: its kept candidates are re-derived from the saved raw answer, without a model
call, and must match.

Discovery reserves 8,000 output tokens (16,000 for its one retry after a cut-off),
citation correction 5,000, and registry/panel calls 8,000 each. Each logical call may
use the existing one structural schema repair generation. A provider `length` finish
reason fails even if partial output looks like JSON. Provider retries can add HTTP requests. Citation and accounting
correction budgets survive restarts. No upper-bound call estimate is presented as
measured runtime or token usage.

Checkpoint keys and resume comparisons use only provider, base URL, model and
reasoning effort. Timeout, concurrency, retries and backoff can change without
invalidating semantic work. Full provider descriptions remain in call audits.
Changing a model still changes checkpoint keys and refuses mixing generations in
an unfinished selection/extraction. See [per-step models](STEP_MODELS.md).

## A separate panel trial from saved discovery

On a completed automatic run's **Stakeholder roles** page, choose **Choose a new
panel from this saved discovery scan**. This opens the same downstream settings as
the step-4 trial form, plus **Progression**. **Step by step** is the default here:
the new registry and panel are saved, then the trial pauses before fresh extraction.
Automatic mode continues through the machine stages. The source run is unchanged.
No extraction, assessment, discussion or human decisions are copied into this trial.

Only complete automatic v11/v12 scans qualify. The source snapshot, evidence
coverage, discovery prompt and exact batch payload hashes, candidate/output limits,
contract, saved generated candidates and citation validation must match. New calls
record a schema hash. V11 predates that field: its known excerpt-ID contract is
checked using its policy, citation policy, exact prompt/payload hashes, contract
name, limits and revalidation of saved generated output against the current schema.
Other missing schema hashes are refused. Derived chains preserve the original
contract policy in their lineage.

The new manifest copies candidates and validation/repair records and pins
`discovery_reused_from` with the source run ID and manifest hash. Original discovery
call records are stored separately from the new run's model-call log, so new cost
counts include only new work. Their old provider does not bind registry or panel
generations to that model. Newly generated decisions are bound to the new trial's
configured selection model. Extraction starts afresh under its configured step model.

## API

`POST /api/rq1/v2/runs` accepts the existing fields plus:

```json
{
  "snapshot_id": "<saved snapshot>",
  "strategy": "multi_agent",
  "role_selection": "automatic",
  "max_roles": 4,
  "allow_live_provider": true
}
```

The API defaults to `role_selection: manual` for compatibility with existing callers.
The UI defaults to automatic selection when an agent/demo strategy is selected.
`role_ids` is used only for manual panels. The usual provider opt-in remains required.
No hosted fallback or provider credentials are introduced by this feature.

For a human override, create another run using `role_selection: override`,
`based_on_run_id`, `override_rationale` and `role_overrides` containing role proposals.
The original manifest must be complete and the snapshot identical. The server verifies
citations and records its trusted local reviewer identity; callers cannot supply a
reviewer name. Use the generated v2 JSON schema for the full contract.

To reuse completed discovery, send `POST /api/rq1/v2/runs/<source-run-id>/derive`:

```json
{
  "expected_version": 123,
  "start_from": "role_selection",
  "name": "New panel from saved discovery",
  "execution_mode": "stepwise",
  "allow_live_provider": true,
  "rationale": "Review the whole-corpus panel before fresh extraction."
}
```

`step_models` may be supplied, using the existing model-list validation. A live
provider is contacted only after explicit opt-in. Creating the trial does not
change its source, including when compatibility checks refuse creation.

## Experimental interpretation and validation

Role selection belongs to the full workflow's cost. Evaluation exports separately report
selector call count, failures, summed latency, output reservations, coverage and role
basis counts. Reported provider token usage is retained when supplied; missing counts and monetary
cost remain unknown.
No requirement recovery, labour saving or human-review effectiveness is inferred.

The source label is a boundary, not a document classifier. A target answer uploaded as
an ordinary source remains an input. Curators must establish source/section eligibility
before upload, especially for mixed workshop minutes and reports containing final answers.
Snapshot exclusions are evaluator audit metadata; they are not sent to selection agents.

Offline scripted-provider tests cover full discovery-to-discussion use, held-out source
exclusion, bad citations and reducer outputs, context limits, restart without rediscovery,
manifest integrity, immutable override lineage and critic preservation. They also cover
absent/repeated quotations, invalid offsets, targeted correction, retained originals,
unchanged valid candidates, exhausted correction budgets and policy compatibility.
The v12 change was tested offline; no live provider run or new browser execution was made.
These checks do not
establish live provider quality or role-selection stability.

## Preparing sources without reading every page

Upload the original text-based documents; manual sentence extraction or quotation
offsets are not a curator task. The parser groups PDF lines into bounded passages
while retaining their exact extracted text and page/source locations. Start with a
brief inventory: document title, publisher, date/version, purpose, relevant sections,
and whether it contains the target profile's final answers. Use this to establish
eligibility and distinguish source evidence from held-out evaluation references.
For mixed documents, review the relevant sections before treating them as inputs.

After ingestion, spot-check the parsing status and a few representative passages,
especially tables, multi-column layouts and known stakeholder sections. Review the
proposed role list, its documented/inferred/proposed labels and linked quotations.
You do not need to read every page to fix ingestion errors or hand-select every role,
but exact quotation matching alone cannot establish that a document is eligible or
that the inferred perspective is semantically correct. A brief summary is a review
aid, not a substitute for the original source evidence. Scans without usable text
need OCR before ingestion; the workflow reports that failure rather than inventing
missing evidence.

## Scripted call-count comparison

The offline 48-batch regression uses 13 synthetic sources, 48 candidates, no
citation/accounting/schema corrections and a scripted merger that combines each
source's equivalent candidates and then combines the source entries:

| Logical call | Previous incremental flow | v12 whole-registry flow |
| --- | ---: | ---: |
| Discovery | 48 | 48 |
| Per-batch panel selection | 48 | 0 |
| Per-source registry merges | 0 | 13 |
| Cross-source registry merge | 0 | 1 |
| Final whole-registry panel | 0 | 1 |
| Total | 96 | 63 |

This counts logical calls under the stated fixture, not live performance, quality,
Mobility results or savings in human effort. Real registry sizes, corrections,
provider retries and model output lengths change the counts.
