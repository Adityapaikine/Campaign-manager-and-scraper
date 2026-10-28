"""Bounded public-email sessions; browser objects never cross worker threads."""
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
import copy
import queue
import threading

from company_public_data import host


def run_email_batch(rows, factory, apply_result, *, stopped, pause_check, workers=2, progress=None):
    groups = defaultdict(list)
    for row, record in rows:
        groups[host(record.get('Company Website', ''))].append((row, record))
    pending = deque(groups.values())
    total = len(rows)
    completed = 0
    output = queue.Queue(maxsize=max(2, workers * 2))
    sessions = {}
    aborted = threading.Event()
    executors = [ThreadPoolExecutor(max_workers=1, thread_name_prefix=f'public-email-{i}')
                 for i in range(max(1, min(2, workers, len(groups) or 1)))]
    active = {}

    def process(slot, group):
        try:
            if slot not in sessions:
                sessions[slot] = factory()
        except Exception as exc:
            for row, record in group:
                if aborted.is_set() or stopped(): break
                output.put((row, record, exc))
            return
        for row, record in group:
            if aborted.is_set() or stopped() or not pause_check(): break
            try:
                result = sessions[slot].process(copy.deepcopy(record))
                output.put((row, result, None))
            except Exception as exc:
                output.put((row, record, exc))

    if progress: progress(0, total)
    try:
        while pending or active or not output.empty():
            if stopped(): pending.clear()
            for slot, executor in enumerate(executors):
                if slot not in active and pending and not stopped():
                    active[slot] = executor.submit(process, slot, pending.popleft())
            try:
                row, result, error = output.get(timeout=0.05)
                apply_result(row, result, error)
                completed += 1
                if progress: progress(completed, total)
            except queue.Empty:
                pass
            for slot in list(active):
                if active[slot].done():
                    active.pop(slot).result()
        return completed
    finally:
        aborted.set()
        # A failed workbook write must not deadlock a worker publishing its result.
        while any(not future.done() for future in active.values()):
            try: output.get(timeout=0.05)
            except queue.Empty: pass
        try:
            for slot, session in sessions.items():
                executors[slot].submit(session.close).result()
        finally:
            for executor in executors: executor.shutdown(wait=True, cancel_futures=True)
