# StatDCAT-AP

Freeze **v1.0.0, 2016-12-15**, not the 2019 revision or 2026 redevelopment. The
[official SEMIC repository](https://github.com/SEMICeu/StatDCAT-AP) preserves the original
licensed 94-physical-page report. It remains under `reference-requirements/`, since it
contains both requirements and modelling solutions.

The strict raw allowlist includes W3C DCAT (2014) and RDF Data Cube (2014). SDMX and
ESMS are explicitly documented background sources, but their exact original full
artifacts are citation-only. The served DCAT-AP 1.1 PDF has a later 2017 metadata date
and is excluded from the 2016 runtime corpus.

The report's §5 use cases have a separate factual synopsis in
`input-raw/reconstructed-use-cases.json`. This is **retrospective evidence from a final
report**, not recovered original use-case submissions, and is disabled in the strict
allowlist. It may support an explicitly named retrospective variant after reviewer
inspection. Never supply the full report as raw evidence.

`reference-requirements/requirements-and-resolutions.json` provides **seven scoped
entries** from §7.2: dimensions, attributes, quality, visualisation, series count,
measurement unit and time-series representation. The final entry is representation
guidance rather than a new-property requirement. Original resolution terms are retained
for secondary traceability, not for RQ1 property-name matching. This does not enumerate
all conformance obligations in the profile.

The original landscape spreadsheets, early working-group submissions and complete
historical issue-resolution corpus were not recovered. This is a **partial standards
benchmark** with a richer evaluator-side reference; a high raw recovery score cannot be
assumed from the available standards alone. No B consolidation experiment is enabled.

See [manifest](provenance/manifest.json), [gaps](provenance/GAPS.md),
[methodology](../BENCHMARK-METHODOLOGY.md), and [runtime allowlists](../runtime-inputs.json).
