import pytest

from core.yaml_store import (
    YamlStore,
    Preset,
    Library,
    SkipRule,
    SkipCondition,
    WebhookConfig,
    AudioConfig,
    AudioTrackConfig,
    SubtitleConfig,
    BUILTIN_PRESETS,
    _config_from_dict,
    _config_to_dict,
)


@pytest.fixture
async def store(tmp_path, monkeypatch):
    """YamlStore backed by a temp file."""
    import config

    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.yaml")
    s = YamlStore()
    await s.load()
    return s


def _preset(**overrides) -> Preset:
    defaults = {"ffmpeg_args": "-c:v libx265 -crf 20"}
    defaults.update(overrides)
    return Preset(**defaults)


def _library(**overrides) -> Library:
    defaults = {"paths": ["/media/movies"], "preset": "HEVC"}
    defaults.update(overrides)
    return Library(**defaults)


# Preset CRUD


class TestPresetCRUD:
    async def test_create_and_get(self, store):
        await store.create_preset("Custom", _preset())
        p = await store.get_preset("Custom")
        assert p is not None
        assert p.ffmpeg_args == "-c:v libx265 -crf 20"

    async def test_get_nonexistent(self, store):
        assert await store.get_preset("nope") is None

    async def test_get_builtin(self, store):
        p = await store.get_preset("HEVC Transparent")
        assert p is not None
        assert p is BUILTIN_PRESETS["HEVC Transparent"]

    async def test_list_includes_builtins(self, store):
        await store.create_preset("Custom", _preset())
        presets = await store.get_presets()
        assert "Custom" in presets
        for name in BUILTIN_PRESETS:
            assert name in presets

    async def test_custom_overrides_builtin_name(self, store):
        custom = _preset(ffmpeg_args="-c:v libx264 -crf 18")
        await store.create_preset("HEVC Transparent", custom)
        p = await store.get_preset("HEVC Transparent")
        assert p.ffmpeg_args == "-c:v libx264 -crf 18"

    async def test_builtins_not_persisted(self, store):
        await store.create_preset("Custom", _preset())
        data = _config_to_dict(store.config)
        assert "Custom" in data["presets"]
        for name in BUILTIN_PRESETS:
            assert name not in data["presets"]

    async def test_rename_file_round_trip(self, store):
        await store.create_preset("Renamer", _preset(rename_file=True))
        data = _config_to_dict(store.config)
        assert data["presets"]["Renamer"]["rename_file"] is True
        cfg = _config_from_dict(data)
        assert cfg.presets["Renamer"].rename_file is True

    async def test_rename_file_default_not_persisted(self, store):
        await store.create_preset("Plain", _preset())
        data = _config_to_dict(store.config)
        assert "rename_file" not in data["presets"]["Plain"]

    async def test_ten_bit_round_trip(self, store):
        await store.create_preset("Deep", _preset(ten_bit=True))
        data = _config_to_dict(store.config)
        assert data["presets"]["Deep"]["ten_bit"] is True
        cfg = _config_from_dict(data)
        assert cfg.presets["Deep"].ten_bit is True

    async def test_ten_bit_default_not_persisted(self, store):
        await store.create_preset("Plain", _preset())
        data = _config_to_dict(store.config)
        assert "ten_bit" not in data["presets"]["Plain"]

    def test_builtins_are_ten_bit(self):
        for p in BUILTIN_PRESETS.values():
            assert p.ten_bit is True

    def test_builtins_copy_subtitles(self):
        for name, p in BUILTIN_PRESETS.items():
            assert "-c:s copy" in p.ffmpeg_args, name

    async def test_update(self, store):
        await store.create_preset("P1", _preset())
        await store.update_preset("P1", _preset(ffmpeg_args="-c:v libx264"))
        p = await store.get_preset("P1")
        assert p.ffmpeg_args == "-c:v libx264"

    async def test_delete(self, store):
        await store.create_preset("P1", _preset())
        assert await store.delete_preset("P1") is True
        assert await store.get_preset("P1") is None

    async def test_delete_nonexistent(self, store):
        assert await store.delete_preset("nope") is False

    async def test_rename(self, store):
        await store.create_preset("Old", _preset())
        await store.rename_preset("Old", "New", _preset(description="renamed"))
        assert await store.get_preset("Old") is None
        p = await store.get_preset("New")
        assert p.description == "renamed"

    async def test_rename_cascades_to_libraries(self, store):
        await store.create_preset("Old", _preset())
        await store.create_library("movies", _library(preset="Old"))
        await store.rename_preset("Old", "New", _preset())
        lib = await store.get_library("movies")
        assert lib.preset == "New"

    async def test_rename_does_not_affect_unrelated_libraries(self, store):
        await store.create_preset("P1", _preset())
        await store.create_preset("P2", _preset())
        await store.create_library("movies", _library(preset="P1"))
        await store.create_library("tv", _library(preset="P2"))
        await store.rename_preset("P1", "P1_new", _preset())
        lib = await store.get_library("tv")
        assert lib.preset == "P2"


