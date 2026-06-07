from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.staticfiles import StaticFiles

from core.logger import log
from core import db
from core.queue_manager import queue_manager
from core.yaml_store import store
from core.watcher import watcher
from core.scanner import periodic_scanner
from app.routers import queue, presets, libraries


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting Undarr")
    await store.load()
    await db.init_db()
    await queue_manager.start()
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
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")