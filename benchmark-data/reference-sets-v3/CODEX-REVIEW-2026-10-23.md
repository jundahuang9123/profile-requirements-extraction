# PR #45 — provisional adjudication, 23 October 2026

**Reviewed head:** `8e81e5b373c7f9e8a80693dba71a5804d3429281` on `codex/benchmark-reference-audit`.

**Recommendation:** retain the merged v3 as a substantially improved review corpus, but revise the issues below before freezing a quantitative scoring reference. This is assistant source review, not independent human adjudication. The review was performed read-only. This report was subsequently committed at the user’s request; benchmark data and scoring remain unchanged.

## Review coverage and verification

The PR now replaces the original audit with five merged case sets: 188 rows and 317 atoms, of which 195 are selected by default. The inventory comprises 75 v1 rows, 109 v2 additions and four v3 rows. I inspected the complete atom-statement inventory, methodology, merge rules, independent-check report, overlap relationships and provenance/coverage ledger; I examined selected full atom records and original source passages for the findings below. This is not a claim that every atom's semantic correctness has been independently adjudicated.

- All 256 original Codex review items (157 candidates plus 99 Mobility clauses) occur in the coverage ledger; no missing or unexpected original item IDs were found. Ledger targets resolve to atoms.
- The supplied validator passes with Poppler available: **202 local reference anchor quotes and 1,311 input-evidence quotes verified**, no errors. There are separately 114 live-Web anchors not verified locally and one locator-only anchor. Exact-text occurrence does not establish entailment, correct attribution or completeness.
- All evidence-source paths examined programmatically belong to their case's allowlist for the stated raw/consolidation mode. No evidence-path leakage was found.
- The temporary checkout remained clean. Changes versus the base are confined to benchmark documentation/reference files. No extraction execution or application changes were needed for this review.
- The v2 additions are identifiable through v3's row IDs and provenance. I did not obtain a separately frozen original v2 artifact and therefore do not certify byte-for-byte preservation of the independent v2 set.

## Findings

### P1 — Overlap links do not remove duplicate scoring targets

