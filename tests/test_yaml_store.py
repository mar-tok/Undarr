import pytest

from core.yaml_store import (
    YamlStore,
    Preset,
    Library,
    SkipRule,
    SkipCondition,
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


# Settings


class TestSettings:
    async def test_defaults(self, store):
        s = await store.get_settings()
        assert s.cache_dir == "/tmp/undarr"
        assert s.process_priority == "normal"
        assert s.max_size_ratio == 1.0
        assert s.queue_order == "fifo"
        assert s.schedule_enabled is False

    async def test_update(self, store):
        s = await store.update_settings(
            process_priority="low", queue_order="largest_first"
        )
        assert s.process_priority == "low"
        assert s.queue_order == "largest_first"

    async def test_update_ignores_unknown_fields(self, store):
        s = await store.update_settings(nonexistent_field="value")
        assert not hasattr(s, "nonexistent_field")


# Validation and migration


class TestConfigFromDict:
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
