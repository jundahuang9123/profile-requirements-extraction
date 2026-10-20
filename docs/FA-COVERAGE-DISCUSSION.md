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
6. **Cases:** task-based grouping can combine needs from different source files. Bounded windows and packet size limits are recorded; this does not guarantee all distant related needs meet. Include latest set-asides and unresolved proposals, labelled as such. Oversized cases split with a shared group hash; an oversized singleton remains pending human preparation.
7. **Discussion:** save independent initial positions without peer answers; aggregate issues; obtain a mediator draft; solicit responses to proposed changes or material objections even from a role previously marked finished; obtain final mediation when responses occurred; independently check every disposition, including retain and set-aside. No concern is a valid response; silence or repetition does not establish consensus or weight.
8. **Persistence/review:** apply source-checked machine revisions transactionally. Preserve before/after revision IDs, parents, evidence and observations. Invalid changes retain parents and a review question. A case whose structured output remains invalid after bounded correction is explicitly queued for human review; under `rq1-fa-dialogue-v3` the valid parts of its plan are salvaged first (see below). The run can continue with other cases. Transport failures still stop unfinished work for supported resume. Machine outcomes are never human acceptance. The pre-discussion machine snapshot remains unchanged.

The mediator can propose retain, revise, split, merge, add/recover, covered-by-base, reversible set-aside or defer. Priority requires explicit applicable source support. Cross-case conflicts require joint review rather than a decision that cannot see both sides. New wording invalidates old base comparisons and shows a recheck flag. A covered-by-base label cannot be manufactured without an existing checked match.

## Coverage and traceability

`GET /api/rq1/v2/runs/{run_id}/coverage` returns source processing, extraction assignments/attempt statuses, source spans, observations, revision links, transformation events, set-asides, base/scope annotations, discussions and human-decision links. It exposes unprocessed and unaccounted work explicitly.

The UI provides a collapsed coverage/inventory view and saved dialogue phases. The needs export and trace export carry the same ledger and model choices. The inventory contains historical need revisions as well as current ones; the working IDs identify current needs not labelled covered by base. Do not confuse inventory revision count with distinct current requirement count.

Processing every passage is not evidence of finding every requirement. Accounted observations are not independently evaluated semantic coverage. Quality/recall and effort saving require separate adjudication and evaluation.

## Evidence expansion and budgets

Both dialogue protocols measure the exact JSON sent after reversible identifier aliases against the unchanged 45,000-character context limit. The `rq1-fa-context-budget-case-v1` phase audit records internal, wire and measured sizes plus the wire hash. An oversized case retains its original needs and accepted phases and is deferred visibly to human review; later cases continue. Full internal payloads still determine checkpoint identity.

A stakeholder may request a specific missing passage. Bounded lexical retrieval searches only the frozen run evidence IDs: up to eight distinct queries, two passages per query and four new passages overall. It records query, exact selected location, source/content hash, eligible-ID hash and excluded count. No benchmark/reference file or web retrieval is available to discussion. A no-result query remains visible as unresolved.

A case permits at most 14 model generations including schema/semantic corrections and revision assessments, 112,000 reserved output tokens and 1,800 seconds of accumulated model-call time. Primary calls reserve 4,000 tokens and truncation correction may reserve 8,000. The time guard prevents starting another request after the recorded budget; the provider transport timeout bounds an in-flight request. With many revisions or corrections, some work can remain for human review. It is not reported as successful mediation.

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
and the parent plan/implementation identity; the child's call log covers only
new requests. Upstream settings and primary model choices cannot change in this
operation. Totals must include parent calls when reporting the whole workflow.
A discussion planned under another protocol, such as `rq1-fa-dialogue-v2`, is
refused; derive a base-review trial instead (see below).

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
before discussion. Policy `rq1-base-expert-v4` reviews current revisions sorted
by ID, in batches of up to four: one review generation and one independent check
per batch. (`rq1-base-expert-v3` names an earlier version of these fixes whose
prompts differ; only JRC `run-fd39639e` and StatDCAT `run-7211c6ec` used it.)
Each generation allows at most one correction, which shows the rejected answer
and names its problems by the N/B/E aliases the model saw (v2 sent internal
revision IDs and no previous answer). Oversized payloads split; a single need
that cannot fit the 30,000-character payload budget is marked `not_reviewed` /
`payload_budget`. An oversized independent-check payload splits its checks
without repeating the already accepted review.