[Mobility Req-19.7](https://github.com/jundahuang9123/profile-requirements-extraction/blob/8e81e5b373c7f9e8a80693dba71a5804d3429281/benchmark-data/reference-sets-v3/mobilitydcat.json#L7044) and [Req-24.1](https://github.com/jundahuang9123/profile-requirements-extraction/blob/8e81e5b373c7f9e8a80693dba71a5804d3429281/benchmark-data/reference-sets-v3/mobilitydcat.json#L8240) both describe payload location/georeferencing methods. They share CMC-11 evidence and the same intended profile property, are linked as overlapping, and both remain default-scored.

The rule that one prediction cannot match both prevents duplicate credit; it does not remove the duplicate denominator. A single correct statement of the shared need still has two possible targets and can recover only one. A duplicate-heavy output could instead supply two predictions. Single parentage does not solve semantic duplication across parents.

**Provisional decision: merge the shared need into a canonical scoring unit with both published row IDs retained as provenance.** If service applicability is a distinct additional need, isolate that residual instead of scoring the shared dataset clause twice. Review the other overlap pairs as equivalence, subsumption or merely related; do not merge all overlaps indiscriminately. For example, dataset model identity and model version can remain distinct, while an umbrella description must not compete with all its component needs. Recompute denominators only after this adjudication.

### P1 — Some “supported” labels overstate the evidence for the full requirement

[H-1.1](https://github.com/jundahuang9123/profile-requirements-extraction/blob/8e81e5b373c7f9e8a80693dba71a5804d3429281/benchmark-data/reference-sets-v3/healthdcat.json#L1855) is a mandatory persistent, dereferenceable identifier for every metadata record. Its cited raw evidence recommends global identifiers and includes a DCAT-AP dataset identifier with cardinality 0..n. This supports identifier practice, but does not establish the full mandatory record-level obligation.

[H-29.1](https://github.com/jundahuang9123/profile-requirements-extraction/blob/8e81e5b373c7f9e8a80693dba71a5804d3429281/benchmark-data/reference-sets-v3/healthdcat.json#L6464) requires every record in an access-body catalogue to carry HEAL. Its raw evidence includes an M6.1 query selecting HEAL records and DCAT-AP's controlled vocabulary rule. A query that finds HEAL-labelled datasets does not establish a requirement to assign HEAL to every catalogue record. The universal requirement is explicit in the evaluator reference, D6.2 §5.3.1.3, physical page 74, which is not an allowed raw input.

**Provisional decision: retain both reference requirements, but downgrade these raw labels to partial pending a stronger input passage.** H-22.1 has a similar scope jump: assigning access-body competence in the inputs is related to, but does not explicitly require, an HDAB metadata field for every personal/non-public dataset. Its raw label also merits partial rather than supported unless an additional passage supplies that metadata obligation.

A reasonable inference may be useful elicitation evidence, but it should be distinguished from full support for actor, scope, modality and conditions. Do not publish the current supported-only denominator as independently established. If modality is intentionally ignored, define that alternative metric consistently across cases rather than silently discarding Health obligations while retaining them in the atoms.

### P2 — Some scored “atoms” are still compound, and lose the quality-label context

[H-46.1](https://github.com/jundahuang9123/profile-requirements-extraction/blob/8e81e5b373c7f9e8a80693dba71a5804d3429281/benchmark-data/reference-sets-v3/healthdcat.json#L8350) combines population representativeness and average duration of a person's appearance in the data. [H-46.3](https://github.com/jundahuang9123/profile-requirements-extraction/blob/8e81e5b373c7f9e8a80693dba71a5804d3429281/benchmark-data/reference-sets-v3/healthdcat.json#L8487) combines collection-to-inclusion delay and approval-to-delivery delay. These can independently be satisfied or missed.

D6.2 §5.2.8, physical page 60, places them in the contents of a data quality and utility label, where applicable. The records' applicability is empty; H-46.3 omits that qualifier altogether. The staged historical EHDS proposal also distinguishes label duties and the publicly funded cohort; these conditions are not interchangeable with an unconditional requirement on every catalogue record.

**Provisional decision: split each pair before freezing the atomic reference, preserve quality-label context and applicability, and reassess evidence for each child.** Keep H-46 as the source row. This is a source-fidelity/atomisation change, not a new current-law interpretation.

### P2 — The merger drops metadata-quality assessment from JRC coverage

[JRC-10.1](https://github.com/jundahuang9123/profile-requirements-extraction/blob/8e81e5b373c7f9e8a80693dba71a5804d3429281/benchmark-data/reference-sets-v3/jrc-research.json#L1210) concerns dataset quality and JRC-10.2 concerns feedback on data. Original audit item JC-006 explicitly included metadata quality; both mappings are present, but that meaning is absent from the resulting statements. JRC-10.1 also has no anchor quote.

The author's [paper, “Additional requirements”](https://www.w3.org/2016/11/sdsvoc/SDSVoc16_paper_27), explicitly includes metadata in the quality-assessment scope. **Provisional decision: restore a separate metadata-quality capability or an explicit scope-preserving representation, retain its under-investigation status, and add the source anchor.** This demonstrates why complete ID mapping is not complete semantic coverage.

## Compact adjudication register

| Item | Decision | Reason / boundary |
|---|---|---|
| H-3.1 | Accept source correction | D6.2 §5.2.1.3 p32 supports holder actor, annual cadence and accuracy/currency; raw support remains a separate assessment. |
| H-3.2 | Retain as proposed/conditional | Exchanged review date is an option; an internal solution is also discussed. |
| H-10.1 | Accept locator correction | Explicit variable-selection passage is §5.2.6 pp43–44, before §5.2.6.1. |
| H-37.2 | Accept recovered content | D6.2 §5.3.1.3 p75 explicitly lists unique-individual count. |
| H-40.1 | Accept conditional form | Applicability correctly limits the deletion/retention need to datasets with a deletion deadline; avoid reading its statement alone as universal. |
| H-1.1, H-29.1 | Revise evidence labels | Full mandatory/universal obligations are not established by the cited raw passages; provisional partial. |
| H-22.1 | Revise/recheck evidence label | Access-body competence does not alone establish per-dataset metadata obligation; source cardinality conflict remains open. |
| H-46.1, H-46.3 | Split and qualify | Independent information needs plus quality-label context and applicability. |
| Req-19.7 / Req-24.1 | Merge shared need for scoring | Preserve both parent rows; isolate service-specific residual only if independently justified. |
| Req-28.4 / Req-30.1 | Retain distinction provisionally | Model identity and precise model version can be independently useful; overlap alone is not equivalence. |
| JRC-8.2 | Accept restored capability | Source explicitly requires interface/query-parameter descriptions; preserve distinction from the unsettled implementation. |
| JRC-6.4 | Revise status to conditional requirement | DataCite's DOI rule is stated explicitly; uncertainty concerns broader identifier modelling, not that conditional rule itself. |
| JRC-10.1 / JC-006 | Restore omitted scope | Metadata-quality assessment is not preserved by dataset-quality and data-feedback atoms alone. |
| Geo M/C/O scoring choice | Leave unresolved as a declared scope choice | Do not infer acceptance or reverse the recorded decision. Keep need-level scoring distinct from obligation-sensitive scoring and preserve conditions in source fields. |
| H-9.1 / H-13.4 | Unresolved source tension | Mandatory dictionary, conditional wording and redacted fallback must not be flattened into one unconditional need. |
| Deferred Stat S-19.1–S-21.1 | Accept exclusion from default scoring | Preserves future-work status. |
| EPOS | Keep excluded | No recovered upstream elicitation gold was supplied by this merge. |

## Reporting and release boundaries

The default 195 includes 50 proposed/open-issue/guidance atoms: 38 Health, four Stat and eight JRC. This is disclosed, so it is not a hidden implementation defect, but primary results should name the selected status population and report a settled-requirement sensitivity analysis. Do not describe all 195 as agreed requirements.

The README discloses prior exposure of Health, Stat and JRC outputs. Health therefore cannot simultaneously be claimed as an untouched held-out test. The original methodology's Health-held-out wording needs to be reconciled in the paper/evaluation plan. Geo's overlap with Mobility inputs also remains a threat requiring disclosure.

The validator verifies quote occurrence but does not prove support labels. It also does not currently enforce input allowlist membership or validate the completeness/semantics of coverage-ledger mappings; this review checked the actual paths and IDs separately. A fail-closed scoring-release check would distinguish “structurally valid” from “approved for quantitative evaluation.” No such changes were made here.

Final disposition: **accept the expanded collection as a review corpus; request the four targeted corrections above before a scoring freeze.** No final revised denominator or full-set human adjudication is claimed.
