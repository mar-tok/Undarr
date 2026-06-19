from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import config
from core.logger import log
from core.ffmpeg import detect_encoders

_SUFFIX_MAP: dict[str, tuple[str, str]] = {
    "_nvenc": ("nvenc", "NVIDIA NVENC"),
    "_qsv": ("qsv", "Intel QSV"),
    "_vaapi": ("vaapi", "VAAPI"),
    "_amf": ("amf", "AMD AMF"),
    "_videotoolbox": ("videotoolbox", "VideoToolbox"),
    "_v4l2m2m": ("v4l2m2m", "V4L2 M2M"),
}

_CPU_ENCODERS = {"libx264", "libx265", "libsvtav1", "libaom-av1", "libvpx-vp9"}


@dataclass
class Device:
    id: str
    name: str
    type: str  # "cpu" or "gpu"
    encoders: list[str] = field(default_factory=list)


_device_cache: list[Device] | None = None


def _classify_encoder(name: str) -> tuple[str, str, str]:
    """Returns (device_id, device_name, device_type)."""
    if name in _CPU_ENCODERS:
        return "cpu", "CPU", "cpu"
    for suffix, (dev_id, dev_name) in _SUFFIX_MAP.items():
        if name.endswith(suffix):
            return dev_id, dev_name, "gpu"
    return "cpu", "CPU", "cpu"


async def _probe_encoder(encoder: str, semaphore: asyncio.Semaphore) -> tuple[str, bool]:
    """Probe-encode a single frame to verify an encoder actually works."""
    async with semaphore:
        log.debug("Probing encoder: %s", encoder)
        try:
            proc = await asyncio.create_subprocess_exec(
                config.FFMPEG_BIN,
                "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "color=black:s=256x256:d=0.04",
                "-c:v", encoder,
                "-frames:v", "1",
                "-f", "null", "-",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=5.0)
            ok = proc.returncode == 0
        except asyncio.TimeoutError:
            log.warning("Probe timed out for encoder: %s", encoder)
            try:
                proc.kill()
                await proc.wait()
            except (ProcessLookupError, OSError):
                pass
            ok = False
        except Exception as e:
            log.warning("Probe failed for encoder %s: [%s] %s", encoder, type(e).__name__, e)
            ok = False
    return encoder, ok


async def detect_devices() -> list[Device]:
    """Detect available encoding devices. Results are cached for the process lifetime."""
    global _device_cache
    if _device_cache is not None:
        return _device_cache

    log.info("Detecting encoding devices...")

    encoder_map = await detect_encoders()
    all_encoders: list[str] = []
    for family_encoders in encoder_map.values():
        for enc in family_encoders:
            all_encoders.append(enc["name"])

    if not all_encoders:
        log.warning("No video encoders found in FFmpeg")
        _device_cache = [Device(id="cpu", name="CPU", type="cpu")]
        return _device_cache

    candidates: list[str] = []
    for enc_name in all_encoders:
        _, _, dev_type = _classify_encoder(enc_name)
        if dev_type == "cpu" and enc_name not in _CPU_ENCODERS:
            continue
        candidates.append(enc_name)

    semaphore = asyncio.Semaphore(4)
    results = await asyncio.gather(
        *[_probe_encoder(enc, semaphore) for enc in candidates],
        return_exceptions=True,
    )

    verified: dict[str, list[str]] = {}
    device_meta: dict[str, tuple[str, str]] = {}

    for result in results:
        if isinstance(result, Exception):
            continue
        enc_name, ok = result
        if not ok:
            log.info("Encoder not available: %s", enc_name)
            continue
        dev_id, dev_name, dev_type = _classify_encoder(enc_name)
        verified.setdefault(dev_id, []).append(enc_name)
        device_meta[dev_id] = (dev_name, dev_type)
        log.info("Verified encoder: %s (%s)", enc_name, dev_name)

    devices: list[Device] = []
    if "cpu" in verified:
        devices.append(Device(
            id="cpu", name="CPU", type="cpu",
            encoders=sorted(verified["cpu"]),
        ))
    else:
        devices.append(Device(id="cpu", name="CPU", type="cpu"))

    for dev_id in sorted(verified):
        if dev_id == "cpu":
            continue
        name, dev_type = device_meta[dev_id]
        devices.append(Device(
            id=dev_id, name=name, type=dev_type,
            encoders=sorted(verified[dev_id]),
        ))

    log.info(
        "Device detection complete: %s",
        ", ".join(f"{d.name} ({len(d.encoders)} encoders)" for d in devices),
    )
    _device_cache = devices
    return devices


def encoder_to_device_id(encoder_name: str) -> str:
    if encoder_name in _CPU_ENCODERS:
        return "cpu"
    for suffix, (dev_id, _) in _SUFFIX_MAP.items():
        if encoder_name.endswith(suffix):
            return dev_id
    return "cpu"


def device_display_name(device_id: str) -> str:
    if _device_cache:
        for dev in _device_cache:
            if dev.id == device_id:
                return dev.name
    return device_id
