from unittest.mock import patch, AsyncMock, MagicMock

import pytest

import core.ffmpeg as ffmpeg

SAMPLE_ENCODERS = b"""Encoders:
 V..... = Video
 A..... = Audio
 S..... = Subtitle
 ------
 V....D libx264              libx264 H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10 (codec h264)
 V....D libx265              libx265 H.265 / HEVC (codec hevc)
 V....D libsvtav1            SVT-AV1(Scalable Video Technology for AV1) encoder (codec av1)
 V....D hevc_nvenc           NVIDIA NVENC hevc encoder (codec hevc)
 V....D mpeg4                MPEG-4 part 2
 A....D aac                  AAC (Advanced Audio Coding)
 S..... srt                  SubRip subtitle
"""


def _mock_proc(stdout: bytes) -> MagicMock:
    proc = MagicMock()
    proc.communicate = AsyncMock(return_value=(stdout, b""))
    return proc


@pytest.fixture(autouse=True)
def clear_encoder_cache():
    ffmpeg._encoder_cache = None
    yield
    ffmpeg._encoder_cache = None


class TestCompatibleContainer:
    def test_compatible_extension_unchanged(self):
        assert ffmpeg.compatible_container("libx265", ".mkv") is None

    def test_incompatible_extension_switched(self):
        assert ffmpeg.compatible_container("libsvtav1", ".avi") == ".mp4"

    def test_uppercase_extension_unchanged(self):
        assert ffmpeg.compatible_container("libx265", ".MKV") is None


class TestDetectEncoders:
    async def test_groups_by_codec_family(self):
        with patch(
            "asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=_mock_proc(SAMPLE_ENCODERS)),
        ):
            result = await ffmpeg.detect_encoders()
        assert [e["name"] for e in result["h264"]] == ["libx264"]
        assert [e["name"] for e in result["hevc"]] == ["libx265", "hevc_nvenc"]
        assert [e["name"] for e in result["av1"]] == ["libsvtav1"]

    async def test_skips_non_video_and_unknown_codecs(self):
        with patch(
            "asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=_mock_proc(SAMPLE_ENCODERS)),
        ):
            result = await ffmpeg.detect_encoders()
        names = [e["name"] for encs in result.values() for e in encs]
        assert "aac" not in names
        assert "srt" not in names
        assert "mpeg4" not in names
        assert "=" not in names

    async def test_empty_families_dropped(self):
        with patch(
            "asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=_mock_proc(SAMPLE_ENCODERS)),
        ):
            result = await ffmpeg.detect_encoders()
        assert "vp9" not in result

    async def test_second_call_uses_cache(self):
        mock = AsyncMock(return_value=_mock_proc(SAMPLE_ENCODERS))
        with patch("asyncio.create_subprocess_exec", new=mock):
            first = await ffmpeg.detect_encoders()
            second = await ffmpeg.detect_encoders()
        assert first is second
        assert mock.call_count == 1

    async def test_probe_failure_returns_empty(self):
        with patch(
            "asyncio.create_subprocess_exec",
            new=AsyncMock(side_effect=FileNotFoundError("ffmpeg")),
        ):
            result = await ffmpeg.detect_encoders()
        assert result == {}
        assert ffmpeg._encoder_cache is None
