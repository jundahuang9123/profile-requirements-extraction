# RQ1 requirement-extraction workflow: implementation guide

Status: original design and implementation plan. The persistent nine-stage v2 workflow now lives in `requirement_reuse_service/workflow/` and the default workbench. See [current operating behavior and limitations](WORKFLOW_V2.md); prospective extensions below are not claims of completed functionality. The repository is now named `profile-requirements-extraction`.

Repository inspected: `jundahuang9123/rq1-blackboard`, commit `8d512b9071750d300f08d5c87fa0612a1c65bea2` on `main`, 4 October 2026. “Current” refers to that snapshot. New types, services, routes, thresholds, and filenames are proposals unless explicitly identified as existing. Repository links are relative to this document.

## 1. Purpose and methodological boundary

RQ1 transforms heterogeneous domain material and declared stakeholder needs into a human-validated, evidence-linked requirement baseline for RQ2. RQ2 chooses vocabulary terms, designs application profiles, and generates implementation constraints. A requirement states the information or capability needed, its scope, and any evidenced obligation; it does not prematurely select an RDF predicate, database field, API, or SHACL shape.

The target workflow is:

1. Source acquisition.
2. Evidence decomposition into stable, addressable evidence units.
3. Independent multi-perspective elicitation.
4. Normalization into atomic, typed, implementation-neutral RequirementRecords.
5. Candidate verification and qualification: deterministic provenance/grounding, then semantic support and quality.
6. Consolidation while preserving disagreement.
7. Selective blackboard deliberation.
8. Human adjudication.
9. Validated requirement baseline for RQ2.

Stages 3 and 7 are deliberately different. Extractors initially see the frozen corpus and their recorded analytical context, not each other's proposals. Discussion happens later, only for selected issues. Multiple perspectives are not independent statistical samples, and model agreement is not proof of correctness.

Three boundaries are mandatory:

- **Observed content versus normative requirement:** an AAS element or IFC property proves that a structure occurs in an artifact. It does not alone establish that every dataset must expose it.
- **Source grounding versus semantic support:** a resolvable quote or triple proves a citation is authentic. It does not establish that the cited material entails the proposed requirement.
- **Requirement versus solution suggestion:** existing `candidate_metadata_actions` can remain optional, separately labelled RQ2 hints. Neither term availability nor a mapping score determines whether an RQ1 requirement is valid.

“Validated” means accepted through the documented human process with current verification evidence. It is not an automatic label assigned by a model or by passing a schema validator.

## 2. Current implementation and concrete changes

The existing workbench is a substantial starting point. Extend it incrementally; preserve the rules, LLM, hybrid, and existing multi-agent conditions for reproducible comparisons.

| Existing location | Observed behavior | Required extension |
| --- | --- | --- |
| [README](../README.md), [migration plan](VPE_MIGRATION.md) | Standalone RQ1 application migrated from VPE; upstream Sebastian code retained separately | Keep this application as the implementation target and retain attribution |
| [models.py](../requirement-reuse-service/requirement_reuse_service/models.py) | `EvidenceUnit`, `SourceEvidence`, `CandidateRequirement`, intent, provenance, contributions, consolidation events, critiques, evaluation and baseline models | Add source versions, typed selectors, immutable requirement revisions, orthogonal verification states, conflicts, deliberations and decisions |
| [service.py](../requirement-reuse-service/requirement_reuse_service/service.py) | `extract_evidence_units`, format-specific decomposition, normalization, validation, duplicate detection, exports | Separate decomposition, source verification, normalization, qualification and solution hints into services |
| [llm/extractor.py](../requirement-reuse-service/requirement_reuse_service/llm/extractor.py) | `locate_quote` uses exact then whitespace-tolerant matching inside `EvidenceUnit.content`; `convert_requirement` removes invalid evidence references | Retain quote matching but bind it to immutable original-source representations; preserve failed citation attempts in audit records |
| [agents/orchestrator.py](../requirement-reuse-service/requirement_reuse_service/agents/orchestrator.py) | Independent extraction via a thread pool, role context, cached outputs, bounded consolidation followed by critics | Insert explicit normalization and qualification before consolidation; schedule bounded deliberation after consolidation |
| [agent_roles.yaml](../requirement-reuse-service/config/agent_roles.yaml) | Full panel has 12 extraction roles, one consolidator, two critics; separate post-evaluation revision role | Reuse role identities, version their stage responsibilities, add deliberation policy separately from panel selection |
| [agents/consolidation.py](../requirement-reuse-service/requirement_reuse_service/agents/consolidation.py) | Preserves raw outputs and events; rechecks quotes; handles `merge`, `keep_separate`, `discard_unsupported`, `flag_conflict` | Prevent `flag_conflict` from materializing one representative as if alternatives were consolidated; retain linked alternatives and typed conflict records |
| [agents/critics.py](../requirement-reuse-service/requirement_reuse_service/agents/critics.py) | Structured critique findings after consolidation | Reuse findings for pre-consolidation qualification and post-consolidation review; distinguish which revision and stage each finding assesses |
| [evaluation.py](../requirement-reuse-service/requirement_reuse_service/evaluation.py) | Frozen packages, expert submissions, aggregation, controlled revision, consensus finalization | Enforce revision-specific grounding/qualification at finalization and preserve baseline dependency manifests |
| [main.py](../requirement-reuse-service/requirement_reuse_service/main.py) | FastAPI extraction, export, evaluation and requirement-set routes | Add persistent workflow/run and decision APIs without silently changing existing export semantics |
| [RequirementWorkbench.tsx](../frontend/src/components/RequirementWorkbench.tsx), [requirementApi.ts](../frontend/src/lib/requirementApi.ts) | Source and requirement inspection, editing, approval/rejection, merge/split, browser-state dataset export | Persist complete sessions; expose verification, conflicts, deliberation threads and revision history |
| [evaluation script](../scripts/evaluate_rq1.py), [tests](../tests) | Existing evaluation tooling and offline tests | Extend with source-resolution, disagreement preservation, state-machine and comparative evaluation fixtures |

Specific limitations to address, rather than treating the existing names as completed functionality:

- Text decomposition currently filters sentences using keyword patterns; sentences without recognized facts disappear before elicitation. Replace this with broad structural decomposition plus explicit inclusion/exclusion accounting.
- AAS JSON evidence uses generated strings such as `idShort = ...` and JSONPath-like locators. AAS XML uses regular-expression extraction; the main evidence dispatcher does not have an explicit standalone `aas-xml` branch. AASX delegates embedded files to JSON/XML helpers. Add an explicit, validated adapter contract for each accepted format.
- RDF evidence currently summarizes predicate counts and selected linked objects; it does not retain complete subject/predicate/object/graph evidence for each claim.
- IFC evidence currently reports schema, class counts and property-set names through lightweight text matching. It is not entity/property relationship resolution.
- `source_id` currently derives from the source name, and evidence IDs from source/kind/locator/content. Equal filenames and changed source bytes need explicit source-version handling.
- `normalize_requirements` primarily fills missing fields. It does not guarantee atomicity or implementation neutrality.
- `validate_requirement` mainly checks evidence presence and candidate-term/resource compatibility. Its `valid` state must not be interpreted as semantic entailment or human validation.
- Consolidation may choose a high-confidence representative, union evidence, and label a result explicit if any input was explicit. Support must instead be reassessed against the final wording and scope.
- Existing consensus finalization checks package/reviewer/decision consistency, but does not rerun source and semantic verification for final edited wording.
- YAML requirement-set storage and role caches exist; the README explicitly notes that full UI sessions are not automatically persisted. A workflow trace is currently a handoff ledger, not a persistent threaded debate.

## 3. Reuse from Sebastian: mechanism, not task semantics

The inspected [upstream core](../blackboard/codebase/core/blackboard_semantic_mapping.py) obtains discussion proposals from a reasoning agent and calls [DiscussionEngine](../blackboard/codebase/components/discussion_engine.py). That engine builds attribute/mapping context, iterates participants with a turn limit, applies mapping commands, records turns, and reports correction, acceptance, or no agreement. The RQ1 orchestrator currently does not call it.

| Sebastian-inspired mechanism | RQ1 adaptation | Do not transfer unchanged |
| --- | --- | --- |
| Shared inspectable decision context | Blackboard snapshot of requirement revisions, verified evidence, findings and conflicts | Attribute-to-ontology candidate state |
| Selective discussion scheduling | Deterministic issue triggers with optional model-assisted prioritization | Mapping uncertainty, ontology-candidate margins or attribute compatibility as RQ1 validity criteria |
| Participant selection | Originating perspective plus relevant domain critic and counter-perspective | Attribute names as participants, mapping-specific weak/strong roles |
| Bounded turns and explicit stopping | Budgeted discussion with proposal, dissent and unresolved outcomes | “Acceptance” interpreted as human acceptance |
| Structured commands | Validated proposals to clarify, split, link conflict, request evidence or recommend an outcome | Commands that mutate `final_mapping` or select ontology terms |
| Turn logs and decision history | Durable messages, evidence links, revision lineage and decisions | Logs as a substitute for original-source provenance |
| Signals before discussion | Source checks, support assessments and quality findings | Semantic-typing precision/recall as requirement-extraction evaluation |

Implement a small RQ1-specific deliberation adapter using the existing RQ1 LLM client. Reuse bounded orchestration ideas; do not make RQ1 depend on the upstream mapper's mutable state or prompt format. Any copied code requires the repository's existing attribution/licensing review through [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md). The separate `blackboard-workbench` can inform later UX experiments, but its implementation was not audited for this guide.

## 4. Proposed domain contracts

Use Pydantic as the runtime contract and keep [the LinkML schema](../requirement-reuse-service/schema/requirement_record.linkml.yaml), generated/export schemas and TypeScript types aligned. The definitions below are design contracts, not runnable replacements for current models. Introduce a versioned schema rather than changing the meaning of v1 fields in place.

### 4.1 SourceArtifact and source versions

```text
SourceArtifact
  source_id: persistent logical identity, independent of filename
  source_version_id: immutable ID for this registered version
  original_name, media_type, artifact_kind, declared_format_version
  raw_sha256, byte_length, blob_ref
  parent_source_version_id?: enclosing AASX/package version
  package_entry_path?: exact archive member
  origin_uri?, title?, authority?, license_or_access_note?
  source_role: normative_spec | stakeholder_need | example | observation | background
  acquisition_actor, acquired_at, previous_version_id?
  parse_status: pending | parsed | failed | unsupported
  parser_name, parser_version, parser_config_hash, parse_diagnostics[]

CorpusSnapshot
  corpus_id, snapshot_id, source_version_ids[], user_task_versions[]
  inclusion_policy_version, exclusions[], manifest_sha256, frozen_at
```

Keep logical source identity separate from content deduplication: identical bytes from two sources can share a blob while retaining separate provenance. Updating a file registers another version, never overwrites the old bytes. A declared stakeholder need can be a first-class source, with its author/date and text snapshot; an uncited analyst assumption stays an assumption.

### 4.2 EvidenceUnit and EvidenceLink

An evidence unit is a source-addressable fragment with enough context to support or contradict a candidate claim. It may be a paragraph, table row with headers, AAS element with parent identity, RDF subgraph, IFC relationship/property context, or complete competency question. It is not necessarily the smallest token chunk, and the same unit may support multiple requirements.

```text
EvidenceUnit
  evidence_id, schema_version, source_id, source_version_id
  kind: text_span | table_region | aas_element | rdf_subgraph | ifc_property | user_task
  selector: discriminated union described in section 6
  content: faithful display representation
  content_sha256, representation_version
  structural_context: headings / parents / identifiers / linked selectors
  source_claim_kind: normative | descriptive | example | stakeholder_statement
  derived_annotations[]: separately attributed, never treated as source quotations
  extraction_activity_id, parser_version, created_at

EvidenceLink
  link_id, requirement_revision_id, evidence_id
  relation: supports | contradicts | contextualizes
  claim_component: statement | obligation | scope | condition | value_kind
  selector_within_unit?, exact_quote_or_fact, inference_rationale?
  grounding_check_id, semantic_assessment_id?
```

Use a deterministic evidence key over `(source_version_id, canonical selector, decomposition version, representation hash)`. Re-decomposing the same snapshot with the same parser/configuration must reproduce IDs. New parsing rules or changed source bytes create new evidence versions, with `supersedes` links if needed. Do not promise that offsets, array positions, STEP IDs or blank-node labels remain stable across source versions.

`extracted_facts` from the current model should migrate into attributed derived annotations unless they are demonstrably direct source facts. Retrieval chunks may contain several evidence units; their retrieval IDs are not citation IDs.

### 4.3 Observation and RequirementRecord

Preserve initial elicitation output separately from normalized requirements:

