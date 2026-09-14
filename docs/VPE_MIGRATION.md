# RQ1 migration from Visual Profile Editor

The RQ1 service and UI migration is implemented in this repository. Source
provenance is recorded in `VPE_SOURCE_MANIFEST.json`; source VPE files remain
unchanged. The standalone app exposes RQ1 routes, requirements review, agent
traces, and expert evaluation without VPE's editor or backend proxy. RQ2 profile
generation routes and screens were removed. Some shared legacy model/helper
names remain for compatibility; no profile-generation engine was migrated.

The following source inventory and acceptance plan records the separation
boundary. The persistent threaded discussion board and adaptation of Sebastian's
engine to RQ1 remain planned work. Current behavior preserves VPE's bounded study
process. No live model run or Docker build was performed for this migration.

## Inspected source

- Repository: <https://github.com/jundahuang9123/visual-profile-editor>
- Inspection date: 2026-09-14
- Checked-out branch: `feature/role-conditioned-15-agent-workflow`
- HEAD: `dc216b0e410594b7fb22eef3f823a17dd57a46e2`
- The local `main` and `origin/main` references pointed to the same commit.
- The inspected working tree contained 23 modified tracked files and additional
  untracked RQ1 components, agent code, role configuration, RAG resources, and
  tests. Those changes are not represented by the commit above. A clone at HEAD
  will not reproduce the inspected implementation.

Before migration, capture the intended working-tree files in a reviewed source
snapshot or commit, with a file manifest and content hashes. Record that snapshot
as the actual migration source. Exclude credentials, local caches, generated
research runs, and private corpus or reviewer data. Do not alter or discard the
VPE working tree as part of creating that snapshot.

## Ownership after separation

| Responsibility | New RQ1 repository | VPE / RQ2 |
| --- | --- | --- |
| Corpus ingestion, evidence units, task links | Owns | Consumes evidence references in the handoff |
| Extraction strategies, role contexts, consolidation, critics | Owns | Does not rerun extraction |
| Traceable discussion and human review | Owns | Consumes accepted requirements |
| Frozen evaluation, revision, consensus | Owns | Enforces eligibility at import/generation |
| Requirement records and validated baseline export | Owns and versions | Imports through a versioned contract |
| Profile change proposals, LinkML and SHACL generation | Exports metadata-action suggestions | Owns generation and review |
| Visual profile editing, validation, final profile export | Outside RQ1 scope | Owns |

Candidate metadata actions remain suggestions in the RQ1 handoff. Generating a
profile change set or accepting a suggested term remains a downstream decision.

## Source components to migrate

All paths below are relative to the VPE repository root.

| Source paths | Intended use |
| --- | --- |
| `requirement-reuse-service/requirement_reuse_service/service.py` | Extract the RQ1 analysis dispatch, evidence parsing, candidate extraction, verification, duplicate detection, and RQ1 export functions. Separate the reuse recommendation and constraint-generation functions. |
| `requirement-reuse-service/requirement_reuse_service/llm/` | Provider configuration, structured output clients, extraction prompts, and evidence verification. |
| `requirement-reuse-service/requirement_reuse_service/agents/` | Bounded orchestration, context assembly, consolidation, critics, and controlled post-evaluation revision. |
| `requirement-reuse-service/config/agent_roles.yaml` | Versioned role definitions and the existing panel presets. |
| `requirement-reuse-service/requirement_reuse_service/models.py` | RQ1 request/response, evidence, candidate, trace, evaluation, review, and baseline models. Split downstream profile-generation models. |
| `requirement-reuse-service/schema/requirement_record.linkml.yaml` and `requirement-reuse-service/schema/rq1_codebook.yaml` | Requirement representation and research boundary. Keep definitions aligned with runtime models. |
| `requirement-reuse-service/requirement_reuse_service/rq1_codebook.py` | Load the versioned codebook into extraction and export. |
| `requirement-reuse-service/requirement_reuse_service/term_registry.py` | Preserve shared vocabulary validation used by RQ1; extract a shared resource or version its exported vocabulary contract. |
| `requirement-reuse-service/requirement_reuse_service/evaluation.py` | Package freezing, independent review validation, aggregation, controlled revision, and consensus. |
| `requirement-reuse-service/requirement_reuse_service/registry.py` | Requirement-set storage; extend storage deliberately for board and study artifacts. |
| `frontend/src/components/requirements/AgentProcessGraph.tsx`, `AgentRunSummary.tsx`, `AgentContributionView.tsx`, `MultiAgentSetupPanel.tsx`, `EvaluationWorkflowPanel.tsx`, and `agentRoles.ts` | Reuse setup, trace inspection, contributions, critique, and human evaluation UI after adapting API imports. All six files are in `frontend/src/components/requirements/`. |
| `frontend/src/components/RequirementWorkbench.tsx` | Extract corpus/task input, candidate review, edit/merge/split, filtering, and reviewed-state export. Remove VPE editor-store and RQ2 generation dependencies. |
| `frontend/src/lib/requirementApi.ts` and relevant rules in `frontend/src/styles.css` | Split RQ1 API types/client and UI styles from profile-specific types and endpoints. |
| `requirement-reuse-service/requirement_reuse_service/main.py`, `requirement-reuse-service/Dockerfile`, and `requirement-reuse-service/requirements.txt` | Adapt the independently deployable service into the new application; include required schema and configuration assets in packaging. |
| `scripts/extract_requirements.py` and `scripts/evaluate_rq1.py` | Preserve offline corpus runs and reproducible strategy evaluation. |

