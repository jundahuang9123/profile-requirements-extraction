# F/A requirements and stakeholder discussion

## Purpose

This version gathers source-supported requirements for discovering/selecting datasets and understanding or obtaining access. It supplies inputs to later profile development. It does not design an extension or generate an ontology. Interoperability and reuse alone do not establish relevance. Format, structure, quality and population can be relevant when a source supports a discovery/access task.

New UI runs use the `find_access_v1` requirements contract. Automatic stakeholder discussion selects `fa_mediated`. Historical `independent` and `routed_mediated` runs retain their original interpretation. A historical extraction cannot validate the new extraction contract: derive from elicitation, retaining the snapshot/panel but extracting afresh.

## Saved steps

1. **Sources and base:** freeze the inputs, source locations, selected base version/catalogue and any declared use cases. Base-only context does not create domain demands. Missing use cases remain visible; they do not establish stakeholder endorsement.
2. **Panel and routing:** preserve documented/inferred role bases and route every passage to a specific perspective, shared extraction or visibly uncertain shared extraction. The existing sealed panel and routing audit remain authoritative. A pre-extraction audit shows declared tasks without a linked role, overlapping task links, source bases and missing formal task documents; these annotations are not stakeholder endorsement.
3. **One planned extraction pass:** read each assignment once, in bounded batches. Invalid output may receive bounded corrections. There is no repeated whole-corpus completeness sweep. Preserve actor, modality, conditions and negation; a quoted fact is not automatically an information need.
4. **Grouping/writing:** keep original observations and member links. A new independent preservation check rejects a broad summary that loses information, actor, purpose, conditions, obligation or negation. Rejected or unavailable rewrites retain their original proposals as visible set-asides. “The metadata must let users …” is allowed only with a separately source-checked mandatory obligation. Historical neutral wording is unchanged.
5. **Independent scope axes:** record source support, find/access relevance, statement nature, actor/task/example and cited evidence separately. Unchecked or disputed rows retain a review flag. A definite unsupported/out-of-scope judgement is reversible, with evidence and rationale retained. Category/applicability failure cannot erase these axes. Base-covered domain needs remain in the inventory with their domain evidence and base matches.
6. **Cases:** task-based grouping can combine needs from different source files (since `rq1-fa-dialogue-v5` over the whole inventory; see Task cases). Bounded windows and packet size limits are recorded; this does not guarantee all distant related needs meet. Include latest set-asides and unresolved proposals, labelled as such. Oversized cases split with a shared group hash; an oversized singleton remains pending human preparation.
7. **Discussion:** save independent initial positions without peer answers; aggregate issues; obtain a mediator draft; solicit responses to proposed changes or material objections even from a role previously marked finished; obtain final mediation when responses occurred; independently check every disposition, including retain and set-aside. No concern is a valid response; silence or repetition does not establish consensus or weight. Since `rq1-fa-dialogue-v6` roles may also bring claims from the practice of their role, which the mediator admits or excludes, and concerns the mediator does not answer are recorded as noted (see Experience claims).
8. **Persistence/review:** apply source-checked machine revisions transactionally. Preserve before/after revision IDs, parents, evidence and observations. Invalid changes retain parents and a review question. A case whose structured output remains invalid after bounded correction is explicitly queued for human review; since `rq1-fa-dialogue-v3` the valid parts of its plan are salvaged first (see below). The run can continue with other cases. Transport failures still stop unfinished work for supported resume. Machine outcomes are never human acceptance. The pre-discussion machine snapshot remains unchanged.

The mediator can propose retain, revise, split, merge, add/recover, covered-by-base, reversible set-aside or defer. Priority requires explicit applicable source support. Cross-case conflicts require joint review rather than a decision that cannot see both sides. New wording invalidates old base comparisons and shows a recheck flag. A covered-by-base label cannot be manufactured without an existing checked match.

## Coverage and traceability

`GET /api/rq1/v2/runs/{run_id}/coverage` returns source processing, extraction assignments/attempt statuses, source spans, observations, revision links, transformation events, set-asides, base/scope annotations, discussions and human-decision links. It exposes unprocessed and unaccounted work explicitly.

The UI provides a collapsed coverage/inventory view and saved dialogue phases. The needs export and trace export carry the same ledger and model choices. The inventory contains historical need revisions as well as current ones; the working IDs identify current needs not labelled covered by base. Do not confuse inventory revision count with distinct current requirement count.

Processing every passage is not evidence of finding every requirement. Accounted observations are not independently evaluated semantic coverage. Quality/recall and effort saving require separate adjudication and evaluation.

## Evidence expansion and budgets

Every dialogue protocol measures the exact JSON sent after reversible identifier aliases against a context limit: 45,000 characters (`rq1-fa-context-budget-case-v1`), or 53,000 since `rq1-fa-dialogue-v4` (`rq1-fa-context-budget-case-v2`), or 66,000 since v6 (`rq1-fa-context-budget-case-v3`), for the role cards and experience claims that v6 adds to discussion inputs (the claim size is estimated, not measured). The phase audit records internal, wire and measured sizes, the limit and the wire hash; v2 and v3 also record the phase's output-token caps. An oversized case retains its original needs and accepted phases and is deferred visibly to human review; later cases continue. Full internal payloads still determine checkpoint identity.

A stakeholder may request a specific missing passage, and since v6 a passage that might support one of its experience claims. Bounded lexical retrieval searches only the frozen run evidence IDs: up to eight distinct queries, two passages per query and four new passages overall. It records query, exact selected location, source/content hash, eligible-ID hash and excluded count. No benchmark/reference file or web retrieval is available to discussion. A no-result query remains visible as unresolved.

A case permits at most 14 model generations including schema/semantic corrections and revision assessments, 112,000 reserved output tokens and 1,800 seconds of accumulated model-call time. Primary calls reserve 4,000 tokens and truncation correction may reserve 8,000. Since `rq1-fa-dialogue-v4` a case permits 16 generations and 128,000 tokens, and a mediation plan starts at 8,000 tokens; since v5 each further need of a case adds one generation, 8,000 tokens and 300 seconds. Each case records its limits when it is built, and execution reads them from the case, so a case keeps the limits it was planned with. The time guard prevents starting another request after the recorded budget; the provider transport timeout bounds an in-flight request. With many revisions or corrections, some work can remain for human review. It is not reported as successful mediation.

Phase checkpoints bind policy, prompt, packet, schema, aliases and effective model/reasoning options. Finished phases resume without new calls. Exact field-scoped local IDs avoid fuzzy identifier repair. An absent/wrong quotation offset can be repaired only when the exact quotation occurs once in the frozen source; the repair is audited. Repeated/ambiguous text still needs a valid offset. No source is rewritten.

## Models and options

Advanced settings are collapsed by default. New slots:

| Slot | Purpose | First hybrid experiment |
| --- | --- | --- |
| `stakeholder_review` | Independent positions and targeted replies | `inferenz-gpt-oss-120b` |
| `mediation` | Draft and final mediator | `inferenz-qwen3-8-27b` |
| `mediation_check` | Independent check of all dispositions | `inferenz-gpt-oss-120b` |
| `assessment` | Source/semantic qualification of revisions | `inferenz-gpt-oss-120b` |

Unset discussion subslots inherit the explicit `discussion` model, then the configured model. Per-step `step_model_options` can override `reasoning_effort`; unset subslot options inherit discussion options, then configuration. Model IDs are checked against the provider catalogue before run creation. Unsupported effort values for recognised models are rejected; unknown model families receive no reasoning option. The hybrid preset is enabled only after the provider list contains both exact aliases. It sets Qwen mediation effort to low initially; it is an experiment preset, not a claim of superiority.

