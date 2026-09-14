# Consolidation and conflict-resolution working knowledge

## Boundary of the role

The consolidator receives candidates and produces a traceable canonical set. It
does not introduce new requirements, new evidence, stronger obligations, or
silent compromises. Background RAG helps identify equivalence and quality
problems but cannot repair missing corpus support.

## Canonicalisation sequence

1. Reject or quarantine candidates without an identifiable evidence span.
2. Normalise the subject resource, action, object/value, purpose, condition, and
   obligation strength.
3. Group candidates by semantic intent, not by shared keywords.
4. Merge only when the user outcome, resource level, value semantics, conditions,
   and obligation are compatible.
5. Preserve distinct requirements when one can be satisfied while the other
   fails.
6. Record unresolved disagreements and issue one bounded decision record.
7. Retain every contributing candidate ID, role, corpus source, evidence span,
   and relevant critic finding.

## Equivalence tests

- **Substitution test:** would implementing either candidate satisfy the other?
- **Counterexample test:** can one be true while the other is false?
- **Resource test:** do both constrain the same DCAT resource?
- **Strength test:** are MUST, SHOULD, MAY, recommendation, and information need
  being kept distinct?
- **Value test:** are free text, identifier, controlled concept, document, and
  endpoint actually interchangeable?
- **Condition test:** do jurisdiction, lifecycle phase, access state, or format
  conditions differ?

Lexical similarity is only a retrieval hint. Frequency and the number of agents
supporting a proposal are not proof (`w3c_dcat_ucr`, `iso_29148_2018`).

## Conflict taxonomy

- Direct contradiction: the same subject is required and prohibited from the
  same action under the same condition.
- Obligation conflict: candidates express different normative strengths.
- Resource conflict: the same field is assigned to Dataset versus Distribution,
  DataService, Catalog, or CatalogRecord.
- Representation conflict: literal versus URI, single versus multiple value, or
  local versus registered scheme.
- Scope conflict: catalogue metadata versus internal BIM/AAS/GIS content.
- Evidence conflict: sources support incompatible assertions, or one candidate
  exceeds its source.

## Provenance model

Treat source candidates and the consolidated requirement as distinct entities;
the consolidation operation is an activity and the acting role is an agent. A
canonical requirement may be derived from several candidates without erasing
their identities (`w3c_prov_o`). The final record should explain merges, rejects,
splits, and unresolved alternatives.

## Requirement-quality checks

Canonical wording should be singular, necessary, unambiguous, complete enough to
test, feasible, and traceable (`iso_29148_2018`,
`requirements_quality_roadmap`). If a statement contains independently testable
obligations, split it while preserving shared evidence. Do not turn SHACL
cardinality or severity choices into normative policy unless the evidence
supports them (`w3c_shacl`).

## Output discipline

Run consolidation once over the full candidate set. Never use consolidation as
an iterative voting stage. Every destructive-looking action must be reversible
from its decision record and provenance links.
