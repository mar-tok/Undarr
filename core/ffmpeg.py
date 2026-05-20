from __future__ import annotations

import asyncio
import shlex
from dataclasses import dataclass

import config
from core.logger import log


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
