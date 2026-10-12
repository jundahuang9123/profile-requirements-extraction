# Operating the persistent RQ1 workflow

This describes the implemented `rq1-nine-stage-v2` workflow. The
[implementation guide](RQ1_IMPLEMENTATION_GUIDE.md) remains the design record,
including prospective research extensions; this document states current behavior.

## First offline run

1. Launch with `RRS_LLM_PROVIDER=disabled` using [the README](../README.md).
2. Choose the source role and authority, paste text or upload files, and save them.
   Parsing diagnostics stay visible.
3. Select evidence sources and enter competency questions, one per line. Background
   material and sources labelled `evaluation_reference` are excluded from the evidence snapshot.
4. Choose rules or offline mock perspectives and start the saved workflow. Rules
   generate normative-looking text proposals only. Empty output is distinct from failure.
5. Inspect a candidate and its original evidence. Source `pass` establishes citation
   fidelity; support `uncertain` means semantic assessment is pending.
6. Record a support/quality assessment and rationale. Address type, resource, scope,
   obligation or atomicity issues through edit/split. Replacement revisions start
   unaccepted and are independently verified and assessed again.
7. Reject incompatible alternatives before accepting a conflict member with an
   explicit resolution rationale. Add missed requirements or propose merges as needed;
   these human changes never count as machine extraction.
8. Inspect targeted discussion threads. In offline runs, queued cases are human
   threads; contribute and explicitly close them before publishing affected records.
9. Accept eligible revisions, publish their baseline and download it. Reloading
   restores saved server state without another extraction.

Examples and model structures can motivate an inference but do not establish
universal obligations. A genuine irrelevant quote can pass source verification and
fail semantic support. Human assessment makes that distinction in offline runs.

## Evidence addressing and fidelity

| Input | Original-source verification | Limits |
| --- | --- | --- |
| Text / Markdown | Representation hash and Unicode code-point span; all nonempty spans retained; table rows retain headers/heading context | Offsets pinned to one version; no keyword filter in decomposition |
| PDF | Original bytes, pinned pdfplumber extraction, page and representation/span hashes | Text only; image-only PDFs fail visibly; no OCR/layout fidelity claim |
| AAS JSON | RFC 6901 escaped pointers, exact typed-value hashes, element/parent/semantic identity | Array positions version-local; examples do not impose obligations |
| AAS XML | Expanded namespace names, child-index path, text/attribute hash; defusedxml rejects DTD/entities | Version-local paths; no schema-validation claim |
| AASX | Parent package hash, entry path, child source version and entry bytes; JSON/XML parsed | No file extraction; duplicate entries, excessive size/count and malformed packages fail |
| RDF | RDFlib reparse and PyLD URDNA2015 canonical N-Quads; graph, language, datatype and blank-node identity retained | URDNA2015, not RDFC-1.0; remote JSON-LD contexts/imports and XML entities rejected; no dereferencing |
| IFC | IfcOpenShell STEP entity/GlobalId/occurrence-or-type property relationship/property/typed value/explicit unit chain | Duplicate GlobalIds fail; STEP IDs version-local; geometry and complete derived-unit inference outside adapter |

Source/evidence IDs incorporate raw bytes, parser version/dependencies and selectors.
Repeating decomposition with the same logical source ID and identical metadata reproduces evidence IDs. Changed
bytes, authority, parser or dependencies create new source versions. Callers supply
the same `source_id` to group logical source versions; citations are never retargeted.

Resolution regenerates evidence from stored original bytes and compares selector,
content hash and structural context. Quotes must be exact spans. Repeated quotes need
`quote_start` within the unit, in Unicode code points. If an elicitation model reports
an invalid offset but its exact quote occurs once in that cited unit, normalization
replaces the offset with that unique unit-local position and records the correction on
the role report. No match or multiple matches remain unresolved and fail verification.
Known obligation claims need a separate supportive `component: obligation` citation.
Every material citation must resolve; one good citation cannot hide a fabricated
premise.

## Models, transitions and acceptance

Runtime contracts are in [workflow/models.py](../requirement-reuse-service/requirement_reuse_service/workflow/models.py).
`scripts/export_workflow_schema.py` generates the v2 JSON Schema; `--check` detects
drift. Contracts include discriminated selectors, snapshots, observations, requirement
revisions, qualifications, conflicts, cases, commands and saved runs. TypeScript view
contracts are in `workflowApi.ts`. V1 Pydantic/LinkML/export semantics are retained.
V2 never silently defaults intent to a Dataset scope or discovery need.

Authenticity, semantic support, quality findings, lifecycle and conflict status are
separate fields. Model output does not count as validation. Acceptance requires:

