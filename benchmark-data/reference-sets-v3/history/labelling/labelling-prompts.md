# Input-evidence labelling: subagent prompts (22 October 2026)

Eight Claude subagents labelled every atom against the staged runtime inputs. Each saw only its atom packet (`packets/atoms-<case>.json`, statements without references or curation notes) and the extracted input texts. Their raw outputs are in `raw-outputs/`; `integrate_labels.py` (in `../build-scripts/v3/`) checked every quotation against the inputs and merged the three Mobility raw-input groups by rank.

## Label Health atoms H-1–H-33 evidence

Started 2026-10-22T19:50:49.721Z (UTC). Prompt, verbatim:

```text
You are labelling benchmark reference requirements with the evidence for them in a fixed set of input documents. This supports an "evidence-eligible recall" denominator: a requirement can only be expected from an extraction pipeline if its input documents contain support for it.

## Atoms
File: /home/claude/merge/label/atoms-healthdcat.json. Label ONLY the atoms whose atom_id starts with H-1. through H-33. (rows H-1 to H-33; e.g. H-1.1, H-5.9, H-17.3, H-33.1). Each atom has atom_id, statement (the requirement to label), row_statement (its parent, for context), stratum, applicability, notes.

## Inputs (plain-text extractions; PDF texts contain page markers like "=== [page 12] ===")
Raw inputs (runtime path -> text file):
- healthdcat/input-raw/ehds-proposal.html -> /home/claude/merge/inputs/healthdcat/input-raw/ehds-proposal.html.txt
- healthdcat/input-raw/gdpr.html -> /home/claude/merge/inputs/healthdcat/input-raw/gdpr.html.txt
- healthdcat/input-raw/w3c-dcat-2-2020.html -> /home/claude/merge/inputs/healthdcat/input-raw/w3c-dcat-2-2020.html.txt
- healthdcat/input-raw/dcat-ap-2.1.1.pdf -> /home/claude/merge/inputs/healthdcat/input-raw/dcat-ap-2.1.1.pdf.txt
- healthdcat/input-raw/landscape-analysis-ms6.1.pdf -> /home/claude/merge/inputs/healthdcat/input-raw/landscape-analysis-ms6.1.pdf.txt
Consolidation input:
- healthdcat/input-preconsolidation/twg-observations.json -> /home/claude/merge/inputs/healthdcat/input-preconsolidation/twg-observations.json.txt (8 observations TWG-1..TWG-8)

## Labels (give one for raw and one for consolidation)
- supported: a passage states this need, or a rule, obligation or purpose from which a metadata-profile designer would directly derive it (same information item and same purpose or obligation; wording may differ). A specification that defines the property (e.g. DCAT-AP making title mandatory) supports a requirement that restates it.
- partial: the inputs support the general need but not a specific part of it (an obligation level, a named vocabulary, a condition, or one of two components).
- uncertain: a related passage exists but it is unclear whether it supports the need.
- unsupported: nothing in these inputs supports it.
Judge only from these input files. Do not use outside knowledge of HealthDCAT-AP or the HealthData@EU deliverable D6.2; they are not inputs. Search efficiently with Grep (case-insensitive, several synonyms) and read around the hits. Profile- and system-level atoms need support too (e.g. a passage asking for validation, harvesting endpoints, governance, multilingual descriptions).

For every supported, partial or uncertain label cite the 1–3 strongest passages: path (the runtime path above, not the .txt path), locator (Article or Recital number for legal texts, section heading for specifications, "[page N]" for PDFs, the item id for JSON), and quote: a verbatim excerpt of at most 300 characters copied from the text file, containing the words that carry the support. Before finishing, check every quote against its text file (grep -F or a short Python check that ignores whitespace differences) and fix any that do not match.

## Output
A JSON array, one object per atom, exactly:
{"atom_id": "...", "raw": {"label": "...", "sources": [{"path": "...", "locator": "...", "quote": "..."}], "rationale": "at most 25 words"}, "consolidation": {"label": "...", "sources": [...], "rationale": "..."}}
Write it with the Write tool to /tmp/claude-0/-home-claude/52db0194-1e75-558e-bfb2-4f590f0a248c/scratchpad/label/health-a.json. If writing fails, put the whole JSON array in your final message between lines ===BEGIN JSON=== and ===END JSON===. Otherwise your final message is just the counts per label and anything that blocked you. Do not edit any other file.
```

