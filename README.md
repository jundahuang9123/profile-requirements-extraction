# Profile Requirements Extraction

A local research workbench for extracting, inspecting, and validating traceable
metadata requirements from heterogeneous domain materials. Formerly `rq1-blackboard`.

New agent runs produce a **minimal, traceable list of needs**. RQ1 states what
people or systems need to know, find, judge or do; vocabulary terms stay separately
as observed RQ2 hints. Source-checked candidates are grouped into needs, classified
against the selected base, optionally scoped by independently checked use-case
necessity, assessed once per retained need, and ranked for human review.

See [RQ1 needs: definitions, processing, UI and limits](docs/RQ1_NEEDS.md).
Set-aside items remain visible and restorable. Discussion is on request by default;
automatic discussion is optional. Saved extractions can be reprocessed in separate
trials without changing historical runs or using reference answers.

See [the operating guide](docs/WORKFLOW_V2.md) for formats, review gates, APIs,
persistence, evaluation and limitations, and [the implementation design](docs/RQ1_IMPLEMENTATION_GUIDE.md)
for the architectural rationale. The UI opens the persistent workflow; the v1
tab has been removed. Historical backend endpoints remain for compatibility,
and [the old UI guide](docs/UI_GUIDE.md) describes that earlier interface.
See [current validation status and known issues](docs/CURRENT_VALIDATION_STATUS.md)
before interpreting saved trials as research results.

The [stakeholder role-selection guide](docs/ROLE_SELECTION.md) explains automatic
panel selection, documented/inferred/proposed roles, citation checks, bounded processing,
saved manifests and optional human overrides. Fixed panels remain available for comparisons.
The [source preparation guide](docs/SOURCE_PREPARATION.md) explains what to skim,
what the software prepares, and which evidence still needs human review.

## Starting version and active branch

`main` is the default development branch. Historical branches are
preserved as archive tags rather than active branches; see [repository maintenance](docs/REPOSITORY_MAINTENANCE.md).

On **Sources & scope**, select the starting DCAT / DCAT-AP version for each run:
DCAT-AP 2.0.1, 2.1.1, 3.0.0 or 3.0.1, or W3C DCAT 2 / 3. Mobility reproduction
keeps DCAT-AP 2.0.1. New profiles can explicitly target a 3.x release. The choice
and pinned checksum stay with the saved run. See [base selection and version
provenance](docs/BASE_PROFILE.md) for the distinction between vocabulary terms and
application-profile obligations, offline registry sources, and derived comparisons.

## Run locally

