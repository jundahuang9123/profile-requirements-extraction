"""Immutable run model choices and explicit, thread-safe step routing."""
from dataclasses import replace
from threading import Lock
from typing import Annotated, Literal

from pydantic import StringConstraints

from .client import create_client
from .model_catalog import generation_models

StepName = Literal['role_selection', 'extraction', 'proposal_support', 'grouping',
    'writer', 'rewrite_critic', 'membership', 'classification', 'profile_scope', 'use_case_linker',
    'link_critic', 'assessment', 'discussion', 'dataset_categories', 'selection']
STEPS = ('role_selection', 'extraction', 'proposal_support', 'grouping', 'writer',
    'rewrite_critic', 'membership', 'classification', 'profile_scope', 'use_case_linker', 'link_critic',
    'assessment', 'discussion', 'dataset_categories', 'selection')
ModelID = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=256)]

# Writer and critic deliberately have separate keys although they share a saved stage.
CONTRACT_STEPS = {
    'RoleCandidates': 'role_selection', 'RoleCitationCorrections': 'role_selection',
    'RolePanel': 'role_selection', 'RoleRegistry': 'role_selection', 'StakeholderPanel': 'role_selection',
    'SpanElicitationResult': 'extraction', 'NeedSpanElicitationResult': 'extraction',
    'ProposalSupport': 'proposal_support', 'SemanticGrouping': 'grouping',
    'NeedStatements': 'writer', 'NeedGrounding': 'rewrite_critic',
    'NeedMembership': 'membership', 'NeedClassifications': 'classification',
    'ProfileScope': 'profile_scope', 'NeedApplicability': 'profile_scope',
    'DatasetCategories': 'dataset_categories', 'NeedEquivalence': 'selection',
    'NeedUseCaseLinks': 'use_case_linker', 'UseCaseCritic': 'link_critic',
    'Qualification': 'assessment',
}


def resolve_models(config, overrides):
    """Validate against the saved provider's catalogue; never generate an answer."""
    choices = {step: overrides.get(step, config.resolved_model()) for step in STEPS}
    available = set(generation_models(config))
    unknown = sorted(set(choices.values()) - available)
    if unknown:
        raise ValueError('Models unavailable for text generation at this provider: ' + ', '.join(unknown))
    # Validate model-specific options now, before persisting a run.
    from .model_options import reasoning_effort_for
    for model in set(choices.values()):
        reasoning_effort_for(model, config.reasoning_effort)
    return choices


class StepModelRouter:
    def __init__(self, config, choices, factory=create_client):
        self.config, self.choices, self.factory = config, dict(choices), factory
        self._clients, self._lock = {}, Lock()

    def for_step(self, step):
        if step not in STEPS:
            raise ValueError('Unknown model step: ' + step)
        model = self.choices.get(step, self.config.resolved_model())
        with self._lock:
            if model not in self._clients:
                self._clients[model] = self.factory(replace(self.config, model=model))
            return self._clients[model]

    def describe(self):
        return {'provider': self.config.provider, 'step_models': dict(self.choices)}

    def generate_structured(self, **kwargs):
        step = contract_step(kwargs['output_model'])
        if not step:
            raise ValueError('Structured call has no model step; bind its client explicitly.')
        return self.for_step(step).generate_structured(**kwargs)


def contract_step(output_model):
    return CONTRACT_STEPS.get(output_model.__name__)


def for_step(client, step):
    """Keep legacy and scripted test clients usable without a routing API."""
    return client.for_step(step) if client is not None and hasattr(client, 'for_step') else client


def for_contract(client, output_model):
    step = contract_step(output_model)
    if not step:
        raise ValueError('No model step registered for ' + output_model.__name__)
    return for_step(client, step)


def model_settings(description):
    """Generation identity excludes transport tuning; full descriptions remain in audits."""
    if not isinstance(description, dict):
        return description
    return {key: description.get(key) for key in ('provider', 'base_url', 'model', 'reasoning_effort')}


def model_identity(client):
    if client is None:
        return 'offline'
    # Small legacy scripted fixtures need not implement the provider protocol.
    describe = getattr(client, 'describe', None)
    return model_settings(describe() if describe else {'provider': 'scripted', 'model': type(client).__qualname__})
