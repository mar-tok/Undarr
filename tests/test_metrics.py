from types import SimpleNamespace
from unittest.mock import patch

import aiosqlite
import pytest
from prometheus_client import CONTENT_TYPE_LATEST
from prometheus_client.parser import text_string_to_metric_families

from app.routers.metrics import get_metrics
from core import db as db_mod
from core.db import SCHEMA, insert_job_history
from core.queue_manager import Job, QueueManager


@pytest.fixture
async def db_setup():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await conn.executescript(SCHEMA)
    await conn.commit()
    old_db = db_mod._db
    db_mod._db = conn
    yield conn
    db_mod._db = old_db
    await conn.close()


@pytest.fixture
def qm():
    manager = QueueManager()
    manager._device_limits = {"cpu": 2, "nvenc": 1}
    manager._device_active = {"cpu": 1, "nvenc": 0}
    manager._pending.append(Job(id="p1", file_path="/m/a.mkv", library_name="movies"))
    manager._pending.append(Job(id="p2", file_path="/m/b.mkv", library_name="movies"))
    manager._blocked.append(Job(id="b1", file_path="/m/c.mkv", library_name="movies"))
    manager._active["a1"] = Job(id="a1", file_path="/m/d.mkv", library_name="movies")
    return manager


async def _insert(status, old=1000, new=None):
    await insert_job_history(
        id=f"{status}-{old}-{new}",
        library_name="movies",
        file_path="/m/x.mkv",
        status=status,
        old_size_bytes=old,
        new_size_bytes=new,
        started_at="",
        finished_at="",
        duration_seconds=1.0,
        ffmpeg_log="",
        error_message=None,
    )


async def _scrape(qm, libraries=None):
    fake_store = SimpleNamespace(config=SimpleNamespace(libraries=libraries or {}))
    with (
        patch("app.routers.metrics.queue_manager", qm),
        patch("app.routers.metrics.store", fake_store),
    ):
        response = await get_metrics()
    families = {}
    for family in text_string_to_metric_families(response.body.decode()):
        families[family.name] = {
            tuple(sorted(s.labels.items())): s.value for s in family.samples
        }
    return response, families


class TestMetricsEndpoint:
    async def test_content_type(self, db_setup, qm):
        response, _ = await _scrape(qm)
        assert response.headers["content-type"] == CONTENT_TYPE_LATEST

    async def test_queue_gauges(self, db_setup, qm):
        _, families = await _scrape(qm)
        jobs = families["undarr_queue_jobs"]
        assert jobs[(("status", "pending"),)] == 2
        assert jobs[(("status", "blocked"),)] == 1
        assert jobs[(("status", "active"),)] == 1
        devices = families["undarr_device_active_jobs"]
        assert devices[(("device", "cpu"),)] == 1
        assert devices[(("device", "nvenc"),)] == 0

    async def test_paused_flag(self, db_setup, qm):
        _, families = await _scrape(qm)
        assert families["undarr_queue_paused"][()] == 0
        qm._running.clear()
        _, families = await _scrape(qm)
        assert families["undarr_queue_paused"][()] == 1

    async def test_libraries_total(self, db_setup, qm):
        _, families = await _scrape(qm, {"movies": object(), "shows": object()})
        assert families["undarr_libraries"][()] == 2

    async def test_history_counts_fill_zeroes(self, db_setup, qm):
        await _insert("completed", 1000, 400)
        await _insert("completed", 2000, 1500)
        await _insert("failed")
        await _insert("skipped (rule)")
        _, families = await _scrape(qm)
        totals = families["undarr_jobs"]
        assert totals[(("result", "completed"),)] == 2
        assert totals[(("result", "failed"),)] == 1
        assert totals[(("result", "skipped (rule)"),)] == 1
        assert totals[(("result", "skipped"),)] == 0
        assert totals[(("result", "cancelled"),)] == 0
        assert families["undarr_space_saved_bytes"][()] == 1100

    async def test_empty_history(self, db_setup, qm):
        _, families = await _scrape(qm)
        assert all(v == 0 for v in families["undarr_jobs"].values())
        assert families["undarr_space_saved_bytes"][()] == 0
