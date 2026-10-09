# Paper figures: benchmark evidence and requirements

Two original vector figures derived from the frozen 7 October 2026 corpus. Figure
creation date: 8 October 2026. Both use the same labelled blue/green/ochre A/B/C
encoding; meaning does not depend on colour alone.

## Figure 1: benchmark evidence map

Use this figure in the evaluation or dataset subsection. It combines the two
experimental entry points with a six-case inventory of available evidence. All A/B
file counts come from `../runtime-inputs.json`; reference-entry counts come from the
curated inventories. A file may contain many observations, and counts across layers
are not equivalent units. This is an inventory, not a measure of extraction quality.

- [Vector PDF](01-benchmark-evidence-map.pdf): recommended for LaTeX or print.
- [Editable SVG](01-benchmark-evidence-map.svg): vector shapes and editable text.
- [PNG](01-benchmark-evidence-map.png): 300 dpi raster export.

**Suggested caption.** Evidence organisation and evaluation paths for the DCAT
extension benchmark corpus. (a) Raw-evidence runs start from layer A and execute the
full requirement-extraction workflow; consolidation runs start from layer B and
execute the later workflow stages. Each run produces a separate prediction set,
compared semantically against evaluator-only reference material in layer C.
(b) The reconstructed corpus spans six cases with different source availability
and reference scopes. Counts in A/B denote allowlisted files; counts in C denote
reference entries. All historical reconstructions are partial, curator paraphrases
require independent review, and EPOS is exploratory rather than a scored benchmark.

## Figure 2: mobilityDCAT content examples

Use this figure to explain the task to readers unfamiliar with metadata
requirements. The first two rows juxtapose actual corpus items on validity and
licensing. The lower panel illustrates two partner needs that could map to a
shared consolidated regulatory requirement. Dotted connectors are thematic,
non-causal correspondences chosen by the curator. They are not original-project
traceability links, model predictions, or independently adjudicated gold mappings.

- [Vector PDF](02-mobility-requirement-examples.pdf).
- [Editable SVG](02-mobility-requirement-examples.svg).
- [PNG](02-mobility-requirement-examples.png): 300 dpi raster export.

**Suggested caption.** Selected source and requirement examples from mobilityDCAT-AP.
Task and concept synopses from SPRINT and the Coordinated Metadata Catalogue (A)
are shown alongside partner requirement paraphrases from NAPCORE Annex 1 (B) and
consolidated requirement paraphrases from NAPCORE Table 1 (C). The examples concern
data validity, licensing and regulatory applicability. Dotted connectors indicate
illustrative semantic correspondence, including a potential many-to-one match;
they do not assert historical derivation or constitute adjudicated evaluation
labels. Italian partner IDs are country-qualified to distinguish them from the
final table's requirement IDs.

## Sources to cite in the manuscript

For Figure 1, cite the archived release/commit of the benchmark corpus once one
exists; this working copy has not been assigned an archival identifier. The
per-case provenance manifests contain the primary source citations.

For Figure 2, cite these primary sources (URLs and versions are recorded in the
existing corpus manifests; no new retrieval is implied):

1. NAPCORE (2022), *Requirements Analysis for a new Metadata Specification*,
   v1.0: Annex 1 (IT original rows Req-17/Req-21, BE-02 and GR-01), and Table 1
   (Req-22, Req-27 and Req-20; PDF pp. 15-19).
   [Original report](https://napcore.eu/wp-content/uploads/2022/08/NAPCORE-4.4.2.1-Requirement-analysis_v1.0.pdf).
2. SPRINT (2020), *D2.3 Requirements for an IF architectural design (F-REL)*,
   revision 3, PDF pp. 26-27, competency questions 9 and 11.
   [Original deliverable](https://projects.shift2rail.org/download.aspx?id=e74711aa-0c2c-4dc9-b5d3-16081145b2fd).
3. EU EIP (2019), *Coordinated Metadata Catalogue*, v2.0, section 2.2,
   validity beginning/end and licensing/use-conditions concepts.
   [Original catalogue](https://www.its-platform.eu/wp-content/uploads/ITS-Platform/AchievementsDocuments/NAP/EU%20EIP_Coord.%20Metadata%20Catalogue_v2.0_191115.pdf).

Local source representations: `../mobilitydcat/input-raw/sprint-competency-tasks.json`,
`../mobilitydcat/input-raw/cmc-2019-concept-inventory.json`,
`../mobilitydcat/input-preconsolidation/partner-requirements.json`, and
`../mobilitydcat/reference-requirements/consolidated-requirements.json`.
The drawings and short paraphrases are newly composed; no original document page
or screenshot is reproduced.

## Placement, editing and reproduction

Use full text width (typically a two-column figure), not a narrow single column.
Check text size against the venue's requirements after scaling. The PDF pages are
720 x 615 pt and 720 x 542 pt. SVG text can be edited in a vector graphics editor.
Keep the qualifications about partial coverage and illustrative links in the figure
or caption when adapting it. For publication layouts, the descriptive title and
small footer can be moved into the caption to save vertical space.

Rebuild PDF/SVG with Python and ReportLab:

```sh
python3 benchmark-data/figures/build_figures.py
```

Render each PDF to a 300 dpi PNG with Poppler:

```sh
pdftoppm -r 300 -singlefile -png benchmark-data/figures/01-benchmark-evidence-map.pdf benchmark-data/figures/01-benchmark-evidence-map
pdftoppm -r 300 -singlefile -png benchmark-data/figures/02-mobility-requirement-examples.pdf benchmark-data/figures/02-mobility-requirement-examples
```

`figure-data.json` records checked source counts and the status of illustrative
links. `figure-validation.json` records final file and PDF readability checks.
These figures are evaluator/manuscript material and must not be added to runtime
allowlists or model retrieval indexes.
