# RQ1 benchmark methodology

## Objective and unit of analysis

Evaluate whether the workflow elicits evidence-supported, implementation-neutral
metadata requirements and consolidates equivalent candidates while preserving
provenance, alternatives and conflicts. The output under evaluation is a requirement
record, not a vocabulary property, ontology, LinkML schema or SHACL shape. Finished
profiles provide a secondary requirement-to-design traceability check only.

Use “published reference set” rather than unqualified “ground truth”. The mobility
reference preserves all 40 published rows, including compound statements; JRC preserves
its five numbered core needs. Health, Stat and Geo JSON files are scoped curator
representations. They must be checked against the cited passages and independently
adjudicated before quantitative scoring. Their counts must not be reported as the
number of all requirements in those profiles.

## Two separate experiments

**Raw elicitation (A → C).** Supply only eligible `input-raw/` documents from the case's
`raw` allowlist. Run acquisition, decomposition, independent elicitation, normalization,
grounding, consolidation and review under a frozen configuration. Freeze machine output
before human revision; score it separately from the human-adjudicated result.

**Consolidation (B → C).** Supply only the `consolidation` allowlist, containing preserved
candidate rows or clearly labelled curator summaries of published preconsolidation
material. Do not also supply A by default. If a grounded consolidation variant needs
A to verify B's citations, define and report that as a separate experimental condition.
Mobility's 60 labelled annex rows preserve duplicates. Health's eight observations are
a partial synopsis, not the original survey-response corpus; its condition should be
called “curated TWG-observation consolidation”.

These modes answer different questions. B already contains human elicitation and may
use wording similar to C; success on B does not establish raw-evidence extraction
performance. Report verbatim-original and curator-synopsis conditions separately if
original rights-cleared candidates are obtained later.

## Leakage prevention

`runtime-inputs.json` is an explicit document allowlist. Reference files, READMEs,
methodology, provenance manifests, URL records, review annotations and final target
specifications are evaluator-only. They must not be available through retrieval tools,
shared workspaces, prompt context, embeddings, browser history or agent memory during a
run. A directory boundary alone is not an access control: stage only the selected files
in an isolated run workspace and restrict retrieval there.

Mixed documents require section-level review. The complete NAPCORE report contains its
40-row answer table and is not a raw input. Its annex facts are represented separately.
Full Health TWG minutes contain decisions and a final draft: keep them in provenance;
only the scoped needs/discussion synopsis is allowlisted. The September 2024 functional
analysis follows profile development and is provenance-only. The Stat report includes
both use cases and solutions: a separate retrospective §5 synopsis is provided but is
disabled in the strict raw allowlist. It can be enabled only as a named retrospective
variant; it must never be called recovered original pre-profile evidence.

A previously published *different* profile can be legitimate historical input. Mobility's
prior GeoDCAT 1.0.1 is documented by the literature review and is allowed for that case;
GeoDCAT's own final specification is excluded from its raw experiment. Avoid cross-case
contamination through tuning, cached retrieval or reuse of held-out reference sets.

A publication-access restriction cannot cure pretrained-model contamination: models may
have encountered public profiles during training. Record model/version and discuss this
threat; run grounding checks, source ablations and baselines rather than claiming an
unseen public reference is guaranteed absent from model training.

## Version freezing and historical eligibility

Freeze the local bytes and SHA-256, original URL, exact version, manuscript date,
archival-publication date when different, retrieval date, and immutable repository
commit when available. Null dates mean unknown; a review/upload date is not a source
publication date. Do not replace unavailable historical artifacts with “latest”. A new
source/version changes the corpus and requires a new manifest snapshot and a rerun.

The principal reference dates are mobility's 2022 requirements report, Health's
2024-09-30 D6.2, Stat's 2016-12-15 v1.0.0, Geo's 2015-12-23 v1.0, and JRC's November
2016 workshop paper. EPOS is pinned to its v1.0.0 tag commit; an exact original publication
date was not independently established.

Several sources need special care:

- NAPCORE's cover says 2022-06-14; its final-version history says 2022-06-20. Keep both.
  Do not use M2.7 (August 2024), which postdates the original requirements exercise.