## Label Health atoms H-34–H-69 evidence

Started 2026-10-22T19:51:00.276Z (UTC). Prompt, verbatim:

```text
You are labelling benchmark reference requirements with the evidence for them in a fixed set of input documents. This supports an "evidence-eligible recall" denominator: a requirement can only be expected from an extraction pipeline if its input documents contain support for it.

## Atoms
File: /home/claude/merge/label/atoms-healthdcat.json. Label ONLY the atoms of rows H-34 to H-69 (atom_id H-34.1 ... H-69.1). Each atom has atom_id, statement (the requirement to label), row_statement (its parent, for context), stratum, applicability, notes.

## Inputs (plain-text extractions; PDF texts contain page markers like "=== [page 12] ===")
Raw inputs (runtime path -> text file):
- healthdcat/input-raw/ehds-proposal.html -> /home/claude/merge/inputs/healthdcat/input-raw/ehds-proposal.html.txt
- healthdcat/input-raw/gdpr.html -> /home/claude/merge/inputs/healthdcat/input-raw/gdpr.html.txt
- healthdcat/input-raw/w3c-dcat-2-2020.html -> /home/claude/merge/inputs/healthdcat/input-raw/w3c-dcat-2-2020.html.txt
- healthdcat/input-raw/dcat-ap-2.1.1.pdf -> /home/claude/merge/inputs/healthdcat/input-raw/dcat-ap-2.1.1.pdf.txt
- healthdcat/input-raw/landscape-analysis-ms6.1.pdf -> /home/claude/merge/inputs/healthdcat/input-raw/landscape-analysis-ms6.1.pdf.txt
Consolidation input:
- healthdcat/input-preconsolidation/twg-observations.json -> /home/claude/merge/inputs/healthdcat/input-preconsolidation/twg-observations.json.txt (8 observations TWG-1..TWG-8)

## Labels (give one for raw and one for consolidation)
- supported: a passage states this need, or a rule, obligation or purpose from which a metadata-profile designer would directly derive it (same information item and same purpose or obligation; wording may differ). A specification that defines the property (e.g. DCAT-AP making title mandatory) supports a requirement that restates it.
- partial: the inputs support the general need but not a specific part of it (an obligation level, a named vocabulary, a condition, or one of two components).
- uncertain: a related passage exists but it is unclear whether it supports the need.
- unsupported: nothing in these inputs supports it.
Judge only from these input files. Do not use outside knowledge of HealthDCAT-AP or the HealthData@EU deliverable D6.2; they are not inputs. Search efficiently with Grep (case-insensitive, several synonyms) and read around the hits. Profile- and system-level atoms need support too (e.g. a passage asking for validation, harvesting endpoints, governance, multilingual descriptions).

For every supported, partial or uncertain label cite the 1–3 strongest passages: path (the runtime path above, not the .txt path), locator (Article or Recital number for legal texts, section heading for specifications, "[page N]" for PDFs, the item id for JSON), and quote: a verbatim excerpt of at most 300 characters copied from the text file, containing the words that carry the support. Before finishing, check every quote against its text file (grep -F or a short Python check that ignores whitespace differences) and fix any that do not match.

## Output
A JSON array, one object per atom, exactly:
{"atom_id": "...", "raw": {"label": "...", "sources": [{"path": "...", "locator": "...", "quote": "..."}], "rationale": "at most 25 words"}, "consolidation": {"label": "...", "sources": [...], "rationale": "..."}}
Write it with the Write tool to /tmp/claude-0/-home-claude/52db0194-1e75-558e-bfb2-4f590f0a248c/scratchpad/label/health-b.json. If writing fails, put the whole JSON array in your final message between lines ===BEGIN JSON=== and ===END JSON===. Otherwise your final message is just the counts per label and anything that blocked you. Do not edit any other file.
```

## Label Mobility atoms vs policy inputs

