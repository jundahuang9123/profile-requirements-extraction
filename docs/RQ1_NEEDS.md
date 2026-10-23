# RQ1: a minimal, traceable list of needs

The needs workflow is the default for new agent runs and derived trials. It states
what people or systems need to know, find, judge or do. Choosing vocabulary terms,
classes, properties and modelling solutions belongs to RQ2.

A need names no RDF CURIE or class/property local name such as `accessURL` or
`DataService`. Ordinary words such as *dataset* and *title* are allowed. External
standards, regulations and code lists can remain when the source makes them binding.
The statement template is “[Actor] can [know/find/judge/do] [what] [for which
resource] [stated condition]”, for example “Users can identify the organisation
that publishes a dataset.” Use Users unless the members name a specific actor.
Never use the whole words must, shall or should in a need statement; obligation
lives only in its separate field. Unknown is shown as “not stated by sources”.

An **RQ2 hint** is a literally observed term, vocabulary, code list or modelling
element. Its origin is a proposal or authentic evidence quotation, with the original
evidence/revision IDs. The detector collects all `prefix:Local` spellings and camelCase
or PascalCase names in the selected base registry. Proposed hints absent from both
the statement and quoted evidence are not admitted; the provider response remains
in the call audit. Hints do not establish a correct mapping. Base-catalogue matches
are stored separately as `base_need_matches`, with catalogue provenance, because
calling them observed proposal/evidence hints would misrepresent their origin.

A **generic need** is fully served as stated by the selected base, without domain
meaning, condition or scope. A **domain use of the base** refines a base information
need with domain meaning, scope or conditions. The server checks that a claimed
refinement adds a word, condition, scope or stronger obligation the matched entries do
not state. Until `rq1-generic-domain-v3` it counted the scope placeholder `Unspecified`
of a need without a scope as such a word, so every need without a scope passed this
check; from `rq1-generic-domain-v4` the placeholder is ignored. A **domain need** is not covered by
an offered base need. These are machine judgements requiring review, not facts that
an optional base property is populated in every catalogue. A **use case** is a
competency question, user task, stakeholder need or cross-cutting goal declared
in the frozen snapshot.

## Processing order and saved pages

| Processing | Purpose and output | Saved UI view |
|---|---|---|
| Normalize | Preserve raw proposals; set uncited proposals aside | 4 · Normalized candidates |
| Base-source pre-filter | Set aside proposals supported only by configured base-specification sources | 4 · Normalized candidates |
| Original-source check | Resolve each candidate's exact source and every quotation; no model assessment | 5 · Original-source checks |
| Proposal support | Judge the information/capability against own exact excerpts, at most 25 proposals / 24,000 characters; retain only selected supporting quotes in needs | 6 · Grouped needs & scope |
| Group underlying needs | Same information/capability, resource and condition/scope; ignore typed labels, terms, wording, obligation strength and perspective | 6 · Grouped needs & scope |
| Write and check a need | Write every group, including singletons; independently check no added actor, obligation, scope or condition; move non-expressing members to singleton follow-ups | 6 · Grouped needs & scope |
| Classify against the base | Generic needs are visible asides; retain domain and domain use of base | 6 · Grouped needs & scope |
| Dataset kinds | Scan every frozen evidence unit for explicit kinds, retain exact source quotes and report unchecked units | 6 · Grouped needs & scope |
| Profile scope (D5) | Judge each need on dataset level, discovery contribution and representativeness; needs failing the first two are visible asides; the third labels kept needs common, specialised or for review; no need is added or rewritten | 6 · Grouped needs & scope |
| Scope and critic | Propose contributing use-case links with justifications and a necessity note; independently keep/drop each link on its contribution; set unlinked needs aside | 6 · Grouped needs & scope |
| Support assessment | One logical assessment per retained need against its union of source-checked excerpts | 6 · Grouped needs & scope |
| Rank | Order all retained needs deterministically; no cutoff hides needs | 6 · Grouped needs & scope |
| Families (D5) | Group kept needs that one catalogue element would serve; secondary review and comparison view | `needs.json` and the step download |
| Discuss on request | A reviewer opens a bounded case on a need; automatic discussion remains an explicit option | 7 · Discussion |
| Human review | Inspect, assess, accept/reject/defer, revise, split or merge; review/restore asides | 8 · Human review |
| Baseline | Publish accepted revisions only, with their traceability and unresolved appendix | 9 · Validated baseline |

Acquisition, decomposition, role selection and independent extraction remain pages
1–3b. Stepwise use pauses after saved UI stages; automatic mode traverses the same
stages for tests. The new processing substeps within page 6 have individual saved
outputs and resumable call checkpoints, but not a separate user pause after each
substep. Use “Download this step” for its full records and audit.

Content and consumer perspectives can express the same need: “metadata contains
the title” and “a consumer can read the title”. Different information, actor goals,
conditions, scopes and negations remain separate. A group's evidence is the union
of its passing members' selected supporting quotes. Other authentic quotes remain
on the original members for the audit; support is a separate model judgement. Source-failed and quote-unsupported proposals are visible asides with failed checks
or support rationales. They receive no writer, critic or rank and never enter a
passing group. Restoring one is unaccepted and requires evidence/support repair.

