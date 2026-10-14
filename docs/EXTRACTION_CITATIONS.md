# Exact excerpts and bounded provider requests

The persistent RQ1 workflow uses `rq1-independent-elicitation-v3.3` for new agent
runs. Agents select source excerpt IDs for each requirement premise. The server
supplies the original quotation and its character offset; agents no longer generate
quotation text. The saved public requirement format remains `EvidenceLink` with
`evidence_id`, `quote`, `quote_start`, `relation` and `component`.

## From source to requirement

Each evidence unit is exposed as its metadata and an ordered catalogue of exact
source excerpts. Excerpts retain the extracted text, spaces, line breaks and
hyphenation. From policy v2.11 an excerpt is a block of consecutive lines of one
unit: lines are joined, line breaks included, for as long as the block stays within
400 characters, and a blank line always ends a block. A single line longer than 400
characters is cut every 400 characters; its last piece can be joined by the lines
after it. Every excerpt is one contiguous slice of the unit, so its quotation and
character offset stay exact, and only line breaks and blank lines lie outside the
excerpts. Earlier policies offered every physical line as its own excerpt. That
spread one definition or sentence over many links and made the 12-link limit easy
to exceed: the two StatDCAT allowlist sources yield 2,902 line excerpts with a
median length of 34 characters, against 404 block excerpts with a median of 367.
A block can contain neighbouring lines that the cited premise does not need, so an
authentic excerpt says even less about relevance than a single line did.
Adjacent excerpts provide context; agents can cite several when a premise spans
them. Up to 12 premise links can be returned per observation. Batches include the
catalogue and role/task context with a 16,000-character target and at most four
evidence units. A single larger unit may use the 45,000-character hard limit. An oversized unit
fails explicitly rather than losing input. Character limits are not model-specific
token limits; the provider also receives a schema and system prompt.

The provider-only `SpanElicitationResult` contains `source_span_id` selections,
with a relation (`supports`, `contradicts`, `contextualizes`) and component
(`statement`, `obligation`, `scope`, `condition`, `value_kind`). Selecting the same
excerpt for different components is allowed; a duplicate identical link or an
unknown ID rejects the whole answer (see recovery below). The raw provider output,
batch catalogue, catalogue hash and transformation outcome remain in the contribution audit.
Each catalogue is stored once per run, in the run's `catalogues` map under the hash that
the role report records; roles that read the same batch share it. The run export and the
extraction step's download include the catalogues.

Extraction receives a selected stakeholder's label, stakeholders, basis, purpose,
focus questions and rationale. Discovery quotations, citations and candidate merge
history stay in the role-selection audit and are excluded from extraction prompts.
Only excerpts supplied in the extraction batch may support a proposal. Policy v3.3
applies to both needs and legacy candidate output; their output contracts remain
distinct. A partial extraction from an older policy needs a fresh run.

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
both halves. A single evidence unit that still fails is marked failed, and the role
goes on to the remaining units.

A schema-valid answer can still cite an excerpt ID that is not in the supplied
catalogue, or repeat an identical link. No observation from such an answer is
accepted, and the application neither drops nor deduplicates links. A multi-unit
batch is split in half. A single unit is requested once more with a short note
naming the two rules; if that answer is rejected too, the unit is marked failed and
the role goes on. Rejected raw answers stay in the contribution audit.

Output cutoffs follow the same pattern: a multi-unit batch is split, a single unit
gets one retry at 12,000 tokens, and a unit that is cut off again is marked failed
while the role goes on.

A role with any failed unit is incomplete, even when it retains valid proposals
from other units. Its report lists every failed unit with the kind of failure
(`schema_invalid`, `citation_invalid` or `output_cutoff`) and counts processed
against total evidence units. Resume skips successfully materialized units and
retries only unfinished units. Split attempts, failed units, accepted outputs and
exact source catalogues remain in the audit. Schema and citation failures do not
increase the response cap. For one initial batch of four units all recovery kinds
together are bounded by fifteen requests of at most two generations each,
excluding transport retries.

