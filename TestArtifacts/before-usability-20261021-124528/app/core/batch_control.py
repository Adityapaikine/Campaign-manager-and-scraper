from __future__ import annotations

import threading
import time


class BatchCancelled(RuntimeError):
    """Raised cooperatively when the user cancels a background batch."""


class BatchControl:
    """Thread-safe pause/resume/cancel controller for long-running jobs.

    Workers should call :meth:`checkpoint` between units of work and before
    starting network calls. Pause is cooperative: an already-running HTTP
    request is allowed to finish, then the worker blocks before the next unit.
    """

    def __init__(self) -> None:
        self._resume_event = threading.Event()
        self._resume_event.set()
        self._cancel_event = threading.Event()
        self._lock = threading.Lock()
        self._paused_at: float | None = None

    @property
    def cancelled(self) -> bool:
        return self._cancel_event.is_set()

    @property
    def paused(self) -> bool:
        return not self._resume_event.is_set() and not self.cancelled

    def pause(self) -> None:
        if self.cancelled:
            return
        with self._lock:
            if self._resume_event.is_set():
                self._paused_at = time.monotonic()
                self._resume_event.clear()

    def resume(self) -> None:
        with self._lock:
            self._paused_at = None
            self._resume_event.set()

    def cancel(self) -> None:
        self._cancel_event.set()
        # Release paused workers so they can observe cancellation immediately.
        self._resume_event.set()

    def checkpoint(self, poll_seconds: float = 0.1) -> None:
        """Block while paused and raise :class:`BatchCancelled` if cancelled."""
        if self.cancelled:
            raise BatchCancelled("Batch cancelled by user")
        while not self._resume_event.wait(timeout=max(0.02, poll_seconds)):
            if self.cancelled:
                raise BatchCancelled("Batch cancelled by user")
        if self.cancelled:
            raise BatchCancelled("Batch cancelled by user")