An obligation counts only with a passing obligation quote; missing quotes downgrade
the label to unknown and retain the claimed label as `unbacked_obligation`. Every
quote must still resolve exactly; candidate runs retain source-check v2.1.
If all members agree on quoted obligation, keep it. Otherwise use `unknown`, preserve the
counts and original revision IDs in `obligation_alternatives`, and use neutral
wording. The reviewer decides. Source authentication does not establish entailment;
the independent rewrite critic and support assessor are fallible model judgements.
A valid negative critic verdict is preserved. Only rejected groups get one new
writer request with that rationale. A changed rewrite gets its own critic check;
an identical rewrite reuses the negative verdict. Until `rq1-need-statement-v2`, a
group without a usable rewrite (writer output still invalid after its correction,
critic or F/A preservation check failed or unavailable, or rejected twice) was set
aside whole as `rewrite_rejected`: in Stat `run-6455e495` 26 groups (37 needs, every
Stat set-aside before the discussion), in JRC `run-a89957db` 11 groups (15 needs).
A failed rewrite says nothing about the needs, so `rq1-need-statement-v3` sets none
aside: a group goes back to the writer member by member, as members a written need
does not express already did (`split_unwritten_group`), and a single need keeps its
own normalised statement, flagged `rewrite_not_applied` (`keep_unwritten_need`).
Both events record the reason and the rejected rewrites. A kept need takes a
condition or scope only when it stands in its own statement, the rule a written need
follows; the extraction's scope label is not source-checked. A kept statement may
still hold vocabulary terms or obligation words the writer would have removed, so
acceptance asks a human to edit it first; the flag makes it visible for review.
Failed groups are retried in batch order, so a replay sends the same requests.

## Scope choices

The form offers automatic resolution, use-case scoping or off. Automatic resolution
uses `use_cases` if the frozen snapshot has tasks; otherwise it saves `off`.
Before each development run, Junda authors dated use cases from the stated purpose.
Scoping off is a separately reported comparison. If no tasks are supplied, the
software records scoping off rather than inventing any.
Benchmark import copies the case's declared tasks into the form; it does not invent
questions from example UI text.

With scoping on (`rq1-use-case-contribution-v1`), a linker links a need to each
declared use case it contributes to: catalogue metadata meeting the need helps answer
the competency question or carry out the task, for example by letting users find,
filter, identify, compare or judge suitable datasets. It explains the contribution in
one sentence and marks a link `necessary` only when the use case cannot be met without
the need. A separate critic rejudges every link on its contribution alone; it does not
see the necessity claim. Shared words, a contribution nobody names, or one the use case
does not support are rejected; a link need not be indispensable. Necessity is kept per
link as an annotation (`use_case_necessity`), never as a filter. The earlier policy
(`rq1-use-case-necessity-v1`) kept only indispensable links; in the functional Mobility
run it set aside 532 of 849 classified needs, useful ones included. Extraction task
links are hints only. With scoping off, all otherwise retained needs remain, and the
run makes no use-case claim. Source-failed
and unsupported proposals remain visible in their set-aside lists for repair.

## Profile scope (D5)

Decided by Junda on 16 Oct 2026. DCAT-AP 2.0.0 starts from the European
Commission's call for “a thin layer of commonly agreed metadata”, which “could
facilitate data cross-reference and interoperability and therefore considerably
enhance its value for reuse”, and says a common format for portals “would support the
sharing, discovery and re-use” of datasets. An application profile's purpose is that
users can find datasets and get access to them through catalogues (FAIR F and A).
Interoperability and reuse (I and R) are what such a profile delivers; they are not
tests of what belongs in it.

D5 is a rule for elicitation, applied to the needs the sources state. It never puts
a need into the list: every kept need still comes from source-checked proposals, and
a topic that no source raises (a licence, say) does not appear. The judge sees
each need's statement, condition, scope, supporting excerpts and the offered source-linked
dataset categories. It returns one verdict per offered need
ID and has no field for proposing, merging or rewriting a need; rows for IDs it was
not offered are ignored.

D5 follows the design principle agreed on 16 October; `rq1-profile-scope-v3` adds
source-backed category context to it. The
extension adds what makes the domain's datasets distinguishable, as a minimum set
that covers their different kinds. A need that matters for one kind of dataset is
**specialised**, not out of scope. The judgement has three criteria:

1. **Dataset-level relevance (C1, `catalogue_level`).** The need concerns what a
   record states about a catalogued resource as a whole. Since `rq1-profile-scope-v6`
   the judge names that resource (`record_resource`: catalogue, dataset, distribution,
   data service, another kind the profile catalogues such as a facility, equipment or
   software, or none) and what its record would state (`record_statement`, for example
   "dataset: the dimensions its observations use"; for another kind it starts with the
   kind, as in "facility: the instruments it hosts"). With no named resource the need
   fails C1: a catalogue record does not state rules about how people or organisations
   must act or how data must be processed, legal or administrative procedures, or facts
   about the source document itself. A resource's properties that concern such rules
   pass when a record can state them, such as the legal basis or purpose under which a
   dataset's personal data are processed, the categories of personal data it holds, or
   who may grant access. Describing a resource's structure (its dimensions, attributes,
   units or code lists) passes. It fails when it prescribes
   what the data must be or contain (content, structure, values, quality level, update
   interval, licence choice) or how the data is produced or delivered, or when it
   describes individual records, fields or values. Pointing to where such details are
   documented (a schema, specification or quality report) is catalogue level.
