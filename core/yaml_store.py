from __future__ import annotations

import asyncio
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml

import config
from core.logger import log


@dataclass
class SkipCondition:
    field: str
    operator: str
    value: str | int | float


@dataclass
class SkipRule:
    conditions: list[SkipCondition]


@dataclass
class AudioTrackConfig:
    codec: str = "copy"
    bitrate: str | None = None


@dataclass
class AudioConfig:
    stereo: AudioTrackConfig | None = None
    surround: AudioTrackConfig | None = None
    languages: list[str] | None = None
    remove_commentary: bool = False
    add_stereo_downmix: str = "never"
    downmix_bitrate: str | None = None


@dataclass
class SubtitleConfig:
    mode: str = "keep"
    languages: list[str] | None = None
    remove_commentary: bool = False


@dataclass
class DeviceConfig:
    max_jobs: int = 1


DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
VALID_PRIORITIES = ("normal", "low", "lowest")
VALID_QUEUE_ORDERS = ("fifo", "largest_first", "highest_bitrate")
VALID_WEBHOOK_EVENTS = ("job_failed", "queue_stalled", "daily_digest", "top_reduction")
VALID_WEBHOOK_TEMPLATES = ("discord", "ntfy", "gotify", "generic")


def _default_schedule() -> dict[str, list[bool]]:
    return {day: [True] * 24 for day in DAYS}


@dataclass
class WebhookConfig:
    url: str
    template: str = "discord"
    events: list[str] = field(default_factory=list)
    enabled: bool = True
    digest_hour: int = 0


@dataclass
class Settings:
    cache_dir: str = "/tmp/undarr"
    devices: dict[str, DeviceConfig] = field(default_factory=dict)
    schedule_enabled: bool = False
    schedule: dict[str, list[bool]] = field(default_factory=_default_schedule)
    process_priority: str = "normal"
    max_size_ratio: float = 1.0
    queue_order: str = "fifo"
    allow_duplicate_deletion: bool = False
    webhooks: list[WebhookConfig] = field(default_factory=list)


@dataclass
class Preset:
    ffmpeg_args: str
    output_container: str | None = None
    description: str = ""
    audio: AudioConfig | None = None
    subtitle: SubtitleConfig | None = None
    resolution_cap: int | None = None
    rename_file: bool = False
    ten_bit: bool = False


BUILTIN_PRESETS: dict[str, Preset] = {
    "HEVC Transparent": Preset(
        ffmpeg_args="-c:s copy -c:v libx265 -crf 20 -preset slow",
        description="Converts video to H.265 with no discernible quality loss. Safe default for most content. Typically saves 40-50% storage with broad device compatibility.",
        ten_bit=True,
    ),
    "HEVC Space Saver": Preset(
        ffmpeg_args="-c:s copy -c:v libx265 -crf 26 -preset slow",
        description="Converts video to H.265 with aggressive compression. Saves more space, and quality differences remain difficult to discern for most content. Broad device compatibility.",
        ten_bit=True,
    ),
    "AV1 Transparent": Preset(
        ffmpeg_args="-c:s copy -c:v libsvtav1 -crf 25 -preset 6",
        description="Converts video to AV1 with no discernible quality loss. Better compression than HEVC, but rarely compatible with older devices and players. Requires AV1-compatible playback devices.",
        ten_bit=True,
    ),
    "AV1 Space Saver": Preset(
        ffmpeg_args="-c:s copy -c:v libsvtav1 -crf 32 -preset 6",
        description="Converts video to AV1 with aggressive compression. Maximum storage savings. Better compression than HEVC, but rarely compatible with older devices and players. Requires AV1-compatible playback devices.",
        ten_bit=True,
    ),
}


def is_builtin_preset(name: str) -> bool:
    return name in BUILTIN_PRESETS


TIME_UNITS = {"seconds": 1, "minutes": 60, "hours": 3600, "days": 86400}


@dataclass
class Library:
    paths: list[str]
    preset: str
    watch: bool = True
    skip_rules: list[SkipRule] = field(default_factory=list)
    path_patterns: list[str] = field(default_factory=list)
    scan_interval: int = 0
    scan_unit: str = "hours"
    description: str = ""
    new_file_delay: int = 0
    new_file_delay_unit: str = "minutes"
    paused: bool = False
    mark_processed_pending: bool = False

    @property
    def scan_interval_seconds(self) -> int:
        return self.scan_interval * TIME_UNITS.get(self.scan_unit, 60)

    @property
    def new_file_delay_seconds(self) -> int:
        return self.new_file_delay * TIME_UNITS.get(self.new_file_delay_unit, 60)


