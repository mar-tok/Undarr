from __future__ import annotations

from pydantic import BaseModel, ValidationInfo, field_validator, model_validator

from core.skip_rules import SKIP_FIELDS, SKIP_OPERATORS
from core.yaml_store import TIME_UNITS


def _validate_name(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("Name cannot be empty")
    if len(v) > 200:
        raise ValueError("Name cannot exceed 200 characters")
    if "/" in v:
        raise ValueError("Name cannot contain /")
    return v


def _validate_paths(paths: list[str]) -> list[str]:
    if not paths:
        raise ValueError("At least one path is required")
    for p in paths:
        if not p.startswith("/"):
            raise ValueError(f"Paths must be absolute: {p}")
    return paths


def _validate_unit(v: str, info: ValidationInfo) -> str:
    if v not in TIME_UNITS:
        raise ValueError(f"{info.field_name} must be one of: {', '.join(TIME_UNITS)}")
    return v


def _validate_non_negative(v: int, info: ValidationInfo) -> int:
    if v < 0:
        raise ValueError(f"{info.field_name} must be 0 or greater")
    return v


def _validate_resolution_cap(v: int | None) -> int | None:
    if v is not None and v <= 0:
        raise ValueError("resolution_cap must be greater than 0")
    return v


class SkipConditionIn(BaseModel):
    field: str
    operator: str
    value: str | int | float

    @field_validator("field")
    @classmethod
    def check_field(cls, v: str) -> str:
        if v not in SKIP_FIELDS:
            raise ValueError(f"field must be one of: {', '.join(SKIP_FIELDS)}")
        return v

    @field_validator("operator")
    @classmethod
    def check_operator(cls, v: str) -> str:
        if v not in SKIP_OPERATORS:
            raise ValueError(f"operator must be one of: {', '.join(SKIP_OPERATORS)}")
        return v

    @model_validator(mode="after")
    def check_value(self):
        if self.operator in ("less_than", "greater_than"):
            try:
                float(self.value)
            except (TypeError, ValueError):
                raise ValueError(
                    "value must be a number for less_than and greater_than"
                )
        elif self.operator == "contains" and not str(self.value).strip():
            raise ValueError("value is required for contains")
        return self


class SkipRuleIn(BaseModel):
    conditions: list[SkipConditionIn]


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


class SubtitleConfigIn(BaseModel):
    mode: str = "keep"
    languages: list[str] | None = None
    remove_commentary: bool = False


class PresetCreate(BaseModel):
    name: str
    ffmpeg_args: str
    output_container: str | None = None
    description: str | None = None
    audio: AudioConfigIn | None = None
    subtitle: SubtitleConfigIn | None = None
    resolution_cap: int | None = None
    rename_file: bool = False
    ten_bit: bool = False

    @field_validator("name")
    @classmethod
    def check_name(cls, v: str) -> str:
        return _validate_name(v)

    @field_validator("resolution_cap")
    @classmethod
    def check_resolution_cap(cls, v: int | None) -> int | None:
        return _validate_resolution_cap(v)


class PresetUpdate(BaseModel):
    name: str | None = None
    ffmpeg_args: str
    output_container: str | None = None
    description: str | None = None
    audio: AudioConfigIn | None = None
    subtitle: SubtitleConfigIn | None = None
    resolution_cap: int | None = None
    rename_file: bool = False
    ten_bit: bool = False

    @field_validator("name")
    @classmethod
    def check_name(cls, v: str | None) -> str | None:
        return _validate_name(v) if v is not None else None

    @field_validator("resolution_cap")
    @classmethod
    def check_resolution_cap(cls, v: int | None) -> int | None:
        return _validate_resolution_cap(v)


class LibraryCreate(BaseModel):
    name: str
    paths: list[str]
    preset: str
    watch: bool = True
    skip_rules: list[SkipRuleIn] = []
    path_patterns: list[str] = []
    scan_interval: int = 0
    scan_unit: str = "hours"
    description: str | None = None
    mark_existing_processed: bool = False
    new_file_delay: int = 0
    new_file_delay_unit: str = "minutes"

    @field_validator("name")
    @classmethod
    def check_name(cls, v: str) -> str:
        return _validate_name(v)

    @field_validator("paths")
    @classmethod
    def check_paths(cls, v: list[str]) -> list[str]:
        return _validate_paths(v)

    @field_validator("scan_unit", "new_file_delay_unit")
    @classmethod
    def check_unit(cls, v: str, info: ValidationInfo) -> str:
        return _validate_unit(v, info)

    @field_validator("scan_interval", "new_file_delay")
    @classmethod
    def check_non_negative(cls, v: int, info: ValidationInfo) -> int:
        return _validate_non_negative(v, info)


class LibraryUpdate(BaseModel):
    name: str | None = None
    paths: list[str]
    preset: str
    watch: bool = True
    skip_rules: list[SkipRuleIn] = []
    path_patterns: list[str] = []
    scan_interval: int = 0
    scan_unit: str = "hours"
    description: str | None = None
    new_file_delay: int = 0
    new_file_delay_unit: str = "minutes"

    @field_validator("name")
    @classmethod
    def check_name(cls, v: str | None) -> str | None:
        return _validate_name(v) if v is not None else None

    @field_validator("paths")
    @classmethod
    def check_paths(cls, v: list[str]) -> list[str]:
        return _validate_paths(v)

    @field_validator("scan_unit", "new_file_delay_unit")
    @classmethod
    def check_unit(cls, v: str, info: ValidationInfo) -> str:
        return _validate_unit(v, info)

    @field_validator("scan_interval", "new_file_delay")
    @classmethod
    def check_non_negative(cls, v: int, info: ValidationInfo) -> int:
        return _validate_non_negative(v, info)


class PreviewRequest(BaseModel):
    name: str = ""
    paths: list[str]
    skip_rules: list[SkipRuleIn] = []
    path_patterns: list[str] = []
    new_file_delay: int = 0
    new_file_delay_unit: str = "minutes"

    @field_validator("paths")
    @classmethod
    def check_paths(cls, v: list[str]) -> list[str]:
        return _validate_paths(v)

    @field_validator("new_file_delay_unit")
    @classmethod
    def check_unit(cls, v: str, info: ValidationInfo) -> str:
        return _validate_unit(v, info)

    @field_validator("new_file_delay")
    @classmethod
    def check_non_negative(cls, v: int, info: ValidationInfo) -> int:
        return _validate_non_negative(v, info)


class SettingsUpdate(BaseModel):
    cache_dir: str | None = None
    schedule_enabled: bool | None = None
    schedule: dict[str, list[bool]] | None = None
    process_priority: str | None = None
    max_size_ratio: float | None = None
    queue_order: str | None = None
    allow_duplicate_deletion: bool | None = None


class DeviceUpdate(BaseModel):
    max_jobs: int


class PauseRequest(BaseModel):
    paused: bool


class RetryRequest(BaseModel):
    ids: list[str]


class DismissRequest(BaseModel):
    ids: list[str]


class RequeueRequest(BaseModel):
    ids: list[str]


class SkipRequest(BaseModel):
    ids: list[str]


class CancelBatchRequest(BaseModel):
    ids: list[str]


class EnqueuePathsRequest(BaseModel):
    library: str
    paths: list[str]


class WebhookIn(BaseModel):
    url: str
    template: str = "discord"
    events: list[str] = []
    enabled: bool = True
    digest_hour: int = 0


class WebhookTestIn(BaseModel):
    url: str
    template: str = "discord"
