#!/usr/bin/env python3
"""Base labels for closed-book (CB) needs (rq1-cb-base-labels-v1).

Junda's option 1: CB needs are labelled by the workbench's procedural base review (base_review expert_v1,
workflow/base_review.py) with the same prompts, the same model and the same pinned base catalogue as the PM run the
CB run is paired with, only without source passages. The domain-use verdict needs a cited passage, so a CB need cannot
get it (see CB_RULE).

The script builds the requests as review_base() does: the same system texts, payload, aliases, batches of four, halves
over the payload budget, contracts, corrections, isolation of valid rows and independent checks. It imports the
workbench read-only and never changes it. The only changes are for having no passages, listed below; each must match
exactly once. Input: a CB record (scripts/closed_book.py) and the PM run, read from a workbench store opened
read-only. Output: one JSON record of kind cb_base_labels with a label per CB need. Neither credentials nor the
provider URL are recorded. Spec: docs/CB_BASE_LABELS.md."""
import argparse
import hashlib
import json
import sqlite3
import sys
import time
from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'requirement-reuse-service'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import closed_book  # noqa: E402  (the CB runner: the same sanitising, client set-up, endpoint comparison and writing)
from closed_book import RecordWriteError, make_client, same_endpoint, sanitized, write_json  # noqa: E402
from requirement_reuse_service.llm.client import (LLMError, OpenAICompatibleClient,  # noqa: E402
                                                  OutputTokenLimitError, OutputValidationError)
from requirement_reuse_service.workflow import base_review as br  # noqa: E402
from requirement_reuse_service.workflow.engine import implementation_identity  # noqa: E402
from requirement_reuse_service.workflow.models import NormalizedIntent, RequirementRecord  # noqa: E402
from requirement_reuse_service.workflow.storage import canonical, digest, now, uid  # noqa: E402

POLICY = 'rq1-cb-base-labels-v1'
# The workflow code the replacements below were last checked against (tests/test_cb_base_labels.py). Other code only
# gives a warning: the parity check with the PM run's recorded base-review calls decides.
CHECKED_IMPLEMENTATION = 'fd154ddc52eb2d87'
# CB needs, like PM's machine inventory, have had no discussion: PM's full review is the before_discussion phase.
PHASE = 'before_discussion'
BATCH = 4                       # review_base(): batches of four needs, in revision-ID order
MAX_TOKENS = 4000               # base_review.generation(): the response budget of every review and check call
ATTEMPTS = 2                    # base_review.generation(): an answer and one correction per batch key
STEPS = {'base_review': br.BaseReview, 'base_review_check': br.BaseReviewChecks}
REQUIRED_RUN_FIELDS = ('run_id', 'base_profile_id', 'base_profile_sha256', 'base_needs_catalogue', 'request')
REQUIRED_NEED_FIELDS = ('need_id', 'statement', 'condition', 'scope')

# The rule for domain-use verdicts. A CB need never gets domain_use_of_base. The CB texts say so and send the case PM
# would label a domain use (an entry names the information and the need adds a value, condition, unit, stronger
# obligation, other resource class or narrower meaning) to uncertain, with the entry, the addition and its kind.
# A domain_use_of_base answer is refused by the workbench's own verdict_errors(): it needs a cited excerpt of the need,
# and a CB need has none. The correction says why (FEEDBACK_REPLACEMENTS); after that the workbench's recovery runs
# unchanged (valid rows kept, the need reviewed alone, at most two attempts each). Every refused answer is counted
# per need (domain_use_refused); a need that keeps the verdict ends not_reviewed. A checked uncertain verdict that
# cites an entry and states an addition is reported as addition_without_passage, CB's counterpart of a domain use.
CB_RULE = ('domain_use_of_base is refused; the case goes to uncertain with the entry and the addition, reported as '
           'addition_without_passage')

# Closed book: each (PM text, CB text) pair replaces wording that presupposes source passages. Every sentence not
# listed stays as PM sends it, including the check's domain-use sentences: no domain-use verdict reaches the check.
REVIEW_REPLACEMENTS = (
    ('Judge each offered need only against the pinned base catalogue and its cited passages.',
     'Judge each offered need only against the pinned base catalogue. No source passages are given.'),
    ('Cite the passage stating the addition.',
     'It needs a cited passage stating the addition, so it cannot be given here.'),
    ('when an entry names it and the need adds a value, condition or narrower meaning, the verdict is '
     'domain_use_of_base.',
     'when an entry names it and the need adds a value, condition or narrower meaning, the verdict is uncertain.'),
    ('uncertain: the catalogue text is insufficient.',
     'uncertain: the catalogue text is insufficient, or an entry names the information and the need adds one of the '
     'additions above; then cite the entry and give the addition and its kind.'),
)
CHECK_REPLACEMENTS = (
    ('Independently check each verdict against the pinned catalogue (base.index and base.entries) and the source '
     'passages.',
     'Independently check each verdict against the pinned catalogue (base.index and base.entries). No source passages '
     'are given.'),
    ('for uncertain the catalogue text is indeed insufficient.',
     'for uncertain the catalogue text is indeed insufficient, or a cited entry names the information and the need '
     'indeed adds the stated addition.'),
)
# The problems verdict_errors() reports that presuppose passages, as message endings after "<need ID>". The
# workbench's correction shows them to the model; the CB endings say what a CB answer can do instead.
FEEDBACK_REPLACEMENTS = (
    (': cite only this item’s excerpts, each once.', ': cite no excerpt: no passages are given.'),
    (': matched entries omit a condition. Cite the entries that state it, or answer domain_use_of_base with the '
     'condition as a cited addition.',
     ': matched entries omit a condition. Cite the entries that state it, or answer uncertain with the condition as '
     'the addition.'),
    (': source-cited addition and kind required.',
     ': domain_use_of_base cannot be given: no passages are given. Answer uncertain, cite the entry and give the '
     'addition and its kind.'),
)
CLASSES = ('restates_base', 'new', 'addition_without_passage', 'uncertain', 'check_failed', 'not_reviewed',
           'not_labelled')


def sha256(text):
    return hashlib.sha256(text.encode()).hexdigest()


RUNNER_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
CLOSED_BOOK_SHA256 = closed_book.RUNNER_SHA256
SCHEMA_SHA256 = {step: sha256(canonical(contract.model_json_schema())) for step, contract in STEPS.items()}


# Texts --------------------------------------------------------------------------------------------------------