```text
ElicitationObservation
  observation_id, run_id, role_id, source_evidence_ids[]
  proposed_need, rationale, assumptions[], support_claim
  user_task_ids[], raw_output_ref, context_hash
  disposition: pending | normalized | non_requirement | unsupported

RequirementRecord
  requirement_id: logical identity across edits
  revision_id, revision_number, schema_version, content_hash
  parent_revision_ids[], derived_from_observation_ids[]
  raw_statement, normalized_statement
  requirement_type: existing RequirementType vocabulary
  normalized_intent:
    resource_type: existing ResourceType; Unknown when unresolved
    metadata_need, value_kind, obligation_hint
  scope: subject_population, lifecycle_stage?, jurisdiction?, applicability?
  conditions[], rationale, assumptions[]
  evidence_links[], supports_user_tasks[]
  support_level: explicit | evidence_supported_inference | unsupported
  verification_report_id, qualification_report_id
  conflict_ids[], consolidation_event_ids[], deliberation_ids[]
  lifecycle_state, review_decision_id?
  created_by, created_at, run_id, provenance_activity_ids[]
  rq2_hints?: separate nonbinding candidate_metadata_actions
```

Retain the current requirement-type taxonomy initially: descriptive metadata, semantic anchor, technical metadata, access policy, quality/provenance, lifecycle context, controlled vocabulary, validation constraint, competency question and unknown. A type says what need is being expressed; it is not a vocabulary mapping. Unknown values are valid intermediate results and should trigger review, not default silently to `Dataset` or a guessed obligation.

Example normalized candidate:

```json
{
  "requirement_id": "REQ-017",
  "revision_id": "REQ-017-r1",
  "normalized_statement": "Dataset descriptions shall identify the construction asset represented by the dataset.",
  "requirement_type": "descriptive_metadata",
  "normalized_intent": {
    "resource_type": "Dataset",
    "metadata_need": "identify the represented construction asset",
    "value_kind": "unknown",
    "obligation_hint": "mandatory"
  },
  "scope": {"subject_population": "datasets in the agreed construction discovery use case"},
  "conditions": [],
  "support_level": "evidence_supported_inference",
  "supports_user_tasks": ["CQ-03"],
  "evidence_links": [
    {"evidence_id": "EU-031", "relation": "supports", "claim_component": "statement"},
    {"evidence_id": "EU-014", "relation": "contextualizes", "claim_component": "statement"}
  ],
  "lifecycle_state": "normalized",
  "rq2_hints": []
}
```

This is a partial illustrative record, not an accepted requirement or complete API payload. Suppose EU-031 says “Users must be able to discover datasets according to the represented construction asset,” and EU-014 contains an AAS identifier. The metadata obligation is an inference from the user need; the AAS identifier is contextual corroboration, not proof that a particular field or URI is mandatory. The obligation still needs its own assessment. If no authoritative evidence establishes it, set the obligation to `unknown` rather than inventing “shall.”

Atomicity means one independently assessable need per record. “Describe the asset and publish a download URL” becomes two child records with separate evidence assessments. Keep conditions necessary to the meaning attached. If a source explicitly requires a named standard, preserve that externally imposed constraint and its citation; implementation neutrality does not authorize deleting source obligations.

### 4.4 Verification, conflicts and decisions

| Proposed type | Required information |
| --- | --- |
| `VerificationReport` | Revision ID/hash; per-link resolver result; source/representation hashes; method/version; exact match or typed fact; `pass/fail/unverifiable/not_run`; diagnostics |
| `QualificationReport` | Revision ID; semantic support `explicit/inferred/unsupported/contradicted/uncertain`; rationale and premise links; atomicity, clarity, relevance, scope, obligation and implementation-neutrality findings; assessor identity/version |
| `ConflictRecord` | Member revision IDs; conflicting component; scope overlap; `contradiction/obligation/scope/interpretation`; supporting and opposing links; `open/resolved/deferred`; resolution decision |
| `ConsolidationEventV2` | All input/output revision IDs; `equivalent/merge_proposed/merged/keep_separate/conflict_linked/excluded`; component-level lineage; rationale; actor; timestamp |
| `DeliberationCase` | Subject revisions; trigger facts and policy version; frozen context hash; selected participants; round/token/time budgets; status; outcome proposal and unresolved issues |
| `BlackboardMessage` | Case ID, sequence, author/role, reply target, message type, body, citations, proposed revision/action, timestamp and idempotency key |
| `AdjudicationDecision` | Target revision/hash; human actor(s); `accept/reject/edit/split/merge/defer/out_of_scope`; rationale; resulting revisions; conflict dispositions; timestamp |
| `BaselineManifest` | Baseline ID/version/hash; exact accepted revisions; source snapshot; verification/decision dependencies; unresolved/excluded manifest; workflow/schema/code versions; predecessor baseline |

Every assessment targets a revision, not just a mutable requirement ID. An edit invalidates derived assessments unless a documented dependency rule proves they remain applicable. Initially choose conservative invalidation and rerun verification/qualification after every semantic edit.

## 5. Stage behavior and gates

| Stage | Inputs and responsibilities | Output and exit gate |
| --- | --- | --- |
| 1. Acquire | Register documents, structured artifacts, stakeholder needs and user tasks; distinguish evidence corpus from background; hash original bytes; classify authority | Immutable corpus snapshot; missing/unsupported/failed sources visible; no silent fallback labelled successful parsing |
| 2. Decompose | Adapter creates typed units and context; accounts for all parsed regions with inclusion/exclusion reasons | Units resolve to the source version; manifest records parser versions, omissions and truncation |
| 3. Elicit independently | Each configured perspective reads the same frozen corpus/task boundary plus recorded role context; may return no findings | Immutable observations and role-run records; no extractor has read peer candidates; failures retained |
| 4. Normalize | Preserve intent; split compound observations; assign type, scope and tentative obligation; separate RQ2 hints | Schema-valid atomic candidate revisions or explicit normalization issues; every observation accounted for |
| 5. Verify/qualify | Run deterministic resolvers first; assess support and quality on resolved content; record opposing evidence | Pass, repair-needed or blocked disposition with component-level reasons; no single confidence score substitutes for checks |
| 6. Consolidate | Detect potential equivalents; compare scope, obligation, conditions and evidence; preserve all alternatives | Canonical revisions plus lineage, keep-separate links and explicit conflicts; changed wording re-enters stage 5 |
| 7. Deliberate selectively | Policy selects qualified issues; participants challenge interpretations and propose revisions using frozen evidence | Proposed resolution or unresolved/deferred result; new revisions return to stage 5; no automatic human acceptance |
| 8. Adjudicate | Human inspects original evidence, findings, alternatives and proposed resolution; accept/reject/edit/split/merge/defer | Revision-specific decision; edits/splits/merges reverified before acceptance; every conflict explicitly disposed of |
| 9. Publish baseline | Assemble accepted current revisions and complete traceability closure; enforce study gates | Immutable validated baseline and separate unresolved/rejected appendix; RQ2 receives needs, not automatic profile changes |