```json
{
  "stakeholder_workflow": "fa_mediated",
  "requirements_scope": "find_access_v1",
  "step_models": {
    "discussion": "inferenz-gpt-oss-120b",
    "mediation": "inferenz-qwen3-8-27b"
  },
  "step_model_options": {"mediation": {"reasoning_effort": "low"}}
}
```

The existing client parses final-answer content, separates Qwen thinking, rejects unfinished thinking and rejects `finish_reason=length`. It records numerical token usage where provided without exporting raw reasoning. Output tokens are a per-request cap, not a daily allowance.

[Qwen's thinking-budget documentation](https://qwen.readthedocs.io/en/v3.0/getting_started/thinking_budget.html) treats thinking as part of generated tokens in its example. [Qwen's vLLM guidance](https://qwen.readthedocs.io/en/stable/deployment/vllm.html) describes separate reasoning content. These do not prove how KI:connect's particular alias/server accounts for reasoning. Confirm that endpoint's finish reason and numerical usage in a small authorised compatibility probe before a hybrid trial. Do not assume that a reasoning budget leaves the same amount of room for final JSON.

## Controlled evaluation after offline implementation

No live inference was used to implement or test this change.

1. Run a small compatibility probe using source-shaped synthetic input and bounded output. Verify actual model alias, accepted options, final JSON, numerical reasoning usage where reported and truncation handling.
2. On a newly extracted small F/A run, freeze a fixed set of up to twelve case packets with both simple and contentious cases. Compare no discussion, all GPT-OSS and Qwen mediator only. Keep upstream records, roles, input packets and budgets identical; do not compare independently regenerated upstream outputs as if controlled.
3. `scripts/prepare_fa_case_comparison.py` prepares an offline manifest from a saved trace export. It does not call a provider or alter a run. The manifest records exact frozen case/role hashes and the three model assignments. It is preparation, not a live replay tool; a matched-case runner or manually sealed case replay must preserve those inputs.
4. Independently judge retained distinctions, source-supported gains/losses, added unsupported claims, unresolved questions, calls, tokens and time. Keep evaluator reference answers outside all prompts and retrieval.
5. Only then run a fresh small complete trial; evaluate extraction changes with fresh extraction. Health/JRC/Stat have informed development and are not untouched held-out sets. Larger corpus trials follow after the small trial is reliable.

Offline tests use synthetic fixtures. Offline success establishes software behaviour, not improved requirement recall or model quality. Real role-selection/task coverage and distant case grouping still need human inspection; an absent perspective cannot be inferred solely from these tests.

## Interrupted discussion replay

Every accepted stakeholder phase now saves its complete message, including the original timestamp, before another phase consumes it. Resume reuses that message and its output rather than regenerating a timestamp and invalidating downstream input hashes. Transport tuning is excluded from model generation identity, so a longer HTTP wait can reuse compatible phase outputs; case call, token and elapsed-time budgets still apply.

`rq1-fa-message-replay-v1` also supports one narrow legacy recovery: an interrupted final mediator phase with no accepted output, a saved draft and complete targeted role responses. The original draft input hash must still match exactly. Recovered responses are validated again; unavailable response timestamps are explicitly null. The saved trace records the recovery policy and each old/new downstream input hash while preserving outputs, attempts and budgets. This is an audited reconstruction, not a claim that the lost historical timestamps were recovered. Other mismatches or incomplete legacy transcript shapes remain errors. Completed cases and human decisions are not reopened.

### Optional per-case timeout fallback

A run may freeze `mediation_timeout_fallback` with policy
`rq1-case-mediation-timeout-v1`, a provider-validated `fallback_model`, and
`timeout_seconds` (120 by default). The primary mediation model remains in
`step_models`. Each mediation HTTP request uses that timeout with transient and
rate-limit retries disabled. This bounds an unanswered request, not the total
case: a schema/length correction remains a separate, budgeted generation.

Only an actual provider timeout triggers the fallback. The same case uses the
fallback for its unfinished mediation phases, then the next case starts with the
primary model again. Authentication, connection, HTTP, validation and budget
errors do not trigger a model switch. A fallback timeout stops the run. Existing
source validation and case budgets remain in force; timed-out attempts count.
A client timeout does not prove the remote provider has stopped computing.

New timeout-fallback policies default to two minutes per request. Existing runs
retain their explicitly saved timeout, including earlier 300-second policies;
changing this default does not rewrite their checkpoints or resume them. A new
discussion continuation must explicitly freeze `timeout_seconds: 120` when
adopting the shorter wait. In the observed pilot, 20 of 25 successfully parsed
Qwen mediation responses finished within 120 seconds. This is a timing
observation, not evidence that those outputs passed semantic review or that
future requests will have the same retention rate.

The saved `mediator_routing` trace records the policy, primary/active model and
switch time/reason. Each fallback phase has its own model-bound checkpoint key;
accepted primary outputs and stakeholder messages are reused. Call audits show
the actual model. The discussion page exposes this routing trace and exports
retain it. No machine action constitutes human approval.

`POST /runs/{id}/derive` with `start_from: deliberation` can continue a failed,
interrupted or user-cancelled F/A discussion under the new policy. It copies completed upstream
outputs and all case checkpoints without replaying extraction or completed
cases. The parent stays unchanged. Lineage records inherited call counts/hashes
and the parent plan/implementation identity and code history; the child's call
log covers only new requests. `implementation_hash` names the code that created a
run; `code_history` lists each later start under other code, with the stage
states that start found. Upstream settings and primary model choices cannot change in this
operation. Totals must include parent calls when reporting the whole workflow.
A discussion planned under another protocol, such as `rq1-fa-dialogue-v2` or
`rq1-fa-dialogue-v3`, is refused; derive a base-review trial instead (see below).

A user-cancelled parent can produce a linked continuation only when unfinished
user-cancelled cases remain and no human decisions or baseline exist. Only those
unfinished cancelled cases return to the queue. An existing fallback policy may
shorten its request timeout while retaining its models and protocol. Completed
cases keep their historical policies; unfinished routes record the old/new
policy, retained phase hash and unchanged attempt/time budgets. Accepted outputs,
existing fallback switches and exhausted corrections are not reset.

## Optional procedural base reviewer

Set `base_review: "expert_v1"` on a new F/A run with a selected base profile.
The default is `none`: existing v1 packet, phase and grouping identities and
recovery rules remain unchanged. The advanced option is initially collapsed in
the Stakeholder roles setup. It does not add a stakeholder or a vote.

The new **Base review** stage runs after consolidation (and its stepwise pause),
before discussion. Policy `rq1-base-expert-v5` reviews current revisions sorted
by ID, in batches of up to four: one review generation and one independent check
per batch. (`rq1-base-expert-v3` names an earlier version of these fixes whose
prompts differ; only JRC `run-fd39639e` and StatDCAT `run-7211c6ec` used it.
`rq1-base-expert-v4` differs from v5 only in the check of a domain use, see below.)
Each generation allows at most one correction. It names the problems by the
N/B/E aliases the model saw and shows the rejected answer when that answer met
the output contract; an answer that failed the schema gets only its schema
errors (v2 sent internal revision IDs and no previous answer). Oversized payloads split; a single need
that cannot fit the 30,000-character payload budget is marked `not_reviewed` /
`payload_budget`. An oversized independent-check payload splits its checks
without repeating the already accepted review.

One need no longer sinks its batch. When a batch stays invalid after its
correction, each judgement in its newest parsed answer that is valid on its own
is kept, and still independently checked; every other need is reviewed alone.
An answer that fails the output schema (for example one row citing too many
excerpts, or more rows than needs) is still read row by row, each row against
its own contract: its parsed JSON is saved on the attempt, so a resumed run makes
the same decisions. Checks are isolated the same way. Kept results record
`isolated_from_failed_batch` (`review` and/or `check` names the failed batch); a
need reviewed or checked alone carries no marker. Only a need whose own review stays
invalid remains `not_reviewed` / `invalid_output` with `base_review_pending` and
its validation `errors`; a need whose own check stays invalid is `not_reviewed` /
`check_invalid_output`, also with its errors, and its unchecked verdict is not
recorded as a judgement. v2 marked whole batches: 10 of
46 JRC needs in three batches. A verdict may cite up to 12 entries (one per item
of a need that lists items) and up to 12 of the need's own excerpts, each once; the old
limit of 4 excerpts rejected a review call in JRC `run-fd39639e`. Transport
failures stop the stage rather than inventing a result. Checkpoint identities bind the policy, prompts, payload, aliases, schema
and actual model; accepted outputs are reused and changed identities are refused.

Review inputs are **only** the run's pinned catalogue and authentic cited source
passages, with up to 600 characters of surrounding frozen context on each side.
Every batch carries the catalogue **index**: class, property and need phrase of
every pinned entry, so any entry of the base can be cited. Likely candidates
(classifier matches first, then lexically ranked entries, up to ten per need)
also supply label, definition, up to two usage notes of 300 characters, and
obligation. Ranking only orders these details: on the JRC development run it
missed paraphrases such as "year of public release" for `dct:issued` and
"thematic classification" for `dcat:theme`. The classifier state is its result
and search status only, not its search audit. The checker receives the index and
the full text of each cited entry and of each entry the base classifier matched,
so a verdict that contradicts the classifier is checked against the entry the
classifier relied on. Local N/B/E aliases are scoped to identifier
fields; quotations are not rewritten. A property not in the index is not in this
base; another version and model memory cannot supply missing base knowledge. A
changed catalogue pin refuses review.

| Verdict | Meaning |
| --- | --- |
| `restates_base` | Cited index entries express the whole need without an added constraint |
| `domain_use_of_base` | A cited entry is used with a cited addition: condition, value set/unit, obligation, resource or meaning |
| `new` | No index entry names the information the need asks for; when an entry names it and the need adds a value, condition or narrower meaning, the verdict is `domain_use_of_base` |
| `uncertain` | The supplied text is insufficient |

Wording, synonyms, examples, actor and purpose alone are not additions. A
restatement must also pass the classifier's condition and stronger-obligation
guards. The independent check answers two questions: `verdict_supported` (the
verdict is right: the cited entries of a restatement share the resource and
property meaning; those of a domain use share the property meaning, on the same
resource unless the stated addition is another resource class; no index entry
(including a classifier match) names the information of a new need; or the
catalogue text is indeed insufficient) and
`nothing_lost`. Under `rq1-base-expert-v4` the check required the same resource
for a domain use too, although the review prompt allows a domain use on another
resource class, so such verdicts could only fail (2 of the 4 failed checks of JRC
`run-934df8ba`, see Live results). For `new` and `uncertain` verdicts v5 uses
`verdict_supported` alone: `nothing_lost` adds nothing there, and in JRC
`run-e1e4810f` 3 of 6 failed checks agreed with a new verdict but answered
`nothing_lost=false`, which kept a wrong label. Otherwise both must be true before labels change; a failed check adds
`base_relation_review` and leaves labels unchanged. Policy v1 asked instead
whether the entries express the need, which is false for a correct `new`
verdict: in the JRC trial of 19–20 October 2026, 31 of its 35 failed checks
were such agreements.

| Classifier at review time | Checked restatement | Checked domain use | Checked new | Uncertain |
| --- | --- | --- | --- | --- |
| Already `covered_by_base` | Confirm | Remove flag | Remove flag | Note |
| Domain use | Add flag | Agree | Note | Note |
| Domain / unchecked / newly written | Add flag | Note | Agree | Note |

The label follows the checked conclusion in both directions. A removed label
(`flag_removed`) keeps the classifier's original judgement in `classifier_state`;
an added or removed label records both judgements and a human-review question.
Policy v2 instead kept the classifier's label as a `dispute`, and its discussion
had to defer such needs. `rq1-base-expert-v3` removed the label but still wrote
`dispute`; the ledger, report and need cards decide by the recorded policy
(`base_review.label_removed`), so its records count as removed labels and a v1/v2
`dispute` still means the label was kept. **No need is deleted or set aside by this reviewer.**
`covered_by_base` stays in the complete inventory and is excluded only from the
working count. `base_relation` records the phase, verdict, effect, check,
classifier state, exact entry and evidence IDs, pin, checkpoint and model, with
`human_accepted: false`. Metadata refresh changes the integrity hash but not the
need's content hash or revision ID.

For opt-in runs, the base-aware dialogue (`rq1-fa-dialogue-v2` to `-v4`) gives each discussion packet the compact
review and pinned classifier-matched/reviewer-cited entry text. Stakeholders can
identify additions the base lacks. A need labelled `covered_by_base` may be
retained, disposed `covered_by_base` or deferred with a human question and
alternatives; any other action on it (revise, merge, split, resolve, recover,
set aside) is refused. A need whose label the checked review removed is an
ordinary working need and is not forced into deferral. The rule that a `dispute`
requires a deferral with a human question applies only to cases planned under
`rq1-fa-dialogue-v2`. Until 20 October 2026 deferral of a labelled need was
refused too; in the JRC trial that rejected mediator drafts in 18 cases. Up to v4 cases are grouped as in v1; v5 forms them by task (see Task cases); budgets are described above. Every revision created
by revise, merge, add, recover or split requires a new base check. After all
cases, a second procedural pass reviews those current revisions before the final
coverage ledger. Reviewed revisions clear `base_recheck_required`; unreviewed
ones retain it. Neither procedural review nor mediation is human approval.

The ledger adds verdict/effect counts by phase (read by the recorded policy, so a
`rq1-base-expert-v3` `dispute` counts as `flag_removed`), coverage-label provenance split
between classifier and reviewer, removed labels, legacy disputes, pending rechecks
and unreviewed IDs. Its contract hash includes the current reviewer prompts
unless stage 6a recorded another policy: a run reviewed under another policy
(such as `run-fd39639e`) binds only that recorded policy name, so it never
reports the current contract. Need cards, the Base review
page and discussion view show these judgements, and need cards show a need's
validation errors; the coverage panel exposes the counts (legacy disputes only
when present) and the complete ledger remains downloadable.

### Mediator plan bookkeeping and salvage (v3)

In the JRC trials of 19–20 October 2026 (runs `280b0fab…` and `c84ef4a3…`, policy
`rq1-fa-dialogue-v2`), 57 of 84 cases ended with an invalid mediator plan. Most
plans answered each stakeholder concern with its own action, often naming no need
or naming one need several times; questions listed action IDs as needs. The
correction attempt fixed 12 of 61 rejected plans: it listed only rule names, named
revisions by internal IDs the model had never seen, and omitted the rejected plan.
`rq1-fa-dialogue-v3` changes only this bookkeeping:

- **Guidance.** The mediator prompt states that an action disposes needs and is
  never a reply to a concern, that each need occurs in exactly one action, how
  each concern is answered, that a question lists need and concern IDs only, and
  that an idea to drop is left out rather than added and then set aside or
  deferred (18 of the 27 JRC actions that named no need did that).
- **Repairs.** Before validation, four deterministic repairs: a question that lists
  an action ID gets that action's needs (an ID the model repeated stays repeated
  and invalid); question/concern links are made
  reciprocal when one side names the other; in a plan without additions, an
  action without a need that no concern links and that carries no statement,
  condition, source, priority, alternative, child or question is an empty note
  and is dropped; empty deferral fields
  are copied from their unique fully linked question. An action without a need is
  never guessed onto one, and one with content goes to correction and, if it
  stays, to review. (Dropping every unlinked parentless action, as first written,
  could apply an addition whose set-aside withdrew it.) Each attempt keeps the model's plan (`model_output`) beside
  the repaired plan and lists the `repairs`.