2. **Discovery contribution (C2, `serves`).** Met in catalogue records, it helps users
   find datasets (search, filter, browse, identify, compare, judge relevance, also
   across catalogues that harvest each other) or get access to them (distributions,
   formats, access addresses and services, the licence, rights or access conditions
   that apply, whom to contact). A distinction finer than users search, filter or
   decide on does not count. The judge gives one concrete `example` of the search,
   filter or access decision the need enables. A need stated from the publisher side
   counts by what users do with the information.
3. **Representativeness (C3).** `common` when the need recurs across the kinds of
   datasets the profile covers; `specialized` when it matters within an identifiable
   group of them; `single_case` when it concerns only one dataset, publisher or system,
   or fixes a choice that legitimately differs between datasets (one quality threshold
   for all); `uncertain` when the need as stated does not show which. How often a need
   was proposed is not evidence of how common it is.

Only C1 and C2 can set a need aside. C3 labels a kept need: `scope_class` is `common`,
`specialized` or `review` (single case or uncertain), for the later selection and for
the reviewer. Version 1 set aside needs that were not "commonly agreed"; an LLM cannot
know what a community agrees, and the test removed specialised needs. The fourth
test, the extension test, remains the generic/domain classification below
(`generic_need_served_by_base`).

Topics that come up often are judged like this. They are examples for judging stated
needs, not a checklist of needs to add:

| Topic | In scope | Out of scope |
|---|---|---|
| Licence | Knowing which licence, rights statement or access conditions apply: they decide on what terms users can obtain the data (access) | Using data once obtained (combining, redistributing); prescribing which licence the data must have |
| Quality | Seeing a dataset's quality information, for example that a quality report or conformance result exists and where | Fixing particular quality measures or thresholds for all datasets: quality is not one standard that fits all |
| Update frequency | Knowing, or filtering by, how often a dataset is updated | Requiring datasets to be updated at a given interval |

C1–C3 run as one batched judgement after classification and before use-case
scoping. A need failing C1 or C2 is set aside with the first failure as its reason
(`not_catalogue_level`, then `not_find_or_access`), the judge's rationale and both
results. It stays visible and restorable, as under D3; recall is reported with and
without these set-asides. Runs under version 1 can also show `not_commonly_agreed`. A
source-failed need is not judged and stays blocked. A need whose judgement is
unavailable after bounded recovery stays for review, flagged
`profile_scope_not_checked`. Dataset applicability now has cited evidence (`dataset_coverage`). A model's unsupported common/specialized claim is downgraded to uncertain. The judgement is stored on the need (`profile_scope`) and
bound by its integrity hash; a human edit clears it. The step records the counts of
each scope class; the export also reports category coverage and compact selection counts.

### Families: a secondary review view

After ranking, kept needs that one catalogue element would serve form a **family**:
they ask records for the same kind of information about the same kind of resource,
whatever the wording, actor, level of detail, condition or user task. Finding
datasets by the area they cover and seeing a dataset's bounding box are one family;
the area and the period a dataset covers are two. A family only groups existing
needs. It is headed by its best-ranked member, and no family text is written.
Source-failed needs stay outside families until repaired.

Families are ranked by their best member's support; then by distinct supporting
documents, contributing roles and kept use-case links across members, and member
count (descending); then head rank and head need ID. `needs.json` lists them under
`families`, from the frozen machine output; human edits, splits and merges do not
change them. The planned scorer uses atomic needs as its primary unit, with strict
relations (equivalent, narrower, broader, partial; see
`benchmark-data/BENCHMARK-METHODOLOGY.md`): one broad need cannot earn credit for
several specific reference rows. Only equivalence earns primary recovery credit. Broader, narrower and partial relations are reported separately. Families are a secondary view, for comparing
conditions at equal size (the same number of top-ranked families).

## Source-backed categories and compact coverage

`rq1-dataset-categories-v2` scans the frozen input corpus once, with durable per-batch
checkpoints. Each row names explicitly documented dataset kinds with verbatim labels,
quotes, offsets, evidence IDs and source names. Exact spelling variants are joined;
semantic synonyms are not guessed together. The complete registry is exported. Failed
rows receive at most one correction and remain visibly unchecked; provider failures
stop and resume unfinished batches. Large rows are not silently truncated. When no needs remain after classification, discovery is skipped without model calls. An empty
registry is a valid result, not permission to invent a taxonomy.

The separate applicability judge receives relevant category citations and the need's original supporting
excerpts, in bounded batches. Each applicability link requires an offered category ID,
an exact quote from the need's evidence, and a rationale. Quote validation establishes
provenance, not entailment; the applicability remains a machine proposal. At most 16
categories and 7,000 category-context characters are offered; omitted categories are
counted. A `common` label requires either explicit profile-wide source evidence or links to every category in a complete scan with at
least two categories, all offered to the judge. The latter means common across this registry,
not all datasets in the world. Unsupported labels become uncertain/review; source-linked
subsets can be specialised. Category frequency is never community consensus.

