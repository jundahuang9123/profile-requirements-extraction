# Benchmark reference sets, version 3

Evaluator-only. Never stage these files with extraction inputs, prompts or retrieval.

Version 3 merges three sources into one reference set per case:

- the published v1 rows (75 identities, unchanged IDs);
- Claude's completion pass (v2, 22 October 2026: 109 added rows with verified source quotes);
- the ChatGPT/Codex completeness audit first proposed in this PR (commit 7fec154: 157 candidates and 99 Mobility clauses).

## Decisions

- Mobility is scored at clause level. The PR #45 clauses were checked against the original NAPCORE Table 1 (see below).
- Requirements that only restate DCAT-AP are included and flagged (`restates_dcat_ap`), so they can be left out at scoring time.
- Geo restatement tags stay as coded. INSPIRE and ISO obligation levels are kept as fields but are not part of each need, because requirements are scored on the need and implementations may differ later.

## Files

- `<case>.json`: the merged set for one case. `requirements` holds the rows (v1, v2 and four new v3 rows), for a separate row-level analysis. `atoms` holds the scoring units. Each atom belongs to exactly one row (`parent_id`); atom IDs are the row ID plus a number (`H-5.3`).
- `atoms-review.csv`: all atoms, with your_decision and your_note columns for review.
- `reference-coverage.csv`: the input-evidence labels per atom, in the columns of `../REFERENCE-COVERAGE-TEMPLATE.csv`.
- `coverage-ledger.csv`: where every v1 row, Claude v2 row and PR #45 item went.
- `counts.json`: counts per case.
- `INDEPENDENT-CHECK.md`: the independent source check and how each finding was resolved.
- `validate_v3.py`: integrity checks. With pdftotext installed it also re-checks every anchor against the reference PDF and every evidence quote against its input.

## Key atom fields

- `stratum`: content, profile or system.
- `status_in_source`: requirement, proposed, deferred, open_issue or guidance.
- `modality`: the source's own obligation wording where known. For Mobility this is the Table 1 importance and modal verb.
- `relation_to_base`: restates_base, tightens_base, extends_base, partly_base, beyond_base, not_term_level or unresolved, measured against the DCAT-AP version the case cites. `restates_dcat_ap` is true exactly when this is restates_base.
- `reuse_or_alignment_rule`: reuse and alignment rules (RQ2 scope).
- `derived_from`: where the reference document says the requirement comes from (for Mobility, the Source column of Table 1, with contributor and perspective on the row).
- `anchor_quote`, `anchor_check`, `anchor_page`: the reference passage. It is machine-checked for Health, Stat and Geo, with the PDF page where it starts. JRC and Mobility quotes come from the live documents via WebFetch.
- `input_evidence`: whether the case's staged runtime inputs support the atom, given separately for `raw` and, where the case has them, `consolidation` inputs. Each has a label (supported, partial, uncertain or unsupported), the input passages (path, locator, verbatim quote, `quote_check`) and a rationale.
- `overlaps`: atoms that state closely related needs. Under one-to-one matching, a prediction can be credited to only one of them.
- `source_flags`: source inconsistencies or errors, recorded but not resolved.
- `provenance`: the v1 row, Claude v2 rows and PR #45 items behind the atom, `added_in_merge`, and a `found_by` summary.

## Merge rules

- Rows: all v1 rows and all Claude v2 rows keep their IDs. A row statement, locator or status changes only where a source check showed it wrong; the earlier value is kept in statement_before_v3, source_locator_before_v3 or status_in_source_before_v3.
- Atoms are the scoring units and every atom belongs to exactly one row. PR #45 splits are used where PR #45 split a need; PR #45 items that state the same need for another data group are merged into one atom whose applicability lists the groups.
- Content found only in Claude v2 is split into atoms; content found only in PR #45 is added; a few needs found while checking anchors are added and marked added_in_merge.
- Requirements that only restate DCAT-AP (relation_to_base = restates_base) are kept and flagged with restates_dcat_ap so they can be left out at scoring time.
- Source inconsistencies and source errors are recorded on the atom (source_flags), not resolved.
- Overlapping atoms point to each other in overlaps; under one-to-one matching a prediction can be credited to only one of them.

