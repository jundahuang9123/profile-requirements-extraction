> Original agreed design, retained for review. Implementation details and limitations: [F/A workflow guide](../FA-COVERAGE-DISCUSSION.md). Controlled live evaluation is a subsequent activity; no live results are claimed here.

# RQ1 work plan: preserve requirement coverage and make discussion substantive

Date: 19 October 2026. Status: proposed implementation and evaluation plan; no implementation or live experiment started by this document.

## 1. Objective and boundaries

Gather source-supported requirements for finding datasets and understanding or obtaining access to them. These requirements inform later DCAT profile or extension development; RQ1 does not design an extension, select RDF properties, or generate an ontology.

Optimise for retaining useful requirements. Compact wording and fewer review items are secondary objectives, permitted only when supported distinctions remain recoverable and visible. Do not claim exhaustive extraction.

Findability and accessibility are the research scope. Interoperability and reusability can be downstream considerations; neither is automatically achieved, and neither should independently expand the extraction scope. Information such as quality, structure, population, format or usage conditions can be in scope when sources connect it to discovering, selecting or accessing datasets. Do not impose an arbitrary ban on those topics.

Preserve the user's single planned extraction pass. Chunking is allowed. Bounded correction of an invalid response is allowed. Repeated whole-corpus extraction until a desired requirement count is reached is not part of the design.

Existing reference requirement lists and previous mock-evaluation matches remain evaluator-only material. Do not use them in extraction, routing, discussion, prompts, development fixtures or retrieval. HealthDCAT, JRC and Stat have already informed development and must not subsequently be described as untouched held-out tests.

## 2. What already exists and what needs to change

The inspected checkout is `dcat-ap-base-recovery`. Its documentation already describes finding/accessing datasets as the purpose of scope checking. This is therefore partly a failure to enforce the intended distinction, not a wholly new principle that can be fixed by adding one sentence to a prompt.

Existing components to extend rather than replace:

- Source routing, exact evidence links, immutable snapshots and resumable work.
- Need grouping, source-support checks, base classification and visible set-asides.
- Stakeholder messages, mediation outcomes, human questions and export traces.
- `step_models`, provider model-list validation and model-aware generation checkpoints.
- Qwen answer/reasoning separation and bounded structured-output recovery.

Observed HealthDCAT behaviour motivates the redesign: 576 active needs were split into 542 cases; 508 cases had one need. Only five cases reached a second stakeholder round. The final dispositions were 542 retain, 33 defer and one blocked revision. The run's sources and outputs demonstrate that confirming a citation is insufficient to establish a useful dataset discovery/access requirement.

Current interaction limits: later roles see earlier answers; a role marked finished does not re-engage when a subsequent role raises a new concern; mediation happens after stakeholder turns; cases use shared evidence rather than common tasks; reviews see surviving needs and their linked excerpts rather than the wider source/decision history. The mediator has no reversible need-level set-aside action. All discussion substeps currently share the `discussion` model.

## 3. Work package A — enforce the research scope without hiding uncertainty

### Changes

Freeze a versioned scope contract on each new run. For each candidate, record separate judgements for:

1. Source support: explicit, supported inference, disputed or unsupported.
2. Discovery/access relevance: find, access, both, neither or unresolved.
3. Actor and task: who needs what information to make which source-supported decision.
4. Nature of the statement: information requirement, operational obligation, implementation detail or background observation.
5. Base relationship: served by base, refines a base need, no match after complete comparison, unresolved or unchecked.

Avoid collapsing these axes into one confidence score. A fact may be explicitly supported but irrelevant. A useful need may be relevant but lack enough evidence to publish as supported. Missing use-case documents must be reported; do not invent stakeholder endorsements or turn absent formal use-case links into automatic rejection.

Replace automatic rewriting of arbitrary facts into “Users can know that …” with an actor/task/information requirement contract. Preserve the original actor, modality, negation and conditions. Use the user's preferred “The metadata must let users …” only when the source establishes that obligation; otherwise preserve weaker wording.

### Acceptance

- A survey statistic remains background even when its quotation is valid.
- A requirement to know a dataset's update frequency is distinguished from an obligation to update all datasets at a specified interval.
- Information enabling an access application is distinguished from general legal or equipment compliance duties.
- A specialised discovery need is retained without requiring it to apply to all dataset types.
- Invalid category/applicability evidence cannot erase independently valid source-support or F/A judgements.
- Unsupported or ambiguous items are visible in a review queue, not silently promoted or deleted.

## 4. Work package B — preserve coverage through every transformation

### Changes

Extend the existing provenance into a queryable coverage ledger:

`source span → extraction assignment → observation → need revision → grouping/base/scope decisions → discussion outcome → human decision`.

Every source unit receives an explicit processing result: processed with proposals, processed with no applicable proposal and a recorded reason, failed, or unprocessed. Processing all source units is not evidence of finding every requirement.

Every extracted observation must remain accounted for through a current need, a merge member, a covered-by-base need, a set-aside record or an unresolved review item. No row may disappear because one assessment or one field fails validation.

Maintain two distinct user views:

- The complete traced requirement inventory, including useful needs already supported by the base.
- The working list for later development, with base coverage, refinements and unresolved needs clearly labelled.

Do not generate every requirement in the base specification as a domain demand. Base-only material supplies context and comparison. A source-supported domain need already served by the base stays in the inventory with its domain evidence and base link. “Served by base” does not mean every real catalogue implements it.

Before a merge or compressed statement can replace needs, check preservation of actor, information sought, purpose, conditions, obligation and negation. A summary can be a family label with distinct child needs underneath; it need not replace those children.

### Acceptance

- Every observation has a visible disposition; trace counts reconcile exactly.
- Same-topic needs with different conditions or actors cannot disappear under a broad summary.
- Equivalent duplicates combine evidence and attribution without multiplying the requirement count.
- Failed transformations retain original proposals and a failure reason.
- Exporting and reopening a run preserves the same ledger and links.
- The UI distinguishes processed-source coverage, proposal accounting and independently evaluated requirement coverage.

## 5. Work package C — prepare task-based discussion cases

### Changes

Group related needs by the source-supported task or decision they help with, not only by a shared quotation. A case can contain needs from multiple source files. Keep unrelated details separate and cap context by the deployed model's measured budget.

The case packet contains the relevant needs, their source excerpts with surrounding context, stakeholder tasks, prior set-aside reasons, base annotations and known conflicts. Retrieve only from the run's frozen input corpus. Record retrieval queries, selected spans, exclusions and hashes. Do not retrieve benchmark answers or browse for missing answers during discussion.

Allow an audited, bounded evidence expansion when a role identifies a specific missing piece. This is a targeted source check, not a fresh corpus-wide extraction loop. If no support is found, preserve a question rather than fabricate a requirement.

Include potentially relevant set-aside or unresolved proposals in related cases, with their status visible. Keep unsupported proposals distinguishable from source-supported needs. Every relevant proposal must be considered somewhere; context overflow produces linked cases or explicit pending work, not silent truncation.

Review panel coverage against documented F/A tasks before extraction. Surface overlapping perspectives and documented tasks without a representative. Do not hard-code HealthDCAT roles or invent a researcher role merely to match an evaluator answer. Clearly label any suggested perspective when source documentation is insufficient.

### Acceptance

- Related needs from different documents can enter the same case.
- Different needs citing the same paragraph are not automatically treated as equivalent.
- Decisions involving cross-case needs are reopened in a jointly scoped case or deferred explicitly; they are not resolved without seeing both sides.
- Every retrieved passage belongs to the frozen inputs and has a verifiable source location.

## 6. Work package D — redesign stakeholder interaction and mediation

### Proposed sequence

1. **Independent first positions.** Relevant stakeholders receive the same case packet but do not see each other's initial answers. Each states the source-supported task, whether the needs address it, missing distinctions, interference and a possible remedy. “No additional concern” is a valid concise response.
2. **Shared issue list.** Aggregate positions without erasing minority concerns or equating repeated agreement with stronger evidence. Separate scope, evidence, wording, overlap and genuine incompatibility.
3. **Mediator proposal.** Produce a disposition for every need and a response to every material concern. Identify which roles are affected by each proposed change.
4. **Targeted response.** Affected roles review that proposal and relevant peer objections. A prior finished flag cannot suppress a response to a new issue. Do not force every role to repeat approval of an unchanged case.
5. **Final mediation.** Incorporate supported responses or preserve explicit alternatives and questions. Permit one further targeted round only under a recorded material-issue rule and remaining budget.
6. **Validation and persistence.** Check semantic preservation, citations, source priority where applicable and scope. Apply valid machine revisions transactionally. Invalid changes leave the parents intact and visible for review. No machine outcome counts as human acceptance.

### Outcomes

- Retain a supported need.
- Revise or split an ambiguous/compound need while preserving its source-supported distinctions.
- Merge genuine equivalents with full lineage.
- Recover or add a missing source-supported need from the case's audited input evidence.
- Label a need covered by the base without deleting its domain demand.
- Set aside background/out-of-scope material reversibly with a specific reason.
- Defer unresolved alternatives with one precise question describing what information or decision is needed.