@dataclass
class Config:
    settings: Settings = field(default_factory=Settings)
    presets: dict[str, Preset] = field(default_factory=dict)
    libraries: dict[str, Library] = field(default_factory=dict)


def _config_from_dict(data: dict) -> Config:
    raw_settings = data.get("settings") or {}
    devices: dict[str, DeviceConfig] = {}
    for dev_id, dev in (raw_settings.get("devices") or {}).items():
        devices[dev_id] = DeviceConfig(max_jobs=dev.get("max_jobs", 1))

    schedule = _default_schedule()
    raw_schedule = raw_settings.get("schedule")
    if isinstance(raw_schedule, dict):
        for day in DAYS:
            raw_day = raw_schedule.get(day)
            if isinstance(raw_day, list) and len(raw_day) == 24:
                schedule[day] = [bool(v) for v in raw_day]

    priority = raw_settings.get("process_priority", "normal")
    if priority not in VALID_PRIORITIES:
        priority = "normal"

    max_size_ratio = raw_settings.get("max_size_ratio", 1.0)
    if not isinstance(max_size_ratio, (int, float)) or not (
        0.0 < max_size_ratio <= 1.0
    ):
        max_size_ratio = 1.0

    queue_order = raw_settings.get("queue_order", "fifo")
    if queue_order not in VALID_QUEUE_ORDERS:
        queue_order = "fifo"

    webhooks: list[WebhookConfig] = []
    for raw_wh in raw_settings.get("webhooks") or []:
        if not isinstance(raw_wh, dict) or not raw_wh.get("url"):
            continue
        template = raw_wh.get("template", "discord")
        if template not in VALID_WEBHOOK_TEMPLATES:
            template = "discord"
        events = [e for e in (raw_wh.get("events") or []) if e in VALID_WEBHOOK_EVENTS]
        digest_hour = raw_wh.get("digest_hour", 0)
        if not isinstance(digest_hour, int) or not 0 <= digest_hour <= 23:
            digest_hour = 0
        webhooks.append(
            WebhookConfig(
                url=raw_wh["url"],
                template=template,
                events=events,
                enabled=bool(raw_wh.get("enabled", True)),
                digest_hour=digest_hour,
            )
        )

    settings = Settings(
        cache_dir=raw_settings.get("cache_dir", "/tmp/undarr"),
        devices=devices,
        schedule_enabled=bool(raw_settings.get("schedule_enabled", False)),
        schedule=schedule,
        process_priority=priority,
        max_size_ratio=float(max_size_ratio),
        queue_order=queue_order,
        allow_duplicate_deletion=bool(
            raw_settings.get("allow_duplicate_deletion", False)
        ),
        webhooks=webhooks,
    )

    presets: dict[str, Preset] = {}
    for name, p in (data.get("presets") or {}).items():
        audio = None
        raw_audio = p.get("audio")
        if raw_audio:
            stereo = None
            raw_stereo = raw_audio.get("stereo")
            if raw_stereo:
                stereo = AudioTrackConfig(
                    codec=raw_stereo.get("codec", "copy"),
                    bitrate=raw_stereo.get("bitrate"),
                )
            surround = None
            raw_surround = raw_audio.get("surround")
            if raw_surround:
                surround = AudioTrackConfig(
                    codec=raw_surround.get("codec", "copy"),
                    bitrate=raw_surround.get("bitrate"),
                )
            langs = raw_audio.get("languages")
            audio = AudioConfig(
                stereo=stereo,
                surround=surround,
                languages=langs if langs else None,
                remove_commentary=bool(raw_audio.get("remove_commentary", False)),
                add_stereo_downmix=raw_audio.get("add_stereo_downmix", "never"),
                downmix_bitrate=raw_audio.get("downmix_bitrate"),
            )
        subtitle = None
        raw_subtitle = p.get("subtitle")
        if raw_subtitle:
            langs = raw_subtitle.get("languages")
            subtitle = SubtitleConfig(
                mode=raw_subtitle.get("mode", "keep"),
                languages=langs if langs else None,
                remove_commentary=bool(raw_subtitle.get("remove_commentary", False)),
            )

        raw_res_cap = p.get("resolution_cap")
        resolution_cap = int(raw_res_cap) if raw_res_cap is not None else None

        presets[name] = Preset(
            ffmpeg_args=p.get("ffmpeg_args", ""),
            output_container=p.get("output_container"),
            description=p.get("description", ""),
            audio=audio,
            subtitle=subtitle,
            resolution_cap=resolution_cap,
            rename_file=bool(p.get("rename_file", False)),
            ten_bit=bool(p.get("ten_bit", False)),
        )

    libraries: dict[str, Library] = {}
    for name, lib in (data.get("libraries") or {}).items():
        skip_rules = []
        for r in lib.get("skip_rules") or []:
            conds = [
                SkipCondition(
                    field=c["field"], operator=c["operator"], value=c["value"]
                )
                for c in r["conditions"]
            ]
            skip_rules.append(SkipRule(conditions=conds))
        libraries[name] = Library(
            paths=lib.get("paths", []),
            preset=lib.get("preset", ""),
            watch=lib.get("watch", True),
            skip_rules=skip_rules,
            path_patterns=lib.get("path_patterns", []),
            scan_interval=lib.get("scan_interval", 0),
            scan_unit=lib.get("scan_unit", "hours"),
            description=lib.get("description", ""),
            new_file_delay=lib.get("new_file_delay", 0),
            new_file_delay_unit=lib.get("new_file_delay_unit", "minutes"),
            paused=bool(lib.get("paused", False)),
            mark_processed_pending=bool(lib.get("mark_processed_pending", False)),
        )

    return Config(settings=settings, presets=presets, libraries=libraries)