## Counts

Default selection: content atoms that are not deferred (`scored_by_default`). Never score a row and its atoms together.

| Case | v1 rows | v3 rows | Atoms | Scored by default | Without DCAT-AP restatements |
|---|---:|---:|---:|---:|---:|
| Mobility | 40 | 40 | 98 | 40 | 33 |
| Health | 16 | 69 | 119 | 88 | 75 |
| Stat | 7 | 22 | 27 | 14 | 8 |
| Geo | 7 | 46 | 56 | 37 | 21 |
| JRC | 5 | 11 | 17 | 16 | 12 |
| **Total** | 75 | 188 | 317 | 195 | 149 |

## Input-evidence labels (evidence-eligible denominators)

Every atom is labelled against the case's runtime inputs (`../runtime-inputs.json`): raw inputs, and for Health and Mobility also the pre-consolidation inputs. A label counts only when at least one quote was found verbatim in the cited input.

The labellers were Claude subagents that saw only the atoms and the inputs, not the reference documents or the curation. They are AI labels and still need human review.

| Case | Scored by default | Raw: supported | Raw: supported or partial | Consolidation: supported | Consolidation: supported or partial |
|---|---:|---:|---:|---:|---:|
| Mobility | 40 | 32 | 38 | 39 | 40 |
| Health | 88 | 60 | 83 | 6 | 22 |
| Stat | 14 | 4 | 8 | – | – |
| Geo | 37 | 37 | 37 | – | – |
| JRC | 16 | 6 | 12 | – | – |

Report full-reference recall over all scored atoms, and evidence-eligible recall over the supported (or supported-or-partial) atoms of the input mode that was run.

## Mobility clauses checked against NAPCORE Table 1

The PR #45 clauses were decomposed from curator paraphrases. They were compared with the original Table 1 text, read from the NAPCORE report via WebFetch on 22 October 2026. Each row now carries `table1_text` (short exact excerpts), `table1_source`, `table1_contributor` and `table1_perspective`.

Changes:

- **Req-1:** three list items the paraphrase had dropped were restored: richness, adequate data description, easy data access. "Distinguish entity identities" has no counterpart in Table 1 and is folded into referential integrity. "Strong typing and ruling" is one item.
- **Req-17:** one timestamp ("last date and time when the metadata set was created or last modified") instead of two.
- **Req-32:** database, GUI and harvesting are examples of deployment rules, not three separate obligations.
- **Req-21.5 and Req-39.2:** keep their permissive wording ("could", "may").
- **Req-34:** controlled vocabularies are an example, not the requirement.
- **Wording:** several clauses were reworded to keep the Table 1 qualifiers (for example "where possible", "without proprietary licences", "Delegated Regulations").

Result: 98 clauses (99 in the PR #45 draft).

## Changes to existing rows

- **H-3:** statement corrected (data holders, annual review); status changed to requirement. The review-date property stays proposed (atom H-3.2).
- **H-10:** locator corrected to D6.2 §5.2.6 (pp. 43–44).
- **H-37:** adds the number of unique individuals.
- **JRC-8:** adds the description of the service interface with its query parameters.
- **G-30 and G-38:** drop clauses that are not in GeoDCAT-AP.
- Earlier values are kept in `statement_before_v3`, `source_locator_before_v3` and `status_in_source_before_v3`.

## New rows

- **H-66:** title, description and access URL, which DCAT-AP already requires.
- **H-67:** one format per distribution for protected (NSIP) data.
- **H-68:** frequency.
- **H-69:** a harmonised data validator (proposed).

H-66 to H-68 come from PR #45 items. H-69 was found while checking anchors, as was atom H-15.4 (a standardised quality description).

## Not done

- No independent human adjudication of the atoms or the evidence labels.
- JRC and Mobility quotes come from live documents that are not byte-frozen in the corpus.
- Health, Stat and JRC are development cases whose outputs had been viewed before this version. The decomposition was built from the source documents and the two completion passes, not from system outputs. Disclose the earlier exposure as the methodology requires.

## Verify

From the repository root:

```sh
python3 benchmark-data/reference-sets-v3/validate_v3.py
```