# Library CRUD


class TestLibraryCRUD:
    async def test_create_and_get(self, store):
        await store.create_library("movies", _library())
        lib = await store.get_library("movies")
        assert lib is not None
        assert lib.paths == ["/media/movies"]
        assert lib.preset == "HEVC"

    async def test_get_nonexistent(self, store):
        assert await store.get_library("nope") is None

    async def test_list(self, store):
        await store.create_library("movies", _library())
        await store.create_library("tv", _library(paths=["/media/tv"]))
        libs = await store.get_libraries()
        assert len(libs) == 2
        assert "movies" in libs
        assert "tv" in libs

    async def test_update(self, store):
        await store.create_library("movies", _library())
        await store.update_library("movies", _library(paths=["/new/path"]))
        lib = await store.get_library("movies")
        assert lib.paths == ["/new/path"]

    async def test_delete(self, store):
        await store.create_library("movies", _library())
        assert await store.delete_library("movies") is True
        assert await store.get_library("movies") is None

    async def test_delete_nonexistent(self, store):
        assert await store.delete_library("nope") is False

    async def test_pause_unpause(self, store):
        await store.create_library("movies", _library())
        await store.set_library_paused("movies", True)
        assert (await store.get_library("movies")).paused is True
        await store.set_library_paused("movies", False)
        assert (await store.get_library("movies")).paused is False

    async def test_pause_nonexistent_no_error(self, store):
        await store.set_library_paused("nope", True)

    async def test_skip_rules_roundtrip(self, store):
        rules = [
            SkipRule(
                conditions=[
                    SkipCondition(field="video_codec", operator="equals", value="hevc")
                ]
            )
        ]
        await store.create_library("movies", _library(skip_rules=rules))
        lib = await store.get_library("movies")
        assert len(lib.skip_rules) == 1
        assert len(lib.skip_rules[0].conditions) == 1
        assert lib.skip_rules[0].conditions[0].field == "video_codec"
        assert lib.skip_rules[0].conditions[0].value == "hevc"

    async def test_compound_skip_rules_roundtrip(self, store):
        rules = [
            SkipRule(
                conditions=[
                    SkipCondition(field="video_codec", operator="equals", value="hevc"),
                    SkipCondition(
                        field="bitrate_kbps", operator="less_than", value=3000
                    ),
                ]
            )
        ]
        await store.create_library("movies", _library(skip_rules=rules))
        lib = await store.get_library("movies")
        assert len(lib.skip_rules) == 1
        assert len(lib.skip_rules[0].conditions) == 2
        assert lib.skip_rules[0].conditions[1].field == "bitrate_kbps"


class TestLibraryIntervals:
    def test_scan_interval_seconds(self):
        lib = _library(scan_interval=2, scan_unit="hours")
        assert lib.scan_interval_seconds == 7200

    def test_new_file_delay_seconds(self):
        lib = _library(new_file_delay=5, new_file_delay_unit="minutes")
        assert lib.new_file_delay_seconds == 300

    def test_unknown_unit_counts_as_minutes(self):
        lib = _library(scan_interval=2, scan_unit="fortnights")
        assert lib.scan_interval_seconds == 120


# Settings


class TestSettings:
    async def test_defaults(self, store):
        s = await store.get_settings()
        assert s.cache_dir == "/tmp/undarr"
        assert s.process_priority == "normal"
        assert s.max_size_ratio == 1.0
        assert s.queue_order == "fifo"
        assert s.schedule_enabled is False
        assert s.allow_duplicate_deletion is False

    async def test_update(self, store):
        s = await store.update_settings(
            process_priority="low", queue_order="largest_first"
        )
        assert s.process_priority == "low"
        assert s.queue_order == "largest_first"

    async def test_update_ignores_unknown_fields(self, store):
        s = await store.update_settings(nonexistent_field="value")
        assert not hasattr(s, "nonexistent_field")

    async def test_device_config(self, store):
        dc = await store.update_device_config("qsv", 3)
        assert dc.max_jobs == 3
        s = await store.get_settings()
        assert s.devices["qsv"].max_jobs == 3

    async def test_device_config_overwrite(self, store):
        await store.update_device_config("cpu", 2)
        await store.update_device_config("cpu", 4)
        s = await store.get_settings()
        assert s.devices["cpu"].max_jobs == 4

    async def test_allow_duplicate_deletion_round_trip(self, store):
        await store.update_settings(allow_duplicate_deletion=True)
        data = _config_to_dict(store.config)
        assert data["settings"]["allow_duplicate_deletion"] is True
        cfg = _config_from_dict(data)
        assert cfg.settings.allow_duplicate_deletion is True

    async def test_allow_duplicate_deletion_default_not_persisted(self, store):
        data = _config_to_dict(store.config)
        assert "allow_duplicate_deletion" not in data["settings"]