def replace_once(text, pairs, what):
    for old, new in pairs:
        if text.count(old) != 1:
            raise ValueError(f'The CB {what} no longer matches the workbench text ({text.count(old)} matches): '
                             f'{old[:70]!r}')
        text = text.replace(old, new)
    return text


def pm_texts():
    """The system texts review_base() sends PM's base review and its check (workflow/base_review.py)."""
    return {'base_review': br.REVIEW_SYSTEM, 'base_review_check': br.CHECK_SYSTEM}


def cb_texts():
    return {'base_review': replace_once(br.REVIEW_SYSTEM, REVIEW_REPLACEMENTS, 'review text'),
            'base_review_check': replace_once(br.CHECK_SYSTEM, CHECK_REPLACEMENTS, 'check text')}


def cb_feedback(errors):
    """The workbench's problems, with the endings of FEEDBACK_REPLACEMENTS replaced (each at most once per problem)."""
    changed = []
    for error in errors:
        for old, new in FEEDBACK_REPLACEMENTS:
            if isinstance(error, str) and error.endswith(old):
                if error.count(old) != 1:
                    raise ValueError(f'A base-review problem holds a replaced ending twice: {error[:120]!r}')
                error = error[:-len(old)] + new
                break
        changed.append(error)
    return changed


def cb_verdict_errors(answer, records, payload, catalogue):
    """verdict_errors() of the workbench, unchanged, with the CB endings (FEEDBACK_REPLACEMENTS)."""
    return cb_feedback(br.verdict_errors(answer, records, payload, catalogue))


def feedback_check(catalogue, base_profile_id):
    """Each ending of FEEDBACK_REPLACEMENTS is what the workbench's verdict_errors() reports for the fault it names,
    once, on a synthetic CB need; a changed workbench message stops the script before any call."""
    need = record_of({'need_id': 'cbneed-feedback-probe', 'statement': 'Users can find the licence of a dataset when '
                      'they plan reuse.', 'condition': 'when they plan reuse', 'scope': 'Dataset'})
    context = {'base_profile_id': base_profile_id, 'evidence_ids': []}
    payload, _ = br.make_payload(None, context, [need], catalogue, PHASE)
    entry = payload['needs'][need.revision_id]['offered_entry_ids'][:1]
    faults = [dict(verdict='new', evidence_ids=['E1']),
              dict(verdict='restates_base', entry_ids=entry),
              dict(verdict='domain_use_of_base', entry_ids=entry, addition_kind='condition', addition='When reused.')]
    found = []
    for (old, _), fault in zip(FEEDBACK_REPLACEMENTS, faults):
        answer = br.BaseReview(verdicts=[br.BaseVerdict(item_id=need.revision_id, rationale='Probe.', **fault)])
        errors = br.verdict_errors(answer, [need], payload, catalogue)
        hits = [e for e in errors if e == need.revision_id + old]
        if len(hits) != 1:
            raise ValueError(f'The workbench no longer reports {old[:60]!r} for this fault; update '
                             'FEEDBACK_REPLACEMENTS.')
        found.append(old)
    return {'status': 'passed', 'endings_checked': len(found)}


def with_schema(system, contract):
    """The system prompt as the OpenAI-compatible workbench client sends it: the JSON schema appended."""
    schema = json.dumps(contract.model_json_schema(), indent=2)
    return (f'{system}\n\nRespond with a single JSON object only - no prose, no markdown fences. '
            f'The JSON object must conform to this JSON Schema:\n{schema}')


def system_as_sent(client, system, contract):
    return with_schema(system, contract) if client is None or isinstance(client, OpenAICompatibleClient) else system


# CB record and needs --------------------------------------------------------------------------------------------

def read_cb_record(path):
    raw = Path(path).read_bytes()
    record = json.loads(raw)
    if not isinstance(record, dict) or record.get('kind') != 'closed_book_run':
        raise ValueError(f'{path} holds no CB record (kind closed_book_run).')
    if record.get('status') != 'completed':
        raise ValueError(f'{path} is a CB record with status {record.get("status")!r}; label a completed CB run.')
    for field in ('cb_run_id', 'pm_run_id', 'base_profile_id', 'base_profile_sha256', 'needs'):
        if not record.get(field):
            raise ValueError(f'The CB record lacks {field}.')
    ids = [need.get('need_id') for need in record['needs'] if isinstance(need, dict)]
    if len(ids) != len(record['needs']) or len(set(ids)) != len(ids):
        raise ValueError('The CB needs are not objects with distinct need_id values.')
    for need in record['needs']:
        missing = [field for field in REQUIRED_NEED_FIELDS if not isinstance(need.get(field), str)]
        if missing or not need['statement'].strip():
            raise ValueError(f'CB need {need["need_id"]} lacks {", ".join(missing) or "a statement"}.')
    return record, hashlib.sha256(raw).hexdigest()


def record_of(need):
    """A CB need as the workbench record review_base() reads: its statement, condition and scope; obligation unknown;
    no evidence links, F/A scope, classifier result or earlier base relation."""
    statement = need['statement']
    return RequirementRecord(requirement_id=need['need_id'], revision_id=need['need_id'], revision_number=1,
                             content_hash=digest(need), raw_statement=statement, normalized_statement=statement,
                             need_statement=statement, need_condition=need['condition'], scope=need['scope'],
                             requirement_type='unknown', normalized_intent=NormalizedIntent(obligation_hint='unknown'),
                             evidence_links=[], support_level='closed_book', lifecycle_state='active')


# PM run ---------------------------------------------------------------------------------------------------------

@contextmanager
def read_only(path, immutable=False):
    """A connection to the workbench store that cannot write: a read-only URI and query_only. immutable=1 also tells
    SQLite that no process writes the file (only for a store whose server is down)."""
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError(f'No workbench store at {path}.')
    db = sqlite3.connect(path.as_uri() + '?mode=ro' + ('&immutable=1' if immutable else ''), uri=True, timeout=30)
    try:
        db.execute('PRAGMA query_only=ON')
        yield db
    finally:
        db.close()


CALL_FIELDS = ('call_id', 'step', 'output_contract', 'system_hash', 'status', 'max_output_tokens',
               'schema_repair_attempts', 'provider.provider', 'provider.model', 'provider.reasoning_effort')


