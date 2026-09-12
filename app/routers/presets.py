from fastapi import APIRouter, HTTPException

from core.logger import log
from app.models.requests import (
    PresetCreate,
    PresetUpdate,
    AudioConfigIn,
    SubtitleConfigIn,
)
from app.models.responses import (
    PresetOut,
    AudioConfigOut,
    AudioTrackConfigOut,
    SubtitleConfigOut,
)
from core.yaml_store import (
    store,
    Preset,
    AudioConfig,
    AudioTrackConfig,
    SubtitleConfig,
    is_builtin_preset,
)
from core.queue_manager import queue_manager

router = APIRouter(prefix="/api/presets", tags=["presets"])


def _track_from_body(t) -> AudioTrackConfig | None:
    if t is None:
        return None
    return AudioTrackConfig(codec=t.codec, bitrate=t.bitrate)


def _audio_from_body(body_audio: AudioConfigIn | None) -> AudioConfig | None:
    if body_audio is None:
        return None
    return AudioConfig(
        stereo=_track_from_body(body_audio.stereo),
        surround=_track_from_body(body_audio.surround),
        languages=body_audio.languages,
        remove_commentary=body_audio.remove_commentary,
        add_stereo_downmix=body_audio.add_stereo_downmix,
        downmix_bitrate=body_audio.downmix_bitrate,
    )


def _track_to_out(t: AudioTrackConfig | None) -> AudioTrackConfigOut | None:
    if t is None:
        return None
    return AudioTrackConfigOut(codec=t.codec, bitrate=t.bitrate)


def _audio_to_out(audio: AudioConfig | None) -> AudioConfigOut | None:
    if audio is None:
        return None
    return AudioConfigOut(
        stereo=_track_to_out(audio.stereo),
        surround=_track_to_out(audio.surround),
        languages=audio.languages,
        remove_commentary=audio.remove_commentary,
        add_stereo_downmix=audio.add_stereo_downmix,
        downmix_bitrate=audio.downmix_bitrate,
    )


def _subtitle_from_body(body_sub: SubtitleConfigIn | None) -> SubtitleConfig | None:
    if body_sub is None:
        return None
    return SubtitleConfig(
        mode=body_sub.mode,
        languages=body_sub.languages,
        remove_commentary=body_sub.remove_commentary,
    )


def _subtitle_to_out(sub: SubtitleConfig | None) -> SubtitleConfigOut | None:
    if sub is None:
        return None
    return SubtitleConfigOut(
        mode=sub.mode,
        languages=sub.languages,
        remove_commentary=sub.remove_commentary,
    )


def _preset_out(name: str, p: Preset, builtin: bool = False) -> PresetOut:
    return PresetOut(
        name=name,
        ffmpeg_args=p.ffmpeg_args,
        output_container=p.output_container,
        description=p.description or None,
        audio=_audio_to_out(p.audio),
        subtitle=_subtitle_to_out(p.subtitle),
        resolution_cap=p.resolution_cap,
        rename_file=p.rename_file,
        ten_bit=p.ten_bit,
        is_builtin=builtin,
    )


@router.get("", response_model=list[PresetOut])
async def list_presets():
    presets = await store.get_presets()
    return [
        _preset_out(name, p, is_builtin_preset(name)) for name, p in presets.items()
    ]


@router.post("", response_model=PresetOut, status_code=201)
async def create_preset(body: PresetCreate):
    if is_builtin_preset(body.name):
        raise HTTPException(409, "A built-in preset with that name already exists")
    if await store.get_preset(body.name):
        raise HTTPException(409, "Preset already exists")
    preset = Preset(
        ffmpeg_args=body.ffmpeg_args,
        output_container=body.output_container,
        description=body.description or "",
        audio=_audio_from_body(body.audio),
        subtitle=_subtitle_from_body(body.subtitle),
        resolution_cap=body.resolution_cap,
        rename_file=body.rename_file,
        ten_bit=body.ten_bit,
    )
    await store.create_preset(body.name, preset)
    log.info("Preset created: '%s'", body.name)
    await queue_manager.re_evaluate_blocked()
    return _preset_out(body.name, preset)


@router.put("/{name}", response_model=PresetOut)
async def update_preset(name: str, body: PresetUpdate):
    if is_builtin_preset(name):
        raise HTTPException(403, "Built-in presets cannot be modified")
    if not await store.get_preset(name):
        raise HTTPException(404, "Preset not found")
    preset = Preset(
        ffmpeg_args=body.ffmpeg_args,
        output_container=body.output_container,
        description=body.description or "",
        audio=_audio_from_body(body.audio),
        subtitle=_subtitle_from_body(body.subtitle),
        resolution_cap=body.resolution_cap,
        rename_file=body.rename_file,
        ten_bit=body.ten_bit,
    )
    new_name = body.name if body.name and body.name != name else name
    if new_name != name:
        if is_builtin_preset(new_name):
            raise HTTPException(409, "A built-in preset with that name already exists")
        if await store.get_preset(new_name):
            raise HTTPException(409, "Preset with that name already exists")
        await store.rename_preset(name, new_name, preset)
        log.info("Preset renamed: '%s' -> '%s'", name, new_name)
    else:
        await store.update_preset(name, preset)
        log.info("Preset updated: '%s'", name)
    await queue_manager.re_evaluate_blocked()
    return _preset_out(new_name, preset)


@router.delete("/{name}", status_code=204)
async def delete_preset(name: str):
    if is_builtin_preset(name):
        raise HTTPException(403, "Built-in presets cannot be deleted")
    libraries = await store.get_libraries()
    in_use = [n for n, lib in libraries.items() if lib.preset == name]
    if in_use:
        raise HTTPException(
            409,
            f"Cannot delete this preset because it is assigned to: {', '.join(in_use)}. "
            "Reassign those libraries to a different preset first.",
        )
    if not await store.delete_preset(name):
        raise HTTPException(404, "Preset not found")
    log.info("Preset deleted: '%s'", name)
