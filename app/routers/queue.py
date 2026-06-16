from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from core.queue_manager import queue_manager, job_to_dict

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