- Unique current revisions and the expected saved-run version.
- Fresh original-source verification of the exact content hash.
- Hash-bound `explicit` or `inferred` semantic assessment.
- No outstanding blocking/review findings and resolved type/resource/scope.
- Explicit disposition of incompatible alternatives, which cannot both be accepted.
- A human decision with trusted local reviewer identity and rationale.

Edit/split/merge retain parents, observations, assessments and decisions, but create
new hashes and require fresh review. Human additions have separate provenance and
an `add` event. Their evidence must be in the frozen corpus; new sources need a new run.

States are `created → selecting_roles → eliciting → normalizing → verifying → consolidating → routing
→ awaiting_human → completed`, with `failed` and `cancelled` outcomes. Stage indicators
are independent. Partial baselines can be published while other records await review.
Publication completes the run when all active records are accepted/rejected/out of
scope. Deferred records stay unresolved. Editing a completed run reopens adjudication
without changing an already published baseline.

## Agent responsibilities and selective discussion

Stage 3a can automatically select stakeholder perspectives from the frozen sources
and CQs; stage 3b uses the resulting immutable panel. The UI defaults to automatic
selection for agent/demo runs. See [role selection and overrides](ROLE_SELECTION.md)
for the documented/inferred/proposed distinction, bounded scan, provenance and limits.
The manual mode preserves the 12 configured extraction perspectives from
`config/agent_roles.yaml` for existing callers and controlled comparisons. Each
receives frozen corpus/task/role context and bounded batches, without peer candidates.
Up to four run concurrently. Raw structured outputs, prompt/context hashes, partial
failures and completed roles are retained. Retry skips completed perspectives.
Only declared task identifiers are retained on observations; unknown identifiers
from model output are dropped and listed on the role report. The original structured
output remains in the call audit.
Held-out expert evaluation inputs are excluded. V1 role retrieval stores are not
yet connected to the v2 context builder.

Normalization preserves raw wording and emits typed revisions. Compound-statement
and premature-solution heuristics flag review issues. Atomic splitting is proposed
by live elicitation or performed by a human; valid JSON does not prove atomicity.
Qualification resolves original sources first, then assesses support and quality.
Live assessments use the existing structured provider client. Offline assessments
remain uncertain pending a human judgement.

Automatic consolidation requires identical normalized statement, type, intent,
scope and assumptions with valid provenance. It unions evidence/contributions and
requalifies the merged revision. Similarity alone does not merge candidates. A
token-set Jaccard threshold of 0.65 flags similar needs with different scope,
polarity or modality as potential conflicts; humans must identify missed conflicts.
This is a conservative routing heuristic, not exhaustive contradiction detection.

Failed grounding routes to evidence repair. Grounded conflicts route to cases.
Live multi-agent runs also deliberate uncertain/unsupported/contradicted support
or blocking/review findings. Clean candidates go to human review. Humans can
request follow-up cases, bounded to two cases involving a given revision.

The run setting `discussion` decides whether these cases open automatically.
`automatic`, the API default, opens them as described above. `on_request` opens
none: candidates that would be discussed go to human review with the same routing
reasons, the discussion step is marked `skipped`, and a reviewer can still request
a targeted case for a candidate. The review heuristics flag most candidates (an
unknown obligation, type or scope, a compound statement, a vocabulary term), so
automatic discussion usually adds several calls per candidate. Discussion runs
after the machine output is frozen: the setting changes neither extraction,
verification and assessment nor consolidation, only the number of model calls and
what the reviewer finds already discussed. The run request saves the setting, and
the run metrics and the evaluation export report it.

Cases freeze exact revisions and evidence. Up to four participants, including a
grounding/scope critic, challenge claims and retain proposals and dissent. Defaults
are three rounds, 12 generation attempts, 4,000 output tokens initially with one
8,000-token recovery attempt, 48,000 reserved output tokens and 300 seconds for
scheduling new calls. An in-flight provider request uses
its configured timeout and may finish after that scheduling window. Actual token
usage is recorded when supplied by the provider; missing counts and unpriced cost
remain unknown and are never reported as zero.
New cases record discussion policy `rq1-selective-v5`. Role-selection quotations
are omitted from discussion perspective descriptions: only evidence frozen for the
case is admissible. Allowed evidence IDs appear explicitly in the prompt and in
the response schema; invalid IDs are rejected, never silently removed or repaired.
Agents are instructed to finish when they have no new evidence-based contribution,
including unresolved dissent. An exact whitespace-normalized repeat of a role's
body, proposal and citation set finishes that role early; this is a repetition
check, not a semantic convergence test. The repeated message remains in the audit.
Cases stop on finished participants, no new contributions, budgets, provider failure or cancellation.
Finished/repeated discussions remain `unresolved` for human review, not resolved.
Agreement cannot accept or mutate requirements; proposed changes require human
revision, requalification and a later acceptance decision.

