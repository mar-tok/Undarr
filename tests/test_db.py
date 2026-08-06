import aiosqlite

import core.db as db_mod
from core.db import (
    SCHEMA,
    PROCESSED_SCHEMA,
    insert_job_history,
    get_history,
    get_job_log,
    get_history_entry,
    dismiss_history_entries,
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


class TestInsertAndGetHistory:
    async def test_insert_and_retrieve(self, db_setup):
        await _insert_sample()
        rows = await get_history()
        assert len(rows) == 1
        assert rows[0]["id"] == "job1"
        assert rows[0]["status"] == "completed"

    async def test_filter_by_status(self, db_setup):
        await _insert_sample("j1", status="completed")
        await _insert_sample("j2", status="failed")
        rows = await get_history(status="failed")
        assert len(rows) == 1
        assert rows[0]["id"] == "j2"

    async def test_filter_by_search(self, db_setup):
        await _insert_sample("j1", file_path="/media/action/movie.mkv")
        await _insert_sample("j2", file_path="/media/comedy/show.mkv")
        rows = await get_history(search="comedy")
        assert len(rows) == 1
        assert rows[0]["id"] == "j2"

    async def test_sort_by_valid_column(self, db_setup):
        await _insert_sample("j1", file_path="/media/b.mkv")
        await _insert_sample("j2", file_path="/media/a.mkv")
        rows = await get_history(sort_by="file_path", sort_dir="asc")
        assert rows[0]["id"] == "j2"

    async def test_sort_by_invalid_column_fallback(self, db_setup):
        await _insert_sample("j1", finished_at="2026-01-02T00:00:00")
        await _insert_sample("j2", finished_at="2026-01-01T00:00:00")
        # Invalid sort_by should fall back to finished_at desc
        rows = await get_history(sort_by="nonexistent")
        assert rows[0]["id"] == "j1"

    async def test_sort_dir_asc(self, db_setup):
        await _insert_sample("j1", finished_at="2026-01-02T00:00:00")
        await _insert_sample("j2", finished_at="2026-01-01T00:00:00")
        rows = await get_history(sort_dir="asc")
        assert rows[0]["id"] == "j2"

    async def test_limit_offset(self, db_setup):
        for i in range(5):
            await _insert_sample(f"j{i}", finished_at=f"2026-01-0{i+1}T00:00:00")
        rows = await get_history(limit=2, offset=0, sort_dir="asc")
        assert len(rows) == 2
        assert rows[0]["id"] == "j0"
        rows2 = await get_history(limit=2, offset=2, sort_dir="asc")
        assert rows2[0]["id"] == "j2"

    async def test_exclude_dismissed(self, db_setup):
        await _insert_sample("j1", dismissed=False)
        await _insert_sample("j2", dismissed=True)
        rows = await get_history(exclude_dismissed=True)
        assert len(rows) == 1
        assert rows[0]["id"] == "j1"


class TestGetJobLog:
    async def test_existing_job(self, db_setup):
        await _insert_sample("j1", ffmpeg_log="some log output")
        log = await get_job_log("j1")
        assert log == "some log output"

    async def test_missing_job(self, db_setup):
        assert await get_job_log("nonexistent") is None


class TestGetHistoryEntry:
    async def test_existing(self, db_setup):
        await _insert_sample("j1")
        entry = await get_history_entry("j1")
        assert entry is not None
        assert entry["id"] == "j1"
        assert entry["library_name"] == "movies"

    async def test_missing(self, db_setup):
        assert await get_history_entry("nonexistent") is None


class TestDismissHistoryEntries:
    async def test_dismiss(self, db_setup):
        await _insert_sample("j1")
        await _insert_sample("j2")
        count = await dismiss_history_entries(["j1"])
        assert count == 1
        rows = await get_history(exclude_dismissed=True)
        assert len(rows) == 1
        assert rows[0]["id"] == "j2"

    async def test_empty_list(self, db_setup):
        assert await dismiss_history_entries([]) == 0


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
