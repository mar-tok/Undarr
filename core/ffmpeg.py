from __future__ import annotations

import asyncio
import re
import shlex
from collections.abc import Callable
from dataclasses import dataclass

import config
from core.logger import log
from core.codecs import ENCODER_TO_CODEC
from core.yaml_store import AudioConfig, AudioTrackConfig, SubtitleConfig

_CODEC_FAMILIES: dict[str, str] = {
    "hevc": "HEVC (H.265)",
    "h264": "H.264 (AVC)",
    "av1": "AV1",
    "vp9": "VP9",
}

# Containers that can hold each codec. Keeping the source container when it
# can't hold the target codec produces a broken file (AV1 in .avi).
_CODEC_CONTAINERS: dict[str, set[str]] = {
    "av1": {".mp4", ".mkv", ".webm"},
    "vp9": {".mkv", ".webm"},
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


_AUDIO_CODEC_ALIASES: dict[str, str] = {
    "libopus": "opus",
    "aac": "aac",
    "ac3": "ac3",
    "eac3": "eac3",
}


def strip_audio_flags(ffmpeg_args: str) -> str:
    result = re.sub(r"-c:a(?::\d+)?\s+\S+", "", ffmpeg_args)
    result = re.sub(r"-b:a(?::\d+)?\s+\S+", "", result)
    result = re.sub(r"-ac(?::a)?(?::\d+)?\s+\S+", "", result)
    result = re.sub(r"-c\s+copy", "", result)
    return re.sub(r"\s+", " ", result).strip()


@dataclass
class AudioBuildResult:
    map_args: list[str] | None
    codec_args: str


def build_audio_args(
    audio_config: AudioConfig,
    audio_streams: list[dict],
) -> AudioBuildResult:
    stereo = audio_config.stereo
    surround = audio_config.surround

    if stereo is None and surround is None:
        return AudioBuildResult(None, "-c:a copy")

    has_filtering = (
        audio_config.languages is not None
        or audio_config.remove_commentary
        or audio_config.add_stereo_downmix != "never"
    )
    both_copy = (stereo is None or stereo.codec == "copy") and (
        surround is None or surround.codec == "copy"
    )
    if both_copy and not has_filtering:
        return AudioBuildResult(None, "-c:a copy")

    if not audio_streams:
        return AudioBuildResult(None, "")

    allowed_langs = set(audio_config.languages) if audio_config.languages else None
    downmix_mode = audio_config.add_stereo_downmix

    do_downmix = downmix_mode == "always"
    if downmix_mode == "if_no_stereo":
        has_stereo_output = False
        for stream in audio_streams:
            if allowed_langs is not None:
                lang = stream.get("language", "und")
                if lang != "und" and lang not in allowed_langs:
                    continue
            if audio_config.remove_commentary and stream.get("is_commentary", False):
                continue
            if stream["channels"] <= 2:
                has_stereo_output = True
                break
        do_downmix = not has_stereo_output

    map_args: list[str] = []
    codec_parts: list[str] = []
    out_idx = 0

    for stream_idx, stream in enumerate(audio_streams):
        if allowed_langs is not None:
            lang = stream.get("language", "und")
            if lang != "und" and lang not in allowed_langs:
                continue

        if audio_config.remove_commentary and stream.get("is_commentary", False):
            continue

        is_surround = stream["channels"] > 2
        track_config = surround if is_surround else stereo

        if track_config is None:
            track_config = AudioTrackConfig(codec="copy")

        map_args.extend(["-map", f"0:a:{stream_idx}"])

        if track_config.codec == "copy":
            codec_parts.append(f"-c:a:{out_idx} copy")
        else:
            target_codec = _AUDIO_CODEC_ALIASES.get(
                track_config.codec, track_config.codec
            )
            target_bitrate_k = (
                _parse_bitrate_k(track_config.bitrate) if track_config.bitrate else None
            )
            if _audio_stream_matches(stream, target_codec, target_bitrate_k, None):
                codec_parts.append(f"-c:a:{out_idx} copy")
            else:
                codec_parts.append(f"-c:a:{out_idx} {track_config.codec}")
                if track_config.bitrate:
                    codec_parts.append(f"-b:a:{out_idx} {track_config.bitrate}")
        out_idx += 1

        if is_surround and do_downmix:
            map_args.extend(["-map", f"0:a:{stream_idx}"])
            codec_parts.append(f"-c:a:{out_idx} aac")
            if audio_config.downmix_bitrate:
                codec_parts.append(f"-b:a:{out_idx} {audio_config.downmix_bitrate}")
            codec_parts.append(f"-ac:a:{out_idx} 2")
            out_idx += 1

    return AudioBuildResult(map_args if map_args else None, " ".join(codec_parts))


def _audio_stream_matches(
    stream: dict,
    target_codec: str,
    target_bitrate_k: int | None,
    target_channels: int | None,
) -> bool:
    if stream["codec_name"] != target_codec:
        return False
    if target_channels is not None and stream["channels"] > target_channels:
        return False
    if target_bitrate_k is not None and stream["bit_rate"] is not None:
        stream_bitrate_k = stream["bit_rate"] // 1000
        if stream_bitrate_k > target_bitrate_k:
            return False
    return True


def _parse_bitrate_k(bitrate_str: str) -> int:
    s = bitrate_str.strip().lower()
    if s.endswith("k"):
        return int(s[:-1])
    return int(s)


def build_subtitle_args(
    subtitle_config: SubtitleConfig,
    subtitle_streams: list[dict],
) -> list[str] | None:
    mode = subtitle_config.mode

    if mode == "keep":
        return None

    if mode == "remove":
        return []

    allowed_langs = (
        set(subtitle_config.languages) if subtitle_config.languages else None
    )
    map_args: list[str] = []

    for stream_idx, stream in enumerate(subtitle_streams):
        if allowed_langs is not None:
            lang = stream.get("language", "und")
            if lang != "und" and lang not in allowed_langs:
                continue

        if subtitle_config.remove_commentary and stream.get("is_commentary", False):
            continue

        map_args.extend(["-map", f"0:s:{stream_idx}"])

    return map_args


def build_scale_filter(resolution_cap: int, source_height: int) -> str | None:
    if source_height <= resolution_cap:
        return None
    return f"scale=-2:{resolution_cap}"


@dataclass
class TranscodeProgress:
    out_time_us: int = 0
    percent: float = 0.0
    total_size: int = 0


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
    duration_us: int,
    on_progress: asyncio.Queue[TranscodeProgress] | None = None,
    on_proc: Callable[[asyncio.subprocess.Process], None] | None = None,
    audio_maps: list[str] | None = None,
    subtitle_maps: list[str] | None = None,
    scale_filter: str | None = None,
    process_priority: str = "normal",
) -> TranscodeResult:
    map_flags = ["-map", "0:V?"]
    if audio_maps is not None:
        map_flags.extend(audio_maps)
    else:
        map_flags.extend(["-map", "0:a?"])
    if subtitle_maps is not None:
        map_flags.extend(subtitle_maps)
    else:
        map_flags.extend(["-map", "0:s?"])

    vf_flags: list[str] = []
    if scale_filter:
        vf_flags = ["-vf", scale_filter]

    prefix: list[str] = []
    if process_priority == "low":
        prefix = ["nice", "-n", "10", "ionice", "-c", "2", "-n", "7"]
    elif process_priority == "lowest":
        prefix = ["nice", "-n", "19", "ionice", "-c", "3"]

    args = [
        *prefix,
        config.FFMPEG_BIN,
        "-y",
        "-nostats",
        "-progress",
        "pipe:1",
        "-i",
        input_path,
        *map_flags,
        *vf_flags,
        *shlex.split(ffmpeg_args),
        output_path,
    ]

    log.info("FFmpeg command: %s", " ".join(args))

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    if on_proc is not None:
        on_proc(proc)

    log_lines: list[str] = []
    progress = TranscodeProgress()

    async def read_stderr():
        assert proc.stderr is not None
        async for line in proc.stderr:
            log_lines.append(line.decode(errors="replace"))

    async def read_stdout():
        assert proc.stdout is not None
        frame: dict[str, str] = {}
        async for raw_line in proc.stdout:
            line = raw_line.decode(errors="replace").strip()
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip()
            frame[key] = val
            if key != "progress":
                continue
            # Time keys vary by ffmpeg version and can be "N/A", prefer the most precise one available
            for time_key in ("out_time_us", "out_time_ms", "out_time"):
                raw = frame.get(time_key, "")
                if not raw or raw == "N/A":
                    continue
                try:
                    if time_key == "out_time_us":
                        val = int(raw)
                    elif time_key == "out_time_ms":
                        val = int(raw) * 1000
                    elif ":" in raw:
                        h, m, s = raw.split(":")
                        val = int((int(h) * 3600 + int(m) * 60 + float(s)) * 1_000_000)
                    else:
                        continue
                except (ValueError, IndexError):
                    continue
                if val > 0:
                    progress.out_time_us = val
                    break
            try:
                progress.total_size = int(frame.get("total_size", "0"))
            except ValueError:
                pass
            if duration_us > 0:
                progress.percent = min(
                    (progress.out_time_us / duration_us) * 100.0, 100.0
                )
            if on_progress is not None:
                await on_progress.put(
                    TranscodeProgress(
                        out_time_us=progress.out_time_us,
                        percent=progress.percent,
                        total_size=progress.total_size,
                    )
                )
            frame.clear()

    await asyncio.gather(read_stdout(), read_stderr())
    await proc.wait()

    ffmpeg_log = "".join(log_lines)

    if proc.returncode == 0:
        return TranscodeResult(
            success=True,
            output_path=output_path,
            ffmpeg_log=ffmpeg_log,
        )
    else:
        err_lines = [l.strip() for l in log_lines if l.strip()]
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
            config.FFMPEG_BIN,
            "-hide_banner",
            "-encoders",
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