def recorded_review_calls(db, run):
    """The base-review and check calls a run recorded (run part model_calls, or inline in an earlier layout), and the
    endpoints they went to, kept apart: compared, never recorded."""
    calls, endpoints = [], []
    inline = [call for call in run.get('model_calls') or [] if isinstance(call, dict)]
    for call in inline:
        provider = call.get('provider') if isinstance(call.get('provider'), dict) else {}
        calls.append({**{key: call.get(key) for key in CALL_FIELDS if '.' not in key},
                      **{key.split('.')[1]: provider.get(key.split('.')[1]) for key in CALL_FIELDS if '.' in key}})
        endpoints.append(provider.get('base_url'))
    try:
        rows = db.execute('SELECT ' + ', '.join(f"json_extract(body, '$.{key}')" for key in CALL_FIELDS)
                          + ", json_extract(body, '$.provider.base_url') FROM run_parts WHERE run_id=? AND "
                          "part='model_calls' AND json_extract(body, '$.step') IN ('base_review', 'base_review_check') "
                          'ORDER BY sequence', (run['run_id'],)).fetchall()
    except sqlite3.OperationalError:     # a store from before run parts
        rows = []
    for row in rows:
        calls.append({key.split('.')[-1]: value for key, value in zip(CALL_FIELDS, row)})
        endpoints.append(row[-1])
    kept = [(call, endpoint) for call, endpoint in zip(calls, endpoints)
            if call.get('step') in STEPS and call.get('output_contract') == STEPS[call['step']].__name__]
    return [{**call, 'run_id': run['run_id']} for call, _ in kept], [(call['step'], e) for call, e in kept]


def review_attempts(db, run):
    """For each recorded call, the base-review checkpoint (stakeholder_audit) and the attempt it answered: attempt 0
    is sent with the plain system text, a later attempt with the workbench's correction appended."""
    saved = {k: v for k, v in (run.get('stakeholder_audit') or {}).items() if k.startswith(('base_review:',
                                                                                              'base_review_check:'))}
    try:
        saved.update({key: json.loads(body) for key, body in db.execute(
            "SELECT key, body FROM run_parts WHERE run_id=? AND part='stakeholder_audit' AND "
            "(key LIKE 'base_review:%' OR key LIKE 'base_review_check:%')", (run['run_id'],))
            if key.startswith(('base_review:', 'base_review_check:'))})
    except sqlite3.OperationalError:
        pass
    return {call_id: (key, index) for key, checkpoint in saved.items() if isinstance(checkpoint, dict)
            for index, attempt in enumerate(checkpoint.get('attempts') or [])
            for call_id in attempt.get('call_ids') or []}


def read_run(db, run_id):
    row = db.execute("SELECT body FROM objects WHERE kind='run' AND id=?", (run_id,)).fetchone()
    return json.loads(row[0]) if row else None


def read_store(path, run_id, immutable=False):
    """The PM run, its recorded base-review calls (its own or, when it made none, those of the run it was derived
    from) and their checkpoints, read through a read-only connection; nothing is written."""
    with read_only(path, immutable) as db:
        run = read_run(db, run_id)
        if run is None:
            raise ValueError(f'Run {run_id} is not in the store.')
        calls, endpoints, attempts, lineage, current = [], [], {}, [], run
        while True:
            own, ends = recorded_review_calls(db, current)
            calls, endpoints = calls + own, endpoints + ends
            attempts.update(review_attempts(db, current))
            lineage.append({'run_id': current['run_id'], 'base_review_calls': len(own)})
            source_id = (current.get('derived_from') or {}).get('run_id')
            if own or not source_id or source_id in {entry['run_id'] for entry in lineage}:
                break
            current = read_run(db, source_id)
            if current is None:
                break
    return {'run': run, 'scope': 'store', 'calls': calls, 'endpoints': endpoints, 'attempts': attempts,
            'lineage': lineage}


def parity_check(pm, texts=None):
    """Whether the PM texts held here are what PM sent: their digest, as the workbench records system_hash, against
    every base-review and check call the PM run recorded. Corrections (a later attempt of a checkpoint) append the
    workbench's correction and are left out; so are failed calls no checkpoint lists, whose attempt is unknown."""
    texts = texts or pm_texts()
    expected = {step: digest(text) for step, text in texts.items()}
    checked, mismatching, corrections, failed = [], [], 0, 0
    for call in pm['calls']:
        attempt = pm['attempts'].get(call['call_id'])
        if attempt is not None and attempt[1] > 0:
            corrections += 1
            continue
        if attempt is None and call['system_hash'] != expected[call['step']] and call.get('status') != 'completed':
            failed += 1
            continue
        checked.append(call)
        if call['system_hash'] != expected[call['step']]:
            mismatching.append(call['call_id'])
    by_step = {step: sum(c['step'] == step for c in checked) for step in STEPS}
    result = {'status': 'failed' if mismatching else 'passed' if checked else 'not_checked', 'scope': pm['scope'],
              'expected_system_hash': expected, 'runs': pm['lineage'], 'calls_checked': len(checked),
              'calls_checked_by_step': by_step, 'calls_matching': len(checked) - len(mismatching),
              'correction_calls_excluded': corrections, 'failed_calls_excluded': failed,
              'mismatching_call_ids': mismatching[:50]}
    if not checked:
        result['reason'] = 'The PM run and the runs it was derived from record no base-review call.'
    elif not all(by_step.values()):
        result['reason'] = 'The PM run records calls of only one of the two steps.'
        result['status'] = 'failed' if mismatching else 'not_checked'
    return result


def pm_models(pm):
    """The model and reasoning effort of each step as the PM run's recorded calls name them, else step_models and
    step_model_options; and the endpoint of each step (compared, never recorded)."""
    run, models, endpoints = pm['run'], {}, {}
    for step in STEPS:
        identities = {(c.get('provider'), c.get('model'), c.get('reasoning_effort')) for c in pm['calls']
                      if c['step'] == step and c.get('model')}
        ends = {endpoint for s, endpoint in pm['endpoints'] if s == step}
        if len(identities) > 1:
            raise ValueError(f'The PM run made {step} calls with different models; CB copies one model per step.')
        if len(ends) > 1:
            raise ValueError(f'The PM run made {step} calls at different endpoints; CB copies one model per step.')
        endpoints[step] = next(iter(ends), None)
        if identities:
            provider, model, effort = identities.pop()
            models[step] = {'provider': provider, 'model': model, 'reasoning_effort': effort, 'source': 'model_calls'}
            continue
        model = (run.get('step_models') or {}).get(step)
        if not model:
            raise ValueError(f'The PM run records no {step} model (model calls or step_models).')
        option = (run.get('step_model_options') or {}).get(step) or {}
        models[step] = {'provider': None, 'model': model, 'reasoning_effort': option.get('reasoning_effort'),
                        'source': 'step_models'}
    return models, endpoints


