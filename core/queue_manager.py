from __future__ import annotations

import asyncio
import json
import re
import shutil
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from core.logger import log
from core import db
from core.ffprobe import (
    probe_file,
    extract_media_info,
    extract_audio_streams,
    extract_subtitle_streams,
    get_duration_us,
    verify_output,
)
from core.ffmpeg import (
    transcode,
    compatible_container,
    build_audio_args,
    strip_audio_flags,
    build_subtitle_args,
    build_scale_filter,
)
from core.devices import encoder_to_device_id, device_display_name
from core.yaml_store import store, DAYS
from core.watcher import suppress_path, unsuppress_path


class JobStatus(str, Enum):
    PENDING = "pending"
    BLOCKED = "blocked"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Job:
    id: str
    file_path: str
    library_name: str
    device: str = "cpu"
    status: JobStatus = JobStatus.PENDING
    old_size_bytes: int = 0
    new_size_bytes: int | None = None
    started_at: str | None = None
    error_message: str | None = None
    ffmpeg_args: str = ""
    output_container: str = ""
    preset_name: str = ""
    block_reason: str | None = None
    media_info: dict | None = None
    seq: int = 0


def job_to_dict(job: Job) -> dict:
    d = {
        "id": job.id,
        "file_path": job.file_path,
        "library_name": job.library_name,
        "device": job.device,
        "status": job.status.value,
        "old_size_bytes": job.old_size_bytes,
        "new_size_bytes": job.new_size_bytes,
        "started_at": job.started_at,
    }
    if job.error_message:
        d["error_message"] = job.error_message
    if job.block_reason:
        d["block_reason"] = job.block_reason
    if job.media_info:
        d["media_info"] = job.media_info
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
        self._blocked: list[Job] = []
        self._active: dict[str, Job] = {}
        self._subscribers: list[asyncio.Queue[str]] = []
        self._lock = asyncio.Lock()
        self._known_paths: set[str] = set()
        self._next_seq = 0
        self._running = asyncio.Event()
        self._running.set()
        self._dispatcher_task: asyncio.Task | None = None
        self._dispatch_event = asyncio.Event()
        self._device_limits: dict[str, int] = {}
        self._device_active: dict[str, int] = {}
        self._paused_libraries: set[str] = set()
        self._schedule_wakeup_handle: asyncio.TimerHandle | None = None
        self._schedule_is_active: bool = True

    @property
    def pending_jobs(self) -> list[Job]:
        return list(self._pending)

    @property
    def active_jobs(self) -> list[Job]:
        return list(self._active.values())

    @property
    def blocked_jobs(self) -> list[Job]:
        return list(self._blocked)

    @property
    def paused(self) -> bool:
        return not self._running.is_set()

    @property
    def paused_libraries(self) -> set[str]:
        return set(self._paused_libraries)

    @property
    def schedule_active(self) -> bool:
        return self._schedule_is_active

    async def start(self, device_limits: dict[str, int]) -> None:
        self._device_limits = dict(device_limits)
        self._device_active = {dev: 0 for dev in device_limits}
        self._dispatcher_task = asyncio.create_task(self._dispatcher())
        self._dispatch_event.set()
        log.info("Queue started, device limits: %s", device_limits)

    async def update_device_limit(self, device_id: str, max_jobs: int) -> None:
        async with self._lock:
            self._device_limits[device_id] = max_jobs
            if device_id not in self._device_active:
                self._device_active[device_id] = 0
        self._dispatch_event.set()
        log.info("Device %s limit set to %d", device_id, max_jobs)

    def _sort_pending(self) -> None:
        order = store.config.settings.queue_order
        if order == "largest_first":
            self._pending.sort(key=lambda j: j.old_size_bytes, reverse=True)
        elif order == "highest_bitrate":
            self._pending.sort(
                key=lambda j: (j.media_info or {}).get("bitrate_kbps", 0),
                reverse=True,
            )
        else:
            self._pending.sort(key=lambda j: j.seq)

    async def queue_order_changed(self) -> None:
        async with self._lock:
            self._sort_pending()
            pending = [job_to_dict(j) for j in self._pending]
        self._dispatch_event.set()
        await self._broadcast("queue_changed", {"pending": pending})

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

    def load_paused_libraries(self, names: set[str]) -> None:
        self._paused_libraries = set(names)

    async def pause_library(self, name: str) -> None:
        self._paused_libraries.add(name)
        await self._broadcast("library_paused", {"library_name": name, "paused": True})
        log.info("Library '%s' paused", name)

    async def resume_library(self, name: str) -> None:
        self._paused_libraries.discard(name)
        await self._broadcast("library_paused", {"library_name": name, "paused": False})
        self._dispatch_event.set()
        log.info("Library '%s' resumed", name)

    async def rename_paused_library(self, old: str, new: str) -> None:
        if old in self._paused_libraries:
            self._paused_libraries.discard(old)
            self._paused_libraries.add(new)
            await self._broadcast(
                "library_paused", {"library_name": old, "paused": False}
            )
            await self._broadcast(
                "library_paused", {"library_name": new, "paused": True}
            )

    async def clear_paused_library(self, name: str) -> None:
        if name in self._paused_libraries:
            self._paused_libraries.discard(name)
            await self._broadcast(
                "library_paused", {"library_name": name, "paused": False}
            )

    def _check_schedule_active(self) -> bool:
        settings = store.config.settings
        if not settings.schedule_enabled:
            return True
        now = datetime.now()
        day_key = DAYS[now.weekday()]
        return settings.schedule[day_key][now.hour]

    def _set_schedule_wakeup(self) -> None:
        if self._schedule_wakeup_handle is not None:
            self._schedule_wakeup_handle.cancel()
        now = datetime.now()
        seconds_to_next_hour = 3600 - (now.minute * 60 + now.second) + 1
        loop = asyncio.get_event_loop()
        self._schedule_wakeup_handle = loop.call_later(
            seconds_to_next_hour, self._dispatch_event.set
        )

    async def schedule_changed(self) -> None:
        was_active = self._schedule_is_active
        self._schedule_is_active = self._check_schedule_active()
        if was_active != self._schedule_is_active:
            await self._broadcast(
                "schedule_status", {"active": self._schedule_is_active}
            )
        self._dispatch_event.set()

    async def _resolve_device(self, library_name: str) -> tuple[str, str | None]:
        library = await store.get_library(library_name)
        if not library:
            return "", "Library not found"
        if not library.preset:
            return "", "No preset assigned"
        preset = await store.get_preset(library.preset)
        if not preset:
            return "", f"Preset '{library.preset}' not found"
        m = re.search(r"-c:v\s+(\S+)", preset.ffmpeg_args)
        if not m:
            return "cpu", None
        return encoder_to_device_id(m.group(1)), None

    async def enqueue(
        self, file_path: str, library_name: str, *, media_info: dict | None = None
    ) -> Job | None:
        async with self._lock:
            if file_path in self._known_paths:
                return None
            self._known_paths.add(file_path)

            try:
                size = Path(file_path).stat().st_size
            except OSError:
                self._known_paths.discard(file_path)
                return None

        device_id, block_reason = await self._resolve_device(library_name)

        ffmpeg_args = ""
        output_container = ""
        preset_name = ""
        if not block_reason:
            library = await store.get_library(library_name)
            preset = await store.get_preset(library.preset)
            ffmpeg_args = preset.ffmpeg_args
            output_container = preset.output_container or ""
            preset_name = library.preset

        if media_info is None:
            probe_data = await probe_file(file_path)
            if probe_data:
                media_info = extract_media_info(probe_data)

        async with self._lock:
            job = Job(
                id=uuid.uuid4().hex[:12],
                file_path=file_path,
                library_name=library_name,
                device=device_id,
                old_size_bytes=size,
                ffmpeg_args=ffmpeg_args,
                output_container=output_container,
                preset_name=preset_name,
                media_info=media_info,
                seq=self._next_seq,
            )
            self._next_seq += 1
            if block_reason:
                job.status = JobStatus.BLOCKED
                job.block_reason = block_reason
                self._blocked.append(job)
                await self._broadcast("job_blocked", job_to_dict(job))
                log.info("Blocked: %s [%s] reason=%s", file_path, job.id, block_reason)
            else:
                self._pending.append(job)
                self._sort_pending()
                await self._broadcast(
                    "job_queued",
                    {**job_to_dict(job), "position": self._pending.index(job)},
                )
                self._dispatch_event.set()
                log.info("Queued: %s [%s] device=%s", file_path, job.id, device_id)
        return job

    async def re_evaluate_blocked(self) -> None:
        unblocked = False
        async with self._lock:
            still_blocked = []
            for job in self._blocked:
                device_id, reason = await self._resolve_device(job.library_name)
                if reason:
                    job.block_reason = reason
                    still_blocked.append(job)
                else:
                    library = await store.get_library(job.library_name)
                    preset = await store.get_preset(library.preset)
                    job.status = JobStatus.PENDING
                    job.device = device_id
                    job.block_reason = None
                    job.ffmpeg_args = preset.ffmpeg_args
                    job.output_container = preset.output_container or ""
                    job.preset_name = library.preset
                    self._pending.append(job)
                    await self._broadcast("job_unblocked", job_to_dict(job))
                    log.info("Unblocked: %s [%s]", job.file_path, job.id)
                    unblocked = True
            self._blocked = still_blocked
            if unblocked:
                self._sort_pending()
                pending = [job_to_dict(j) for j in self._pending]
        if unblocked:
            self._dispatch_event.set()
            await self._broadcast("queue_changed", {"pending": pending})

    def search_jobs(self, query: str) -> list[dict]:
        q = query.lower()
        results = []
        for job in list(self._active.values()) + self._pending + self._blocked:
            if q in job.file_path.lower():
                results.append(job_to_dict(job))
        return results

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

            was_active = self._schedule_is_active
            self._schedule_is_active = self._check_schedule_active()
            if was_active != self._schedule_is_active:
                await self._broadcast(
                    "schedule_status", {"active": self._schedule_is_active}
                )
            if not self._schedule_is_active:
                self._set_schedule_wakeup()
                continue

            async with self._lock:
                still_pending: list[Job] = []
                for job in self._pending:
                    if job.library_name in self._paused_libraries:
                        still_pending.append(job)
                        continue
                    limit = self._device_limits.get(job.device, 1)
                    active = self._device_active.get(job.device, 0)
                    if active >= limit:
                        still_pending.append(job)
                        continue
                    self._active[job.id] = job
                    self._device_active[job.device] = active + 1
                    asyncio.create_task(self._run_job(job))
                self._pending = still_pending

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

            input_path = Path(job.file_path)
            container = job.output_container
            out_ext = "." + container if container else input_path.suffix

            m = re.search(r"-c:v\s+(\S+)", job.ffmpeg_args)
            if m:
                fixed = compatible_container(m.group(1), out_ext)
                if fixed:
                    log.info(
                        "Container %s can't hold %s output, using %s",
                        out_ext,
                        m.group(1),
                        fixed,
                    )
                    out_ext = fixed

            settings = await store.get_settings()
            cache_dir = Path(settings.cache_dir)
            cache_dir.mkdir(parents=True, exist_ok=True)
            temp_output = cache_dir / f"{job.id}{out_ext}"

            ffmpeg_args = job.ffmpeg_args
            audio_maps = None
            preset = await store.get_preset(job.preset_name)
            if preset and preset.audio is not None:
                ffmpeg_args = strip_audio_flags(ffmpeg_args)
                audio_streams = extract_audio_streams(probe_data) if probe_data else []
                audio_result = build_audio_args(preset.audio, audio_streams)
                audio_maps = audio_result.map_args
                ffmpeg_args = f"{audio_result.codec_args} {ffmpeg_args}".strip()

            subtitle_maps = None
            if preset and preset.subtitle is not None:
                sub_streams = extract_subtitle_streams(probe_data) if probe_data else []
                subtitle_maps = build_subtitle_args(preset.subtitle, sub_streams)

            scale_filter = None
            if preset and preset.resolution_cap and job.media_info:
                source_height = job.media_info.get("resolution_height", 0)
                if source_height > 0:
                    scale_filter = build_scale_filter(
                        preset.resolution_cap, source_height
                    )

            result = await transcode(
                input_path=job.file_path,
                output_path=str(temp_output),
                ffmpeg_args=ffmpeg_args,
                audio_maps=audio_maps,
                subtitle_maps=subtitle_maps,
                scale_filter=scale_filter,
                process_priority=store.config.settings.process_priority,
            )
            ffmpeg_log = result.ffmpeg_log

            if result.success:
                ok, reason = await verify_output(str(temp_output), duration_us)
                if not ok:
                    temp_output.unlink(missing_ok=True)
                    job.status = JobStatus.FAILED
                    job.error_message = f"Post-encode verification failed: {reason}"
                    log.warning("Job %s verification failed: %s", job.id, reason)
                else:
                    if out_ext != input_path.suffix:
                        final_path = input_path.with_suffix(out_ext)
                    else:
                        final_path = input_path
                    suppress_path(str(final_path))
                    try:
                        try:
                            temp_output.rename(final_path)
                        except OSError:
                            # cache dir and media can be on different filesystems (Docker)
                            tmp_dest = final_path.with_suffix(
                                final_path.suffix + ".undarr_tmp"
                            )
                            try:
                                shutil.copyfile(temp_output, tmp_dest)
                                tmp_dest.rename(final_path)
                            except Exception:
                                tmp_dest.unlink(missing_ok=True)
                                raise
                            temp_output.unlink(missing_ok=True)
                        if final_path != input_path:
                            input_path.unlink(missing_ok=True)
                    except Exception:
                        unsuppress_path(str(final_path))
                        raise
                    job.file_path = str(final_path)

                    job.status = JobStatus.COMPLETED
                    try:
                        job.new_size_bytes = Path(job.file_path).stat().st_size
                    except OSError:
                        pass
                    saved = job.old_size_bytes - (job.new_size_bytes or 0)
                    log.info(
                        "Completed: %s [%s] saved %s",
                        job.file_path,
                        job.id,
                        _format_size(saved),
                    )
            else:
                temp_output.unlink(missing_ok=True)
                job.status = JobStatus.FAILED
                job.error_message = result.error_message
                log.warning(
                    "Failed: %s [%s] %s", job.file_path, job.id, result.error_message
                )
        except Exception as e:
            job.status = JobStatus.FAILED
            job.error_message = f"[{type(e).__name__}] {e}"
            log.error("Job %s crashed: %s", job.id, e)
        finally:
            duration_secs = time.monotonic() - started
            async with self._lock:
                self._active.pop(job.id, None)
                self._device_active[job.device] -= 1
                self._known_paths.discard(job.file_path)
            if job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
                try:
                    mtime = Path(job.file_path).stat().st_mtime
                except OSError:
                    mtime = 0.0
                await db.mark_processed(job.file_path, job.library_name, mtime)
            await db.insert_job_history(
                id=job.id,
                library_name=job.library_name,
                file_path=job.file_path,
                status=job.status.value,
                old_size_bytes=job.old_size_bytes,
                new_size_bytes=job.new_size_bytes,
                started_at=job.started_at or "",
                finished_at=datetime.now(timezone.utc).isoformat(),
                duration_seconds=duration_secs,
                ffmpeg_log=ffmpeg_log,
                error_message=job.error_message,
                preset_name=job.preset_name,
                device_name=device_display_name(job.device),
            )
            await self._broadcast("job_finished", job_to_dict(job))
            self._dispatch_event.set()

            async def _delayed_unsuppress():
                await asyncio.sleep(5)
                unsuppress_path(job.file_path)

            asyncio.create_task(_delayed_unsuppress())


queue_manager = QueueManager()
