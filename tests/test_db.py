import aiosqlite

import core.db as db_mod
from core.db import (
    SCHEMA,
    PROCESSED_SCHEMA,
    insert_job_history,
    get_history,
    clear_history,
    mark_processed,
    is_processed,
    clear_processed,
    remove_processed,
)

import pytest


@pytest.fixture
async def db_setup():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await conn.executescript(SCHEMA)
    await conn.executescript(PROCESSED_SCHEMA)
    await conn.commit()
    old_db = db_mod._db
    db_mod._db = conn
    yield conn
    db_mod._db = old_db
    await conn.close()


async def _insert_sample(id: str = "job1", status: str = "completed", **overrides):
    defaults = dict(
        id=id,
        library_name="movies",
        file_path=f"/media/{id}.mkv",
        status=status,
        old_size_bytes=1000000,
        new_size_bytes=500000,
        started_at="2026-01-01T00:00:00",
        finished_at="2026-01-01T00:01:00",
        duration_seconds=60.0,
        ffmpeg_log="frame=100",
        error_message=None,
        preset_name="HEVC",
        device_name="CPU",
    )
    defaults.update(overrides)
    await insert_job_history(**defaults)


class TestClearHistory:
    async def test_clears_all(self, db_setup):
        await _insert_sample("j1")
        await _insert_sample("j2")
        count = await clear_history()
        assert count == 2
        assert await get_history() == []

    async def test_clear_processed_true(self, db_setup):
        await _insert_sample("j1")
        await mark_processed("/media/file.mkv", "movies", 1000.0)
        await clear_history(clear_processed=True)
        assert not await is_processed("/media/file.mkv", "movies", 1000.0)

    async def test_clear_processed_false(self, db_setup):
        await _insert_sample("j1")
        await mark_processed("/media/file.mkv", "movies", 1000.0)
        await clear_history(clear_processed=False)
        assert await is_processed("/media/file.mkv", "movies", 1000.0)


class TestMarkAndIsProcessed:
    async def test_mark_and_check(self, db_setup):
        await mark_processed("/media/m.mkv", "lib1", 1000.0)
        assert await is_processed("/media/m.mkv", "lib1", 1000.0) is True

    async def test_mtime_differs(self, db_setup):
        await mark_processed("/media/m.mkv", "lib1", 1000.0)
        assert await is_processed("/media/m.mkv", "lib1", 2000.0) is False

    async def test_mtime_within_tolerance(self, db_setup):
        await mark_processed("/media/m.mkv", "lib1", 1000.0)
        # 0.0005 difference is within the 0.001 tolerance
        assert await is_processed("/media/m.mkv", "lib1", 1000.0005) is True

    async def test_path_not_in_db(self, db_setup):
        assert await is_processed("/media/unknown.mkv", "lib1", 1000.0) is False


class TestClearProcessed:
    async def test_clears_by_library(self, db_setup):
        await mark_processed("/a.mkv", "lib1", 1.0)
        await mark_processed("/b.mkv", "lib2", 2.0)
        count = await clear_processed("lib1")
        assert count == 1
        assert not await is_processed("/a.mkv", "lib1", 1.0)
        assert await is_processed("/b.mkv", "lib2", 2.0)


class TestRemoveProcessed:
    async def test_removes_entry(self, db_setup):
        await mark_processed("/a.mkv", "lib1", 1.0)
        await remove_processed("/a.mkv", "lib1")
        assert not await is_processed("/a.mkv", "lib1", 1.0)
