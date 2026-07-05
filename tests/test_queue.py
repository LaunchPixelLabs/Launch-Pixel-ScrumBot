"""Tests for the async work queue (pure stdlib, no external deps)."""
from __future__ import annotations

from scrumbot.queue import RequestQueue


async def test_enqueue_runs_jobs() -> None:
    queue = RequestQueue(num_workers=2)
    await queue.start()
    results: list[int] = []

    async def job(value: int) -> None:
        results.append(value)

    await queue.enqueue(job, 1)
    await queue.enqueue(job, 2)
    await queue.queue.join()
    await queue.stop()

    assert sorted(results) == [1, 2]


async def test_worker_survives_a_failing_job() -> None:
    queue = RequestQueue(num_workers=1)
    await queue.start()
    completed: list[bool] = []

    async def boom() -> None:
        raise RuntimeError("intentional failure")

    async def good() -> None:
        completed.append(True)

    await queue.enqueue(boom)
    await queue.enqueue(good)
    await queue.queue.join()
    await queue.stop()

    # The failing job must not take the worker down with it.
    assert completed == [True]
