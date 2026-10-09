# JRC research / DCAT-AP-JRC sanity case

The reference is the JRC-authored November 2016 workshop paper
[Using DCAT-AP for research data](https://www.w3.org/2016/11/sdsvoc/SDSVoc16_paper_27).
`reference-requirements/core-requirements.json` preserves its **five explicitly enumerated
core needs** as curator paraphrases: authors, lineage, usage guidance, scientific
publications and input datasets. Adopted terms are evaluator-side traceability only.

Raw input includes the rights-cleared **2015 JRC Data Policy**, W3C DCAT (2014), and a
factual synopsis of DataCite **3.1 (August 2015 documentation)**. The JRC paper documents
DataCite as input, but does not establish its exact minor version. Our particular 3.1
selection and synopsis are labelled curator reconstruction. The full historical DataCite
PDF is citation-only because redistribution rights were not established from that PDF.

The currently served DCAT-AP 1.1 PDF contains 2017 metadata, so it is provenance-only.
The JRC paper itself contains both its answers and modelling decisions; it must never be
a raw input. Its original full-text redistribution permission is not assumed solely from
W3C hosting. Additional identifier, agent-role, API, quality and provenance issues in the
paper are not silently added to the five-row sanity set.

This is a **small, partial development/sanity benchmark**, not a complete reconstruction
of scientific stakeholder elicitation. Do not assume policy context alone supports all
five reference rows. No B consolidation condition is available.

See [manifest](provenance/manifest.json), [gaps](provenance/GAPS.md),
[methodology](../BENCHMARK-METHODOLOGY.md), and [runtime allowlists](../runtime-inputs.json).
