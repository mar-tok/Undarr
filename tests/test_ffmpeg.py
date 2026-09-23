from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

import core.ffmpeg as ffmpeg
from core.ffprobe import probe_file, get_duration_us

FIXTURES = Path(__file__).parent / "fixtures"

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
    @pytest.mark.parametrize(
        "encoder, ext, expected",
        [
            ("av1_qsv", ".mov", ".mp4"),
            ("av1_nvenc", ".avi", ".mp4"),
            ("av1_qsv", ".mp4", None),
            ("libsvtav1", ".mkv", None),
            ("hevc_qsv", ".mov", None),
            ("libx265", ".mp4", None),
            ("libx265", ".avi", ".mp4"),
            ("libx264", ".avi", None),
            ("libx264", ".webm", ".mp4"),
            ("libvpx-vp9", ".mkv", None),
            ("libvpx-vp9", ".avi", ".mp4"),
            ("vp9_qsv", ".mp4", None),
            ("some_future_encoder", ".mov", None),
            ("av1_qsv", ".MOV", ".mp4"),
            ("av1_qsv", ".MP4", None),
        ],
    )
    def test_target_container(self, encoder, ext, expected):
        assert ffmpeg.compatible_container(encoder, ext) == expected


class TestTenBitPixFmt:
    def test_software_encoder(self):
        assert ffmpeg.ten_bit_pix_fmt("libx265") == "yuv420p10le"

    def test_hardware_encoder(self):
        assert ffmpeg.ten_bit_pix_fmt("hevc_nvenc") == "p010le"

    def test_h264_has_no_ten_bit_format(self):
        assert ffmpeg.ten_bit_pix_fmt("libx264") is None
        assert ffmpeg.ten_bit_pix_fmt("h264_nvenc") is None

    def test_unknown_encoder(self):
        assert ffmpeg.ten_bit_pix_fmt("some_future_encoder") is None


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

    async def test_marks_encoders_with_ten_bit_format(self):
        with patch(
            "asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=_mock_proc(SAMPLE_ENCODERS)),
        ):
            result = await ffmpeg.detect_encoders()
        ten_bit = {e["name"]: e["ten_bit"] for encs in result.values() for e in encs}
        assert ten_bit == {
            "libx264": False,
            "libx265": True,
            "libsvtav1": True,
            "hevc_nvenc": True,
        }

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


def _streams(probe, codec_type, attached=None):
    out = []
    for s in probe["streams"]:
        if s["codec_type"] != codec_type:
            continue
        if attached is not None and bool(s["disposition"]["attached_pic"]) != attached:
            continue
        out.append(s)
    return out


class TestTranscode:
    ARGS = "-c:a copy -c:s copy -c:v libx264 -crf 23 -preset ultrafast"

    async def test_attached_picture_dropped(self, tmp_path):
        source = str(FIXTURES / "edge_cases" / "attached_pic.mp4")
        probe = await probe_file(source)
        assert len(_streams(probe, "video", attached=True)) == 1

        output = str(tmp_path / "output.mp4")
        result = await ffmpeg.transcode(
            source, output, self.ARGS, get_duration_us(probe)
        )
        assert result.success, result.error_message

        out_probe = await probe_file(output)
        assert _streams(out_probe, "video", attached=True) == []
        assert len(_streams(out_probe, "video")) == 1
        assert len(_streams(out_probe, "audio")) == 1

    async def test_h264_into_mov(self, tmp_path):
        source = str(FIXTURES / "edge_cases" / "valid.mov")
        probe = await probe_file(source)
        output = str(tmp_path / "output.mov")
        result = await ffmpeg.transcode(
            source, output, self.ARGS, get_duration_us(probe)
        )
        assert result.success, result.error_message
        assert result.output_path == output
