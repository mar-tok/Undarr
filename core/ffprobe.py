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


async def probe_file(file_path: str) -> dict | None:
    try:
        proc = await asyncio.create_subprocess_exec(
            config.FFPROBE_BIN,
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
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


async def verify_output(output_path: str, source_duration_us: int) -> tuple[bool, str]:
    probe_data = await probe_file(output_path)
    if not probe_data:
        return False, "Output file is not readable by ffprobe"

    has_video = any(
        s.get("codec_type") == "video" for s in probe_data.get("streams", [])
    )
    if not has_video:
        return False, "Output file has no video stream"

    if source_duration_us > 0:
        output_duration_us = get_duration_us(probe_data)
        if output_duration_us == 0:
            return False, "Could not determine output file duration"
        tolerance_us = max(1_000_000, int(source_duration_us * 0.005))
        diff = abs(output_duration_us - source_duration_us)
        if diff > tolerance_us:
            src_s = source_duration_us / 1_000_000
            out_s = output_duration_us / 1_000_000
            return (
                False,
                f"Output duration ({out_s:.1f}s) differs from source ({src_s:.1f}s)",
            )

    return True, ""


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
