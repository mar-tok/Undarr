import aiosqlite

import core.db as db_mod
from core.db import (
    SCHEMA,
    PROCESSED_SCHEMA,
    LIBRARY_FILES_SCHEMA,
    FILE_HASHES_SCHEMA,
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
    get_library_files_page,
    get_library_file_filters,
    resolve_library_file_paths,
    remove_file_hashes,
    delete_file_and_hashes,
    get_size_groups,
    get_files_by_sizes,
    get_cached_hashes,
    upsert_file_hash,
)

import pytest


@pytest.fixture
async def db_setup():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await conn.executescript(SCHEMA)
    await conn.executescript(PROCESSED_SCHEMA)
    await conn.executescript(LIBRARY_FILES_SCHEMA)
    await conn.executescript(FILE_HASHES_SCHEMA)
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


class TestLibraryFilesPage:
    async def test_default_sort_size_desc(self, db_setup):
        await upsert_library_file("/media/a.mkv", "lib1", "h264", 1080, 1000, 1.0)
        await upsert_library_file("/media/b.mkv", "lib1", "hevc", 1080, 3000, 1.0)
        await upsert_library_file("/media/c.mkv", "lib1", "hevc", 1080, 2000, 1.0)
        rows, total = await get_library_files_page("lib1")
        assert total == 3
        assert [r["file_path"] for r in rows] == [
            "/media/b.mkv",
            "/media/c.mkv",
            "/media/a.mkv",
        ]

    async def test_scoped_to_library(self, db_setup):
        await upsert_library_file("/media/a.mkv", "lib1", "h264", 1080, 100, 1.0)
        await upsert_library_file("/other/b.mkv", "lib2", "h264", 1080, 100, 1.0)
        rows, total = await get_library_files_page("lib1")
        assert total == 1
        assert rows[0]["file_path"] == "/media/a.mkv"

    async def test_limit_offset(self, db_setup):
        for i in range(5):
            await upsert_library_file(
                f"/media/f{i}.mkv", "lib1", "h264", 1080, (i + 1) * 100, 1.0
            )
        rows, total = await get_library_files_page("lib1", limit=2, offset=2)
        assert total == 5
        assert [r["file_path"] for r in rows] == ["/media/f2.mkv", "/media/f1.mkv"]

    async def test_sort_path_asc(self, db_setup):
        await upsert_library_file("/media/b.mkv", "lib1", "h264", 1080, 200, 1.0)
        await upsert_library_file("/media/a.mkv", "lib1", "h264", 1080, 100, 1.0)
        rows, _ = await get_library_files_page(
            "lib1", sort_by="file_path", sort_dir="asc"
        )
        assert [r["file_path"] for r in rows] == ["/media/a.mkv", "/media/b.mkv"]

    async def test_unknown_sort_falls_back_to_size(self, db_setup):
        await upsert_library_file("/media/a.mkv", "lib1", "h264", 1080, 100, 1.0)
        await upsert_library_file("/media/b.mkv", "lib1", "h264", 1080, 200, 1.0)
        rows, _ = await get_library_files_page(
            "lib1", sort_by="mtime; DROP TABLE library_files"
        )
        assert [r["file_path"] for r in rows] == ["/media/b.mkv", "/media/a.mkv"]

    async def test_codec_and_container_filters(self, db_setup):
        await upsert_library_file(
            "/media/a.mkv", "lib1", "h264", 1080, 100, 1.0, container="mkv"
        )
        await upsert_library_file(
            "/media/b.mp4", "lib1", "hevc", 1080, 200, 1.0, container="mp4"
        )
        rows, total = await get_library_files_page("lib1", codec="hevc")
        assert total == 1
        assert rows[0]["file_path"] == "/media/b.mp4"
        rows, total = await get_library_files_page("lib1", container="mkv")
        assert total == 1
        assert rows[0]["file_path"] == "/media/a.mkv"

    async def test_resolution_ranges(self, db_setup):
        await upsert_library_file("/media/uhd.mkv", "lib1", "hevc", 2160, 100, 1.0)
        await upsert_library_file("/media/fhd.mkv", "lib1", "hevc", 1080, 100, 1.0)
        await upsert_library_file("/media/low.mkv", "lib1", "hevc", 480, 100, 1.0)
        rows, _ = await get_library_files_page("lib1", resolution="4k")
        assert [r["file_path"] for r in rows] == ["/media/uhd.mkv"]
        rows, _ = await get_library_files_page("lib1", resolution="sd")
        assert [r["file_path"] for r in rows] == ["/media/low.mkv"]
        _, total = await get_library_files_page("lib1", resolution="8k")
        assert total == 3

    async def test_search_matches_path(self, db_setup):
        await upsert_library_file(
            "/media/Video Title.mkv", "lib1", "h264", 1080, 100, 1.0
        )
        await upsert_library_file("/media/Other.mkv", "lib1", "h264", 1080, 100, 1.0)
        rows, total = await get_library_files_page("lib1", search="Title")
        assert total == 1
        assert rows[0]["file_path"] == "/media/Video Title.mkv"

    async def test_status_filter_and_processed_flag(self, db_setup):
        await upsert_library_file("/media/a.mkv", "lib1", "h264", 1080, 200, 1.0)
        await upsert_library_file("/media/b.mkv", "lib1", "h264", 1080, 100, 1.0)
        await mark_processed("/media/a.mkv", "lib1", 1.0)
        rows, _ = await get_library_files_page("lib1")
        assert [(r["file_path"], r["processed"]) for r in rows] == [
            ("/media/a.mkv", 1),
            ("/media/b.mkv", 0),
        ]
        rows, total = await get_library_files_page("lib1", status="processed")
        assert total == 1
        assert rows[0]["file_path"] == "/media/a.mkv"
        rows, total = await get_library_files_page("lib1", status="unprocessed")
        assert total == 1
        assert rows[0]["file_path"] == "/media/b.mkv"

    async def test_hdr_type_stored_and_sortable(self, db_setup):
        await upsert_library_file(
            "/media/a.mkv", "lib1", "hevc", 2160, 100, 1.0, hdr_type="hdr10"
        )
        await upsert_library_file("/media/b.mkv", "lib1", "h264", 1080, 200, 1.0)
        rows, _ = await get_library_files_page(
            "lib1", sort_by="hdr_type", sort_dir="desc"
        )
        assert [(r["file_path"], r["hdr_type"]) for r in rows] == [
            ("/media/a.mkv", "hdr10"),
            ("/media/b.mkv", ""),
        ]