Review `requirement-reuse-service/rag/`, `examples/requirement-corpus/`,
`examples/rq1-gold/`, and `examples/rq1-exports/` separately before moving any
assets. They are useful migration inputs, not an instruction to copy research
data. Gold requirements and expert answers remain held out from extraction.

Leave `requirement-reuse-service/requirement_reuse_service/profile_generation.py`
and the corresponding RQ2 endpoints, UI, and exports with VPE. Adapt
`backend/app/requirement_routes.py` only when VPE is ready to consume the external
RQ1 service or exported baseline.

## Two explicit modes

**Study mode preserves the implemented bounded process:** a fixed corpus and
predefined tasks feed 12 independent extraction roles; one consolidator receives
their preserved raw candidates; two independent critics inspect the consolidated
set; the machine output and findings are frozen for human evaluation. Extraction
roles do not see one another's outputs. There is no debate loop and agents never
approve requirements. Preserve `full_15`, `pilot_core`, and `extraction_12` labels
without reporting reduced or incomplete runs as the full formal condition.

**Discussion mode adds the requested blackboard interaction:** proposals,
questions, replies, objections, evidence references, and human decisions can be
linked to requirement versions. Treat this as a separate, explicitly labeled
mode until its study methodology is defined. A discussion must not silently
change frozen machine output, reveal other experts' submissions during
independent review, or add extra agent passes to a formal study run. Any promotion
of discussion content into a study or revised baseline must be an explicit,
recorded operation.

The VPE source contains an ordered workflow trace ledger and reviewer comments;
it does not yet implement a threaded discussion board. The new board should keep
stable post IDs, author identity/type, timestamps, reply links, referenced
requirement versions and evidence IDs, and edit history. Human decisions must
record the actor and rationale; an agent post is never a human decision.

## Handoff and provenance contract

Preserve the current serialized contracts while introducing explicit schema
versioning for any new board objects:

- `rq1-requirement-dataset-v1` and `rq1-multi-agent-dataset-v1` distinguish
  reproducible machine runs from exports of reviewed frontend state.
- `rq1-evaluation-package-v1` freezes original machine requirements, evidence,
  role configuration, context packages, runs, consolidation, critique, and trace
  data under a canonical hash.
- `rq1-expert-review-v1`, `rq1-review-aggregation-v1`, and
  `rq1-post-evaluation-revision-v1` keep independent submissions, aggregate
  findings, and later revisions separate.
- `rq1-validated-requirement-baseline-v1` carries consensus-accepted requirements,
  consensus decisions, the originating package ID/hash, and original machine
  requirement IDs. `RequirementSet` remains a convenience interchange/storage
  model, not proof of formal consensus on its own.

Retain evidence locators and verified quotes, task links, raw-to-consolidated
candidate mappings, role/model/prompt/workflow versions, context hashes, and
exact input/output IDs. Supplemental RAG context remains distinguishable from
citable corpus evidence. Retain original machine statements through revision;
expert additions remain labeled `expert_added`. For formal RQ2 import, require
approved status and an accepted or accepted-with-revision formal consensus
decision. Import must not automatically mutate the active VPE profile.

## Migration sequence and acceptance checks

1. **Capture and inventory the source.** Record the reviewed working-tree
   snapshot, licenses, hashes, and selected paths. Verify that untracked agent and
   evaluation files are included and that private data, credentials, and caches
   are absent.
2. **Move the RQ1 service and contracts.** Separate profile generation, update
   imports and packaging, and expose a standalone API. An offline fixture must
   produce evidence-linked candidates and an export without requiring VPE or a
   live model provider.
3. **Preserve the research behavior.** Port relevant checks from
   `tests/test_llm_extraction.py`, `tests/test_multi_agent_extraction.py`,
   `tests/test_expert_evaluation.py`, `tests/test_rq1_export.py`, and
   `tests/test_requirement_reuse_service.py`. Verify fabricated quotes are
   rejected, role failures remain visible, raw candidates survive consolidation,
   critics do not rewrite statements, and rerunning one role preserves the other
   successful cached outputs.
4. **Integrate the RQ1 UI and traceable board.** Verify a user can inspect a
   requirement's source span, producing role, consolidation and critic records,
   then create a linked discussion and see its history after reload. Check that
   mode labels and frozen-study restrictions hold across the API and UI.
5. **Verify independent evaluation and export.** Changing a frozen package must
   invalidate its hash; mismatched or duplicate review items must be rejected;
   independent reviewers must not receive each other's submissions. Complete a
   three-reviewer fixture, controlled revision, and consensus; confirm that
   exported requirements preserve original statements and all provenance links.
6. **Connect VPE at the handoff.** Import a baseline fixture into RQ2. Confirm
   nonaccepted formal candidates cannot generate changes, accepted requirements
   retain evidence/requirement mappings, and applying a generated profile draft
   remains a separate user action. Keep VPE's existing implementation intact
   until this integration passes.

The migrated RQ1 tests and standalone API checks pass; the production UI builds.
Discussion-board and downstream VPE integration checks remain future work.
