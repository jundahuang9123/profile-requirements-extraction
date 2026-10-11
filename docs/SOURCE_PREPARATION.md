# Preparing sources for an RQ1 run

You do not need to read every document end to end, manually identify stakeholders,
or retype PDF paragraphs before a run. Supply the originals and enough context to
decide what belongs in the corpus. A short overview supports that initial decision;
it is not evidence that the final extracted requirements are complete or correct.

## Before upload

- Give each document a recognizable title and retain its URL, publisher, date and
  version when known. Unknown authority should stay unknown.
- Skim the abstract, introduction, contents or executive summary to check scope.
  State your domain, intended users and competency questions when available.
- Distinguish stakeholder needs, normative specifications, examples and background
  material. A paper reporting a use case is an indirect account, not an interview.
- Keep benchmark reference requirements separate from runtime input. References
  must not guide source preparation, stakeholder selection or extraction.
- Prefer a text-searchable original PDF. A scan with no usable text needs an OCR
  transcript with its provenance retained. The current parser does not perform OCR.

## What the software does

The parser retains original bytes and a versioned extracted-text representation.
PDF evidence is grouped into bounded passages within pages, with source offsets.
It preserves line breaks and hyphens rather than silently rewriting quotations.
The role selector distinguishes documented, inferred and proposed perspectives.
It checks quotations and records one bounded citation correction attempt when
needed; unresolved citations stop selection visibly rather than becoming accepted
stakeholder evidence. Selecting roles does not prove actual stakeholder endorsement.

## What to review

1. Check the source list, eligibility and parsing diagnostics. Inspect a few
   extracted passages per document, especially a dense page or a table, to catch
   obvious reading-order or missing-text problems. A parse success flag only means
   usable text was obtained, not that the entire document was interpreted correctly.
2. Review the short stakeholder panel: roles, remit, documented/inferred/proposed
   labels and supporting excerpts. Correct obvious omissions or unsuitable roles.
3. Review candidate requirements using their linked passages. Prioritize failed
   checks, weak support, disagreements and mandatory claims, while also sampling
   apparently clean items to look for systematic errors. To claim a fully validated
   baseline, assess every requirement you accept; sampling alone cannot establish it.

A future automatic source brief can reduce initial reading effort by summarizing
purpose, scope, actors and parsing warnings with page links. It should remain an
orientation layer; extraction and review must still reach the original passages.
The current UI provides source diagnostics, the role panel and evidence inspection,
not a complete automatic source-brief feature.

## After a parser or selector change

Re-upload the original source under the new parser and create a fresh run. Historical
sources, snapshots and failed attempts remain unchanged and inspectable. Resuming
an incomplete run under a different selector policy is rejected to prevent mixing
methods in one audit trail. Keep pilot databases and screenshots outside the repo.