`rq1-compact-coverage-v2` produces a separate **compact requirement list**, while keeping
every atomic need in the full review list. Its objective is to cover every retained
atomic distinction across the documented dataset kinds—not merely choose one arbitrary
need per kind. Within the existing coarse families, bounded model calls propose strict
semantic equivalences. A shared catalogue property, broad/narrow relationship or partial
overlap cannot establish equivalence. Both rows must name each other. The server also
requires identical condition, scope and obligation profiles, and a representative must
retain every category link and use-case link of the need it represents. Nontransitive
judgements are not expanded by inference. Uncertain support, processing failures,
unresolved applicability and incomplete offered category context keep the affected needs in the
selected list. An incomplete global scan is reported but does not block individually checked equivalences. This can legitimately keep the entire list when safe compression is not
established.

Selection starts with a deterministic greedy cover and removes redundant representatives.
A bounded exact search improves each connected component of up to 80 needs (10,000
search nodes per component). `optimal_for_recorded_coverage` is true only when all searches
complete. It never establishes global semantic minimality: equivalence search is bounded
to groups of 20 within families. Ranking breaks ties; it never hides a unique need.
Every retained need has a `covered_by` witness. Categories with no retained linked need
are explicit gaps; no requirement is invented to fill them.

The UI's **Dataset kinds and compact requirements** panel shows the source registry,
selected needs, represented alternatives, protected needs and category gaps. `needs.json`
adds `dataset_categories`, `compact_selection`, and `compact_needs`. The compact list is
frozen machine output; the original `needs` list remains the current full human-review
view. Human edits clear their applicability and scope judgements and do not retroactively
change the frozen compact list. Source integrity hashes bind applicability evidence.
Two advanced model choices, `dataset_categories` and `selection`, default to the configured
model and participate in checkpoint identity. No additional inference is required during
export or review.

These policies apply to new runs and trials derived from saved extraction. Historical
runs and frozen results remain unchanged; their unfinished needs processing cannot be
resumed under new policies. To apply these changes use a separate trial from step 4.

## Base catalogues and review

Run `python scripts/build_base_needs.py` to build each `<id>.needs.json` offline
from its pinned registry. Each class and property has an entry, label-based phrase,
original term and base obligation. Definitions and usage notes are copied only
from the official files listed in the registry’s `source.files`, after verifying
their SHA-256 hashes. Separate RDF descriptions preserve class-specific anchors;
HTML definitions retain their original anchors. Where those files provide no
prose for an entry, its definition stays empty. No definitions are generated.
The six prose input files are bundled in `config/base_profiles/source-inputs`,
so rebuilding and `--check` need no network access. Catalogue files contain a registry checksum,
policy and catalogue hash and read **unreviewed**. They contain no benchmark material.

Junda reviews the selected catalogue before research evaluation. Keep the generated
catalogue intact and save human review separately in the adjacent
`<id>.needs-review.json`. It declares `base_profile_id`, `draft_catalogue_hash`,
`status: reviewed`, `reviewer`, `reviewed_at` (YYYY-MM-DD), and `phrase_corrections`,
keyed by entry ID with `need` and `note`. The draft hash binds review to the exact
registry and pinned official prose. A changed draft requires a new explicit review.

Use the worksheet without hand-editing the generated JSON:

```sh
.venv/bin/python scripts/base_needs_review.py export dcat-ap-2.0.1
# Junda fills only the corrected phrase and note columns in the CSV.
.venv/bin/python scripts/base_needs_review.py import dcat-ap-2.0.1 dcat-ap-2.0.1.needs-review.csv --reviewer "YOUR NAME" --reviewed-at YYYY-MM-DD
.venv/bin/python scripts/build_base_needs.py
.venv/bin/python scripts/build_base_needs.py --check
```

Export reads the current draft and leaves correction/note columns empty. Import
checks entry IDs and every read-only worksheet cell against that draft before
writing the review file; retain all exported rows. It imports only nonblank
corrected phrases. Import refuses modified or stale worksheet cells; build refuses reviews with
stale draft hashes. Both refuse unknown IDs, empty phrases, vocabulary terms and
duplicate phrases within a class. Review may
have zero corrections: it still records who reviewed the unchanged draft.

**Only phrases change.** A corrected entry retains its original text in
`need_draft` and the reviewer’s rationale in `review_note`. Definitions, usage notes,
obligations, labels and IDs are untouched. The generated catalogue's `review`
records status, reviewer, date, review filename, exact file SHA-256 and corrected
count, and its catalogue hash is recomputed. `--check` now reproduces the reviewed
output from the registry, pinned sources and review file. Without a review file,
output remains byte-identical to the unreviewed draft. The policy remains
`rq1-base-needs-catalogue-v2`.

New needs runs and derived trials pin the current catalogue when created.
Existing runs keep their saved catalogue hash and review metadata; classification
refuses a changed catalogue. Derive a new trial after rebuilding a reviewed
catalogue. The workbench shows its reviewer/date beside the reviewed status and
provides a catalogue download. The saved reviewer identifies the author; an
AI-assisted review is not human approval. On 19 October 2026, Codex reviewed the
six remaining catalogues at Junda’s request, preserving the earlier DCAT-AP 2.0.1
review. See [the review record](BASE-CATALOGUE-REVIEW-2026-10-19.md) for scope,
counts, source limitations and use in future runs.

