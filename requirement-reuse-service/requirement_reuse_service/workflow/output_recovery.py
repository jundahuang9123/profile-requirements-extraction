"""Keep the usable rows of a role-selection answer that failed its output contract.

Applied after the client's single schema correction, to complete JSON only. A row is kept
only when it passes its own contract unchanged; nothing is trimmed, rewritten or invented.
Only an answer with nothing usable in it, or a provider failure, stops a run.
"""
from typing import get_args, get_origin

from pydantic import BaseModel, ValidationError

POLICY = 'rq1-role-selection-output-recovery-v1'


def issues(exc: ValidationError) -> list[dict]:
    """Paths, types and messages only; never the invalid input values."""
    return [{'loc': list(error['loc']), 'type': error['type'], 'message': error['msg']}
            for error in exc.errors(include_url=False, include_input=False, include_context=False)]


def row_model(field):
    args = get_args(field.annotation)
    if get_origin(field.annotation) is list and args and isinstance(args[0], type) and issubclass(args[0], BaseModel):
        return args[0]
    return None


def salvage_rows(contract, parsed):
    """``(answer, dropped)``: the rows that pass their own contract, or ``(None, dropped)``.

    A list of rows keeps every row that validates; the others are reported. A failing field
    without rows that has a default (such as ``kept_ids``) falls back to that default.
    """
    if not isinstance(parsed, dict):
        return None, []
    data, dropped = {}, []
    for name, field in contract.model_fields.items():
        if name not in parsed:
            continue
        value, model = parsed[name], row_model(field)
        if model is None or not isinstance(value, list):
            data[name] = value
            continue
        rows = []
        for index, row in enumerate(value):
            try:
                rows.append(model.model_validate(row).model_dump(mode='json'))
            except ValidationError as exc:
                dropped.append({'field': name, 'index': index, 'issues': issues(exc)})
        data[name] = rows
    for _ in range(2):
        try:
            return contract.model_validate(data), dropped
        except ValidationError as exc:
            failing = {error['loc'][0] for error in exc.errors() if error['loc']}
            resettable = sorted(name for name in failing if name in data and name in contract.model_fields
                                and not contract.model_fields[name].is_required()
                                and row_model(contract.model_fields[name]) is None)
            if not resettable:
                return None, [*dropped, {'field': None, 'issues': issues(exc)}]
            for name in resettable:
                data.pop(name)
                dropped.append({'field': name, 'reset_to_default': True})
    return None, dropped