def identity(model):
    return {key: model.get(key) for key in ('provider', 'model', 'reasoning_effort')}


# Plan -------------------------------------------------------------------------------------------------------------

def plan(cb, pm, texts=None, validate=None):
    """Check the CB record against the PM run and the pinned catalogue, and build the texts and the first review
    request of every batch; no model call. texts and validate are for the parity tests only."""
    record, run = cb['record'], pm['run']
    missing = [field for field in REQUIRED_RUN_FIELDS if field not in run]
    if missing:
        raise ValueError('The PM run lacks ' + ', '.join(missing) + '.')
    if record['pm_run_id'] != run['run_id']:
        raise ValueError(f'The CB record is paired with {record["pm_run_id"]}, not {run["run_id"]}.')
    if run['request'].get('base_review') != 'expert_v1':
        raise ValueError(f'The PM run used base review {run["request"].get("base_review")!r}, not expert_v1.')
    for field in ('base_profile_id', 'base_profile_sha256'):
        if record[field] != run[field]:
            raise ValueError(f'The CB record and the PM run pin another base ({field}).')
    catalogue = br.pinned_catalogue(run)       # checks the registry sha and the catalogue hash the PM run pinned
    texts = texts or cb_texts()
    feedback = feedback_check(catalogue, run['base_profile_id'])
    parity = parity_check(pm)
    if parity['status'] == 'failed':
        differing = parity['calls_checked'] - parity['calls_matching']
        raise ValueError(f'The base-review texts are not what PM sent: {differing} of the {parity["calls_checked"]} '
                         'calls the PM run recorded have another system_hash.')
    models, endpoints = pm_models(pm)
    records = [record_of(need) for need in record['needs']]
    context = {'base_profile_id': run['base_profile_id'], 'evidence_ids': []}
    batches = first_batches(records, catalogue, context)
    adaptations = [{'text': what, 'pm': old, 'cb': new} for what, pairs in (
        ('base_review', REVIEW_REPLACEMENTS), ('base_review_check', CHECK_REPLACEMENTS),
        ('feedback', FEEDBACK_REPLACEMENTS)) for old, new in pairs]
    label_run_id = uid('cbbl', POLICY, record['cb_run_id'], run['run_id'], catalogue['catalogue_hash'], PHASE,
                       br.POLICY, {step: sha256(text) for step, text in texts.items()}, SCHEMA_SHA256,
                       digest(FEEDBACK_REPLACEMENTS), cb['sha256'])
    return {'label_run_id': label_run_id, 'catalogue': catalogue, 'context': context, 'texts': texts,
            'validate': validate or cb_verdict_errors, 'records': records, 'batches': batches, 'models': models,
            'pm_endpoints': endpoints, 'parity_check': parity, 'feedback_check': feedback, 'adaptations': adaptations}


def first_batches(records, catalogue, context):
    """The batches review_base() sends first, before any answer: four needs in revision-ID order, halved while the
    payload is over the budget; a single need over it is not sent (payload_budget)."""
    selected, batches = sorted(records, key=lambda n: n.revision_id), []

    def split(batch):
        payload, aliases = br.make_payload(None, context, batch, catalogue, PHASE)
        user = canonical(br.translate_ids(payload, {v: k for k, v in aliases.items()}))
        if len(user) > br.MAX_PAYLOAD:
            if len(batch) > 1:
                half = len(batch) // 2
                split(batch[:half])
                split(batch[half:])
                return
            batches.append({'need_ids': [n.revision_id for n in batch], 'sent': False, 'reason': 'payload_budget',
                            'payload_chars': len(user)})
            return
        batches.append({'need_ids': [n.revision_id for n in batch], 'sent': True, 'payload_chars': len(user),
                        'key': 'base_review:' + PHASE + ':' + digest([n.revision_id for n in batch]), 'user': user})
    for i in range(0, len(selected), BATCH):
        split(selected[i:i + BATCH])
    return batches


# The review -----------------------------------------------------------------------------------------------------

class CallFailed(Exception):
    """A transport, authentication or provider failure: the run stops; --resume repeats the call."""


