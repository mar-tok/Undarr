import pytest

from core.queue_manager import QueueManager


@pytest.fixture
def qm():
    """Fresh QueueManager."""
    manager = QueueManager()
    manager._device_limits = {"cpu": 2}
    manager._device_active = {"cpu": 0}
    return manager


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
