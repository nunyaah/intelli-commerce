"""Ambient run context so tool-level guardrail events can be linked to the active
trace/thread without threading IDs through the agent's tool signatures.
"""
from __future__ import annotations

import contextvars
from contextlib import contextmanager

_trace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("trace_id", default=None)
_thread_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("thread_id", default=None)


def get_context() -> tuple[str | None, str | None]:
    return _trace_id.get(), _thread_id.get()


@contextmanager
def run_context(trace_id: str | None, thread_id: str | None):
    t1 = _trace_id.set(trace_id)
    t2 = _thread_id.set(thread_id)
    try:
        yield
    finally:
        # In a streaming (SSE) generator the body suspends/resumes across
        # contexts, so reset() can raise "Token created in a different Context".
        # The next run overwrites these values anyway, so a failed reset is safe.
        for var, tok in ((_trace_id, t1), (_thread_id, t2)):
            try:
                var.reset(tok)
            except ValueError:
                var.set(None)
