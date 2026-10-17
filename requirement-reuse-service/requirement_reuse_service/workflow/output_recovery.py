"""Recover usable output from an answer that failed its output contract.

Role selection keeps the rows that pass their own contract unchanged; nothing is trimmed,
rewritten or invented. Extraction resets typed labels outside their values to unknown.
Both apply after the client's single schema correction, to complete JSON only. Only an
answer with nothing usable in it, or a provider failure, stops a run.
"""
from copy import deepcopy
from typing import get_args, get_origin

from pydantic import BaseModel, ValidationError

POLICY = 'rq1-role-selection-output-recovery-v1'
LABEL_POLICY = 'rq1-extraction-label-recovery-v1'
# Typed labels of an extraction proposal are suggestions, not evidence. Each has a value
# that says the label is not known; no other value is ever guessed.
NEUTRAL_LABELS = {('requirement_type',): 'unknown', ('intent', 'resource_type'): 'Unknown',
                  ('intent', 'value_kind'): 'unknown', ('intent', 'obligation_hint'): 'unknown'}
RECORDED_VALUE_CHARS = 200


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


def reset_unknown_labels(contract, issues, parsed):
    """``(answer, resets)`` when every issue is a typed label outside its values, else ``(None, [])``.

    Each such label is set to its neutral unknown value and recorded with the value the
    model gave. Statements, citations, scope, support level and task links stay as answered;
    an obligation is never added. Any other issue leaves the answer rejected as before.
    """
    if not isinstance(parsed, dict) or not issues:
        return None, []
    data, resets, seen = deepcopy(parsed), [], set()
    rows = data.get('observations')
    for issue in issues:
        loc = list(issue.get('loc') or [])
        field = tuple(loc[2:])
        if (issue.get('type') != 'literal_error' or len(loc) < 3 or loc[0] != 'observations'
                or type(loc[1]) is not int or field not in NEUTRAL_LABELS):
            return None, []
        if (loc[1], field) in seen:
            continue
        row = rows[loc[1]] if isinstance(rows, list) and 0 <= loc[1] < len(rows) else None
        holder = row.get('intent') if len(field) == 2 and isinstance(row, dict) else row
        if not isinstance(holder, dict) or field[-1] not in holder:
            return None, []
        value = holder[field[-1]]
        resets.append({'observation_index': loc[1], 'field': '.'.join(field),
                       'value': (value if isinstance(value, str) else repr(value))[:RECORDED_VALUE_CHARS],
                       'replacement': NEUTRAL_LABELS[field]})
        holder[field[-1]] = NEUTRAL_LABELS[field]
        seen.add((loc[1], field))
    try:
        return contract.model_validate(data), resets
    except ValidationError:
        return None, []
