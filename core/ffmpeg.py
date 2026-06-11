from __future__ import annotations

import asyncio
import re
import shlex
from dataclasses import dataclass

import config
from core.logger import log
from core.codecs import ENCODER_TO_CODEC

_CODEC_FAMILIES: dict[str, str] = {
    "hevc": "HEVC (H.265)",
    "h264": "H.264 (AVC)",
    "av1": "AV1",
    "vp9": "VP9",
}

# Containers that can hold each codec. Keeping the source container when it
# can't hold the target codec produces a broken file (AV1 in .avi).
_CODEC_CONTAINERS: dict[str, set[str]] = {
    "av1":  {".mp4", ".mkv", ".webm"},
    "vp9":  {".mkv", ".webm"},
    "hevc": {".mp4", ".mkv", ".mov", ".ts"},
    "h264": {".mp4", ".mkv", ".mov", ".ts", ".avi"},
}


def compatible_container(encoder: str, source_ext: str) -> str | None:
    codec = ENCODER_TO_CODEC.get(encoder)
    if not codec:
        return None
    allowed = _CODEC_CONTAINERS.get(codec)
    if not allowed:
        return None
    if source_ext in allowed:
        return None
    return ".mp4"


@dataclass
class TranscodeResult:
    success: bool
    output_path: str
    ffmpeg_log: str
    error_message: str | None = None


async def transcode(
    input_path: str,
    output_path: str,
    ffmpeg_args: str,
) -> TranscodeResult:
    # TODO: Needs progress parsing, duration tracking
    args = [
        config.FFMPEG_BIN,
        "-y",
        "-i", input_path,
        "-map", "0",
        *shlex.split(ffmpeg_args),
        output_path,
    ]

    log.info("FFmpeg command: %s", " ".join(args))

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await proc.communicate()
    ffmpeg_log = stderr.decode(errors="replace")

    if proc.returncode == 0:
        return TranscodeResult(
            success=True,
            output_path=output_path,
            ffmpeg_log=ffmpeg_log,
        )
    else:
        err_lines = [l.strip() for l in ffmpeg_log.splitlines() if l.strip()]
        tail = "\n".join(err_lines[-6:]) if err_lines else "(no stderr)"
        error_msg = f"FFmpeg exited with code {proc.returncode}\n{tail}"
        log.warning("FFmpeg stderr tail:\n%s", tail)
        return TranscodeResult(
            success=False,
            output_path=output_path,
            ffmpeg_log=ffmpeg_log,
            error_message=error_msg,
        )


_encoder_cache: dict[str, list[dict]] | None = None


async def detect_encoders() -> dict[str, list[dict]]:
    global _encoder_cache
    if _encoder_cache is not None:
        return _encoder_cache

    try:
        proc = await asyncio.create_subprocess_exec(
            config.FFMPEG_BIN, "-hide_banner", "-encoders",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
    except Exception as e:
        log.error("Failed to detect encoders: [%s] %s", type(e).__name__, e)
        return {}

    result: dict[str, list[dict]] = {k: [] for k in _CODEC_FAMILIES}
    codec_re = re.compile(r"\(codec (\w+)\)")

    for raw in stdout.decode(errors="replace").splitlines():
        line = raw.strip()
        if not line or not line.startswith("V"):
            continue
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        name = parts[1]
        desc = parts[2]

        m = codec_re.search(desc)
        codec = m.group(1) if m else name.split("_")[0]

        if codec in result:
            result[codec].append({"name": name, "description": desc})

    result = {k: v for k, v in result.items() if v}
    _encoder_cache = result
    return result
