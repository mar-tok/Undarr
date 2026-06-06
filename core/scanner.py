from __future__ import annotations

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
