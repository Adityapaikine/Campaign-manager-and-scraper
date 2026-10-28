"""A shared wall-clock allowance for one lookup, isolated per worker/thread."""
from contextlib import contextmanager
from contextvars import ContextVar
import time


class LookupTimeout(TimeoutError):
    pass


_deadline = ContextVar("lookup_deadline", default=None)


def active():
    return _deadline.get() is not None


def remaining():
    deadline = _deadline.get()
    return float("inf") if deadline is None else max(0.0, deadline - time.monotonic())


def timeout(seconds):
    left = remaining()
    if left <= 0.02:
        raise LookupTimeout("Lookup time budget reached")
    return min(float(seconds), left)


def sleep(seconds):
    delay = timeout(seconds)
    time.sleep(delay)
    timeout(1)


@contextmanager
def budget(seconds=15):
    deadline = time.monotonic() + max(0.02, float(seconds))
    previous = _deadline.get()
    token = _deadline.set(min(deadline, previous) if previous is not None else deadline)
    try:
        yield
    finally:
        _deadline.reset(token)
