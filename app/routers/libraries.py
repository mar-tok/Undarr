import asyncio
from pathlib import PurePosixPath

from fastapi import APIRouter, HTTPException, Query

from core.logger import log
from app.models.requests import (
    LibraryCreate,
    LibraryUpdate,
    PauseRequest,
    PreviewRequest,
)
from app.models.responses import LibraryOut, PreviewOut, SkipRuleOut, SkipConditionOut
from core.yaml_store import store, Library, SkipRule, SkipCondition
from core.scanner import (
    scan_library,
    preview_library,
    periodic_scanner,
    mark_library_processed,
)
from core.queue_manager import queue_manager
from core.watcher import watcher
from core import db

router = APIRouter(prefix="/api/libraries", tags=["libraries"])

_scanning: set[str] = set()
_preview_abort: asyncio.Event | None = None
_preview_lock = asyncio.Lock()
_mark_tasks: set[asyncio.Task] = set()


def _paths_overlap(a: str, b: str) -> bool:
    pa = PurePosixPath(a)
    pb = PurePosixPath(b)
    try:
        pa.relative_to(pb)
        return True
    except ValueError:
        pass
    try:
        pb.relative_to(pa)
        return True
    except ValueError:
        return False


async def _check_path_overlaps(
    paths: list[str], exclude_library: str | None = None
) -> str | None:
    libraries = await store.get_libraries()
    for lib_name, lib in libraries.items():
        if lib_name == exclude_library:
            continue
        for new_path in paths:
            for existing_path in lib.paths:
                if _paths_overlap(new_path, existing_path):
                    return f"Path {new_path} overlaps with library '{lib_name}' ({existing_path})"
    return None


def _to_skip_rules(rules_in: list) -> list[SkipRule]:
    return [
        SkipRule(
            conditions=[
                SkipCondition(field=c.field, operator=c.operator, value=c.value)
                for c in r.conditions
            ]
        )
        for r in rules_in
    ]


def _skip_rules_out(lib: Library) -> list[SkipRuleOut]:
    return [
        SkipRuleOut(
            conditions=[
                SkipConditionOut(field=c.field, operator=c.operator, value=c.value)
                for c in r.conditions
            ]
        )
        for r in lib.skip_rules
    ]


@router.get("", response_model=list[LibraryOut])
async def list_libraries():
    libs = await store.get_libraries()
    return [
        LibraryOut(
            name=n,
            paths=l.paths,
            preset=l.preset,
            watch=l.watch,
            skip_rules=_skip_rules_out(l),
            path_patterns=l.path_patterns,
            scan_interval=l.scan_interval,
            scan_unit=l.scan_unit,
            new_file_delay=l.new_file_delay,
            new_file_delay_unit=l.new_file_delay_unit,
            paused=l.paused,
        )
        for n, l in libs.items()
    ]


@router.post("", response_model=LibraryOut, status_code=201)
async def create_library(body: LibraryCreate):
    if await store.get_library(body.name):
        raise HTTPException(409, "Library already exists")
    if body.preset and not await store.get_preset(body.preset):
        raise HTTPException(400, f"Preset '{body.preset}' not found")
    overlap = await _check_path_overlaps(body.paths)
    if overlap:
        raise HTTPException(409, overlap)
    lib = Library(
        paths=body.paths,
        preset=body.preset,
        watch=body.watch,
        skip_rules=_to_skip_rules(body.skip_rules),
        path_patterns=body.path_patterns,
        scan_interval=body.scan_interval,
        scan_unit=body.scan_unit,
        new_file_delay=body.new_file_delay,
        new_file_delay_unit=body.new_file_delay_unit,
    )
    await store.create_library(body.name, lib)
    log.info("Library created: '%s'", body.name)
    if body.mark_existing_processed:
        lib.mark_processed_pending = True
        await store.update_library(body.name, lib)

        async def _bg_mark(name: str, lib: Library):
            try:
                await mark_library_processed(name, lib)
            except Exception as e:
                log.error("Mark as processed failed for '%s': %s", name, e)
                return
            current = await store.get_library(name)
            if not current or not current.mark_processed_pending:
                return
            current.mark_processed_pending = False
            await store.update_library(name, current)

        task = asyncio.create_task(_bg_mark(body.name, lib))
        _mark_tasks.add(task)
        task.add_done_callback(_mark_tasks.discard)
    await watcher.restart(queue_manager.enqueue)
    await periodic_scanner.restart(queue_manager.enqueue)
    return LibraryOut(
        name=body.name,
        paths=lib.paths,
        preset=lib.preset,
        watch=lib.watch,
        skip_rules=_skip_rules_out(lib),
        path_patterns=lib.path_patterns,
        scan_interval=lib.scan_interval,
        scan_unit=lib.scan_unit,
        new_file_delay=lib.new_file_delay,
        new_file_delay_unit=lib.new_file_delay_unit,
        paused=lib.paused,
    )


