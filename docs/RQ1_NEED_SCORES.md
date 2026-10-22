# Need scores (`rq1-need-scores-v2`)

`scripts/score_needs.py` gives every active need of a saved run two scores and ranks the needs by F, then S,
so they can be reviewed in that order and runs compared without reading every need. It only reads the run
(GET requests or a saved JSON file): no model calls, no reference rows, nothing written back. It runs after a
run finishes and before human review; it does not change what the pipeline produces.

```
.venv/bin/python scripts/score_needs.py --api http://127.0.0.1:8013 --run <run-id> [--compare <run-id>] --out scores/
.venv/bin/python scripts/score_needs.py --run saved-run.json --out scores/
```

It writes `<run-id>-need-scores.csv` (one row per need in rank order, every criterion) and
`<run-id>-need-scores.md` (distributions, groups, the 10 highest and lowest ranked and the 10 least specific
needs, the requirement flags, and with `--compare` the rank correlation of needs with the same statement in
both runs).

## Design decisions (Junda, 22 Oct 2026)

| Question | Decision |
|---|---|
| Why more than one score | F alone ranks near-copies of source sentences highest, including statements about a policy or document rather than user needs, and ranks low a need whose only source is a single word. A second dimension keeps such cases visible. |
| Requirement-ness (R) | Reported as flags, not as a score: in F/A runs the workflow has already filtered on it (the F/A scope check, the writer's "Users can …" wording, no catalogue-level judgement), so most needs pass. |
| Corroboration | Counts in F (F5), but repeats add less. |
| Needs the base already covers | Scored and labelled, so new and covered needs can be ranked separately. |
| Specificity | A second score, S. Needs are ranked by F, then S. |
| Criteria that cannot be judged | Left out of the mean rather than counted as 0.5. |
| Reference requirement sets | The scores are not tuned to match them. |

## F, fidelity to the source

The mean of the criteria that can be judged for the need.

| | Criterion | Read from | Value |
|---|---|---|---|
| F1 | Support of the need by its quotes | `qualification.support`, else `fa_scope.support` | explicit 1, inferred 0.5, uncertain or disputed 0.25, unsupported, contradicted or missing 0 |
| F2 | Its wording found in its own quotes | statement and supporting `evidence_links[].quote` | share of the statement's content words (frame such as "Users can know" and stop words removed, plural and verb endings folded) that occur in the quotes |
| F3 | Closeness to the first extracted statement | `raw_statement` of the proposals it descends from (`parent_revision_ids`) | 1 − word edit distance ratio to the closest one; blank for a need the discussion added |
| F4 | Nothing added beyond the quotes | `unbacked_obligation`; condition and scope against the quote words | 1, minus 0.5 for an unbacked obligation and 0.5 for a condition or scope whose words are not in the quotes |
| F5 | Corroboration | distinct supporting quotes (case and spacing folded); distinct source-reading roles | the mean of the two counts, each mapped so that every further one adds half as much as the one before (0, 0.5, 0.75, 0.875, …): repeats add less |

## S, specificity

Whether the need names a concrete information item ("the unit of measure of an observation") or a vague topic
("metadata about data quality"). Of the words that name what the need is about (content words without the
frame, and without the resource words *data, dataset, distribution, catalogue, service, resource, record*,
which count neither way), S is the share that is not in a fixed list of vague words: *metadata, information,
details, aspects, elements, characteristics, features, content, things, items, issues, topics, matters, facts*
and qualifiers such as *general, various, relevant, related, other, additional, several, many*. A need that names
nothing beyond the resource gets 0.

## Requirement flags (R)

Reported, not a score: in F/A runs the workflow has already filtered on these (the F/A scope check sets aside
needs that serve neither finding nor access, and the writer words needs as "Users can …"), so most needs pass
all three.

| | Criterion | Read from | Value · flag |
|---|---|---|---|
| R1 | Serves finding or accessing data | `fa_scope` (F/A runs), else `profile_scope` (D5) | find, access or both as an information requirement 1; operational obligation 0.5 · `operational_obligation`; background, implementation detail or neither 0 · `not_find_or_access`; blank if not judged |
| R2 | Worded as a user need | the statement | an obligation word or a statement about a document or rule ("The policy obliges …", "… shall be …") 0 · `rule_or_policy_wording`; else an actor with a capability ("Users can …") 1; otherwise 0.5 · `unclear_wording` |
| R3 | At catalogue level | `profile_scope.record_resource`, `catalogue_level` (D5 runs) | a catalogued resource described as a whole 1, a part of it 0.5 · `part_of_a_resource`, none 0 · `not_catalogue_level`; blank in F/A runs, which do not judge it |

Also reported: rewording steps, extracted proposals, passages, evidence units and source roles behind the need,
whether the base covers it, its base relation and its flags.

## First results (22 Oct 2026, `rq1-need-scores-v2`)

Computed for two development runs in the browser pane by a function-by-function JavaScript port of this
script, so the run data stayed on the machine that runs the app; the port gives identical rows to the script on
2,000 random runs. Running the script against the app reproduces them.

| | JRC v11 `run-12a2c91a` | Stat v10 `run-1428af21` |
|---|---|---|
| Active needs | 68 | 53 |
| F mean · median · range | 0.83 · 0.86 · 0.60–0.97 | 0.79 · 0.81 · 0.50–0.90 |
| S mean · needs at 1.00 | 0.93 · 48 | 0.96 · 42 |
| Requirement flags | 2 rule or policy wording, 2 operational obligation | 2 operational obligation |
| F / S by origin | consolidated (58) 0.85 / 0.93; revised by the discussion (8) 0.76 / 0.98; added by the discussion (2) 0.61 / 0.84 | consolidated (53) 0.79 / 0.96 |

- Lowest F: needs whose support was judged unsupported, whose words are mostly not in their quotes (for example
  quotes that are RDF examples), or that were rewritten far from their extracted statement.
- S misfires where a listed word belongs to a concrete item: "rights information associated with a
  distribution" scores 0.33.

## Limits

- Both scores are lexical and rule-based proxies over machine judgements; they order needs for review, they do
  not measure correctness.
- S rests on a fixed word list. It catches vague wording, not a need that is concrete but trivial.
- Needs that keep the same records in two runs (for example two discussion trials derived from one parent)
  get identical scores; comparing such runs says nothing about the scorer.
