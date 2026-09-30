"""Fixed stage reporting; no user-provided log text crosses this boundary."""
from contextvars import ContextVar

reporter = ContextVar('operation_progress', default=None)


def report(stage: str) -> None:
    callback = reporter.get()
    if callback:
        callback(stage)