Since `rq1-base-gap-status-v1`, each classified need records a `base_gap`:
`served_by_base` (generic), `refines_base` (domain use of the base), `unresolved` (no
match among the offered entries while the search was incomplete), `no_base_match`
(no match after a complete search) or `not_checked` (no base selected, or no checked
classification). It records how many entries were compared out of the catalogue, and
the step lists each batch's offered entry IDs. A miss among the offered entries is not
proof that the base lacks the capability, so it is never reported as a new gap.

Classification offers at most 25 catalogue entries per batch using conservative,
deterministic word retrieval over phrases, definitions and usage notes
(up to five candidates per need, round-robin). Definitions and notes also appear
in the classifier offer. Only
offered IDs can be selected. A missed base match remains a domain proposal rather
than being discarded. This bound can leave generic duplicates in the review list;
classification and false exclusions require independent evaluation. A literal
stated condition cannot be erased by declaring a need generic. A stronger source
obligation than every matched base entry also prevents generic exclusion, including
stronger alternatives hidden behind a group’s `unknown` obligation.

## Policies and bounds

| Step | Policy | Bound / recovery |
|---|---|---|
| Fresh need extraction | `rq1-independent-elicitation-v3.3` | Selected role descriptions exclude discovery citations and merge history; no `extension_kind` or `base_property` in the needs provider contract |
| Normalization | `rq1-need-normalization-v1` | Uncited and base-only filtering; historical extraction annotations remain readable |
| Source check | `rq1-original-source-v2.2` | Deterministic; every cited link checked |
| Proposal support | `rq1-proposal-support-v1` | At most 25 proposals / 24,000 input characters; only own excerpt IDs allowed |
| Grouping | `rq1-semantic-consolidation-v3` | 40 candidates, 24,000 input characters, at most 25 prior offered groups; audited exact fallback for invalid model grouping |
| Need writing / rewrite critic | `rq1-need-statement-v3` | At most 20 groups; 24,000 writer input characters; independent critic up to 48,000 characters; initial response plus one output correction; a failed rewrite is retried member by member, a single need keeps its statement |
| Additional member checking | `rq1-need-membership-v1` | Large groups use a bounded writing basis (up to 20 members / 16,000 statement characters); every remaining member checked in batches up to 40 / 24,000 characters |
| Base catalogue | `rq1-base-needs-catalogue-v2` | Frozen base-only file and checksum; optional hash-bound human phrase review |
| Generic/domain and base search | `rq1-generic-domain-v4`, `rq1-base-needs-full-search-v3` | One need per call against the complete catalogue in chunks (first chunk 10–20 entries, then 20); a need listing several items is generic when one listed entry covers each item; a match without an entry ID counts as no match in that chunk |
| Dataset categories | `rq1-dataset-categories-v1` | Up to 12 evidence rows / 22,000 input characters; exact source citations; partial scans explicit |
| Compact selection | `rq1-compact-coverage-v1` | Up to 20 needs / 22,000 input characters per equivalence call; bounded exact cover; all retained needs preserved |
| Base-gap status | `rq1-base-gap-status-v1` | Deterministic; from the classification and the number of entries compared |
| Profile scope (D5) | `rq1-profile-scope-v7` (named catalogue record; in F/A runs also after the F/A test) | Up to 25 needs / 24,000 input characters; statement, condition, scope, supporting excerpts and source-linked dataset categories; one verdict per offered need ID; an example is required unless serves is neither |
| Contribution linking | `rq1-use-case-contribution-v1` | Up to 25 needs / 24,000 input characters; at most 32 task links per response row; necessity as an annotation |
| Link critic | `rq1-use-case-contribution-critic-v1` | Up to 25 links / 24,000 input characters; judges contribution only |
| Need assessment | `rq1-need-support-v1` | One logical assessment per kept need; complete selected excerpts, max 45,000 input characters; at most two generations for schema/cutoff recovery |
| Row recovery | `rq1-needs-row-recovery-v2` | Valid rows saved; correction includes only failing rows; invalid/cutoff output gets durable fallbacks after exhaustion; provider failures stop and remain retryable |
| Rank | `rq1-need-ranking-v1` | Deterministic; every kept need remains listed |
| Families (D5) | `rq1-need-families-v1` | 40 needs, 24,000 input characters and at most 60 earlier families per grouping call (`grouping` model setting); invalid grouping keeps that chunk's needs as singleton families, audited |
| Discussion routing | `rq1-needs-routing-v3` | An obligation that no source states opens no case by itself (since v2), nor does the lexical 'and' hint when the model judged atomicity (v3); both stay on the need for review. Runs saved under v2 keep v2 routing; runs saved without a routing policy keep their original routing |

A single oversized needs-processing row receives the recorded conservative
fallback below; need assessment requires human review/splitting. Evidence is not truncated to make an assessment
fit. Extraction hints sent to the use-case linker are deduplicated, with at most
two deterministic justification examples per declared task; all original hints
remain on members. The linker records this selection and original distinct count.

Checkpoints bind policy, prompt, schema and complete input. Each row gets an initial
response and at most one explicit correction containing only failing rows. Other
valid rows are saved first. `rq1-needs-row-recovery-v2` records exhausted fallbacks
and replays them on Resume without new generations; valid negative judgements are
never corrected away.

