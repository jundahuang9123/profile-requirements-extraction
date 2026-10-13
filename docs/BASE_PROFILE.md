# Extending an inherited DCAT-AP base

A domain profile starts with DCAT-AP's existing classes, properties and obligations.
The extraction workflow therefore looks for the additions or changes a domain needs:
new information needs, stricter obligations, added value/cardinality/usage constraints,
controlled vocabularies, and new classes or relations. Restating the base should not
create another requirement for a reviewer to accept.

This changes the experimental condition. Existing run results remain historical
results under their recorded policies. A new run uses the current extraction policy;
a separate derived run can apply the new normalization and base check to the saved
step 3b observations without making extraction calls. Its lineage identifies the
source run, saved extraction and changed downstream conditions.

## Policies and reproducible base data

The registry policy is `rq1-base-registry-v1`, the base-check policy is
`rq1-base-check-v1`, normalization uses `rq1-normalization-v3`, semantic grouping
uses `rq1-semantic-consolidation-v2`, and extension extraction uses
`rq1-independent-elicitation-v3.0`. Runs record the selected `base_profile_id`,
`base_registry_policy_version` and the SHA256 of the exact registry JSON bytes.
Saved stage results and the frozen
machine output retain the corresponding policy/base metadata. A derived run retains
its source extraction policy; applying the base check does not relabel old v2.11
extraction as v3. An unfinished v2.11 extraction cannot resume under v3.

