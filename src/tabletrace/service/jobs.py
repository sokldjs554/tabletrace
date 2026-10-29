"""Async job runner for questions.

The model is CPU-bound, so each question runs in a worker thread; the event loop stays free to
answer status polls and serve the console. Concurrency is bounded (semaphore), the queue is
bounded (429 when full), and each job has a hard timeout (status `timeout`). States:
queued -> running -> done | failed | timeout.
"""
from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

JobStatus = Literal["queued", "running", "done", "failed", "timeout", "cancelled"]


@dataclass
class Job:
    id: str
    request: dict
    status: JobStatus = "queued"
    created: float = field(default_factory=time.time)
    started: float | None = None
    finished: float | None = None
    result: Any = None
    error: str | None = None
    task: asyncio.Task | None = None

    def view(self) -> dict:
        return {
            "id": self.id, "status": self.status, "request": self.request,
            "created": self.created, "started": self.started, "finished": self.finished,
            "elapsed_ms": round(((self.finished or time.time()) - (self.started or self.created)) * 1000, 1),
            "error": self.error,
            "result": self.result.model_dump() if hasattr(self.result, "model_dump") else self.result,
        }


class JobRunner:
    def __init__(self, run_fn: Callable[[dict], Any], max_concurrent: int, timeout_s: float, queue_limit: int) -> None:
        self.run_fn = run_fn
        self.sem = asyncio.Semaphore(max_concurrent)
        self.timeout_s = timeout_s
        self.queue_limit = queue_limit
        self.jobs: dict[str, Job] = {}
        self.max_concurrent = max_concurrent

    @property
    def pending(self) -> int:
        return sum(1 for j in self.jobs.values() if j.status in ("queued", "running"))

    def submit(self, request: dict) -> Job:
        if self.pending >= self.queue_limit:
            raise OverflowError(f"queue full ({self.queue_limit} pending jobs)")
        job = Job(id=uuid.uuid4().hex[:12], request=request)
        self.jobs[job.id] = job
        job.task = asyncio.create_task(self._execute(job))
        return job

    async def _execute(self, job: Job) -> None:
        async with self.sem:
            job.status = "running"
            job.started = time.time()
            loop = asyncio.get_running_loop()
            try:
                job.result = await asyncio.wait_for(loop.run_in_executor(None, self.run_fn, job.request), timeout=self.timeout_s)
                job.status = "done"
            except TimeoutError:
                job.status = "timeout"
                job.error = f"job exceeded {self.timeout_s}s"
            except asyncio.CancelledError:
                job.status = "cancelled"
                raise
            except Exception as e:
                job.status = "failed"
                job.error = f"{type(e).__name__}: {e}"
            finally:
                job.finished = time.time()

    async def wait(self, job: Job, max_wait_s: float | None = None) -> Job:
        if job.task is not None:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(asyncio.shield(job.task), timeout=max_wait_s)
        return job

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def prune(self, max_age_s: float = 3600) -> None:
        now = time.time()
        for jid in [j.id for j in self.jobs.values() if j.finished and now - j.finished > max_age_s]:
            del self.jobs[jid]
