from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from core.logger import log
from core import db
from core.ffprobe import probe_file, get_duration_us
from core.ffmpeg import transcode


class JobStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Job:
    id: str
    file_path: str
    status: JobStatus = JobStatus.PENDING
    old_size_bytes: int = 0
    new_size_bytes: int | None = None
    started_at: str | None = None
    error_message: str | None = None


def job_to_dict(job: Job) -> dict:
    d = {
        "id": job.id,
        "file_path": job.file_path,
        "status": job.status.value,
        "old_size_bytes": job.old_size_bytes,
        "new_size_bytes": job.new_size_bytes,
        "started_at": job.started_at,
    }
    if job.error_message:
        d["error_message"] = job.error_message
    return d


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1048576:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1073741824:
        return f"{size_bytes / 1048576:.1f} MB"
    return f"{size_bytes / 1073741824:.1f} GB"


class QueueManager:
    def __init__(self) -> None:
        self._pending: list[Job] = []
        self._active: Job | None = None
        self._subscribers: list[asyncio.Queue[str]] = []
        self._lock = asyncio.Lock()
        self._known_paths: set[str] = set()
        self._running = asyncio.Event()
        self._running.set()
        self._dispatcher_task: asyncio.Task | None = None
        self._dispatch_event = asyncio.Event()

    @property
    def pending_jobs(self) -> list[Job]:
        return list(self._pending)

    @property
    def active_job(self) -> Job | None:
        return self._active

    @property
    def paused(self) -> bool:
        return not self._running.is_set()

    async def start(self) -> None:
        self._dispatcher_task = asyncio.create_task(self._dispatcher())
        log.info("Queue started")

    async def stop(self) -> None:
        if self._dispatcher_task:
            self._dispatcher_task.cancel()
            await asyncio.gather(self._dispatcher_task, return_exceptions=True)
            self._dispatcher_task = None
        log.info("Queue stopped")

    async def pause(self) -> None:
        self._running.clear()
        await self._broadcast("queue_paused", {"paused": True})
        log.info("Queue paused")

    async def resume(self) -> None:
        self._running.set()
        self._dispatch_event.set()
        await self._broadcast("queue_paused", {"paused": False})
        log.info("Queue resumed")

    async def enqueue(self, file_path: str, ffmpeg_args: str) -> Job | None:
        async with self._lock:
            if file_path in self._known_paths:
                return None
            self._known_paths.add(file_path)

            try:
                size = Path(file_path).stat().st_size
            except OSError:
                self._known_paths.discard(file_path)
                return None

            job = Job(
                id=uuid.uuid4().hex[:12],
                file_path=file_path,
                old_size_bytes=size,
            )
            # TODO: ffmpeg_args need to be stored on the job
            self._pending.append(job)

        await self._broadcast("job_queued", job_to_dict(job))
        self._dispatch_event.set()
        log.info("Queued: %s [%s]", file_path, job.id)
        return job

    def subscribe(self) -> asyncio.Queue[str]:
        q: asyncio.Queue[str] = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[str]) -> None:
        self._subscribers = [s for s in self._subscribers if s is not q]

    async def _broadcast(self, event: str, data: dict) -> None:
        msg = f"event: {event}\ndata: {json.dumps(data)}\n\n"
        dead: list[asyncio.Queue[str]] = []
        for q in self._subscribers:
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self._subscribers.remove(q)

    async def _dispatcher(self) -> None:
        while True:
            await self._running.wait()
            await self._dispatch_event.wait()
            self._dispatch_event.clear()

            async with self._lock:
                if self._active or not self._pending:
                    continue
                job = self._pending.pop(0)
                self._active = job

            asyncio.create_task(self._run_job(job))

    async def _run_job(self, job: Job) -> None:
        job.status = JobStatus.ACTIVE
        job.started_at = datetime.now(timezone.utc).isoformat()
        await self._broadcast("job_started", job_to_dict(job))
        log.info("Started: %s [%s]", job.file_path, job.id)

        started = time.monotonic()
        ffmpeg_log = ""

        try:
            probe_data = await probe_file(job.file_path)
            duration_us = get_duration_us(probe_data) if probe_data else 0

            # TODO: get ffmpeg_args from job/preset
            result = await transcode(
                input_path=job.file_path,
                output_path=job.file_path,
                ffmpeg_args="-c:v libx265 -crf 24",
            )
            ffmpeg_log = result.ffmpeg_log

            if result.success:
                job.status = JobStatus.COMPLETED
                try:
                    job.new_size_bytes = Path(result.output_path).stat().st_size
                except OSError:
                    pass
                saved = job.old_size_bytes - (job.new_size_bytes or 0)
                log.info("Completed: %s [%s] saved %s", job.file_path, job.id, _format_size(saved))
            else:
                job.status = JobStatus.FAILED
                job.error_message = result.error_message
                log.warning("Failed: %s [%s] %s", job.file_path, job.id, result.error_message)
        except Exception as e:
            job.status = JobStatus.FAILED
            job.error_message = f"[{type(e).__name__}] {e}"
            log.error("Job %s crashed: %s", job.id, e)
        finally:
            duration_secs = time.monotonic() - started
            async with self._lock:
                self._active = None
                self._known_paths.discard(job.file_path)
            await db.insert_job_history(
                id=job.id,
                library_name="",
                file_path=job.file_path,
                status=job.status.value,
                old_size_bytes=job.old_size_bytes,
                new_size_bytes=job.new_size_bytes,
                started_at=job.started_at or "",
                finished_at=datetime.now(timezone.utc).isoformat(),
                duration_seconds=duration_secs,
                ffmpeg_log=ffmpeg_log,
                error_message=job.error_message,
            )
            await self._broadcast("job_finished", job_to_dict(job))
            self._dispatch_event.set()


queue_manager = QueueManager()