class Labeller:
    """review_base() for needs outside a run: the same procedure, with checkpoints, calls and labels kept in the
    record instead of the store. generate(step, system, user, contract) sends one request."""

    def __init__(self, planned, generate, describe, checkpoints=None, calls=None, on_save=None, sent_as=None):
        self.planned, self.generate, self.describe = planned, generate, describe
        self.checkpoints = checkpoints if checkpoints is not None else {}
        self.calls = calls if calls is not None else []
        self.on_save = on_save or (lambda: None)
        self.sent_as = sent_as or (lambda step, system, contract: with_schema(system, contract))
        self.results, self.done = [], {}

    # base_review.generation(), with the checkpoint in the record
    def generation(self, key, step, contract, system, payload, aliases, validate):
        model = self.describe(step)
        # The workbench digests model_identity(), which holds the endpoint; here the endpoint is left out.
        ident = digest([br.POLICY, system, payload, aliases, contract.model_json_schema(), model])
        saved = self.checkpoints.get(key)
        if saved and saved['identity'] != ident:
            raise ValueError('Base reviewer checkpoint mismatch: ' + key)
        if not saved:
            saved = {'identity': ident, 'model': model, 'attempts': []}
        if saved.get('output'):
            return contract.model_validate(saved['output']), saved
        while len(saved['attempts']) < ATTEMPTS:
            errors, parsed = [], None
            sent = system + (br.correction(saved['attempts'][-1], aliases) if saved['attempts'] else '')
            user = canonical(br.translate_ids(payload, {v: k for k, v in aliases.items()}))
            call_ids = []
            try:
                result = self.send(key, step, contract, len(saved['attempts']) + 1, sent, user, call_ids)
                result = contract.model_validate(br.translate_ids(result.model_dump(mode='json'), aliases))
                errors = validate(result)
                output = result.model_dump(mode='json')
            except (OutputValidationError, OutputTokenLimitError) as exc:
                errors, output, parsed = [str(exc)], None, getattr(exc, 'parsed_payload', None)
            attempt = {'output': output, 'errors': errors, 'call_ids': call_ids}
            if isinstance(parsed, dict):
                attempt['parsed'] = br.translate_ids(parsed, aliases)
            saved['attempts'].append(attempt)
            if not errors:
                saved['output'] = output
            self.checkpoints[key] = saved
            self.on_save()
            if not errors:
                return result, saved
        return None, saved

    def send(self, key, step, contract, attempt, system, user, call_ids):
        sequence = len(self.calls) + 1
        as_sent = self.sent_as(step, system, contract)
        call = {'call_id': uid('cbblcall', self.planned['label_run_id'], sequence), 'sequence': sequence,
                'step': step, 'batch_key': key, 'attempt': attempt, 'purpose': 'initial' if attempt == 1 else
                'correction', 'contract': contract.__name__, 'max_output_tokens': MAX_TOKENS,
                'schema_repair_attempts': 0, 'system_prompt': as_sent, 'user_payload': user,
                'prompt_sha256': sha256(as_sent), 'payload_sha256': sha256(user), 'system_hash': digest(system),
                'context_hash': digest(user), 'started_at': now()}
        call_ids.append(call['call_id'])
        started, result, failure = time.monotonic(), None, None
        try:
            result = self.generate(step, system, user, contract, call)
            call['status'] = 'accepted'
            return result
        except OutputValidationError as exc:
            call.update(status='schema_invalid', error=sanitized(exc, self.client_of(step)),
                        invalid_output=exc.parsed_payload)
            raise
        except OutputTokenLimitError as exc:
            call.update(status='output_cutoff', error=sanitized(exc, self.client_of(step)))
            raise
        except Exception as exc:        # transport, authentication or provider failure: the run stops
            call.update(status='failed', error=sanitized(exc, self.client_of(step)))
            failure = exc
        finally:
            call.setdefault('status', 'interrupted')        # an interrupt (Ctrl-C) while the call was in flight
            call['latency_seconds'] = round(time.monotonic() - started, 3)
            call['output'] = result.model_dump(mode='json') if result is not None else None
            self.calls.append(call)
            self.on_save()
        raise CallFailed(f'{step} call {call["call_id"]} failed: {call["error"]["type"]}') from failure

    def client_of(self, step):
        return getattr(self, 'clients', {}).get(step, object())

    # review_base(): process, check_batch and finish, with the CB texts and validator
    def run(self):
        planned = self.planned
        catalogue, context = planned['catalogue'], planned['context']
        texts, validate = planned['texts'], planned['validate']
        # Fresh copies: the labels are written into the records (base_relation, processing_flags).
        selected = sorted((n.model_copy(deep=True) for n in planned['records']), key=lambda n: n.revision_id)

        def process(batch):
            payload, aliases = br.make_payload(None, context, batch, catalogue, PHASE)
            if len(canonical(br.translate_ids(payload, {v: k for k, v in aliases.items()}))) > br.MAX_PAYLOAD:
                if len(batch) > 1:
                    half = len(batch) // 2
                    process(batch[:half])
                    process(batch[half:])
                    return
                finish(batch, None, None, 'payload_budget', payload, aliases)
                return
            key = 'base_review:' + PHASE + ':' + digest([n.revision_id for n in batch])
            verdict, saved = self.generation(key, 'base_review', br.BaseReview, texts['base_review'], payload, aliases,
                                             lambda a: validate(a, batch, payload, catalogue))
            if verdict:
                check_batch(batch, verdict, key, saved['model'], review_calls=br.used_calls(saved))
                return
            if len(batch) == 1:
                finish(batch, None, None, 'invalid_output', payload, aliases, key, saved['model'],
                       errors=saved['attempts'][-1]['errors'], review_calls=br.used_calls(saved))
                return
            kept = br.isolated(saved, batch, lambda v, n: not validate(br.BaseReview(verdicts=[v]), [n], payload,
                                                                        catalogue), 'verdicts')
            accepted = [n for n in batch if n.revision_id in kept]
            if accepted:
                check_batch(accepted, br.BaseReview(verdicts=[kept[n.revision_id] for n in accepted]), key,
                            saved['model'], {'review': key}, br.used_calls(saved))
            for n in batch:
                if n.revision_id not in kept:
                    process([n])

        def check_batch(batch, verdict, key, model, isolation=None, review_calls=()):
            payload, aliases = br.make_payload(None, context, batch, catalogue, PHASE)
            ids = {n.revision_id for n in batch}
            selected_verdict = br.BaseReview(verdicts=[v for v in verdict.verdicts if v.item_id in ids])
            check_payload = br.make_check_payload(payload, selected_verdict.model_dump(mode='json')['verdicts'],
                                                  catalogue)
            if len(canonical(br.translate_ids(check_payload, {v: k for k, v in aliases.items()}))) > br.MAX_PAYLOAD:
                if len(batch) > 1:
                    half = len(batch) // 2
                    check_batch(batch[:half], verdict, key, model, isolation, review_calls)
                    check_batch(batch[half:], verdict, key, model, isolation, review_calls)
                    return
                finish(batch, None, None, 'payload_budget', payload, aliases, key, model, isolation,
                       review_calls=review_calls)
                return
            check_key = 'base_review_check:' + PHASE + ':' + digest([n.revision_id for n in batch])
            checks, saved = self.generation(check_key, 'base_review_check', br.BaseReviewChecks,
                                            texts['base_review_check'], check_payload, aliases,
                                            lambda a: br.check_errors(a, batch))
            if checks or len(batch) == 1:
                finish(batch, selected_verdict, checks, None if checks else 'check_invalid_output', payload, aliases,
                       key, model, isolation, None if checks else saved['attempts'][-1]['errors'], review_calls,
                       br.used_calls(saved))
                return
            kept = br.isolated(saved, batch, lambda c, n: True, 'checks')
            accepted = [n for n in batch if n.revision_id in kept]
            if accepted:
                finish(accepted, selected_verdict, br.BaseReviewChecks(checks=[kept[n.revision_id] for n in accepted]),
                       None, payload, aliases, key, model, {**(isolation or {}), 'check': check_key}, None,
                       review_calls, br.used_calls(saved))
            for n in batch:
                if n.revision_id not in kept:
                    check_batch([n], verdict, key, model, isolation, review_calls)

        def finish(batch, answer, checks, reason, payload, aliases, key=None, model=None, isolation=None, errors=None,
                   review_calls=(), check_calls=()):
            by_id = {v.item_id: v for v in answer.verdicts} if answer else {}
            checked = {c.item_id: c for c in checks.checks} if checks else {}
            for n in batch:
                if reason:
                    n.base_relation = {'policy': br.POLICY, 'phase': PHASE, 'status': 'not_reviewed', 'reason': reason,
                                       'classifier_state': br.classifier_state(n, PHASE),
                                       'catalogue_hash': catalogue['catalogue_hash'], 'batch_key': key, 'model': model,
                                       'human_accepted': False}
                    if errors:
                        n.base_relation['errors'] = list(errors)
                    n.processing_flags = list(dict.fromkeys([*n.processing_flags, 'base_review_pending']))
                else:
                    br.apply_verdict(n, by_id[n.revision_id], checked.get(n.revision_id), PHASE, catalogue, key, model,
                                     payload)
                if isolation:
                    n.base_relation['isolated_from_failed_batch'] = dict(isolation)
                if review_calls:
                    n.base_relation['review_call_ids'] = list(review_calls)
                if check_calls:
                    n.base_relation['check_call_ids'] = list(check_calls)
                self.done[n.revision_id] = n
                self.results.append(deepcopy(n.base_relation) | {'revision_id': n.revision_id})
            self.on_save()

        for i in range(0, len(selected), BATCH):
            process(selected[i:i + BATCH])
        return self.done


