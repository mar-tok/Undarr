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
    description: str | None = None
    audio: AudioConfigOut | None = None
    subtitle: SubtitleConfigOut | None = None
    resolution_cap: int | None = None
    rename_file: bool = False
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
    description: str | None = None
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
    not_scanned: int


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


class StatsTotals(BaseModel):
    completed: int
    failed: int
    skipped: int
    space_saved_bytes: int
    original_bytes: int
    processing_seconds: float
    eta_seconds: float | None = None


class StatsDaily(BaseModel):
    date: str
    completed: int
    failed: int
    space_saved_bytes: int


class StatsLibrary(BaseModel):
    library: str
    completed: int
    failed: int
    processed: int
    skipped: int
    space_saved_bytes: int
    original_bytes: int


class StatsTopSaving(BaseModel):
    file_path: str
    old_size_bytes: int
    new_size_bytes: int
    library_name: str


class StatsDevice(BaseModel):
    device: str
    completed: int
    processing_seconds: float
    avg_duration_seconds: float


class StorageEntry(BaseModel):
    name: str
    path: str
    is_dir: bool
    total_size: int
    file_count: int
    codecs: dict[str, int]
    space_saved: int


class StorageTreeOut(BaseModel):
    library: str
    path: str | None
    parent: str | None
    total_size: int
    total_files: int
    total_saved: int
    entries: list[StorageEntry]


class LibraryFileOut(BaseModel):
    file_path: str
    file_size: int
    video_codec: str
    resolution_h: int
    bitrate_kbps: int = 0
    container: str = ""
    audio_codec: str = ""
    audio_channels: int = 0
    duration: float = 0
    hdr_type: str = ""
    processed: int = 0


class LibraryFilesPageOut(BaseModel):
    files: list[LibraryFileOut]
    total: int


class LibraryFileFiltersOut(BaseModel):
    codecs: list[str]
    containers: list[str]


class DuplicateFileOut(BaseModel):
    file_path: str
    library_name: str
    video_codec: str
    resolution_h: int
    audio_codec: str
    container: str
    duration: float


class DuplicateGroupOut(BaseModel):
    file_size: int
    full_hash: str
    files: list[DuplicateFileOut]


class DuplicateScanOut(BaseModel):
    groups: list[DuplicateGroupOut]
    total_duplicate_size: int
    total_groups: int
    not_hashed: int = 0


class StatsOut(BaseModel):
    totals: StatsTotals
    daily: list[StatsDaily]
    by_library: list[StatsLibrary]
    top_savings: list[StatsTopSaving]
    by_device: list[StatsDevice]
    composition: dict[str, dict[str, int]]
    file_counts: dict[str, int]
    processed_counts: dict[str, int]
    library_sizes: dict[str, int]