- **Corrections.** A rejected plan is shown again with item-level problems
  (`feedback`), all named by the aliases the model saw, including IDs repeated
  inside one list; when more than 30 problems exist, the correction says how many
  were not shown. The validators still decide validity. A resumed second attempt
  also receives its correction.
- **Salvage** (`rq1-fa-salvage-v1`). When a plan stays invalid after its
  correction, its latest parsed version keeps each action that passes every
  one-action rule and names needs no other action names. When several unchanged
  dispositions (retain, covered_by_base, defer) name one need, its single valid
  deferral is kept. Additions are never kept: the invalid plan may have meant to
  withdraw them. Every other need receives a marked system deferral (`salvage-N`)
  that retains the original for a person. Its question offers to apply a rejected
  action after review only when a dropped action named that need; otherwise it
  offers a separately reviewed revision. Concern dispositions that are
  inconsistent with what was kept become unresolved under one system review
  question. Every action dropped from the applied plan keeps its full proposal and
  appears in the case outcomes as an unapplied `human_review` row
  (`salvage_rejected`) with its problems; the discussion view labels it "rejected,
  not applied". Nothing is written or cited by salvage, and the result must pass the
  normal plan validators. A salvaged draft goes through the normal response round
  and final mediation; kept actions are then independently checked and applied
  like any others. Up to v11, salvage needs at least one valid disposition of an
  existing need; otherwise the case stays `invalid_output_pending_human_review`
  (v12 salvages such a plan too; see below). A case
  whose applied plan was salvaged stops as `bounded_fa_dialogue_salvaged`, its
  mediation lists `salvage` audits by phase, and metrics count `salvaged_cases`.

