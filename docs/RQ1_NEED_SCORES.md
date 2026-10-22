# Need scores (`rq1-need-scores-v3`)

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
both runs). File names keep only letters, digits, `.`, `_` and `-` of the run ID, so they stay inside `--out`.

## Design decisions (Junda, 22 Oct 2026)

| Question | Decision |
|---|---|
| Why more than one score | F alone ranks near-copies of source sentences highest, including statements about a policy or document rather than user needs, and ranks low a need whose only source is a single word. A second dimension keeps such cases visible. |
| Requirement-ness (R) | Reported as flags, not as a score: in F/A runs the workflow has already filtered on it (the F/A scope check, the writer's "Users can …" wording, no catalogue-level judgement), so most needs pass. |
| Corroboration | Counts in F (F5), but repeats add less. |
| Needs the base already covers | Scored and labelled, so new and covered needs can be ranked separately. |
| Specificity | A second score, S. Needs are ranked by F, then S: S orders needs with the same F and is reported for every need. |
| Criteria that cannot be judged | Left out of the mean rather than counted as a fixed value. |
| Reference requirement sets | The scores are not tuned to match them. |

## F, fidelity to the source

The mean of the criteria that can be judged for the need.

| | Criterion | Read from | Value |
|---|---|---|---|
| F1 | Support of the need by its quotes | `qualification.support`, else `fa_scope.support`, else `profile_scope.support` | explicit 1, inferred 0.5, uncertain or disputed 0.25, unsupported or contradicted 0; blank when no support judgement exists or its label is unknown |
| F2 | Its wording found in its own quotes | statement and supporting `evidence_links[].quote` | share of the statement's content words (frame such as "Users can know" and stop words removed, plural and verb endings folded) that occur in the quotes |
| F3 | Closeness to the first extracted statement | `raw_statement` of the proposals it descends from (`parent_revision_ids`); a record without parents written by a source-reading role is its own extracted statement | 1 − word edit distance ratio to the closest one; blank for a need the discussion added |
| F4 | Nothing added beyond the quotes | `unbacked_obligation`; condition and scope against the quote words | 1, minus 0.5 for an unbacked obligation and 0.5 for a condition or scope whose words are not in the quotes |
| F5 | Corroboration | distinct supporting quotes (case and spacing folded); distinct source-reading roles | the mean of the two counts, each mapped so that every further one adds half as much as the one before (0, 0.5, 0.75, 0.875, …): repeats add less |

## S, specificity

Whether the need names a concrete information item ("the unit of measure of an observation") or a vague topic
("metadata about data quality"). S looks at the content words of the statement (frame and stop words
removed), whole words only. Resource words and qualifiers count neither way; of the remaining words, S is the
share that is not a vague noun. A need that names nothing beyond the resource gets 0.

| List | Words |
|---|---|
| Vague nouns | metadata, information, info, detail(s), aspect(s), element(s), characteristic(s), feature(s), thing(s), item(s), issue(s), topic(s), matter(s), fact(s), stuff |
| Qualifiers (neither way) | general, generic, various, relevant, related, other, certain, appropriate, additional, further, overall, useful, important, necessary, available, associated, corresponding, respective, particular, given, existing, possible, different, several, many, multiple, more, most, less, etc |
| Resource words (neither way) | data, dataset(s), distribution(s), catalogue(s), catalog(s), service(s), resource(s), record(s) |

So "the available formats of a distribution" scores 1 (formats), "metadata about data quality" 0.5 (metadata
is vague, quality is not), "various details of the dataset" 0.

## Requirement flags (R)

Reported, not a score: in F/A runs the workflow has already filtered on these (the F/A scope check sets aside
needs that serve neither finding nor access, and the writer words needs as "Users can …"), so most needs pass
all three.

| | Criterion | Read from | Value · flag |
|---|---|---|---|
| R1 | Serves finding or accessing data | `fa_scope` (F/A runs), else `profile_scope` (D5) | find, access or both as an information requirement 1; operational obligation 0.5 · `operational_obligation`; background, implementation detail or neither 0 · `not_find_or_access`; blank if not judged |
| R2 | Worded as a user need | the statement | a statement about a document or rule ("The policy obliges …") 0 · `rule_or_policy_wording`; an actor with a capability ("Users can …", "Users should be able to …") 1, unless what they would know is itself a rule ("Users can know that JRC data shall be provided …") 0 · `rule_or_policy_wording`; any other statement with must, shall or should ("Metadata … shall be open …") 0 · `rule_or_policy_wording`; otherwise 0.5 · `unclear_wording`. F/A needs may keep the source's modality, so a modal word alone does not flag a user need. |
| R3 | At catalogue level | `profile_scope.record_resource`, `catalogue_level` (D5 runs) | a catalogued resource described as a whole 1, a part of it 0.5 · `part_of_a_resource`; `none` 0 · `not_catalogue_level`; blank in F/A runs, which do not judge it, and for labels this version does not know |

Also reported: the need's origin (consolidated, revised or added by the discussion, extracted), rewording
steps, extracted proposals, passages, evidence units and source roles behind it, whether the base covers it,
its base relation and its flags.

## First results (22 Oct 2026, `rq1-need-scores-v3`)

Computed in the browser pane, where the run data stays, by a function-by-function JavaScript port of this script
kept outside the repository: it gives rows identical to the script on 2,500 random runs, and its source was
checked in the page. To check the numbers, run the script against the app.

| | JRC v11 `run-12a2c91a` | JRC re-normalised on needs v3 `run-0834b623` | Stat v10 `run-1428af21` |
|---|---|---|---|
| Active needs | 68 | 85 | 53 |
| F mean · median · range | 0.83 · 0.86 · 0.60–0.97 | 0.83 · 0.85 · 0.56–0.95 | 0.79 · 0.81 · 0.50–0.90 |
| S mean · needs at 1.00 | 0.96 · 59 | 0.96 · 72 | 0.98 · 48 |
| Requirement flags | 2 rule or policy wording, 2 operational obligation, 1 unclear wording | 3 rule or policy wording, 3 operational obligation, 2 unclear wording | 2 operational obligation |
| F / S by origin | consolidated (58) 0.85 / 0.96; revised by the discussion (8) 0.76 / 1.00; added by the discussion (2) 0.61 / 0.94 | consolidated (75) 0.84 / 0.96; revised by the discussion (10) 0.73 / 1.00 | consolidated (53) 0.79 / 0.98 |

- Lowest F: needs whose support was judged unsupported, whose words are mostly not in their quotes (for example
  quotes that are RDF examples), or that were rewritten far from their extracted statement.
- Least specific: "Users can find what elements of metadata are provided for JRC data." and "Users can know the
  rights information associated with a distribution …" (0.50).

## Limits

- Both scores are lexical and rule-based proxies over machine judgements; they order needs for review, they do
  not measure correctness.
- S rests on fixed word lists. It catches vague wording, not a need that is concrete but trivial.
- R2 reads wording only: a rule phrased without a modal word or a document subject passes.
- Needs that keep the same records in two runs (for example two discussion trials derived from one parent)
  get identical scores; comparing such runs says nothing about the scorer.
