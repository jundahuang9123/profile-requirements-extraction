# Model choice per workflow step

New agent runs and derived trials accept `step_models`. Leave it empty to use the
configured provider model everywhere. The service resolves every step default,
reads that provider's `/models` catalogue, rejects unavailable and embedding
models, and saves the resolved mapping in both `run.step_models` and
`run.request.step_models` before creating the run. Exact provider IDs are used,
including IDs containing spaces. Catalogue failure prevents creation; there is
no model fallback. Native Anthropic model catalogues are paginated.

```json
{
  "step_models": {
    "extraction": "inferenz-qwen3-8-27b",
    "writer": "inferenz-qwen3-8-27b",
    "rewrite_critic": "inferenz-gpt-oss-120b"
  }
}
```

| Setting | Work performed |
| --- | --- |
| `role_selection` | Stakeholder discovery, citation correction, registry merging and final panel selection |
| `extraction` | Independent source-span extraction by every selected role |
| `proposal_support` | Check whether excerpts support each extracted proposal |
| `grouping` | Group proposals describing the same underlying need; group kept needs into families (D5) |
| `writer` | Write neutral, term-free needs, including bounded rewrite recovery |
| `rewrite_critic` | Independently check that a rewrite preserves its source meaning |
| `membership` | Verify whether other grouped proposals express that need |
| `classification` | Compare needs with the frozen base-needs catalogue |
| `dataset_categories` | Identify explicit dataset kinds with source citations |
| `selection` | Propose strict equivalence for the compact cover |
| `profile_scope` | Judge needs against the profile scope (D5): dataset level, discovery contribution, representativeness |
| `use_case_linker` | Link needs to declared use cases |
| `link_critic` | Check what those links contribute to their use cases |
| `assessment` | Assess final retained needs against their authentic excerpts |
| `discussion` | All stakeholder and critic turns in a discussion case |

These are model choices within one configured provider. They are not separate
provider accounts or keys. Source parsing, source verification, ranking and human
decisions do not invoke a model. Writer and rewrite critic have independent
settings; one never changes the other. A global model change after creation does
not change the saved IDs. Credentials are resolved by the existing provider
configuration and never stored in the mapping or exports.

## UI and derived trials

On the Stakeholder roles setup page, expand **Advanced · model per step**. It is
collapsed initially. **Load provider models** performs only a catalogue lookup;
choose overrides and leave other steps on **Configured model**. Creation checks
the catalogue again so an old browser list cannot authorize an unavailable ID.
Saved runs show their frozen choices in **Saved models per step**.

The reprocessing form on step 4 has the same advanced control. The derive API
accepts `step_models` for `start_from: "normalization"` (reuse extraction),
`start_from: "elicitation"` (reuse the sealed panel and extract afresh), or
`start_from: "role_selection"` (reuse compatible completed discovery, rebuild the
registry/panel, then extract afresh). The completed automatic panel page offers
that last option, including a step-by-step pause before extraction.
Omitted settings resolve to the provider's current configured model, rather than
inheriting earlier experimental overrides. The source run is unchanged.

A trial from saved extraction retains the source's extraction reports and model
audit. Its new extraction setting is not a claim that the old extraction used
that model: no extraction calls occur in such a trial. Choose a step-3b trial to
compare extraction models. A trial from a saved panel similarly retains that
panel's original audit.

## Checkpoints and audit

Need row recovery keys include the bound client's provider/model configuration,
input, contract and policy. Grouping and assessment keys also include the actual
selected client, rather than the router's default. Repeating identical work with
the same model reuses its checkpoint; another model gets another key. Candidate
assessment reuse checks the assessor model. Discussion reuse keys include the
discussion model. Extraction context hashes and role-selection batch hashes
include their model configuration; partial extraction or selection refuses a
changed generation configuration instead of mixing answers. Generation identity
contains only provider, base URL, model and reasoning effort: changing concurrency,
timeout, retry count or backoff does not change keys or block Resume. Full provider
descriptions are still audited. Copied discovery calls in a panel trial do not bind
its new registry/panel generations to the original model.

Each generation audit records `step`, `model`, `provider.model`, output contract,
input hashes, response-token cap, timing, status and available token usage.
Existing call logs and original-source integrity checks remain in force. Legacy
runs without `step_models` keep their original configured-client behaviour; use a
separate trial for a model comparison. Earlier need-row/grouping checkpoints
without a model-bound key remain readable but are not treated as a match for the
new keys. Completed saved stages are not invalidated or rewritten by this PR.

## Reasoning settings and Qwen JSON

`RRS_LLM_REASONING_EFFORT` is sent only for recognised compatible models with
documented support. GPT-OSS accepts `low`, `medium`, `high`; Qwen 3.8 accepts
`low`, `medium`, `xhigh`. An unsupported level on those models is rejected before
run creation. For models without a registered reasoning capability, including
the KI:connect Mistral ID and older Qwen IDs, the setting is omitted; the audit
records the effective value as null. This does not turn off a model's default
thinking. No unverified KI:connect template parameters are added.

