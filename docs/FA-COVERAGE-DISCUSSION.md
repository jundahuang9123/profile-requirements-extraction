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
8. **Persistence/review:** apply source-checked machine revisions transactionally. Preserve before/after revision IDs, parents, evidence and observations. Invalid changes retain parents and a review question. A case whose structured output remains invalid after bounded correction is explicitly queued for human review; the run can continue with other cases. Transport failures still stop unfinished work for supported resume. Machine outcomes are never human acceptance. The pre-discussion machine snapshot remains unchanged.

The mediator can propose retain, revise, split, merge, add/recover, covered-by-base, reversible set-aside or defer. Priority requires explicit applicable source support. Cross-case conflicts require joint review rather than a decision that cannot see both sides. New wording invalidates old base comparisons and shows a recheck flag. A covered-by-base label cannot be manufactured without an existing checked match.

## Coverage and traceability

`GET /api/rq1/v2/runs/{run_id}/coverage` returns source processing, extraction assignments/attempt statuses, source spans, observations, revision links, transformation events, set-asides, base/scope annotations, discussions and human-decision links. It exposes unprocessed and unaccounted work explicitly.

The UI provides a collapsed coverage/inventory view and saved dialogue phases. The needs export and trace export carry the same ledger and model choices. The inventory contains historical need revisions as well as current ones; the working IDs identify current needs not labelled covered by base. Do not confuse inventory revision count with distinct current requirement count.

Processing every passage is not evidence of finding every requirement. Accounted observations are not independently evaluated semantic coverage. Quality/recall and effort saving require separate adjudication and evaluation.

## Evidence expansion and budgets

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

`POST /runs/{id}/derive` with `start_from: deliberation` can continue a failed or
interrupted F/A discussion under the new policy. It copies completed upstream
outputs and all case checkpoints without replaying extraction or completed
cases. The parent stays unchanged. Lineage records inherited call counts/hashes
and the parent plan/implementation identity; the child's call log covers only
new requests. Upstream settings and primary model choices cannot change in this
operation. Totals must include parent calls when reporting the whole workflow.
