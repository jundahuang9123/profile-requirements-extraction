# Mock benchmark on evidence-eligible atoms: discussion v6–v11 against reference sets v3

Machine-made: two blind AI reviewers and an AI adjudicator, no people. JRC and Stat are development cases; nothing here is a test result. Reference: v3 with the 23 October adjudication (commit 671c60a). Only atoms that the staged raw inputs support are scored: `supported` (primary) or `supported` or `partial` (secondary). Method: `METHOD.md`.

## Key results

Recovered atoms (equivalent, one-to-one) out of the eligible atoms.

| Version | JRC: supported (6) | JRC: supported or partial (12) | Stat: supported (4) | Stat: supported or partial (8) |
|---|---:|---:|---:|---:|
| before the discussion (6a input) | 1/6 | 1/12 | 1/4 | 1/8 |
| v6 | 0/6 | 0/12 | 1/4 | 1/8 |
| v8 | 0/6 | 0/12 | 1/4 | 1/8 |
| v9 | 1/6 | 1/12 | – | – |
| v10 | 1/6 | 1/12 | 1/4 | 1/8 |
| v11 | 1/6 | 1/12 | – | – |
| needs v3 (#44), before the discussion | 1/6 | 1/12 | – | – |
| needs v3 (#44) + v11 | 1/6 | 1/12 | – | – |

## Findings

- **Two eligible atoms are ever recovered**, both supported: JRC-1.1 (authors, by "Users can know the creator of a dataset.") and S-6.1 (unit of measurement, by "Users can know the units (years) of the measured values for each observation.").
- **JRC differs between versions by one need.** The v6 and v8 discussions set the creator need aside (0 of 6); v9, v10, v11 and the needs-v3 run keep it (1 of 6). Stat is 1 of 4 in v6, v8 and v10.
- **The missed supported atoms have only weaker needs.** JRC: lineage (JRC-2.1), primary versus alternative identifiers (JRC-6.3) and the DOI rule (JRC-6.4) get partial needs, identifier types (JRC-6.5) a narrower one, and an API pointer (JRC-8.1) none outside the needs-v3 run. Stat: start and end of a time series (S-7.1, S-7.2) get only "temporal coverage" (broader), the structure definition link (S-17.1) a partial need.
- **Every eligible Stat atom has a related need; three JRC atoms have none** in v9 to v11 (persistent identifiers JRC-6.1, API pointer JRC-8.1, API description JRC-8.2); the needs-v3 run adds partial needs for JRC-8.1 and JRC-8.2.
- **Settled requirements only:** JRC 0 of 5 (v6, v8) or 1 of 5 (v9 onward); Stat 1 of 1 (S-6.1 is its only supported atom with requirement status; the others are guidance).
- **Label caveat:** JRC-8.1 and S-17.1 may overstate "supported" in the way the adjudication's P1 describes (the inputs show the distinction or the link at another level, not the requirement). They were not relabelled, because they were checked after the results were seen. Without them, the supported figures would be JRC 1 of 5 and Stat 1 of 3.

## JRC

| Run | Discussion | Needs (covered / working) | Supported | Supported or partial | Settled requirements among supported | Supported, without DCAT-AP restatements | Supported or partial: only broader / narrower / partial / none |
|---|---|---:|---:|---:|---:|---:|---:|
| **before the discussion** (v6, v8, v9, v10, v11) | — | 62 | 1/6 | 1/12 | 1/5 | 1/3 | 2 / 1 / 5 / 3 |
| v6 `a89957db` | rq1-fa-dialogue-v6=49 | 61 (29 / 32) | 0/6 | 0/12 | 0/5 | 0/3 | 0 / 1 / 3 / 8 |
| v8 `0ebfaffd` | rq1-fa-dialogue-v8=52 | 58 (33 / 25) | 0/6 | 0/12 | 0/5 | 0/3 | 2 / 1 / 5 / 4 |
| v9 `4d980b17` | rq1-fa-dialogue-v9=46 | 61 (31 / 30) | 1/6 | 1/12 | 1/5 | 1/3 | 2 / 1 / 5 / 3 |
| v10 `efc543e4` | rq1-fa-dialogue-v10=47 | 65 (36 / 29) | 1/6 | 1/12 | 1/5 | 1/3 | 2 / 1 / 5 / 3 |
| v11 `12a2c91a` | rq1-fa-dialogue-v11=50 | 68 (36 / 32) | 1/6 | 1/12 | 1/5 | 1/3 | 2 / 1 / 5 / 3 |
| **before the discussion** (v11+needs-v3) | — | 80 | 1/6 | 1/12 | 1/5 | 1/3 | 2 / 1 / 5 / 3 |
| v11+needs-v3 `0834b623` | rq1-fa-dialogue-v11=65 | 85 (41 / 44) | 1/6 | 1/12 | 1/5 | 1/3 | 2 / 1 / 7 / 1 |

Atoms: E equivalent (credited), e* equivalent but its need is credited to another atom, b broader, n narrower, p partial, · none.

| Atom | Raw evidence | Status | Restates DCAT-AP | set aside upstream | before | v6 | v8 | v9 | v10 | v11 | set aside upstream (needs v3) | before (needs v3) | v11+needs-v3 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| JRC-1.1 | supported | requirement |  | · | E | · | · | E | E | E | · | E | E |
| JRC-2.1 | supported | requirement | yes | · | p | · | p | p | p | p | · | p | p |
| JRC-4.1 | partial | requirement |  | · | b | · | b | b | b | b | · | b | b |
| JRC-5.1 | partial | requirement | yes | · | b | · | b | b | b | b | · | b | b |
| JRC-6.1 | partial | requirement |  | · | · | · | · | · | · | · | · | · | · |
| JRC-6.3 | supported | requirement | yes | · | p | p | p | p | p | p | · | p | p |
| JRC-6.4 | supported | requirement |  | · | p | p | p | p | p | p | · | p | p |
| JRC-6.5 | supported | requirement | yes | · | n | n | n | n | n | n | · | n | n |
| JRC-7.1 | partial | open_issue |  | · | p | p | p | p | p | p | · | p | p |
| JRC-8.1 | supported | open_issue |  | · | · | · | · | · | · | · | · | · | p |
| JRC-8.2 | partial | open_issue |  | · | · | · | · | · | · | · | · | · | p |
| JRC-9.1 | partial | open_issue |  | · | p | · | p | p | p | p | · | p | p |

Reviewers on these atoms: 18 pairs flagged by either; agreement 0.833, kappa 0.671 on those; equivalence kappa over all 1632 pairs 1.0; 3 disagreements adjudicated, 0 unresolved.

## StatDCAT

| Run | Discussion | Needs (covered / working) | Supported | Supported or partial | Settled requirements among supported | Supported, without DCAT-AP restatements | Supported or partial: only broader / narrower / partial / none |
|---|---|---:|---:|---:|---:|---:|---:|
| **before the discussion** (v6, v8, v10) | — | 53 | 1/4 | 1/8 | 1/1 | 1/1 | 3 / 0 / 4 / 0 |
| v6 `6455e495` | rq1-fa-dialogue-v6=71 | 54 (16 / 38) | 1/4 | 1/8 | 1/1 | 1/1 | 3 / 0 / 4 / 0 |
| v8 `c4cbca44` | rq1-fa-dialogue-v8=63 | 51 (17 / 34) | 1/4 | 1/8 | 1/1 | 1/1 | 3 / 0 / 4 / 0 |
| v10 `1428af21` | rq1-fa-dialogue-v10=63 | 53 (21 / 32) | 1/4 | 1/8 | 1/1 | 1/1 | 3 / 0 / 4 / 0 |

Atoms: E equivalent (credited), e* equivalent but its need is credited to another atom, b broader, n narrower, p partial, · none.

| Atom | Raw evidence | Status | Restates DCAT-AP | set aside upstream | before | v6 | v8 | v10 |
|---|---|---|---|---|---|---|---|---|
| S-1.1 | partial | requirement |  | p | b | b | b | b |
| S-2.1 | partial | requirement |  | p | p | p | p | p |
| S-6.1 | supported | requirement |  | b | E | E | E | E |
| S-7.1 | supported | guidance | yes | · | b | b | b | b |
| S-7.2 | supported | guidance | yes | · | b | b | b | b |
| S-16.1 | partial | requirement | yes | p | p | p | p | p |
| S-17.1 | supported | guidance | yes | · | p | p | p | p |
| S-18.1 | partial | requirement | yes | p | p | p | p | p |

Reviewers on these atoms: 22 pairs flagged by either; agreement 0.773, kappa 0.56 on those; equivalence kappa over all 728 pairs 1.0; 5 disagreements adjudicated, 0 unresolved.

## What the discussion changed (eligible atoms)

| Case | Run | Atom | Before | After | Why |
|---|---|---|---|---|---|
| jrc | v6 | JRC-1.1 | equivalent | none | equivalent need set aside by the discussion: Users can know the creator of a dataset. |
| jrc | v6 | JRC-2.1 | partial | none | partial need set aside by the discussion: Users can know narrative descriptions that explain the resource, its methods or technical information for a dataset.; partial need set aside by the discussion: Users can know what typed relationships connect the resource to related objects for a resource. |
| jrc | v6 | JRC-4.1 | broader | none | broader need set aside by the discussion: Users can know what typed relationships connect the resource to related objects for a resource. |
| jrc | v6 | JRC-5.1 | broader | none | broader need set aside by the discussion: Users can know what typed relationships connect the resource to related objects for a resource. |
| jrc | v6 | JRC-9.1 | partial | none | partial need set aside by the discussion: Users can know narrative descriptions that explain the resource, its methods or technical information for a dataset.; partial need set aside by the discussion: Users can know what typed relationships connect the resource to related objects for a resource. |
| jrc | v8 | JRC-1.1 | equivalent | none | equivalent need set aside by the discussion: Users can know the creator of a dataset. |
| jrc | v11+needs-v3 | JRC-8.1 | none | partial | partial need added by the discussion: Users can know the accepted interfaces through which the JRC data can be accessed. |
| jrc | v11+needs-v3 | JRC-8.2 | none | partial | partial need added by the discussion: Users can know the accepted interfaces through which the JRC data can be accessed. |
