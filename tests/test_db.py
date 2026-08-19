import aiosqlite

import core.db as db_mod
from core.db import (
    SCHEMA,
    PROCESSED_SCHEMA,
    LIBRARY_FILES_SCHEMA,
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
    upsert_library_file,
    remove_library_file,
    find_rename_candidate,
    rename_file,
    rename_library,
    remove_library_files,
    cleanup_library_files,
    get_library_files_mtimes,
    get_stats_totals,
    get_stats_by_library,
    get_stats_by_device,
    get_device_avg_duration,
    get_stats_library_sizes,
    get_stats_composition,
    get_stats_file_counts,
    get_stats_processed_counts,
    get_storage_files,
    get_storage_savings,
)

import pytest


@pytest.fixture
async def db_setup():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await conn.executescript(SCHEMA)
    await conn.executescript(PROCESSED_SCHEMA)
    await conn.executescript(LIBRARY_FILES_SCHEMA)
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


class TestLibraryFiles:
    async def test_upsert_and_mtimes(self, db_setup):
        await upsert_library_file("/a.mkv", "lib1", "h264", 1080, 1000, 1.0)
        await upsert_library_file("/b.mkv", "lib1", "hevc", 2160, 2000, 2.0)
        mtimes = await get_library_files_mtimes("lib1")
        assert mtimes == {"/a.mkv": 1.0, "/b.mkv": 2.0}

    async def test_upsert_replaces(self, db_setup):
        await upsert_library_file("/a.mkv", "lib1", "h264", 1080, 1000, 1.0)
        await upsert_library_file("/a.mkv", "lib1", "hevc", 1080, 800, 5.0)
        mtimes = await get_library_files_mtimes("lib1")
        assert mtimes == {"/a.mkv": 5.0}

    async def test_remove(self, db_setup):
        await upsert_library_file("/a.mkv", "lib1", "h264", 1080, 1000, 1.0)
        await remove_library_file("/a.mkv", "lib1")
        assert await get_library_files_mtimes("lib1") == {}

    async def test_cleanup_removes_stale(self, db_setup):
        await upsert_library_file("/a.mkv", "lib1", "h264", 1080, 1000, 1.0)
        await upsert_library_file("/b.mkv", "lib1", "h264", 1080, 1000, 1.0)
        await cleanup_library_files("lib1", {"/a.mkv"})
        assert await get_library_files_mtimes("lib1") == {"/a.mkv": 1.0}

    async def test_remove_library_files_scoped(self, db_setup):
        await upsert_library_file("/a.mkv", "lib1", "h264", 1080, 1000, 1.0)
        await upsert_library_file("/b.mkv", "lib2", "h264", 1080, 1000, 1.0)
        await remove_library_files("lib1")
        assert await get_library_files_mtimes("lib1") == {}
        assert await get_library_files_mtimes("lib2") == {"/b.mkv": 1.0}

    async def test_rename_library(self, db_setup):
        await upsert_library_file("/a.mkv", "lib1", "h264", 1080, 1000, 1.0)
        await mark_processed("/a.mkv", "lib1", 1.0)
        await _insert_sample("job1", library_name="lib1")
        await rename_library("lib1", "lib2")
        assert await get_library_files_mtimes("lib1") == {}
        assert await get_library_files_mtimes("lib2") == {"/a.mkv": 1.0}
        assert await is_processed("/a.mkv", "lib2", 1.0)
        assert not await is_processed("/a.mkv", "lib1", 1.0)
        rows = await get_history()
        assert rows[0]["library_name"] == "lib2"