- NAPCORE reviewed the **2020 DGA proposal**, not the subsequently enacted version.
- Health M6.1 is dated 2023-03-30 and M6.2 2024-01-31, although their public deposits are
  from March 2025. The recorded TWG sessions occurred in 2023. D6.2 uses the 2024 EHDS
  compromise with provisional article numbering; the adopted 2025 regulation is context
  only. Do not evaluate 2024 outputs as though they were derived from that adopted law.
- The available DCAT-AP 1.1 PDF has a 2017 metadata date despite 2015 footers. It is kept
  in provenance, not the earlier Geo/Stat/JRC runtime corpus.
- The official INSPIRE guideline landing page now supplies a 2023 revision rather than
  the 2017 version named in NAPCORE. That later document is not substituted. Public
  INSPIRE v1.3 (2013) is preserved; copyrighted ISO standards remain citation-only.

## Completeness, confidence and denominator selection

Every manifest's overall corpus status is **partial**. Record separately:

1. **Artifact availability:** original copy, metadata copy, citation only, curated
   paraphrase or retrospective reconstruction.
2. **Scope completeness:** artifact complete, all published table rows represented,
   scoped section complete, or partial. These are never interchangeable.
3. **Historical input evidence:** explicit project documentation (with passage),
   curator inference, or unknown. A source named in a final bibliography is evidence of
   consideration, not proof that every version or passage was used in elicitation.
4. **Curation confidence:** high/medium/low confidence in source identity and role;
   confidence is not a semantic-validity score.

Before evaluating, independently label each reference row with whether its meaning is
supported by the actual staged A or B corpus, unsupported by the available corpus, or
uncertain. Cite supporting source spans. Keep a full-reference recall denominator and a
separate available-evidence recall denominator; disclose all exclusions and counts.
Never quietly remove hard rows after inspecting predictions. Private experience,
interviews, unavailable versions and citation-only documents can explain unrecoverable
rows; do not invent surrogate testimony or count citation metadata as full evidence.

NAPCORE's body reports 53 individual requirements, whereas its published country annex
contains DE 17, BE 4, CY 1, CZ 5, IT 27 and GR 6 labelled rows (60 total). Preserve those
rows and their duplicate content rather than forcing the count to 53. The same report
mentions 50 reviewed resources and 18 summaries; the public annex exposes 17 named
numbered source groups after its methodology, not the private reference-folder contents.
This collection therefore does not claim to reconstruct all 50 original files.

## Semantic matching and atomicity

Freeze candidate and reference IDs before scoring. Reviewers compare the obligation,
entity, scope, constraints, rationale and evidence, not lexical overlap or shared property
names. Embedding or language-model matching may suggest pairs but does not decide
correctness. Use at least two independent reviewers for a sample or the full set, blind
them to system condition where feasible, record disagreements and adjudicate them.
Report agreement and the adjudication rule.

Represent matches as a bipartite mapping with reference IDs, predicted IDs, relation
(`equivalent`, `covers`, `partial`, `conflicts`, `unrelated`), evidence locators, decision
and reviewer rationale. Support:

- **1:1:** one equivalent prediction covers one reference requirement.
- **1:n:** several predictions jointly cover a compound reference row; a row is fully
  recovered only when every essential clause is supported. Partial coverage is separate.
- **n:1:** one prediction covers several reference rows; count each supported reference
  once, but record compoundness and score prediction validity once. Do not give extra
  precision credit for repeating the same meaning.

Keep row-level recovery and an independently defined atomic/clause-level analysis
separate. Establish any clause decomposition before viewing outputs. Preserve mandatory
versus optional distinctions and architectural versus content requirements. A correct
property name without the required meaning/evidence does not constitute recovery.

## Novel requirements and metrics

Classify unmatched predictions as supported-and-relevant novel requirements, unsupported,
out-of-scope, duplicates or unresolved. An absent published match is not automatically a
false positive. Have experts assess novel claims against raw source evidence and domain
scope; never add them to the reference retrospectively without publishing a new version.

