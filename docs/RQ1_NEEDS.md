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
need with domain meaning, scope or conditions. A **domain need** is not covered by
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
| Scope and critic | Propose necessary use-case links with justifications; independently keep/drop each link; set unlinked needs aside | 6 · Grouped needs & scope |
| Support assessment | One logical assessment per retained need against its union of source-checked excerpts | 6 · Grouped needs & scope |
| Rank | Order all retained needs deterministically; no cutoff hides needs | 6 · Grouped needs & scope |
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
an identical rewrite reuses the negative verdict. Twice-rejected groups are visible
`rewrite_rejected` asides with both statements and rationales; valid groups continue.

## Scope choices

The form offers automatic resolution, use-case scoping or off. Automatic resolution
uses `use_cases` if the frozen snapshot has tasks; otherwise it saves `off`.
Before each development run, Junda authors dated use cases from the stated purpose.
Scoping off is a separately reported comparison. If no tasks are supplied, the
software records scoping off rather than inventing any.
Benchmark import copies the case's declared tasks into the form; it does not invent
questions from example UI text.

With scoping on, a linker must explain why a use case cannot be met without a need.
A separate critic rejudges every link. Relatedness and general usefulness are not
necessity. Extraction task links are hints only. With scoping off, all otherwise
retained needs remain, and the run makes no use-case necessity claim. Source-failed
and unsupported proposals remain visible in their set-aside lists for repair.

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

Junda should review the selected catalogue before research evaluation. A revision
or review annotation changes its hash; record the reviewer/date, freeze the reviewed
catalogue as a versioned artefact and derive new trials rather than changing an
existing run's catalogue. The deterministic builder deliberately reproduces its
unreviewed draft; do not rebuild over a manually reviewed catalogue. `--check`
checks the generated draft. No review has been performed on Junda's behalf.
The UI provides a catalogue download next to the pinned base version.

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
| Fresh need extraction | `rq1-independent-elicitation-v3.2` | Existing excerpt and extraction budgets; no `extension_kind` or `base_property` in the new provider contract |
| Normalization | `rq1-need-normalization-v1` | Uncited and base-only filtering; historical extraction annotations remain readable |
| Source check | `rq1-original-source-v2.2` | Deterministic; every cited link checked |
| Proposal support | `rq1-proposal-support-v1` | At most 25 proposals / 24,000 input characters; only own excerpt IDs allowed |
| Grouping | `rq1-semantic-consolidation-v3` | 40 candidates, 24,000 input characters, at most 25 prior offered groups; audited exact fallback for invalid model grouping |
| Need writing / rewrite critic | `rq1-need-statement-v2` | At most 20 groups; 24,000 writer input characters; independent critic up to 48,000 characters; initial response plus one output correction |
| Additional member checking | `rq1-need-membership-v1` | Large groups use a bounded writing basis (up to 20 members / 16,000 statement characters); every remaining member checked in batches up to 40 / 24,000 characters |
| Base catalogue | `rq1-base-needs-catalogue-v2` | Frozen base-only file and checksum; currently unreviewed |
| Generic/domain | `rq1-generic-domain-v1` | Up to 25 needs / 24,000 input characters |
| Necessity linking | `rq1-use-case-necessity-v1` | Up to 25 needs / 24,000 input characters; at most 32 task links per response row |
| Link critic | `rq1-use-case-critic-v1` | Up to 25 links / 24,000 input characters |
| Need assessment | `rq1-need-support-v1` | One logical assessment per kept need; complete selected excerpts, max 45,000 input characters; at most two generations for schema/cutoff recovery |
| Row recovery | `rq1-needs-row-recovery-v2` | Valid rows saved; correction includes only failing rows; invalid/cutoff output gets durable fallbacks after exhaustion; provider failures stop and remain retryable |
| Rank | `rq1-need-ranking-v1` | Deterministic; every kept need remains listed |

A single oversized needs-processing row receives the recorded conservative
fallback below; need assessment requires human review/splitting. Evidence is not truncated to make an assessment
fit. Extraction hints sent to the necessity linker are deduplicated, with at most
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
| Use-case linker or link critic | Retain, flagged scoping not checked; exhausted invalid/cutoff answers never create no-use-case asides |

Metrics report fallbacks per step. Oversized rows use the same visible fallback
without a provider request; source quotes are never truncated. Unexpected code
defects still fail visibly. No model substitution or reference tuning is performed.

## Review, ranking and exports

Cards show the need, rank, obligation or alternatives, justified links, base class
and matches, expandable supporting candidates and evidence, and “For RQ2” hints.
Set-aside lists distinguish no source, base specification only, source-check
failure, quote-unsupported proposals, rejected rewrites, generic needs and no
use case. A reviewer can inspect or restore an item with a recorded rationale.
Restoration leaves it unaccepted, resets support assessment and preserves the frozen
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
suggestions, review decisions, asides, policies and per-step audits. It is suitable
as RQ2 input and as input to a separately defined evaluation, not an automatic
benchmark score. Review-budget entries for 25/50/100 count decisions on the frozen
machine prefixes; they do not hide other needs or measure effort saved.

`workflow_metrics()` adds proposals → asides by reason → source-checked candidates
→ needs → classified/scoped/kept needs. It reports model calls, failures and latency
per processing step and rejected outputs separately. A logical assessment can need
two generations. Sequential call latency is not parallel wall time; missing token
usage/cost remains unknown.

## Compatibility and test protocol

Historical runs remain unchanged. `output_form: candidates` preserves the old
pipeline for explicit API compatibility and offline rule/demo comparisons. New
agent UI runs and derived trials explicitly select `needs`; the public request
contract resolves an omitted output form by strategy: `multi_agent` selects
needs, while `rules` and `mock` select candidates. Explicit needs output with
an offline strategy is refused at creation, including derived trials. Historical requests missing this field resume
under their original candidate policy. A separate derived trial reuses the exact
saved extraction, including v2.11 wording, while rewriting every resulting group.
It neither re-extracts nor reuses old per-candidate assessments.

Mobility is the held-out test case. Use JRC, StatDCAT, HealthDCAT-AP and GeoDCAT-AP
as development cases, with Junda-authored and dated use cases from each
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
