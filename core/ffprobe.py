from __future__ import annotations

import asyncio
import json

import config
from core.logger import log


async def probe_file(file_path: str) -> dict | None:
    try:
        proc = await asyncio.create_subprocess_exec(
            config.FFPROBE_BIN,
            "-v", "quiet",
            "-print_format", "json",
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
