from __future__ import annotations

from pydantic import BaseModel


class PresetOut(BaseModel):
    name: str
    ffmpeg_args: str
    output_container: str | None = None


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