Normalization may be implemented inside the same model request as elicitation initially, but its artifact, validation and lineage must remain a separate logical stage. A model returning structured JSON does not demonstrate that its statements are atomic or supported.

## 6. Deterministic grounding by source type

Reuse established parsing and addressing methods. Do not ask an LLM whether a locator exists, and do not use embedding similarity as proof of a citation. A deterministic check establishes fidelity to a pinned artifact; semantic inference is assessed separately in section 7.

### 6.1 Text, documents, tables and competency questions

- Preserve original bytes and a versioned extracted-text representation. Selectors contain representation hash and zero-based Unicode code-point offsets `[start, end)`. Python and JavaScript string indexing differ for non-BMP characters; convert explicitly in the UI and test emoji/non-Latin fixtures.
- Store exact quoted text and optional prefix/suffix context. Validate `representation[start:end] == quote`; when the existing whitespace-tolerant matcher is used, store the actual matched span and matching method. Repeated quotes require the supplied locator/context, not an arbitrary first match.
- Preserve page/section/paragraph identifiers for navigation. PDF extraction/OCR must record extractor/version and page bounding boxes when available. Text equality after OCR proves fidelity to the OCR representation, not accuracy against the visual page; uncertain OCR requires human inspection.
- Preserve table row/cell coordinates, headers, units and footnotes; a detached value without column context is insufficient. Competency questions and stakeholder statements keep their complete scope and author/source metadata.
- A normalization map is necessary if Unicode or whitespace normalization changes offsets. Never silently repair a failed quotation into a paraphrase. Exact evidence and model interpretation remain separate fields.

### 6.2 AAS JSON, XML and AASX

