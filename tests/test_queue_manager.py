from unittest.mock import patch

import pytest

from core.queue_manager import Job, QueueManager


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
