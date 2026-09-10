import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from core.queue_manager import job_to_dict, Job, JobStatus, QueueManager
from core.ffmpeg import TranscodeProgress
from core.yaml_store import Library, Preset


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

    async def test_no_dispatch_on_wake_after_pause(self, qm):
        started = []

        async def fake_run(job):
            started.append(job.id)

        qm._run_job = fake_run
        task = asyncio.create_task(qm._dispatcher())
        await asyncio.sleep(0.01)
        await qm.pause()
        qm._pending.append(_make_job(device="cpu"))
        qm._dispatch_event.set()
        await asyncio.sleep(0.01)
        try:
            assert started == []
            assert len(qm._pending) == 1
            await qm.resume()
            await asyncio.sleep(0.01)
            assert started == ["abc123"]
        finally:
            task.cancel()


# Stall notification


class TestStall:
    @pytest.fixture
    def fired(self):
        with patch("core.queue_manager.fire_event", AsyncMock()) as fire:
            yield fire

    async def _wake(self, qm):
        qm._dispatch_event.set()
        await asyncio.sleep(0.01)

    async def test_fires_once_while_blocked(self, qm, fired):
        qm._run_job = AsyncMock()
        qm._device_limits = {"cpu": 0}
        task = asyncio.create_task(qm._dispatcher())
        qm._pending.append(_make_job(device="cpu"))
        try:
            await self._wake(qm)
            await self._wake(qm)
            assert fired.call_count == 1
            event, data = fired.call_args.args
            assert event == "queue_stalled"
            assert data == {
                "pending_count": 1,
                "reasons": ["Device 'cpu' is disabled"],
            }
        finally:
            task.cancel()

    async def test_reasons_cover_paused_and_unavailable(self, qm, fired):
        qm._run_job = AsyncMock()
        qm._paused_libraries.add("movies")
        qm._unavailable_libraries["shows"] = "/media/shows"
        task = asyncio.create_task(qm._dispatcher())
        qm._pending.append(_make_job(id="a", library_name="movies", device="cpu"))
        qm._pending.append(_make_job(id="b", library_name="shows", device="cpu"))
        try:
            await self._wake(qm)
            assert fired.call_args.args[1]["reasons"] == [
                "Library 'movies' is paused",
                "Library 'shows' is unavailable",
            ]
        finally:
            task.cancel()

    async def test_silent_while_a_job_is_active(self, qm, fired):
        qm._run_job = AsyncMock()
        qm._active["other"] = _make_job(id="other")
        qm._paused_libraries.add("movies")
        task = asyncio.create_task(qm._dispatcher())
        qm._pending.append(_make_job(device="cpu"))
        try:
            await self._wake(qm)
            assert not fired.called
        finally:
            task.cancel()

    async def test_fires_again_after_a_dispatch(self, qm, fired):
        qm._run_job = AsyncMock()
        qm._paused_libraries.add("movies")
        task = asyncio.create_task(qm._dispatcher())
        qm._pending.append(_make_job(id="blocked", device="cpu"))
        try:
            await self._wake(qm)
            qm._pending.append(_make_job(id="free", library_name="shows", device="cpu"))
            await self._wake(qm)
            qm._active.clear()
            await self._wake(qm)
            assert fired.call_count == 2
        finally:
            task.cancel()

    async def test_fires_again_after_the_queue_empties(self, qm, fired):
        qm._run_job = AsyncMock()
        qm._paused_libraries.add("movies")
        task = asyncio.create_task(qm._dispatcher())
        qm._pending.append(_make_job(device="cpu"))
        try:
            await self._wake(qm)
            qm._pending[0].status = JobStatus.CANCELLED
            await self._wake(qm)
            qm._pending.append(_make_job(id="again", device="cpu"))
            await self._wake(qm)
            assert fired.call_count == 2
        finally:
            task.cancel()


# Library availability


class TestUnavailable:
    async def test_mark_unavailable(self, qm):
        await qm.mark_unavailable("movies", "All paths missing: /media")
        assert qm.unavailable_libraries == {"movies": "All paths missing: /media"}

    async def test_mark_unavailable_broadcasts(self, qm):
        sub = qm.subscribe()
        await qm.mark_unavailable("movies", "gone")
        msg = sub.get_nowait()
        assert "library_unavailable" in msg

    async def test_mark_available_wakes_dispatcher(self, qm):
        await qm.mark_unavailable("movies", "gone")
        qm._dispatch_event.clear()
        await qm.mark_available("movies")
        assert "movies" not in qm.unavailable_libraries
        assert qm._dispatch_event.is_set()

    async def test_on_unavailable_tracks_missing_paths(self, qm):
        await qm.on_unavailable("movies", False, "", ["/media/two"])
        assert qm.missing_paths_by_library == {"movies": ["/media/two"]}
        await qm.on_unavailable("movies", False, "", [])
        assert qm.missing_paths_by_library == {}

    async def test_rename_unavailable_library(self, qm):
        await qm.on_unavailable("movies", True, "gone", ["/media"])
        await qm.rename_unavailable_library("movies", "films")
        assert qm.unavailable_libraries == {"films": "gone"}
        assert qm.missing_paths_by_library == {"films": ["/media"]}

    async def test_clear_unavailable_library(self, qm):
        await qm.on_unavailable("movies", True, "gone", ["/media"])
        await qm.clear_unavailable_library("movies")
        assert qm.unavailable_libraries == {}
        assert qm.missing_paths_by_library == {}


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
        assert "is_retry" not in d

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

    def test_is_retry(self):
        job = _make_job(is_retry=True)
        d = job_to_dict(job)
        assert d["is_retry"] is True

    def test_is_retry_false_excluded(self):
        job = _make_job(is_retry=False)
        d = job_to_dict(job)
        assert "is_retry" not in d

    def test_progress_percent_rounded(self):
        prog = TranscodeProgress(percent=33.3333)
        job = _make_job(progress=prog)
        d = job_to_dict(job)
        assert d["progress"]["percent"] == 33.3