Only invalid structured output, output-token cutoffs and deterministic input-bound
failures consume the correction budget. Authentication errors, timeouts and other
provider failures stop the stage visibly. The chunk records `transport_failed`,
the error class and requested IDs, without consuming an attempt or creating
fallbacks. Resume retries unfinished rows and preserves previously accepted rows.
Historical v1 runs retain their frozen conditions; use a derived trial to apply v2.

| Exhausted row | Visible fallback |
|---|---|
| Proposal support | Keep authentic `supports` quotations and document counts, flagged support not checked; semantic support remains unchecked |
| Writer or rewrite critic | Restorable rewrite-rejected group with its audit |
| Membership | Each unchecked member becomes a singleton, flagged membership not checked |
| Classifier | Retain as domain, flagged not classified |
| Profile scope judge | Retain, flagged profile scope not checked; never a scope set-aside |
| Use-case linker or link critic | Retain, flagged scoping not checked; exhausted invalid/cutoff answers never create no-use-case asides |

Metrics report fallbacks per step. Oversized rows use the same visible fallback
without a provider request; source quotes are never truncated. Unexpected code
defects still fail visibly. No model substitution or reference tuning is performed.

## Review, ranking and exports

Cards show the need, rank, obligation or alternatives, justified links, base class
and matches, expandable supporting candidates and evidence, and “For RQ2” hints.
Set-aside lists distinguish no source, base specification only, source-check
failure, quote-unsupported proposals, rejected rewrites, generic needs, the three
profile-scope tests and no use case. A reviewer can inspect or restore an item with
a recorded rationale. Restoration leaves it unaccepted, resets support assessment and preserves the frozen
machine output. An uncited or term-bearing proposal cannot bypass source or
term-free gates; repair its evidence/wording before acceptance.

Human edits, splits and merges create new unaccepted revisions. Old classification,
rank and use-case judgements are cleared because they may no longer apply. Parent
lineage and observed hints remain, and original-source checks still run. These
human revisions/restorations require explicit review; they are not claimed as
machine-verified use-case coverage. Human acceptance does not require choosing
vocabulary classes/properties or a value kind; those are RQ2 modelling decisions.

Rank keys: explicit support, inferred support, then the rest; descending number of
distinct supporting documents (source IDs), contributing roles and kept use-case
links; ascending need ID breaks ties. Rank is the machine review order. Restored or
human-created needs without a machine rank are listed afterwards, visibly labelled.
Ranking is not a precision or confidence measure.

`GET /api/rq1/v2/runs/{run_id}/needs?download=true` exports `needs.json`: ranked current
needs, members, original evidence, justified use cases, observed hints, catalogue
suggestions, profile-scope judgements, families, review decisions, asides, policies
and per-step audits. It is suitable as RQ2 input and as input to a separately
defined evaluation, not an automatic
benchmark score. Review-budget entries for 25/50/100 count decisions on the frozen
machine prefixes; they do not hide other needs or measure effort saved.

`workflow_metrics()` adds proposals → asides by reason → source-checked candidates
→ needs → classified/profile-scoped/scoped/kept needs → families. It reports model
calls, failures and latency per processing step and rejected outputs separately. A logical assessment can need
two generations. Sequential call latency is not parallel wall time; missing token
usage/cost remains unknown.

## Discussion routing

With automatic discussion, a kept need opens a bounded case when its assessment
support is uncertain, unsupported or contradicted, when it has a blocking or review
finding, or when it conflicts with another need. Since `rq1-needs-routing-v2`, one
finding is excluded: an obligation that no source states. It is the normal state of
a need ("not stated by sources"), and a discussion cannot add a source statement.
The finding stays on the need, and its routing reason reads
`obligation_not_stated_by_sources`. A need whose obligation is stated keeps its
obligation findings as triggers. This change followed a functional Mobility run
(counts only, no reference rows): applied to its 417 cases, 208 would not open
because the unstated obligation was their only trigger, and 209 would still open
on their other triggers.

`rq1-needs-routing-v3` also excludes the lexical atomicity hint. Every assessment of a
statement containing ';', 'and' or 'as well as' carries the deterministic finding
"Potential compound requirement; assess whether it needs splitting", whatever the
model concludes. The model's assessment itself judges atomicity. When the model
assessed the need and raised no atomicity finding of its own, the hint opens no case;
it stays on the need, and its routing reason reads `possible_compound_wording`. A
model finding about atomicity (or compound or split statements) remains a trigger, as
does the hint when no model assessment exists (assessment unavailable, input bound,
offline). Of those 209 cases, 111 had atomicity as their only remaining trigger; that
count does not separate the lexical hint from the model's own findings. Runs saved
under v2 keep v2 routing and can continue processing.

## Comparison conditions

These conditions answer whether the multi-agent parts improve on simpler set-ups.
Keep the frozen snapshot, base profile, use cases, model per step and evaluation
protocol identical across them; only the condition changes.

| Condition | How to create it in the workbench |
|---|---|
| Single analyst with the same evidence checks | Stakeholder panel: **Single analyst · comparison baseline**. One neutral extraction role (`single_analyst`, not in any preset) reads every passage; all later steps are unchanged. Discussion: only when a reviewer asks |
| Independent stakeholder roles, no discussion | Stakeholder panel selected from the sources; discussion only when a reviewer asks |
| Independent roles with selective discussion | The same panel; discussion of flagged needs automatically. A trial from the saved extraction (step 4) reuses the extraction of the previous condition |
| Fewer roles | Stakeholder panel selected from the sources with a smaller maximum number of roles |

