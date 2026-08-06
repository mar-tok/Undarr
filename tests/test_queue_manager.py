from unittest.mock import patch

import pytest

from core.queue_manager import _format_size, job_to_dict, Job, JobStatus, QueueManager
from core.ffmpeg import TranscodeProgress


@pytest.fixture
def qm():
    """Fresh QueueManager."""
    manager = QueueManager()
    manager._device_limits = {"cpu": 2}
    manager._device_active = {"cpu": 0}
    return manager


def _make_job(**overrides) -> Job:
    defaults = {
        "id": "abc123",
        "file_path": "/media/movie.mkv",
        "library_name": "movies",
    }
    defaults.update(overrides)
    return Job(**defaults)


# Pause/Resume


class TestPauseResume:
    async def test_global_pause(self, qm):
        assert qm.paused is False
        await qm.pause()
        assert qm.paused is True

    async def test_global_resume(self, qm):
        await qm.pause()
        await qm.resume()
        assert qm.paused is False

    async def test_pause_broadcasts(self, qm):
        sub = qm.subscribe()
        await qm.pause()
        msg = sub.get_nowait()
        assert "queue_paused" in msg

    async def test_library_pause(self, qm):
        await qm.pause_library("movies")
        assert "movies" in qm.paused_libraries

    async def test_library_resume(self, qm):
        await qm.pause_library("movies")
        await qm.resume_library("movies")
        assert "movies" not in qm.paused_libraries

    async def test_library_pause_broadcasts(self, qm):
        sub = qm.subscribe()
        await qm.pause_library("movies")
        msg = sub.get_nowait()
        assert "library_paused" in msg

    async def test_rename_paused_library(self, qm):
        await qm.pause_library("old")
        await qm.rename_paused_library("old", "new")
        assert "old" not in qm.paused_libraries
        assert "new" in qm.paused_libraries

    async def test_rename_unpaused_library_no_op(self, qm):
        await qm.rename_paused_library("old", "new")
        assert "new" not in qm.paused_libraries

    async def test_clear_paused_library(self, qm):
        await qm.pause_library("movies")
        await qm.clear_paused_library("movies")
        assert "movies" not in qm.paused_libraries

    async def test_clear_unpaused_library_no_op(self, qm):
        await qm.clear_paused_library("movies")
        assert "movies" not in qm.paused_libraries

    async def test_load_paused_libraries(self, qm):
        qm.load_paused_libraries({"a", "b"})
        assert qm.paused_libraries == {"a", "b"}


# Sorting


class TestSorting:
    async def test_sort_fifo(self, qm):
        j1 = _make_job(id="j1", old_size_bytes=100)
        j2 = _make_job(id="j2", old_size_bytes=500)
        qm._pending = [j1, j2]
        with patch("core.queue_manager.store") as mock_store:
            mock_store.config.settings.queue_order = "fifo"
            qm._sort_pending()
        assert qm._pending[0].id == "j1"

    async def test_sort_largest_first(self, qm):
        j1 = _make_job(id="j1", old_size_bytes=100)
        j2 = _make_job(id="j2", old_size_bytes=500)
        qm._pending = [j1, j2]
        with patch("core.queue_manager.store") as mock_store:
            mock_store.config.settings.queue_order = "largest_first"
            qm._sort_pending()
        assert qm._pending[0].id == "j2"

    async def test_sort_highest_bitrate(self, qm):
        j1 = _make_job(id="j1", media_info={"bitrate_kbps": 1000})
        j2 = _make_job(id="j2", media_info={"bitrate_kbps": 5000})
        qm._pending = [j1, j2]
        with patch("core.queue_manager.store") as mock_store:
            mock_store.config.settings.queue_order = "highest_bitrate"
            qm._sort_pending()
        assert qm._pending[0].id == "j2"

    async def test_sort_highest_bitrate_missing_media_info(self, qm):
        j1 = _make_job(id="j1", media_info=None)
        j2 = _make_job(id="j2", media_info={"bitrate_kbps": 5000})
        qm._pending = [j1, j2]
        with patch("core.queue_manager.store") as mock_store:
            mock_store.config.settings.queue_order = "highest_bitrate"
            qm._sort_pending()
        assert qm._pending[0].id == "j2"

    async def test_sort_fifo_restores_arrival_order(self, qm):
        j1 = _make_job(id="j1", old_size_bytes=100, seq=0)
        j2 = _make_job(id="j2", old_size_bytes=500, seq=1)
        qm._pending = [j1, j2]
        with patch("core.queue_manager.store") as mock_store:
            mock_store.config.settings.queue_order = "largest_first"
            qm._sort_pending()
            assert qm._pending[0].id == "j2"
            mock_store.config.settings.queue_order = "fifo"
            qm._sort_pending()
        assert qm._pending[0].id == "j1"


