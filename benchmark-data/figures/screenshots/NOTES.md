# Workbench screenshots for the RQ1 paper: notes

These are the capture notes for `paper/`, `record/`, `data/`, `manifest.json` and `contact-sheet.pdf` in this folder. `scripts/capture_figures.cjs` made every file; the content choices are in `scripts/capture_figures.ids.json`.

## The run used, and why

- **Run:** `run-e8bc1d3725a54664991c46d39ee1aa74`, titled *"StatDCAT re-normalized — v5 writer fold + speed fixes (PR #55, #56; main aefc12a) — GPT-OSS only — confirmation run — 30 Oct 2026"*.
  - This is the StatDCAT-AP confirmation run of the frozen configuration, the spec's first choice under Rule 1.
  - Its status is `awaiting_human`. No human assessment, decision, restoration or edit is recorded on it.
- **Policies:** the script checks these against Rule 1 and stops if any differs. All match:

  | Step | Policy |
  |---|---|
  | Grouping | `rq1-need-semantic-grouping-v3` |
  | Need statement | `rq1-need-statement-v5` |
  | Profile scope | `rq1-profile-scope-v9` |
  | Proposal support | `rq1-proposal-support-v2` |
  | Discussion (all 82 cases) | `rq1-fa-dialogue-v14` |

  The other saved policies are in `manifest.json` (`policy_versions`).
- **Derivation:** the run was derived at the extraction step from `run-6455e495a12c4cbbb5664239a942d776` (StatDCAT fresh, 22 Oct), the same way as the Stat guard runs.
  - Its steps 1–3b therefore show that run's sources, evidence units, roles and extraction.
  - Its extraction model calls stay in that run, and a need's trace follows the derivation back to them.
- **No other run appears.** No mobilityDCAT-AP or GeoDCAT-AP run is in the store the screenshots were taken from (see below).

## How the shots were taken (Rule 2)

- **A copy of the store, never the live one.**
  - The run store keeps a snapshot of the workflow store from the end of this run: `store/workflow-cloud-2026-10-31-v5-stat-confirm-done.sqlite3.gz`, seven parts. All part checksums and the whole-file checksum `74807169…f6b7` were verified.
  - The snapshot was unpacked to memory. A new store was built from it holding only:
    - this run and the run it was derived from;
    - their corpus snapshot, its 2 sources and 60 evidence units, and their role manifest.
  - That is 66 objects, 4,200 run parts and 12,580 events.
- **Server:** the service and the built UI ran on that copy, on its own port, with `RRS_LLM_PROVIDER=disabled`. Opening a page cannot start a model call.
- **Workbench:** commit `0e3e704` (UI and service, unchanged), built with `npm run build`.
- **Nothing saved changed.**
  - The only clicks open the evidence inspector, a need's review page, a trace's "Full chain" and one saved result. All of them only read.
  - A digest of every row of every table of the copy was taken before and after the capture, and again after the last re-capture. All three are identical: objects 66 rows (`9cb605610cf2…`), events 12,580 (`999a06de43f0…`), run parts 4,200 (`ad0bd79a4995…`), run state 2 (`032c96b4c7ed…`), commands and part history empty.
- **Capture settings:**
  - Playwright Chromium 1.56.1, headless.
  - Light colour scheme, `deviceScaleFactor` 2, locale `en`, reduced motion.
  - Network quiet and fonts loaded before each shot.
  - Every `<details>` closed except those a shot opens. Each shot's list is `details_opened` in the manifest.
  - Element screenshots (`locator.screenshot`) as PNG.
- **Widths:** each shot exists at 600 px (`paper/`) and 1000 px (`record/`).

## Hidden by CSS before capture (Rule 3)

- **On every page:**
  - `header.rq1-header` (project name, and a link naming a person);
  - `footer.rq1-status`;
  - `details.provider-settings` (`ProviderSettings`, which shows the provider host);
  - `details.workflow-step-models` (`StepModelsSettings`);
  - scrollbars, focus outlines, animations and the caret.
- **S09 only:** the panel's list of the 76 compact representatives. That list makes the panel about 29,000 px tall at 600 px; it is visible in `record/page-consolidation@1000.png` and in the data.
- **Text checks:**
  - The visible text of every shot was scanned for personal names, GitHub, home or temp paths, database file names, the provider host, API keys, bearer tokens, `localhost` and e-mail addresses. The result per shot is `forbidden_text` in the manifest: nothing was found in any of the 93 PNGs (60 in `paper/`, 33 in `record/`, full pages included).
  - Web addresses in visible text (`url_hosts`) are only `example.org`, inside quoted W3C examples.
  - The "Imported use cases · author, date and purpose" details does not exist on a saved run's Sources page, and this run has no use cases.

## Content chosen (Rule 6)

| Item | ID | Why |
|---|---|---|
| Evidence unit (S02) | `eu-7f93da009c0775ace8b6ddb9` | The unit cited by the traced need below, in `w3c-dcat-2014.html`. |
| Grouped need (S04b, S06) | `rev-324e3b9486b4b22fc0a90129` | Grouped from two proposals, one by a selected role and one by the shared extractor. Its base label was removed by a checked reviewer verdict. Rank 1. |
| Rejected proposal (S04c) | `rev-2a370919dcdcc65bb0ad1867` | The run's only proposal rejected by proposal support and judged again. The second judgment confirmed "not supported", so it is set aside as not supported by its quote. |
| Need covered by the base (S08) | `rev-b09ac95ce086f614b392d53a` | Labelled as restating the base, confirmed by the base reviewer, with source-linked dataset kinds. |
| Need with a disputed judgment (S05, S11, trace in `data/`) | `rev-93437ef84fc283334ed629cc` | The two find/access judgments disagree (`fa_scope` confirmation outcome `disputed`). Labelled a domain use of the base. Discussed in `case-705bb404c208a0f00b179759` and deferred to human review with a question. The trace chain is complete. |
| Discussion case (S10) | `case-9c4ea08f602b6aa07902ad4c` | One need, kept set aside by the mediator (outside scope: not for finding or access), with a question for a person. Two experience claims excluded and two admitted, each with a reason. Chosen among the 19 cases that meet Rule 6 because its texts are short. |

