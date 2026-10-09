# HealthDCAT-AP

This case freezes the HealthData@EU pilot's **2023/2024** evidence and September 2024
reference, rather than mixing it with current profile releases. The official
[Health Data Hub project page](https://health-data-hub.fr/page/healthdataeu-pilot)
links to archival Zenodo deposits. Their explicit CC BY 4.0 metadata is saved alongside
the reports; manuscript dates and March 2025 deposit dates are distinguished.

## Available corpus and separation

`input-raw/` includes [M6.1 landscape analysis](https://zenodo.org/records/15089787)
(2023-03-30), the 2022 EHDS proposal, GDPR, and pre-2023 DCAT/DCAT-AP baseline documents.
The report describes the catalogue landscape, forms and sandbox before TWG design.
The exact minor DCAT-AP 2.1.1 baseline is a curator selection; M6.1 names v2 generally.

[Full TWG M6.2 minutes](https://zenodo.org/records/15095515) (2024-01-31) are kept in
`provenance/`, because they mix input, candidate properties, decisions and final drafts.
`input-preconsolidation/twg-observations.json` supplies only eight scoped curator
summaries of needs/discussion topics from the 2023 sessions. It is a **partial** B corpus,
not the complete EU Survey responses or the original stakeholder submissions.

`reference-requirements/` contains [D6.2](https://zenodo.org/records/15085025)
(2024-09-30), the D6.1 delivery document (a short deliverable, not a complete standalone
specification), and **16 curated rationale requirements** linked to D6.2 sections. This
subset is not an official enumerated complete gold set and requires independent review.
The [D6.2 functional-analysis annex](https://zenodo.org/records/15089825) is provenance-only:
it follows the extension and its personas are not assumed independent upstream evidence.

D6.2 uses the 2024 EHDS compromise with provisional article numbering. The 2025 adopted
regulation is preserved only in provenance. Do not score the historical reference against
that later law without a separately versioned experiment.

## Limitations

Original survey exports, complete independent use-case submissions, private recordings
and missing stakeholder conversations were not recovered. D6.2's methodology includes a
September–December 2024 statement despite its September 2024 manuscript date; use the
actual dated 2023 M6.2 sessions rather than assuming that sentence establishes chronology.
Some PDFs say all rights reserved while the later deposits explicitly declare CC BY 4.0;
both notices and the deposit metadata are retained. Current release 5 is not silently
substituted for the 2024 profile.

See [manifest](provenance/manifest.json), [gaps](provenance/GAPS.md),
[methodology](../BENCHMARK-METHODOLOGY.md), and [runtime allowlists](../runtime-inputs.json).
