# Need scores (`rq1-need-scores-v1`)

`scripts/score_needs.py` gives every active need of a saved run two scores, so needs can be ranked and runs
compared without reading every need. It only reads the run (GET requests or a saved JSON file): no model
calls, no reference rows, nothing written back. It runs after a run finishes and before human review; it
does not change what the pipeline produces.

```
.venv/bin/python scripts/score_needs.py --api http://127.0.0.1:8013 --run <run-id> [--compare <run-id>] --out scores/
.venv/bin/python scripts/score_needs.py --run saved-run.json --out scores/
```

It writes `<run-id>-need-scores.csv` (one row per need, every criterion) and `<run-id>-need-scores.md`
(distributions, groups, the 10 highest and lowest needs on each score, and with `--compare` the rank
correlation of needs with the same statement in both runs).

## F, fidelity to the source

The mean of the criteria that can be judged for the need.

| | Criterion | Read from | Value |
|---|---|---|---|
| F1 | Support of the need by its quotes | `qualification.support`, else `fa_scope.support` | explicit 1, inferred 0.5, uncertain or disputed 0.25, unsupported, contradicted or missing 0 |
| F2 | Its wording found in its own quotes | statement and supporting `evidence_links[].quote` | share of the statement's content words (frame such as "Users can know" and stop words removed, plural and verb endings folded) that occur in the quotes |
| F3 | Closeness to the first extracted statement | `raw_statement` of the proposals it descends from (`parent_revision_ids`) | 1 − word edit distance ratio to the closest one; blank for a need the discussion added |
| F4 | Nothing added beyond the quotes | `unbacked_obligation`; condition and scope against the quote words | 1, minus 0.5 for an unbacked obligation and 0.5 for a condition or scope whose words are not in the quotes |

## R, requirement-ness

| | Criterion | Read from | Value |
|---|---|---|---|
| R1 | Serves finding or accessing data | `fa_scope` (F/A runs), else `profile_scope` (D5) | find, access or both as an information requirement 1; operational obligation 0.5; background, implementation detail or neither 0; blank if not judged |
| R2 | Worded as a user need | the statement | an obligation word or a statement about a document or rule ("The policy obliges …", "… shall be …") 0; else an actor with a capability ("Users can …", "Publishers can …") 1; otherwise 0.5 |
| R3 | At catalogue level | `profile_scope.record_resource`, `catalogue_level` (D5 runs) | a catalogued resource described as a whole 1, a part of it 0.5, none 0; blank in F/A runs, which do not judge it |

Reported beside the scores, not in them: rewording steps, extracted proposals, evidence units and source
roles behind the need (corroboration), whether the base covers it, its base relation and its flags.

## Limits

- Both scores are lexical and rule-based proxies over machine judgements; they rank needs for review, they do
  not measure correctness.
- In F/A runs R rests on R1 and R2 only, and both are near 1 for most needs, because the F/A scope check has
  already set aside needs that serve neither finding nor access. R then separates mainly needs worded as
  rules or policy statements and operational obligations.
- Needs that keep the same records in two runs (for example two discussion trials derived from one parent)
  get identical scores; comparing such runs says nothing about the scorer.
