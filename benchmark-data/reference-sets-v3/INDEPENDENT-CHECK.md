# Independent source check of v3 (22 October 2026)

A separate reviewer, who had not built the set, checked the draft v3 atoms against the source texts and the DCAT-AP base files:

- every atom found only by PR #45 or added in the merge;
- every merged atom and every changed row;
- all 45 atoms coded as DCAT-AP restatements;
- all 111 term-level content atoms;
- a random sample of 30 further atoms (seed 20261022);
- a duplicate scan over all 319 atoms;
- all 40 Mobility rows.

Its results:

- **Anchors:** all Health, Stat and Geo anchor quotes occurred verbatim in the source text, and the JRC anchors occurred in the live paper.
- **Changed rows:** all four row changes (H-3, H-10, H-37, JRC-8) were confirmed by the sources.
- **Mobility:** all 40 rows were fully covered by their atoms.
- **Issues:** 47 (5 high, 18 medium, 24 low).

Claude verified the high-severity claims against the sources before applying them. The table lists what changed in the delivered v3.

| # | Atoms or rows | Finding | Resolution |
|---|---|---|---|
| 1 | G-31.1 | DCAT-AP maps only conformity of degree "conformant" (Annex II.14), so this is not a restatement | partly_base; source flag (Table 5 vs II.14) |
| 2 | H-17.1 | EHDS Art. 55 makes the source information mandatory; base terms are optional | tightens_base, with note |
| 3 | G-13.1 | Annex II.18 maps the metadata standard to dct:conformsTo on the catalogue record, as DCAT-AP does | restates_base; source flag (Table 5 vs II.18) |
| 4 | G-14.1 | Same evidence | extends_base; source flag |
| 5 | S-16.1 | StatDCAT-AP uses the DCAT-AP vocabularies; dcat:theme stays recommended | restates_base; the Eurostat mapping is noted as guidance |
| 6 | JRC-6.3 | The paper says DCAT-AP already models primary and alternative identifiers | restates_base, status requirement |
| 7 | H-17.2 | Relation ambiguous | tightens_base, with the reading stated in a note |
| 8 | G-22.1 | The atom names only temporal extent, which DCAT-AP covers | restates_base; note on the uncovered vertical extent |
| 9 | G-8.1, G-12.1 | DCAT-AP dataset terms used on the catalogue record | extends_base |
| 10 | G-29.1, G-30.1 (row G-30) | dct:conformsTo used for reference systems; "where it is not the default one" is not in the source | extends_base; condition removed from atom and row |
| 11 | JRC-8.1 | dct:type is not a distribution property in DCAT-AP 1.1 | extends_base |
| 12 | JRC-6.1 | The paper's "key requirement" is persistent identifiers for authors and input data | Reworded; status requirement; anchor added |
| 13 | JRC-6.5 | The need is met by the base; the note misread the paper | Status requirement; note corrected |
| 14 | H-12.2 | "In future processes …" is future work | deferred (not scored by default) |
| 15 | H-12.1 | Only content atom with not_term_level; a recommendation | restates_base (each logical dataset is a dcat:Dataset); modality recommendation |
| 16 | S-17.1 | The source says an RDF distribution "may use" dct:conformsTo | Status guidance; modality optional |
| 17 | H-56.3 | The access body's duty to assign an identifier was lost | Reworded |
| 18 | H-18.1 | Applicable legislation is mandatory for all three cohorts; anchor was from another context | Applicability all cohorts; anchor from §5.3.1.3 |
| 19 | H-33.1, H-33.2 | The same derived-to-source link | Merged into H-33.1 |
| 20 | H-4.1 | Umbrella over H-16.1, H-26.1, H-28.1, H-36.1 | partly_base; overlaps linked |
| 21–22 | Req-19.7/Req-24.1, Req-17.2/Req-35.1 | Unlinked duplicates | Overlaps linked |
| 23 | Req-14.1 | Umbrella over the mobility content atoms | Moved to the profile stratum |
| 24 | G-38.1 (row G-38) | "and the reasons for them" is not in the source; obligation M vs (C) | Clause removed from atom and row; flag added |
| 25 | G-9.1, G-27.1, G-39.1, G-41.1, G-41.2 | Table inconsistencies not flagged | Source flags added |
| 26 | G-20.1 | Encoding constraints in Annex II.10 | Note added |
| 27 | G-16.x | Anchor stopped before the creation date | Anchor extended. Other Geo anchors stay on Annex II, because the Table 5 text is fragmented in extraction. |
| 28 | G-11.1, G-12.1 | Wording overstated the obligation | Reworded |
| 29 | H-22.1, H-27.1 | Text vs §5.3.1.4 table inconsistencies | Source flags added |
| 30 | H-29.1 | Applies to all records in access-body catalogues | Applicability corrected |
| 31 | H-37.1 | "Mandatory" rationale vs recommended listing | Source flag added |
| 32 | H-68.1 | Weak anchor | Anchor from the §5.3.1.4 table |
| 33 | H-23.1, H-13.4 | Inconsistent relation codes | H-23.1 extends_base; H-13.4 beyond_base |
| 34–35 | H-11.x, S-2.1, H-46.4 | Ambiguous reading; unlinked near-duplicates | Notes added; overlaps H-11.3/H-11.4↔H-7.3, H-11.6↔H-7.4, S-2.1↔S-6.1, H-46.4↔H-26.1 |
| 36 | H-5.3, H-28.2 | DCAT-AP 3.0.0 has dct:type on foaf:Agent | H-5.3 extends_base; H-28.2 tightens_base; notes added |
| 37 | JRC-6.4 | A DataCite rule the paper reports | Anchor, note and overlap with JRC-6.3 |
| 38 | JRC-1.1 to JRC-5.1 | Anchors missing; "authors" | Anchors added from the paper's numbered items; wording aligned |
| 39 | H-49.1, H-15.4, H-54.2, H-65.1, H-2.1 | Status or modality stronger than the source | Proposed or recommendation; language-tag clause dropped from H-54.2 |
| 40 | H-1.1, H-30.2, H-38.1 | Minor fidelity | Reworded; note; open-question flag |
| 41 | H-30.3 | A system need outside its row | Moved to a new row, H-69 (atom H-69.1) |
| 42 | Page numbers | PR #45 pages did not always match the quote | New field `anchor_page`, computed from the PDF page breaks; PR #45 pages kept as `pr45_pdf_pages` |
| 43 | Overlaps | 17 one-way links | All overlap links made symmetric |
| 44 | Rows H-3, H-6 and several Mobility rows | Row-level relation reflects the v1 response coding | Not changed: row relations keep the v1 coding of how the published profile answered the row. Atom relations are coded per atom. |
| 45 | Req-1, Req-11, Req-21, Req-23, Req-30, Req-31 | Qualifiers lost when the rows were split | Superseded by the full check of all clauses against NAPCORE Table 1 (README) |
| 46 | Req-35.2 | Ambiguous relation | Resolved by Table 1 ("versions of metadata records on a NAP"): extends_base, since DCAT-AP 2.0.1 has no version terms for catalogue records |
| 47 | Req-23.1/23.2, Req-28.4/30.1, Req-27.2/27.3 | Possible double counting | First two pairs linked. Req-27.2/27.3 not linked, because they are distinct in the row text. |

## Framing question (decided)

The reviewer asked whether INSPIRE's M/C/O obligation levels belong to each Geo need. If they did, restatements of elements that are mandatory in INSPIRE would become tightens_base. Examples are G-10.1, G-23.1 and G-36.1.

Decision (Junda, 22 October 2026): keep the coding. Requirements are scored on the need, and implementations may differ later. GeoDCAT-AP itself keeps DCAT-AP obligations. The INSPIRE and ISO levels stay available in `geo.inspire_obligation` and `geo.iso19115_core_obligation`.
