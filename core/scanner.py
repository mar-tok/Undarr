from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from core.logger import log
from core.ffprobe import is_video_file, probe_file, extract_media_info
from core.skip_rules import should_skip, match_path_pattern, format_rule
from core.yaml_store import Library, store
from core import db


def _collect_video_files(library: Library) -> list[Path]:
    files: list[Path] = []
    for dir_path in library.paths:
        p = Path(dir_path)
        if not p.exists():
            log.warning("Library path does not exist: %s", dir_path)
            continue
        for file in p.rglob("*"):
            if file.is_file() and is_video_file(str(file)):
                files.append(file)
    return files


async def scan_library(
    library_name: str,
    library: Library,
    enqueue_fn,
) -> tuple[int, int]:
    if not library.preset:
        log.warning("Scan skipped for '%s': no preset assigned", library_name)
        return 0, 0

    files = _collect_video_files(library)
    count = 0
    skipped = 0
    for file in files:
        try:
            st = file.stat()
        except OSError:
            continue

        file_str = str(file)
        if await db.is_processed(file_str, library_name, st.st_mtime):
            continue

        if library.new_file_delay:
            newest = max(st.st_mtime, st.st_ctime)
            age = time.time() - newest
            if age < library.new_file_delay_seconds:
                continue

        result = await scan_single_file(file_str, library_name, library, enqueue_fn)
        if result == "queued":
            count += 1
        elif result == "skipped":
            skipped += 1

    log.info("Scan of '%s': queued %d, skipped %d", library_name, count, skipped)
    return count, skipped


def _relative_to_library(file_path: str, library_paths: list[str]) -> str | None:
    fp = Path(file_path)
    for root in library_paths:
        try:
            return str(fp.relative_to(root))
        except ValueError:
            continue
    return None


async def _log_skip(
    file_path: str, library_name: str, preset: str, reason: str
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    try:
        st = Path(file_path).stat()
        file_size = st.st_size
        mtime = st.st_mtime
    except OSError:
        file_size = 0
        mtime = None
    await db.insert_job_history(
        id=str(uuid.uuid4()),
        library_name=library_name,
        file_path=file_path,
        status="skipped (rule)",
        old_size_bytes=file_size,
        new_size_bytes=None,
        started_at=now,
        finished_at=now,
        duration_seconds=0,
        ffmpeg_log="",
        error_message=reason,
        preset_name=preset,
        device_name="",
    )
    if mtime is not None:
        await db.mark_processed(file_path, library_name, mtime)


async def scan_single_file(
    file_path: str,
    library_name: str,
    library: Library,
    enqueue_fn,
) -> str:
    """Returns 'queued', 'skipped', or 'none'."""
    if library.path_patterns:
        rel_path = _relative_to_library(file_path, library.paths)
        if rel_path:
            matched = match_path_pattern(rel_path, library.path_patterns)
            if matched:
                log.debug("Skipping %s (matched path pattern: %s)", file_path, matched)
                await _log_skip(
                    file_path,
                    library_name,
                    library.preset or "",
                    f"Matched path pattern: {matched}",
                )
                return "skipped"

    media_info = None
    probe_data = await probe_file(file_path)
    if probe_data:
        media_info = extract_media_info(probe_data)
    if library.skip_rules and media_info:
        matched_rule = should_skip(media_info, library.skip_rules)
        if matched_rule:
            log.debug(
                "Skipping %s (matched skip rule: %s)",
                file_path,
                format_rule(matched_rule),
            )
            await _log_skip(
                file_path,
                library_name,
                library.preset or "",
                f"Matched skip rule: {format_rule(matched_rule)}",
            )
            return "skipped"

    result = await enqueue_fn(file_path, library_name, media_info=media_info)
    return "queued" if result is not None else "none"


async def mark_library_processed(
    library_name: str,
    library: Library,
) -> int:
    count = 0
    for file in _collect_video_files(library):
        try:
            st = file.stat()
        except OSError:
            continue
        await db.mark_processed(str(file), library_name, st.st_mtime)
        count += 1
    log.info("Marked %d files as processed in '%s'", count, library_name)
    return count


def _to_seconds(interval: int, unit: str) -> int:
    multipliers = {"seconds": 1, "minutes": 60, "hours": 3600, "days": 86400}
    return interval * multipliers.get(unit, 60)


class PeriodicScanner:
    def __init__(self) -> None:
        self._tasks: list[asyncio.Task] = []

    async def start(self, enqueue_fn) -> None:
        await self.stop()
        libraries = await store.get_libraries()
        for name, lib in libraries.items():
            if lib.scan_interval <= 0:
                continue
            interval_secs = _to_seconds(lib.scan_interval, lib.scan_unit)
            task = asyncio.create_task(self._run_loop(name, interval_secs, enqueue_fn))
            self._tasks.append(task)
            log.info("Periodic scan for '%s' every %d seconds", name, interval_secs)

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    async def restart(self, enqueue_fn) -> None:
        await self.stop()
        await self.start(enqueue_fn)

    async def _run_loop(
        self, library_name: str, interval_secs: int, enqueue_fn
    ) -> None:
        try:
            while True:
                await asyncio.sleep(interval_secs)
                lib = await store.get_library(library_name)
                if not lib:
                    log.warning(
                        "Periodic scan: library '%s' no longer exists", library_name
                    )
                    return
                log.info("Periodic scan starting for '%s'", library_name)
                await scan_library(library_name, lib, enqueue_fn)
        except asyncio.CancelledError:
            pass


periodic_scanner = PeriodicScanner()