# Size formatting


class TestFormatSize:
    def test_bytes(self):
        assert _format_size(500) == "500 B"

    def test_zero(self):
        assert _format_size(0) == "0 B"

    def test_exact_kb_boundary(self):
        assert _format_size(1024) == "1.0 KB"

    def test_kb(self):
        assert _format_size(2048) == "2.0 KB"

    def test_exact_mb_boundary(self):
        assert _format_size(1048576) == "1.0 MB"

    def test_mb(self):
        assert _format_size(5 * 1048576) == "5.0 MB"

    def test_exact_gb_boundary(self):
        assert _format_size(1073741824) == "1.0 GB"

    def test_gb(self):
        assert _format_size(3 * 1073741824) == "3.0 GB"


# Job serialization


class TestJobToDict:
    def test_minimal(self):
        job = _make_job()
        d = job_to_dict(job)
        assert d["id"] == "abc123"
        assert d["file_path"] == "/media/movie.mkv"
        assert d["library_name"] == "movies"
        assert d["status"] == "pending"
        assert d["device"] == "cpu"
        assert d["old_size_bytes"] == 0
        assert d["new_size_bytes"] is None
        assert d["started_at"] is None
        # Optional fields absent when falsy
        assert "progress" not in d
        assert "error_message" not in d
        assert "block_reason" not in d
        assert "preset_name" not in d
        assert "media_info" not in d

    def test_with_progress(self):
        prog = TranscodeProgress(
            out_time_us=1000000,
            speed="2.5x",
            fps=60.0,
            bitrate="5000kbits/s",
            percent=50.0,
            total_size=500000,
        )
        job = _make_job(progress=prog)
        d = job_to_dict(job)
        assert d["progress"]["percent"] == 50.0
        assert d["progress"]["speed"] == "2.5x"
        assert d["progress"]["fps"] == 60.0
        assert d["progress"]["bitrate"] == "5000kbits/s"

    def test_with_error_message(self):
        job = _make_job(error_message="Something broke", status=JobStatus.FAILED)
        d = job_to_dict(job)
        assert d["error_message"] == "Something broke"
        assert d["status"] == "failed"

    def test_with_block_reason(self):
        job = _make_job(block_reason="No preset assigned", status=JobStatus.BLOCKED)
        d = job_to_dict(job)
        assert d["block_reason"] == "No preset assigned"

    def test_with_preset_name(self):
        job = _make_job(preset_name="HEVC Transparent")
        d = job_to_dict(job)
        assert d["preset_name"] == "HEVC Transparent"

    def test_with_media_info(self):
        info = {"video_codec": "h264", "resolution_width": 1920}
        job = _make_job(media_info=info)
        d = job_to_dict(job)
        assert d["media_info"] == info

    def test_progress_percent_rounded(self):
        prog = TranscodeProgress(percent=33.3333)
        job = _make_job(progress=prog)
        d = job_to_dict(job)
        assert d["progress"]["percent"] == 33.3
