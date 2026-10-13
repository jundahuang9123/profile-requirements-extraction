# Reprocessing and consolidation

Use **Re-run steps 4–7 with new settings** on a fully completed extraction to create a separate downstream trial. It copies the frozen observations, stakeholder panel, completed role reports and referenced excerpt catalogues. Acquisition through extraction remain completed. The original run and its review decisions are unchanged; the new trial has no extraction calls and inherits the original extraction policy version.

The derive endpoint requires the source's current version, completed extraction and all role reports completed; automatic/override panels must also be completed. Active workers and incomplete extraction are refused. Derived trials can resume downstream checkpoints but cannot reset extraction.

Identical content hashes reuse assessments only under `rq1-support-quality-v2.2`, with the matching revision hash. Provider-failed, old-policy and human assessments are not imported. Original-source verification always runs again. Metrics distinguish reused extraction and assessments from newly incurred calls. Human review and baseline publication remain explicit human actions.

This implementation is offline-tested only. No new live inference or consolidation-quality evaluation has been performed.

## Uncited observations

New and derived runs use `rq1-normalization-v2`. Observations with no evidence links stay in the original observation audit and are indexed by `set_aside_observations` with reason `no_source_link`. They generate no candidate, verification, assessment, discussion or review item. Step 4 lists their text, role and extractor support label. A reviewer may use the existing add-requirement editor to create an evidenced need. Context-only or contradicting links still produce a candidate; the strict source gate determines its lane.

Historical runs with no normalization policy keep their legacy behavior on load and resume. The extraction prompt is unchanged. Metrics and frozen machine exports include the count and role/support-label distributions of proposals set aside.

## Consolidation settings and versions

New agent and mock runs default to **Merge candidates with the same meaning** (`rq1-semantic-consolidation-v1`). **Exact copies only** (`rq1-exact-consolidation-v1`) preserves the earlier condition for comparison. Rules runs always use exact consolidation. A historical run without a consolidation policy retains exact behavior even when loaded by the new software. Settings do not rewrite previous trials.

Semantic mode blocks records by resource type and the first non-stopword in `metadata_need`, stripping a final plural `s` from words longer than four characters. If no word remains, the first recognized vocabulary term supplies its local name; otherwise the head is `misc`. Vocabulary matching recognizes DCAT, DCT/DCTERMS, FOAF, VCARD, ADMS, SKOS, PROV, ODRL, SPDX, LOCN, DQV, mobilityDCAT-AP and related prefixes. This can miss equivalent needs whose first words differ; it is a bounded grouping condition, not a proven equivalence classifier.

Within a block, revision IDs give a deterministic order. Each model payload contains at most 40 candidates and 24,000 characters, including previously formed groups offered for joining. It contains statements and typed intent, scope and assumptions, never evidence text. Later chunks offer the current medoid representative of each earlier group. A singleton block requires no grouping call. If earlier groups or an individual record make the payload too large, that chunk falls back visibly to exact consolidation; candidates are not dropped.

The model returns only candidate IDs, optional existing group IDs and a short rationale. Each candidate must appear exactly once; unknown IDs, repeated IDs and repeated joins are refused. Positive and explicitly negated statements cannot share a group. Initial output is capped at 4,000 response tokens, with one 8,000-token retry for schema errors or truncation. A schema-valid accounting failure permits one correction at 8,000 tokens. Persistent invalid output causes an audited `semantic_grouping_unavailable` fallback for that chunk. Transport/authentication failures stop the stage for Resume, without a silent provider change.

## Building review items

For each group, the server builds separate mandatory, recommended, optional and unknown variants. Two or more passing members become one record whose wording, intent, scope, assumptions and rationale are copied from a member. The representative maximizes average word overlap; ties use the lowest revision ID. Passing evidence links, tasks, original observation IDs and contributing roles are preserved as unions, and parent revision IDs record the merge. Verification runs again and a new assessment runs once unless an identical current-policy assessment is available.

Failed members of a variant with passing members remain listed as `attached_failed`. Their evidence is never added to a passing record. With one passing member, its record is kept. With no passing members, multiple members become one blocked record with their failed provenance retained. Even if combining complementary links could satisfy the structural checks, it stays blocked until explicit evidence repair. A singleton stays unchanged apart from its group annotation.

All original members and active variants share a `group_id`. Multiple obligation variants create one conflict containing every variant, rather than pairwise conflicts. Between different groups of the same block, only potential negation contradictions are added; cross-block lexical conflicts retain their earlier behavior. Routing, discussion prompts, human acceptance and the reviewer's split action remain unchanged. Grouping does not validate or accept a requirement.

Mock semantic runs use a deterministic grouping key (case/modal/punctuation/prefix normalization, with matching typed fields and scope) and no grouping model call. This tests mechanics and is not semantic evaluation.

## Checkpoints, metrics and review

`consolidation_chunks` stores each input fingerprint, offered groups, model output or fallback, validation issues, call IDs and checkpoint hash as a separate run part. Resume validates and reuses finished chunks. Completed merged assessments are checkpointed before later blocks can fail; these are reused results, never new grouping inputs. Derived runs verify their frozen extraction and assessment-cache hashes before processing.

Step 4 lists uncited observations separately. Step 6 shows input counts, active review items, groups, variants, source-check outcomes and fallback counts. Step 8 shows one card per active record, with original members, failed attachments and links to obligation conflicts. Full/stage exports retain all original observations and lineage; the full audit also includes chunk checkpoints and recorded grouping outputs.

The metrics endpoint reports set-aside counts by role and extractor label; grouping calls, failures and summed latency; merged groups, attached failed duplicates, obligation conflicts and reused merged assessments. Assessment reuse from extraction is reported separately. Call latency sums are not necessarily wall time; token caps are not measured usage.

## Acceptance check still required

No live comparison was started for this implementation. On the saved Mobility run, create a **new** downstream trial with semantic consolidation, **Only when a reviewer asks**, and assessment reuse enabled. Supply the KI:connect key through the provider panel. Do not Resume the completed original run.

Compare the original and derived exports for normalized/active counts, set-aside count, passing source checks, conflicts, grouping/fallback calls, new/reused assessments and stage wall time. The original trial had 2,670 normalized observations, including 1,051 without links; a derived trial should set those 1,051 aside while preserving them in its audit. These are expected input counts, not a new execution result. Inspect the publisher family and at least 20 randomly sampled merged groups for distinct constraints accidentally grouped together.

For a paper claim, independently annotate duplicate groups in a stratified sample of blocks with two annotators. Report pairwise precision/recall and annotator agreement, adjudicate disagreements, and check whether merging hides reference-matching candidates. Until then, reduced review-item counts alone do not establish accuracy or human-effort savings.