The mediator is a facilitator, not the stakeholder with the strongest vote. Conflicts may be resolved only by explicitly applicable evidence or declared project priorities; never by invented stakeholder weights, majority agreement or model confidence. Independent final checking covers the justification for retaining and setting aside needs as well as changed text; it need not require a separate call per need.

The lone blocked Health revision should be treated as a general citation-handling regression: preserve source-span IDs and absolute offsets through model aliases; use deterministic resolution only when the supplied exact quote resolves unambiguously. Repeated or nonmatching quotes remain unresolved. Do not disable strict citation checks.

### Bounds and acceptance

Use a finite state machine with checkpointed phases and material-change hashes. A new phase is not triggered by repeated wording. As a starting engineering limit for four roles, allow up to 14 generation attempts per ordinary case, including corrections, and a separately declared time/token budget. Evidence expansion or extra rounds consume that same allowance. Larger cases must declare their budget before execution. Exhaustion produces an explicit unresolved outcome.

Tests must show that a late objection reaches the affected earlier role; a supported compromise changes the final machine need; an uncertain priority produces a human question; invalid changes retain parents; empty agreement does not fabricate consensus; repeated identical concerns do not trigger an endless loop.

## 7. Work package E — allow GPT-OSS and Qwen within one run

### Existing support and proposed addition

The application already permits model choices per step, saved at creation and validated against the provider's model list. The recorded KI:connect aliases are `inferenz-gpt-oss-120b` and `inferenz-qwen3-8-27b`. Their current availability must be revalidated through the authenticated provider catalogue before a live experiment; this planning task has not queried the account or run either model.

Split the current discussion route into independently selectable operations:

- `stakeholder_review`
- `mediation`
- `mediation_check`

Keep `assessment` as its existing separate route. Optionally support `discussion_role_models` as an advanced later addition; it is not necessary for the first mixed-model experiment. Model identity must not define stakeholder identity.

For new runs, unset discussion substep choices inherit the explicit `discussion` setting, then the run's configured default. Preserve legacy run semantics. Store a fully resolved mapping at creation. Preserve the router through nested calls so the mediator's bound client cannot accidentally override an explicitly selected assessment model.

Use per-operation effective model options rather than one global reasoning level for every model. Record model, effective reasoning configuration, output allowance, input/contract/policy hashes and case/role/round identity in checkpoints and call audits. Include generation-affecting settings in cache keys; exclude credentials and transport-only settings. Model changes require a linked trial or an explicit new unfinished-work policy, never silent reinterpretation of a completed checkpoint.

### Recommended first hybrid hypothesis

| Operation | Initial model | Reason |
|---|---|---|
| Routing, extraction and normalisation | GPT-OSS | Hold existing upstream behaviour fixed while testing discussion |
| Independent stakeholder positions and responses | GPT-OSS | Keep role arguments comparable across experiment arms |
| Mediator proposal and final decision | Qwen 3.8 | Test whether it combines constraints and formulates resolutions better |
| Independent mediation check and source assessment | GPT-OSS | Check Qwen proposals with another model and deterministic evidence checks |
| Citation/location/accounting checks | Deterministic code | These do not need model reasoning |

This is a testable allocation, not a claim that GPT-OSS is cheaper or that Qwen is superior. Different models may still share errors, and a second model is not an independent human evaluator.

Keep a same-model redesigned-discussion control. Start reasoning settings at a documented supported level; if medium reasoning is tested later, change it in a separate comparison rather than simultaneously changing model, prompt, extraction and budget. Do not enable the highest reasoning setting by default.

### Provider and output compatibility