def _track_to_dict(t: AudioTrackConfig) -> dict:
    d: dict = {"codec": t.codec}
    if t.bitrate:
        d["bitrate"] = t.bitrate
    return d


def _audio_config_to_dict(a: AudioConfig) -> dict:
    d: dict = {}
    if a.stereo:
        d["stereo"] = _track_to_dict(a.stereo)
    if a.surround:
        d["surround"] = _track_to_dict(a.surround)
    if a.add_stereo_downmix != "never":
        d["add_stereo_downmix"] = a.add_stereo_downmix
    if a.downmix_bitrate:
        d["downmix_bitrate"] = a.downmix_bitrate
    if a.languages:
        d["languages"] = a.languages
    if a.remove_commentary:
        d["remove_commentary"] = True
    return d


def _subtitle_config_to_dict(s: SubtitleConfig) -> dict:
    d: dict = {"mode": s.mode}
    if s.languages:
        d["languages"] = s.languages
    if s.remove_commentary:
        d["remove_commentary"] = True
    return d


def _config_to_dict(cfg: Config) -> dict:
    return {
        "settings": {
            "cache_dir": cfg.settings.cache_dir,
            "devices": {
                dev_id: {"max_jobs": dc.max_jobs}
                for dev_id, dc in cfg.settings.devices.items()
            },
            "schedule_enabled": cfg.settings.schedule_enabled,
            "schedule": cfg.settings.schedule,
            "process_priority": cfg.settings.process_priority,
            "max_size_ratio": cfg.settings.max_size_ratio,
            "queue_order": cfg.settings.queue_order,
            **(
                {"allow_duplicate_deletion": True}
                if cfg.settings.allow_duplicate_deletion
                else {}
            ),
            **(
                {
                    "webhooks": [
                        {
                            "url": wh.url,
                            "template": wh.template,
                            "events": wh.events,
                            **({"enabled": False} if not wh.enabled else {}),
                            **(
                                {"digest_hour": wh.digest_hour}
                                if wh.digest_hour
                                else {}
                            ),
                        }
                        for wh in cfg.settings.webhooks
                    ]
                }
                if cfg.settings.webhooks
                else {}
            ),
        },
        "presets": {
            name: {
                "ffmpeg_args": p.ffmpeg_args,
                "output_container": p.output_container,
                **({"description": p.description} if p.description else {}),
                **({"audio": _audio_config_to_dict(p.audio)} if p.audio else {}),
                **(
                    {"subtitle": _subtitle_config_to_dict(p.subtitle)}
                    if p.subtitle
                    else {}
                ),
                **(
                    {"resolution_cap": p.resolution_cap}
                    if p.resolution_cap is not None
                    else {}
                ),
                **({"rename_file": True} if p.rename_file else {}),
                **({"ten_bit": True} if p.ten_bit else {}),
            }
            for name, p in cfg.presets.items()
        },
        "libraries": {
            name: {
                "paths": lib.paths,
                "preset": lib.preset,
                "watch": lib.watch,
                "skip_rules": [
                    {
                        "conditions": [
                            {"field": c.field, "operator": c.operator, "value": c.value}
                            for c in r.conditions
                        ]
                    }
                    for r in lib.skip_rules
                ],
                "scan_interval": lib.scan_interval,
                "scan_unit": lib.scan_unit,
                **({"description": lib.description} if lib.description else {}),
                **(
                    {"new_file_delay": lib.new_file_delay} if lib.new_file_delay else {}
                ),
                **(
                    {"new_file_delay_unit": lib.new_file_delay_unit}
                    if lib.new_file_delay
                    else {}
                ),
                **({"path_patterns": lib.path_patterns} if lib.path_patterns else {}),
                **({"paused": True} if lib.paused else {}),
                **(
                    {"mark_processed_pending": True}
                    if lib.mark_processed_pending
                    else {}
                ),
            }
            for name, lib in cfg.libraries.items()
        },
    }