# Webhooks


class TestWebhooks:
    async def test_empty_by_default_and_not_persisted(self, store):
        assert await store.get_webhooks() == []
        assert "webhooks" not in _config_to_dict(store.config)["settings"]

    async def test_set_and_round_trip(self, store):
        await store.set_webhooks(
            [
                WebhookConfig(url="https://a/hook", events=["job_failed"]),
                WebhookConfig(url="https://b/hook", enabled=False),
            ]
        )
        data = _config_to_dict(store.config)
        assert data["settings"]["webhooks"] == [
            {"url": "https://a/hook", "template": "discord", "events": ["job_failed"]},
            {
                "url": "https://b/hook",
                "template": "discord",
                "events": [],
                "enabled": False,
            },
        ]
        cfg = _config_from_dict(data)
        assert cfg.settings.webhooks == [
            WebhookConfig(url="https://a/hook", events=["job_failed"]),
            WebhookConfig(url="https://b/hook", enabled=False),
        ]

    def test_bad_entries_dropped_and_values_coerced(self):
        cfg = _config_from_dict(
            {
                "settings": {
                    "webhooks": [
                        "not a dict",
                        {"template": "discord"},
                        {
                            "url": "https://a/hook",
                            "template": "slack",
                            "events": ["job_failed", "bogus"],
                        },
                    ]
                }
            }
        )
        assert cfg.settings.webhooks == [
            WebhookConfig(
                url="https://a/hook", template="discord", events=["job_failed"]
            )
        ]

    async def test_template_round_trip(self, store):
        await store.set_webhooks(
            [WebhookConfig(url="https://ntfy.sh/undarr", template="ntfy")]
        )
        data = _config_to_dict(store.config)
        assert data["settings"]["webhooks"][0]["template"] == "ntfy"
        assert _config_from_dict(data).settings.webhooks[0].template == "ntfy"

    async def test_digest_hour_round_trip_and_omitted_when_zero(self, store):
        await store.set_webhooks(
            [
                WebhookConfig(
                    url="https://a/hook", events=["daily_digest"], digest_hour=8
                ),
                WebhookConfig(url="https://b/hook", events=["daily_digest"]),
            ]
        )
        data = _config_to_dict(store.config)
        assert data["settings"]["webhooks"][0]["digest_hour"] == 8
        assert "digest_hour" not in data["settings"]["webhooks"][1]
        hours = [wh.digest_hour for wh in _config_from_dict(data).settings.webhooks]
        assert hours == [8, 0]

    @pytest.mark.parametrize("raw", [24, -1, "8", None])
    def test_bad_digest_hour_falls_back_to_zero(self, raw):
        cfg = _config_from_dict(
            {"settings": {"webhooks": [{"url": "https://a/hook", "digest_hour": raw}]}}
        )
        assert cfg.settings.webhooks[0].digest_hour == 0

    async def test_get_returns_a_copy(self, store):
        await store.set_webhooks([WebhookConfig(url="https://a/hook")])
        (await store.get_webhooks()).clear()
        assert len(await store.get_webhooks()) == 1


# Validation and migration


# Persistence


async def _reload(store):
    store2 = YamlStore()
    store2._path = store._path
    await store2.load()
    return store2


class TestPersistence:
    async def test_roundtrip(self, store):
        await store.create_preset("P1", _preset(description="test"))
        await store.create_library("L1", _library())
        await store.update_settings(process_priority="low")
        await store.update_device_config("cpu", 2)

        store2 = await _reload(store)
        assert (await store2.get_preset("P1")).description == "test"
        assert (await store2.get_library("L1")).paths == ["/media/movies"]
        s = await store2.get_settings()
        assert s.process_priority == "low"
        assert s.devices["cpu"].max_jobs == 2

    async def test_load_nonexistent_creates_default(self, store):
        assert store._path.exists()
        assert await store.get_presets() == dict(BUILTIN_PRESETS)
        assert await store.get_libraries() == {}

    async def test_audio_config_roundtrip(self, store):
        audio = AudioConfig(
            stereo=AudioTrackConfig(codec="aac", bitrate="128k"),
            surround=AudioTrackConfig(codec="copy"),
            languages=["eng", "nor"],
            remove_commentary=True,
            add_stereo_downmix="if_no_stereo",
            downmix_bitrate="128k",
        )
        await store.create_preset("P1", _preset(audio=audio))
        store2 = await _reload(store)
        assert (await store2.get_preset("P1")).audio == audio

    async def test_subtitle_config_roundtrip(self, store):
        sub = SubtitleConfig(
            mode="keep_by_language", languages=["eng"], remove_commentary=True
        )
        await store.create_preset("P1", _preset(subtitle=sub))
        store2 = await _reload(store)
        assert (await store2.get_preset("P1")).subtitle == sub

    async def test_resolution_cap_roundtrip(self, store):
        await store.create_preset("P1", _preset(resolution_cap=1080))
        store2 = await _reload(store)
        assert (await store2.get_preset("P1")).resolution_cap == 1080


