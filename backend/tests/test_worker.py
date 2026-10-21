"""The worker's queue, driven by hand: `inline` off, and no thread — each test
runs the queued jobs itself with `_run_next`."""
import threading

import pytest

import worker


@pytest.fixture(autouse=True)
def queued(monkeypatch):
    monkeypatch.setattr(worker, 'inline', False)
    yield
    while not worker._queue.empty():
        worker._run_next()


def _drain():
    while not worker._queue.empty():
        worker._run_next()


def test_a_keyed_job_waiting_is_queued_once():
    runs = []
    first  = worker.submit(runs.append, 'a', key='k')
    second = worker.submit(runs.append, 'b', key='k')
    assert second is first
    _drain()
    assert runs == ['a']


def test_a_request_goes_ahead_of_the_sweep():
    runs = []
    worker.submit(runs.append, 'sweep 1')
    worker.submit(runs.append, 'sweep 2')
    worker.submit(runs.append, 'request', priority=worker.HIGH)
    _drain()
    assert runs == ['request', 'sweep 1', 'sweep 2']


def test_a_job_moved_up_runs_once_at_its_new_place():
    runs = []
    worker.submit(runs.append, 'sweep')
    low  = worker.submit(runs.append, 'feeds', key='feeds')
    high = worker.submit(runs.append, 'feeds', key='feeds', priority=worker.HIGH)
    assert high is low
    _drain()
    assert runs == ['feeds', 'sweep']


def test_a_failing_job_hands_its_exception_to_whoever_waits():
    def boom():
        raise ValueError('malformed XML')
    future = worker.submit(boom)
    _drain()
    with pytest.raises(ValueError):
        future.result(0)
    assert not worker.busy()


def test_a_job_calling_the_worker_runs_it_rather_than_wait_on_itself(monkeypatch):
    # The worker can't wait on a job queued behind the one it is running.
    monkeypatch.setattr(worker, '_thread', threading.current_thread())
    assert worker.call(lambda: 42) == 42