class TestLibraryFileFilters:
    async def test_distinct_sorted(self, db_setup):
        await upsert_library_file(
            "/media/a.mkv", "lib1", "hevc", 1080, 100, 1.0, container="mkv"
        )
        await upsert_library_file(
            "/media/b.mp4", "lib1", "av1", 1080, 100, 1.0, container="mp4"
        )
        await upsert_library_file(
            "/media/c.mkv", "lib1", "hevc", 1080, 100, 1.0, container="mkv"
        )
        filters = await get_library_file_filters("lib1")
        assert filters == {"codecs": ["av1", "hevc"], "containers": ["mkv", "mp4"]}

    async def test_excludes_empty_and_other_libraries(self, db_setup):
        await upsert_library_file("/media/a.mkv", "lib1", "", 0, 100, 1.0)
        await upsert_library_file(
            "/other/b.mkv", "lib2", "h264", 1080, 100, 1.0, container="mkv"
        )
        filters = await get_library_file_filters("lib1")
        assert filters == {"codecs": [], "containers": []}


class TestResolveLibraryFilePaths:
    async def test_exact_file_match(self, db_setup):
        await upsert_library_file("/media/a.mkv", "lib1", "h264", 1080, 100, 1.0)
        result = await resolve_library_file_paths("lib1", ["/media/a.mkv"])
        assert result == ["/media/a.mkv"]

    async def test_directory_expands_to_files(self, db_setup):
        await upsert_library_file("/media/show/e1.mkv", "lib1", "h264", 1080, 100, 1.0)
        await upsert_library_file("/media/show/e2.mkv", "lib1", "h264", 1080, 100, 1.0)
        await upsert_library_file("/media/other.mkv", "lib1", "h264", 1080, 100, 1.0)
        result = await resolve_library_file_paths("lib1", ["/media/show"])
        assert result == ["/media/show/e1.mkv", "/media/show/e2.mkv"]

    async def test_file_inside_selected_directory_dedupes(self, db_setup):
        await upsert_library_file("/media/show/e1.mkv", "lib1", "h264", 1080, 100, 1.0)
        result = await resolve_library_file_paths(
            "lib1", ["/media/show", "/media/show/e1.mkv"]
        )
        assert result == ["/media/show/e1.mkv"]

    async def test_scoped_to_library(self, db_setup):
        await upsert_library_file("/media/a.mkv", "lib2", "h264", 1080, 100, 1.0)
        result = await resolve_library_file_paths("lib1", ["/media/a.mkv"])
        assert result == []

    async def test_directory_prefix_needs_separator(self, db_setup):
        await upsert_library_file("/media/showdown.mkv", "lib1", "h264", 1080, 100, 1.0)
        result = await resolve_library_file_paths("lib1", ["/media/show"])
        assert result == []