class TestRenameDetection:
    async def test_candidate_must_be_gone_from_disk(self, db_setup, tmp_path):
        still_here = tmp_path / "old.mkv"
        still_here.write_bytes(b"x")
        await upsert_library_file(str(still_here), "lib1", "h264", 1080, 1000, 1.0)
        assert await find_rename_candidate("/new.mkv", "lib1", 1000) is None
        await upsert_library_file("/gone.mkv", "lib1", "h264", 1080, 1000, 1.0)
        assert await find_rename_candidate("/new.mkv", "lib1", 1000) == "/gone.mkv"

    async def test_candidate_requires_matching_size(self, db_setup):
        await upsert_library_file("/gone.mkv", "lib1", "h264", 1080, 1000, 1.0)
        assert await find_rename_candidate("/new.mkv", "lib1", 999) is None

    async def test_rename_file_moves_records(self, db_setup):
        await upsert_library_file("/old.mkv", "lib1", "h264", 1080, 1000, 1.0)
        await mark_processed("/old.mkv", "lib1", 1.0)
        assert await rename_file("/old.mkv", "/new.mkv", "lib1", 7.0) is True
        assert await is_processed("/new.mkv", "lib1", 7.0)
        assert await get_library_files_mtimes("lib1") == {"/new.mkv": 7.0}

    async def test_rename_file_no_records(self, db_setup):
        assert await rename_file("/old.mkv", "/new.mkv", "lib1", 7.0) is False

    async def test_rename_file_new_path_already_scanned(self, db_setup):
        # scan_library upserts the new path before rename detection runs
        await upsert_library_file("/old.mkv", "lib1", "h264", 1080, 1000, 1.0)
        await mark_processed("/old.mkv", "lib1", 1.0)
        await upsert_library_file("/new.mkv", "lib1", "h264", 1080, 1000, 7.0)
        assert await rename_file("/old.mkv", "/new.mkv", "lib1", 7.0) is True
        assert await is_processed("/new.mkv", "lib1", 7.0)
        assert await get_library_files_mtimes("lib1") == {"/new.mkv": 7.0}


class TestStatsQueries:
    async def test_totals(self, db_setup):
        await _insert_sample("j1", status="completed")
        await _insert_sample("j2", status="failed", new_size_bytes=None)
        await _insert_sample("j3", status="skipped (rule)", new_size_bytes=None)
        totals = await get_stats_totals()
        assert totals["completed"] == 1
        assert totals["failed"] == 1
        assert totals["skipped"] == 1
        assert totals["space_saved_bytes"] == 500000

    async def test_totals_exclude_dismissed(self, db_setup):
        await _insert_sample("j1", status="completed")
        await dismiss_history_entries(["j1"])
        totals = await get_stats_totals()
        assert totals["completed"] == 0

    async def test_by_library(self, db_setup):
        await _insert_sample("j1", library_name="lib1", status="completed")
        await _insert_sample(
            "j2", library_name="lib1", status="skipped", new_size_bytes=None
        )
        await _insert_sample("j3", library_name="lib2", status="completed")
        by_lib = {r["library"]: r for r in await get_stats_by_library()}
        assert by_lib["lib1"]["completed"] == 1
        assert by_lib["lib1"]["processed"] == 2
        assert by_lib["lib2"]["completed"] == 1

    async def test_by_device(self, db_setup):
        await _insert_sample("j1", device_name="CPU", duration_seconds=60.0)
        await _insert_sample("j2", device_name="CPU", duration_seconds=120.0)
        await _insert_sample("j3", device_name="NVENC", duration_seconds=30.0)
        await _insert_sample("j4", status="failed", device_name="CPU")
        by_dev = {r["device"]: r for r in await get_stats_by_device()}
        assert by_dev["CPU"]["completed"] == 2
        assert by_dev["CPU"]["processing_seconds"] == 180.0
        assert by_dev["NVENC"]["completed"] == 1

    async def test_by_device_excludes_empty_name(self, db_setup):
        await _insert_sample("j1", device_name="")
        assert await get_stats_by_device() == []

    async def test_device_avg_duration(self, db_setup):
        await _insert_sample("j1", device_name="CPU", duration_seconds=60.0)
        await _insert_sample("j2", device_name="CPU", duration_seconds=120.0)
        await _insert_sample(
            "j3", status="failed", device_name="CPU", duration_seconds=500.0
        )
        assert await get_device_avg_duration() == {"CPU": 90.0}

    async def test_library_sizes(self, db_setup):
        await upsert_library_file("/a.mkv", "lib1", "h264", 1080, 1000, 1.0)
        await upsert_library_file("/b.mkv", "lib1", "hevc", 1080, 2000, 1.0)
        await upsert_library_file("/c.mkv", "lib2", "hevc", 1080, 500, 1.0)
        assert await get_stats_library_sizes() == {"lib1": 3000, "lib2": 500}

    async def test_composition_and_counts(self, db_setup):
        await upsert_library_file("/a.mkv", "lib1", "h264", 1080, 1000, 1.0)
        await upsert_library_file("/b.mkv", "lib1", "hevc", 1080, 1000, 1.0)
        await upsert_library_file("/c.mkv", "lib1", "hevc", 1080, 1000, 1.0)
        await mark_processed("/b.mkv", "lib1", 1.0)
        assert await get_stats_composition() == {"lib1": {"h264": 1, "hevc": 2}}
        assert await get_stats_file_counts() == {"lib1": 3}
        assert await get_stats_processed_counts() == {"lib1": 1}