# Validation


class TestConfigFromDict:
    def test_empty_dict(self):
        cfg = _config_from_dict({})
        assert cfg.settings.cache_dir == "/tmp/undarr"
        assert cfg.presets == {}
        assert cfg.libraries == {}

    def test_schedule_partial_days_keep_defaults(self):
        cfg = _config_from_dict({"settings": {"schedule": {"mon": [True] * 24}}})
        assert cfg.settings.schedule["mon"] == [True] * 24
        assert cfg.settings.schedule["tue"] == [True] * 24

    def test_schedule_wrong_length_ignored(self):
        cfg = _config_from_dict({"settings": {"schedule": {"mon": [True] * 12}}})
        assert cfg.settings.schedule["mon"] == [True] * 24

    def test_invalid_priority_resets(self):
        cfg = _config_from_dict({"settings": {"process_priority": "ultra"}})
        assert cfg.settings.process_priority == "normal"

    def test_invalid_queue_order_resets(self):
        cfg = _config_from_dict({"settings": {"queue_order": "random"}})
        assert cfg.settings.queue_order == "fifo"

    def test_invalid_max_size_ratio_resets(self):
        cfg = _config_from_dict({"settings": {"max_size_ratio": 2.0}})
        assert cfg.settings.max_size_ratio == 1.0

    def test_zero_max_size_ratio_resets(self):
        cfg = _config_from_dict({"settings": {"max_size_ratio": 0.0}})
        assert cfg.settings.max_size_ratio == 1.0

    def test_negative_max_size_ratio_resets(self):
        cfg = _config_from_dict({"settings": {"max_size_ratio": -0.5}})
        assert cfg.settings.max_size_ratio == 1.0

    def test_resolution_cap_coerced_to_int(self):
        data = {
            "presets": {"P1": {"ffmpeg_args": "-c:v libx265", "resolution_cap": 1080.0}}
        }
        cfg = _config_from_dict(data)
        assert cfg.presets["P1"].resolution_cap == 1080
        assert isinstance(cfg.presets["P1"].resolution_cap, int)

    def test_library_skip_rules(self):
        data = {
            "libraries": {
                "L1": {
                    "paths": ["/media"],
                    "preset": "P1",
                    "skip_rules": [
                        {
                            "conditions": [
                                {
                                    "field": "video_codec",
                                    "operator": "equals",
                                    "value": "hevc",
                                },
                                {
                                    "field": "bitrate_kbps",
                                    "operator": "less_than",
                                    "value": 3000,
                                },
                            ]
                        }
                    ],
                }
            }
        }
        cfg = _config_from_dict(data)
        rules = cfg.libraries["L1"].skip_rules
        assert len(rules) == 1
        assert [c.field for c in rules[0].conditions] == ["video_codec", "bitrate_kbps"]
        assert rules[0].conditions[1].value == 3000

    def test_library_defaults(self):
        data = {"libraries": {"L1": {"paths": ["/media"], "preset": "P1"}}}
        lib = _config_from_dict(data).libraries["L1"]
        assert lib.watch is True
        assert lib.scan_unit == "hours"
        assert lib.new_file_delay_unit == "minutes"
        assert lib.paused is False


class TestConfigToDict:
    def test_roundtrip_preserves_data(self):
        data = {
            "settings": {
                "cache_dir": "/custom/cache",
                "devices": {"cpu": {"max_jobs": 2}},
                "schedule_enabled": True,
                "process_priority": "low",
                "max_size_ratio": 0.9,
                "queue_order": "largest_first",
            },
            "presets": {
                "P1": {
                    "ffmpeg_args": "-c:v libx265 -crf 20",
                    "output_container": "mkv",
                    "description": "Test preset",
                }
            },
            "libraries": {
                "L1": {
                    "paths": ["/media"],
                    "preset": "P1",
                    "watch": False,
                    "scan_interval": 6,
                    "scan_unit": "hours",
                }
            },
        }
        cfg = _config_from_dict(data)
        cfg2 = _config_from_dict(_config_to_dict(cfg))
        assert cfg2.settings == cfg.settings
        assert cfg2.presets == cfg.presets
        assert cfg2.libraries == cfg.libraries
        assert cfg2.libraries["L1"].watch is False