Sebastian-inspired mechanisms are selective routing, bounded turns, frozen shared
context and observable messages. RQ1-specific logic is source addressing, support
assessment, metadata-neutral normalization, disagreement and human acceptance.
Upstream mutable mapping state and mapping commands are not invoked.

## API, persistence and retry

Before running a new benchmark, run `scripts/preflight_benchmarks.py --output
<directory-outside-repository>` using the project's Python environment. It checks
every strict raw allowlist without reading reference requirements or calling a
model: parsing, original-source resolution, empty/missing artifacts, complete
snapshot eligibility, role-selection limits and estimated extraction payload sizes.
Reports and its isolated database remain outside the repository. Readiness does not
prove historical corpus completeness, table interpretation or semantic quality.

Parser v2.4 handles HTML/HTM directly as deterministic body-text passages, retaining
original bytes and hashes. Citation selectors address a regenerated representation,
not raw HTML character offsets. Entities and whitespace are normalized; scripts,
styles, document head and templates are excluded. Text in the body remains in order;
linked files are not fetched. Tables retain textual row/cell boundaries but complex
layout, CSS visibility and image content require assessment. Earlier parser versions
remain resolvable for saved runs. Legacy HTML ingested as raw markup must be
re-ingested before entering a new snapshot. Empty extraction fails, and PDF pages
containing images with no extracted text block a complete snapshot pending OCR or
source assessment. A blank page without images produces a diagnostic instead.

New endpoints use `/api/rq1/v2`; `/docs` exposes complete request contracts.

| Endpoint | Purpose |
| --- | --- |
| `POST /sources`, `GET /sources`, `GET /sources/{version}` | Acquire and inspect immutable sources/diagnostics |
| `POST /snapshots` | Freeze sources, evidence and declared tasks |
| `GET /evidence/{id}` | Inspect source resolution and selectors |
| `POST /runs` | Return 202 and queue execution; `discussion` is `automatic` or `on_request` |
| `GET /runs`, `GET /runs/{id}` | Restore run state/progress |
| `POST /runs/{id}/cancel`, `/resume` | Cancel or resume interrupted unreviewed work |
| `GET /runs/{id}/events`, `/export`, `/evaluation` | Audit events, saved review and metrics |
| `POST /runs/{id}/assessments`, `/decisions`, `/requirements` | Human assessment, decisions/revisions and additions |
| `POST /runs/{id}/deliberations` | Open a targeted case |
| `POST /runs/{id}/deliberations/{case}/messages`, `/close` | Contribute or explicitly close for adjudication |
| `POST /runs/{id}/baselines` | Freeze accepted revisions and dependencies |
| `GET /runs/{id}/baselines/{baseline}` | Download an existing immutable baseline |

Review/baseline commands carry expected versions and idempotency keys. Changed
payload under the same key or stale versions yield 409; invalid transitions/citations
yield 422; missing objects yield 404. Source/snapshot IDs are content-based.
Decisions, events and aggregate updates commit together in SQLite. Immutable source
bytes/evidence and all candidate revisions remain available.

Workers have a persisted 15-minute lease refreshed at stages and provider call starts.
Restart does not silently restart work; resume after the lease expires. Resume skips
completed roles and only applies to interrupted/partial unreviewed runs. Continue
adjudicated runs through review or create another trial. The background worker is
local, not a distributed queue; large/multi-process deployments need a job service.

Reviewer identity is `RQ1_LOCAL_REVIEWER` (default `local-reviewer`), not a
model-supplied actor. The server binds to loopback. Shared deployments need
authenticated sessions, authorization and operational backups. Exports contain no
credentials. Back up stopped SQLite files or use SQLite's online backup API.

## Evaluation and RQ2 handoff

Machine output freezes after consolidation, before discussion or human decisions.
Metrics separate frozen machine output, current review and accepted results, with
role failures/proposals, support/quality distributions, actions/additions, discussion
outcomes and observable call latency/parameters. Structured outputs and prompt/context
hashes are saved. Actual provider tokens/cost remain unavailable. Summed call latency
is not wall-clock duration when roles run concurrently.

`scripts/evaluate_workflow.py` reads saved review/baseline JSON offline. It does not
rerun extraction or infer precision/recall from token overlap. V1 retains independent
expert packages, ratings and aggregation. No lossless automatic v2→v1 conversion or
integrated v2 multi-reviewer summative package is supplied. Formal evaluation still
needs a predeclared reference/equivalence rubric, independent labels, repeated model
trials and frozen study configuration. Task links alone do not establish coverage.
No full-corpus recall, model quality or empirical deliberation benefit is claimed.