Offline replay of the 57 saved invalid plans (no model calls; the latest parsed
plan of each case) on the merged v3 code gave: 9 valid after repairs, 15 salvaged
(no addition kept), 26 without a valid need disposition, and 7 without a
parseable plan. (Before the narrower repair 3 and the rule that salvage keeps no
addition, it gave 10 and 14.) The first live v3 discussion is reported under Live
results. A discussion planned under an earlier version cannot continue, and
labels from another base-review policy are refused; derive a separate
base-review trial instead. The legacy v1 protocol is unchanged.

### Stakeholder concerns, limits and set-asides (v4)

`rq1-fa-dialogue-v4` keeps the v3 bookkeeping and changes what the first live v3
discussion (JRC `run-934df8ba`, below) showed:

- **Concern rules.** Every stakeholder prompt says that `revision_ids` name only
  the needs N of the case, never an invented need or an action, question or
  concern ID; that a missing need is proposed in `proposed_statement` of a scope
  concern on the closest need; that `missing_evidence` means a missing source
  passage, and no data catalogue or its records are given, so a role reports a
  catalogue lacking a property only when a source passage says so; that MUST or
  SHOULD wording is asked for only when a source passage states the obligation;
  and that each issue is raised once, in at most four concerns, and a response
  raises only new issues. In the v3 run 15 cases ended on a stakeholder review
  that named IDs that are not needs of the case, and completed cases carried a
  median of 15 concerns, many saying that "the current catalog" lacks a property.
- **Draft references.** In a response round, a concern that names an action or
  question of the draft it was shown (including a salvage review question) gets
  the needs that action or question names, when they are needs of the case. The
  attempt keeps the model's answer (`model_output`) and lists the
  `concern_need_from_draft` repairs. An ID used twice in the draft with
  different needs, an invented ID, or a mapping beyond four needs is not
  repaired.
