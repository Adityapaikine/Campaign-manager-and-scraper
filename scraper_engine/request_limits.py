"""Shared, bounded request starts and Retry-After cooldowns across worker threads."""
from contextlib import contextmanager
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import threading
import time
from urllib.parse import urlsplit


class RequestDeferred(RuntimeError):
    """A service asked us to wait; keep this lookup available for a later retry."""


class RequestLimits:
    def __init__(self):
        self.condition = threading.Condition()
        self.hosts = {}

    @staticmethod
    def key(url):
        return (urlsplit(url).hostname or url).lower().removeprefix("www.")

    @contextmanager
    def slot(self, url, *, interval=1.0, concurrency=1, budget=None, checkpoint=None, metrics=None):
        key = self.key(url)
        started = time.monotonic()
        while True:
            if checkpoint:
                checkpoint()
            if budget:
                budget.timeout(1)
            with self.condition:
                state = self.hosts.setdefault(key, {"active": 0, "next": 0.0, "blocked": 0.0})
                now = time.monotonic()
                if state["blocked"] > now:
                    raise RequestDeferred(f"Website cooldown active; retry in {int(state['blocked'] - now) + 1} seconds")
                delay = max(state["next"], state["blocked"]) - now
                if state["active"] < max(1, concurrency) and delay <= 0:
                    state["active"] += 1
                    state["next"] = now + max(0, interval)
                    break
                wait = min(0.1, max(0.01, delay)) if delay > 0 else 0.05
            if budget:
                budget.sleep(wait)
            else:
                time.sleep(wait)
        if metrics:
            metrics.count("requests")
            with metrics.lock:
                metrics.seconds["request_wait"] = metrics.seconds.get("request_wait", 0) + time.monotonic() - started
        try:
            yield
        finally:
            with self.condition:
                state["active"] -= 1
                self.condition.notify_all()

    def cooldown(self, url, retry_after=None, default=30.0):
        try:
            seconds = float(retry_after)
        except (TypeError, ValueError):
            try:
                date = parsedate_to_datetime(str(retry_after))
                if date.tzinfo is None:
                    date = date.replace(tzinfo=timezone.utc)
                seconds = (date - datetime.now(timezone.utc)).total_seconds()
            except (TypeError, ValueError, OverflowError):
                seconds = default
        with self.condition:
            state = self.hosts.setdefault(self.key(url), {"active": 0, "next": 0.0, "blocked": 0.0})
            state["blocked"] = max(state["blocked"], time.monotonic() + max(0, seconds))
            self.condition.notify_all()


REQUEST_LIMITS = RequestLimits()
