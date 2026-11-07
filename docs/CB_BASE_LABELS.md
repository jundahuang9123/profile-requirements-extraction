# Base labels for closed-book needs

`scripts/cb_base_labels.py` (policy `rq1-cb-base-labels-v1`) labels the needs of a closed-book
(CB) run against the pinned base catalogue. CB runs are made by `scripts/closed_book.py`
(docs/CLOSED_BOOK.md). PM and S runs get their base labels inside the workflow.

The design (Junda, option 1):

- CB needs are labelled by the workbench's procedural base review (`base_review` `expert_v1`,
  `workflow/base_review.py`).
- The prompts, the model and the pinned catalogue are those of the PM run the CB run is paired
  with.
- The only difference is that CB needs have no source passages. So the verdict
  `domain_use_of_base`, which needs a cited passage, cannot be given.

The script lives outside `workflow/` and imports the workbench read-only, so the implementation
hash stays `fd154ddc52eb2d87`. It writes nothing to the workbench store. It imports
`scripts/closed_book.py` for the client set-up, the endpoint comparison, the sanitising of
errors and the writing of records, so these are the same as for CB runs.

## Running it

The provider is configured by the `RRS_LLM_*` variables, as for `closed_book.py`. The model and
the reasoning effort are copied from the PM run.

```bash
cd <checkout>
PY=/home/user/profile-requirements-extraction/.venv/bin/python
# 1. look at the requests first: no model call, no provider needed
$PY scripts/cb_base_labels.py --cb-record <case>-cb-run1.json --store <workbench store>.sqlite3 \
    --out <case>-cb-run1.labels-preview.json --prompts-only
# 2. the labels
$PY scripts/cb_base_labels.py --cb-record <case>-cb-run1.json --store <workbench store>.sqlite3 \
    --out <case>-cb-run1.labels.json --allow-live-provider
```

`--store` is the workbench store that holds the PM run (the whole store or a saved subset). It
is opened through a read-only URI (`mode=ro`, `query_only`). `--immutable` adds `immutable=1`;
use it only for a store that no process writes, for example when its server is down. The PM
run is the CB record's `pm_run_id`. `--run-id` may name it again; another run is refused.

`--prompts-only` records the first review request of every batch, as the OpenAI-compatible
client sends it, and the check text. The check requests, and any correction, depend on the
answers, so they are not in the preview.

An existing `--out` is never overwritten. `--resume` completes it: every saved answer and every
call is kept, and only the missing calls are made. A completed record is left as it is.

Exit status:

- 0: completed. Every need has a label (see "Labels").
- 1: incomplete. A call failed (transport, authentication or provider). Its error is recorded,
  and `--resume` repeats the call.
- 2: refused before any call. Nothing was called.
- 3: the record could not be written after calls were made. The record at `--out` holds what
  was written before.

Ctrl-C writes the record with status `interrupted` and raises the interrupt again. The call in
flight is recorded with status `interrupted`; `--resume` repeats it.

## Refusals

The script refuses, before any call:

- a CB record that is not of kind `closed_book_run`, is not `completed`, or has needs without a
  distinct `need_id`, a statement, a condition or a scope;
- a PM run other than the record's `pm_run_id`;
- a PM run whose base review is not `expert_v1`;
- a CB record and a PM run that pin different bases (`base_profile_id`, `base_profile_sha256`);
- a pinned catalogue that is not the one the PM run pinned. The workbench's
  `pinned_catalogue()` checks the registry's SHA-256 and the catalogue hash;
- a replacement (see "Adaptations") that does not match exactly once in the workbench text;
- a problem message of the workbench's `verdict_errors()` that is no longer the one a feedback
  replacement names. A probe on a synthetic need checks each one (`diagnostics.feedback_check`);
- a parity check that fails (see "Parity with PM");
- PM calls of one step made with different models or at different endpoints.

Before model calls it also refuses:

- a run without `--allow-live-provider`;
- a parity check that did not pass;
- a client that is not the PM model and effort of its step;
- an endpoint other than PM's, unless `--allow-other-endpoint` is given;
- a `--resume` record that is not a record of this labelling, or was written by another
  version of the script, another workbench implementation, another model, another endpoint
  comparison or another `--allow-other-endpoint` setting.

## What stays as PM's

The script builds the requests as `review_base()` does. It calls the workbench's own
functions for each part:

- the system texts `REVIEW_SYSTEM` and `CHECK_SYSTEM`, changed only as listed below;
- the payload (`make_payload`, `make_check_payload`): the policy, the phase, the base block
  (profile, catalogue hash, review fields, the whole index and the offered entries), the needs
  and the excerpts. The aliases N, B and E are the workbench's;
