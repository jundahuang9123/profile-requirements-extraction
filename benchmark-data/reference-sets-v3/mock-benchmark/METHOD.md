# Mock benchmark: method

A dry run of the scoring protocol in `benchmark-data/BENCHMARK-METHODOLOGY.md` on the saved
needs runs, against the reference sets v3 with the 23 October adjudication applied (PR #45, commit `671c60a`).
Only evidence-eligible atoms are scored. Machine-made throughout: the pair labels come from AI
reviewers, not from people.

## Runs

Every run with discussion v6 to v11 on the 8013 API (read with GET requests on 22 Oct 2026):

| Case | Run | Discussion | Derived from |
|---|---|---|---|
| JRC | `a89957db` | v6 | `4b8eaaca` at base review |
| JRC | `0ebfaffd`, `4d980b17`, `efc543e4`, `12a2c91a` | v8, v9, v10, v11 | `a89957db` at base review (6a) |
| JRC | `0834b623` | v11, consolidation needs v3 (#44) | `a89957db` at elicitation |
| JRC | `4933ff56` | none (cancelled before the discussion) | `a89957db` at base review |
| Stat | `6455e495` | v6 | fresh |
| Stat | `c4cbca44`, `1428af21` | v8, v10 | `6455e495` at base review (6a) |

- No run used discussion v7 (`rq1-fa-dialogue-v7` appears in no run).
- Health `d5ce31fb` was cancelled during consolidation and has no active needs. There are no
  Mobility or Geo runs.
- JRC and Stat runs used exactly the raw allowlists in `runtime-inputs.json` (checked by source
  name), so the raw evidence labels of v3 apply.
- The fetched data (227 distinct statements, run states) was checked against SHA-256 hashes
  computed in the page.

## What is scored

- Predictions: the run's active needs (machine output; no run has human decisions). Also the
  needs before the discussion (the 6a input, reconstructed from the run and checked against a
  run with no applied change in each lineage) and the frozen compact selection, which here
  equals the 6a input.
- Reference: the v3 atoms with `scored_by_default` whose raw input-evidence label is `supported`
  (primary: JRC 6, Stat 4) or `supported` or `partial` (secondary: JRC 12, Stat 8). Atoms that the
  staged inputs do not support (unsupported, uncertain) are left out of every figure.
- Sensitivities: settled requirements only (status `requirement`: JRC 5, Stat 1 of the supported
  atoms) and supported atoms without DCAT-AP restatements (JRC 3, Stat 1).
- The pair labels of the first mock (made on all scored atoms, 22 October) are reused: no
  eligible atom's statement or source passage changed in the adjudication; only JRC-6.4's status
  did (open issue to requirement).

## Pair labels

- Every statement seen in any run of a case (active, set aside, replaced, or in the compact
  selection) was pooled under random IDs, so reviewers could not tell runs or versions apart.
- Two reviewers (independent Claude subagents, different presentation orders) labelled every
  atom against the whole pool: `equivalent`, `narrower`, `broader`, `partial`, `conflicts`;
  unlisted pairs are unrelated. Protocol: `judge/INSTRUCTIONS.md`.
- A third subagent adjudicated every pair the two labelled differently.
- Agreement is reported on the pairs either reviewer flagged, and for equivalence over the full
  atom × statement grid.

## Scores

- Only `equivalent` earns credit. Matching is one-to-one (maximum bipartite matching between
  atoms and needs, computed separately for each denominator): a need counts for one atom only,
  and duplicate needs cannot raise recall.
- Atoms without an equivalent need are reported by their best other label (broader, narrower,
  partial) and are not counted as recovered.
- Bounds: strict (both reviewers said equivalent) and lenient (either said equivalent).

## Not done

- No human reviewers or adjudication; no blinding of the adjudicator to the reviewers' labels.
- No precision: needs related to no atom are counted but not classified as novel, unsupported or
  out of scope.
- JRC and Stat are development cases. Their outputs had been viewed before v3 was frozen, and
  earlier mock checks inspected the closest needs. Nothing here is a test result.
