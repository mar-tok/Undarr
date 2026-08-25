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


def _collect_video_files(library: Library) -> tuple[list[Path], list[str]]:
    files: list[Path] = []
    missing: list[str] = []
    for dir_path in library.paths:
        p = Path(dir_path)
        if not p.exists():
            log.warning("Library path does not exist: %s", dir_path)
            missing.append(dir_path)
            continue
        for file in p.rglob("*"):
            if file.is_file() and is_video_file(str(file)):
                files.append(file)
    return files, missing


async def _probe_and_upsert(file_path: str, library_name: str, st) -> dict | None:
    container = Path(file_path).suffix.lstrip(".").lower()
    probe_data = await probe_file(file_path)
    if probe_data:
        info = extract_media_info(probe_data)
        await db.upsert_library_file(
            file_path,
            library_name,
            info.get("video_codec", ""),
            info.get("resolution_height", 0),
            st.st_size,
            st.st_mtime,
            bitrate_kbps=info.get("bitrate_kbps", 0),
            container=container,
            audio_codec=info.get("audio_codec", ""),
            audio_channels=info.get("audio_channels", 0),
            duration=info.get("duration_seconds", 0),
            hdr_type=info.get("hdr_type", ""),
        )
    else:
        await db.upsert_library_file(
            file_path,
            library_name,
            "",
            0,
            st.st_size,
            st.st_mtime,
            container=container,
        )
    return probe_data


async def scan_library(
    library_name: str,
    library: Library,
    enqueue_fn,
    *,
    progress_fn=None,
    on_unavailable=None,
) -> tuple[int, int]:
    if library.mark_processed_pending:
        log.info(
            "Scan skipped for '%s': files are still being marked as processed",
            library_name,
        )
        return 0, 0

    all_files, missing_paths = await asyncio.to_thread(_collect_video_files, library)
    if on_unavailable and library.paths:
        if len(missing_paths) == len(library.paths):
            await on_unavailable(
                library_name,
                True,
                f"All paths missing: {', '.join(missing_paths)}",
                missing_paths,
            )
        else:
            await on_unavailable(library_name, False, "", missing_paths)
    total = len(all_files)
    count = 0
    skipped = 0
    scanned = 0

    cached_mtimes = await db.get_library_files_mtimes(library_name)

    for file in all_files:
        scanned += 1
        try:
            st = file.stat()
        except OSError:
            if progress_fn:
                await progress_fn(scanned, total, count)
            continue

        file_str = str(file)
        cached_mtime = cached_mtimes.get(file_str)
        probe_data = None
        if cached_mtime is None or abs(cached_mtime - st.st_mtime) >= 0.001:
            probe_data = await _probe_and_upsert(file_str, library_name, st)

        if await db.is_processed(file_str, library_name, st.st_mtime):
            if progress_fn:
                await progress_fn(scanned, total, count)
            continue
        # If the file was renamed, its processed record is still under the old path
        old_path = await db.find_rename_candidate(file_str, library_name, st.st_size)
        if old_path:
            await db.rename_file(old_path, file_str, library_name, st.st_mtime)
            log.debug("Renamed tracked file: %s -> %s", old_path, file_str)
            if progress_fn:
                await progress_fn(scanned, total, count)
            continue
        if library.new_file_delay:
            newest = max(st.st_mtime, st.st_ctime)
            age = time.time() - newest
            if age < library.new_file_delay_seconds:
                if progress_fn:
                    await progress_fn(scanned, total, count)
                continue
        result = await scan_single_file(
            file_str, library_name, library, enqueue_fn, probe_data=probe_data
        )
        if result == "queued":
            count += 1
        elif result == "skipped":
            skipped += 1
        if progress_fn:
            await progress_fn(scanned, total, count)

    if not missing_paths:
        await db.cleanup_library_files(library_name, {str(f) for f in all_files})
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
    *,
    probe_data: dict | None = None,
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
    if probe_data is None:
        probe_data = await probe_file(file_path)
    if probe_data:
        media_info = extract_media_info(probe_data)
        try:
            st = Path(file_path).stat()
            container = Path(file_path).suffix.lstrip(".").lower()
            await db.upsert_library_file(
                file_path,
                library_name,
                media_info.get("video_codec", ""),
                media_info.get("resolution_height", 0),
                st.st_size,
                st.st_mtime,
                bitrate_kbps=media_info.get("bitrate_kbps", 0),
                container=container,
                audio_codec=media_info.get("audio_codec", ""),
                audio_channels=media_info.get("audio_channels", 0),
                duration=media_info.get("duration_seconds", 0),
                hdr_type=media_info.get("hdr_type", ""),
            )
        except OSError:
            pass
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


