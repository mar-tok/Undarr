from unittest.mock import patch, AsyncMock

import pytest

from core.ffprobe import get_video_duration_us, verify_output


def _probe(format_duration, streams):
    return {"format": {"duration": str(format_duration)}, "streams": streams}


def _video(**extra):
    return {"codec_type": "video", "codec_name": "h264", **extra}


# The container duration is 1464.08s and the video track is 1440.02s
WRONG_DURATION_SOURCE = _probe(
    1464.08,
    [
        _video(tags={"DURATION": "00:24:00.024000000"}),
        {"codec_type": "audio", "tags": {"DURATION": "00:24:00.085000000"}},
        {"codec_type": "subtitle", "duration": "1464.080000"},
    ],
)


class TestGetVideoDurationUs:
    def test_stream_duration_field(self):
        assert get_video_duration_us(_probe(10, [_video(duration="9.5")])) == 9_500_000

    def test_matroska_duration_tag(self):
        assert get_video_duration_us(WRONG_DURATION_SOURCE) == 1_440_024_000

    def test_language_suffixed_tag(self):
        probe = _probe(10, [_video(tags={"DURATION-eng": "00:00:05.500000000"})])
        assert get_video_duration_us(probe) == 5_500_000

    def test_attached_picture_skipped(self):
        probe = _probe(
            10,
            [
                _video(duration="1", disposition={"attached_pic": 1}),
                _video(duration="8"),
            ],
        )
        assert get_video_duration_us(probe) == 8_000_000

    def test_unparseable_tag(self):
        probe = _probe(10, [_video(tags={"DURATION": "soon"})])
        assert get_video_duration_us(probe) == 0

    def test_no_video_stream(self):
        assert get_video_duration_us(_probe(10, [{"codec_type": "audio"}])) == 0


def _patched(output_probe):
    return patch("core.ffprobe.probe_file", AsyncMock(return_value=output_probe))


class TestVerifyOutput:
    async def test_unreadable_output(self):
        with _patched(None):
            ok, reason = await verify_output("/out.mkv", WRONG_DURATION_SOURCE)
        assert ok is False
        assert "not readable" in reason

    async def test_no_video_stream(self):
        with _patched(_probe(5, [{"codec_type": "audio"}])):
            ok, reason = await verify_output("/out.mkv", WRONG_DURATION_SOURCE)
        assert ok is False
        assert "no video stream" in reason

    async def test_unknown_source_skips_duration_check(self):
        with _patched(_probe(5, [_video()])):
            ok, reason = await verify_output("/out.mkv", None)
        assert ok is True
        assert reason == ""

    async def test_matching_duration_passes(self):
        with _patched(_probe(1463.5, [_video()])):
            ok, reason = await verify_output("/out.mkv", WRONG_DURATION_SOURCE)
        assert ok is True

    async def test_wrong_container_duration_diagnosed(self):
        with _patched(_probe(1440.0, [_video()])):
            ok, reason = await verify_output("/out.mkv", WRONG_DURATION_SOURCE)
        assert ok is False
        assert reason == (
            "Output duration (1440.0s) differs from source (1464.1s). "
            "The output matches the source's video stream (1440.0s). "
            "The source container's duration is wrong, so the output is probably "
            "complete. A remux of the source can correct the container's duration."
        )

    async def test_truncation_diagnosed(self):
        with _patched(_probe(900.0, [_video()])):
            ok, reason = await verify_output("/out.mkv", WRONG_DURATION_SOURCE)
        assert ok is False
        assert "the encode stopped early" in reason

    async def test_truncation_without_stream_duration(self):
        source = _probe(100, [_video()])
        with _patched(_probe(40.0, [_video()])):
            ok, reason = await verify_output("/out.mkv", source)
        assert ok is False
        assert "the encode stopped early" in reason

    async def test_longer_output_has_no_diagnosis(self):
        source = _probe(3, [_video(duration="3")])
        with _patched(_probe(10, [_video()])):
            ok, reason = await verify_output("/out.mkv", source)
        assert ok is False
        assert reason == "Output duration (10.0s) differs from source (3.0s)"