Use Python 3.11 or 3.12 and Node.js 22. From the repository root:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cd frontend
npm ci
npm run build
cd ..
RRS_LLM_PROVIDER=disabled ./scripts/run-rq1.sh
```

Open http://127.0.0.1:8011. The server serves the built UI and API; interactive
API documentation is at http://127.0.0.1:8011/docs.

**Rules** and **offline mock perspectives** use no model service. Rules are a
conservative text baseline, and mock proposals are explicitly labelled demos.
Their authentic citations still require a human semantic/quality assessment.
No model credentials are needed for either strategy.

Live independent elicitation and deliberation use the existing provider client
and role configuration. Copy `.env.example` to `.env`, configure a provider and
model locally, then explicitly opt in to live calls in the new workbench. For
test and benchmark runs, choose **Discussion: only when a reviewer asks** to skip
the automatic discussion step and its model calls. V2
rejects an unavailable provider instead of silently falling back. A ChatGPT/Codex
subscription does not supply a model endpoint to this application. Development
and tests for this implementation made no paid model requests. A small synthetic,
local-only Qwen3.5 27B run exercised the persistent workflow; its simulated
human decisions are demonstration data, not validated research requirements.

The RQ1 UI also has a **Model provider** panel for OpenAI, KI:connect, Ollama,
Anthropic, and other OpenAI-compatible endpoints. You can enter a model ID or
load IDs from the selected endpoint. Credentials entered in the panel stay in
the running service's memory and are never placed in browser storage or run
exports; restarting the service clears them. Ollama defaults to localhost for
the local Mac service and to `host.docker.internal` in Docker. Confirm the
model is present in Ollama before running a live workflow.

Agent runs also support a collapsed **Advanced · model per step** setting.
Defaults use the configured model throughout; overrides are validated and saved
with each run or derived trial. See [model choices and the one-role Qwen smoke
test](docs/STEP_MODELS.md) for routing, checkpoint and reasoning-budget details.

For frontend development, keep the API running and use `npm run dev` from
`frontend`. Port 5174 proxies `/api` to port 8011. Alternatively,
`docker compose up --build` builds the app with a named data volume; that
configuration has not been exercised in this implementation.

## Persistence and exports

V2 saves sources, evidence, runs, review decisions, discussion threads and
baselines in SQLite, by default `.rq1-workflow/workflow.sqlite3`. Override
`RQ1_WORKFLOW_STORE` to choose a location. Docker uses `/data/workflow.sqlite3`.
Reloading the UI restores saved runs from the server. The browser only remembers
the selected run ID. Model-call logs, stage copies and other parts that only grow
are stored as rows next to each run, so a model call no longer rewrites the run.
Do not open a database written by this version with an earlier one. Back up the
database while the application is stopped, or use SQLite's backup API while
running; exports are portable audit artifacts, not database restore files.

**Export saved review** downloads `rq1-requirement-dataset-v2` without rerunning
extraction. **Publish accepted requirements** creates
`rq1-validated-requirement-baseline-v2`, with exact accepted revisions, original
source bytes, resolvable evidence, assessments, human decisions, derivation history,
frozen machine output and an excluded/unresolved appendix. Edits after publication
create new unaccepted revisions; previously published baselines remain unchanged.
RQ1 does not generate LinkML/SHACL profile decisions as an acceptance side effect.

The legacy v1 tab and endpoints retain their original export/persistence semantics.
Do not relabel a v1 frozen evaluation package as v2.

## Validate and evaluate offline

```sh
.venv/bin/python -m pytest tests -q
.venv/bin/python scripts/export_workflow_schema.py --check
cd frontend
npm run build
```

Tests block outbound sockets and use fixtures or mocks. They cover original
source resolution, structured selectors, tampering, role isolation, partial failure,
bounded dissent, conflict preservation, stale/idempotent commands, revision gates,
human-added needs, restart/retry, frozen machine metrics and baseline provenance.

Download the new workbench's review or baseline JSON, then summarize it without
calling a model:

```sh
.venv/bin/python scripts/evaluate_workflow.py rq1-saved-workflow.json --out metrics.json
```

Machine, current review and accepted results are reported separately. Task-link
presence is not evidence of successful task coverage. Precision/recall needs an
independently adjudicated reference set; the new metrics do not infer it from
lexical similarity. `scripts/evaluate_rq1.py` remains the v1 strategy and
expert-evaluation harness.

## Repository structure and attribution

- `requirement-reuse-service/requirement_reuse_service/workflow/`: v2 contracts,
  adapters, source verification, orchestration, storage, evaluation and API.
- `frontend/`: persistent v2 React workbench plus the original v1 study interface.
- `requirement-reuse-service/schema/rq1_workflow_v2.schema.json`: generated v2
  runtime contracts. The original LinkML schema describes v1.
- `scripts/`, `tests/`, `docs/`: launchers, offline evaluation, fixtures and guides.
- `blackboard/`, `simplellm/`, `datacorpus/`, root `main.py` and `requirements.txt`:
  Sebastian's original prototype, separate from the RQ1 app's dependencies.

Derived from [Sebastian's SimpleLLM & SAST Blackboard](https://github.com/U0iS112/654321),
with the earlier RQ1 service/interface migrated from
[Visual Profile Editor](https://github.com/jundahuang9123/visual-profile-editor).
V2 adapts bounded turns, selective routing, frozen context and durable messages to
requirement review. It does not invoke upstream semantic-mapping commands or
treat agent agreement as human acceptance. See [attribution](THIRD_PARTY_NOTICES.md)
and [the source snapshot manifest](docs/VPE_SOURCE_MANIFEST.json).

See [exact extraction citations and provider request limits](docs/EXTRACTION_CITATIONS.md) for the current citation policy and KI:connect configuration.

### Workflow pages and progression

The application now opens only the persistent workflow. Each step has its own page
and saved-result download. Choose **Step by step** for human use: processing saves
and pauses after each stage, until Continue is clicked. Choose **Automatic** for a
test run. Opening or changing pages never starts a model call. Completed extraction
batches and matching semantic assessments are checkpointed for interruption recovery.
See [WORKFLOW_V2.md](docs/WORKFLOW_V2.md) for recovery limits and historical-run behaviour.

Completed extraction can be reprocessed in a **new run** using **Re-run steps 4–7 with new settings**. The source run stays unchanged; extraction is reused and compatible identical assessments can be reused. See [consolidation and downstream trials](docs/CONSOLIDATION.md).

New agent runs default to **Merge candidates with the same meaning**; choose **Exact copies only** for the earlier comparison condition. Rules runs retain exact merging. Uncited proposals stay in the step 4 audit, and step 6 groups linked candidates with their original members and obligation variants. Human review remains required. Historical saved runs keep their original policies; no previous results are rewritten.

For source-routed extraction, stakeholder discussion and mediator revisions, see
[the protocol and traceability guide](docs/ROUTED_STAKEHOLDER_WORKFLOW.md).