Report full and evidence-eligible reference recall; supported/relevant prediction
precision (including separately reported valid novel requirements); evidence-resolution
rate and semantic grounding quality; duplicate detection and conflict preservation;
compoundness/fragmentation; and human edit/split/merge/reject effort. Unresolved cases
need an explicit denominator convention and sensitivity bounds. For consolidation, use
independently annotated duplicate groups and pairwise or cluster metrics; do not infer
clusters from final-row lexical similarity. Report case-level results and macro averages
without mixing exploratory cases into gold-recovery totals.

Compare a simple single-pass extraction baseline, the full workflow and justified
ablations under the same sources, model and budget. Record perspective contributions,
latency, token/cost budget, random seeds where supported, number of runs, failures and
uncertainty. Neither the corpus nor this document contains measured evaluation results.

## Train, development and held-out use

Use JRC and a predeclared part of Stat for debugging/development. Split by source and
requirement family, not random paraphrase rows: duplicates and statements from one
source must stay together. Use mobility as the main external evaluation. Reserve Health
and Geo as domain-held-out tests after prompts, perspectives, thresholds and budgets are
frozen. If their references have already influenced implementation, disclose that and
use a genuinely new held-out case/version rather than calling them untouched.

Source-overlap audit is essential: mobility's documented prior GeoDCAT 1.0.1 input
contains nearly the same alignment criteria as the GeoDCAT 1.0 target. If mobility is
used for training or iterative tuning with that input, Geo cannot be called an
independent held-out benchmark. Freeze the workflow before both evaluation runs, use
isolated run contexts, and reserve Health as the cleaner domain-held-out case. Report
shared baseline standards and prior-extension overlaps explicitly.

Do not fine-tune on held-out inputs/references, repeatedly adjust prompts after seeing
scores, or reuse held-out data for retrieval examples. Log every exposure. EPOS remains
exploratory until independent upstream inputs and a defensible reference set exist.

## Paper-ready evaluation setup draft

We evaluate RQ1 using a versioned collection of public evidence associated with six
DCAT application-profile initiatives. The benchmark distinguishes raw source documents,
preconsolidation observations or candidate requirements, and published reference
requirements. These layers support two experiments: elicitation from raw evidence and,
where material is preserved, consolidation of previously elicited candidates. The
published references are treated as project-derived baselines rather than exhaustive
ground truth. Finished application profiles are withheld from extraction and used only
for secondary traceability inspection.

MobilityDCAT provides the principal case because NAPCORE documents its literature,
partner-input and expert-consultation process and publishes a 40-row consolidation table.
The public annex contains 60 labelled partner rows, despite the body's count of 53; our
collection retains the published rows and documents the discrepancy. HealthDCAT provides
heterogeneous landscape, regulatory and stakeholder evidence, while StatDCAT and GeoDCAT
provide statistical and standards-alignment cases. JRC supplies a five-requirement sanity
case. EPOS is included for exploratory analysis and is excluded from quantitative
reference-recovery aggregation because its original elicitation corpus was not recovered.

Corpus reconstruction is necessarily partial. Every artifact records its authority,
version, acquisition date, role and availability, and distinguishes documented inputs
from curator-selected context. Licensed originals are retained where possible; restricted
or unlicensed material is represented by citations and explicitly labelled factual
synopses. References derived through curation undergo independent passage-level review
before scoring. Full-reference recovery is reported alongside recovery restricted to
requirements supported by the actually supplied evidence, with exclusions established
before predictions are inspected.

Matching assesses semantic obligations and evidence rather than word overlap. The
protocol supports one-to-one and split/merged mappings, records partial coverage, and
separately adjudicates supported novel requirements. Machine output is frozen before
human revision, allowing recovery, grounding and consolidation performance to be
reported separately from final accepted output and adjudication effort. Development uses
JRC and a predefined Stat subset; Health is reserved for held-out domain assessment,
while Geo is assessed after configuration freeze with its overlap with the mobility
inputs explicitly disclosed. Model pretraining on public
profile documents remains a validity threat and is disclosed alongside source access,
version uncertainty and incomplete stakeholder evidence.