Publication rechecks accepted revisions against original bytes. Unresolved conflicts
or pending cases affecting them block publication. Baselines contain exact accepted
hashes, source bytes, evidence, assessments, decisions, frozen machine output,
derivations and an excluded/unresolved appendix. Canonical SHA-256 excludes only its
own derived hash/ID. Later review leaves saved baselines unchanged. Audit exports
are not database-import files; no import/supersession endpoint is implemented.
RQ2 consumes validated needs/optional hints and makes vocabulary/profile decisions.

## Validation boundaries

Offline tests deny outbound socket connections. Fixtures cover exact/tampered/
fabricated/repeated citations, irrelevant evidence, JSON/XML/AASX addressing,
RDF graphs/blank nodes/literals/context rejection, IFC relationship/value/unit
chains, independent role failures, bounded dissent, conflicts, stale/idempotent
commands, restart, human revisions/additions, frozen metrics and baseline provenance.
The frontend TypeScript/production build is checked. Browser checks use disposable
offline fixtures. Live provider runs, Docker and formal research evaluation require
separate validation.

## Catalogue record resource types

`CatalogRecord` is a supported resource type for requirements about catalogue
entries. It remains distinct from `Dataset`: describing an entry and describing
the dataset represented by that entry can involve different needs. The shared
backend contracts, extraction validation, exported workflow schema and UI resource
selectors preserve this distinction. This is a structural validation fix, not an
assertion that every model proposal mentioning a catalogue entry is correct.

Extraction policy v2.7 includes this contract change and bounded output-cutoff recovery. Start a new extraction run
to use it; historical runs and their failures remain unchanged, and resuming a
run created under an older extraction policy is rejected.

## Bounded extraction output recovery

The v2.7 extractor targets at most four evidence units and 16,000 input characters
per batch. A single larger unit remains intact under the existing 45,000-character
hard limit; no source text is silently discarded. These are character budgets,
not guarantees about provider tokenization or output size.

Each initial response reserves 8,000 tokens. When an OpenAI-compatible provider
explicitly reports `finish_reason=length`, the partial response remains rejected.
A multi-unit batch is split in half and retried as smaller independent batches.
For a single unit there is one retry at 12,000 tokens. From policy v2.10 a unit that is
cut off again is marked failed and the role continues with the remaining units; earlier
policies stopped the role there. Authentication and other transport errors do not trigger
this recovery and still stop the role. Completed smaller-batch observations are retained if a later batch fails.
Every request is recorded, and citation selections identify cutoff attempts,
recovery choices, input evidence IDs and response caps. Smaller batches/recovery
can increase calls, latency and cost; improved live completion is not yet measured.

New v5 discussion cases start with 4,000 response tokens per turn. A response
explicitly cut off at the output limit, or rejected by the JSON/schema contract,
can receive one new generation on the same frozen context with an 8,000-token
cap. The retry includes a concise recovery instruction; it cannot broaden the
allowed citations or approve a requirement. Internal schema repair is disabled
for these calls so every generation is visible in case accounting.
Every attempt consumes one of twelve calls and reserves its full response cap
against the unchanged 48,000-token case budget. The three-round limit and
300-second window for scheduling new calls also apply to retries. Reserved
tokens are not actual consumption. Exhausted budgets and repeated unusable
output remain visible unresolved/failed outcomes, never agreement. Historical
v4 cases retain their original no-retry policy; create a new case for new defaults.

## Bounded semantic assessment recovery

Assessment policy `rq1-support-quality-v2.2` starts at 4,000 response tokens and
allows one 8,000-token retry only after explicit output truncation or typed
JSON/schema validation failure. This accounts for reasoning tokens consuming
the response allowance even when little or no final JSON is returned. It does
not imply an input context-window error. Both attempts and measured usage are
audited; partial/invalid output is never accepted. Authentication, transport and
exhausted rate-limit failures still stop the job without this generation retry.

Repeated references to one evidence unit send that unit once to the assessor;
all component links and the full source passage remain available. If both
generations fail, the draft retains its source check and becomes `uncertain`
with a blocking `assessment_unavailable` finding. It goes directly to human
review rather than treating a model-output failure as a substantive disagreement.
The finding prevents acceptance until a reviewer supplies a valid semantic
assessment. Other records continue processing. This preserves drafts, not a
successful assessment or a positive benchmark outcome.