class YamlStore:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._config: Config = Config()
        self._path: Path = config.CONFIG_PATH

    @property
    def config(self) -> Config:
        return self._config

    async def load(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if self._path.exists():
            text = self._path.read_text(encoding="utf-8")
            data = yaml.safe_load(text) or {}
            self._config = _config_from_dict(data)
            log.info("Loaded config from %s", self._path)
        else:
            self._config = Config()
            await self._save()
            log.info("Created default config at %s", self._path)

    async def _save(self) -> None:
        data = _config_to_dict(self._config)
        fd, tmp = tempfile.mkstemp(dir=self._path.parent, suffix=".yaml.tmp")
        try:
            with open(fd, "w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)
            Path(tmp).replace(self._path)
        except Exception:
            Path(tmp).unlink(missing_ok=True)
            raise

    async def get_settings(self) -> Settings:
        return self._config.settings

    async def update_settings(self, **kwargs) -> Settings:
        async with self._lock:
            for k, v in kwargs.items():
                if hasattr(self._config.settings, k):
                    setattr(self._config.settings, k, v)
            await self._save()
        return self._config.settings

    async def update_device_config(self, device_id: str, max_jobs: int) -> DeviceConfig:
        async with self._lock:
            self._config.settings.devices[device_id] = DeviceConfig(max_jobs=max_jobs)
            await self._save()
        return self._config.settings.devices[device_id]

    async def get_presets(self) -> dict[str, Preset]:
        return {**BUILTIN_PRESETS, **self._config.presets}

    async def get_preset(self, name: str) -> Preset | None:
        return self._config.presets.get(name) or BUILTIN_PRESETS.get(name)

    async def create_preset(self, name: str, preset: Preset) -> None:
        async with self._lock:
            self._config.presets[name] = preset
            await self._save()

    async def update_preset(self, name: str, preset: Preset) -> None:
        async with self._lock:
            self._config.presets[name] = preset
            await self._save()

    async def rename_preset(self, old_name: str, new_name: str, preset: Preset) -> None:
        async with self._lock:
            del self._config.presets[old_name]
            self._config.presets[new_name] = preset
            for lib in self._config.libraries.values():
                if lib.preset == old_name:
                    lib.preset = new_name
            await self._save()

    async def delete_preset(self, name: str) -> bool:
        async with self._lock:
            if name not in self._config.presets:
                return False
            del self._config.presets[name]
            await self._save()
        return True

    async def get_libraries(self) -> dict[str, Library]:
        return dict(self._config.libraries)

    async def get_library(self, name: str) -> Library | None:
        return self._config.libraries.get(name)

    async def create_library(self, name: str, library: Library) -> None:
        async with self._lock:
            self._config.libraries[name] = library
            await self._save()

    async def update_library(self, name: str, library: Library) -> None:
        async with self._lock:
            self._config.libraries[name] = library
            await self._save()

    async def set_library_paused(self, name: str, paused: bool) -> None:
        async with self._lock:
            lib = self._config.libraries.get(name)
            if lib:
                lib.paused = paused
                await self._save()

    async def delete_library(self, name: str) -> bool:
        async with self._lock:
            if name not in self._config.libraries:
                return False
            del self._config.libraries[name]
            await self._save()
        return True

    async def get_webhooks(self) -> list[WebhookConfig]:
        return list(self._config.settings.webhooks)

    async def set_webhooks(self, webhooks: list[WebhookConfig]) -> list[WebhookConfig]:
        async with self._lock:
            self._config.settings.webhooks = webhooks
            await self._save()
        return self._config.settings.webhooks


store = YamlStore()
