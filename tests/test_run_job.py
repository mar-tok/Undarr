import asyncio
import shutil
from pathlib import Path
from unittest.mock import patch, AsyncMock

import aiosqlite
import pytest

import config
import core.db as db_mod
import core.watcher as watcher_mod
from core.db import (
    SCHEMA,
    PROCESSED_SCHEMA,
    LIBRARY_FILES_SCHEMA,
    FILE_HASHES_SCHEMA,
    get_history,
    get_job_log,
    is_processed,
    get_library_files_mtimes,
)
from core.ffprobe import probe_file, extract_media_info
from core.queue_manager import JobStatus, QueueManager
from core.watcher import is_suppressed
from core.yaml_store import YamlStore, Preset, Library

FIXTURES = Path(__file__).parent / "fixtures"
SOURCE = FIXTURES / "edge_cases" / "valid.mkv"

# ultrafast x265 comes out well under the 16 KB source, ultrafast x264 does not
HEVC = "-c:v libx265 -preset ultrafast -crf 35"
H264 = "-c:v libx264 -preset ultrafast -crf 35"


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


@pytest.fixture
async def store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.yaml")
    s = YamlStore()
    await s.load()
    await s.update_settings(cache_dir=str(tmp_path / "cache"))
    await s.create_preset("HEVC", Preset(ffmpeg_args=HEVC))
    await s.create_library(
        "movies", Library(paths=[str(tmp_path / "lib")], preset="HEVC")
    )
    monkeypatch.setattr("core.queue_manager.store", s)
    return s


@pytest.fixture
async def qm(store, db_setup):
    manager = QueueManager()
    manager._device_limits = {"cpu": 1}
    manager._device_active = {"cpu": 0}
    yield manager
    for task in manager._unsuppress_tasks:
        task.cancel()
    watcher_mod._suppressed_paths.clear()


@pytest.fixture
def fired():
    with patch("core.queue_manager.fire_event", AsyncMock()) as fire:
        yield fire


async def _queue(qm, tmp_path, name="valid.mkv", source=SOURCE):
    lib = tmp_path / "lib"
    lib.mkdir(exist_ok=True)
    path = lib / name
    shutil.copy(source, path)
    job = await qm.enqueue(str(path), "movies")
    qm._pending.remove(job)
    qm._active[job.id] = job
    qm._device_active["cpu"] += 1
    return job


async def _run(qm, job):
    await qm._run_job(job)
    assert qm._active == {}
    assert qm._device_active["cpu"] == 0
    assert job.file_path not in qm._known_paths
    rows = await get_history()
    assert [r["id"] for r in rows] == [job.id]
    return rows[0]


def _cache_files(tmp_path):
    return sorted(p.name for p in (tmp_path / "cache").iterdir())


class TestCompleted:
    async def test_output_replaces_original(self, qm, tmp_path):
        job = await _queue(qm, tmp_path)
        path = Path(job.file_path)
        row = await _run(qm, job)

        assert job.status == JobStatus.COMPLETED
        assert path.stat().st_size == job.new_size_bytes < job.old_size_bytes
        info = extract_media_info(await probe_file(str(path)))
        assert info["video_codec"] == "hevc"
        assert _cache_files(tmp_path) == []

        assert row["status"] == "completed"
        assert row["new_size_bytes"] == job.new_size_bytes
        assert row["preset_name"] == "HEVC"
        assert "x265" in await get_job_log(job.id)
        assert await is_processed(str(path), "movies", path.stat().st_mtime)
        assert await get_library_files_mtimes("movies") == {
            str(path): path.stat().st_mtime
        }
        assert is_suppressed(str(path))

    async def test_container_switch_removes_old_file(self, qm, store, tmp_path):
        await store.create_preset(
            "MP4", Preset(ffmpeg_args=HEVC, output_container="mp4")
        )
        await store.update_library(
            "movies", Library(paths=[str(tmp_path / "lib")], preset="MP4")
        )
        job = await _queue(qm, tmp_path)
        old = Path(job.file_path)
        row = await _run(qm, job)

        new = old.with_suffix(".mp4")
        assert job.status == JobStatus.COMPLETED
        assert not old.exists()
        assert new.exists()
        assert job.file_path == str(new)
        assert row["file_path"] == str(new)
        assert list(await get_library_files_mtimes("movies")) == [str(new)]
        assert await is_processed(str(new), "movies", new.stat().st_mtime)

    async def test_rename_after_replace(self, qm, store, tmp_path):
        await store.update_preset("HEVC", Preset(ffmpeg_args=HEVC, rename_file=True))
        job = await _queue(qm, tmp_path, "Video.Title.2020.1080p.WEB-DL.x264-GROUP.mkv")
        old = Path(job.file_path)
        row = await _run(qm, job)

        new = old.with_name("Video.Title.2020.1080p.WEB-DL.x265-GROUP.mkv")
        assert job.status == JobStatus.COMPLETED
        assert not old.exists()
        assert new.exists()
        assert job.file_path == str(new)
        assert row["file_path"] == str(new)
        assert list(await get_library_files_mtimes("movies")) == [str(new)]
        assert await is_processed(str(new), "movies", new.stat().st_mtime)
        assert is_suppressed(str(old))
        assert is_suppressed(str(new))


