# Profile Requirements Extraction

A local research workbench for extracting, inspecting, and validating traceable
metadata requirements from heterogeneous domain materials. Formerly `rq1-blackboard`.

The default interface implements the persistent **nine-stage RQ1 workflow**:

1. Acquire versioned source artifacts and record their authority.
2. Decompose them into stable, addressable evidence units.
3. Elicit candidates independently from selected perspectives.
4. Normalize atomic, typed, implementation-neutral requirement records.
5. Verify original-source provenance before assessing semantic support and quality.
6. Consolidate exact equivalents while retaining conflicting alternatives.
7. Deliberate selectively on grounded issues within explicit budgets.
8. Obtain revision-specific human adjudication.
9. Publish an immutable, traceable validated requirement baseline for RQ2.

See [the operating guide](docs/WORKFLOW_V2.md) for formats, review gates, APIs,
persistence, evaluation and limitations, and [the implementation design](docs/RQ1_IMPLEMENTATION_GUIDE.md)
for the architectural rationale. The **Original study workbench** tab
preserves the earlier v1 extraction/expert-evaluation workflow for comparisons;
[its UI guide](docs/UI_GUIDE.md) applies to that tab.

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
model locally, then explicitly opt in to live calls in the new workbench. V2
rejects an unavailable provider instead of silently falling back. A ChatGPT/Codex
subscription does not supply a model endpoint to this application. Development
and tests for this implementation made no paid model requests. A small synthetic,
local-only Qwen3.5 27B run exercised the persistent workflow; its simulated
human decisions are demonstration data, not validated research requirements.

For frontend development, keep the API running and use `npm run dev` from
`frontend`. Port 5174 proxies `/api` to port 8011. Alternatively,
`docker compose up --build` builds the app with a named data volume; that
configuration has not been exercised in this implementation.

## Persistence and exports

V2 saves sources, evidence, runs, review decisions, discussion threads and
baselines in SQLite, by default `.rq1-workflow/workflow.sqlite3`. Override
`RQ1_WORKFLOW_STORE` to choose a location. Docker uses `/data/workflow.sqlite3`.
Reloading the UI restores saved runs from the server. The browser only remembers
the selected run ID. Back up the database while the application is stopped, or
use SQLite's backup API while running; exports are portable audit artifacts,
not database restore files.

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
