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
3. Explicitly allow the configured provider and start the saved workflow. Selection
   proceeds straight into extraction; routine human approval is not required.
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

All supplied role citations must resolve inside the permitted corpus. At discovery,
only the current batch's IDs are accepted. Each quotation must be one literal,
contiguous substring of the cited evidence unit's `content`, preserving spaces,
line breaks and hyphens. A short actor/responsibility phrase is sufficient; agents
must use separate links for separate passages rather than reconstruct a sentence.
The validator derives a character offset when the quote is unique. A repeated quote
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
it does not fuzzy-match a paraphrase. An empty selection with an explanation, an
unknown ID or duplicate IDs stops selection visibly. Choosing an authentic excerpt
does not establish semantic support: the excerpt may still be irrelevant.
The correction may change only the invalid candidates'
citations: their labels, basis, stakeholder identities and remit stay unchanged,
and valid candidates cannot be replaced. Original responses, corrections and both
validation reports remain in `role_manifest.validation_attempts`. A failed correction
stops selection visibly; it never drops unsupported candidates, silently changes
documented roles to proposed roles, or triggers generic fallback. Task/source
resolution errors and unrelated provider errors do not trigger citation repair.

Quote authenticity is deterministic; semantic correctness of a documented/inferred
classification is still a model or author judgement. The UI states this distinction.

A stakeholder role is task context, not a requirement premise. Extraction and discussion
receive its full remit and basis, but still have to justify each requirement separately.
Agreement among simulated roles is not stakeholder endorsement. The discussion panel
reserves a slot for the grounding/scope critic even when many roles contributed.

## Bounded selection and restart

The versioned policy is `rq1-stakeholder-selection-v6`:

1. Read all snapshot evidence in deterministic source/selector order. Discovery batches
   have at most 40,000 serialized characters, and the policy allows at most 32 batches.
   An oversized unit/corpus fails explicitly; it is not silently truncated.
2. One logical selector uses the configured provider to discover at most the requested
   panel size per batch (1–8). CQs accompany each batch. Only selected snapshot evidence is loaded;
   there is no filesystem search, external retrieval or reference-set access.
   Validate all proposals and, when needed, make the single citation correction
   described above before accepting any candidates from that batch.
3. After each batch, consolidate its candidates with the retained panel. The reducer
   can choose existing IDs and group equivalent perspectives; it cannot invent new
   evidence or rewrite their remits. Every input candidate must appear exactly once
   in a group or an explicit omission. The representative's description and basis are
   preserved unchanged; grouping lineage is retained.
4. Save each discovery batch before consolidation, and save each resulting panel.
   Resume skips completed work. A failed reducer can reuse that batch's discovery.
   Completed panels are hash-bound and stored as immutable artifacts. Incomplete
   manifests from an older selection policy require a new run; completed historical
   manifests remain readable. The correction attempt is recorded before calling the
   provider, so an interrupted or unsuccessful correction cannot be silently repeated
   by Resume. Inspect the saved validation report and create a new run instead.
5. If a successful full scan yields no candidates, use explicitly **proposed** generic
   perspectives with a recorded fallback reason. Provider/validation failures never
   trigger that fallback and never proceed with a partial panel.

This is incremental consolidation: previously omitted candidates remain in the audit
but are not all reconsidered in a final global optimization. Selection may depend on
source order. The manifest records coverage, candidate lineage, provider identity per
batch/round and omissions. Per-call outputs, hashes and timings are in the run audit.
There are at most three logical selector calls per batch (discovery, optional citation
correction, consolidation; 96 for a single uninterrupted maximum-size pass). An
explicit retry of failed discovery/consolidation can add calls; citation correction
remains limited to one attempt per batch across resumes. Provider-level retries may
also add HTTP requests. Discovery reserves at most 8,000 output tokens; correction
and consolidation reserve at most 5,000 each per generation. V5 allows one
additional schema correction generation per logical OpenAI-compatible call, so
these reservations can double when correction is used. Citation correction remains
a separate semantic operation with its existing across-resume bound. User payloads
over 60,000 characters are rejected. These are character/output bounds, not a claim
that every provider context limit is supported. The provider adds its schema prompt.

V5 retains the V4 bound on each discovery response to the requested panel size (default four,
maximum eight), with concise role descriptions, up to two stakeholder names/two
focus questions, and at most two literal quotations. Quotations preferably stay
under 160 characters, but the shared citation schema allows up to 400 characters
to preserve necessary context. Exact-source matching remains mandatory. The schema
enforces the remaining limits. All source batches are still scanned, but the smaller
candidate pool changes discovery breadth compared with the previous eight-candidate
policy; it is a new experimental condition, not an equivalent replay. Human role
overrides and completed historical manifests retain their original contracts.

OpenAI-compatible calls retain provider finish reason, response character count,
and reported token counts, including reasoning/cached counts when supplied. Counts
the provider omits remain unknown. A `length` finish reason fails explicitly even
if the partial text happens to be valid JSON; it is never accepted as complete
discovery, and it does not trigger an automatic model retry or citation repair.
Other malformed responses receive one bounded structural correction using the
same provider, original context and unchanged schema. Excess stakeholder names
must be grouped into appropriate perspectives by the model; the application does
not silently discard them or widen the limits. An invalid corrected response still
fails before extraction. This recovery policy changes the experimental condition:
incomplete older manifests need a fresh run; historical artifacts are preserved.
Each generation retains its validation errors and finish reason, with a fingerprint
of the response. Invalid response content is not retained in transport metadata.
Audit records exclude response reasoning text, API keys, and request headers.
Evaluation exports distinguish recorded partial usage from fully measured usage;
they do not infer monetary cost from token reservations.

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

## Experimental interpretation and validation

Role selection belongs to the full workflow's cost. Evaluation exports separately report
selector call count, failures, summed latency, output reservations, coverage and role
basis counts. Actual provider tokens/cost remain unavailable in the existing client.
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
Browser checks exercise the mock path and panel override. These offline checks do not
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