The parser uses the answer's `message.content`. Separate `reasoning_content` or
`reasoning` fields are never parsed or saved. If Qwen puts a leading thinking
segment into content, the segment is removed before JSON validation; the template
variant containing only a closing `</think>` is handled too. Literal markers
inside JSON string values are preserved. An unclosed segment, missing answer or
`finish_reason=length` is rejected; even apparently complete JSON from a truncated
response is not accepted. Only presence flags, hashes and numeric usage enter the
audit, never the thinking text.

The [Qwen 3.8 model card](https://huggingface.co/Qwen/Qwen3.8-27B) documents its
reasoning levels and separate answer/reasoning channels.
[vLLM's reasoning documentation](https://docs.vllm.ai/en/v0.21.0/features/reasoning_outputs/)
states that without a separate thinking budget, reasoning is governed by the
normal `max_tokens` limit. Accordingly, this implementation budgets Qwen thinking
and its JSON answer together. **KI:connect's exact deployment/accounting has not
been measured by this change:** its public API documentation does not establish
that detail, and no live inference was authorized for this PR. The audit calls
this `output_budget_assumption`. If the provider returns numeric
`completion_tokens_details.reasoning_tokens`, those are recorded; absence means
unknown, not zero. Caps are per generation, not per run or day. Extraction keeps
the existing 8,000-token initial cap and 12,000-token bounded recovery cap.

KI:connect's [API documentation](https://help.itc.rwth-aachen.de/en/service/1808737e10424937b76e564ed15d8028/article/4f07ebbbc8c4477a8db9baa441494941/)
explains retrieving the provider's current model IDs. A model appearing in the
catalogue establishes availability, not quality or every optional capability.

## One-role Qwen extraction smoke test (manual; not run for this PR)

Do this only after the current run has finished and this PR has been reviewed,
merged and loaded into your local service. Keep the same KI:connect provider and
configured GPT-OSS default, with reasoning effort `low`.

1. Create a new custom-document workflow. Use a small text source, marked
   **stakeholder need**, such as:

   > Users need to find mobility datasets covering their geographic area.
   > Publishers need to state the update frequency of each mobility dataset.

2. Freeze those sources. Leave the base profile empty and use-case scoping off
   for this small extraction test. Do not use reference requirement lists.
3. Select **Use a fixed panel**, keep only **consumer discovery**, choose
   **Step by step**, and choose discussion **Only when a reviewer asks**.
4. Expand **Advanced · model per step**, load the KI:connect model list, and set
   **Independent extraction** to `inferenz-qwen3-8-27b`. Leave the other eleven
   choices on the configured model. Allow live calls and start the new workflow.
5. The fixed-panel stage saves without selector inference. Click **Continue**
   once to execute step 3b. Stop at the next saved pause; do not continue into
   downstream processing for this extraction-only smoke test.
6. Check that the single role is completed, processed units equal total units,
   and its excerpts resolve to the original text. Download the full saved-run
   export and inspect `run.model_calls`: extraction calls must record
   `step: "extraction"`, `model: "inferenz-qwen3-8-27b"`, valid structured output,
   finish reason, token usage and elapsed time. Note any bounded recovery and
   unknown reasoning-token counts. Do not interpret a valid response as measured
   requirement accuracy.

To compare with GPT-OSS, create another separate trial from this run's **saved
panel** using `start_from: "elicitation"`, set extraction to
`inferenz-gpt-oss-120b`, and keep the same source, role and limits. A downstream
trial from saved extraction would not test a different extraction model.

For an optional one-role *whole-workflow* smoke, continue through the remaining
steps after reviewing step 3b, or start a distinct automatic trial. Those stages
use their separately saved choices. This is separate authorization from the
extraction-only check above and is not a full Mobility benchmark.

## Offline validation

The tests exercise all fifteen routes through actual selection and needs-processing
call sites, independent writer/critic choices, creation validation, derived-trial
isolation, model-specific row/grouping/assessment/discussion checkpoints, supported
reasoning payloads and Qwen thinking/token-limit handling. HTTP replies and model
answers are scripted; the test suite forbids external network calls. Frontend,
schema and catalogue checks accompany the tests. No current service, key, saved
run or reference corpus is modified by the feature's tests.

## Procedural base review

Two additional model slots are `base_review` (pinned-catalogue comparison of up
to four needs) and `base_review_check` (independent verdict check). Both inherit
the configured model when unset, **not** the discussion default. They appear in
the collapsed advanced control and are frozen/validated like other slots. They
run only when `base_review: "expert_v1"` is enabled on an F/A run with a base.

A `start_from: "base_review"` trial preserves the source's resolved upstream
models and permits overrides only for these two slots, `stakeholder_review`,
`mediation`, `mediation_check` and `assessment`, including their options. It
restores the machine snapshot rather than partially discussed requirements.
See [the base-review design](FA-COVERAGE-DISCUSSION.md#optional-procedural-base-reviewer)
for the independent check, checkpoint identities and stepwise trial.