All conditions pass through the same needs processing, including the D5 profile scope
and families. Score atomic needs first; use equal-size family comparisons as a secondary analysis.

Choose between conditions on a development case. Then freeze the pipeline and run
Mobility once per chosen condition, as described below.

## Compatibility and test protocol

Runs saved under earlier needs policies (before `rq1-profile-scope-v3`,
`rq1-use-case-contribution-v1` and `rq1-base-gap-status-v1`) keep their results, but
their needs processing cannot continue under the new policies. To apply them, derive a
trial from the saved extraction (`start_from: "normalization"`).

Historical runs remain unchanged. `output_form: candidates` preserves the old
pipeline for explicit API compatibility and offline rule/demo comparisons. New
agent UI runs and derived trials explicitly select `needs`; the public request
contract resolves an omitted output form by strategy: `multi_agent` selects
needs, while `rules` and `mock` select candidates. Explicit needs output with
an offline strategy is refused at creation, including derived trials. Historical requests missing this field resume
under their original candidate policy. A separate derived trial reuses the exact
saved extraction, including v2.11 wording, while rewriting every resulting group.
It neither re-extracts nor reuses old per-candidate assessments.

Mobility is the held-out test case. Use JRC and all of StatDCAT as development
cases, never reported as test results; HealthDCAT-AP and GeoDCAT-AP are held out
(`benchmark-data/BENCHMARK-METHODOLOGY.md`). Junda writes dated use cases from each
documented purpose before running. Scoping off is a reported comparison. Prior base-check and grouping heuristics
were adjusted while reading Mobility candidates, never Mobility reference rows;
this must be disclosed in the paper.

First run a development case, then an authorised functional Mobility derived trial
using counts, calls, time and errors only. After development, freeze/tag the pipeline;
only then run Mobility once derived and once fresh and compare with reference
requirements. A later change requires a new tag/condition. No live run, freeze tag,
reference scoring, measured effort saving or partner-requirement condition is
created by this implementation request.

Offline validation:

```sh
PYTHONPATH=requirement-reuse-service .venv/bin/python -m pytest -q tests
.venv/bin/python scripts/export_workflow_schema.py --check
.venv/bin/python scripts/build_base_needs.py --check
npm run build --prefix frontend
```

The automated and browser checks use scripted/synthetic fixtures and isolated
storage, not saved research runs. Their success establishes implementation
behaviour, not live-model quality, recall or scientific validity.

### User-authored, versioned use cases

For each development case, Junda writes `benchmark-data/<case>/use-cases.json`
from the profile's stated purpose **before** running. The optional file is a list
of `{id, statement, kind, basis, author, written_at}`; every field is required in
that file. `basis` names the purpose document and section, and `written_at` is an
ISO date or timestamp. Kinds are `competency_question`, `user_task`,
`stakeholder_need` and `cross_cutting_goal`. Purpose-based goals may cover legal
reuse, publisher contact or quality judgement. The agent does not author them.

Import freezes the tasks and the exact file SHA-256 into the snapshot. The UI
shows their metadata and preserves it when the text is unchanged. Editing the
text makes manual tasks and drops the imported file attribution. Absence of a
file imports no tasks; existing snapshots without this metadata remain valid.
No Mobility task file is added until Junda confirms copying its 12 frozen tasks.

A scoping-off run is a reported comparison, not the intended development setup.
Evaluation must report recall for kept needs and for kept needs plus the visible
`no_use_case` set-asides. Neither figure is claimed without an evaluation.


## Independent relevance and applicability checks (17 October 2026)

PR #25 keeps extraction proposals with off-contract typed labels by recording a neutral-label
reset, and distinguishes specification authorship from participating in data use. The follow-up
uses `rq1-profile-scope-v4`, `rq1-dataset-applicability-v1`, `rq1-dataset-categories-v2` and
`rq1-compact-coverage-v2`.

C1 (catalogue-level relevance) and C2 (find/access contribution) have their own `ProfileScope`
contract and checkpoint. Invalid category IDs, malformed applicability rows or inauthentic
category quotations cannot erase an accepted C1/C2 decision. Only the independently saved
applicability rows receive their bounded correction; exhausted rows remain unresolved and
visible. Source checks and the two relevance criteria still apply normally. Applicability is
only judged for retained, source-checked needs with checked C1/C2 decisions.

Dataset distinctions record separate, overlapping **format**, **structure**, **subject** and
**unspecified** dimensions. Formats and structures are appropriate when the source connects
them with describing or distinguishing datasets; a class definition by itself is insufficient.
Sharing a format does not establish equivalent metadata requirements. Exact spelling variants
(and file/files suffixes within formats) are joined; other aliases must occur explicitly in
the same cited source passage. Every original label and citation is retained. Different
dimensions are never merged. Semantic synonym discovery is not automatic.

Every evidence unit is attempted and accounted for as fully checked or unchecked. An exhausted
unit may contribute individually valid source-linked mentions, with `unit_scan_complete: false`;
rejected mentions stay in the audit. This preserves partial evidence without claiming a complete
scan. No invented quotation is materialized. Valid mentions are machine proposals, not an
independently established domain taxonomy.