Resume reuses completed qualifications for the exact content hash, including
those from v2.1; it does not relabel or re-request them under v2.2. Remaining
assessments use v2.2, recorded in each assessor field. Such a resumed run has
mixed assessment conditions and must be reported as a recovery trial. A fresh
run is necessary for a comparison using one assessment policy throughout.

## Step pages, human progression and checkpoints

The UI now opens only the persistent workflow; the v1 study interface is no longer
an option. Historical backend endpoints remain available for compatibility.
Each step has its own hash route, previous/next navigation and saved-step JSON
download. Reloading restores the selected run and route. Browser setup choices
are stored locally; uploaded sources and completed results are saved in SQLite.
Review edits are saved when submitted, not merely when visiting a page.

Human use defaults to **Step by step** in the UI. A run with
`execution_mode=stepwise` saves and pauses after stakeholder selection, extraction,
normalization, verification and consolidation. Continue advances one processing
stage, then pauses again. Discussion runs within its existing bounds and hands
control to human review. Changing pages does not trigger processing. **Automatic**
mode is intended for tests and retains continuous execution. The API defaults to
automatic for compatibility with existing clients and historical runs.

Completed stage payloads are saved separately from later review state. In new
runs, normalization/verification/consolidation pages and downloads use those
checkpoints. Human decisions cannot rewrite the earlier stage results. Older runs
without stage checkpoints expose their current saved state and label exports
accordingly; historical stage snapshots cannot be reconstructed reliably.

Extraction policy v2.9 checkpoints every successfully materialized batch and its
observations, response and source selection audit. After interruption, only
unfinished evidence units are requested again. A completed response without any
observations still counts as processed input. Parallel roles checkpoint separately.
A call interrupted before its checkpoint may need to be repeated; no exact-once
remote-inference guarantee is made. Earlier policy versions require a new run.
For OpenAI-compatible providers, role selection and extraction now allow one
schema correction generation per request. Unrecoverable extraction batches split
into smaller source batches; a failed singleton stays visible while other sources
are processed. A role with unresolved units stays incomplete. Source verification
is unchanged. See [EXTRACTION_CITATIONS.md](EXTRACTION_CITATIONS.md) for recovery,
provenance and finite request bounds.

Extraction policy v2.10 applies the same rule to the two remaining per-unit failures.
An answer that cites an unknown excerpt ID or repeats an identical link, and a single
unit that is cut off again after its larger retry, no longer stop the role: the batch
is split, a single unit gets one further request, and a unit that still fails is
marked failed while later units are processed. Each role report counts processed
against total evidence units, and the extraction page shows that count. Only
transport, authentication and unexpected errors stop a role before its last unit.

Extraction policy v2.11 and role-selection policy v6 change what an excerpt is.
Consecutive lines of one evidence unit are offered as one block of at most 400
characters instead of one excerpt per physical line. Quotations and offsets remain
exact slices of the unit, and source verification is unchanged. A requirement needs
fewer links, requests carry less wrapper text, and the same corpus needs fewer
extraction batches. Excerpt IDs from earlier policies do not match the new
catalogue, so both policies require a new run.

Semantic assessment also checkpoints each completed exact-revision result.
Resuming rechecks original-source resolution and reuses completed matching
assessments. Stale revision hashes are reassessed. The failed stage is marked
explicitly. Resuming failed extraction invalidates downstream stages/checkpoints
so new observations are normalized and assessed rather than mixed with old results.
In-flight calls cannot be recovered as completed, and an active worker lease can
prevent resumption until release/expiry. Some operations inside consolidation or
a discussion case may need an explicit repeat/follow-up after interruption.

Resume repeats a discussion only when its input is new, changed or unfinished.
Each routed case is compared with the cases of the earlier attempt by its
discussion input: triggers, participants, policy, and for every frozen candidate
its revision, content hash, contributing roles, assessment and source-check
outcome, ignoring check timestamps. A finished case (`unresolved` or
`budget_exhausted`) with the same input is kept with its messages and outcome; a
case that failed, was cancelled or was interrupted is run again. An earlier case
whose candidate changed is replaced and stays in the attempt history, which now
records the discussions of each attempt. Cases a reviewer requested are carried
over unchanged and never repeated by resume. A run awaiting review can therefore
be resumed when a role failed or a routed discussion did not finish; the UI then
offers **Retry unfinished work**. The run metrics count reused discussions as
`deliberation_reused`.

Two details keep unchanged candidates identical across attempts. Extraction
restores panel order after a resume, so consolidation merges the same observations
in the same order and the merged revision keeps its identifier. Consolidation reuses
the completed assessment of an identical merged revision from the earlier attempt,
as normalization already does for single candidates.
