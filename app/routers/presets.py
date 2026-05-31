from fastapi import APIRouter, HTTPException

from core.logger import log
from app.models.requests import PresetCreate, PresetUpdate
from app.models.responses import PresetOut
from core.yaml_store import store, Preset

router = APIRouter(prefix="/api/presets", tags=["presets"])


def _preset_out(name: str, p: Preset) -> PresetOut:
    return PresetOut(
        name=name,
        ffmpeg_args=p.ffmpeg_args,
        output_container=p.output_container,
    )


@router.get("", response_model=list[PresetOut])
async def list_presets():
    presets = await store.get_presets()
    return [_preset_out(name, p) for name, p in presets.items()]


@router.post("", response_model=PresetOut, status_code=201)
async def create_preset(body: PresetCreate):
    if await store.get_preset(body.name):
        raise HTTPException(409, "Preset already exists")
    preset = Preset(
        ffmpeg_args=body.ffmpeg_args,
        output_container=body.output_container,
    )
    await store.create_preset(body.name, preset)
    log.info("Preset created: '%s'", body.name)
    return _preset_out(body.name, preset)


@router.put("/{name}", response_model=PresetOut)
async def update_preset(name: str, body: PresetUpdate):
    if not await store.get_preset(name):
        raise HTTPException(404, "Preset not found")
    preset = Preset(
        ffmpeg_args=body.ffmpeg_args,
        output_container=body.output_container,
    )
    new_name = body.name if body.name and body.name != name else name
    if new_name != name:
        if await store.get_preset(new_name):
            raise HTTPException(409, "Preset with that name already exists")
        await store.update_preset(new_name, preset)
        log.info("Preset renamed: '%s' -> '%s'", name, new_name)
    else:
        await store.update_preset(name, preset)
        log.info("Preset updated: '%s'", name)
    return _preset_out(new_name, preset)


@router.delete("/{name}", status_code=204)
async def delete_preset(name: str):
    if not await store.delete_preset(name):
        raise HTTPException(404, "Preset not found")
    log.info("Preset deleted: '%s'", name)
