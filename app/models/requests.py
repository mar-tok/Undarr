from __future__ import annotations

from pydantic import BaseModel, field_validator


def _validate_name(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("Name cannot be empty")
    if len(v) > 200:
        raise ValueError("Name cannot exceed 200 characters")
    return v


class AudioTrackConfigIn(BaseModel):
    codec: str = "copy"
    bitrate: str | None = None


class AudioConfigIn(BaseModel):
    stereo: AudioTrackConfigIn | None = None
    surround: AudioTrackConfigIn | None = None
    languages: list[str] | None = None
    remove_commentary: bool = False
    add_stereo_downmix: str = "never"
    downmix_bitrate: str | None = None


class PresetCreate(BaseModel):
    name: str
    ffmpeg_args: str
    output_container: str | None = None
    audio: AudioConfigIn | None = None

    @field_validator("name")
    @classmethod
    def check_name(cls, v: str) -> str:
        return _validate_name(v)


class PresetUpdate(BaseModel):
    name: str | None = None
    ffmpeg_args: str
    output_container: str | None = None
    audio: AudioConfigIn | None = None

    @field_validator("name")
    @classmethod
    def check_name(cls, v: str | None) -> str | None:
        return _validate_name(v) if v is not None else None


class LibraryCreate(BaseModel):
    name: str
    paths: list[str]
    preset: str
    watch: bool = True
    scan_interval: int = 0
    scan_unit: str = "hours"

    @field_validator("name")
    @classmethod
    def check_name(cls, v: str) -> str:
        return _validate_name(v)


class LibraryUpdate(BaseModel):
    name: str | None = None
    paths: list[str]
    preset: str
    watch: bool = True
    scan_interval: int = 0
    scan_unit: str = "hours"

    @field_validator("name")
    @classmethod
    def check_name(cls, v: str | None) -> str | None:
        return _validate_name(v) if v is not None else None


class SettingsUpdate(BaseModel):
    cache_dir: str | None = None


class DeviceUpdate(BaseModel):
    max_jobs: int
