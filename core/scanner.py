from __future__ import annotations

import asyncio
from pathlib import Path

from core.logger import log
from core.ffprobe import is_video_file, probe_file
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
) -> int:
    files = _collect_video_files(library)
    preset = await store.get_preset(library.preset)
    if not preset:
        log.warning("Scan aborted for '%s': preset '%s' not found", library_name, library.preset)
        return 0

    count = 0
    for file in files:
        file_str = str(file)

        if await db.has_completed_job(file_str):
            continue

        try:
            size = file.stat().st_size
        except OSError:
            continue

        result = await enqueue_fn(
            file_str,
            preset.ffmpeg_args,
            output_container=preset.output_container or "",
        )
        if result is not None:
            count += 1

    log.info("Scan of '%s': queued %d files", library_name, count)
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

    async def _run_loop(self, library_name: str, interval_secs: int, enqueue_fn) -> None:
        try:
            while True:
                await asyncio.sleep(interval_secs)
                lib = await store.get_library(library_name)
                if not lib:
                    log.warning("Periodic scan: library '%s' no longer exists", library_name)
                    return
                log.info("Periodic scan starting for '%s'", library_name)
                await scan_library(library_name, lib, enqueue_fn)
        except asyncio.CancelledError:
            pass


periodic_scanner = PeriodicScanner()