# Must mirror scan_single_file's checks and order, or previews diverge from real scans
async def preview_library(
    library_name: str,
    library: Library,
    *,
    progress_fn=None,
    abort_event: asyncio.Event | None = None,
) -> dict:
    all_files, _ = await asyncio.to_thread(_collect_video_files, library)
    total = len(all_files)
    scanned = 0

    already_processed = 0
    too_new = 0
    queue_list: list[dict] = []
    skipped_list: list[dict] = []

    for file in all_files:
        if abort_event and abort_event.is_set():
            break
        scanned += 1
        file_str = str(file)
        try:
            st = file.stat()
        except OSError:
            if progress_fn:
                await progress_fn(scanned, total)
            continue

        file_size = st.st_size

        if await db.is_processed(file_str, library_name, st.st_mtime):
            already_processed += 1
            if progress_fn:
                await progress_fn(scanned, total)
            continue

        if library.new_file_delay:
            newest = max(st.st_mtime, st.st_ctime)
            age = time.time() - newest
            if age < library.new_file_delay_seconds:
                too_new += 1
                rel = _relative_to_library(file_str, library.paths) or file_str
                skipped_list.append(
                    {
                        "path": rel,
                        "size_bytes": file_size,
                        "reason": "Too new (file delay not elapsed)",
                    }
                )
                if progress_fn:
                    await progress_fn(scanned, total)
                continue

        if library.path_patterns:
            rel_path = _relative_to_library(file_str, library.paths)
            if rel_path:
                matched = match_path_pattern(rel_path, library.path_patterns)
                if matched:
                    skipped_list.append(
                        {
                            "path": rel_path,
                            "size_bytes": file_size,
                            "reason": f"Path pattern: {matched}",
                        }
                    )
                    if progress_fn:
                        await progress_fn(scanned, total)
                    continue

        probe = await probe_file(file_str)
        info = extract_media_info(probe) if probe else None

        if library.skip_rules and info:
            matched_rule = should_skip(info, library.skip_rules)
            if matched_rule:
                rel = _relative_to_library(file_str, library.paths) or file_str
                skipped_list.append(
                    {
                        "path": rel,
                        "size_bytes": file_size,
                        "reason": f"Skip rule: {format_rule(matched_rule)}",
                    }
                )
                if progress_fn:
                    await progress_fn(scanned, total)
                continue

        rel = _relative_to_library(file_str, library.paths) or file_str
        if info:
            w = info.get("resolution_width", 0)
            h = info.get("resolution_height", 0)
            queue_list.append(
                {
                    "path": rel,
                    "size_bytes": file_size,
                    "video_codec": info.get("video_codec", "unknown"),
                    "resolution": f"{w}x{h}" if w and h else "unknown",
                    "bitrate_kbps": info.get("bitrate_kbps", 0),
                }
            )
        else:
            queue_list.append(
                {
                    "path": rel,
                    "size_bytes": file_size,
                    "video_codec": "unknown",
                    "resolution": "unknown",
                    "bitrate_kbps": 0,
                }
            )
        if progress_fn:
            await progress_fn(scanned, total)

    return {
        "summary": {
            "total_files": total,
            "would_queue": len(queue_list),
            "would_queue_bytes": sum(f["size_bytes"] for f in queue_list),
            "already_processed": already_processed,
            "skipped": len(skipped_list),
            "too_new": too_new,
            "not_scanned": total - scanned,
        },
        "queue": queue_list,
        "skipped": skipped_list,
    }


async def mark_library_processed(
    library_name: str,
    library: Library,
) -> int:
    count = 0
    for file in (await asyncio.to_thread(_collect_video_files, library))[0]:
        try:
            st = file.stat()
        except OSError:
            continue
        file_str = str(file)
        await _probe_and_upsert(file_str, library_name, st)
        await db.mark_processed(file_str, library_name, st.st_mtime)
        count += 1
    log.info("Marked %d files as processed in '%s'", count, library_name)
    return count


def _to_seconds(interval: int, unit: str) -> int:
    multipliers = {"seconds": 1, "minutes": 60, "hours": 3600, "days": 86400}
    return interval * multipliers.get(unit, 60)


class PeriodicScanner:
    def __init__(self) -> None:
        self._tasks: list[asyncio.Task] = []
        self._on_unavailable = None

    async def start(self, enqueue_fn, *, on_unavailable=None) -> None:
        await self.stop()
        if on_unavailable is not None:
            self._on_unavailable = on_unavailable
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

    async def restart(self, enqueue_fn, *, on_unavailable=None) -> None:
        if on_unavailable is not None:
            self._on_unavailable = on_unavailable
        await self.stop()
        await self.start(enqueue_fn, on_unavailable=self._on_unavailable)

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
                await scan_library(
                    library_name, lib, enqueue_fn, on_unavailable=self._on_unavailable
                )
        except asyncio.CancelledError:
            pass


periodic_scanner = PeriodicScanner()
