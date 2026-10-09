# mobilityDCAT / NAPCORE

Use the **2022 requirements exercise**, which initially called the proposed profile
napDCAT-AP. The main reference is [NAPCORE Requirements Analysis v1.0](https://napcore.eu/wp-content/uploads/2022/08/NAPCORE-4.4.2.1-Requirement-analysis_v1.0.pdf),
by Petr Bureš, Peter Lubrich and colleagues. The cover says June 14, 2022; the document
history says final release June 20. The official downloaded PDF has 57 physical pages
and contains the main report plus its annexes. The 2024 M2.7 report is not substituted.

## Available corpus

`input-raw/` contains original EU legal/policy texts, historical DCAT/DCAT-AP baselines,
public INSPIRE guidance, the FAIR report and cost study, NISO's noncommercial primer,
the licensed 2021 SPRINT paper, prior GeoDCAT, and factual synopses of CMC's 32 concepts
and SPRINT D2.3's 12 competency tasks. Those last two are explicitly **paraphrases**, not
original full documents. Their source versions predate the 2022 exercise.

`input-preconsolidation/` contains curator representations of all labelled Annex 1
partner rows, the named Annex 2 review-group observations, and a partial published
SEMIC/CMC/expert-observation synopsis. These are B inputs, never raw-evidence A inputs.
No final Table 1 IDs or answer mappings are supplied in B.

`reference-requirements/consolidated-requirements.json` preserves all **40** original
Table 1 IDs and their four types and mandatory/optional labels. Statements are curator
paraphrases, with compoundness preserved. There are 8 General, 5 Existing Vocabularies,
22 Content and 5 Implementation rows; 32 mandatory and 8 optional. Check wording and
scope against the original table before final annotation. The separately saved
mobilityDCAT-AP 1.0.0 ReSpec HTML is a later **final-profile reference**, not a runtime input;
it is source HTML with external resources, not a self-contained rendered publication.

## Count and reconstruction limitations

The report body states **53** partner requirements from six countries. The published
annex actually contains **60 labelled rows**: DE 17, BE 4, CY 1, CZ 5, IT 27, GR 6. DE-00
and DE-06 duplicate the same need; rows are not deduplicated during acquisition. Italy's
original Req-* IDs are country-qualified to avoid confusing them with final Table 1 IDs.
This discrepancy is preserved in `provenance/napcore-retrieval-audit.json`.

The report mentions 50 reviewed resources and 18 summaries. Annex 2 exposes 17 numbered
source groups after its methodology, not a complete copy of the private source folder.
The manifest inventories the named groups and unresolved variants; no claim is made that
all 50 resources were acquired. Exact national-profile versions, all training recordings,
LOD-RoadTran reports, the 2017 INSPIRE version, and private interviews remain gaps. One official SEMIC 2021 training deck is saved; it is
not claimed to reconstruct the full Academy webinar series. The served DCAT-AP 2.1.0
release-path PDF is also saved, with its internal draft-status metadata discrepancy
recorded in the manifest.

The original NAPCORE report, CMC and SPRINT D2.3 were readable during curation, but no
explicit full-document redistribution licence was established. They are citation-only;
curator factual summaries are supplied where feasible. Raw evaluation therefore measures
a **partial public reconstruction**. Consolidation is stronger in row coverage but still
uses paraphrases and incomplete expert/review context. Private testimony is not fabricated.

See [manifest](provenance/manifest.json), [gaps](provenance/GAPS.md),
[methodology](../BENCHMARK-METHODOLOGY.md), and [runtime allowlists](../runtime-inputs.json).
