# Exact excerpts and bounded provider requests

The persistent RQ1 workflow uses `rq1-independent-elicitation-v2.9` for new agent
runs. Agents select source excerpt IDs for each requirement premise. The server
supplies the original quotation and its character offset; agents no longer generate
quotation text. The saved public requirement format remains `EvidenceLink` with
`evidence_id`, `quote`, `quote_start`, `relation` and `component`.

## From source to requirement

Each evidence unit is exposed as its metadata and an ordered catalogue of exact
source excerpts. Excerpts retain the extracted text, spaces and hyphenation. Each
nonblank physical line is an excerpt, split at 400 characters when necessary.
Adjacent excerpts provide context; agents can cite several when a premise crosses
lines. Up to 12 premise links can be returned per observation. Batches include the
catalogue and role/task context with a 16,000-character target and at most four
evidence units. A single larger unit may use the 45,000-character hard limit. An oversized unit
fails explicitly rather than losing input. Character limits are not model-specific
token limits; the provider also receives a schema and system prompt.

The provider-only `SpanElicitationResult` contains `source_span_id` selections,
with a relation (`supports`, `contradicts`, `contextualizes`) and component
(`statement`, `obligation`, `scope`, `condition`, `value_kind`). Selecting the same
excerpt for different components is allowed; duplicate identical links and unknown
IDs fail that extraction role visibly. The raw provider output, batch catalogue,
catalogue hash and transformation outcome remain in the contribution audit.

Authentic excerpts do not establish entailment. The ordinary original-source
verification, separate obligation-premise requirement and semantic assessment
remain in effect. Unsupported hypotheses may retain empty links and remain blocked.
A claimed mandatory/recommended/optional obligation without supporting obligation
evidence still fails verification. An agent must not label descriptive implementation
choices as universal metadata obligations merely because it can cite them.

Use a **fresh run** for this policy. Completed historical runs remain readable and
exportable. Resuming an older extraction policy is rejected before provider setup,
so partial results cannot mix quotation-generation and excerpt-selection methods.
Older failed pilot results are not rewritten to pass.

## Recovery from invalid structured output

Role selection and extraction opt into one schema correction generation per
OpenAI-compatible request. A complete response that fails JSON parsing or schema
validation is sent back to the same configured model with the original source
context, schema and validation paths/types. The model must correct its structure
while preserving supported needs. The application does not slice excess citations,
guess enum aliases or accept the valid fraction of an invalid object. The corrected
response is validated again; ordinary citation/source and obligation checks still apply.
Native Anthropic structured parsing does not use this additional correction path.
Qualification and discussion requests retain their existing generation budgets.

If extraction still fails its schema, split a multi-unit batch in half and process
both halves. A single evidence unit that still fails remains explicitly failed,
while the role attempts the remaining units. A role with any such unresolved unit
is incomplete, even when it retains valid proposals from other units. Resume skips
successfully materialized units and retries only unfinished units. Split attempts,
failed units, accepted outputs and exact source catalogues remain in the audit.
Each generation retains the existing response cap; schema failures do not increase
it. With four units per initial batch, schema-only recovery has at most seven batch
requests and fourteen generations for that batch, excluding transport retries.
The separate token-cutoff recovery has its own existing bounds.

Extraction prompts spell out the 12-link limit and all value-kind enum values.
Compound needs should be split into atomic observations instead of inventing a
`mixed` value type. A valid schema alone cannot establish source support or quality.

Provider audits save each generation's validation outcome, issue paths/types,
response fingerprint and measured usage, without retaining invalid response text,
prompts, headers or credentials in transport metadata. Logical calls and HTTP
attempts remain distinguishable. Usage totals include both initial and corrective
generations only when measured for every generation; missing counts remain unknown.
Per-generation counts remain available when aggregate usage is incomplete.

## KI:connect and other OpenAI-compatible endpoints

`RRS_LLM_MAX_CONCURRENCY=1` is the default. Request slots are shared by all clients
with the same base URL in one server process, including concurrently running roles
and runs. Perspectives remain independent; the network requests are queued.
Changing the limit requires restarting the process. Multiple server processes or
machines have separate limits; configure a shared gateway for a global deployment.
The optional limit is 1–4.

Only HTTP `429` responses receive rate-limit retries. Defaults are two additional
attempts, fallback waits of 2 then 4 seconds, and a total retry-wait budget of 30
seconds. A valid `Retry-After` delay (seconds or HTTP date) takes precedence. If it
exceeds the remaining wait budget, the call fails explicitly rather than retrying
too early or sleeping indefinitely. The endpoint request slot stays occupied during
cooldown. Authentication errors and other HTTP failures are not retried by this
policy. Schema correction above is separate from transport retries. The existing one-time response-format fallback remains
bounded and is recorded separately.

Set `RRS_LLM_RATE_LIMIT_RETRIES` (0–3), `RRS_LLM_RETRY_BACKOFF` (positive, at most
60 seconds) and `RRS_LLM_RETRY_WAIT_BUDGET` (0–60 seconds) to tune these bounds.
Retries cannot guarantee success under exhausted quota or persistent throttling.
The existing `RRS_LLM_TIMEOUT` applies to each HTTP attempt; retry-wait budget
bounds waiting, not total provider duration or queue time.

Run model-call audits record HTTP status/attempts, retry waits and queue time.
They contain no API key or HTTP headers. Evaluation exports distinguish logical
model calls from HTTP attempts. Historical calls without transport metadata have
unknown HTTP attempt counts. Reported token usage is recorded; monetary cost remains unknown.

## Validation

Offline tests cover exact multiline quotations and offsets, separate obligation
premises, unknown IDs, unsupported hypotheses, schema rejection of generated quotes,
policy compatibility, shared endpoint concurrency, finite 429 retries, `Retry-After`,
long cooldown rejection, authentication failure, and response-format fallback.
Recovery tests replay excess stakeholder names, 13 citations, invalid `mixed`
value types and malformed JSON through the real client with fake HTTP responses.
They cover exhausted correction, unknown citations after correction, complete
measured usage versus missing usage, continued source coverage after a singleton
failure and resume without repeating successful sources.
A live KI:connect pilot is a separate validation step after restarting the service;
offline success does not imply requirement quality or benchmark accuracy.
