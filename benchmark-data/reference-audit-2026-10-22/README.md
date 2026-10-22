# Benchmark reference completeness audit — 22 October 2026

The existing reference collection is **not a complete atomic benchmark**. This audit preserves its 75 reference identities and supplies a substantially broader, evaluator-only review package: **157 expansion/refinement candidates** and **99 draft Mobility clauses covering all 40 existing Mobility rows**. These are review items, not 256 new distinct requirements and not a scoring denominator.

The shared repository was inspected read-only. This package can be compared with Claude's work without overwriting it. No extraction runs, prompts, runtime allowlists, legacy references, or evaluation results were changed.

## What was found and prepared

| Case | Existing references | This package | Interpretation |
|---|---:|---:|---|
| Mobility | 40 | 99 draft clauses | Every existing parent row represented; decomposed from the local curator paraphrases, not independently re-transcribed from the report. |
| Health | 16 | 95 candidates | Expanded across D6.2 §§5.2 and 5.3: discovery facets, metadata management, access routing, dictionaries, rights and conditional minimum metadata. |
| Geo | 7 | 37 candidates | Content inventory covering all 34 rows of Annex I Table 5, with dates and reference systems split. Preserves mandatory/conditional/optional distinctions and partial representation. |
| Stat | 7 | 14 refinements/principles | Retains §7.2 needs; makes format independence, quality-annotation content and time-series components explicit; separates architectural principles. |
| JRC | 5 | 11 supplementary candidates | Separates additional identifier, role, service-access and research issues from the five numbered core needs. |
| EPOS | 0 scored | No invented reference set | Remains exploratory; its final profile is insufficient evidence of original elicitation requirements. |

Counts are deliberately not added to the old reference counts. Many candidates refine or overlap legacy rows, and architecture, governance, UI and access-workflow requirements need separate scope decisions.

## Concrete corrections and qualifications

- Health H-5 omits trusted-data-holder status from the explicit facet list. Its single compound row also hides separately testable population and coding facets.
- Health H-3 loses the holder actor and annual review cadence. An exchanged review-date property is a conditional design option; an internal review record is also discussed.
- Health H-10's explicit variable-selection passage is in §5.2.6, physical pages 43–44, before §5.2.6.1.
- Health's sample/dictionary wording varies between mandatory and conditional/recommended language. The IPR passage introduces a redacted-dictionary fallback. This disagreement must be adjudicated, not normalised away.
- Health §5.3 adds access routing, contacts, population descriptions, record and individual counts, temporal resolution, retention and metadata survival requirements absent or underspecified in the original 16 rows.
- The Health source itself contains apparent copy/paste errors: the personal-data rationale repeats publisher text, and publisher type/note wording is inconsistent. Geographic applicability is explicitly questioned. Candidate presence does not resolve those defects.
- Geo's seven legacy rows are architectural constraints. They cannot stand in for the individual content needs in Annex I. The source supports only temporal extent within a broader extent row, free-text spatial resolution, frequency-only maintenance information, and conformance-result-only logical consistency.
- Stat's S-7 combines start, end and periodicity. Its source status is representation guidance; it must not silently become three newly published stakeholder requirements.
- JRC core needs and supplementary/open research issues remain separate. The live paper reports modification on 5 December 2016, while local citation metadata uses November 2016. Its citation-file hash does not freeze the paper's text.

## Package contents

Files in this evaluator-only directory:

- `legacy-row-review.json`: all 75 original identities and statements, review actions, and candidate cross-references.
- `expansion-candidates.json`: 157 candidates with source URLs, physical PDF page locators, applicability, modality, class and parent IDs.
- `mobility-clause-draft.json`: 99 parent-linked clauses; original importance levels preserved. Qualifier and actor fidelity still needs original-report review.
- `review-queue.csv`: the 157 candidates in a portable review table.
- `snapshot.json`: repository commit, source and legacy-file hashes, runtime-allowlist hash, counts and provenance.
- `COVERAGE-AND-RELEASE.md`: audited scope, remaining gaps and acceptance criteria.
- `validate_audit.py` and `VALIDATION.json`: reproducible integrity checks for this package.
- `BASELINE-VALIDATION.json`: the existing repository validator's separate result; it failed before any repository edits.

## Validation and limits

The package checks pass for unique IDs, all legacy identities, parent relationships, source hashes, unchanged allowlist, page bounds, CSV/JSON agreement and disabled scoring. Source PDFs were text-extracted, and selected Geo/Health tables were rendered and visually inspected to check column alignment and qualifiers. This is a single-assistant source review, not independent human adjudication or exhaustive visual review of all pages.

The existing repository validator checked 95 registered artifacts and reported no registered-file hash mismatch, but returned 30 errors: 26 character-level errors caused by treating `base_profile` strings as file lists; three false reference-leakage classifications from treating `background` as consolidation; and one genuinely unregistered `mobilitydcat/use-cases.json`. These need a separate targeted fix: recognise configuration keys, validate background as raw-input references, and explicitly classify/register the use-case file. Do not suppress all unknown keys or unregistered-file errors.

This audit does **not** establish that every candidate is supported by the actual raw/consolidation inputs. Those labels remain unassessed. It also does not reconstruct unavailable interviews, original source versions, licensed ISO documents, private expert evidence or EPOS elicitation. Full completeness cannot honestly be certified from the recovered public corpus.

## Use alongside the parallel review

Compare candidate IDs and source passages with Claude's findings. Record agreement, disagreement, omissions and proposed merges. Another AI review is useful corroboration but does not satisfy the repository's independent human-review requirement by itself.

Keep this directory evaluator-only. Do not import it into extraction retrieval or prompts. Reconcile overlaps, preserve modality and applicability, annotate available-input evidence, and freeze a separately versioned atomic reference before measuring recovery. Report full-reference and evidence-eligible recall separately.

This directory does not replace legacy gold or change counts used by existing software. From the repository root, run `python3 benchmark-data/reference-audit-2026-10-22/validate_audit.py --corpus benchmark-data` to detect source drift and validate the package.

## Source attribution

Health: [HealthData@EU Pilot, Deliverable D6.2](https://zenodo.org/records/15085025), retained locally under the deposit's CC BY 4.0 licence. This package contains modified factual paraphrases, not an endorsement by the authors. Exact artifact attribution, URLs and licence metadata accompany the source snapshot.

Geo and Stat: the frozen European Commission GeoDCAT-AP v1.0 (23 December 2015) and StatDCAT-AP v1.0 (15 December 2016) reports in the repository; exact original URLs and source hashes are in `snapshot.json`.

JRC: [Perego, Friis-Christensen, Vaccari and Tsinaraki, Using DCAT-AP for research data](https://www.w3.org/2016/11/sdsvoc/SDSVoc16_paper_27), checked live on 22 October 2026. Mobility: existing local 40-row curator representation of [Bureš, Lubrich and colleagues, NAPCORE requirements analysis](https://napcore.eu/wp-content/uploads/2022/08/NAPCORE-4.4.2.1-Requirement-analysis_v1.0.pdf). The original Mobility report was consulted for context and spot checks; the 99-clause draft remains explicitly derived from the local paraphrase.
