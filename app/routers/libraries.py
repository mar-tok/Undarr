from fastapi import APIRouter, HTTPException

from core.logger import log
from app.models.requests import LibraryCreate, LibraryUpdate
from app.models.responses import LibraryOut
from core.yaml_store import store, Library
from core.scanner import scan_library, periodic_scanner
from core.queue_manager import queue_manager
from core.watcher import watcher

router = APIRouter(prefix="/api/libraries", tags=["libraries"])


@router.get("", response_model=list[LibraryOut])
async def list_libraries():
    libs = await store.get_libraries()
    return [LibraryOut(name=n, paths=l.paths, preset=l.preset, watch=l.watch,
                       scan_interval=l.scan_interval, scan_unit=l.scan_unit)
            for n, l in libs.items()]


@router.post("", response_model=LibraryOut, status_code=201)
async def create_library(body: LibraryCreate):
    if await store.get_library(body.name):
        raise HTTPException(409, "Library already exists")
    if not await store.get_preset(body.preset):
        raise HTTPException(400, f"Preset '{body.preset}' not found")
    lib = Library(paths=body.paths, preset=body.preset, watch=body.watch,
                  scan_interval=body.scan_interval, scan_unit=body.scan_unit)
    await store.create_library(body.name, lib)
    log.info("Library created: '%s'", body.name)
    await watcher.restart(queue_manager.enqueue)
    await periodic_scanner.restart(queue_manager.enqueue)
    return LibraryOut(name=body.name, paths=lib.paths, preset=lib.preset, watch=lib.watch,
                      scan_interval=lib.scan_interval, scan_unit=lib.scan_unit)

@router.put("/{name}", response_model=LibraryOut)
async def update_library(name: str, body: LibraryUpdate):
    if not await store.get_library(name):
        raise HTTPException(404, "Library not found")
    if not await store.get_preset(body.preset):
        raise HTTPException(400, f"Preset '{body.preset}' not found")

    lib = Library(paths=body.paths, preset=body.preset, watch=body.watch,
                  scan_interval=body.scan_interval, scan_unit=body.scan_unit)
    new_name = body.name if body.name and body.name != name else name
    if new_name != name:
        if await store.get_library(new_name):
            raise HTTPException(409, "Library with that name already exists")
    await store.update_library(new_name, lib)
    if new_name != name:
        await store.delete_library(name)
        log.info("Library renamed: '%s' -> '%s'", name, new_name)
    else:
        log.info("Library updated: '%s'",  name)
    await watcher.restart(queue_manager.enqueue)
    await periodic_scanner.restart(queue_manager.enqueue)
    return LibraryOut(name=new_name, paths=lib.paths, preset=lib.preset, watch=lib.watch,
                      scan_interval=lib.scan_interval, scan_unit=lib.scan_unit)


@router.delete("/{name}", status_code=204)
async def delete_library(name: str):
    if not await store.delete_library(name):
        raise HTTPException(404, "Library not found")
    log.info("Library deleted: '%s'", name)
    await watcher.restart(queue_manager.enqueue)
    await periodic_scanner.restart(queue_manager.enqueue)

@router.post("/{name}/scan")
async def scan(name: str):
    lib = await store.get_library(name)
    if not lib:
        raise HTTPException(404, "Library not found")
    count = await scan_library(name, lib, queue_manager.enqueue)
    return {"queued": count}