# Labels and record ----------------------------------------------------------------------------------------------

def label_class(relation):
    if not relation:
        return 'not_labelled'
    if relation['status'] in {'not_reviewed', 'check_failed'}:
        return relation['status']
    verdict = relation['verdict']
    if verdict == 'uncertain' and relation.get('entry_ids') and relation.get('addition_kind') != 'none' \
            and (relation.get('addition') or '').strip():
        return 'addition_without_passage'
    if verdict == 'domain_use_of_base':      # cannot pass cb_verdict_errors(); kept visible if it ever does
        return 'domain_use_of_base'
    return verdict


def refused_domain_uses(checkpoints):
    """Per need, the domain_use_of_base answers the CB validator refused (rows of review attempts with problems)."""
    refused = Counter()
    for key, saved in checkpoints.items():
        if not key.startswith('base_review:'):
            continue
        for attempt in saved['attempts']:
            if not attempt.get('errors'):
                continue
            answer = attempt.get('output') or attempt.get('parsed') or {}
            rows = answer.get('verdicts') if isinstance(answer.get('verdicts'), list) else []
            refused.update(r['item_id'] for r in rows if isinstance(r, dict) and isinstance(r.get('item_id'), str)
                           and r.get('verdict') == 'domain_use_of_base')
    return refused


def labels_of(cb, done, checkpoints):
    """One label per CB need, in the record's order: the scorer's view (covered_by_base, as PM's revision-info) and
    the workbench's base_relation and flags."""
    refused, labels = refused_domain_uses(checkpoints), []
    for need in cb['record']['needs']:
        record = done.get(need['need_id'])
        relation = deepcopy(record.base_relation) if record is not None else None
        flags = list(record.processing_flags) if record is not None else []
        covered = None if record is None else 'covered_by_base' in flags       # None: not labelled (yet)
        labels.append({'need_id': need['need_id'], 'role_id': need.get('role_id'), 'statement': need['statement'],
                       'condition': need['condition'], 'covered_by_base': covered,
                       'base_label': None if covered is None else 'covered' if covered else 'working',
                       'label_class': label_class(relation), 'domain_use_refused': refused[need['need_id']],
                       'processing_flags': flags, 'base_relation': relation})
    return labels


def assemble(cb, pm, planned, status, created_at, models, endpoint_match, allow_other_endpoint, labeller=None):
    run, record = pm['run'], cb['record']
    labeller = labeller or Labeller(planned, None, lambda step: identity(planned['models'][step]))
    labels = labels_of(cb, labeller.done, labeller.checkpoints)
    classes = Counter(label['label_class'] for label in labels)
    workbench, catalogue = implementation_identity(), planned['catalogue']
    texts = planned['texts']
    return {
        'kind': 'cb_base_labels', 'policy_version': POLICY, 'label_run_id': planned['label_run_id'],
        'created_at': created_at, 'updated_at': now(), 'status': status, 'cb_run_id': record['cb_run_id'],
        'cb_record_sha256': cb['sha256'], 'cb_policy_version': record.get('policy_version'), 'rep': record.get('rep'),
        'benchmark_case_id': record.get('benchmark_case_id'), 'pm_run_id': run['run_id'],
        'base_profile_id': run['base_profile_id'], 'base_profile_sha256': run['base_profile_sha256'],
        'catalogue': {'catalogue_hash': catalogue['catalogue_hash'], 'entries': len(catalogue['entries']),
                      'policy_version': catalogue.get('policy_version')},
        'phase': PHASE, 'base_review_policy': br.POLICY, 'rule': CB_RULE,
        'pm_implementation_hash': run.get('implementation_hash'), 'workbench_implementation_hash': workbench,
        'runner_sha256': RUNNER_SHA256, 'closed_book_runner_sha256': CLOSED_BOOK_SHA256,
        'models': {step: {**identity(models.get(step) or planned['models'][step]),
                          'copied_from': planned['models'][step]['source'], 'max_output_tokens': MAX_TOKENS}
                   for step in STEPS},
        'contract': {step: {'name': contract.__name__, 'schema_sha256': SCHEMA_SHA256[step],
                            'system_sha256': sha256(texts[step]),
                            'openai_compatible_system_prompt_sha256': sha256(with_schema(texts[step], contract)),
                            'pm_system_hash': digest(pm_texts()[step])} for step, contract in STEPS.items()},
        'adaptations': planned['adaptations'], 'system_texts': dict(texts),
        'counts': {'needs': len(labels), 'covered': sum(l['covered_by_base'] is True for l in labels),
                   'working': sum(l['covered_by_base'] is False for l in labels),
                   'not_labelled': sum(l['covered_by_base'] is None for l in labels),
                   'by_class': {name: classes[name] for name in CLASSES if classes[name]} | (
                       {'domain_use_of_base': classes['domain_use_of_base']} if classes['domain_use_of_base'] else {}),
                   'domain_use_refused': sum(l['domain_use_refused'] for l in labels),
                   'needs_with_domain_use_refused': sum(bool(l['domain_use_refused']) for l in labels),
                   'review_batches_first': sum(b['sent'] for b in planned['batches']),
                   'calls': len(labeller.calls), 'calls_by_step': dict(Counter(c['step'] for c in labeller.calls))},
        'labels': labels,
        # The shape of the benchmark scorer's private/revision-info.json for PM runs, with the CB need IDs; only
        # labelled needs.
        'revision_info': {'run_id': record['cb_run_id'], 'revisions': {
            label['need_id']: {'lifecycle': 'active', 'covered_by_base': label['covered_by_base'], 'parents': []}
            for label in labels if label['covered_by_base'] is not None}, 'set_aside_without_need_statement': []},
        'results': labeller.results, 'checkpoints': labeller.checkpoints, 'calls': labeller.calls,
        'diagnostics': {'parity_check': planned['parity_check'], 'feedback_check': planned['feedback_check'],
                        'first_batches': [{k: v for k, v in b.items() if k != 'user'} for b in planned['batches']],
                        'implementation_matches_pm': run.get('implementation_hash') == workbench,
                        'implementation_is_checked': workbench.startswith(CHECKED_IMPLEMENTATION),
                        'endpoint_matches_pm': endpoint_match, 'other_endpoint_allowed': allow_other_endpoint,
                        'failed_calls': [c['call_id'] for c in labeller.calls if c['status'] == 'failed']}}


