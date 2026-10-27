"""Which model calls made a decision (rq1-need-trace-v1).

TrackedClient reports the ID of every call it records to the logs open in the calling thread, so the code that asked
for a decision can store the calls behind it next to the decision (need rows, base review, discussion phases,
extraction batches) instead of leaving them to be matched by output later.
"""
from contextlib import contextmanager
from contextvars import ContextVar

OPEN_LOGS = ContextVar('rq1_open_call_logs', default=())


@contextmanager
def recorded_calls(log=None):
    """Collect the IDs of the model calls made in this thread inside the block; nested blocks collect into every
    open log."""
    log = [] if log is None else log
    token = OPEN_LOGS.set((*OPEN_LOGS.get(), log))
    try: yield log
    finally: OPEN_LOGS.reset(token)


def report_call(call_id):
    for log in OPEN_LOGS.get(): log.append(call_id)