Started 2026-10-22T19:51:09.974Z (UTC). Prompt, verbatim:

```text
You are labelling benchmark reference requirements with the evidence for them in a fixed set of input documents. This supports an "evidence-eligible recall" denominator: a requirement can only be expected from an extraction pipeline if its input documents contain support for it. You cover one group of the inputs; other reviewers cover the other groups, so judge only against yours.

## Atoms
File: /home/claude/merge/label/atoms-mobilitydcat.json (all 98 atoms, Req-1.1 ... Req-40.1). Each atom has atom_id, statement (the requirement to label), row_statement (its parent, for context), stratum, applicability, notes. The requirements are for a metadata profile for National Access Points (NAPs) for transport data.

## Your inputs: legal and policy texts (runtime path -> text file)
- mobilitydcat/input-raw/open-data-directive.html -> /home/claude/merge/inputs/mobilitydcat/input-raw/open-data-directive.html.txt
- mobilitydcat/input-raw/inspire-directive.html -> /home/claude/merge/inputs/mobilitydcat/input-raw/inspire-directive.html.txt
- mobilitydcat/input-raw/inspire-metadata.html -> /home/claude/merge/inputs/mobilitydcat/input-raw/inspire-metadata.html.txt
- mobilitydcat/input-raw/dga-proposal.html -> /home/claude/merge/inputs/mobilitydcat/input-raw/dga-proposal.html.txt
- mobilitydcat/input-raw/data-strategy.html -> /home/claude/merge/inputs/mobilitydcat/input-raw/data-strategy.html.txt

## Labels
- supported: a passage states this need, or a rule, obligation or purpose from which a metadata-profile designer would directly derive it (same information item and same purpose or obligation; wording may differ).
- partial: the inputs support the general need but not a specific part of it (an obligation level, a named vocabulary, a condition, or one of two components).
- uncertain: a related passage exists but it is unclear whether it supports the need.
- unsupported: nothing in these inputs supports it.
Judge only from these input files. Do not use outside knowledge of mobilityDCAT-AP or the NAPCORE requirements report; they are not inputs. Search efficiently with Grep (case-insensitive, several synonyms) and read around the hits. Profile- and system-level atoms need support too (e.g. passages on metadata quality, multilingualism, interoperability, governance, documentation).

For every supported, partial or uncertain label cite the 1–3 strongest passages: path (the runtime path above, not the .txt path), locator (Article or Recital number, or section heading), and quote: a verbatim excerpt of at most 300 characters copied from the text file, containing the words that carry the support. Before finishing, check every quote against its text file (grep -F or a short Python check that ignores whitespace differences) and fix any that do not match.

## Output
A JSON array, one object per atom (all 98), exactly:
{"atom_id": "...", "raw": {"label": "...", "sources": [{"path": "...", "locator": "...", "quote": "..."}], "rationale": "at most 25 words"}}
Write it with the Write tool to /tmp/claude-0/-home-claude/52db0194-1e75-558e-bfb2-4f590f0a248c/scratchpad/label/mobility-policy.json. If writing fails, put the whole JSON array in your final message between lines ===BEGIN JSON=== and ===END JSON===. Otherwise your final message is just the counts per label and anything that blocked you. Do not edit any other file.
```

## Label Mobility atoms vs standards inputs

Started 2026-10-22T19:51:20.830Z (UTC). Prompt, verbatim:

```text
You are labelling benchmark reference requirements with the evidence for them in a fixed set of input documents. This supports an "evidence-eligible recall" denominator: a requirement can only be expected from an extraction pipeline if its input documents contain support for it. You cover one group of the inputs; other reviewers cover the other groups, so judge only against yours.

## Atoms
File: /home/claude/merge/label/atoms-mobilitydcat.json (all 98 atoms, Req-1.1 ... Req-40.1). Each atom has atom_id, statement (the requirement to label), row_statement (its parent, for context), stratum, applicability, notes. The requirements are for a metadata profile for National Access Points (NAPs) for transport data.

## Your inputs: metadata standards and specifications (runtime path -> text file; PDF texts contain page markers like "=== [page 12] ===")
- mobilitydcat/input-raw/w3c-dcat-2-2020.html -> /home/claude/merge/inputs/mobilitydcat/input-raw/w3c-dcat-2-2020.html.txt
- mobilitydcat/input-raw/dcat-ap-2.0.0.pdf -> /home/claude/merge/inputs/mobilitydcat/input-raw/dcat-ap-2.0.0.pdf.txt
- mobilitydcat/input-raw/dcat-ap-2.1.0.pdf -> /home/claude/merge/inputs/mobilitydcat/input-raw/dcat-ap-2.1.0.pdf.txt
- mobilitydcat/input-raw/geodcat-ap-1.0.1-prior-extension.pdf -> /home/claude/merge/inputs/mobilitydcat/input-raw/geodcat-ap-1.0.1-prior-extension.pdf.txt
- mobilitydcat/input-raw/inspire-metadata-guidelines-1.3.pdf -> /home/claude/merge/inputs/mobilitydcat/input-raw/inspire-metadata-guidelines-1.3.pdf.txt
- mobilitydcat/input-raw/cmc-2019-concept-inventory.json -> /home/claude/merge/inputs/mobilitydcat/input-raw/cmc-2019-concept-inventory.json.txt

## Labels
- supported: a passage states this need, or a rule, obligation or purpose from which a metadata-profile designer would directly derive it (same information item and same purpose or obligation; wording may differ). A specification that defines the property (e.g. DCAT-AP making title mandatory) supports a requirement that restates it.
- partial: the inputs support the general need but not a specific part of it (an obligation level, a named vocabulary, a condition, or one of two components).
- uncertain: a related passage exists but it is unclear whether it supports the need.
- unsupported: nothing in these inputs supports it.
Judge only from these input files. Do not use outside knowledge of mobilityDCAT-AP or the NAPCORE requirements report; they are not inputs. Search efficiently with Grep (case-insensitive, several synonyms) and read around the hits. Profile- and system-level atoms need support too (e.g. passages on extension rules, conformance, validation, controlled vocabularies, multilingualism, maintenance).

For every supported, partial or uncertain label cite the 1–3 strongest passages: path (the runtime path above, not the .txt path), locator (section heading, "[page N]" for PDFs, item id for JSON), and quote: a verbatim excerpt of at most 300 characters copied from the text file, containing the words that carry the support. Before finishing, check every quote against its text file (grep -F or a short Python check that ignores whitespace differences) and fix any that do not match.

## Output
A JSON array, one object per atom (all 98), exactly:
{"atom_id": "...", "raw": {"label": "...", "sources": [{"path": "...", "locator": "...", "quote": "..."}], "rationale": "at most 25 words"}}
Write it with the Write tool to /tmp/claude-0/-home-claude/52db0194-1e75-558e-bfb2-4f590f0a248c/scratchpad/label/mobility-standards.json. If writing fails, put the whole JSON array in your final message between lines ===BEGIN JSON=== and ===END JSON===. Otherwise your final message is just the counts per label and anything that blocked you. Do not edit any other file.
```

## Label Mobility atoms vs literature inputs

Started 2026-10-22T19:51:31.177Z (UTC). Prompt, verbatim:

```text
You are labelling benchmark reference requirements with the evidence for them in a fixed set of input documents. This supports an "evidence-eligible recall" denominator: a requirement can only be expected from an extraction pipeline if its input documents contain support for it. You cover one group of the inputs; other reviewers cover the other groups, so judge only against yours.

## Atoms
File: /home/claude/merge/label/atoms-mobilitydcat.json (all 98 atoms, Req-1.1 ... Req-40.1). Each atom has atom_id, statement (the requirement to label), row_statement (its parent, for context), stratum, applicability, notes. The requirements are for a metadata profile for National Access Points (NAPs) for transport data.

## Your inputs: literature and project documents (runtime path -> text file; PDF texts contain page markers like "=== [page 12] ===")
- mobilitydcat/input-raw/turning-fair-into-reality-2018.pdf -> /home/claude/merge/inputs/mobilitydcat/input-raw/turning-fair-into-reality-2018.pdf.txt
- mobilitydcat/input-raw/fair-cost-benefit-2018.pdf -> /home/claude/merge/inputs/mobilitydcat/input-raw/fair-cost-benefit-2018.pdf.txt
- mobilitydcat/input-raw/niso-understanding-metadata-2017.pdf -> /home/claude/merge/inputs/mobilitydcat/input-raw/niso-understanding-metadata-2017.pdf.txt
- mobilitydcat/input-raw/sprint-nap-federation-2021.pdf -> /home/claude/merge/inputs/mobilitydcat/input-raw/sprint-nap-federation-2021.pdf.txt
- mobilitydcat/input-raw/sprint-competency-tasks.json -> /home/claude/merge/inputs/mobilitydcat/input-raw/sprint-competency-tasks.json.txt

## Labels
- supported: a passage states this need, or a rule, obligation or purpose from which a metadata-profile designer would directly derive it (same information item and same purpose or obligation; wording may differ).
- partial: the inputs support the general need but not a specific part of it (an obligation level, a named vocabulary, a condition, or one of two components).
- uncertain: a related passage exists but it is unclear whether it supports the need.
- unsupported: nothing in these inputs supports it.
Judge only from these input files. Do not use outside knowledge of mobilityDCAT-AP or the NAPCORE requirements report; they are not inputs. Search efficiently with Grep (case-insensitive, several synonyms) and read around the hits. General metadata-quality literature can support the profile-level atoms (e.g. expressiveness, modularity, persistent identifiers, human- and machine-readable metadata, governance).

For every supported, partial or uncertain label cite the 1–3 strongest passages: path (the runtime path above, not the .txt path), locator ("[page N]" for PDFs, item id for JSON, plus a section heading if visible), and quote: a verbatim excerpt of at most 300 characters copied from the text file, containing the words that carry the support. Before finishing, check every quote against its text file (grep -F or a short Python check that ignores whitespace differences) and fix any that do not match.

## Output
A JSON array, one object per atom (all 98), exactly:
{"atom_id": "...", "raw": {"label": "...", "sources": [{"path": "...", "locator": "...", "quote": "..."}], "rationale": "at most 25 words"}}
Write it with the Write tool to /tmp/claude-0/-home-claude/52db0194-1e75-558e-bfb2-4f590f0a248c/scratchpad/label/mobility-literature.json. If writing fails, put the whole JSON array in your final message between lines ===BEGIN JSON=== and ===END JSON===. Otherwise your final message is just the counts per label and anything that blocked you. Do not edit any other file.
```

## Label Mobility atoms vs partner inputs

Started 2026-10-22T19:51:40.332Z (UTC). Prompt, verbatim:

```text
You are labelling benchmark reference requirements with the evidence for them in a fixed set of input documents. This supports an "evidence-eligible recall" denominator for a consolidation experiment: the pipeline receives pre-consolidation candidate requirements and must consolidate them into final requirements. A final requirement is only expected if the pre-consolidation inputs contain support for it.

## Atoms
File: /home/claude/merge/label/atoms-mobilitydcat.json (all 98 atoms, Req-1.1 ... Req-40.1). Each atom has atom_id, statement (the requirement to label), row_statement (its parent, for context), stratum, applicability, notes. The requirements are for a metadata profile for National Access Points (NAPs) for transport data.

## Your inputs: pre-consolidation material (runtime path -> text file; each is a JSON file pretty-printed as text)
- mobilitydcat/input-preconsolidation/partner-requirements.json -> /home/claude/merge/inputs/mobilitydcat/input-preconsolidation/partner-requirements.json.txt (60 partner candidates with ids such as DE-00, IT-03)
- mobilitydcat/input-preconsolidation/expert-and-cmc-observations.json -> /home/claude/merge/inputs/mobilitydcat/input-preconsolidation/expert-and-cmc-observations.json.txt (EX-1 ... observations)
- mobilitydcat/input-preconsolidation/literature-review-observations.json -> /home/claude/merge/inputs/mobilitydcat/input-preconsolidation/literature-review-observations.json.txt (17 observations; use the source_locator as the locator)
These files are small: read all three in full before labelling.

## Labels
- supported: an input item states this need (same information item and same purpose or obligation; wording may differ).
- partial: an item supports the general need but not a specific part of it (an obligation level, a named vocabulary, a condition, or one of two components).
- uncertain: a related item exists but it is unclear whether it supports the need.
- unsupported: no item supports it.
Judge only from these input files. Do not use outside knowledge of mobilityDCAT-AP or the NAPCORE requirements report.

For every supported, partial or uncertain label cite the 1–3 strongest items: path (the runtime path above, not the .txt path), locator (the item id, e.g. "DE-00", "EX-3", or the literature item's source_locator), and quote: a verbatim excerpt of at most 300 characters copied from the item text. Before finishing, check every quote against its text file (grep -F or a short Python check that ignores whitespace differences) and fix any that do not match.

## Output
A JSON array, one object per atom (all 98), exactly:
{"atom_id": "...", "consolidation": {"label": "...", "sources": [{"path": "...", "locator": "...", "quote": "..."}], "rationale": "at most 25 words"}}
Write it with the Write tool to /tmp/claude-0/-home-claude/52db0194-1e75-558e-bfb2-4f590f0a248c/scratchpad/label/mobility-consolidation.json. If writing fails, put the whole JSON array in your final message between lines ===BEGIN JSON=== and ===END JSON===. Otherwise your final message is just the counts per label and anything that blocked you. Do not edit any other file.
```