def prompts_only(cb, pm, out, planned):
    """The first review request of every batch, as the OpenAI-compatible client sends it, and the check text; no model
    call. The check requests and any correction depend on the answers."""
    record = assemble(cb, pm, planned, 'prompts_only', now(), {}, None, False)
    review, check = planned['texts']['base_review'], planned['texts']['base_review_check']
    record['planned_requests'] = [{'step': 'base_review', 'batch_key': b['key'], 'need_ids': b['need_ids'],
                                   'system_prompt': with_schema(review, br.BaseReview),
                                   'system_prompt_sha256': sha256(with_schema(review, br.BaseReview)),
                                   'system_hash': digest(review), 'user_payload': b['user'],
                                   'payload_sha256': sha256(b['user']), 'context_hash': digest(b['user'])}
                                  for b in planned['batches'] if b['sent']]
    record['planned_check'] = {'step': 'base_review_check', 'system_prompt': with_schema(check, br.BaseReviewChecks),
                               'system_prompt_sha256': sha256(with_schema(check, br.BaseReviewChecks)),
                               'system_hash': digest(check),
                               'note': 'One check request follows each accepted review batch; its payload holds the '
                                       'verdicts.'}
    write_json(out, record)
    return record


# Model calls ----------------------------------------------------------------------------------------------------

def clients_for(models):
    """One workbench client per model setting, configured by the RRS_LLM_* environment variables."""
    made, clients = {}, {}
    for step, model in models.items():
        key = (model['model'], model['reasoning_effort'])
        if key not in made:
            made[key] = make_client(model)
        clients[step] = made[key]
    return clients


def client_identities(clients, models, pm_endpoints):
    """Each client's provider, model and effort, checked against PM's; the endpoints are compared, never recorded."""
    found, matches = {}, []
    for step, client in clients.items():
        described = client.describe() if hasattr(client, 'describe') else {}
        found[step] = identity(described)
        model = models[step]
        if found[step]['model'] != model['model'] or (model['source'] == 'model_calls' and (
                found[step]['reasoning_effort'] != model['reasoning_effort']
                or (model['provider'] and found[step]['provider'] != model['provider']))) or (
                model['source'] == 'step_models' and model['reasoning_effort'] is not None
                and found[step]['reasoning_effort'] != model['reasoning_effort']):
            raise ValueError(f'The configured {step} client ({found[step]}) is not the PM model ({identity(model)}).')
        endpoint, pm_endpoint = described.get('base_url'), pm_endpoints.get(step)
        matches.append(same_endpoint(endpoint, pm_endpoint) if endpoint and pm_endpoint else None)
    match = False if False in matches else None if None in matches else True
    return found, match


def resumed(previous, planned, found, endpoint_match, allow_other_endpoint):
    """The checkpoints and calls of an earlier record of the same labelling, written by this script, workbench,
    models and endpoint comparison."""
    if previous.get('kind') != 'cb_base_labels':
        raise ValueError('--out holds another record; it is not this labelling.')
    if previous.get('status') == 'prompts_only':
        raise ValueError('--out holds a prompts-only record; write the labels to another path.')
    if previous.get('label_run_id') != planned['label_run_id']:
        raise ValueError('--out holds the labels of another CB record, text or catalogue; write to another path.')
    written_by = (previous.get('runner_sha256'), previous.get('closed_book_runner_sha256'))
    if written_by != (RUNNER_SHA256, CLOSED_BOOK_SHA256):
        raise ValueError('--out was written by another version of this script; write the labels to another path.')
    if previous.get('workbench_implementation_hash') != implementation_identity():
        raise ValueError('--out was written with another workbench implementation; write to another path.')
    diagnostics = previous.get('diagnostics') or {}
    if diagnostics.get('endpoint_matches_pm') != endpoint_match:
        raise ValueError('--out was written at an endpoint that compares otherwise with the PM endpoint.')
    if diagnostics.get('other_endpoint_allowed') != allow_other_endpoint:
        raise ValueError('--out was written with another --allow-other-endpoint setting.')
    if {step: identity(m) for step, m in (previous.get('models') or {}).items()} != found:
        raise ValueError('--out was written with another model configuration.')
    return deepcopy(previous.get('checkpoints') or {}), deepcopy(previous.get('calls') or [])