- **Corrections.** A rejected stakeholder review gets sentences that name the
  needs and excerpts it may cite, in its own aliases (for example "Concern 2
  lists N4 in revision_ids, but the needs of this case are only N1, N2"). The
  v3 correction showed only the validator's records; it fixed 10 of 25 reviews.
  A mediator plan that writes `add` for a need it means to reword is told to use
  `revise`, or to keep the need with `retain` beside an add without parents: in a
  GPT-OSS-only JRC replay (`run-4b8eaaca`), 8 of 13 drafts that stayed invalid
  wrote a lone add, were told the need was in no action, and then named the need
  in the add ("Addition cannot replace an existing parent").
- **Base absence.** The mediator and checker prompts say that a need the base
  does not provide is a candidate requirement of the profile, never a reason to
  set it aside; one v3 mediator set three needs aside because the base lacked
  the property (the checker blocked it).
- **Limits.** 53,000 characters of input (13 of the 14 v3 input-size stops were
  45,118–50,262 characters), 16 generations (5 v3 cases ran out of 14), 128,000
  reserved output tokens, and an 8,000-token first cap for mediation plans (all
  38 v3 cut-off answers were plans at the 4,000-token cap; every 8,000-token
  retry finished). The case and each phase record the limits used.
- **Set-asides.** Cases include earlier set-asides for review. A set-aside of a
  need that is already set aside is recorded as `already_set_aside`: not applied,
  not counted as a mediated change, and no second set-aside record (in the v3
  run, 5 of the 7 applied changes were such repeats). The set-aside contract now
  admits the record a mediated set-aside writes (`mediated_fa_set_aside`,
  `reversible`); before, a run holding one failed the validation of a discussion
  continuation (any F/A protocol).
- **Pending questions.** A case stopped by invalid output asks under
  `invalid_output`; `budget` now names budget and input-size stops only.

A discussion planned under v2 or v3 cannot continue, and stage 6a labels must
come from `rq1-base-expert-v5`: derive a base-review trial from an earlier run.
These changes are tested offline only; their effect on live cases is not yet
measured.

### Task cases (v5)

In JRC `run-e1e4810f` 70 of 74 discussion cases held a single need. Grouping saw
batches of 12 needs sorted by the scope task, whose text nearly repeats each
need, and returned single-need groups in 6 of its 7 batches. Related needs (five
on access conditions, three on the publisher, five on licence and rights) were
never discussed together, so the discussion could not merge, compare or filter
them.

`rq1-fa-dialogue-v5` forms cases by task across the whole inventory
(`rq1-fa-task-labels-v2`). Needs, including set-aside proposals, are labelled in
order of revision ID in chunks of 30; each chunk sees the labels given so far and
reuses them for needs about the same task. A need that states a fact about a
document, organisation or specification is labelled "statement about the
sources". Needs with the same label (ignoring case and spacing) form a case of at
most six needs; a larger group is split in order into parts that keep the task.
Labels only group needs: the discussion decides what happens to each.

Each labelling answer is checked after audited repairs: a label for an ID outside
the chunk is dropped, and a need labelled twice with the same label keeps one. A
need without a label or with different labels gets one correction that names it.
A rejected answer is checked from its complete JSON, row by row. The answer with
the fewest problems is kept; a need still unlabelled is discussed alone, and the
chunk records why. An invalid answer never fails the stage; a provider failure
still stops it for resume. Labels v1 (chunks of 60, no repair or correction)
failed the first v6 JRC trial (`run-a89957db`, 21 October): both generations for a
60-need chunk returned more labels than the contract allowed, and the stage
stopped. A run whose labels were saved under v1 is refused by name.

Each case names its task in `packet.task`, and the mediator is told that needs
stating the same information, also from different sources, are merged into one
need that keeps every condition, actor and source. Source windows are the quote
with 300 characters on each side instead of 1,000 before and 4,000 in all, so
several needs fit the 26,000-character packet. Labels are checkpointed per chunk;
a changed labelling prompt or input is refused on resume. The legacy v1 protocol
keeps its grouping and windows. This is tested offline only.

### Experience claims and noted concerns (v6)

In the JRC discussions of 21 October (`run-e1e4810f` and its GPT-OSS replay) roles
raised about 1,000 concerns per run, 50–60% of them `missing_evidence`: the
sources alone gave the roles little to add, and plans spent their bookkeeping on
answering concerns one by one. In an expert discussion people bring their
experience. `rq1-fa-dialogue-v6` lets each role do so from the practice of its
role, has the mediator decide which of it belongs in the case, and records
concerns the mediator does not answer as noted.

- **Experience claims.** Besides its source-backed concerns, a role may add at
  most two claims per review (`ExperienceReview.experience`). A claim names the
  task of the role it comes from, describes the role's practice in that task
  ("When I …, I …"), and says what follows for the needs of the case: `keep`,
  `merge`, `split`, `drop`, or `missing_need` with a proposed statement. A claim
  cites no source. It may carry a query: the queries of first-round claims are
  searched in the frozen sources with the roles' source queries, in turn across
  roles, within the bound of eight queries and four passages (as for source
  queries, response rounds are not searched).
- **Guard.** One correction is given to a claim that names needs outside the
  case, a `missing_need` without a statement, another kind without needs, or a
  `merge` with fewer than two needs. The same holds for a claim that names a
  DCAT-AP extension or national profile (HealthDCAT-AP, GeoDCAT-AP, StatDCAT-AP,
  mobilityDCAT-AP, DCAT-AP-HVD, DCAT-AP-NO, DCAT-AP_IT, DCAT-AP.de, also written
  "Health DCAT-AP" or "healthdcat-ap"); the base itself and words such as
  "DCAT-AP-compliant" are allowed. The guard catches names only. A claim that is
  still invalid after its correction is left out, and the attempt records it
  (`experience_removed`); the role's concerns stay in the discussion.
- **Mediator decision.** The mediator sees the claims under aliases X1, X2, …
  and the role cards of the participants (purpose, focus questions,
  stakeholders). It admits or excludes every claim exactly once, with a reason:
  a claim is admitted when it fits the task of the case and the card of the role
  that made it, and no source passage contradicts it. Only admitted claims may be
  cited by an action (`experience_ids`). Experience never replaces a source: a
  revise, merge, resolve, split, recover or add still needs its source links and
  passes the strict verifier. A retain or a reversible set-aside may rest on
  admitted experience and is checked like any other action; the checker is told
  that experience is not a source. The observation of such a set-aside lists the
  claims (`experience_ids`).
- **Proposals.** A need proposed from experience alone goes to `proposals`
  (statement, admitted claims, closest needs), never to actions. Each becomes an
  outcome row with status `experience_proposal`: never applied, listing the roles
  whose claims it rests on, with a question for a person. Its ID differs from
  every action ID. A proposal in the draft is put to every role in the response
  round, and a response that names it where a need belongs gets its closest
  needs.
- **Noted concerns.** The mediator answers a concern only to reject it or to
  leave it open with a question. Every other concern is recorded in
  `concern_dispositions` with `derived: true`: as `unresolved` when a question
  lists it, otherwise as `noted` against the actions on its needs. A repeated or
  unknown answer is still invalid, and question links stay reciprocal for
  answered concerns.
- **Salvage.** A claim without exactly one valid decision is excluded by the
  system (its decision is marked `system: true`); an action or proposal that cites
  a claim not validly admitted is dropped; only a concern answered inconsistently
  goes to the system question.
- **Limits.** Discussion inputs may be 66,000 characters instead of 53,000. The
  role cards of the four JRC roles in `run-e1e4810f` take 1,263 characters; up to
  16 claims with their decisions are estimated at about 11,000. A plan decides at
  most 64 claims (16 roles). Case call and token limits are unchanged.
- **Reported apart.** Metrics count `experience_claims`, `experience_admitted`,
  `experience_excluded` (by the mediator), `experience_excluded_by_system`,
  `experience_actions` (not counting actions a salvage rejected),
  `experience_applied_changes`, `experience_proposals` and `noted_concerns` over
  completed cases.

**Contamination.** A role's experience is model knowledge. It can carry recall of
existing application profiles, including those a benchmark reference was built
from, in words other than their names. The design keeps this visible rather than
preventing it: claims are a separate kind of argument, never sources; the
mediator records why each is admitted or excluded; needs from experience alone
are never applied; and every change that rests on experience is counted apart.
An evaluation should report results with and without the items that rest on
experience.

A discussion planned under v5 cannot continue under v6: derive a base-review
trial, which no longer inherits the parent's task labels. The legacy v1 protocol
is unchanged. This is tested offline only.

### Splits and plan repairs (v7)

In the first v6 JRC trial (`run-a89957db`, 21 October) 6 of the first 24 cases
ended with an invalid draft, all in single-need or statement cases. 5 of the 6
failed on "Recovery/split requires source-supported statement and links": the
mediator wrote a split whose new needs carried their sources, but gave the split
no statement of its own, which is never applied. `rq1-fa-dialogue-v7`:

- **Split.** A split needs at least two children, each with a statement and
  sources; it no longer needs a statement or sources of its own. A recovery still
  does.
- **Additions that name needs** (audited repairs of v6 plans): a sourced add that
  names needs no other action names rewords them, and becomes a revise of one
  need or a merge of several, as v4's correction already asked; an add that names
  needs other actions dispose is an addition beside them, and its parents are
  cleared. Mixed or unsourced adds stay invalid.
- **Concern links** (audited): a disposition loses links to action IDs the plan
  lacks, and an addressed or satisfied one that then links none gets the actions
  on its needs, as v6 records an unanswered concern.

A discussion planned under v6 cannot continue under v7. This is tested offline
only.

### Set-aside reasons, checker flags and change claims (v8)

The first v6 trials, JRC `run-a89957db` and Stat `run-6455e495` (21–22 October),
applied 11 and 2 changes. Their saved outcomes show three patterns:

- All 4 applied set-asides (JRC) argued that the source states no obligation or
  scope, that the evidence is thin, or that the base lacks the need; the checker
  passed all 4. Of the 6 other set-asides, all sent to human review, 4 argued
  obligation or scope, 1 thin evidence and 1 that a split superseded the need.
- 62 of the 88 human-review outcomes failed only on the checker's
  `condition_supported` or `obligation_preserved`, 37 of them retained or
  base-covered needs. The checker's rationales approved these needs and read a
  source that states no condition or obligation as "not supported" or "not
  preserved".
- 453 of the 860 experience claims of completed cases were `keep`, which changes
  nothing but needs a mediator decision; 2 applied changes rested on experience.

`rq1-fa-dialogue-v8`:

- **Set-aside reasons.** A set_aside names one reason: `not_find_or_access` (the
  need serves no find or access task of a data user), `statement_about_sources`
  (it states a fact about a document, organisation or specification),
  `duplicate` or `contradicted_by_source`. A missing obligation or scope, thin
  evidence and the base lacking the need are not reasons: such a need is
  retained, or deferred with a question. The validator requires the reason and
  what it needs, and the checker judges whether it holds:
  - `duplicate` names the other need in `duplicate_of`. That need is in the
    working list and the plan retains, covers or defers it as it is, so two
    needs cannot set each other aside, nor can a need go with a rewritten one.
    The duplicate cites no source the other lacks; needs from different sources
    are merged, as before, so that the working list keeps every source.
  - `contradicted_by_source` cites the passage with relation `contradicts`; the
    passage must occur in its source at its offset or exactly once, otherwise
    the set-aside goes to human review.
  - A need already set aside before the discussion can be set aside again
    without a reason; nothing changes.
  A reason on another action is cleared (audited). An applied set-aside record
  keeps the reason in `details`.
- **Checker flags.** The check contract `DefinedChecks` defines
  `condition_supported` and `obligation_preserved` for actions that write a
  statement, and asks for true on the others. They now decide revise, merge,
  resolve, split, recover and add only. With the same checker answers, 19 JRC
  and 18 Stat outcomes would have been retained rather than sent to human
  review. Set-asides no longer depend on these two flags, only on their reason,
  `disposition_justified` and `preserves_distinctions`; in those runs the two
  flags held back 4 set-asides, none of which gives a listed reason.
- **Change claims.** A review holds at most one experience claim, which proposes
  a change: merge, split, drop or missing_need (v6 allowed two, keep among
  them). A drop claim follows the set-aside reasons. The schema shows both
  rules, but parsing accepts other kinds and up to four claims: a keep claim and
  every claim after the first sound one get one correction and are then left
  out, so a claim never fails a role's review, and the case with it.

A discussion planned under v7 cannot continue under v8. This is tested offline
only.

### Set-asides against the scope judgement (v9)

The first v8 trial, JRC `run-0ebfaffd` (22 October, derived at 6a from
`run-a89957db`), applied 4 set-asides, all with a listed reason, and the checker
passed all 4. 3 of the reasons contradict the F/A scope judgement that the scope
step made for the need, with an actor, task, example and sources: it serves
find, as an information requirement. The mediator's arguments were the ones v8
excludes, e.g. "Users can know the creator of a dataset" set aside as
`not_find_or_access` because the source has "only the isolated word Creator".
The fourth, which the scope step judged unresolved background, is consistent.

`rq1-fa-dialogue-v9`: a set-aside whose reason the need's checked scope
judgement contradicts is not applied. It goes to human review with the
disagreement recorded (`scope_conflict`):

- `not_find_or_access` or `statement_about_sources` against a need that serves
  find, access or both: both reasons say no data user looks for the information
  (in the Stat v8 trial, `run-c4cbca44`, a need on code lists for dimension
  values that serves both was set aside as a statement about the sources);
- `statement_about_sources` against a need judged an
  `information_requirement`.

A need that scope left unresolved or judged to serve neither is not
contradicted.

`duplicate` and `contradicted_by_source` are not judged by scope, a need
without a checked judgement has nothing to contradict, and a need already set
aside stays as it was. The mediator prompt states the rule; the packet already
shows each need's `fa_scope`.

**Splits written as several actions.** In both v8 trials most invalid cases
ended on the rule that every need is named exactly once (Stat 8 of 15, JRC 7 of
14), mostly in cases whose roles proposed a split or a missing need: such cases
ended invalid in 27% (Stat; 9% under v6) and 34% (JRC; 23%), while cases
without a change claim almost never did. Of the 9 plans that named one need in
several actions, 5 gave each action its own statement and sources: a split
written as two retains or two adds. v9 tells the mediator how to write a split
(one split action with a child per new need), and repairs such a plan (audited):
when every action naming a need names only that need, is a retain, revise or add
with its own sourced statement, every statement differs from the others and from
the need's own wording, and nothing in the plan leaves the need to a person, the
actions become one split with those statements, sources and rationales as
children, under the first action's ID; concern links follow. It stays invalid
with a set-aside or other disposition beside them, a statement without sources
or repeating the need, a question or alternatives on an action, an unresolved
concern on them or a review question on the need, a need set aside before the
discussion (a retain does not restore it) or a labelled need. An add beside a
retain or revise is first read as an addition (v7).

**Broken parts no longer fail a whole answer.** The concern, review-question and
split-child contracts come from the routed workflow (18 October) and every
discussion version reused them unchanged. An answer that broke one of them failed
as a schema error, before correction or salvage could keep the rest; in the v8
trials 5 cases ended so (questions without alternatives or without concerns, a
split of more than four new needs, new needs without IDs, a concern of an unknown
kind, evidence IDs written as one string). v9 has its own copies of these
contracts: the schema still shows each rule (only a split child's ID may now be
left out), but the answer is read, and

- a concern of an unknown kind gets one correction and is then left out of the
  review (audited), like a broken experience claim; one evidence ID written as a
  string is read as a list;
- a question without needs, concerns or alternatives, and a split of more than
  four new needs, get one correction; if they stay, salvage drops only them;
- a split child without an ID gets the next free one (audited).

The legacy v1 protocol keeps the routed contracts.

A discussion planned under v8 cannot continue under v9. This is tested offline
only.

### Checks of split children (v10)

The checker has always had to check every plan action exactly once. gpt-oss
often also checks a split's new needs as actions of their own (`A1`, `A1.1`,
`A1.2`), or checks only the new needs; that answer was refused and, after one
correction, the case was lost. A replay of every saved checker answer shows this
was the cause of the check-count failures before v9 too (JRC v6 1 case, JRC v8
1, Stat v8 2); v9 let many more splits through, and the first JRC v9 trial
(`run-4d980b17`) lost 6 of its first 42 cases to it. `rq1-fa-dialogue-v10`
accepts a check of a split's new need beside the check of the split and does
not use it (each new need is verified with the split's check, as before); every
action still needs exactly one check, and the correction names what is missing,
repeated or unknown. The checker is told to check a split once, and a check
answer may hold up to 24 checks. On the saved answers of the five runs, v10
accepts every answer the old rule accepted. The legacy v1 protocol keeps its
rule.

A discussion planned under v9 cannot continue under v10. This is tested offline
only.

### Quotations that differ in whitespace or hyphenation (v11)

A change (revise, add, merge, split) is applied only when every quotation it
cites is found in its source unit, and until v10 only exact text counted. In JRC
`run-efc543e4` (v10), 16 changes passed the plan rules and the checker; 3 were
applied and 13 blocked, 10 of them because a quotation was not exact text of its
unit: 5 differed only in whitespace (a line break written as a space), 1 wrote
`platform-independent` with U+2011 where the PDF text breaks the line after the
hyphen, 2 left text out with "..." and 2 were not in the unit.

`rq1-fa-dialogue-v11` folds both texts before it compares them
(`rq1-fa-quote-match-v1`): every whitespace run reads as one space and U+2010 and
U+2011 read as `-`; a line break after a hyphen reads both as nothing and as a
space, since the mediator writes it either way. When the folded quotation fits
exactly one span of the unit (overlapping matches and both readings counted), the
change cites that span's exact source text and offset, so the strict verifier and
the new need see exact text. `citation_repairs` records the action (a split's new
need by its own ID), the offsets, the hash of the exact text, the hash of the
quotation as written and the method; the outcome row keeps the quotation as the
mediator wrote it. Text left out or changed is never matched, a quotation that
fits more than one span stays blocked, and an exact quotation is matched first and
recorded as before. The legacy v1 protocol keeps the exact match, and so does the
check of a passage cited for a `contradicted_by_source` set-aside (no saved run
has one).

A replay of the folded match on the saved changes blocked by a quotation (JRC v6,
v8, v9, v10; Stat v6, v8: 31) finds 20 (JRC 1, 2, 5, 6; Stat 5, 1); the other 11
left text out (7) or are not in their unit (4). Those 20 would then reach the
support check, which may still block them: in `run-efc543e4` it blocked 2 of the
5 changes it assessed in full.

A discussion planned under v10 cannot continue under v11. This is tested offline
only.

### Plans that keep no need disposition (v12)

Since v3 a plan that stays invalid after its correction is salvaged, but up to
v11 only when at least one need keeps a valid disposition of the mediator.
Otherwise the case stopped as `invalid_output_pending_human_review` with one
general question, and the mediator's proposals were not shown. In JRC
`run-0834b623`, JRC `run-12a2c91a` and Stat `run-1428af21`, 10 of the 12 lost
cases stopped there (the other two: one schema failure, one budget stop). All 10
held a single need, so one invalid action on it lost the case. On its last try
the mediator wrote:

| Habit | Cases |
|---|---|
| A split or revision of a need labelled as covered by the base; after the correction, covered_by_base beside the split | 5 |
| One action per part: the parts of a split that have a source split off, the others set aside or deferred, each as an action on the one need (or set-asides of rejected ideas beside a revision) | 3 |
| A set-aside without a review question, twice | 1 |
| A split whose new needs have no sources | 1 |

`rq1-fa-dialogue-v12` (`rq1-fa-salvage-v2`) salvages such a plan too: every need
gets the marked system deferral, which keeps the original need for a person. The
salvage applies nothing and writes or cites nothing. What v12 recovers is the rest
of the discussion, not the dropped proposals. A salvaged draft goes through the
response round and the final mediation as before, but the roles and the final
mediator see only the system deferrals; the draft's dropped actions, with their
full proposals, stay in its audit (`mediation.salvage.draft.dropped_actions`).
Dropped actions become unapplied review rows (`salvage_rejected`) only when the
applied plan is the salvaged one, which after a response round is the final: when
the final keeps nothing too, its dropped actions are shown; when the final is
valid, it is checked and applied like any other plan, and the draft's proposals
remain only in the audit.

The salvage audit records `nothing_kept`; the case's mediation records
`salvage_nothing_kept` when its applied plan kept no mediator action, and the run
metric `salvaged_nothing_kept` counts those cases apart within `salvaged_cases`,
so that the lost-case counts of earlier versions stay comparable. A plan that
cannot be parsed, or whose salvaged form exceeds the plan contract or fails the
plan rules, is still not salvaged.

A draft salvaged this way adds the response round, the final mediation and the
check, about 6 to 8 calls. The 9 lost cases of those runs that stopped at the
draft had used 6 or 7 of their 16 calls; the one that stopped at the final had
used 14 and adds only the check. A case whose extra calls run out stops as
`budget_pending_human_review`, and one whose final or check stays invalid as
`invalid_output_pending_human_review`, where v11 would have stopped it earlier as
invalid output; the metric `lost_after_salvage_nothing_kept` counts these lost
cases apart.

A discussion planned under v11 cannot continue under v12. Cases of v3 to v11 keep
the first salvage rule when `salvage_plan` is replayed on them; v1, v2 and cases
without a policy never reach salvage in a discussion. This is tested offline
only.

### Checks of IDs outside the plan (v13)

Since v10 the checker may check a split's new needs beside the split; any other
check had to name an action of the plan. In 10 cases of eight saved runs, the only
fault of a checker answer was a check of an ID that is not an action of the plan,
beside one check of every action. In 4 of them the second try did the same, and
the case was lost:

| Run | Checked beside the plan's actions | Second try |
|---|---|---|
| Stat `run-6455e495` (v6) | `set_aside`; `defer`, `set_aside` (action types, 2 cases) | corrected |
| Stat `run-c4cbca44` (v8) | `retain_B1`, `defer_none`, `set_aside_X1` | corrected |
| JRC `run-4d980b17` (v9) | P1, an experience proposal (and the new needs A1.1, A1.2, which v10 accepts) | corrected |
| JRC `run-efc543e4` (v10) | SA1, SA2 (invented) | corrected |
| JRC `run-efc543e4` (v10) | P1, an experience proposal | the same; lost |
| JRC `run-12a2c91a` (v11) | S1 (invented) | corrected |
| Stat `run-d069be4d` (v11) | A2, a parentless defer the salvage had dropped | the same; lost |
| JRC `run-36730b38` (v12) | S1, beside the two retains of the final plan | the same; lost |
| Stat `run-289823d2` (v12) | three experience claims | the same; lost |

Before v10 the error named no ID ("Check every action exactly once."), so the
first tries up to v9 were found from the IDs of the saved answers. None of the
other saved runs (JRC v6, v8 and `run-0834b623`, Stat v10) has such an answer.
In all: 4 lost cases and 6 second tries. A replay of the 653 checker answers saved
in these 12 runs keeps all 616 that the v12 rule accepts; in the runs from v10 on,
every refused answer (10, in 6 cases) failed only on such IDs, and v13 accepts it.

`rq1-fa-dialogue-v13` ignores such a check as v10 ignores a check of a split's
new need: the answer is accepted when every action of the plan has exactly one
check, and the other checks are not used. Apply reads each action's check by the
action's ID; a proposal row or a row the salvage rejected never takes a check. A
missing check, a check filed under another ID (which leaves its action without
one, as a check named after the action type instead of the action's ID does) and a
repeated check of an action are still refused, and the correction names
what is missing, repeated or unknown. So no action is applied without its own
check, and every answer the v12 rule accepted is still accepted. The legacy v1
protocol keeps its rule.

The case's mediation and discussion trace record the ignored IDs
(`ignored_check_ids`, as internal IDs: an experience claim appears under its claim
ID), the run metric `ignored_checks` counts them, and `scripts/fa_base_report.py`
lists them. The metric counts completed cases only, because it is read from the
mediation record, which only a completed case has: a case stopped after an accepted
check would not be counted (no such case could be produced offline). A derived
base-review trial does not inherit the metric. In the runs
above, the 4 lost cases would have gone on to apply, and each of the 6 corrected
first tries would have saved a check call.

A discussion planned under v12 cannot continue under v13. This is tested offline
only.

### Scope contract v1 at apply (v13)

Scope contract v1 (Junda, 23 October) has one rule: every need, wherever it is
written, passes both scope tests. They are the F/A test (`rq1-find-access-v1`) and
the catalogue-record test (`needs.SCOPE_SYSTEM`, which names the record that would
state the need). At normalisation, `rq1-profile-scope-v7` runs the record test on the
needs the F/A test keeps (see `RQ1_NEEDS.md`). Before v13, the needs the discussion
wrote were judged by neither test. Their `fa_scope` had status `checked_mediation`:
13 of 86 active needs in JRC v12 and 13 of 85 in Stat v12. Among the needs it wrote
were rules such as "Publishers must use all DCAT classes and properties consistently
…".

In v13, apply judges every need a change writes (a revision, each part of a split,
an addition, a merge result) with both tests. It does so after the source and
support gates and before the change is accepted:

- One call per test for the needs of one change. The prompts and contracts are
  those of normalisation, unchanged; the F/A contract stays frozen per run.
- A need fails the F/A test when it serves neither or is unsupported. It fails the
  record test with `not_catalogue_level`, `not_find_or_access` or
  `operational_data_processing`.
- If any written need fails, the change is not applied. It becomes `blocked_change`.
  Its `scope_block` names each failing need with the test, the record resource and
  the rationale. Its `validation_error` names the first failure. The parents stay. A
  split with one failing part is blocked whole, so nothing is lost.
- An applied need carries both verdicts (`fa_scope`, `profile_scope` with
  `record_resource`, `record_statement` and `failed_tests`), not `checked_mediation`.
  The outcome row lists every tested need under `scope_tests`.
- A missing judgement (no valid row after the correction) keeps the need, flagged,
  as at normalisation: `profile_scope_not_checked` or `fa_scope_review_required`.
- The calls go to the `profile_scope` model. The discussion plan records that model
  beside the others.
- The calls share the case budget with the apply-time assessment calls. As there, an
  exhausted budget blocks the change, with "F/A scope test budget exhausted;
  original needs retained.". It never stops the case. So does any other error the
  tests raise, such as a changed checkpoint.

Retained, deferred, base-covered and set-aside needs write nothing and are not judged
again. `scripts/fa_base_report.py` lists the needs the record test set aside at
normalisation and the changes the scope tests blocked at apply, each counted apart
from the other set-asides and blocks. The model's judgement shows only live; the
tests use scripted answers.

### Answer habits

Unit tests with ideal scripted answers did not show what a change does to the
next step: v9's split repair produced splits, and only the live checker showed
how it answers them. `tests/test_fa_quirks.py` runs whole discussion cases
against the answer habits the models showed in saved live runs (checks of split
children or only of them, checks named after action types, one action per
concern, invented need IDs, adds naming their need, a split written as several
actions, oversized or unnamed splits, empty questions, loose set-asides, claim
kinds as concern kinds, keep and second claims, quotations with a line break
written as a space or a hyphen written as U+2011, and single-need plans that keep
no action: a labelled need split beside its covered_by_base, the parts of a split
set aside or deferred on the one need, set-asides of rejected ideas beside a
revision, and checks of IDs outside the plan: an experience proposal, an action
the salvage dropped, an invented ID, experience claims) and checks that every case ends
in a defined state, accounts for every need, applies only what the rules allow
and leaves a record that validates. A habit seen in a new live run is added
there.

### Cheap trial from a saved machine inventory

`POST /api/rq1/v2/runs/{id}/derive` accepts `start_from: "base_review"` with a
fresh `expected_version` and rationale. The source must be inactive, F/A, have
completed stages through consolidation, a machine snapshot and a valid catalogue
pin, and have no human decisions or baselines. The child restores the snapshot's
requirements, active IDs, set-asides, conflicts and consolidation events. It
clears discussion/base-review audit state and preserves source and call lineage,
the snapshot hash and the parent's discussion hash. The parent is unchanged.

Only name, rationale, execution mode, timeout fallback and models/options for
`base_review`, `base_review_check`, `stakeholder_review`, `mediation`,
`mediation_check` and `assessment` may change. `execution_mode: "stepwise"`
pauses after the procedural stage: inspect that cheap result before resuming the
discussion. The two reviewer model slots default to the configured model,
independently of the discussion default. At four needs per batch, 64 needs cost
32 calls and 49 cost 26, before corrections or size splitting. A need reviewed
alone after its batch stayed invalid adds up to two review and two check calls,
and the batch's kept judgements need their own check. Later discussion
revisions add their own review calls; per-case discussion budgets do not grow.

`scripts/fa_base_report.py` reads the run
and coverage through GET requests and produces Markdown and CSV. It reports the
classifier/reviewer matrix, added flags and entry terms, checks, removed labels,
disputes with the label kept (v1/v2), source-stated additions, not-reviewed needs
with their errors, after-discussion results, discussion actions on labelled needs,
salvaged cases (and, since v12, those that kept no mediator action and the cases
lost after such a salvage), mediator actions rejected by salvage, the checks of IDs
outside the plan that v13 ignored, reviewer usage and case stop reasons. The
CSV has `policy`, `errors` and `isolated` columns. Legacy v1 reports leave
reviewer columns empty. Run this helper against a saved trial; it never starts
inference or changes the run.

The helper preserves legacy `entries_express_need` checks under that name and uses
`verdict_supported` for the newer reviewer. Raw check JSON remains in the CSV;
its readable summary labels the actual field rather than reinterpreting old results.

```sh
python scripts/fa_base_report.py --api http://127.0.0.1:8013 --run <run-id> --out <report-directory>
```

### Live results so far

All on KI:connect with `inferenz-gpt-oss-120b` for every step. Two runs (20
October 2026) used `rq1-base-expert-v3`, the earlier version of these fixes, and
stopped after 6a. JRC `run-934df8ba` was derived from `run-fd39639e` at 6a,
reviewed under `rq1-base-expert-v4` and ran the first live discussion
(`rq1-fa-dialogue-v3`, 20–21 October).

| Run | Needs into 6a | Labelled by base check | Checked | Not reviewed | Check failed | Effects | Working after 6a |
| --- | --- | --- | --- | --- | --- | --- | --- |
| JRC `run-fd39639e` (v3) | 41 | 19 | 41 | 0 | 0 | 8 confirmed, 2 added, 11 removed, 17 agree, 3 note | 31 |
| StatDCAT `run-7211c6ec` (v3) | 61 | 16 | 58 | 1 | 2 | 6 confirmed, 6 added, 8 removed, 36 agree, 4 note | 47 |
| JRC `run-934df8ba` (v4) | 41 | 19 | 37 | 0 | 4 | 8 confirmed, 2 added, 10 removed, 15 agree, 6 note | 30 |

In `run-fd39639e` the labels after 6a are exactly its 10 checked restatements (8
confirmed, 2 added). In StatDCAT 2 of the 16 classifier labels were neither
confirmed (6) nor removed (8), and the one invalid verdict left only its own need
unreviewed. In `run-934df8ba` 2 of the 4 failed checks were domain uses on
another resource class, which the v4 check could not pass (fixed in v5).

The discussion of `run-934df8ba` built 91 cases: 38 completed, 5 salvaged (2
additions rejected, not applied) and 48 pending human review (27 invalid output,
19 budget, 2 single-need packets over the packet bound). Of the 19 budget stops,
14 were inputs over 45,000 characters and 5 ran out of generations. 7 changes
were applied, 5 of them set-asides of needs already set aside. It took 962
calls (649 stakeholder review, 246 mediation, 52 checks), about 8.9M tokens and
about 3 h 20 min. The v4 changes above address the 15 stakeholder reviews that
named IDs outside the case, the input-size and generation stops, the cut-off
plans and the repeated set-asides. They do not address the 6 draft plans that
stayed invalid after correction, the 4 final plans that regressed to the
round-1 concerns, or the check that returned the wrong number of checks. They
are not yet run live.

Labels of `rq1-base-expert-v3` or `-v4` are refused by the v4 discussion; derive
a base-review trial from those runs to continue under v5 (27 review and check
calls for JRC under v4; StatDCAT about 32 before corrections).

### Limits

This labels needs the pipeline produced; it cannot recover a base term that
extraction never proposed. The original classifier already reads full entry text
with strict condition and obligation guards. Still, a manual inspection of the
JRC development run (19 October 2026, pipeline output only) found about 11 of its
38 working needs restating a DCAT-AP 1.1 entry the classifier had not matched.
Ranked candidates alone would have let the reviewer cite the right entry for 6
of them, and the guards admit 4; with the index the guards admit 9. The shared
condition guard still refuses the 2 whose condition repeats DCAT's own usage
guidance (for example "when a download URL is provided"); changing it would also
change classification. Its error now tells the reviewer to cite the entries that
state the condition or to answer `domain_use_of_base`, and a refusal that stays
leaves only that need unreviewed. Newly written discussion revisions are the other gap
addressed. The `dcat-ap-1.1.0` catalogue has no definitions, so that version
relies on phrases and usage notes. The reviewer, checker and classifier are all
model judgements, not ground truth, benchmark accuracy or evidence of effort
savings.
