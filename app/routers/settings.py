from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models.requests import SettingsUpdate, DeviceUpdate
from core.logger import log
from core.yaml_store import store
from core.queue_manager import queue_manager
from core.devices import detect_devices

router = APIRouter(prefix="/api", tags=["settings"])


@router.get("/settings")
async def get_settings():
    s = await store.get_settings()
    return {"cache_dir": s.cache_dir}


@router.patch("/settings")
async def update_settings(body: SettingsUpdate):
    s = await store.get_settings()
    if body.cache_dir is not None:
        s = await store.set_cache_dir(body.cache_dir)
        log.info("Cache dir set to %s", s.cache_dir)
    return {"cache_dir": s.cache_dir}


@router.get("/devices")
async def get_devices():
    devices = await detect_devices()
    settings = await store.get_settings()
    result = []
    for dev in devices:
        cfg = settings.devices.get(dev.id)
        result.append({
            "id": dev.id,
            "name": dev.name,
            "type": dev.type,
            "encoders": dev.encoders,
            "max_jobs": cfg.max_jobs if cfg else 1,
        })
    return result


@router.patch("/devices/{device_id}")
async def update_device(device_id: str, body: DeviceUpdate):
    devices = await detect_devices()
    if not any(d.id == device_id for d in devices):
        raise HTTPException(404, "Device not found")
    if body.max_jobs < 0:
        raise HTTPException(400, "max_jobs must be 0 or greater")
    cfg = await store.update_device_config(device_id, body.max_jobs)
    await queue_manager.update_device_limit(device_id, body.max_jobs)
    return {"id": device_id, "max_jobs": cfg.max_jobs}
