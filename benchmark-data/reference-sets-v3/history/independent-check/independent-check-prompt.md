# Independent check of the merged atoms: subagent prompt (22 October 2026)

A fresh Claude subagent checked the merged atoms against the reference documents. Its findings and how each was resolved are in `../../INDEPENDENT-CHECK.md`.

## Independent check of merged reference atoms

Started 2026-10-22T18:57:25.027Z (UTC). Prompt, verbatim:

```text
You are reviewing a benchmark reference set for a research paper on extracting requirements for DCAT application profiles. Someone else built it; your job is an independent, skeptical source check. Do NOT edit any existing file. Write your findings to /home/claude/merge/verify/findings.md (create the folder) and reply with a short summary (counts plus the most serious issues).

## What exists
Merged reference files (schema "rq1-reference-set-3"), one per case. Each has `requirements` (rows) and `atoms` (the scoring units; each atom has `parent_id`, `statement`, `stratum` content/profile/system, `status_in_source`, `modality`, `relation_to_base`, `restates_dcat_ap`, `anchor_quote`, `source_locator`, `overlaps`, `source_flags`, `provenance`):
- /home/claude/merge/out/v3/healthdcat/reference-requirements/curated-requirements-v3.json (source: HealthData@EU D6.2; text at /home/claude/analysis/d62-raw.txt and /home/claude/analysis/d6.2-requirements-and-profile.txt; DCAT-AP base 3.0.0)
- /home/claude/merge/out/v3/statdcat/reference-requirements/requirements-and-resolutions-v3.json (source: StatDCAT-AP 1.0.0; text /home/claude/analysis/stat-final.txt, stat-raw.txt; base DCAT-AP 1.1)
- /home/claude/merge/out/v3/geodcat/reference-requirements/alignment-requirements-v3.json (source: GeoDCAT-AP 1.0; text /home/claude/analysis/geo-final.txt, geo-raw.txt; base DCAT-AP 1.1; Annex I Table 5 has columns INSPIRE obligation, ISO 19115 core obligation, DCAT-AP, GeoDCAT-AP)
- /home/claude/merge/out/v3/jrc-research/reference-requirements/core-requirements-v3.json (source: web paper https://www.w3.org/2016/11/sdsvoc/SDSVoc16_paper_27 — not available locally; you may use WebFetch on that URL)
- /home/claude/merge/out/v3/mobilitydcat/reference-requirements/consolidated-requirements-v3.json (99 clause atoms decomposed from 40 paraphrased rows; the original NAPCORE report is not available — only check internal consistency: does each row's set of atoms cover the row statement without adding or losing content?)
DCAT-AP base obligations per version: /home/claude/jundahuang9123/profile-requirements-extraction/requirement-reuse-service/config/base_profiles/dcat-ap-{1.1.0,2.0.1,3.0.0}.json (classes -> properties -> obligation).
The earlier audit the merge drew on: /home/claude/pr45/benchmark-data/reference-audit-2026-10-22/expansion-candidates.json (items referenced in atoms' provenance.pr45_ids).

Definitions used by the set: `relation_to_base` restates_base = an existing DCAT-AP term of the case's base version already serves the need and the source does not change its obligation; tightens_base = existing term, obligation raised or values constrained; extends_base = existing term used in a new way or on a new class; beyond_base = needs a new or imported term/class/code list; partly_base = partly covered; not_term_level = profile/system requirement. `restates_dcat_ap` is true exactly when relation_to_base is restates_base, and will be used to filter atoms out of scoring, so false positives and false negatives there matter.

## Check these atoms
1. Every atom whose provenance.found_by is "PR #45 only" or "added in merge", every atom whose provenance.pr45_ids has 2+ items, and every row with a `changed_in_v3`, `statement_before_v3` or `source_locator_before_v3` field.
2. Every atom with relation_to_base = restates_base (all cases), and every Health/Stat/Geo/JRC content atom with relation tightens_base or beyond_base whose term is obvious from the source (spot-check at least 25 of these).
3. A random sample of 30 further atoms across Health, Stat, Geo and JRC (use a fixed seed and list which IDs you sampled).
4. Within each case: pairs of atoms that state the same need but are neither merged nor linked in `overlaps` (likely double counting under one-to-one matching).
5. Mobility: for each of the 40 rows, whether its atoms together match the row statement.

For each checked atom: is the statement faithful to the source passage (actor, information, obligation, condition, scope — nothing added or dropped)? Does the anchor_quote actually support it? Are status_in_source/modality plausible (requirement vs proposed vs deferred vs open_issue vs guidance)? Is relation_to_base right against the base version's obligations?

## Output
findings.md: a table of issues (atom/row ID, problem type, evidence with a short source quote and location, suggested fix, severity high/medium/low), then a list of everything you checked that was fine (IDs only), then sample IDs. Be concrete; do not report style preferences. If something is ambiguous in the source, say so rather than forcing a verdict.
```