@router.put("/{name}", response_model=LibraryOut)
async def update_library(name: str, body: LibraryUpdate):
    old_lib = await store.get_library(name)
    if not old_lib:
        raise HTTPException(404, "Library not found")
    if body.preset and not await store.get_preset(body.preset):
        raise HTTPException(400, f"Preset '{body.preset}' not found")
    overlap = await _check_path_overlaps(body.paths, exclude_library=name)
    if overlap:
        raise HTTPException(409, overlap)

    lib = Library(
        paths=body.paths,
        preset=body.preset,
        watch=body.watch,
        skip_rules=_to_skip_rules(body.skip_rules),
        path_patterns=body.path_patterns,
        scan_interval=body.scan_interval,
        scan_unit=body.scan_unit,
        new_file_delay=body.new_file_delay,
        new_file_delay_unit=body.new_file_delay_unit,
        paused=old_lib.paused,
        mark_processed_pending=old_lib.mark_processed_pending,
    )
    new_name = body.name if body.name and body.name != name else name
    if new_name != name:
        if await store.get_library(new_name):
            raise HTTPException(409, "Library with that name already exists")
    await store.update_library(new_name, lib)
    if new_name != name:
        await store.delete_library(name)
        await queue_manager.rename_paused_library(name, new_name)
        log.info("Library renamed: '%s' -> '%s'", name, new_name)
    else:
        log.info("Library updated: '%s'", name)
    await watcher.restart(queue_manager.enqueue)
    await periodic_scanner.restart(queue_manager.enqueue)
    await queue_manager.re_evaluate_blocked()
    return LibraryOut(
        name=new_name,
        paths=lib.paths,
        preset=lib.preset,
        watch=lib.watch,
        skip_rules=_skip_rules_out(lib),
        path_patterns=lib.path_patterns,
        scan_interval=lib.scan_interval,
        scan_unit=lib.scan_unit,
        new_file_delay=lib.new_file_delay,
        new_file_delay_unit=lib.new_file_delay_unit,
        paused=lib.paused,
    )


@router.delete("/{name}", status_code=204)
async def delete_library(name: str):
    if not await store.delete_library(name):
        raise HTTPException(404, "Library not found")
    log.info("Library deleted: '%s'", name)
    await queue_manager.clear_paused_library(name)
    await watcher.restart(queue_manager.enqueue)
    await periodic_scanner.restart(queue_manager.enqueue)


@router.post("/{name}/pause")
async def pause_library(name: str, body: PauseRequest):
    lib = await store.get_library(name)
    if not lib:
        raise HTTPException(404, "Library not found")
    await store.set_library_paused(name, body.paused)
    if body.paused:
        await queue_manager.pause_library(name)
    else:
        await queue_manager.resume_library(name)
    return {"paused": body.paused}


async def _run_preview(library_name: str, lib: Library):
    global _preview_abort
    async with _preview_lock:
        if _preview_abort is not None:
            raise HTTPException(409, "A preview is already running")
        _preview_abort = asyncio.Event()
    abort_event = _preview_abort

    last_reported = 0
    step = 1

    async def progress_fn(scanned: int, total: int) -> None:
        nonlocal last_reported, step
        if step == 1 and total > 0:
            step = max(1, total // 100)
        if scanned - last_reported < step and scanned < total:
            return
        last_reported = scanned
        await queue_manager._broadcast(
            "preview_progress",
            {
                "library": library_name,
                "scanned": scanned,
                "total": total,
            },
        )

    try:
        return await preview_library(
            library_name, lib, progress_fn=progress_fn, abort_event=abort_event
        )
    finally:
        _preview_abort = None


@router.post("/preview/cancel", status_code=204)
async def cancel_preview():
    if _preview_abort:
        _preview_abort.set()


@router.post("/preview", response_model=PreviewOut)
async def preview_from_config(body: PreviewRequest):
    lib = Library(
        paths=body.paths,
        preset="",
        skip_rules=_to_skip_rules(body.skip_rules),
        path_patterns=body.path_patterns,
        new_file_delay=body.new_file_delay,
        new_file_delay_unit=body.new_file_delay_unit,
    )
    return await _run_preview(body.name, lib)


@router.post("/{name}/preview", response_model=PreviewOut)
async def preview(name: str):
    lib = await store.get_library(name)
    if not lib:
        raise HTTPException(404, "Library not found")
    return await _run_preview(name, lib)


@router.post("/{name}/scan")
async def scan(name: str, force: bool = Query(False)):
    lib = await store.get_library(name)
    if not lib:
        raise HTTPException(404, "Library not found")
    if name in _scanning:
        raise HTTPException(409, "This library is already being scanned")
    if lib.mark_processed_pending:
        raise HTTPException(409, "Files are still being marked as processed")
    _scanning.add(name)
    try:
        if force:
            cleared = await db.clear_processed(name)
            log.info(
                "Force rescan: cleared %d processed records for '%s'", cleared, name
            )
        else:
            log.info("Scan triggered for '%s'", name)

        async def progress_fn(scanned: int, total: int, queued: int) -> None:
            await queue_manager._broadcast(
                "scan_progress",
                {
                    "library": name,
                    "scanned": scanned,
                    "total": total,
                    "queued": queued,
                },
            )

        count, skipped = await scan_library(
            name, lib, queue_manager.enqueue, progress_fn=progress_fn
        )
        await queue_manager._broadcast(
            "scan_complete", {"library": name, "queued": count}
        )
        return {"queued": count, "skipped": skipped}
    finally:
        _scanning.discard(name)


@router.post("/{name}/mark-processed")
async def mark_processed(name: str):
    lib = await store.get_library(name)
    if not lib:
        raise HTTPException(404, "Library not found")
    if lib.mark_processed_pending:
        raise HTTPException(409, "Files are still being marked as processed")
    lib.mark_processed_pending = True
    await store.update_library(name, lib)
    count = await mark_library_processed(name, lib)
    current = await store.get_library(name)
    if current and current.mark_processed_pending:
        current.mark_processed_pending = False
        await store.update_library(name, current)
    log.info("Marked all files as processed in '%s'", name)
    return {"marked": count}
