# Operating the persistent RQ1 workflow

This describes the implemented `rq1-nine-stage-v2` workflow. The
[implementation guide](RQ1_IMPLEMENTATION_GUIDE.md) remains the design record,
including prospective research extensions; this document states current behavior.

## First offline run

1. Launch with `RRS_LLM_PROVIDER=disabled` using [the README](../README.md).
2. Choose the source role and authority, paste text or upload files, and save them.
   Parsing diagnostics stay visible.
3. Select evidence sources and enter competency questions, one per line. Background
   material is excluded from the evidence snapshot.
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

States are `created → eliciting → normalizing → verifying → consolidating → routing
→ awaiting_human → completed`, with `failed` and `cancelled` outcomes. Stage indicators
are independent. Partial baselines can be published while other records await review.
Publication completes the run when all active records are accepted/rejected/out of
scope. Deferred records stay unresolved. Editing a completed run reopens adjudication
without changing an already published baseline.

## Agent responsibilities and selective discussion

The 12 existing extraction perspectives come from `config/agent_roles.yaml`. Each
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

Cases freeze exact revisions and evidence. Up to four participants, including a
grounding/scope critic, challenge claims and retain proposals and dissent. Defaults
are three rounds, 12 calls, 1,000 output tokens per call, 12,000 reserved output
tokens and 300 seconds for scheduling new calls. An in-flight provider request uses
its configured timeout and may finish after that scheduling window. Actual token
usage/cost are unavailable in the provider abstraction and are never reported as zero.
Cases stop on finished participants, budgets, provider failure or cancellation.
Agreement cannot accept or mutate requirements; proposed changes require human
revision, requalification and a later acceptance decision.

Sebastian-inspired mechanisms are selective routing, bounded turns, frozen shared
context and observable messages. RQ1-specific logic is source addressing, support
assessment, metadata-neutral normalization, disagreement and human acceptance.
Upstream mutable mapping state and mapping commands are not invoked.

## API, persistence and retry

New endpoints use `/api/rq1/v2`; `/docs` exposes complete request contracts.

| Endpoint | Purpose |
| --- | --- |
| `POST /sources`, `GET /sources`, `GET /sources/{version}` | Acquire and inspect immutable sources/diagnostics |
| `POST /snapshots` | Freeze sources, evidence and declared tasks |
| `GET /evidence/{id}` | Inspect source resolution and selectors |
| `POST /runs` | Return 202 and queue execution |
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
