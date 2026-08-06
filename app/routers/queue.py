from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from core.queue_manager import queue_manager, job_to_dict
from core.yaml_store import store
from core import db
from app.models.requests import (
    CancelBatchRequest,
    DismissRequest,
    PauseRequest,
    RequeueRequest,
    RetryRequest,
    SkipRequest,
)
from app.models.responses import HistoryOut, SearchResultOut

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
            "paused_libraries": list(queue_manager.paused_libraries),
            "schedule_active": queue_manager.schedule_active,
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
async def pause_queue(body: PauseRequest):
    if body.paused:
        await queue_manager.pause()
    else:
        await queue_manager.resume()
    return {"paused": queue_manager.paused}


@router.delete("/api/queue/{job_id}", status_code=204)
async def cancel_job(job_id: str):
    if not await queue_manager.cancel(job_id):
        raise HTTPException(404, "Job not found")


@router.post("/api/queue/skip")
async def skip_jobs(body: SkipRequest):
    skipped = 0
    for job_id in body.ids:
        if await queue_manager.skip(job_id):
            skipped += 1
    return {"skipped": skipped}


@router.post("/api/queue/cancel")
async def cancel_jobs(body: CancelBatchRequest):
    cancelled = 0
    for job_id in body.ids:
        if await queue_manager.cancel(job_id):
            cancelled += 1
    return {"cancelled": cancelled}


@router.post("/api/queue/retry")
async def retry_jobs(body: RetryRequest):
    retried = 0
    skipped = 0
    to_dismiss = []
    for job_id in body.ids:
        entry = await db.get_history_entry(job_id)
        if not entry or entry["status"] != "failed":
            skipped += 1
            continue
        if not Path(entry["file_path"]).exists():
            skipped += 1
            continue
        job = await queue_manager.enqueue(
            entry["file_path"], entry["library_name"], is_retry=True
        )
        if job is None:
            skipped += 1
            continue
        to_dismiss.append(job_id)
        retried += 1
    if to_dismiss:
        await db.dismiss_history_entries(to_dismiss)
    return {"retried": retried, "skipped": skipped}


@router.post("/api/queue/requeue")
async def requeue_jobs(body: RequeueRequest):
    requeued = 0
    skipped = 0
    for job_id in body.ids:
        entry = await db.get_history_entry(job_id)
        if not entry:
            skipped += 1
            continue
        file_path = entry["file_path"]
        library_name = entry["library_name"]
        if not Path(file_path).exists():
            skipped += 1
            continue
        library = await store.get_library(library_name)
        if not library:
            skipped += 1
            continue
        await db.remove_processed(file_path, library_name)
        job = await queue_manager.enqueue(file_path, library_name)
        if job is None:
            skipped += 1
            continue
        requeued += 1
    return {"requeued": requeued, "skipped": skipped}


@router.post("/api/history/dismiss")
async def dismiss_history(body: DismissRequest):
    dismissed = await db.dismiss_history_entries(body.ids)
    return {"dismissed": dismissed}


@router.get("/api/history", response_model=list[HistoryOut])
async def get_history(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None),
    search: str | None = Query(None),
    sort_by: str = Query("finished_at"),
    sort_dir: str = Query("desc"),
    exclude_dismissed: bool = Query(False),
):
    rows = await db.get_history(
        limit=limit,
        offset=offset,
        status=status,
        search=search,
        sort_by=sort_by,
        sort_dir=sort_dir,
        exclude_dismissed=exclude_dismissed,
    )
    return [HistoryOut(**r) for r in rows]


@router.get("/api/history/{job_id}/log")
async def get_job_log(job_id: str):
    log_text = await db.get_job_log(job_id)
    if log_text is None:
        raise HTTPException(404, "Job not found")
    return {"log": log_text}


@router.delete("/api/history", status_code=204)
async def clear_history(clear_processed: bool = False):
    await db.clear_history(clear_processed=clear_processed)


@router.get("/api/search")
async def search_files(
    q: str = Query(""),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sort_by: str = Query("finished_at"),
    sort_dir: str = Query("desc"),
    status: str | None = Query(None),
):
    if len(q) < 2:
        return {"results": [], "total": 0}

    queue_results = []
    for item in queue_manager.search_jobs(q):
        if status and item["status"] != status:
            continue
        queue_results.append(
            SearchResultOut(
                id=item["id"],
                file_path=item["file_path"],
                library_name=item["library_name"],
                status=item["status"],
                old_size_bytes=item["old_size_bytes"],
                new_size_bytes=item.get("new_size_bytes"),
                date=item.get("started_at"),
                source="queue",
            )
        )

    history_rows, history_total = await db.search_files(
        q,
        limit,
        offset,
        sort_by=sort_by,
        sort_dir=sort_dir,
        status=status,
    )
    history_results = []
    for row in history_rows:
        history_results.append(
            SearchResultOut(
                id=row["id"],
                file_path=row["file_path"],
                library_name=row["library_name"],
                status=row["status"],
                old_size_bytes=row["old_size_bytes"],
                new_size_bytes=row.get("new_size_bytes"),
                date=row.get("finished_at"),
                source="history",
            )
        )

    return {
        "results": [r.model_dump() for r in queue_results + history_results],
        "total": len(queue_results) + history_total,
    }