class TestStorageQueries:
    async def test_files_scoped_to_library(self, db_setup):
        await upsert_library_file("/media/a.mkv", "lib1", "h264", 1080, 1000, 1.0)
        await upsert_library_file("/media/sub/b.mkv", "lib1", "hevc", 1080, 2000, 1.0)
        await upsert_library_file("/other/c.mkv", "lib2", "hevc", 1080, 500, 1.0)
        files = await get_storage_files("lib1")
        assert sorted(files) == [
            ("/media/a.mkv", 1000, "h264"),
            ("/media/sub/b.mkv", 2000, "hevc"),
        ]

    async def test_files_prefix(self, db_setup):
        await upsert_library_file("/media/a.mkv", "lib1", "h264", 1080, 1000, 1.0)
        await upsert_library_file("/media/sub/b.mkv", "lib1", "hevc", 1080, 2000, 1.0)
        files = await get_storage_files("lib1", "/media/sub")
        assert files == [("/media/sub/b.mkv", 2000, "hevc")]

    async def test_files_prefix_needs_full_segment(self, db_setup):
        await upsert_library_file(
            "/media/subtitle/x.mkv", "lib1", "h264", 1080, 1000, 1.0
        )
        assert await get_storage_files("lib1", "/media/sub") == []

    async def test_savings_sums_per_path(self, db_setup):
        await _insert_sample("j1", library_name="lib1", file_path="/media/a.mkv")
        await _insert_sample(
            "j2",
            library_name="lib1",
            file_path="/media/a.mkv",
            old_size_bytes=800000,
            new_size_bytes=600000,
        )
        await _insert_sample("j3", library_name="lib1", file_path="/media/b.mkv")
        savings = await get_storage_savings("lib1")
        assert savings == {"/media/a.mkv": 700000, "/media/b.mkv": 500000}

    async def test_savings_only_completed_undismissed(self, db_setup):
        await _insert_sample(
            "j1", library_name="lib1", file_path="/media/a.mkv", status="failed"
        )
        await _insert_sample(
            "j2", library_name="lib1", file_path="/media/b.mkv", dismissed=True
        )
        await _insert_sample(
            "j3", library_name="lib1", file_path="/media/c.mkv", new_size_bytes=None
        )
        assert await get_storage_savings("lib1") == {}

    async def test_savings_prefix(self, db_setup):
        await _insert_sample("j1", library_name="lib1", file_path="/media/sub/a.mkv")
        await _insert_sample("j2", library_name="lib1", file_path="/media/b.mkv")
        assert await get_storage_savings("lib1", "/media/sub") == {
            "/media/sub/a.mkv": 500000
        }