- For JSON, use a parsed document and [RFC 6901 JSON Pointer](https://www.rfc-editor.org/info/rfc6901/) as the deterministic primary locator. Store the selected typed value or subtree hash. A JSONPath-like display string may be retained for compatibility.
- Context includes shell/submodel identity, element type, parent chain, `idShort`, semantic-reference keys, value/value type and qualifiers when present. Do not treat `idShort` alone as globally unique.
- For XML, use a namespace-aware parser and a reproducible element/attribute selector with namespace bindings; resolve and compare typed values. Replace regex pseudo-XPath indices. For AASX, pin package hash, entry path and entry hash before resolving the embedded JSON/XML selector; reject ambiguous duplicate member names.
- Verify the selected node and each asserted component independently. A generated display string such as `ManufacturerName = Acme` is not a verbatim quote from JSON/XML; it is a reproducible rendering of a resolved structured fact.
- Array offsets and XML sibling positions are stable only within the pinned source version. Record an additional semantic identity path for navigation across versions, but never silently retarget an old evidence link.
- Parse failures and unsupported AAS versions create diagnostics, not normative evidence. Apply package size/entry limits and disable external XML entity loading as part of the parser contract.

### 6.3 RDF/DCAT and SHACL inputs

- Parse into a dataset retaining graph names, subject, predicate, object, literal datatype and language. An evidence unit is an explicit triple/quad set, often resource-centred with a bounded, versioned expansion policy.
- Store complete supporting quads and verify membership in the pinned parsed dataset. Predicate frequency is descriptive corpus metadata, not evidence for a particular resource or obligation.
- For blank nodes and order-independent graph fingerprints, use a pinned implementation of [RDF Dataset Canonicalization](https://www.w3.org/TR/rdf-canon/). Preserve the mapping and graph scope; canonical blank-node labels are not stable identities across edited datasets. Canonicalization failures remain visible.
- Record base IRI and parser settings. Freeze any required JSON-LD contexts or imported resources as explicit dependencies; avoid live network resolution changing a supposedly frozen source.
- SPARQL `ASK` or exact quad membership can implement deterministic checks, but record the actual matched quads. An entailed statement must record the rule set, reasoner and premise quads separately from asserted content.
- For SHACL evidence, retain the shape and property-path constraint context. Executing a shape tests data conformance; it does not establish that the shape is an appropriate RQ1 requirement. Preserve that distinction when a profile specification serves as normative source material.

### 6.4 IFC/BIM

- Replace regex-only summaries for claim grounding with a pinned schema-aware IFC parser. [IfcOpenShell's API](https://docs.ifcopenshell.org/autoapi/ifcopenshell/index.html) supports entity lookup, including GlobalId lookup; its [examples](https://docs.ifcopenshell.org/ifcopenshell-python/code_examples.html) demonstrate property-set access.
- Selector: source hash + schema version + entity GlobalId where available + STEP instance ID + relationship/property selector. Many supporting entities do not have a GlobalId; source-scoped STEP IDs are valid locators for them.
- For a property claim, persist and verify the owner entity, relationship chain, property-set identity, property name, typed value and unit. Distinguish occurrence properties from inherited type properties and record the traversal policy.
- A class/property-set count may remain an aggregate observation only if its deterministic query and contributing entity IDs are recorded. It cannot establish a specific property value or mandatory metadata obligation.
- Absent values, duplicate names, broken references and unparseable schema versions return distinct diagnostics. STEP IDs can change after reserialization; use the original snapshot for verification, not a newly saved file.

### 6.5 Shared verification algorithm

```text
for each evidence link on the exact requirement revision:
    load immutable source and representation dependencies
    check recorded hashes
    resolve the discriminated selector with its versioned adapter
    compare the cited quote, typed value, quad set or relationship path
    write a per-link result; retain failed attempts
check statement, obligation, scope and conditions have sufficient valid premises
if a material premise fails or is unavailable:
    block acceptance; route to evidence repair or human clarification
else:
    run semantic support and quality qualification
```

Grounding is not “at least one quote survived.” A candidate with valid contextual evidence and an invalid normative premise remains blocked. A nonmaterial failed reference can be removed only through an audited new revision and requalification. A human may supply new source evidence or register a stakeholder decision; an override must not relabel an unresolved source check as passed.

## 7. Semantic support and quality qualification

Use existing critics and structured LLM output for judgements that are not deterministic, supplemented by human assessment. Each finding contains the assessed revision, criterion, cited premises, concise rationale, severity and recommended action. Model self-confidence is diagnostic metadata, not calibrated probability.

| Criterion | Question | Typical result |
| --- | --- | --- |
| Semantic support | Does resolved evidence support this claim, including conditions and obligation? | Explicit, inference with stated premises, uncertain, unsupported or contradicted |
| Atomicity | Can one part be accepted while another is rejected? | Split proposal with child-specific evidence |
| Clarity | Are subject, information need and conditions understandable? | Wording repair without adding scope |
| Relevance/scope | Does this belong to the agreed RQ1 metadata/use-case scope? | In-scope, uncertain, out-of-scope |
| Obligation | Does the source justify mandatory/recommended/optional wording? | Preserve modality or mark unknown |
| Implementation neutrality | Does it state a need or prematurely choose an encoding/term? | Separate solution hint; preserve externally mandated constraints |
| Sufficiency | Are all material parts supported, rather than only a related phrase? | Additional evidence or narrowed requirement |
| Contradiction | Is there verified counterevidence in an overlapping scope? | Conflict record; never delete opposing citations |

Use deterministic checks for structural schema validity, missing references and invalid enum values. Do not claim to deterministically establish natural-language atomicity or entailment. Optional entailment models can provide versioned assessments; disagreement or uncertainty routes to deliberation/human review. A useful inference is allowed if clearly marked and later accepted by humans; it must not be reported as explicit extraction.

## 8. Consolidation that preserves disagreement

Candidate retrieval can reuse `detect_duplicate_requirements` and later add embeddings. Similarity only nominates pairs. Compare semantic need, resource, scope, conditions, obligation and polarity before merging.

1. Group potential equivalents; keep original revisions immutable.
2. Mark equivalent candidates with separate role and source contributions. Do not count multiple role outputs citing one sentence as multiple independent evidence sources.
3. Materialize a canonical revision only when meanings are compatible. Record all parent revisions and field-level origin. Reverify the canonical statement, including inherited obligations.
4. If meanings conflict, create a `ConflictRecord` and keep each alternative. `flag_conflict` must not choose a winner by confidence or replace the alternatives with one statement.
5. Preserve weaker, unsupported and omitted candidates in the audit dataset with reasons. “Excluded from eligible candidates” is not deletion.
6. A split creates new logical requirement IDs with `split_from` lineage. A merge creates a canonical logical ID with all parent links; predecessor records remain accessible and cannot simultaneously count as accepted duplicates.

Example: one source says access should be public and another limits access to approved participants. First compare dataset population and conditions. Different scopes may justify two requirements; overlapping scope creates an access-policy conflict. A generic merged sentence such as “Provide appropriate access” loses the disagreement and is unacceptable.

## 9. Selective blackboard deliberation

### 9.1 Trigger policy

Run deterministic trigger evaluation over current candidate revisions and conflicts. Persist both selected and unselected decisions with reason codes. Initial policy values below are engineering defaults for pilot testing, not research findings.

| Trigger | Action |
| --- | --- |
| Broken source hash, missing locator or failed material evidence link | Evidence-repair queue; do not spend discussion tokens trying to validate a nonexistent citation |
| Verified sources disagree about an overlapping scope, obligation or polarity | Open conflict deliberation; include perspectives representing both alternatives |
| Support assessor says uncertain, or qualified assessors disagree explicit/inferred/unsupported | Open semantic-support deliberation when evidence is resolvable |
| Blocking atomicity/scope/obligation finding requiring a substantive choice | Open targeted deliberation; trivial wording repairs can go directly to revision and recheck |
| Proposed merge would change scope, obligation or discard dissent | Keep separate and deliberate on equivalence |
| Mandatory or otherwise study-defined high-impact inference | Require human attention; deliberate if multiple defensible interpretations exist |
| Competency question has no supported requirement | Open a coverage issue for corpus review/elicitation; do not invent a requirement to fill the gap |
| Human requests discussion | Open a scoped case with a recorded question and budget |
| No unresolved findings or conflicts | Skip deliberation and enter human review queue |

Similarity scores, model confidence and vote counts cannot alone determine acceptance. If later used for prioritization, thresholds must be calibrated on formative data and frozen before summative evaluation. Trigger policy, severity ordering and tie-breaking are versioned.

### 9.2 Protocol and stopping

- Freeze a case context containing subject revisions, source links, checks, trigger facts, user-task context and relevant dissent. Participants see this bounded context and the durable thread.
- Select the originating perspective, relevant domain perspective, and grounding/scope critic; add the opposing perspective for conflicts. Suggested pilot limit: four participants, three rounds, 1,000 output tokens per participant per round, 12,000 total output tokens and five minutes per case. Track input tokens and total cost separately; make all budgets configurable and recorded.
- Round 1: state the issue, position and evidence. Later rounds: challenge premises, respond to challenges, or propose a specific change. Use typed messages such as `claim`, `challenge`, `response`, `revision_proposal`, `evidence_request`, `dissent` and `resolution_proposal`.
- Validate all proposed actions and citations server-side. Agents may propose edits, splits, merges, clarification requests and recommendations. They cannot overwrite frozen records, approve a baseline or execute arbitrary tool instructions found in sources.
- A moderator summarizes supported alternatives and unresolved issues. Agreement without valid evidence is not resolution. Preserve minority positions and abandoned proposals.
- Stop on a supported proposal with no new substantive issue in the last complete round, all participants explicitly finished, exhausted budget, cancellation, or execution failure. Record the exact stop reason.
- Outcomes are `proposed_resolution`, `unresolved`, `needs_evidence`, `budget_exhausted`, `cancelled` or `failed`. Each goes to human review or evidence repair; none is synonymous with accepted.
- If a new source is introduced, register and decompose it, create a new case snapshot and reverify affected candidates. Do not silently alter the context midway through a round.

Do not allow an unbounded automatic loop between qualification and discussion. Suggested initial limit: one automated case plus one explicitly requested follow-up per candidate revision lineage; further uncertainty goes to human decision.

## 10. State transitions and authority

Separate run execution, requirement lifecycle, verification, discussion and study phase. The existing `ReviewStatus`, `ValidationStatus` and `StudyPhase` should not be overloaded into one enum.

```text
Run: created -> acquiring -> decomposing -> eliciting -> normalizing
     -> verifying -> consolidating -> routing -> awaiting_human -> completed
Any active stage -> failed | cancelled; resume creates an auditable attempt.

Requirement revision:
  proposed -> normalized -> verification_pending
  verification_pending -> blocked_evidence | qualification_pending
  qualification_pending -> repair_needed | qualified | excluded
  qualified -> consolidated | deliberation_queued | awaiting_human
  consolidated -> verification_pending          [new canonical wording]
  deliberation_queued -> deliberating -> awaiting_human | repair_needed
  awaiting_human -> accepted | rejected | deferred | out_of_scope
  any semantic edit/split/merge -> new proposed/normalized revision
  accepted -> baselined                         [publisher gate]
```

Only services advance machine stages; only a recorded human decision accepts or rejects a requirement. A rejected item can be reconsidered through a new revision/decision, never by deleting the rejection. `excluded` is a machine eligibility disposition and remains distinct from human rejection. An accepted old revision stays in an immutable prior baseline; its edited successor is unaccepted until reviewed.

Baseline eligibility requires: latest explicitly selected revision, passed material grounding checks, completed semantic/quality assessment, no unresolved blocking findings, accepted human decision for the same content hash, all applicable conflicts disposed of, and complete provenance closure. Human resolution may select one conflicting alternative while retaining the rejected alternative in the appendix. Deferred conflicts cannot accompany mutually inconsistent accepted requirements in the same applicability scope.

Keep the existing study sequence—development, formative review, frozen workflow, summative review, post-evaluation revision, consensus validation and validated—separate. Freeze the pre-human machine output before independent expert rating. Ratings, reference requirements and post-run corrections must remain held out from extraction and pre-evaluation deliberation. Post-evaluation agent assistance is explicitly human-guided revision, not improved original machine output.

## 11. Agent and service responsibilities

### 11.1 Existing perspectives

| Existing role | RQ1 elicitation responsibility |
| --- | --- |
| `standards_conformance` | Identify evidenced conformance/documentation needs and distinguish normative from informative sources |
| `dcat_reuse` | Identify catalog-level information needs; keep candidate term choices as optional hints |
| `construction_domain` | Interpret construction asset/use-case context without generalizing examples into universal rules |
| `aas_idta` | Interpret AAS structures and identifiers using source-resolved facts |
| `ifc_bim` | Interpret IFC entity/property context and distinguish instance facts from schema obligations |
| `dataspace_interoperability` | Identify exchange/discovery interoperability needs supported by corpus/tasks |
| `publisher_feasibility` | Surface evidenced availability and maintenance constraints, not silently weaken obligations |
| `consumer_discovery` | Elicit discovery needs tied to user tasks and competency questions |
| `stewardship_governance` | Identify accountability, stewardship and lifecycle needs |
| `access_rights_policy` | Identify access, licensing and rights needs with explicit applicability |
| `fair_quality_provenance` | Identify quality/provenance needs; explain FAIR annotations rather than treating FAIR labels as evidence |
| `minimality_scope` | Identify scope boundaries and unnecessary detail while preserving supported minority needs |

`consolidation_conflict` proposes equivalence/merge/conflict relations. `grounding_scope_critic` assesses semantic support, atomicity, scope and obligation after deterministic checks. `reuse_minimality_critic` flags premature solution choices and redundant requirements. `post_evaluation_revision` remains restricted to recorded review-driven revisions. The deterministic source verifier is software, not an additional opinion agent.

Preserve existing full-panel and pilot configurations as named experimental conditions. Role-specific background/RAG remains analytical context unless its source is explicitly registered in the evidence corpus. Record retrieved item IDs/hashes and the exact evidence shown; context-window truncation is a coverage limitation and must be visible.

### 11.2 Proposed module boundaries

Place these under `requirement-reuse-service/requirement_reuse_service/`; filenames below are new proposals:

| Module | Contract |
| --- | --- |
| `sources.py` and `evidence/adapters/` | `register_source`, `freeze_corpus`, `decompose`, `resolve_selector`; return diagnostics and immutable artifacts |
| `normalization.py` | Convert observations into revisioned records; split with lineage; keep hints separate |
| `verification.py` | Deterministic source/selector/content checks; never call an LLM |
| `qualification.py` | Combine semantic and quality assessments into explicit eligibility decisions |
| `conflicts.py` | Typed pair/group relations, scope comparison and conflict disposition |
| `deliberation/policy.py` | Pure, reproducible trigger and participant selection over a snapshot |
| `deliberation/engine.py` | Bounded calls through existing `llm/client.py`; persist messages and validated proposals |
| `adjudication.py` | Revision-bound human decisions, edit/split/merge commands and optimistic concurrency |
| `baselines.py` | Enforce publication gates, build dependency closure, serialize versioned handoff |
| `storage/` | Transactional repositories for immutable artifacts, events, jobs and snapshots |

Keep `service.py` as a compatibility facade while extracting these responsibilities. Reuse `agents/orchestrator.py` for stage dependencies and run records, `agents/context.py` for context boundary enforcement, and `evaluation.py` for the formal expert-review process. Avoid circular imports between adapters, orchestration and legacy service functions.

## 12. APIs and UI

### 12.1 Current APIs to preserve

The prefix is `/api/requirements`. Existing POST routes include `/analyze-artifacts`, `/analyze`, `/extract-requirements`, `/export-rq1-dataset`, `/freeze-evaluation-package`, `/validate-review-submission`, `/aggregate-expert-reviews`, `/revise-after-evaluation`, `/finalize-consensus`, `/save-requirement-set`, `/list-requirement-sets` and `/load-requirement-set`; `/health` is GET.

The existing `/export-rq1-dataset` reruns extraction from an `AnalysisRequest`; it does not export unsaved browser edits. Preserve and label that behavior. Add an explicit export-by-saved-run route for reviewed state.

### 12.2 Proposed persistent API surface

Use `/api/rq1/v2` for the new contracts. These routes are not present today.

| Method and route | Request/result |
| --- | --- |
| `POST /sources` | Upload/register artifact; return source/version/hash and parsing job |
| `POST /corpora/{id}/snapshots` | Freeze selected source/task versions and inclusion policy |
| `POST /runs` | Snapshot ID, strategy, roles, model/prompt/config versions, budgets; return `202` and run ID |
| `GET /runs/{id}` | Stage, progress, failed roles, coverage/truncation and artifact references |
| `POST /runs/{id}/resume` | Explicit failed stage/role selection; preserve prior attempt and outputs |
| `POST /runs/{id}/cancel` | Cancel further work; retain completed artifacts |
| `GET /evidence/{id}` | Unit, source selector, display context and resolver results |
| `GET /requirements/{id}/revisions` | Immutable revisions and lineage |
| `POST /requirements/{id}/revisions` | Proposed edit with parent revision/hash; queue revalidation |
| `POST /requirements/{id}/verify` | Verify specified revision; return job/report reference |
| `POST /runs/{id}/deliberations` | Selected case/trigger or human question; return case ID |
| `GET /deliberations/{id}` | Context, messages, budgets, proposed resolution and dissent |
| `POST /deliberations/{id}/messages` | Human contribution with citations; no implicit acceptance |
| `POST /decisions` | Accept/reject/defer/edit/split/merge against exact revisions; transactional result |
| `POST /baselines` | Selected accepted revisions and study package; gate validation then immutable manifest |
| `GET /baselines/{id}/export` | Exact saved baseline plus dependency manifest, without rerunning extraction |
| `GET /runs/{id}/export` | Saved machine/review state with explicit dataset kind and unresolved items |

Mutations carry idempotency keys and expected revision/hash; use `409` for stale edits, `422` for invalid transitions/citations, `404` for unknown artifacts. A repeat idempotency key with different payload is an error. Long-running work uses durable jobs; polling or server events may report progress without holding an extraction HTTP request open. Human actor identity must come from the deployment's trusted session or explicit local single-user identity configuration, not an arbitrary model-supplied field.

### 12.3 Workbench changes

Extend existing components in `frontend/src/components/requirements/` and the API client rather than replacing the application:

- **Source/evidence browser:** source version/hash, authority/source role, parse diagnostics, included/excluded regions, typed locator and original-content navigation. Display generated annotations separately from quoted or resolved facts.
- **Stage view:** nine-stage status plus counts, partial failures and retry state. Keep `AgentProcessGraph` as a process trace and add an actual deliberation thread view; do not label the extraction graph a debate.
- **Candidate inspector:** statement, type, scope, modality, inference rationale, evidence per claim component, verification methods and quality findings. Show “Source resolved,” “Support assessed” and “Human accepted” as separate statuses.
- **Contribution view:** retain `AgentContributionView` and raw role proposals; reveal exact shared/retrieved context and dissent. Make it possible to compare pre-normalization and canonical revisions.
- **Consolidation/conflict view:** side-by-side alternatives, highlighted scope/obligation differences, evidence union and missing premises; merge preview must show what will change.
- **Discussion view:** why selected, participants, bounded rounds, citation links, proposed edits, stop reason and unresolved issues. “Apply proposal” creates a revision; it does not approve it.
- **Human queue:** sort by blocking issues and study-defined impact; support accept/reject/edit/split/merge/defer with rationale and visible eligibility failures. Optimistic-concurrency conflicts must preserve the user's unsaved text.
- **Evaluation/baseline view:** extend `EvaluationWorkflowPanel`; separate frozen machine package, independent ratings, post-review revisions and final baseline. Show export version and unresolved appendix.
- **Persistence:** save run/review state server-side after successful commands, restore after reload, show saved/unsaved/error state. Reviewer drafts may remain local but must not masquerade as complete backup.

## 13. Persistence, provenance and migration

For the local research workbench, an initial SQLite transactional store plus content-addressed artifact files is sufficient; keep a repository interface so storage can change later. This is a proposed choice, not an existing dependency. Do not use the agent cache as the authoritative database.

Persist source bytes/versions, corpus manifests, evidence, observations, requirement revisions, verification/qualification reports, role runs, consolidation/conflict records, discussion messages, human decisions, evaluation packages, baselines and jobs. A command's domain event and updated read model must commit atomically. Use unique event sequences, foreign keys and expected-version checks. Durable job attempts need leases/attempt IDs so restart cannot duplicate a decision or overwrite a completed stage.

For every generated artifact, record input hashes, output hash, producing activity, actor/role, timestamps, code commit, workflow/schema version, parser/version, model/provider configuration, prompt/template hash, context/retrieval hash and generation parameters when available. Store bounded structured rationales and observable model outputs, not claims about inaccessible internal reasoning. Record token usage, latency, retries and errors. Do not persist credentials in prompts, exports or run configuration.

A baseline's provenance closure must allow traversal:

```text
baseline -> accepted revision -> human decision -> qualification/verification
         -> normalized/merged/revised parents -> independent observations
         -> evidence units -> immutable source versions
```

The closure includes counterevidence, exclusions and resolved conflict decisions. Hashes detect changed content; they do not alone make storage immutable or establish source authority. Enforce immutability in write APIs and back up the database and blob store together.

Migration rules:

1. Preserve legacy v1 exports and existing IDs. Add a mapping table from legacy IDs to v2 artifacts; never claim reconstructed provenance was originally recorded.
2. Import current `CandidateRequirement` into `RequirementRecord` revisions; keep raw and normalized statements, contributions, review state and nonbinding hints. Mark absent source snapshots or unresolvable locators `unverifiable`.
3. Register original sources if available, redecompose, and explicitly link newly verified evidence. A filename/hash inferred from display text cannot replace original bytes.
4. Keep `status` and `validation_status` as compatibility projections; new code uses orthogonal state/report fields. Do not map legacy `valid` directly to qualified or validated.
5. Keep the existing full-panel workflow version runnable; introduce a new workflow version for the nine-stage pipeline. Cache keys include corpus/representation hashes, model and prompt settings, role/context configuration, parser, schema and workflow versions. Cache hits point to their producing activity.
6. Export a new v2 dataset/baseline format for changed semantics. Provide explicit v1 conversion only where information loss is reported. Do not mutate frozen v1 evaluation packages.

## 14. Evaluation hooks and research design

Extend existing funnel metrics, task coverage, expert-rating aggregation and evaluation scripts. Persist stage snapshots so downstream human revisions cannot inflate the quality attributed to machine extraction.

| Layer | Measurements and cautions |
| --- | --- |
| Corpus/decomposition | Parse success by format, excluded/truncated regions, source-resolution success, evidence coverage on annotated fixtures |
| Elicitation | Unique supported needs per perspective, overlap and marginal coverage, failed-role rate; zero output differs from failure |
| Normalization | Atomicity/type/scope agreement against expert labels; meaning drift and unsupported added obligations |
| Grounding | Per-link and per-material-claim success; false pass/false fail on tampered source, locator and quote fixtures |
| Semantic support | Expert-rated support precision; unsupported/contradicted claim rate; explicit versus inferred classification agreement |
| Consolidation | False merges, missed equivalents, retained conflicts, lineage completeness and source diversity rather than agent vote counts |
| Deliberation | Trigger precision/recall on annotated issues, resolution quality, harmful revisions, remaining dissent, cost/latency and proportion skipped |
| Human review | Acceptance/rejection/revision rates, missing-requirement proposals, time per decision and inter-reviewer agreement |
| Baseline | Traceability closure, task coverage, unresolved/excluded counts and accepted-revision reproducibility |

Use matched corpus/task snapshots to compare rules, single LLM, existing multi-agent workflow, and the proposed workflow. Useful ablations: no deliberation, all-candidate deliberation versus selective deliberation, single perspective versus multiple perspectives, and removal of semantic qualification. Keep deterministic provenance safeguards in production; any experimental bypass is offline and visibly labelled.

Use held-out expert reference requirements, semantic matching with adjudicated equivalence, and predeclared precision/recall criteria. Open-ended elicitation rarely has a demonstrably complete gold set; report recall relative to the reference set, reference incompleteness and expert-added needs. Task-link presence alone is not successful competency-question coverage: experts must assess whether the linked requirement actually supports the task.

Freeze corpus, prompts, role selection, policies and thresholds before summative evaluation. Run repeated model trials and report variance; deterministic artifact replay is distinct from reproducing stochastic model output. Report machine, post-deliberation and human-validated results separately, along with token cost, latency and reviewer effort. Do not tune on summative ratings.

## 15. Implementation phases and acceptance criteria

Each phase is independently reviewable. Production rollout should not require implementing every structured source adapter before a text-first end-to-end path works.

### Phase 0 — Freeze contracts and preserve baselines

Scope: capture current workflow version and fixture outputs; document v1/v2 compatibility; define models and migration policy in `models.py`, the LinkML schema and TypeScript contracts.

Acceptance:

- Existing API routes and v1 fixtures retain their documented meanings.
- Unknown scope/obligation remains explicit; RQ2 hints can be omitted without failing RQ1 validation.
- Every new enum and transition has a defined actor and failure outcome.

### Phase 1 — Durable sources and text evidence

Scope: source registry, corpus snapshots, blob storage, text/table/task decomposition, selector resolver, persistent run skeleton and evidence browser.

Acceptance:

- Same source snapshot and parser configuration produce identical evidence IDs.
- Same filename with changed bytes produces a new source version.
- Every unit resolves to its source representation; repeated quotes, whitespace changes, Unicode offsets and changed hashes are covered by fixtures.
- Text without recognized keywords is retained or explicitly excluded; ingestion/truncation counts reconcile.
- Restart restores source/run state and partial failures without losing completed output.

### Phase 2 — Independent elicitation, normalization and qualification

Scope: preserve role isolation, observations, atomic records, deterministic verification and structured support/quality reports.

Acceptance:

- A spy/mock client proves extractor inputs contain no peer candidates; role context and shown evidence are recorded.
- A compound statement yields separately traceable children; scope and obligation are not silently strengthened.
- A fabricated quote, missing ID or invalid material premise blocks acceptance even if other evidence resolves.
- A real but irrelevant quote passes resolution and fails support qualification.
- A failed role is reported as incomplete, including pilot runs; its absence is not represented as successful zero output.
- Agent caches cannot reuse results across changed source/parser/prompt/context versions.

### Phase 3 — Structured evidence adapters

Scope: AAS JSON first, then XML/AASX, RDF datasets and IFC property/relationship traversal. Introduce format capabilities explicitly rather than falling back to text while claiming equivalent support.

Acceptance:

- AAS JSON Pointer escaping, repeated `idShort`, array changes and wrong value types are tested.
- Standalone XML and AASX entry selectors resolve; wrong entry hash, duplicate entries and malformed packages fail clearly.
- RDF fixtures cover named graphs, typed/language literals, blank nodes, reordered serialization and absent quads.
- IFC fixtures cover GlobalId and STEP-only entities, instance/type properties, units and broken relationships.
- Generated display summaries are never labelled verbatim source quotations.

### Phase 4 — Consolidation and conflict preservation

Scope: extend consolidation events, conflict records and comparison UI; rerun qualification on canonical revisions.

Acceptance:

- Every input candidate has a retained output/lineage or explicit exclusion disposition.
- Near-identical statements with different obligations or conditions remain distinct until a reasoned decision.
- `flag_conflict` retains all alternatives and counterevidence.
- A merge that introduces unsupported wording fails requalification; source/support labels are not inherited by confidence.

### Phase 5 — Selective deliberation

Scope: trigger policy, case store, participant selection, bounded RQ1 adapter and threaded UI.

Acceptance:

- Trigger fixtures produce reproducible selected/skipped/repair routes and reason codes.
- Grounding failures enter evidence repair, while supported conflicting interpretations enter discussion.
- Round/token/time limits, cancellation, provider failure and restart are tested; transcript and stop reason survive.
- Invalid citations/actions cannot mutate requirements. Agent agreement cannot accept a requirement.
- Dissent remains visible; any proposed edit creates a new revision and re-enters verification.

### Phase 6 — Human adjudication and RQ2 handoff

Scope: durable decisions, concurrency control, full session restore, strengthened consensus checks and baseline publication.

Acceptance:

- Accept/reject/edit/split/merge/defer are revision-bound and auditable; stale concurrent decisions return a conflict.
- Edited and split/merged requirements cannot inherit acceptance without rechecking and an explicit human decision.
- A baseline rejects unresolved blocking findings, invalid material evidence and inconsistent accepted alternatives.
- Export/import preserves exact accepted revisions, sources, decisions and lineage; the baseline hash is stable for the same canonical payload.
- Reload restores the complete saved review session; export-by-ID never reruns extraction or discards saved decisions.
- RQ2 receives accepted requirements with optional hints, plus a clearly separate unresolved/rejected appendix; no profile artifact is generated as an RQ1 acceptance side effect.

### Phase 7 — Evaluation and study freeze

Scope: instrumentation, curated multi-format fixtures, comparative scripts, formative tuning and frozen summative configuration.

Acceptance:

- All metrics identify denominators, stage snapshot, condition and missing data.
- Held-out expert ratings/reference sets never enter extraction prompts or pre-evaluation deliberation.
- A comparison report separates machine output, deliberation changes and human revisions and includes cost/latency.
- Research success thresholds are agreed before summative runs; this guide does not invent empirical performance claims.

Use the existing `tests/test_llm_extraction.py`, `test_multi_agent_extraction.py`, `test_expert_evaluation.py`, `test_requirement_reuse_service.py`, `test_rq1_export.py` and `test_standalone_api.py` as regression anchors. Add focused adapter/state/provenance tests as the corresponding functionality is implemented. For runtime implementation phases, run the repository's documented Python suite and frontend build; documentation-only changes do not require model calls or a running application.

## 16. First end-to-end implementation slice

Start with one frozen text source and one stakeholder competency question. Persist addressable evidence, collect two isolated perspective outputs, normalize them, run exact-source verification and semantic qualification, retain one deliberate conflict, discuss that conflict within budget, obtain a human decision and export a traceable baseline. Include a fabricated quote and a genuine-but-irrelevant quote as negative cases.

This slice establishes the key invariant before expanding format coverage: every accepted requirement can be traced through its final wording, human decision, assessments and derivation to immutable source evidence, while disagreement and rejected alternatives remain inspectable.