def run_labels(cb, pm, clients, out, planned, *, resume=False, allow_other_endpoint=False):
    """Label every CB need, writing the record after each saved answer and call. ValueError and OSError before the first
    call mean nothing was called; RecordWriteError means calls were made but the record could not be written. A failed
    call stops the run (status incomplete); an interrupt writes status interrupted and is raised again."""
    if planned['parity_check']['status'] != 'passed':
        raise ValueError(f'Model calls need the parity check with the PM run to pass; it is '
                         f'{planned["parity_check"]["status"]}.')
    found, endpoint_match = client_identities(clients, planned['models'], planned['pm_endpoints'])
    if endpoint_match is False and not allow_other_endpoint:
        raise ValueError('The configured endpoint is not the one the PM run used. Pass --allow-other-endpoint to call '
                         'it anyway; the record notes it.')
    out, previous = Path(out), None
    if resume and out.exists():
        previous = json.loads(out.read_text())
        if not isinstance(previous, dict):
            raise ValueError(f'{out} holds no label record (the JSON is not an object); write to another path.')
    checkpoints, calls = resumed(previous, planned, found, endpoint_match, allow_other_endpoint) \
        if previous is not None else ({}, [])
    if previous is not None and previous.get('status') == 'completed':
        return previous                 # nothing left to call: the completed record stays as it is
    created_at = previous['created_at'] if previous is not None else now()
    models = {step: found[step] for step in STEPS}
    state = {'calls_made': False}

    def generate(step, system, user, contract, call):
        state['calls_made'] = True
        client = clients[step]
        try:
            return client.generate_structured(system=system, user=user, output_model=contract, max_tokens=MAX_TOKENS)
        finally:
            metadata = client.last_call_metadata() if hasattr(client, 'last_call_metadata') else {}
            call.update(token_usage=metadata.get('token_usage'), finish_reason=metadata.get('finish_reason'),
                        generations=metadata.get('generation_attempts', []))

    labeller = Labeller(planned, generate, lambda step: found[step], checkpoints, calls,
                        sent_as=lambda step, system, contract: system_as_sent(clients[step], system, contract))
    labeller.clients = clients

    def write(status):
        try:
            write_json(out, assemble(cb, pm, planned, status, created_at, models, endpoint_match, allow_other_endpoint,
                                     labeller))
        except OSError as exc:
            if not state['calls_made'] and previous is None:
                raise
            raise RecordWriteError(f'{out}: the record could not be written after model calls were made: '
                                   f'{exc}') from exc
    labeller.on_save = lambda: write('running')
    write('running')
    try:
        labeller.run()
        status = 'completed'
    except CallFailed:
        status = 'incomplete'
    except BaseException:
        try:
            write('interrupted')
        except RecordWriteError:
            pass
        raise
    record = assemble(cb, pm, planned, status, created_at, models, endpoint_match, allow_other_endpoint, labeller)
    try:
        write_json(out, record)
    except OSError as exc:
        raise RecordWriteError(f'{out}: the record could not be written after model calls were made: {exc}') from exc
    return record


def warn(message):
    print(f'cb_base_labels: warning: {message}', file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--cb-record', type=Path, required=True, help='CB record (scripts/closed_book.py), completed')
    parser.add_argument('--store', type=Path, required=True, help='workbench SQLite store holding the PM run, opened '
                        'read-only')
    parser.add_argument('--run-id', help="PM run ID (default: the CB record's pm_run_id; another one is refused)")
    parser.add_argument('--immutable', action='store_true', help='open the store with immutable=1 as well: only for a '
                        'store no process writes (its server is down)')
    parser.add_argument('--out', type=Path, required=True, help='output label record (JSON)')
    parser.add_argument('--allow-live-provider', action='store_true',
                        help='required for model calls: at most two attempts per review or check batch')
    parser.add_argument('--allow-other-endpoint', action='store_true',
                        help='call the configured endpoint although it is not the one the PM run used')
    parser.add_argument('--prompts-only', action='store_true', help='record the first requests without calling a model')
    parser.add_argument('--resume', action='store_true',
                        help='keep the saved answers and calls of the record at --out and make only the missing calls')
    args = parser.parse_args(argv)
    try:                                # nothing below calls a model: every refusal exits with 2
        if args.out.exists() and (args.prompts_only or not args.resume):
            raise ValueError(f'{args.out} exists; use --resume to complete a label record, or another path.')
        record, record_sha = read_cb_record(args.cb_record)
        if args.run_id and args.run_id != record['pm_run_id']:
            raise ValueError(f'--run-id {args.run_id} is not the CB record\'s PM run {record["pm_run_id"]}.')
        cb = {'record': record, 'sha256': record_sha}
        pm = read_store(args.store, record['pm_run_id'], args.immutable)
        planned = plan(cb, pm)
        if not implementation_identity().startswith(CHECKED_IMPLEMENTATION):
            warn(f'this workbench is {implementation_identity()[:16]}, not {CHECKED_IMPLEMENTATION}, the code the '
                 'replacements were last checked against; the parity check with the PM run decides')
        parity = planned['parity_check']
        if args.prompts_only:
            if parity['status'] != 'passed':
                warn(f'parity with the PM run is {parity["status"]}: {parity.get("reason", "")}')
            prompts_only(cb, pm, args.out, planned)
            sent = [b for b in planned['batches'] if b['sent']]
            print(f'{args.out}: {len(planned["records"])} needs, {len(sent)} review batches '
                  f'({len(planned["batches"]) - len(sent)} over the payload budget), {len(sent)} first review requests '
                  f'recorded, no model called. Parity check: {parity["status"]} ({parity["calls_matching"]} of '
                  f'{parity["calls_checked"]} PM calls, {parity["correction_calls_excluded"]} corrections left out). '
                  f'Adaptations: {len(planned["adaptations"])}, each matched once.')
            return 0
        if not args.allow_live_provider:
            raise ValueError('Model calls need --allow-live-provider (or use --prompts-only).')
        if parity['status'] != 'passed':
            raise ValueError(f'Model calls need the parity check with the PM run to pass; it is {parity["status"]}: '
                             f'{parity.get("reason", "")}')
        clients = clients_for(planned['models'])
        result = run_labels(cb, pm, clients, args.out, planned, resume=args.resume,
                            allow_other_endpoint=args.allow_other_endpoint)
    except RecordWriteError as exc:
        print(f'cb_base_labels: error: {exc}', file=sys.stderr)
        return 3
    except (ValueError, KeyError, OSError, LLMError, sqlite3.Error) as exc:
        print(f'cb_base_labels: error: {exc}', file=sys.stderr)
        return 2
    if result['diagnostics']['endpoint_matches_pm'] is None:
        warn('the PM run records no endpoint, or the client describes none; the endpoints were not compared')
    counts = result['counts']
    print(f'{args.out}: {result["label_run_id"]} {result["status"]}, {counts["needs"]} needs: {counts["covered"]} '
          f'covered, {counts["working"]} working; {counts["calls"]} calls')
    return 0 if result['status'] == 'completed' else 1


if __name__ == '__main__':
    sys.exit(main())