## Label Geo atoms evidence

Started 2026-10-22T19:51:50.377Z (UTC). Prompt, verbatim:

```text
You are labelling benchmark reference requirements with the evidence for them in a fixed set of input documents. This supports an "evidence-eligible recall" denominator: a requirement can only be expected from an extraction pipeline if its input documents contain support for it.

## Atoms
File: /home/claude/merge/label/atoms-geodcat.json (all 56 atoms). Each has atom_id, statement (the requirement to label), row_statement (its parent, for context), stratum, applicability, notes. The requirements are for an RDF/DCAT-AP-based profile for geospatial metadata (INSPIRE and ISO 19115 elements).

## Inputs (runtime path -> text file; PDF texts contain page markers like "=== [page 12] ===")
- geodcat/input-raw/inspire-directive.html -> /home/claude/merge/inputs/geodcat/input-raw/inspire-directive.html.txt
- geodcat/input-raw/inspire-metadata.html -> /home/claude/merge/inputs/geodcat/input-raw/inspire-metadata.html.txt (INSPIRE Metadata Regulation)
- geodcat/input-raw/inspire-interoperability.html -> /home/claude/merge/inputs/geodcat/input-raw/inspire-interoperability.html.txt (INSPIRE data and services interoperability regulation)
- geodcat/input-raw/w3c-dcat-2014.html -> /home/claude/merge/inputs/geodcat/input-raw/w3c-dcat-2014.html.txt
- geodcat/input-raw/inspire-metadata-guidelines-1.3.pdf -> /home/claude/merge/inputs/geodcat/input-raw/inspire-metadata-guidelines-1.3.pdf.txt

## Labels
- supported: a passage states this need, or a rule, obligation or purpose from which a metadata-profile designer would directly derive it (same information item and same purpose or obligation; wording may differ). A regulation or guideline that defines the metadata element supports a requirement to provide that element.
- partial: the inputs support the general need but not a specific part of it (an obligation level, a named vocabulary, a condition, or one of two components).
- uncertain: a related passage exists but it is unclear whether it supports the need.
- unsupported: nothing in these inputs supports it.
Judge only from these input files. Do not use outside knowledge of GeoDCAT-AP; it is not an input. Search efficiently with Grep (case-insensitive, several synonyms) and read around the hits. Profile- and system-level atoms (e.g. "conform to DCAT-AP", "keep the RDF binding simple", "convert ISO/INSPIRE records to RDF") need support too; DCAT-AP itself is not an input here.

For every supported, partial or uncertain label cite the 1–3 strongest passages: path (the runtime path above, not the .txt path), locator (Article/Annex part for regulations, section heading or "[page N]" for the guidelines), and quote: a verbatim excerpt of at most 300 characters copied from the text file, containing the words that carry the support. Before finishing, check every quote against its text file (grep -F or a short Python check that ignores whitespace differences) and fix any that do not match.

## Output
A JSON array, one object per atom, exactly:
{"atom_id": "...", "raw": {"label": "...", "sources": [{"path": "...", "locator": "...", "quote": "..."}], "rationale": "at most 25 words"}}
Write it with the Write tool to /tmp/claude-0/-home-claude/52db0194-1e75-558e-bfb2-4f590f0a248c/scratchpad/label/geo.json. If writing fails, put the whole JSON array in your final message between lines ===BEGIN JSON=== and ===END JSON===. Otherwise your final message is just the counts per label and anything that blocked you. Do not edit any other file.
```

