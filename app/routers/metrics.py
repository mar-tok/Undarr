from fastapi import APIRouter
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from core import db
from core.metrics import (
    registry,
    queue_jobs,
    device_active_jobs,
    queue_paused,
    jobs_by_result,
    space_saved_bytes,
    libraries,
)
from core.queue_manager import queue_manager
from core.yaml_store import store

router = APIRouter(prefix="/api", tags=["metrics"])

HISTORY_STATUSES = ("completed", "failed", "skipped", "skipped (rule)", "cancelled")


@router.get("/metrics")
async def get_metrics():
    queue_jobs.labels(status="pending").set(len(queue_manager.pending_jobs))
    queue_jobs.labels(status="blocked").set(len(queue_manager.blocked_jobs))
    queue_jobs.labels(status="active").set(len(queue_manager.active_jobs))
    for device, count in queue_manager.device_active_counts.items():
        device_active_jobs.labels(device=device).set(count)
    queue_paused.set(1 if queue_manager.paused else 0)
    libraries.set(len(store.config.libraries))

    counts = await db.get_history_status_counts()
    for status in HISTORY_STATUSES:
        jobs_by_result.labels(result=status).set(counts.get(status, 0))
    totals = await db.get_stats_totals()
    space_saved_bytes.set(totals["space_saved_bytes"])

    return Response(content=generate_latest(registry), media_type=CONTENT_TYPE_LATEST)