class TestOriginalKept:
    async def test_larger_output_is_skipped(self, qm, store, tmp_path):
        await store.update_preset("HEVC", Preset(ffmpeg_args=H264))
        job = await _queue(qm, tmp_path)
        path = Path(job.file_path)
        row = await _run(qm, job)

        assert job.status == JobStatus.SKIPPED
        assert path.read_bytes() == SOURCE.read_bytes()
        assert _cache_files(tmp_path) == []
        assert job.error_message.startswith("Output (")
        assert "is not smaller than original" in job.error_message
        assert row["status"] == "skipped"
        assert row["new_size_bytes"] is None
        assert await is_processed(str(path), "movies", path.stat().st_mtime)
        assert await get_library_files_mtimes("movies") == {}

    async def test_ffmpeg_error_fails(self, qm, store, tmp_path, fired):
        await store.update_preset(
            "HEVC", Preset(ffmpeg_args="-c:v libx265 -preset nosuchpreset")
        )
        job = await _queue(qm, tmp_path)
        path = Path(job.file_path)
        row = await _run(qm, job)

        assert job.status == JobStatus.FAILED
        assert path.read_bytes() == SOURCE.read_bytes()
        assert _cache_files(tmp_path) == []
        assert job.error_message
        assert row["status"] == "failed"
        assert row["error_message"] == job.error_message
        assert "nosuchpreset" in await get_job_log(job.id)
        assert await is_processed(str(path), "movies", path.stat().st_mtime)
        fired.assert_called_once()
        assert fired.call_args.args[0] == "job_failed"

    async def test_truncated_output_fails_verification(self, qm, store, tmp_path):
        await store.update_preset("HEVC", Preset(ffmpeg_args=f"{HEVC} -t 1"))
        job = await _queue(qm, tmp_path)
        path = Path(job.file_path)
        row = await _run(qm, job)

        assert job.status == JobStatus.FAILED
        assert path.read_bytes() == SOURCE.read_bytes()
        assert _cache_files(tmp_path) == []
        assert job.error_message.startswith(
            "Post-encode verification failed: Output duration (1.0s) differs from source (3.0s)"
        )
        assert "the encode stopped early" in job.error_message
        assert row["status"] == "failed"

    async def test_cancel_kills_ffmpeg(self, qm, store, tmp_path):
        await store.update_preset(
            "HEVC", Preset(ffmpeg_args="-c:v libx265 -preset slow")
        )
        source = FIXTURES / "video_profiles" / "1080p_h264_8bit.mkv"
        job = await _queue(qm, tmp_path, "big.mkv", source)
        path = Path(job.file_path)

        task = asyncio.create_task(qm._run_job(job))
        for _ in range(400):
            if job.id in qm._active_procs:
                break
            await asyncio.sleep(0.005)
        assert job.id in qm._active_procs
        assert await qm.cancel(job.id)
        await task

        assert job.status == JobStatus.CANCELLED
        assert job.error_message == "Cancelled by user"
        assert path.read_bytes() == source.read_bytes()
        assert _cache_files(tmp_path) == []
        rows = await get_history()
        assert rows[0]["status"] == "cancelled"
        assert not await is_processed(str(path), "movies", path.stat().st_mtime)
