from __future__ import annotations

from pydantic import BaseModel


class AudioTrackConfigOut(BaseModel):
    codec: str
    bitrate: str | None = None


class AudioConfigOut(BaseModel):
    stereo: AudioTrackConfigOut | None = None
    surround: AudioTrackConfigOut | None = None
    languages: list[str] | None = None
    remove_commentary: bool = False
    add_stereo_downmix: str = "never"
    downmix_bitrate: str | None = None


class SubtitleConfigOut(BaseModel):
    mode: str = "keep"
    languages: list[str] | None = None
    remove_commentary: bool = False


class PresetOut(BaseModel):
    name: str
    ffmpeg_args: str
    output_container: str | None = None
    audio: AudioConfigOut | None = None
    subtitle: SubtitleConfigOut | None = None


class LibraryOut(BaseModel):
    name: str
    paths: list[str]
    preset: str
    watch: bool
    scan_interval: int = 0
    scan_unit: str = "hours"


class HistoryOut(BaseModel):
    id: str
    library_name: str
    file_path: str
    status: str
    old_size_bytes: int
    new_size_bytes: int | None = None
    started_at: str
    finished_at: str
    duration_seconds: float
    error_message: str | None = None
    preset_name: str = ""
    device_name: str = ""


class SearchResultOut(BaseModel):
    id: str
    file_path: str
    library_name: str
    status: str
    old_size_bytes: int
    new_size_bytes: int | None = None
    date: str | None = None
    source: str
