from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.staticfiles import StaticFiles

from core.logger import log


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting Undarr")
    yield
    log.info("Undarr stopped")

app = FastAPI(title="Undarr", lifespan=lifespan)

app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")