# How the reference sets were made

A record of the steps behind version 3. Nothing here is read by the workbench or needed for scoring.

- `v2-completion/`: Claude's completion pass of 22 October 2026, frozen as delivered (the files inside `reference-requirements-v2.zip`, SHA-256 `4b502ccd674fcf13c9cde21d743f3db64fff413e3292a6bd830f6bf3dbf65bf8`), plus its review table. Version 3 merged it with the v1 rows and the PR #45 audit; its rows keep their IDs in v3.
- `v1-comparison-2026-10-22/`: the coding and comparison of the 75 published rows (problem, derivation, response) that preceded the completion.
- `v2-vs-pr45-comparison/`: the item-by-item comparison of the completion pass with the PR #45 audit (22 October) that preceded the merge; `../coverage-ledger.csv` records where each item finally went.
- `labelling/`: the input-evidence labelling of 22 October: the atom packets the Claude subagents saw (`packets/`), their raw outputs (`raw-outputs/`) and their prompts. Every quotation was then checked by program and the labels were merged into the case files.
- `independent-check/`: the prompt of the independent source check; its findings and their resolution are in `../INDEPENDENT-CHECK.md`.
- `build-scripts/`: the scripts that built v2 (`v2/`) and v3 (`v3/`, including `adjudication_2026_10_23.py`, which applies the 23 October adjudication). They are a record, not runnable here: they use absolute paths of the build workspace and also read the PR #45 audit (commit `7fec154`) and pdftotext extractions of the reference documents, which are not stored in this folder.

## v2 files

| File | SHA-256 |
|---|---|
| `geodcat/reference-requirements/alignment-requirements-v2.json` | `2184347f82a737c9d6d8e71e6bb232cf107e6fb92ebc396bd43f1879f845dded` |
| `healthdcat/reference-requirements/curated-requirements-v2.json` | `61ad451cd105fadb425bf16486082bd1ee902a912aa680beeb332af515986166` |
| `jrc-research/reference-requirements/core-requirements-v2.json` | `8b50661d9513d8e995bb0782ab444170d544a854c7104d28d6c7a4930eaafc19` |
| `reference-completion-review.csv` | `03d48a9e360f44358292dcecec4e41c817a5942df8c25ff602f0cbce37a000a8` |
| `statdcat/reference-requirements/requirements-and-resolutions-v2.json` | `82bc00478a53b046f6dd95fd9911c34641c5afe6991824683b5d94ca2dbab262` |
