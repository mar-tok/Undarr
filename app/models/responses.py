from __future__ import annotations

from pydantic import BaseModel


class SkipConditionOut(BaseModel):
    field: str
    operator: str
    value: str | int | float


class SkipRuleOut(BaseModel):
    conditions: list[SkipConditionOut]


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
    resolution_cap: int | None = None
    is_builtin: bool = False


class LibraryOut(BaseModel):
    name: str
    paths: list[str]
    preset: str
    watch: bool
    skip_rules: list[SkipRuleOut]
    path_patterns: list[str] = []
    scan_interval: int = 0
    scan_unit: str = "hours"
    new_file_delay: int = 0
    new_file_delay_unit: str = "minutes"
    paused: bool = False


class SettingsOut(BaseModel):
    cache_dir: str
    schedule_enabled: bool
    schedule: dict[str, list[bool]]
    process_priority: str
    max_size_ratio: float
    queue_order: str
    server_timezone: str
    server_utc_offset: int


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


class PreviewFileOut(BaseModel):
    path: str
    size_bytes: int
    video_codec: str
    resolution: str
    bitrate_kbps: int


class PreviewSkippedOut(BaseModel):
    path: str
    size_bytes: int
    reason: str


class PreviewSummaryOut(BaseModel):
    total_files: int
    would_queue: int
    would_queue_bytes: int
    already_processed: int
    skipped: int
    too_new: int


class PreviewOut(BaseModel):
    summary: PreviewSummaryOut
    queue: list[PreviewFileOut]
    skipped: list[PreviewSkippedOut]


class SearchResultOut(BaseModel):
    id: str
    file_path: str
    library_name: str
    status: str
    old_size_bytes: int
    new_size_bytes: int | None = None
    date: str | None = None
    source: str