One need no longer sinks its batch. When a batch stays invalid after its
correction, each judgement in its newest parsed answer that is valid on its own
is kept, and still independently checked; every other need is reviewed alone.
An answer that fails the output schema (for example one row citing too many
excerpts) is still read row by row: its parsed JSON is saved on the attempt, so
a resumed run makes the same decisions. Checks are isolated the same way. Kept
results record `isolated_from_failed_batch`. Only a need whose own review stays
invalid remains `not_reviewed` / `invalid_output` with `base_review_pending` and
its validation `errors`; a need whose own check stays invalid is `not_reviewed` /
`check_invalid_output`, also with its errors, and its unchecked verdict is not
recorded as a judgement. v2 marked whole batches: 10 of
46 JRC needs in three batches. A verdict may cite up to 12 entries (one per item
of a need that lists items) and up to 12 of the need's own excerpts; the old
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
verdict is right: cited entries share the resource and property meaning, no index
entry (including a classifier match) names the information of a new need, or the
catalogue text is indeed insufficient) and
`nothing_lost`. Both must be true before labels change; a failed check adds
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

For opt-in runs, `rq1-fa-dialogue-v3` gives each discussion packet the compact
review and pinned classifier-matched/reviewer-cited entry text. Stakeholders can
identify additions the base lacks. A need labelled `covered_by_base` may be
retained, disposed `covered_by_base` or deferred with a human question and
alternatives; any other action on it (revise, merge, split, resolve, recover,
set aside) is refused. A need whose label the checked review removed is an
ordinary working need and is not forced into deferral. The rule that a `dispute`
requires a deferral with a human question applies only to cases planned under
`rq1-fa-dialogue-v2`. Until 20 October 2026 deferral of a labelled need was
refused too; in the JRC trial that rejected mediator drafts in 18 cases. Cases and their budgets are unchanged. Every revision created
by revise, merge, add, recover or split requires a new base check. After all
cases, a second procedural pass reviews those current revisions before the final
coverage ledger. Reviewed revisions clear `base_recheck_required`; unreviewed
ones retain it. Neither procedural review nor mediation is human approval.

The ledger adds verdict/effect counts by phase, coverage-label provenance split
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
  an action ID gets that action's needs; question/concern links are made
  reciprocal when one side names the other; in a plan without additions, an
  action without a need that no concern links and that carries no statement,
  source, child or question is an empty note and is dropped; empty deferral fields
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
  like any others. Salvage needs at least one valid disposition of an existing
  need; otherwise the case stays `invalid_output_pending_human_review`. A case
  whose applied plan was salvaged stops as `bounded_fa_dialogue_salvaged`, its
  mediation lists `salvage` audits by phase, and metrics count `salvaged_cases`.

Offline replay of the 57 saved invalid plans (no model calls; the latest parsed
plan of each case) gave: 10 valid after repairs, 14 salvaged (each keeping the
mediator's disposition of every need; 67 concerns left to a person), 26 without
a valid need disposition, and 7 without a parseable plan. That replay predates
the narrower repair 3 and the rule that salvage keeps no addition, so fewer
plans may now be valid after repairs. The guidance, corrections and salvage have
not yet run live. v3 refuses to continue a
discussion planned under v2 and refuses labels from an earlier base-review
policy; derive a separate base-review trial instead. The legacy v1 protocol is
unchanged.

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
mediator actions rejected by salvage, reviewer usage and case stop reasons. The
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

Two live runs (20 October 2026, KI:connect) used `rq1-base-expert-v3`, the
earlier version of these fixes, and stopped after 6a; neither reached the
discussion.

| Run | Needs into 6a | Labelled by base check | Checked | Not reviewed | Check failed | Effects | Working after 6a |
| --- | --- | --- | --- | --- | --- | --- | --- |
| JRC `run-fd39639e` | 41 | 19 | 41 | 0 | 0 | 8 confirmed, 2 added, 11 removed, 17 agree, 3 note | 31 |
| StatDCAT `run-7211c6ec` | 61 | 16 | 58 | 1 | 2 | 6 confirmed, 6 added, 8 removed, 36 agree, 4 note | 47 |

In JRC the labels after 6a are exactly its 10 checked restatements (8 confirmed,
2 added). In StatDCAT 2 of the 16 classifier labels were neither confirmed (6)
nor removed (8), and the one invalid verdict left only its own need unreviewed. Both runs'
6a labels come from v3 prompts, so a v3 discussion refuses them; derive a
base-review trial from them to continue under v4 (about 22 and 32 review and
check calls before corrections).

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
