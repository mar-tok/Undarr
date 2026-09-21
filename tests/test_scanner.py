import asyncio

import aiosqlite

import core.db as db_mod
import core.scanner as scanner_mod
from core.db import (
    SCHEMA,
    PROCESSED_SCHEMA,
    LIBRARY_FILES_SCHEMA,
    FILE_HASHES_SCHEMA,
    mark_processed,
    is_processed,
)
from core.scanner import (
    preview_library,
    scan_library,
    _relative_to_library,
    _collect_video_files,
)
from core.yaml_store import Library, SkipRule, SkipCondition

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


MEDIA_INFO = {
    "video_codec": "h264",
    "resolution_width": 1920,
    "resolution_height": 1080,
    "bitrate_kbps": 8000,
}


@pytest.fixture
def media_dir(tmp_path, monkeypatch):
    root = tmp_path / "movies"
    root.mkdir()

    async def fake_probe(file_path):
        return {"path": file_path}

    monkeypatch.setattr(scanner_mod, "probe_file", fake_probe)
    monkeypatch.setattr(
        scanner_mod, "extract_media_info", lambda probe: dict(MEDIA_INFO)
    )
    return root


def _add_file(root, name, size=1000):
    f = root / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b"\0" * size)
    return f


def _library(root, **overrides):
    defaults = {"paths": [str(root)], "preset": "HEVC"}
    defaults.update(overrides)
    return Library(**defaults)


class TestPreviewLibrary:
    async def test_lists_unprocessed_files(self, db_setup, media_dir):
        _add_file(media_dir, "a.mkv", 2000)
        _add_file(media_dir, "sub/b.mkv", 1000)
        result = await preview_library("movies", _library(media_dir))
        assert result["summary"]["total_files"] == 2
        assert result["summary"]["would_queue"] == 2
        assert result["summary"]["would_queue_bytes"] == 3000
        assert {f["path"] for f in result["queue"]} == {"a.mkv", "sub/b.mkv"}
        entry = next(f for f in result["queue"] if f["path"] == "a.mkv")
        assert entry["video_codec"] == "h264"
        assert entry["resolution"] == "1920x1080"
        assert entry["bitrate_kbps"] == 8000

    async def test_failed_probe_reports_unknown(self, db_setup, media_dir, monkeypatch):
        _add_file(media_dir, "a.mkv")

        async def fake_probe(file_path):
            return None

        monkeypatch.setattr(scanner_mod, "probe_file", fake_probe)
        result = await preview_library("movies", _library(media_dir))
        assert result["queue"][0]["video_codec"] == "unknown"
        assert result["queue"][0]["resolution"] == "unknown"

    async def test_counts_already_processed(self, db_setup, media_dir):
        f = _add_file(media_dir, "a.mkv")
        _add_file(media_dir, "b.mkv")
        await mark_processed(str(f), "movies", f.stat().st_mtime)
        result = await preview_library("movies", _library(media_dir))
        assert result["summary"]["already_processed"] == 1
        assert result["summary"]["would_queue"] == 1
        assert result["queue"][0]["path"] == "b.mkv"

    async def test_skip_rule_match_goes_to_skipped(self, db_setup, media_dir):
        _add_file(media_dir, "a.mkv")
        rule = SkipRule(
            conditions=[
                SkipCondition(field="video_codec", operator="equals", value="h264")
            ]
        )
        result = await preview_library("movies", _library(media_dir, skip_rules=[rule]))
        assert result["summary"]["would_queue"] == 0
        assert result["summary"]["skipped"] == 1
        assert result["skipped"][0]["reason"].startswith("Skip rule:")

    async def test_path_pattern_match_goes_to_skipped(self, db_setup, media_dir):
        _add_file(media_dir, "movie-sample.mkv")
        result = await preview_library(
            "movies", _library(media_dir, path_patterns=["*sample*"])
        )
        assert result["summary"]["would_queue"] == 0
        assert result["skipped"][0]["reason"] == "Path pattern: *sample*"

    async def test_new_file_delay(self, db_setup, media_dir):
        _add_file(media_dir, "a.mkv")
        lib = _library(media_dir, new_file_delay=1, new_file_delay_unit="hours")
        result = await preview_library("movies", lib)
        assert result["summary"]["too_new"] == 1
        assert result["summary"]["skipped"] == 1
        assert result["skipped"][0]["reason"] == "Too new (file delay not elapsed)"

    async def test_marks_nothing_processed(self, db_setup, media_dir):
        f = _add_file(media_dir, "a.mkv")
        await preview_library("movies", _library(media_dir))
        assert not await is_processed(str(f), "movies", f.stat().st_mtime)

    async def test_reports_progress(self, db_setup, media_dir):
        for i in range(3):
            _add_file(media_dir, f"f{i}.mkv")
        calls = []

        async def progress(scanned, total):
            calls.append((scanned, total))

        await preview_library("movies", _library(media_dir), progress_fn=progress)
        assert calls == [(1, 3), (2, 3), (3, 3)]

    async def test_abort_returns_partial_results(self, db_setup, media_dir):
        for i in range(5):
            _add_file(media_dir, f"f{i}.mkv")
        abort = asyncio.Event()

        async def progress(scanned, total):
            if scanned == 2:
                abort.set()

        result = await preview_library(
            "movies", _library(media_dir), progress_fn=progress, abort_event=abort
        )
        assert result["summary"]["total_files"] == 5
        assert result["summary"]["would_queue"] == 2
        assert result["summary"]["not_scanned"] == 3

    async def test_unaborted_preview_scans_everything(self, db_setup, media_dir):
        _add_file(media_dir, "a.mkv")
        result = await preview_library("movies", _library(media_dir))
        assert result["summary"]["not_scanned"] == 0