Commonness is strict: either each recorded category has a verified applicability link and the
entire registry was offered after a complete scan, or a supporting excerpt explicitly claims
profile-wide applicability. The output distinguishes `all_recorded_categories` from
`explicit_profile_wide`. Quote validation establishes provenance; semantic applicability and
profile-wide claims still require review. No restriction missing from a need, shared format,
frequency or incomplete scan establishes commonness.

An incomplete scan does not halt requirements production or blanket-protect all needs from
selection. Needs with individually checked applicability may undergo the existing reciprocal
exact-equivalence checks, preserving category links, use cases, conditions and obligations.
Unknown applicability, incomplete offered category context and other processing failures keep
the affected need protected. Selection reports unchecked units and category gaps; a valid cover
of retained needs does not establish complete corpus or domain coverage.

Earlier saved runs and their results are unchanged. Policy changes require a separate derived
trial from a fully completed extraction. A run with failed extraction roles cannot seed such a
trial. No live replay or new run is part of this change. Base selection remains explicit (or a
configured case default): selecting no base performs no inherited-base comparison.


## Named catalogue records and listed base items (19 October 2026)

The routed runs of 18 October kept many needs that restate facts and rules from the
sources rather than information a catalogue holds about a dataset:

- JRC: 25 of 56 kept needs were about the JRC data policy itself, 10 about DCAT.
- Stat: 11 of 39 were about the specifications themselves (W3C Recommendation status,
  contributors, namespaces). The C1 judge also set aside a dataset's dimensions and the
  unit attached at dataset level, which are what StatDCAT-AP adds.
- Health (held out; counts only): of 576 kept needs, about 400 cite GDPR or the EHDS
  proposal and mention no dataset, distribution, catalogue, metadata or record.

`rq1-profile-scope-v6` therefore asks the judge for the catalogue record (resource and
statement) before C1 can pass. The resource may be any kind the profile catalogues; a
record for another kind names it ("facility: …"). Properties of a dataset that concern
processing (legal basis, purpose, personal-data categories, who grants access) are
record statements; rules about how processing must be done are not. The judgement still
only keeps or sets aside offered needs; set-asides stay visible and restorable. A
missing record statement, or an "other" record without its kind, gets one bounded
correction for that need only.

`rq1-profile-scope-v7` is scope contract v1 (Junda, 23 October): every need, wherever
it is written, passes both the F/A test and the record test. Before v7, F/A runs never
ran the record test. Their F/A test sets a need aside only when it serves neither or is
unsupported, and any other nature only gets a review flag. So JRC and Stat v12 kept
statements about the source documents (their status, their patent disclosures) and
rules for publishers.

Since v7, in F/A runs:
- The record test runs, with the same prompt and contract, on the needs the F/A test
  keeps. A need stays only when both pass.
- A need that fails is set aside with the record test's reason (`not_catalogue_level`,
  `not_find_or_access` or `operational_data_processing`). The set-aside keeps both
  verdicts in its details and stays visible and restorable.
- A kept need carries `fa_scope` and the record verdict in `profile_scope`
  (`record_resource`, `record_statement`, `failed_tests`).
- A missing judgement keeps the need, flagged `profile_scope_not_checked`, and its
  dataset applicability is not judged, as in other runs.
- A need that the record test sets aside as `operational_data_processing` (the
  guard on explicit data-processing actions) is a valid set-aside reason of the run
  record.
- The step record counts the F/A and record set-asides apart (`fa_set_aside_count`,
  `record_set_aside_count`) and together (`set_aside_count`, and
  `set_aside_by_reason` with `fa_scope_set_aside`).

The F/A prompts are unchanged, so the frozen F/A contract of older runs still matches.
Non-F/A runs are judged as under v6. The version is in the needs policies, so it
applies from normalisation: a run continued at normalisation under v6 is refused, and
a run derived from normalisation is judged under v7. In the discussion,
`rq1-fa-dialogue-v13` applies the same two tests to every need a change writes (see
`FA-COVERAGE-DISCUSSION.md`).

The risk: on 18 October an earlier wording of the record test set aside Stat's
dimensions and units. The 19 October wording (v6) keeps them, but it has not run on
Stat since.

The base search (`rq1-base-needs-full-search-v3`) changes in three ways:

1. A need that lists several items (the title, keywords and release date of a dataset)
   is generic when the listed entries cover every item; before, one entry had to cover
   the whole need, so such needs stayed as "no base match" (14 in the JRC run).
2. The entries that the need's words name come first, so the items of such a need are
   usually offered in the first chunk. Items named differently from the base (accrual
   periodicity for frequency) can still fall into different chunks; then the need is
   not found generic.
3. A "match" that names no listed entry counts as no match in that chunk and is
   recorded (`unnamed_match` in the search audit) instead of being sent back for a
   correction. In the Health run this correction made up 2,341 of 6,618 base-search
   generations.

Runs saved under earlier policies need a derived trial from their extraction.

The opt-in [procedural base reviewer](FA-COVERAGE-DISCUSSION.md#optional-procedural-base-reviewer)
labels restatements against the run's pinned base catalogue before discussion,
then rechecks discussion-created revisions. It keeps every reviewed need in the
inventory; checked restatements leave only the working count. Legacy v1 runs
remain unchanged, and all new judgements still require human review.
