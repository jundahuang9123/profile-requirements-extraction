# RQ1 Blackboard

A standalone research workbench for extracting and reviewing traceable
DCAT-compatible metadata requirements from domain materials and user tasks.

Derived from [Sebastian's SimpleLLM & SAST Blackboard](https://github.com/U0iS112/654321),
with the existing RQ1 service and interface migrated from
[Visual Profile Editor](https://github.com/jundahuang9123/visual-profile-editor).

See the [visual UI and operating guide](docs/UI_GUIDE.md) for the interface layout,
a first run, review controls, multi-agent setup, expert evaluation and exports.

## Current implementation

- Domain evidence ingestion: text, AAS JSON/AASX, DCAT/RDF, and lightweight IFC.
- Rules, verified LLM, hybrid, and bounded role-conditioned multi-agent extraction.
- The existing 15-role study process: 12 extractors, one consolidator, two critics.
- Requirement/source inspection, contributions and critiques, validation flags,
  editing, approval/rejection, merge/split, and reviewed dataset export.
- Frozen evaluation packages, independent expert review, aggregation, controlled
  revision, and validated requirement baseline export.
- Standalone API and UI; no VPE server or editor state is required.

The original blackboard implementation is preserved as the upstream foundation.
The migrated RQ1 workflow currently uses the VPE bounded orchestration; it does
not yet call Sebastian's discussion engine. The interactive, persistent discussion
board and RQ1-specific deliberation adapter are the next integration milestone.
The current trace ledger is not a threaded debate. See [migration and board plan](docs/VPE_MIGRATION.md).

RQ1 ends with reviewed, evidence-linked requirements. VPE owns downstream
vocabulary/profile decisions, LinkML/SHACL generation, and visual profile editing.
Candidate metadata actions in an RQ1 export remain suggestions. Original VPE
files have not been removed or changed by this migration.

## Run locally

Use Python 3.11 or 3.12 and Node.js 22. From the repository root:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cd frontend
npm ci
npm run build
cd ..
./scripts/run-rq1.sh
```

Open http://127.0.0.1:8011. This single local server serves the built UI and API.
Interactive API documentation is at http://127.0.0.1:8011/docs.

The default has no model credentials and works with the rules baseline. To
configure live LLM extraction, copy `.env.example` to `.env` and set the provider,
model, and provider credentials locally. Existing `RRS_*` environment names are
retained for compatibility. `mock` is an explicit test/demo provider, never a live
model result. Live provider execution has not been validated in the migration.

For UI development, run the API above and `npm run dev` from `frontend` in another
terminal. The development UI uses http://127.0.0.1:5174 and proxies to port 8011.
These ports are separate from VPE's usual ports.

Alternatively, `docker compose up --build` builds and serves the complete app on
127.0.0.1:8011, with a named volume for requirement sets and agent cache. The
Docker configuration is supplied but has not been run during migration.

## Outputs and persistence

The review screen exports `rq1-requirement-dataset-v1` with reviewed requirements,
rejected/unresolved items, evidence, editor history, and merge/split history.
Expert evaluation exports frozen packages and
`rq1-validated-requirement-baseline-v1` for the formal handoff to RQ2.

The `/api/requirements/export-rq1-dataset` API runs a reproducible extraction;
it does not export unsaved browser edits. Use the UI's **Export RQ1 Dataset** for
reviewed browser state. The UI has no full-session save/restore, so export before
reloading. Some reviewer draft fields use browser-local storage; this does not
back up the complete evaluation session. The API also offers explicit requirement
set save/load endpoints, backed by local YAML files; these are not automatic UI
session persistence.

Requirement sets, model keys, role caches, generated retrieval databases, and
research run outputs are ignored by Git. Only source and curated configuration
are versioned. See `requirement-reuse-service/rag/README.md` for building the
optional, role-specific retrieval stores.

## Validate

```sh
.venv/bin/python -m pytest tests -q
cd frontend && npm run build
```

The migrated suite covers evidence verification, model fallback, role isolation,
consolidation, failure handling, cached role reruns, frozen review and consensus,
exports, and the standalone HTTP API. Tests use offline fixtures or mocks.

## Repository layout

- `requirement-reuse-service/`: independent RQ1 API, extraction, evaluation,
  schemas, role configuration, and curated retrieval resources. The original
  Python package name is retained to minimize compatibility changes.
- `frontend/`: RQ1 React workbench and agent/evaluation interfaces.
- `scripts/`: extraction/evaluation tools and local application launcher.
- `tests/`: migrated RQ1 tests and standalone API checks.
- `blackboard/`, `simplellm/`, `datacorpus/`, root `main.py` and `requirements.txt`:
  original Sebastian prototype; not the RQ1 app's runtime/dependencies.
- `docs/`: source provenance, licenses, and the next integration steps.

See [source attribution](THIRD_PARTY_NOTICES.md) and
[source snapshot manifest](docs/VPE_SOURCE_MANIFEST.json).
