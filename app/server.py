from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.staticfiles import StaticFiles

from core.logger import log
from core import db
from core.queue_manager import queue_manager
from core.yaml_store import store
from core.watcher import watcher
from core.scanner import periodic_scanner
from core.devices import detect_devices
from app.routers import queue, presets, libraries, settings, filesystem


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
    yield
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