# Cancel


class TestCancel:
    async def test_cancel_pending(self, qm):
        job = _make_job(id="j1")
        qm._pending.append(job)
        qm._known_paths.add(job.file_path)
        result = await qm.cancel("j1")
        assert result is True
        assert len(qm.pending_jobs) == 0
        assert job.file_path not in qm._known_paths
        assert job.status == JobStatus.CANCELLED

    async def test_cancel_blocked(self, qm):
        job = _make_job(id="j1", status=JobStatus.BLOCKED)
        qm._blocked.append(job)
        qm._known_paths.add(job.file_path)
        result = await qm.cancel("j1")
        assert result is True
        assert len(qm.blocked_jobs) == 0
        assert job.status == JobStatus.CANCELLED

    async def test_cancel_active(self, qm):
        job = _make_job(id="j1", status=JobStatus.ACTIVE)
        qm._active["j1"] = job
        mock_proc = MagicMock()
        qm._active_procs["j1"] = mock_proc
        result = await qm.cancel("j1")
        assert result is True
        assert job.status == JobStatus.CANCELLED
        assert (
            "j1" in qm._active
        )  # removal happens in _run_job's finally block, not cancel
        mock_proc.kill.assert_called_once()

    async def test_cancel_active_no_proc(self, qm):
        job = _make_job(id="j1", status=JobStatus.ACTIVE)
        qm._active["j1"] = job
        result = await qm.cancel("j1")
        assert result is True
        assert job.status == JobStatus.CANCELLED

    async def test_cancel_nonexistent(self, qm):
        result = await qm.cancel("nonexistent")
        assert result is False

    async def test_cancel_broadcasts_event(self, qm):
        job = _make_job(id="j1")
        qm._pending.append(job)
        qm._known_paths.add(job.file_path)
        sub = qm.subscribe()
        await qm.cancel("j1")
        msg = sub.get_nowait()
        assert "job_cancelled" in msg


# Re-evaluate blocked


class TestReEvaluateBlocked:
    async def test_unblocks_when_preset_available(self, qm):
        job = _make_job(
            id="j1", status=JobStatus.BLOCKED, block_reason="Preset 'HEVC' not found"
        )
        qm._blocked.append(job)
        qm._known_paths.add(job.file_path)
        with patch("core.queue_manager.store") as mock_store:
            mock_store.get_library = AsyncMock(
                return_value=Library(paths=["/media"], preset="HEVC")
            )
            mock_store.get_preset = AsyncMock(
                return_value=Preset(ffmpeg_args="-c:v libx265 -crf 20")
            )
            mock_store.config.settings.queue_order = "fifo"
            await qm.re_evaluate_blocked()
        assert len(qm.blocked_jobs) == 0
        assert len(qm.pending_jobs) == 1
        assert job.status == JobStatus.PENDING
        assert job.block_reason is None

    async def test_stays_blocked_when_preset_missing(self, qm):
        job = _make_job(
            id="j1", status=JobStatus.BLOCKED, block_reason="Preset not found"
        )
        qm._blocked.append(job)
        with patch("core.queue_manager.store") as mock_store:
            mock_store.get_library = AsyncMock(
                return_value=Library(paths=["/media"], preset="Missing")
            )
            mock_store.get_preset = AsyncMock(return_value=None)
            await qm.re_evaluate_blocked()
        assert len(qm.blocked_jobs) == 1
        assert job.status == JobStatus.BLOCKED

    async def test_cancelled_blocked_jobs_removed(self, qm):
        job = _make_job(id="j1", status=JobStatus.CANCELLED)
        qm._blocked.append(job)
        qm._known_paths.add(job.file_path)
        with patch("core.queue_manager.store") as mock_store:
            await qm.re_evaluate_blocked()
        assert len(qm.blocked_jobs) == 0
        assert job.file_path not in qm._known_paths

    async def test_unblock_broadcasts_event(self, qm):
        job = _make_job(id="j1", status=JobStatus.BLOCKED, block_reason="test")
        qm._blocked.append(job)
        qm._known_paths.add(job.file_path)
        sub = qm.subscribe()
        with patch("core.queue_manager.store") as mock_store:
            mock_store.get_library = AsyncMock(
                return_value=Library(paths=["/media"], preset="HEVC")
            )
            mock_store.get_preset = AsyncMock(
                return_value=Preset(ffmpeg_args="-c:v libx265 -crf 20")
            )
            mock_store.config.settings.queue_order = "fifo"
            await qm.re_evaluate_blocked()
        msg = sub.get_nowait()
        assert "job_unblocked" in msg