- the batches: four needs in ID order, halved while a payload is over the budget
  (`MAX_PAYLOAD`), a single need over it not sent;
- the contracts `BaseReview` and `BaseReviewChecks`, 4,000 output tokens per call and no
  client schema correction;
- two attempts per batch: an answer and one correction (`correction()`), which shows the
  rejected answer and its problems;
- the recovery: rows of a failed batch that are valid alone are kept and checked; every other
  need is reviewed alone. The same for checks;
- the validator `verdict_errors()` and the check `check_errors()`;
- the labels (`apply_verdict()`): a checked `restates_base` sets `covered_by_base`; a failed
  check adds `base_relation_review`; a need not reviewed gets `base_review_pending`.

Each CB need is given to the workbench as a record with its statement, condition and scope.
The obligation is `unknown`. It has no evidence links, no F/A scope (`actor` and `task` are
null), no classifier result and no earlier base relation. So the payload has no excerpts, and
the need's `classifier` field is the empty state (`need_class` null, no matched entries,
`covered_by_base` false). PM's payload has the same state for a need the classifier did not
label. The phase is `before_discussion`, PM's full review: CB needs, like PM's machine
inventory, have had no discussion.

The workbench keeps checkpoints in the run. The script keeps them in the record
(`checkpoints`), with the same keys and attempts. The workbench's checkpoint identity includes
the endpoint; the script's leaves it out.

## The rule for domain-use verdicts

A CB need never gets `domain_use_of_base`.

- The CB texts say that this verdict needs a cited passage and cannot be given. The case PM
  labels a domain use (an entry names the information and the need adds a value, condition,
  unit, stronger obligation, other resource class or narrower meaning) goes to `uncertain`. The
  model then cites the entry and gives the addition and its kind.
- A `domain_use_of_base` answer is refused by the workbench's own `verdict_errors()`. That
  check asks for a cited excerpt of the need, and a CB need has none. The correction says why
  (see "Adaptations"). Then the workbench's recovery runs unchanged.
- Every refused answer is counted per need (`domain_use_refused`). A need whose answers keep the
  verdict through all its attempts ends `not_reviewed` (`invalid_output`).
- A checked `uncertain` verdict that cites an entry and states an addition is reported as
  `addition_without_passage`. It is CB's counterpart of a domain use.

## Adaptations

Each replacement must match exactly once. Every sentence not listed stays as PM sends it. The
check keeps its sentences on `domain_use_of_base` for parity: no domain-use verdict reaches the
check.

Review text (`REVIEW_SYSTEM`):

| PM text | CB text |
| --- | --- |
| Judge each offered need only against the pinned base catalogue and its cited passages. | Judge each offered need only against the pinned base catalogue. No source passages are given. |
| Cite the passage stating the addition. | It needs a cited passage stating the addition, so it cannot be given here. |
| when an entry names it and the need adds a value, condition or narrower meaning, the verdict is domain_use_of_base. | when an entry names it and the need adds a value, condition or narrower meaning, the verdict is uncertain. |
| uncertain: the catalogue text is insufficient. | uncertain: the catalogue text is insufficient, or an entry names the information and the need adds one of the additions above; then cite the entry and give the addition and its kind. |

Check text (`CHECK_SYSTEM`):

| PM text | CB text |
| --- | --- |
| Independently check each verdict against the pinned catalogue (base.index and base.entries) and the source passages. | Independently check each verdict against the pinned catalogue (base.index and base.entries). No source passages are given. |
| for uncertain the catalogue text is indeed insufficient. | for uncertain the catalogue text is indeed insufficient, or a cited entry names the information and the need indeed adds the stated addition. |

Feedback: the problems `verdict_errors()` reports after a need's ID, as the correction shows
them to the model.

| PM problem | CB problem |
| --- | --- |
| cite only this item’s excerpts, each once. | cite no excerpt: no passages are given. |
| matched entries omit a condition. Cite the entries that state it, or answer domain_use_of_base with the condition as a cited addition. | matched entries omit a condition. Cite the entries that state it, or answer uncertain with the condition as the addition. |
| source-cited addition and kind required. | domain_use_of_base cannot be given: no passages are given. Answer uncertain, cite the entry and give the addition and its kind. |

The record lists every adaptation (`adaptations`) and holds both CB texts (`system_texts`).

## Parity with PM

Two checks keep the PM texts equal to what PM sent:

- A test runs the real `review_base()` on a synthetic run, through the workbench's call
  recording. With PM's texts and validator, the script sends exactly the same requests, in the
  same order, and gives the same labels. With the CB texts, only the listed changes differ.