Transport, authentication and unexpected errors are handled differently: they
stop the role at once, because the next request would most likely fail the same
way. Saved batches are kept, and resume continues with the unfinished units.

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

Two kinds of HTTP failure are retried. Each has its own attempt limit; both draw
on one retry-wait budget per request.

- **Rate limit** (HTTP `429`): by default five additional attempts with fallback
  waits of 2, 4, 8, 16 and 32 seconds, which outlasts a one-minute rate window
  that sends no `Retry-After` header.
- **Transient failure** (a timed-out attempt, a refused or dropped connection, or
  HTTP `500`, `502`, `503`, `504`): by default two additional attempts with
  fallback waits of 2 then 4 seconds.

The retry-wait budget defaults to 120 seconds. A valid `Retry-After` delay (seconds
or HTTP date) takes precedence over the fallback wait for both kinds. If it exceeds
the remaining wait budget, the call fails explicitly rather than retrying too early
or sleeping indefinitely. The endpoint request slot stays occupied during cooldown.
Authentication errors and other `4xx` responses are never retried. Schema correction
above is separate from transport retries. The existing one-time response-format
fallback remains bounded and is recorded separately.

Set `RRS_LLM_RATE_LIMIT_RETRIES` (0–8), `RRS_LLM_TRANSIENT_RETRIES` (0–3),
`RRS_LLM_RETRY_BACKOFF` (positive, at most 60 seconds) and
`RRS_LLM_RETRY_WAIT_BUDGET` (0–600 seconds) to tune these bounds. A local `.env`
copied from an earlier `.env.example` pins the previous values (two rate-limit
retries, 30 seconds) and overrides the new defaults until it is edited.
Retries cannot guarantee success under exhausted quota, persistent throttling or an
endpoint that stays unavailable; the role or stage then fails visibly and can be resumed.

`RRS_LLM_TIMEOUT` applies to each HTTP attempt; the retry-wait budget bounds waiting,
not total provider duration or queue time. A response that needs longer than the
timeout to generate will time out again on every retry: for a slow endpoint or a
large response cap, raise `RRS_LLM_TIMEOUT` rather than the retry count. With the
defaults one generation stays below the 15-minute worker lease (three 240-second
attempts plus waits). A larger timeout, or a schema correction that follows retried
timeouts, can outlast the lease; do not resume such a run while its request is in flight.

`RRS_LLM_REASONING_EFFORT` is sent as `reasoning_effort` when set and omitted
otherwise, which leaves the provider's default. For a reasoning model the response
cap covers reasoning as well as the JSON answer, so a lower effort leaves more of the
cap for the answer. Whether an endpoint honours the parameter has to be checked in
the recorded reasoning-token counts. The value is part of every call's recorded
provider description, so runs with different settings remain distinguishable.

Run model-call audits record HTTP status/attempts, retry waits and queue time.
They contain no API key or HTTP headers. Evaluation exports distinguish logical
model calls from HTTP attempts. Historical calls without transport metadata have
unknown HTTP attempt counts. Reported token usage is recorded; monetary cost remains unknown.

## Validation

Offline tests cover exact multiline quotations and offsets, block excerpts that
join neighbouring lines up to the limit and stop at blank lines, separate obligation
premises, unknown IDs, unsupported hypotheses, schema rejection of generated quotes,
policy compatibility, shared endpoint concurrency, finite 429 retries, `Retry-After`,
long cooldown rejection, authentication failure, and response-format fallback.
Transport tests cover retried timeouts, dropped connections and `5xx` responses,
their exhaustion, the shared wait budget, disabled retries and unretried `4xx` errors.
Recovery tests replay excess stakeholder names, 13 citations, invalid `mixed`
value types and malformed JSON through the real client with fake HTTP responses.
They cover exhausted correction, unknown citations after correction, complete
measured usage versus missing usage, continued source coverage after a singleton
failure and resume without repeating successful sources. Extraction tests cover the
single citation retry, duplicate links, units skipped after a cutoff or a citation
failure while later units are still processed, and an unreachable provider stopping the role.
A live KI:connect pilot is a separate validation step after restarting the service;
offline success does not imply requirement quality or benchmark accuracy.
