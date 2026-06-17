from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from core.queue_manager import queue_manager, job_to_dict
from core import db

router = APIRouter(tags=["queue"])


@router.get("/api/queue")
async def get_queue():
    jobs = [job_to_dict(j) for j in queue_manager.active_jobs]
    for job in queue_manager.pending_jobs:
        jobs.append(job_to_dict(job))
    for job in queue_manager.blocked_jobs:
        jobs.append(job_to_dict(job))
    return jobs


@router.get("/api/queue/events")
async def queue_events():
    sub = queue_manager.subscribe()

    async def stream():
        init_data = {
            "active": [job_to_dict(j) for j in queue_manager.active_jobs],
            "pending": [job_to_dict(j) for j in queue_manager.pending_jobs],
            "blocked": [job_to_dict(j) for j in queue_manager.blocked_jobs],
            "paused": queue_manager.paused,
        }
        yield f"event: init\ndata: {json.dumps(init_data)}\n\n"
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(sub.get(), timeout=30.0)
                    yield msg
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            queue_manager.unsubscribe(sub)

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/api/queue/pause")
async def pause_queue(body: dict):
    if body.get("paused"):
        await queue_manager.pause()
    else:
        await queue_manager.resume()
    return {"paused": queue_manager.paused}


@router.post("/api/queue/retry")
async def retry_jobs(body: dict):
    ids = body.get("ids", [])
    retried = 0
    to_dismiss = []
    for job_id in ids:
        entry = await db.get_history_entry(job_id)
        if not entry or entry["status"] != "failed":
            continue
        if not Path(entry["file_path"]).exists():
            continue
        job = await queue_manager.enqueue(entry["file_path"], entry["library_name"])
        if job is None:
            continue
        to_dismiss.append(job_id)
        retried += 1
    if to_dismiss:
        await db.dismiss_history_entries(to_dismiss)
    return {"retried": retried}


@router.post("/api/history/dismiss")
async def dismiss_history(body: dict):
    ids = body.get("ids", [])
    dismissed = await db.dismiss_history_entries(ids)
    return {"dismissed": dismissed}