- For each run, the script compares the digest of each PM text, computed as the workbench
  records `system_hash`, with every base-review and check call the PM run recorded (run part
  `model_calls`). A correction appends the workbench's correction to the text, so it is left
  out: the script reads the run's checkpoints (`stakeholder_audit`) and leaves out every later
  attempt. A failed call that no checkpoint lists is left out too. Any other differing call
  refuses the run. A run with no such call follows `derived_from` to the run it came from.
  The result is in `diagnostics.parity_check`.

The workbench implementation hash is recorded for information. When it is not
`CHECKED_IMPLEMENTATION`, the code the replacements were last checked against, the script
warns. The parity check decides.

## Calls

The calls go through the workbench client, one client per model setting. The model and effort
of each step (`base_review`, `base_review_check`) come from the PM run's recorded calls of that
step. When the run records none, they come from `step_models` and `step_model_options`. The
script checks the configured client against them.

The endpoint is compared with the one PM's calls of that step record, never recorded
(`diagnostics.endpoint_matches_pm`).

Each call is recorded as `closed_book.py` records calls: the system prompt as sent (with the
JSON schema for the OpenAI-compatible client), the user payload, the SHA-256 of each, the
status, the parsed output, token usage, finish reason, the client's audit of its generations,
latency and a sanitised error. A call also records its step, batch key, attempt and purpose,
and the workbench digests `system_hash` and `context_hash`. The record never holds an API key
or the provider URL. An error message is recorded without the endpoint, its host, the key, any
`Bearer` token and any URL.

## Labels

`labels` has one entry per CB need, in the record's order:

- `need_id`, `role_id`, `statement`, `condition`;
- `covered_by_base`: true for a checked `restates_base`, else false; null while not labelled;
- `base_label`: `covered` or `working`, as the benchmark scorer splits PM needs;
- `label_class`: `restates_base`, `new`, `addition_without_passage`, `uncertain`,
  `check_failed`, `not_reviewed`, or `not_labelled` (only in an incomplete or prompts-only
  record);
- `domain_use_refused`: the refused domain-use answers for this need;
- `processing_flags` and `base_relation`, in the shape PM runs store them
  (`requirements[].processing_flags` and `.base_relation`). `base_relation.model` has no
  endpoint.

`revision_info` has the shape of the scorer's `private/revision-info.json` for a PM run:
`run_id` (the CB run), and per need `lifecycle` (`active`), `covered_by_base` and `parents`
(empty). It lists only labelled needs.

`counts` gives the needs, covered, working and not labelled, the needs per class, the refused
domain uses, the first review batches and the calls by step.

## Reading the labels

- CB needs had no classifier. PM's reviewer sees the classifier's label and matches for most
  needs; CB's sees the empty state. The workbench's `effect` is relative to that state:
  `restates_base` gives `flag_added`, `new` gives `agree`. No review question is written.
- `uncertain` holds two cases in CB: the catalogue text is insufficient, or the need adds to
  an entry (`addition_without_passage`). Compare CB's `addition_without_passage` with PM's
  `domain_use_of_base`, and CB's other `uncertain` with PM's `uncertain`.
- For the covered/working split, the rule changes nothing: a domain use, `new` and `uncertain`
  are all working.
- The labels use the CB statement as the CB record holds it. The template-word cleanup
  (`reports/benchmark-tools/template-cleanup/`) changes only what the blind reviewers see, as
  for PM.

## Tests

`tests/test_cb_base_labels.py` builds a synthetic PM run and reviews it with the real
`review_base()` and a scripted model, through the workbench's call recording. It checks:

- the PM texts are what `review_base()` sends, and the parity check passes on the recorded
  calls, leaves out corrections and failed calls, refuses another text and follows a derived
  run;
- with PM's texts and validator, the script sends what `review_base()` sends, in the same
  order, and gives the same labels, also when batches are halved and when a check fails for a
  batch;
- with the CB texts, only the listed changes differ; each matches once, and a changed
  workbench text or problem message stops the script;
- a domain-use answer is refused and counted; the need ends `addition_without_passage` after
  the correction, or `not_reviewed` when it keeps the verdict;
- the labels have the scorer's shape and follow the checked verdict;
- calls are recorded without the endpoint or the key, and a failed call gives an incomplete
  record;
- `--resume` keeps the saved answers, continues the call sequence and refuses another record;
- an interrupt writes an `interrupted` record;
- the model comes from the recorded calls and must match the client; another endpoint needs
  `--allow-other-endpoint`;
- the CB record and its base are checked; the store is opened read-only;
- `--prompts-only` needs no client and records the first requests of a run;
- the system text as sent is what the real client posts (fake HTTP);
- the exit codes 1, 2 and 3;
- this document lists every adaptation;
- the workflow implementation hash is still `fd154ddc52eb2d87`.
