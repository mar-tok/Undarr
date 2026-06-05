from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.staticfiles import StaticFiles

from core.logger import log
from core import db
from core.queue_manager import queue_manager
from core.yaml_store import store
from app.routers import queue, presets, libraries


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting Undarr")
    await store.load()
    await db.init_db()
    await queue_manager.start()
    yield
    await queue_manager.stop()
    await db.close_db()
    log.info("Undarr stopped")

app = FastAPI(title="Undarr", lifespan=lifespan)
app.include_router(queue.router)
app.include_router(presets.router)
app.include_router(libraries.router)
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")