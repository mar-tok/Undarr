from __future__ import annotations

import asyncio
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml

import config
from core.logger import log


@dataclass
class DeviceConfig:
    max_jobs: int = 1


@dataclass
class Settings:
    cache_dir: str = "/tmp/undarr"
    devices: dict[str, DeviceConfig] = field(default_factory=dict)


@dataclass
class Preset:
    ffmpeg_args: str
    output_container: str | None = None


@dataclass
class Library:
    paths: list[str]
    preset: str
    watch: bool = True
    scan_interval: int = 0
    scan_unit: str = "hours"


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
    settings = Settings(
        cache_dir=raw_settings.get("cache_dir", "/tmp/undarr"),
        devices=devices,
    )

    presets: dict[str, Preset] = {}
    for name, p in (data.get("presets") or {}).items():
        presets[name] = Preset(
            ffmpeg_args=p.get("ffmpeg_args", ""),
            output_container=p.get("output_container"),
        )

    libraries: dict[str, Library] = {}
    for name, lib in (data.get("libraries") or {}).items():
        libraries[name] = Library(
            paths=lib.get("paths", []),
            preset=lib.get("preset", ""),
            watch=lib.get("watch", True),
            scan_interval=lib.get("scan_interval", 0),
            scan_unit=lib.get("scan_unit", "hours"),
        )

    return Config(settings=settings, presets=presets, libraries=libraries)


def _config_to_dict(cfg: Config) -> dict:
    return {
        "settings": {
            "cache_dir": cfg.settings.cache_dir,
            "devices": {
                dev_id: {"max_jobs": dc.max_jobs}
                for dev_id, dc in cfg.settings.devices.items()
            },
        },
        "presets": {
            name: {
                "ffmpeg_args": p.ffmpeg_args,
                "output_container": p.output_container,
            }
            for name, p in cfg.presets.items()
        },
        "libraries": {
            name: {
                "paths": lib.paths,
                "preset": lib.preset,
                "watch": lib.watch,
                "scan_interval": lib.scan_interval,
                "scan_unit": lib.scan_unit,
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

    async def set_cache_dir(self, cache_dir: str) -> Settings:
        async with self._lock:
            self._config.settings.cache_dir = cache_dir
            await self._save()
        return self._config.settings

    async def update_device_config(self, device_id: str, max_jobs: int) -> DeviceConfig:
        async with self._lock:
            self._config.settings.devices[device_id] = DeviceConfig(max_jobs=max_jobs)
            await self._save()
        return self._config.settings.devices[device_id]

    async def get_presets(self) -> dict[str, Preset]:
        return dict(self._config.presets)

    async def get_preset(self, name: str) -> Preset | None:
        return self._config.presets.get(name)

    async def create_preset(self, name: str, preset: Preset) -> None:
        async with self._lock:
            self._config.presets[name] = preset
            await self._save()

    async def update_preset(self, name: str, preset: Preset) -> None:
        async with self._lock:
            self._config.presets[name] = preset
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

    async def delete_library(self, name: str) -> bool:
        async with self._lock:
            if name not in self._config.libraries:
                return False
            del self._config.libraries[name]
            await self._save()
        return True


store = YamlStore()
