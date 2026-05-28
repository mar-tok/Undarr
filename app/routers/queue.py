from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from core.queue_manager import queue_manager, job_to_dict

router = APIRouter(tags=["queue"])


@router.get("/api/queue")
async def get_queue():
    jobs = []
    for job in queue_manager.pending_jobs:
        jobs.append(job_to_dict(job))
    active = queue_manager.active_job
    if active:
        jobs.insert(0, job_to_dict(active))
    return jobs


@router.get("/api/queue/events")
async def queue_events():
    sub = queue_manager.subscribe()

    async def stream():
        init_data = {
            "active": [job_to_dict(queue_manager.active_job)] if queue_manager.active_job else [],
            "pending": [job_to_dict(j) for j in queue_manager.pending_jobs],
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