## Label Stat and JRC atoms evidence

Started 2026-10-22T19:52:00.323Z (UTC). Prompt, verbatim:

```text
You are labelling benchmark reference requirements with the evidence for them in a fixed set of input documents. This supports an "evidence-eligible recall" denominator: a requirement can only be expected from an extraction pipeline if its input documents contain support for it. There are two separate cases; judge each only against its own inputs.

## Case 1: statistical data profile
Atoms: /home/claude/merge/label/atoms-statdcat.json (27 atoms). Inputs (runtime path -> text file):
- statdcat/input-raw/w3c-dcat-2014.html -> /home/claude/merge/inputs/statdcat/input-raw/w3c-dcat-2014.html.txt
- statdcat/input-raw/w3c-data-cube-2014.html -> /home/claude/merge/inputs/statdcat/input-raw/w3c-data-cube-2014.html.txt
Do not use outside knowledge of StatDCAT-AP; it is not an input.

## Case 2: research data profile (JRC)
Atoms: /home/claude/merge/label/atoms-jrc-research.json (17 atoms). Inputs (runtime path -> text file; PDF text has page markers like "=== [page 3] ==="):
- jrc-research/input-raw/w3c-dcat-2014.html -> /home/claude/merge/inputs/jrc-research/input-raw/w3c-dcat-2014.html.txt
- jrc-research/input-raw/jrc-data-policy-2015.pdf -> /home/claude/merge/inputs/jrc-research/input-raw/jrc-data-policy-2015.pdf.txt
- jrc-research/input-raw/datacite-3.1-field-context.json -> /home/claude/merge/inputs/jrc-research/input-raw/datacite-3.1-field-context.json.txt
Do not use outside knowledge of the paper "Using DCAT-AP for research data" (Perego et al. 2016); it is not an input.

Each atom has atom_id, statement (the requirement to label), row_statement (its parent, for context), stratum, applicability, notes.

## Labels
- supported: a passage states this need, or a rule, obligation or purpose from which a metadata-profile designer would directly derive it (same information item and same purpose or obligation; wording may differ). A specification that defines the property supports a requirement that restates it.
- partial: the inputs support the general need but not a specific part of it (an obligation level, a named vocabulary, a condition, or one of two components).
- uncertain: a related passage exists but it is unclear whether it supports the need.
- unsupported: nothing in these inputs supports it.
Search with Grep (case-insensitive, several synonyms) and read around the hits. Profile-level atoms need support too.

For every supported, partial or uncertain label cite the 1–3 strongest passages: path (the runtime path above, not the .txt path), locator (section heading, "[page N]" for the PDF, field name for the JSON), and quote: a verbatim excerpt of at most 300 characters copied from the text file, containing the words that carry the support. Before finishing, check every quote against its text file (grep -F or a short Python check that ignores whitespace differences) and fix any that do not match.

## Output
A JSON array with one object per atom of both cases (27 + 17), exactly:
{"atom_id": "...", "raw": {"label": "...", "sources": [{"path": "...", "locator": "...", "quote": "..."}], "rationale": "at most 25 words"}}
Write it with the Write tool to /tmp/claude-0/-home-claude/52db0194-1e75-558e-bfb2-4f590f0a248c/scratchpad/label/stat-jrc.json. If writing fails, put the whole JSON array in your final message between lines ===BEGIN JSON=== and ===END JSON===. Otherwise your final message is just the counts per label and anything that blocked you. Do not edit any other file.
```
