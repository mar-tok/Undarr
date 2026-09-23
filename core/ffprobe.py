from __future__ import annotations

import asyncio
import json
from pathlib import Path

import config
from core.logger import log

VIDEO_EXTENSIONS = {
    ".mkv",
    ".mp4",
    ".avi",
    ".mov",
    ".wmv",
    ".flv",
    ".webm",
    ".m4v",
    ".mpg",
    ".mpeg",
    ".ts",
    ".m2ts",
    ".vob",
    ".ogv",
}


def is_video_file(path: str) -> bool:
    return Path(path).suffix.lower() in VIDEO_EXTENSIONS


async def _run_ffprobe(file_path: str, *args: str) -> dict | None:
    try:
        proc = await asyncio.create_subprocess_exec(
            config.FFPROBE_BIN,
            "-v",
            "quiet",
            "-print_format",
            "json",
            *args,
            file_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            log.warning("ffprobe timed out for %s", file_path)
            return None
        if proc.returncode != 0:
            log.warning("ffprobe failed for %s: %s", file_path, stderr.decode())
            return None
        return json.loads(stdout)
    except FileNotFoundError:
        log.error("ffprobe binary not found at %s", config.FFPROBE_BIN)
        return None
    except Exception as e:
        log.error("ffprobe error for %s: [%s] %s", file_path, type(e).__name__, e)
        return None


async def probe_file(file_path: str) -> dict | None:
    probe_data = await _run_ffprobe(file_path, "-show_format", "-show_streams")
    if probe_data is None:
        return None
    stream = _main_video_stream(probe_data)
    if (
        stream
        and stream.get("color_transfer") == "smpte2084"
        and "DOVI configuration record" not in _side_data_types(stream)
    ):
        # HDR10+ metadata is only reported on frames, never on the stream
        frames = await _run_ffprobe(
            file_path,
            "-select_streams",
            str(stream.get("index", 0)),
            # Some mp4 files need the explicit 0 start to return a frame
            "-read_intervals",
            "0%+#1",
            "-show_frames",
            "-show_entries",
            "frame=side_data_list",
        )
        if frames:
            stream["frame_side_data_list"] = [
                sd
                for f in frames.get("frames", [])
                for sd in f.get("side_data_list", [])
            ]
    return probe_data


def _main_video_stream(probe_data: dict) -> dict | None:
    for stream in probe_data.get("streams", []):
        if stream.get("codec_type") == "video" and not stream.get(
            "disposition", {}
        ).get("attached_pic", 0):
            return stream
    return None


def _side_data_types(stream: dict) -> set[str]:
    side_data = (stream.get("side_data_list") or []) + (
        stream.get("frame_side_data_list") or []
    )
    return {sd.get("side_data_type", "") for sd in side_data}


def classify_hdr(stream: dict) -> str:
    transfer = stream.get("color_transfer", "")
    side_types = _side_data_types(stream)

    # Dolby Vision profiles 8.2 and 8.4 have SDR and HLG base layers
    if "DOVI configuration record" in side_types:
        return "dolby_vision"
    if transfer == "smpte2084":
        if "HDR Dynamic Metadata SMPTE2094-40 (HDR10+)" in side_types:
            return "hdr10+"
        return "hdr10"
    if transfer == "arib-std-b67":
        return "hlg"
    return ""


def extract_media_info(probe_data: dict) -> dict:
    info: dict = {}

    for stream in probe_data.get("streams", []):
        codec_type = stream.get("codec_type")
        if (
            codec_type == "video"
            and "video_codec" not in info
            and not stream.get("disposition", {}).get("attached_pic", 0)
        ):
            info["video_codec"] = stream.get("codec_name", "")
            info["resolution_width"] = int(stream.get("width", 0))
            info["resolution_height"] = int(stream.get("height", 0))
            info["hdr_type"] = classify_hdr(stream)
            bit_rate = stream.get("bit_rate")
            if bit_rate:
                info["bitrate_kbps"] = int(bit_rate) // 1000
        elif codec_type == "audio" and "audio_codec" not in info:
            info["audio_codec"] = stream.get("codec_name", "")
            info["audio_channels"] = int(stream.get("channels", 0))

    fmt = probe_data.get("format", {})
    if "bitrate_kbps" not in info:
        bit_rate = fmt.get("bit_rate")
        if bit_rate:
            info["bitrate_kbps"] = int(bit_rate) // 1000

    duration = fmt.get("duration")
    if duration:
        info["duration_seconds"] = float(duration)

    size = fmt.get("size")
    if size:
        info["file_size_mb"] = int(size) / (1024 * 1024)

    return info


def extract_audio_streams(probe_data: dict) -> list[dict]:
    streams = []
    for s in probe_data.get("streams", []):
        if s.get("codec_type") != "audio":
            continue
        streams.append(
            {
                "index": s.get("index", 0),
                "codec_name": s.get("codec_name", ""),
                "channels": int(s.get("channels", 0)),
                "bit_rate": int(s["bit_rate"]) if s.get("bit_rate") else None,
                "language": s.get("tags", {}).get("language", "und"),
                "is_commentary": bool(s.get("disposition", {}).get("comment", 0)),
            }
        )
    return streams


def extract_subtitle_streams(probe_data: dict) -> list[dict]:
    streams = []
    for s in probe_data.get("streams", []):
        if s.get("codec_type") != "subtitle":
            continue
        streams.append(
            {
                "codec_name": s.get("codec_name", ""),
                "language": s.get("tags", {}).get("language", "und"),
                "is_commentary": bool(s.get("disposition", {}).get("comment", 0)),
            }
        )
    return streams


async def verify_output(
    output_path: str, source_probe: dict | None
) -> tuple[bool, str]:
    probe_data = await probe_file(output_path)
    if not probe_data:
        return False, "Output file is not readable by ffprobe"

    has_video = any(
        s.get("codec_type") == "video" for s in probe_data.get("streams", [])
    )
    if not has_video:
        return False, "Output file has no video stream"

    source_duration_us = get_duration_us(source_probe) if source_probe else 0
    if source_duration_us > 0:
        output_duration_us = get_duration_us(probe_data)
        if output_duration_us == 0:
            return False, "Could not determine output file duration"
        tolerance_us = max(1_000_000, int(source_duration_us * 0.005))
        diff = abs(output_duration_us - source_duration_us)
        if diff > tolerance_us:
            src_s = source_duration_us / 1_000_000
            out_s = output_duration_us / 1_000_000
            reason = (
                f"Output duration ({out_s:.1f}s) differs from source ({src_s:.1f}s)"
            )
            reason += _duration_diagnosis(
                source_probe, source_duration_us, output_duration_us, tolerance_us
            )
            return False, reason

    return True, ""


def _duration_diagnosis(
    source_probe: dict, source_us: int, output_us: int, tolerance_us: int
) -> str:
    stream_us = get_video_duration_us(source_probe)
    if stream_us and abs(output_us - stream_us) <= tolerance_us:
        return (
            f". The output matches the source's video stream "
            f"({stream_us / 1_000_000:.1f}s). The source container's duration is "
            "wrong, so the output is probably complete. A remux of the source "
            "can correct the container's duration."
        )
    if output_us < source_us and (not stream_us or output_us < stream_us):
        return (
            ". The output is shorter than the source, so the encode stopped early "
            "(an encoder error, a killed process, or a full disk)."
        )
    return ""


def get_duration_us(probe_data: dict) -> int:
    fmt = probe_data.get("format", {})
    duration = fmt.get("duration")
    if duration:
        return int(float(duration) * 1_000_000)
    for stream in probe_data.get("streams", []):
        duration = stream.get("duration")
        if duration:
            return int(float(duration) * 1_000_000)
    return 0


def get_video_duration_us(probe_data: dict) -> int:
    for stream in probe_data.get("streams", []):
        if stream.get("codec_type") != "video":
            continue
        if stream.get("disposition", {}).get("attached_pic", 0):
            continue
        duration = stream.get("duration")
        if duration:
            return int(float(duration) * 1_000_000)
        # Matroska reports a stream duration in a DURATION tag
        for key, value in stream.get("tags", {}).items():
            if key.upper().startswith("DURATION"):
                try:
                    h, m, sec = value.split(":")
                    return int((int(h) * 3600 + int(m) * 60 + float(sec)) * 1_000_000)
                except ValueError:
                    return 0
        return 0
    return 0