The registry is built from the official
[SEMICeu/DCAT-AP repository at commit 4470b8ea907b7eb9ec55ab22befd1ecd2210ff32](https://github.com/SEMICeu/DCAT-AP/tree/4470b8ea907b7eb9ec55ab22befd1ecd2210ff32).
The checked-in registries are:

| Registry | SHA256 of JSON bytes | Recommendation source |
| --- | --- | --- |
| `requirement-reuse-service/config/base_profiles/dcat-ap-2.0.1.json` | `8714b33e415b4576e2bf9046ae66806555f376dffbeeff5e681eb9e0fda70180` | Official 2.0.1 DOCX class tables |
| `requirement-reuse-service/config/base_profiles/dcat-ap-2.1.1.json` | `928c2686f32183b7b6540b8a7d28d1f38bff47fa19e7281f64e2c6f731a912c0` | Official 2.1.1 recommended SHACL shapes |

Each contains 14 classes and 109 class/property entries. Entries hold obligation,
maximum cardinality, range, vocabulary and label/synonym data; union ranges or
multiple schemes use a list. These are a base comparison registry, not a complete
SHACL conformance validator.

Mandatory means `sh:minCount >= 1` in the main release shapes. Recommended means
membership of the 2.1.1 recommended shapes, or a recommended-properties section
in the 2.0.1 DOCX. Other members are optional. The main shapes determine membership,
mandatory status and maximum cardinality. Range/vocabulary supplements refine
existing entries. The DOCX also supplies available 2.0.1 range/label information.
Release RDF `rdfs:label` and SHACL `sh:name` labels are retained where available,
with the local name and the work plan's Appendix A synonyms. In particular, the
lexicon adds no standalone `category` synonym for `dcat:theme`.

Two 2.0.1 property typos are normalized: `http://data.europa.eu/r5ravailability`
becomes `dcatap:availability`, and `dct:licence` becomes `dct:license`.

### Pinned input hashes

Every input below is recorded with its full checksum in the JSON `source.files`.

| Release-relative file | SHA256 |
| --- | --- |
| `releases/2.0.1/dcat-ap_2.0.1_shacl_shapes.ttl` | `864501811f0e599500ba02fd2f15027a6b82728343af3bd8a273d141a6a089da` |
| `releases/2.0.1/DCAT_AP_2.0.1.docx` | `6d1e0db4eb1890fa373436bdc0da3f578c5b58f6cf4b5e447ce45f958a6e8d3f` |
| `releases/2.0.1/dcat-ap_2.0.1_shacl_mdr-vocabularies.shape.ttl` | `10d9194cf8db767ab0d0e99ae0b5c4f21542f0aa2a2066ff8e75a3f8cdda645d` |
| `releases/2.0.1/dcat-ap_2.0.1.rdf` | `d939611b553dde9b080ccdd33941c2161ddf47bd68ec09039d60145de8a8642a` |
| `releases/2.1.1/dcat-ap_2.1.1_shacl_shapes.ttl` | `467ace005196e261b9299422e921aba079c279a9e914e3a2d499e048cbc7cd0b` |
| `releases/2.1.1/dcat-ap_2.1.1_shacl_shapes_recommended.ttl` | `1b46e232e79d1d7875146b6f9b3722b0a53131b6810387bd653175e865f71742` |
| `releases/2.1.1/dcat-ap_2.1.1_shacl_range.ttl` | `36f01df2b8cd0f51bda7c12a64e16868430caebb39dabd998071795f99bfe353` |
| `releases/2.1.1/dcat-ap_2.1.1_shacl_mdr-vocabularies.shape.ttl` | `510cd30b2dd410cf5c2ea11b3c9e523ef07c2bf19036d48cb2d2ca64a6dc9a3b` |
| `releases/2.1.1/dcat-ap_2.1.1.rdf` | `1213214797a8a8c50a7e5240b470fe1cd6f97746b3698078e6bdaebbd4a69e61` |

### Building offline

Put the pinned release files in a local checkout/directory preserving their
`releases/<version>/` paths. With the repository's dependencies installed, run:

```sh
python scripts/build_base_profile.py --input-dir /absolute/path/to/pinned-DCAT-AP
```

The builder makes no downloads and does not follow RDF imports. It checks all
input hashes, parses RDF and the DOCX with `python-docx`, writes both JSONs, and
prints their entry counts, recommendation sources and output hashes. Use
`--profile dcat-ap-2.0.1` or `--output-dir /absolute/path/outside-the-repo` for a
single profile or a separate reproducibility comparison.

Both official registries rebuilt to byte-identical output. The 2.0.1 DOCX parse
succeeded; **no recommended-set fallback was taken**. A parse failure stops the
default build. An explicit `--allow-recommended-fallback` can instead use the
2.1.1 recommended set; its source hash, `recommended_source: "2.1.1"`, and
`fallback_note` record that changed condition. A checksum mismatch always stops
the build.

The usual phase checks are:

```sh
python -m pytest tests -q
python scripts/export_workflow_schema.py
cd frontend
npm run build
```

Registry tests cover pinned values, RDF cardinalities/ranges/vocabularies, DOCX
heading/table association and explanatory rows, the two normalized property
typos, unpinned input rejection, and explicit fallback accounting. Fixtures are
small and offline; tests never download release files or call a model.

### Source limits

The official MDR file's `DataService_ShapeCV` has an upstream Distribution target.
The builder follows expressed targets and does not silently reinterpret it or
add properties absent from the main shapes. IANA media-type/compression/package
restrictions that appear only in comments are not encoded as vocabulary values
in this registry. Missing registry constraints do not imply that the official
profile permits every value. Human review and the official specifications remain
necessary for conformance questions.

## Normalization: remove inherited restatements, retain extension claims

Step 4 first separates uncited observations and declarations of
`not_an_extension`, then runs the base check before source verification and
assessment. Source observations remain available in the audit; a set-aside row
is not silently deleted. Ordinary inherited rows need no verification/assessment
calls. Ambiguous mappings or an unrecognized declared constraint are retained
for review rather than being removed with confidence.

Class resolution recognizes Dataset, Distribution, DataService, Catalog,
CatalogRecord, Agent and Concept. It maps these to the corresponding DCAT,
FOAF or SKOS class. Unknown/unresolved classes stay visible for review.

Property resolution tries the declared v3 `base_property` first, then a prefixed
property in the statement, then the longest matching label in `metadata_need`
and finally the statement. Prefixes are case-insensitive; `dcterms:` aliases
`dct:`. Specific phrases such as endpoint description, access URL and version
notes precede description, URL and version. A declaration is checked against
the class/text and flagged for review if uncorroborated. A new vocabulary term
or unmatched information need remains `new`.

| Relation | Treatment |
| --- | --- |
| `inherited` | Matching base property with equal/unknown obligation and no added constraint: set aside with its base comparison when no review guard is present. An ordinary consumer/system ability to process/retrieve/interpret base metadata is inherited too. |
| `tightened` | Stronger obligation: retain only when at least one cited supporting evidence unit comes from outside the configured base specifications. Otherwise classify as inherited and record “stricter label not supported outside the base specification”. Missing base-source classification leaves that inheritance provisional for review. |
| `loosened` | Weaker obligation: retain with a blocking `conflicts_with_base` finding. A profile extension cannot relax its base. |
| `constrained` | Matching base property plus an added-constraint cue: retain. |
| `new` | No matching property of the resolved base class: retain. |
| `unresolved_class` | Class cannot be resolved: retain with a review finding. |

Obligation ranks are mandatory 3, recommended 2 and optional 1; `unknown` makes
no obligation claim. Added-constraint cues include named controlled vocabularies,
code/authority lists, cardinality, conditions and domain scope. Acronyms such as
`ITS`, `NAP` and `CRS` are case-sensitive so that `ITS` never matches “its”. A
generic scope such as Dataset or Unspecified does not add a domain constraint.

These labels describe a comparison claim, not proven requirements. In particular,
a lexical cue can misidentify a property or constraint, and a nonbase supporting
link can be semantically inadequate. Subsequent evidence verification/support
assessment and human review still apply to retained records. A v3
`value_constraint` declaration without a recognized cue is retained with an
`unconfirmed_extension_constraint` finding; a declared property unsupported by
the text gets `unconfirmed_base_property`. `requires_review` keeps such provisional
inherited labels from causing automatic exclusion.

The same preservation rule covers potentially compound statements and negation.
A statement with multiple property names, a conjunction or a semicolon may combine
an inherited clause with a new need; it gets a `compound_base_check` finding for
inspection/splitting. Negated wording gets `base_polarity_review` rather than being
discarded on the strength of a matching property. If the selected base has no
configured base-source classification, a stronger obligation gets
`unresolved_base_source_classification` and remains reviewable. These guarded
records can retain the provisional relation `inherited` while staying active.
Consequently, the count of inherited relation labels is not the actual number
set aside as inherited; metrics report those two counts separately.

The record's `base_check` carries the base profile, class, property, base/candidate
obligations, relation, resolution method and detected constraint signals. Set-aside
rows also carry their base check and reason: `no_source_link`,
`inherited_from_base` or `declared_not_extension`. Stage results, exports and the
machine snapshot retain these decisions. Semantic consolidation keeps distinct
obligation alternatives linked and uses source checks on retained evidence.

Semantic grouping v2 asks the model to compare statement text. Inconsistent
model-written `value_kind`, `scope` and `requirement_type` labels are omitted from
that grouping payload. Each later chunk offers at most the 25 previous groups with
the greatest word overlap, keeping the existing payload limits. Metadata-presence
requirements and consumer/system capabilities stay separate, and obligation labels
still form separate variants. Word overlap and the bounded offer set can miss
equivalent statements; group correctness remains a review question, with rejected
grouping/fallback recorded in the audit.

## Mobility defaults and base sources as background

Only `mobilitydcat` receives an automatic base selection in
`benchmark-data/runtime-inputs.json`: `dcat-ap-2.0.1`, matching the selected
mobilityDCAT-AP 1.0.0 reference's cited base. It is distinct from the versions of
some contextual PDFs in the input corpus.

The default background list is:

- `mobilitydcat/input-raw/w3c-dcat-2-2020.html`
- `mobilitydcat/input-raw/dcat-ap-2.0.0.pdf`
- `mobilitydcat/input-raw/dcat-ap-2.1.0.pdf`

When the benchmark loader is used with “Treat base specifications as background”
enabled, it registers new versions with `source_role: background` and freezes a
new snapshot. `freeze_snapshot()` excludes their units with
`background_not_evidence`. The files and source provenance remain available;
old source versions and snapshots are unchanged. A derived run from an older
snapshot instead recognizes those same configured base-specification basenames
for the obligation-support check; it does not silently change its input corpus.
Exports retain the excluded background sources in provenance separately from the
snapshot's extraction evidence; that export does not turn them back into evidence.

Only the configured base-specification names identify authoritative base sources
for the comparison. A generic document's `source_role: background` describes its
corpus treatment and does not establish that it is a base specification. Unknown
source identities likewise do not establish outside-base support for tightening.

INSPIRE, GeoDCAT-AP, FAIR, policy and mobility-specific sources remain evidence
by default. Other cases have no automatic base version or background list in this
change. Users must select appropriate versions and scope deliberately; an
available registry is not a decision to assign it to every case.

## Extraction v3 and payload limits

With a selected base, the role context includes the profile id/version and a
compact table such as `dcat:Dataset: dct:title (mandatory), dct:publisher
(recommended), …`. Base specifications are supplied as inherited context, and
extension proposals must cite at least one offered source excerpt. Each proposal
states `extension_kind` and, where applicable, a `base_property` such as
`dcat:Dataset/dct:publisher`. Allowed kinds are new information need, stricter
obligation, value constraint, new class/relation, and not an extension. The server
applies its own base check rather than accepting that label as proof.

The compact table counts toward the existing input bounds: at most four units
and 16,000 characters for a normal extraction batch, or 45,000 characters for
one large unit. The response cap is 8,000 tokens, with a bounded 12,000-token
single-unit retry. These are per-request limits; character sizing is not a
measurement of provider tokens or daily quota. The preflight estimate reserves
5,000 characters for role/task context plus the selected base context. Actual
selected roles can produce different batch counts.

Run the offline preflight with a fresh output directory outside the repository:

```sh
python scripts/preflight_benchmarks.py --output /absolute/path/outside-the-repo/preflight-after
```

It records parsed source provenance, excluded background units, source resolution,
base-table overhead and conservative batch counts. It never reads reference
answers or calls an LLM. `--keep-base-as-evidence` is an explicit comparison
condition rather than the benchmark default.

| Case | Evidence units before → after | Selector batches before → after | Extraction batches/role before → after | Background units excluded | Base context characters |
| --- | ---: | ---: | ---: | ---: | ---: |
| Mobility | 1,030 → 822 | 61 → 48 | 279 → 315 | 208 | 3,391 |
| Health | 511 → 511 | 36 → 36 | 158 → 156 | 0 | 0 |
| GeoDCAT | 271 → 271 | 19 → 19 | 81 → 80 | 0 | 0 |
| StatDCAT | 60 → 60 | 5 → 5 | 20 → 20 | 0 | 0 |
| JRC research | 59 → 59 | 3 → 3 | 15 → 15 | 0 | 0 |
| EPOS | unavailable → unavailable | unavailable → unavailable | unavailable → unavailable | 0 | 0 |

The comparison uses the completed offline before/after reports, parser
`rq1-adapters-v2.4`. Mobility removes 208 evidence units, but its compact base
context consumes 3,391 characters of each request's allowance. Its conservative
extraction estimate therefore rises to 315 batches per role despite the smaller
evidence set. That is a sizing result, not a measured runtime increase or decrease.

The new benchmark importer uses stable `benchmark-` source IDs; the earlier
preflight used `preflight-` IDs. Their evidence hashes differ, and snapshot sorting
changes the greedy batch boundaries. Health's 158 → 156 and GeoDCAT's 81 → 80
differences occur with the same evidence units and no selected base; they do not
demonstrate an optimization. Mobility changes both the input set and the context,
so this before/after comparison does not isolate a single causal runtime effect.
EPOS remains unavailable because it has no allowlisted raw corpus. Document
extraction limitations remain visible in the complete preflight reports.

## Metrics, user review and acceptance still to do

Step 4 lets reviewers filter set-aside observations by reason and inspect
inherited class/property/obligation comparisons. Retained cards display their
base relation and refined property; loosened obligations carry a blocking
conflict. Metrics count relations, resolution methods and inherited exclusions,
and describe retained candidates' evidence source groups: base only,
INSPIRE/GeoDCAT, other generic and mobility. Review-guarded inherited labels are
counted among relations, while actual `inherited_from_base` set-aside rows have a
separate count. Candidate counts must be interpreted
with source-check/support findings and coverage, not as distinct correct
requirements automatically obtained.

This change has offline validation only until Junda's acceptance runs. The next
checks are a derived Run A on saved Mobility extraction with semantic grouping,
base 2.0.1/check enabled and discussion on request; and a fresh Run B with new
background source versions, extraction v3 and automatic roles. Review at least
20 inherited exclusions and 20 retained records, noting misclassifications.
Check the base-only publisher, INSPIRE contact, Regulation 1205/2008 keyword and
spatial-quality examples described in the work plan. Record the run's actual
coverage, failures, policies, timing and costs before comparing outcomes. No
accuracy, effort-saving or end-to-end live-completion claim follows from the
offline tests or reduced candidate counts.

No live inference or visual UI check was performed for this change. The new UI's
available validation is the frontend build, and model-facing behavior is exercised
with offline fixtures/scripted clients. All 419 offline tests pass, the generated
schema matches runtime contracts, and the frontend builds.

Junda still needs to decide the mobility corpus/supportable reference coverage,
whether INSPIRE tightenings fall within scope, whether GeoDCAT-AP remains evidence,
and how to handle nonmetadata policy statements. Base/background choices for
HealthDCAT-AP, GeoDCAT-AP, StatDCAT-AP, JRC and EPOS are also open. StatDCAT's present
raw corpus contains only W3C DCAT and Data Cube specifications; excluding both
would leave no domain evidence. No relevance filter or broader corpus change is
implied by this base check.

## Delivery note

At the start of this plan, the previous work-plan changes were already committed
and pushed to `implement-rq1-workflow`. An additional Phase 0 pull request containing
those same changes would have no diff. The extension work is therefore based on
that pushed state on its separate `codex/extend-dcat-ap` branch; its pull request
records the actual delivery conditions.
