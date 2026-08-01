import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.staticfiles import StaticFiles

from core.logger import log
from core import db
from core.queue_manager import queue_manager
from core.yaml_store import store
from core.watcher import watcher
from core.scanner import scan_library, periodic_scanner
from core.devices import detect_devices
from app.routers import queue, presets, libraries, settings, filesystem


async def _startup_scan() -> None:
    libs = await store.get_libraries()
    for name, lib in libs.items():
        if not lib.preset:
            continue

        async def progress_fn(
            scanned: int, total: int, queued: int, lib_name: str = name
        ) -> None:
            await queue_manager._broadcast(
                "scan_progress",
                {
                    "library": lib_name,
                    "scanned": scanned,
                    "total": total,
                    "queued": queued,
                },
            )

        try:
            if not await store.get_library(name):
                continue
            count, _ = await scan_library(
                name, lib, queue_manager.enqueue, progress_fn=progress_fn
            )
            await queue_manager._broadcast(
                "scan_complete", {"library": name, "queued": count}
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.error("Startup scan of '%s' failed: %s", name, e)
    await queue_manager._broadcast("scan_complete", {"library": None, "queued": 0})
    log.info("Startup scan complete")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting Undarr")
    await store.load()
    await db.init_db()
    devices = await detect_devices()
    cfg = await store.get_settings()
    limits = {}
    for d in devices:
        dev_cfg = cfg.devices.get(d.id)
        limits[d.id] = dev_cfg.max_jobs if dev_cfg else 1
    await queue_manager.start(limits)
    await watcher.start(queue_manager.enqueue)
    await periodic_scanner.start(queue_manager.enqueue)
    scan_task = asyncio.create_task(_startup_scan())
    yield
    scan_task.cancel()
    await asyncio.gather(scan_task, return_exceptions=True)
    await periodic_scanner.stop()
    await watcher.stop()
    await queue_manager.stop()
    await db.close_db()
    log.info("Undarr stopped")


app = FastAPI(title="Undarr", lifespan=lifespan)
app.include_router(queue.router)
app.include_router(presets.router)
app.include_router(libraries.router)
app.include_router(settings.router)
app.include_router(filesystem.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
