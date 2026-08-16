from fastapi import APIRouter

from app.models.responses import (
    StatsOut,
    StatsTotals,
    StatsDaily,
    StatsLibrary,
    StatsTopSaving,
    StatsDevice,
)
from core import db

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("", response_model=StatsOut)
async def get_stats():
    totals = await db.get_stats_totals()
    daily = await db.get_stats_daily()
    by_lib = await db.get_stats_by_library()
    top = await db.get_stats_top_savings()
    by_dev = await db.get_stats_by_device()
    composition = await db.get_stats_composition()
    file_counts = await db.get_stats_file_counts()
    processed_counts = await db.get_stats_processed_counts()

    devices = []
    for d in by_dev:
        avg = d["processing_seconds"] / d["completed"] if d["completed"] else 0.0
        devices.append(StatsDevice(**d, avg_duration_seconds=avg))

    return StatsOut(
        totals=StatsTotals(**totals),
        daily=[StatsDaily(**d) for d in daily],
        by_library=[StatsLibrary(**l) for l in by_lib],
        top_savings=[StatsTopSaving(**t) for t in top],
        by_device=devices,
        composition=composition,
        file_counts=file_counts,
        processed_counts=processed_counts,
    )