class TestScanUnavailable:
    async def test_all_paths_missing_reports_unavailable(self, db_setup, tmp_path):
        missing = str(tmp_path / "gone")
        calls = []

        async def on_unavailable(name, unavailable, reason, missing_paths):
            calls.append((name, unavailable, reason, missing_paths))

        lib = Library(paths=[missing], preset="HEVC")
        await scan_library("movies", lib, None, on_unavailable=on_unavailable)
        assert calls == [("movies", True, f"All paths missing: {missing}", [missing])]

    async def test_partial_missing_reports_paths(self, db_setup, media_dir, tmp_path):
        missing = str(tmp_path / "gone")
        calls = []

        async def on_unavailable(name, unavailable, reason, missing_paths):
            calls.append((name, unavailable, reason, missing_paths))

        lib = _library(media_dir, paths=[str(media_dir), missing])
        await scan_library("movies", lib, None, on_unavailable=on_unavailable)
        assert calls == [("movies", False, "", [missing])]


class TestScanRenameDetection:
    async def _scan(self, media_dir):
        queued = []

        async def enqueue(file_path, library_name, media_info=None):
            queued.append(file_path)
            return "job"

        await scan_library("movies", _library(media_dir), enqueue)
        return queued

    async def test_renamed_processed_file_keeps_its_record(self, db_setup, media_dir):
        new = _add_file(media_dir, "new.mkv")
        gone = str(media_dir / "gone.mkv")
        await db_mod.upsert_library_file(gone, "movies", "h264", 1080, 1000, 1.0)
        await mark_processed(gone, "movies", 1.0)
        assert await self._scan(media_dir) == []
        assert await is_processed(str(new), "movies", new.stat().st_mtime)

    async def test_renamed_unprocessed_file_is_queued(self, db_setup, media_dir):
        new = _add_file(media_dir, "new.mkv")
        gone = str(media_dir / "gone.mkv")
        await db_mod.upsert_library_file(gone, "movies", "h264", 1080, 1000, 1.0)
        assert await self._scan(media_dir) == [str(new)]


class TestRelativeToLibrary:
    def test_path_under_first_dir(self):
        result = _relative_to_library(
            "/media/movies/film.mkv", ["/media/movies", "/media/tv"]
        )
        assert result == "film.mkv"

    def test_path_under_second_dir(self):
        result = _relative_to_library(
            "/media/tv/show/ep.mkv", ["/media/movies", "/media/tv"]
        )
        assert result == "show/ep.mkv"

    def test_not_under_any_dir(self):
        assert _relative_to_library("/other/file.mkv", ["/media/movies"]) is None

    def test_sibling_with_shared_prefix(self):
        assert _relative_to_library("/media/movies2/a.mkv", ["/media/movies"]) is None


class TestCollectVideoFiles:
    def test_finds_video_files(self, tmp_path):
        _add_file(tmp_path, "movie.mkv")
        _add_file(tmp_path, "clip.mp4")
        _add_file(tmp_path, "readme.txt")
        _add_file(tmp_path, "poster.jpg")
        files, missing = _collect_video_files(_library(tmp_path))
        assert {f.name for f in files} == {"movie.mkv", "clip.mp4"}
        assert missing == []

    def test_nonexistent_path_skipped(self, tmp_path):
        bad_path = str(tmp_path / "does_not_exist")
        files, missing = _collect_video_files(_library(tmp_path, paths=[bad_path]))
        assert files == []
        assert missing == [bad_path]

    def test_subdirectories(self, tmp_path):
        _add_file(tmp_path, "subdir/nested.mkv")
        _add_file(tmp_path, "top.mp4")
        files, _ = _collect_video_files(_library(tmp_path))
        assert {f.name for f in files} == {"nested.mkv", "top.mp4"}
