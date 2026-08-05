from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone as tz
from importlib.metadata import version
from urllib.request import urlopen, Request

from fastapi import APIRouter, HTTPException

from app.models.requests import SettingsUpdate, DeviceUpdate
from app.models.responses import SettingsOut
from core.logger import log
from core.yaml_store import store, DAYS, VALID_PRIORITIES, VALID_QUEUE_ORDERS
from core.queue_manager import queue_manager
from core.devices import detect_devices

router = APIRouter(prefix="/api", tags=["settings"])

APP_VERSION = version("undarr")
GITHUB_REPO = "mar-tok/Undarr"
UPDATE_CHECK_INTERVAL = 6 * 3600

_latest_version: str | None = None
_last_check: float = 0


async def _check_latest_version() -> str | None:
    global _latest_version, _last_check
    now = time.monotonic()
    if _latest_version is not None and now - _last_check < UPDATE_CHECK_INTERVAL:
        return _latest_version
    try:

        def _fetch():
            url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
            req = Request(url, headers={"Accept": "application/vnd.github.v3+json"})
            with urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                return data.get("tag_name", "").lstrip("v")

        _latest_version = await asyncio.to_thread(_fetch)
        _last_check = now
    except (OSError, ValueError, KeyError) as e:
        log.debug("Update check failed: %s", e)
    return _latest_version


@router.get("/version")
async def get_version():
    latest = await _check_latest_version()
    result = {"version": APP_VERSION}
    if latest and latest != APP_VERSION:
        result["latest"] = latest
    return result


def _server_tz_info() -> tuple[str, int]:
    try:
        now = datetime.now(tz.utc).astimezone()
        offset_minutes = int(now.utcoffset().total_seconds() // 60)
        name = now.strftime("%Z") or time.tzname[0] or "UTC"
        return name, offset_minutes
    except Exception:
        return "UTC", 0


def _settings_response(s) -> SettingsOut:
    tz_name, tz_offset = _server_tz_info()
    return SettingsOut(
        cache_dir=s.cache_dir,
        schedule_enabled=s.schedule_enabled,
        schedule=s.schedule,
        process_priority=s.process_priority,
        max_size_ratio=s.max_size_ratio,
        queue_order=s.queue_order,
        server_timezone=tz_name,
        server_utc_offset=tz_offset,
    )


@router.get("/settings", response_model=SettingsOut)
async def get_settings():
    s = await store.get_settings()
    return _settings_response(s)


@router.patch("/settings", response_model=SettingsOut)
async def update_settings(body: SettingsUpdate):
    kwargs = {k: v for k, v in body.model_dump().items() if v is not None}

    if "cache_dir" in kwargs and not kwargs["cache_dir"].strip():
        raise HTTPException(400, "Cache directory cannot be empty")

    if "schedule" in kwargs:
        sched = kwargs["schedule"]
        if set(sched.keys()) != set(DAYS):
            raise HTTPException(
                400, f"Schedule must have exactly keys: {', '.join(DAYS)}"
            )
        for day, hours in sched.items():
            if not isinstance(hours, list) or len(hours) != 24:
                raise HTTPException(
                    400, f"Schedule '{day}' must be a list of 24 booleans"
                )

    if "process_priority" in kwargs:
        if kwargs["process_priority"] not in VALID_PRIORITIES:
            raise HTTPException(
                400,
                f"process_priority must be one of: {', '.join(VALID_PRIORITIES)}",
            )

    if "max_size_ratio" in kwargs:
        if not (0.0 < kwargs["max_size_ratio"] <= 1.0):
            raise HTTPException(400, "max_size_ratio must be between 0 and 100%")

    if "queue_order" in kwargs:
        if kwargs["queue_order"] not in VALID_QUEUE_ORDERS:
            raise HTTPException(
                400, f"queue_order must be one of: {', '.join(VALID_QUEUE_ORDERS)}"
            )

    schedule_changed = "schedule" in kwargs or "schedule_enabled" in kwargs
    order_changed = "queue_order" in kwargs
    s = await store.update_settings(**kwargs)
    if kwargs:
        log.info("Settings updated: %s", ", ".join(kwargs))

    if schedule_changed:
        await queue_manager.schedule_changed()
    if order_changed:
        await queue_manager.queue_order_changed()

    return _settings_response(s)


@router.get("/devices")
async def get_devices():
    devices = await detect_devices()
    settings = await store.get_settings()
    result = []
    for dev in devices:
        cfg = settings.devices.get(dev.id)
        result.append(
            {
                "id": dev.id,
                "name": dev.name,
                "type": dev.type,
                "encoders": dev.encoders,
                "max_jobs": cfg.max_jobs if cfg else 1,
            }
        )
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
