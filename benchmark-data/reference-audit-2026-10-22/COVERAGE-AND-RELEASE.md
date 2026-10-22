# Scope coverage and release decision

**Decision: review-ready expansion; not scoring-ready gold; historical corpus still partial.**

## Scope ledger

| Source region | Treatment | Remaining boundary |
|---|---|---|
| Mobility Table 1 Req-1–40 | All parent IDs preserved; 99 draft clauses from existing paraphrases | Full original-report clause-by-clause comparison and actor/qualifier checks remain pending. Annex candidates are not automatically accepted final needs. |
| Health §5.2.1.1 identifiers | Source-linked identifier, source-copy and aggregation metadata candidates | Original historical input support not labelled. |
| Health §5.2.1.2 knowledge graph | Links, broken-link management and maturity separated | Governance excluded from a metadata-only denominator unless expressly scoped in. |
| Health §5.2.1.3 review | Annual check, actor, review timing and profile conformance distinguished | Internal versus exchanged review date remains conditional. |
| Health §5.2.2 semantic/AI search | Free-text and semantic-query capabilities | Does not make implementation technologies or illustrative queries mandatory. |
| Health §5.2.3 facets | All listed health facets represented; typical age endpoints separated | UI prioritisation/dynamic filters separated from content. |
| Health §5.2.4–5 semantic annotation | Concept identity and coding/conformance identifiers | Selected vocabulary bindings are design choices, not distinct discovery needs. |
| Health §5.2.6 samples | Samples, dictionaries, variable selection and script submission | Dictionary modality conflict retained; access workflows separately classified. |
| Health §5.2.6.1 dictionaries | Structure, format, vocabulary, classification, taxonomy and code lists | Examples of actual patient variables do not become catalogue requirements. |
| Health §5.2.6.2 subdivisions | Logical datasets and source relationships | Complete dataset-product method is future work in the source. |
| Health §5.2.6.2.1 federation | Common-model conformance | No universal harmonisation requirement; processing-service interoperability out of source scope. |
| Health §5.2.6.3 IPR | Conditions, affected parts, protection justification, redacted dictionary | Conditions must not be collapsed into an unconditional public-sample obligation. |
| Health §5.2.7 analytics | Suitability assessment without raw-data access | Examples are alternatives; not one mandatory requirement per dashboard/service. |
| Health §5.2.8 quality | Annotations, target, motivation and content | Detailed quality dimensions, reporting and label-generation methods require further scope decisions; no completeness claim for all embedded regulatory quotations. |
| Health §5.2.9 purpose | Purpose, legal basis and personal-data categories | Historical account, not a current legal compliance specification. |
| Health §5.3 minimum metadata | Public, protected and sensitive cases; content inventory represented | Conflicting access-class wording, source errors and proposed cardinalities need adjudication; inventory coverage does not establish obligation completeness. |
| Health other chapters/annexes | Inspected selectively as context; not exhaustively curated | Operational deployment, roadmap, screenshots, examples and meeting minutes need a separately scoped audit if benchmark scope includes them. |
| Geo Annex I Table 5 | All 34 table rows represented in 37 candidates | Source columns differ in obligation and applicability; Annex II conditions still require per-row adjudication. |
| Geo §§1.1,4.1–4.2 | Existing architectural rows retained | Do not infer a unique new term for every content requirement. |
| Geo Annex II/III | Used for context and interpretation | Not a complete inventory of RDF syntax/encoding constraints; out of implementation-neutral RQ1 core unless separately defined. |
| Stat §7.2 | Seven existing needs retained; key constraints and compound time components added | Do not promote examples, future-work proposals or all profile properties to new requirements. |
| Stat §§5–6 | Use-case/decision context read; five §6.2 principles added | Not a complete conformance suite for §§7.3 onward. |
| JRC paper | Five core identities retained; identifiers, roles, API and additional issues represented | Live source not byte-frozen; no new universal historical eligibility claim. |
| EPOS | Explicit evidence gap retained | No defensible recovered elicitation gold; excluded from quantitative recovery. |

## Conditions for a defensible completeness statement

1. Freeze the exact scope: metadata content, architecture, governance, interfaces and access workflow must be distinguishable. Declare which strata are evaluated.
2. Review every source section in that declared scope. Record an include/exclude/duplicate/unresolved decision for every candidate and an explicit reason for exclusions. Do not infer completeness from ID counts.
3. Compare the Mobility clause draft to original Table 1 and restore any lost actor, modality, conjunction, exception, example-versus-obligation distinction or condition.
4. Resolve Health source contradictions explicitly; do not let a source's errors silently become normative gold. Preserve the original wording's status and report reviewer decisions.
5. Resolve Geo applicability per resource type and source condition. Inherit neither INSPIRE nor ISO obligation blindly as a universal Geo requirement.
6. Two independent human reviewers, or the methodology's declared independently reviewed sample, assess source fidelity and disagreements. Record reviewers and adjudication decisions. No such review is claimed here.
7. Map each accepted atom to exact spans in the actually staged raw and/or consolidation inputs. Use supported, unsupported or uncertain with reasons; a final-profile citation alone is not raw support.
8. Deduplicate and freeze atom IDs before inspecting predictions. Never credit both a compound parent and its children or overlapping facets twice. Keep a stable parent-to-atom mapping.
9. Freeze source bytes, corpus version, matching rules, exclusions and denominators. JRC live source identity/version needs explicit treatment. Preserve old runs under their old reference version.
10. Verify retrieval isolation. Do not stage this audit, final profiles, reviewer notes or answer-bearing excerpts with extraction inputs. Record reference exposure and cross-case source overlap.

A defensible final label is “complete for the declared, independently reviewed source scope” when those conditions hold. It is not “all requirements that could exist in the domain.”
