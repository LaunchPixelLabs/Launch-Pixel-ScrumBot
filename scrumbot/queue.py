"""Async work queue: a small worker pool that runs queued coroutines.

Offloads long-running agent turns from the Discord event loop so several
requests are processed concurrently without blocking gateway heartbeats. Jobs
are ``(coroutine_fn, args, kwargs)`` tuples; failures are logged, never fatal.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, List, Optional, Tuple

logger = logging.getLogger(__name__)

Job = Callable[..., Awaitable[Any]]
_QueueItem = Optional[Tuple[Job, tuple, dict]]


class RequestQueue:
    """A fixed pool of asyncio workers draining a shared queue."""

    def __init__(self, num_workers: int = 3) -> None:
        self.queue: "asyncio.Queue[_QueueItem]" = asyncio.Queue()
        self.num_workers = max(1, num_workers)
        self._workers: List[asyncio.Task] = []

    async def start(self) -> None:
        """Spawn the worker tasks (idempotent)."""
        if self._workers:
            return
        self._workers = [
            asyncio.create_task(self._worker(i)) for i in range(self.num_workers)
        ]
        logger.info("RequestQueue started with %d workers.", self.num_workers)

    async def stop(self) -> None:
        """Signal workers to drain and exit, then await them."""
        for _ in self._workers:
            await self.queue.put(None)
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        logger.info("RequestQueue stopped.")

    async def _worker(self, worker_id: int) -> None:
        while True:
            item = await self.queue.get()
            try:
                if item is None:  # shutdown sentinel
                    break
                func, args, kwargs = item
                await func(*args, **kwargs)
            except Exception:  # noqa: BLE001 - one bad job must not kill the worker
                logger.exception("Queue worker %d failed on a job", worker_id)
            finally:
                self.queue.task_done()

    async def enqueue(self, func: Job, *args: Any, **kwargs: Any) -> None:
        """Schedule ``func(*args, **kwargs)`` to run on a worker."""
        await self.queue.put((func, args, kwargs))
