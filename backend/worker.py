"""The one thread that changes the catalog.

Every write — fetching the feeds, reading an episode with the LLM, resolving an
appearance, refreshing a game, purging — runs here, one job at a time. That is
what keeps the writers safe without locks of their own: two resolutions of one
appearance can't interleave, and a sweep can't race a rebuild or a purge.
Requests only read (under `catalog_state.lock`), or submit a job and wait for it.

Jobs are small — one appearance, one game, one episode — so a request's job
(HIGH) waits behind the job running, never behind a whole sweep. A job with a
`key` is queued once: submitting it again while it waits returns the same
Future, or moves it up when asked for at a higher priority.
"""
import concurrent.futures
import functools
import itertools
import logging
import queue
import threading
import time

logger = logging.getLogger(__name__)

HIGH, LOW = 0, 1

# A request waiting on the worker gives up after this long rather than hang.
CALL_TIMEOUT_S = 120

# Tests: run each job at once, in the caller's thread.
inline = False

_queue:  queue.PriorityQueue = queue.PriorityQueue()
_lock    = threading.Lock()
_seq     = itertools.count()
_waiting: dict[str, tuple[int, concurrent.futures.Future]] = {}   # key → (priority, future)
_running = False
_thread: threading.Thread | None = None


def submit(fn, *args, key: str | None = None, priority: int = LOW,
           **kwargs) -> concurrent.futures.Future:
    """Queue `fn(*args, **kwargs)`; its Future carries the result or exception."""
    job = functools.partial(fn, *args, **kwargs)
    if inline or threading.current_thread() is _thread and priority == HIGH:
        # On the worker itself a HIGH job can't wait its turn: the caller is
        # holding it up.
        future = concurrent.futures.Future()
        _run(job, future, key)
        return future
    with _lock:
        if key in _waiting:
            queued_priority, future = _waiting[key]
            if priority >= queued_priority:
                return future
        else:
            future = concurrent.futures.Future()
        if key is not None:
            _waiting[key] = (priority, future)
        # A job moved up stays queued at its old priority too; whichever copy
        # comes out first runs, and the other is skipped (`_run_next`).
        _queue.put((priority, next(_seq), key, job, future))
    return future


def call(fn, *args, key: str | None = None, **kwargs):
    """Run `fn` on the worker at HIGH priority and return its result (raising its
    exception, or TimeoutError after CALL_TIMEOUT_S)."""
    return submit(fn, *args, key=key, priority=HIGH, **kwargs).result(CALL_TIMEOUT_S)


def wait(futures, deadline: float) -> None:
    """Wait for `futures` until the monotonic `deadline` at most."""
    concurrent.futures.wait(futures, timeout=max(0.0, deadline - time.monotonic()))


def busy() -> bool:
    """Whether any work is running or queued."""
    with _lock:
        return _running or bool(_waiting) or not _queue.empty()


def _run_next() -> None:
    global _running
    _, _, key, job, future = _queue.get()
    with _lock:
        if key is not None:
            if _waiting.get(key, (None, None))[1] is not future:
                return                  # the other copy of a job moved up already ran
            del _waiting[key]
        _running = True
    try:
        _run(job, future, key)
    finally:
        with _lock:
            _running = False


def _run(job, future: concurrent.futures.Future, key: str | None) -> None:
    if not future.set_running_or_notify_cancel():
        return
    try:
        future.set_result(job())
    except Exception as exc:
        logger.exception('Job %s failed', key or getattr(job.func, '__name__', job))
        future.set_exception(exc)


def start() -> None:
    global _thread
    if _thread:
        return
    _thread = threading.Thread(target=_loop, daemon=True, name='catalog-worker')
    _thread.start()


def _loop() -> None:
    while True:
        _run_next()