The official Qwen 3.8-27B card documents thinking control and separate reasoning/answer output. That establishes capabilities of the model family, not the exact KI:connect deployment, nor superiority on requirement extraction. [Qwen model card](https://huggingface.co/Qwen/Qwen3.8-27B).

The client must parse only final answer content as JSON, retain existing handling for leading thinking markers, and reject missing/truncated answers. Store concise explicit decision rationales and numeric usage, not hidden thinking text. vLLM documents that ordinary generation limits such as `max_tokens` also constrain reasoning when a separate thinking budget is not set. Treat reasoning and final JSON as sharing the allowance conservatively, while recording KI:connect's actual returned usage; absent reasoning-token counts mean unknown. Do not assume the gateway exposes every upstream parameter. [vLLM reasoning documentation](https://docs.vllm.ai/en/v0.21.0/features/reasoning_outputs/).

Use KI:connect's current model IDs and verify advertised capabilities before live use. No silent model fallback or rotation after a validation failure. [KI:connect API access documentation](https://help.itc.rwth-aachen.de/en/service/1808737e10424937b76e564ed15d8028/article/4f07ebbbc8c4477a8db9baa441494941/).

## 8. Work package F — run pages, human review and exports

Keep a page per stage with saved, resumable output. Human use remains step-by-step; controlled tests may run automatically.

The discussion page should show the case task, source packet, initial independent positions, issue list, mediator draft, targeted replies, final disposition and before/after need wording. Show agent role and actual model separately. Mark base-covered, supported, uncertain, set-aside and human-accepted statuses distinctly.

Provide a concise review queue with expandable evidence and history. Deduplicate repeated questions while retaining links to each affected need and concern. A deferral should not merely ask the user to re-read all sources: it should state the competing alternatives, missing fact and likely consequence of each choice.

Advanced model choices stay collapsed by default. Offer a simple default configuration and an explicitly labelled experimental hybrid preset. Saved runs show their effective model mapping even if global settings later change.

Exports include machine output before discussion, output after discussion, complete inventory, coverage/disposition ledger, all source links, concise role/mediator decisions, unresolved questions, model/usage audit and policy versions. Human edits append decisions; they do not overwrite machine benchmark snapshots.

## 9. Implementation sequence and code areas

| Order | Deliverable | Main existing areas | Completion gate |
|---|---|---|---|
| 1 | Versioned F/A scope and inventory/coverage semantics | `workflow/models.py`, `needs.py`, `coverage.py`, `evaluation.py` | Accounting, relevance and base-preservation regressions pass |
| 2 | Task-based case packets and audited evidence expansion | `stakeholder_workflow.py`, `evidence.py`, `semantic_consolidation.py` | No lost candidates, cross-source cases and bounded retrieval verified |
| 3 | Mediated interaction state machine | `stakeholder_workflow.py`, `engine.py`, storage parts | Late-objection, recovery, semantic-preservation and bounded-progress tests pass |
| 4 | Independent discussion model routes/options | `llm/step_models.py`, `model_options.py`, `client.py`, workflow API/contracts | Correct per-call model, options, audit and checkpoint identity verified |
| 5 | Run UI and complete exports | `WorkflowWorkbench.tsx`, `RunTraceView.tsx`, `StepModelsSettings.tsx`, need views | Human and automatic paths inspected with actual saved fixture runs |
| 6 | Integrated offline checks, then controlled live pilot | Existing routed-workflow, step-model and needs tests | Go/no-go criteria below met before a full profile run |

Use small reviewable changes in this order; do not combine schema redesign, model switching and a full Health rerun into one unreviewable experiment. Preserve historical runs and local changes. Avoid writing through linked frontend asset directories. A future trial gets a new run ID and explicit lineage. This document does not authorise deployment, inference or changing existing runs.

## 10. Offline test matrix

Use synthetic or independently authored development examples, not evaluator-side profile answers.

| Area | Required test |
|---|---|
| F/A relevance | Supported background facts do not become requirements solely through “users can know” phrasing |
| Source fidelity | No invented actor, obligation, condition, negation or access task |
| Coverage | Every span/observation has a recorded state; failures cannot silently remove proposals |
| Base comparison | Supported domain demand remains traceable when already served by the base; no base-derived demand is invented |
| Consolidation | Equivalent paraphrases merge; specialised conditions and different needs survive |
| Discussion packet | Related cross-document needs can be reviewed together; disallowed reference files cannot be retrieved |
| Interaction | Independent first answers; late objection reopens the affected role; bounded completion without forced consensus |
| Mediation | Valid revisions, splits, merges and additions apply; uncertain conflict preserves alternatives; unsupported ones cannot apply |
| Set-aside/recovery | Reversible decisions preserve sources and appear in the ledger and exports |
| Citations | Absolute source offsets, Unicode and repeated quotations are handled without fabricated matches |
| Model routing | Every discussion substep and nested assessment uses its selected model; defaults/legacy settings remain stable |
| Provider handling | Unknown IDs fail before creation; reasoning configuration is validated per model; no fallback |
| JSON/budgets | Thinking-only, truncated JSON, marker-containing strings and unknown usage metadata handled correctly |
| Resume | Completed phase is reused only for matching model/options/context/policy; active workers remain exclusive |
| UI/export | Before/after and all unresolved outcomes agree with persisted data; credentials absent |

Run focused tests while editing, then the relevant broader suite, schema checks, frontend build and export consistency checks once the integrated change stabilises.

## 11. Controlled experiments and benchmark evaluation

### A. Compatibility smoke

Before any large run, use a small source-only development packet to test the exact KI:connect aliases, structured answers, citation IDs, reasoning options, truncation behaviour and usage accounting. Start with approximately six short calls per model plus strictly bounded correction. This is compatibility testing, not evidence of superior reasoning. No inference is launched by this plan.

### B. Isolate the discussion change

Freeze an audited set of roughly twelve development cases with the same input evidence, candidate needs, roles and budgets. Include source-supported disagreements, possible lost conditions, genuine equivalence, specialised needs, ambiguous priorities, irrelevant background and a no-change case. Choose cases by source/task/error type, not by benchmark reference matches.

Compare:

1. The fixed pre-discussion candidate list, as the no-discussion baseline.
2. Redesigned discussion using GPT-OSS throughout.
3. The same redesigned discussion with Qwen only for mediation and GPT-OSS for stakeholder turns and checking.

An optional later arm swaps the models' jobs or changes reasoning effort, one factor at a time. Role-specific mixed models should also be a later test: otherwise stakeholder effect and model effect become confounded. If tested, counterbalance which model plays which role across repeated cases.

Apply equal declared call limits and comparable evidence/context to discussion arms. Report actual latency, tokens, failed/repair calls and output limits; equal token counts across different tokenizers do not mean equal computation or cost. The proposed 14-call case ceiling gives at most 168 attempts per twelve-case arm before any separately approved extension. Report variability; repeat a small balanced subset before drawing a comparative conclusion.

### C. Validate the revised extraction pipeline end to end

Once offline and discussion checks pass, start one new full extraction trial on a small frozen profile corpus with its correct base, documented scope and role configuration. Because extraction/scope contracts change, reusing old step-3b output cannot validate the new pipeline. A saved case comparison is useful only for isolating discussion.

For development, a fresh Stat or JRC run is smaller than Health. After the workflow is stable, scale to Health using frozen input and base versions. Do not pick whichever run looks best; record failed attempts and policy changes. Pre-register the remaining evaluation protocol before using any genuinely untouched case.

### D. What to measure

Primary outcome: coverage of useful, input-supported F/A requirements. Define reference units atomically and label each as supported by inputs, partly supported, not found in inputs, out of RQ1 scope, or uncertain. Report this eligibility process and excluded counts explicitly. Do not quietly remove difficult references from the denominator.

Report separately:

- Strict coverage of eligible reference units by the traced requirement inventory, including base-covered needs where appropriate.
- Strict coverage by the working list without requiring manual restoration of set-asides.
- Partial coverage, with the missing actor/action/condition named; do not add partial matches to full matches without a declared scoring rule.
- Requirements captured during extraction but lost or weakened downstream.
- Useful additions/corrections from discussion, and useful distinctions lost or unsupported claims introduced by discussion.
- Relevance and evidence support on a random, stratified sample of generated outputs; the incomplete reference list cannot label all unmatched outputs false positives.
- Reviewer questions, duplicates and measured review/edit time on a small human exercise before claiming effort savings.
- Calls, tokens, elapsed time, corrections, truncations, remaining uncertainty and provider metadata limitations.

Use human adjudication blind to model/arm where feasible. Record disagreements. Automated matches are assistance, not the final benchmark authority. Supplementary requirements discovered during evaluation must be labelled separately and applied consistently across all arms, not retrospectively used to favour one run.

## 12. Go/no-go and deliverables

Engineering gate: zero silently unaccounted proposals; zero accepted invalid source links in the regression suite; all historical data retained; all model and policy changes auditable; resume does not repeat finished work; budgets terminate safely; no benchmark material reaches runtime inputs.

Quality gate: no confirmed loss of useful distinctions on the reviewed development cases; genuine conflicts can produce validated changes or useful unresolved alternatives; background facts cannot be retained solely because they are quoted. If the hybrid loses a supported requirement or adds an unsupported one, investigate before scaling rather than compensating with a larger output list.

Do not promise a 100% real-world recall threshold. Set the empirical target after the eligible reference inventory and evaluation protocol are fixed. More output, more agreement or more discussion messages alone do not establish improvement.

Deliverables: versioned scope/coverage contracts; source and decision ledger; revised discussion engine; per-operation model settings; stage UI and export updates; offline test report; matched discussion experiment; fresh small-profile trial report; documented limitations and a decision on whether Qwen earns a place in the default workflow.

Recommended first implementation slice: scope/coverage preservation and the mediated state machine, with the model split implemented alongside it but evaluated as a separate condition. Keep GPT-OSS as the control. Trial Qwen as mediator before changing extraction or assigning different models to individual stakeholders.