class TestFileHashes:
    async def test_upsert_and_cached_lookup(self, db_setup):
        await upsert_file_hash("/media/a.mkv", "lib1", 1.0, "p1", "")
        await upsert_file_hash("/media/a.mkv", "lib1", 2.0, "p1", "f1")
        cached = await get_cached_hashes(
            [("/media/a.mkv", "lib1"), ("/media/b.mkv", "lib1")]
        )
        assert cached == {
            ("/media/a.mkv", "lib1"): {
                "mtime": 2.0,
                "partial_hash": "p1",
                "full_hash": "f1",
            }
        }

    async def test_cached_lookup_empty(self, db_setup):
        assert await get_cached_hashes([]) == {}

    async def test_cached_lookup_crosses_chunks(self, db_setup):
        pairs = [(f"/media/{i}.mkv", "lib1") for i in range(1203)]
        for fp, lib in pairs:
            await upsert_file_hash(fp, lib, 1.0, "p", "")
        assert len(await get_cached_hashes(pairs)) == 1203

    async def test_size_groups_need_two_files(self, db_setup):
        await upsert_library_file("/media/a.mkv", "lib1", "h264", 1080, 1000, 1.0)
        await upsert_library_file("/media/b.mkv", "lib1", "h264", 1080, 1000, 1.0)
        await upsert_library_file("/media/c.mkv", "lib1", "h264", 1080, 2000, 1.0)
        assert await get_size_groups(["lib1"]) == [(1000, 2)]

    async def test_size_groups_span_libraries_when_unscoped(self, db_setup):
        await upsert_library_file("/media/a.mkv", "lib1", "h264", 1080, 1000, 1.0)
        await upsert_library_file("/other/a.mkv", "lib2", "h264", 1080, 1000, 1.0)
        assert await get_size_groups(["lib1"]) == []
        assert await get_size_groups(None) == [(1000, 2)]

    async def test_files_by_sizes(self, db_setup):
        await upsert_library_file("/media/a.mkv", "lib1", "h264", 1080, 1000, 1.0)
        await upsert_library_file("/media/b.mkv", "lib1", "h264", 1080, 2000, 1.0)
        await upsert_library_file("/other/c.mkv", "lib2", "h264", 1080, 1000, 1.0)
        rows = await get_files_by_sizes([1000], ["lib1"])
        assert [r["file_path"] for r in rows] == ["/media/a.mkv"]
        rows = await get_files_by_sizes([1000], None)
        assert sorted(r["file_path"] for r in rows) == ["/media/a.mkv", "/other/c.mkv"]
        assert await get_files_by_sizes([], None) == []

    async def test_rename_file_moves_hash(self, db_setup):
        await upsert_library_file("/old.mkv", "lib1", "h264", 1080, 1000, 1.0)
        await upsert_file_hash("/old.mkv", "lib1", 1.0, "p", "f")
        assert await rename_file("/old.mkv", "/new.mkv", "lib1", 7.0) is True
        cached = await get_cached_hashes([("/new.mkv", "lib1")])
        assert cached[("/new.mkv", "lib1")]["full_hash"] == "f"

    async def test_rename_library_moves_hashes(self, db_setup):
        await upsert_file_hash("/a.mkv", "lib1", 1.0, "p", "f")
        await rename_library("lib1", "lib9")
        assert ("/a.mkv", "lib9") in await get_cached_hashes([("/a.mkv", "lib9")])

    async def test_remove_file_hashes_scoped(self, db_setup):
        await upsert_file_hash("/a.mkv", "lib1", 1.0, "p", "f")
        await upsert_file_hash("/b.mkv", "lib2", 1.0, "p", "f")
        await remove_file_hashes("lib1")
        cached = await get_cached_hashes([("/a.mkv", "lib1"), ("/b.mkv", "lib2")])
        assert list(cached) == [("/b.mkv", "lib2")]

    async def test_delete_file_and_hashes(self, db_setup):
        await upsert_library_file("/a.mkv", "lib1", "h264", 1080, 1000, 1.0)
        await upsert_library_file("/a.mkv", "lib2", "h264", 1080, 1000, 1.0)
        await upsert_file_hash("/a.mkv", "lib1", 1.0, "p", "f")
        await upsert_file_hash("/a.mkv", "lib2", 1.0, "p", "f")
        await delete_file_and_hashes("/a.mkv", "lib1")
        assert await get_library_files_mtimes("lib1") == {}
        assert await get_library_files_mtimes("lib2") == {"/a.mkv": 1.0}
        cached = await get_cached_hashes([("/a.mkv", "lib1"), ("/a.mkv", "lib2")])
        assert list(cached) == [("/a.mkv", "lib2")]
