export type AgentPhase = 'extraction' | 'consolidation' | 'criticism';

export type AgentRoleDefinition = {
  id: string;
  order: number;
  label: string;
  phase: AgentPhase;
  purpose: string;
  suggestedBackground: string;
};

export const ALL_AGENT_ROLES: AgentRoleDefinition[] = [
  {
    id: 'standards_conformance', order: 1, phase: 'extraction', label: 'Standards and normative conformance',
    purpose: 'Find corpus-stated obligations, cardinalities, and compatibility constraints.',
    suggestedBackground: 'Apply DCAT/DCAT-AP normative terminology carefully. Distinguish MUST/SHALL obligations from examples, recommendations, and descriptive mentions.',
  },
  {
    id: 'dcat_reuse', order: 2, phase: 'extraction', label: 'DCAT and DCAT-AP reuse',
    purpose: 'Identify reusable DCAT-family terms and evidence that extensions are unnecessary.',
    suggestedBackground: 'Prefer DCAT, DCAT-AP, DCTERMS, PROV, SKOS, and FOAF terms. Check the owning resource type before proposing specialization or extension.',
  },
  {
    id: 'construction_domain', order: 3, phase: 'extraction', label: 'Construction domain semantics',
    purpose: 'Identify construction distinctions needed for dataset discovery and interpretation.',
    suggestedBackground: 'Focus on asset, spatial, lifecycle, discipline, project, and representation context at dataset/catalog level; do not mirror operational model content.',
  },
  {
    id: 'aas_idta', order: 4, phase: 'extraction', label: 'AAS and IDTA semantics',
    purpose: 'Identify dataset-level discovery needs for AAS-related resources.',
    suggestedBackground: 'Use AAS identifiers, semantic IDs, concept descriptions, and submodel references only when the corpus supports them. Avoid copying submodel-element values.',
  },
  {
    id: 'ifc_bim', order: 5, phase: 'extraction', label: 'IFC and BIM semantics',
    purpose: 'Identify IFC/BIM representation context needed at catalogue level.',
    suggestedBackground: 'Consider IFC schema/version, model view, discipline, project, spatial scope, and exchange context. Link to BIM semantics without mirroring geometry or entities.',
  },
  {
    id: 'dataspace_interoperability', order: 6, phase: 'extraction', label: 'Dataspace and connector interoperability',
    purpose: 'Identify portable catalogue, service, participant, and policy metadata.',
    suggestedBackground: 'Separate portable semantic metadata from connector implementation fields. Focus on participant identity, endpoints, federation, contracts, and policy references supported by the corpus.',
  },
  {
    id: 'publisher_feasibility', order: 7, phase: 'extraction', label: 'Data publisher feasibility',
    purpose: 'Assess whether evidenced metadata can be supplied and maintained by publishers.',
    suggestedBackground: 'Consider publication-time availability, onboarding burden, update responsibility, and obligation feasibility without deleting evidenced needs.',
  },
  {
    id: 'consumer_discovery', order: 8, phase: 'extraction', label: 'Data consumer and discovery',
    purpose: 'Identify metadata needed to find, compare, select, access, and reuse datasets.',
    suggestedBackground: 'Evaluate whether a user can answer predefined discovery tasks before opening the data. Keep internal application behavior out of scope.',
  },
  {
    id: 'stewardship_governance', order: 9, phase: 'extraction', label: 'Data stewardship and governance',
    purpose: 'Identify responsibility, lifecycle, provenance, and vocabulary-governance metadata.',
    suggestedBackground: 'Consider ownership, contact, maintenance, version, status, provenance, and controlled-vocabulary governance only where evidenced.',
  },
  {
    id: 'access_rights_policy', order: 10, phase: 'extraction', label: 'Access, rights, policy, and usage',
    purpose: 'Identify metadata required to assess permitted access and reuse.',
    suggestedBackground: 'Focus on licences, access rights, usage constraints, sensitivity, policy references, and access services. Do not provide legal advice or invent policy language.',
  },
  {
    id: 'fair_quality_provenance', order: 11, phase: 'extraction', label: 'FAIR, quality, and provenance',
    purpose: 'Identify actionable fitness, trust, provenance, and FAIR-oriented metadata.',
    suggestedBackground: 'Connect provenance, source, date, completeness, quality, and trust signals to declared tasks. Avoid generic FAIR claims or unsupported scores.',
  },
  {
    id: 'minimality_scope', order: 12, phase: 'extraction', label: 'Minimality and scope control',
    purpose: 'Find the smallest corpus-supported dataset-level requirement set and exclusions.',
    suggestedBackground: 'Challenge redundancy, examples, implementation details, and internal object content while retaining every evidenced discovery distinction.',
  },
  {
    id: 'consolidation_conflict', order: 13, phase: 'consolidation', label: 'Consolidation and conflict resolution',
    purpose: 'Canonicalize verified raw candidates while preserving disagreements and provenance.',
    suggestedBackground: 'Merge only semantically equivalent candidates. Preserve source candidate IDs, evidence IDs, role origins, conflicts, and unsupported audit records.',
  },
  {
    id: 'grounding_scope_critic', order: 14, phase: 'criticism', label: 'Grounding, scope, obligation, and atomicity critic',
    purpose: 'Challenge evidence fidelity, scope, obligation wording, and atomicity.',
    suggestedBackground: 'Audit whether each consolidated statement exceeds its evidence, combines obligations, or drifts beyond catalogue/profile scope. Report findings without mutating output.',
  },
  {
    id: 'reuse_minimality_critic', order: 15, phase: 'criticism', label: 'Reuse, minimality, and validation critic',
    purpose: 'Challenge missed reuse, over-modeling, and downstream compatibility.',
    suggestedBackground: 'Check registered-term reuse, resource compatibility, extension necessity, and minimal-profile fit. Report findings without approving or changing requirements.',
  },
];

export const EXTRACTION_ROLES = ALL_AGENT_ROLES.filter((role) => role.phase === 'extraction');
export const SYNTHESIS_ROLES = ALL_AGENT_ROLES.filter((role) => role.phase !== 'extraction');
