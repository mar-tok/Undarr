from fastapi import APIRouter

from app.models.responses import (
    StatsOut,
    StatsTotals,
    StatsDaily,
    StatsLibrary,
    StatsTopSaving,
)
from core import db

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("", response_model=StatsOut)
async def get_stats():
    totals = await db.get_stats_totals()
    daily = await db.get_stats_daily()
    by_lib = await db.get_stats_by_library()
    top = await db.get_stats_top_savings()
    composition = await db.get_stats_composition()
    file_counts = await db.get_stats_file_counts()
    processed_counts = await db.get_stats_processed_counts()

    return StatsOut(
        totals=StatsTotals(**totals),
        daily=[StatsDaily(**d) for d in daily],
        by_library=[StatsLibrary(**l) for l in by_lib],
        top_savings=[StatsTopSaving(**t) for t in top],
        composition=composition,
        file_counts=file_counts,
        processed_counts=processed_counts,
    )