## Shots that differ from the specification, and UI differences from Sect. 3

- **S01, Sources & scope.** Split into the base-profile panel (S01a) and "Frozen input sources" (S01b).
  - "Material retained outside the evidence corpus" is not shown: this run has no excluded material.
  - "Version and diagnostics" and "Imported use cases" exist only on the form that starts a new run. A saved run lists its source names.
  - "Scope & competency questions" is empty: the run has no user tasks.
- **S03.** The stakeholder panel is about 3,600 px tall at 600 px, so it is also cut into appendix-sized parts.
- **S04, extraction.** The extraction page of a needs run shows extraction per role: the routing of evidence units to the selected roles and the shared extractor (S04a). It has no proposal cards, and "Show set-aside proposals" exists only for runs whose output is not needs. A proposal is shown instead in two places:
  - as a member of the need it was grouped into (S04b: its statement, its role, its source check and its cited quotations);
  - as a set-aside item with its reason and the restore control (S04c).

  The second support judgment of the rejected proposal is saved but this UI does not display it: the set-aside item shows the first judgment's rationale. The judgment is in the saved run, and the trace of a need lists such decisions.
- **S05, original-source checks.** The verification page has no per-quotation view. The shot is the saved original-source check of the traced need's record. It was opened from the need's trace in the result drawer, where each cited quotation shows its evidence unit, status, `quote_start` and `quote_end`.
- **S06, need.** The need card is 641 px tall at 600 px, so for a main-text strip it is also cut into three parts of 211, 200 and 230 px (S06-part1…3; the last part includes the card's bottom edge).
- **S10, discussion.**
  - The case's dialogue steps are saved as one JSON record per step ("Saved dialogue steps"). Those stay closed.
  - The stakeholders' positions are the messages below the mediator outcome.
  - No part of the case fits a 220 px strip at 600 px. Four crops are given, as close as the case allows:
    - the mediator outcome with the human-review question (S10-strip1, 869 px);
    - a position with an excluded claim (S10-strip2, 307 px);
    - a position with an admitted claim (S10-strip3, 283 px);
    - the mediator action alone: set aside, its reason and rationale (S10-strip4, 248 px).
  - The appendix version (S10-appendix) has the complete mediation audit open and is cut into page-sized parts.
- **S11, human review.**
  - In this UI, "Cited evidence" with unit identifiers sits inside "Edit or split", which is an editor, so it stays closed.
  - The shot shows the cited quotations with their inspect buttons, and the trace's sources and decisions.
  - "Semantic and quality assessment" and the trace's "Full chain" are open. No decision is recorded.
- **S12, run trace.** `RunTraceView` holds the complete-trace download and the need picker. "Saved needs policies" is in the "Needs processing progress" panel, and "Saved history & metrics" is a panel of its own. They are shot separately as S12a–c, on the discussion step.
- **S13, validated baseline.** Nothing is published on this test run (no human decisions). The shot shows the page with the publish button disabled.
- **Full pages in `record/`.** Pages longer than 6,000 CSS px are cut at 6,000 px. Their manifest entry gives the page's full height.
- **JSON boxes.** Some panels show saved JSON in a box that scrolls inside the panel: the evidence inspector (S02), "Saved history & metrics" (S12b), and the run trace's saved inputs and results, which stay closed in S12c. A shot shows the top of such a box only.
- **"Download this step".** This button is in the toolbar of every step. The step download in `data/` is exactly what it downloads (`/runs/{run}/stages/deliberation?download=true`).

## Data (`data/`)

- **`need-trace-rev-93437ef84fc283334ed629cc.json`:** the trace of the S11 need (`rq1-need-trace-v1`), as the trace endpoint returns it.
- **`stage-7-deliberation.json`:** the download of step 7 (discussion).
  - The downloads of steps 6, 7 and 8 together are 17.5 MB (3.7, 12.3 and 1.6 MB), over the 5 MB limit, so only this one and the trace are kept, as the specification says.
  - The download names the model provider's endpoint in every model call (`model.base_url`, 991 times). That host would point to the authors' region, so in this copy it is replaced by `[provider endpoint withheld for double-blind review]`. Nothing else is changed.
  - Checksums: as downloaded `56d76dd42893c1ed65ba250e13d49340882429ff260b0d8b0157ce84e70372d5`; as published `6df3d726b96a3ea67c696f18d91b9eb48bdb83a08bb99dd49a88ceb4d20b353b`.
  - Other names and addresses in the download come from the quoted W3C sources: a reference author, and `public-gld-comments@w3.org`.

## Checks before the PR

- **No forbidden text** in any PNG, `record/` included: see above, and `forbidden_text` per shot. I also looked at the shots: the header, footer and provider settings are absent from the full pages in `record/`.
- **Smallest text:** at least 6 pt on the contact sheet for every `paper/` panel. The smallest is 6.34 pt, in S05 (the result drawer); all others are 6.5 pt or more (`min_font_pt_at_12_2cm` in the manifest).
- **Policy versions:** match Rule 1, as checked by the script.
- **`git status`:** shows only `scripts/capture_figures.cjs`, `scripts/capture_figures.ids.json` and this folder.
