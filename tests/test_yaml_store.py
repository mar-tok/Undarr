import pytest

from core.yaml_store import YamlStore, Library, SkipRule, SkipCondition


@pytest.fixture
async def store(tmp_path, monkeypatch):
    """YamlStore backed by a temp file."""
    import config

    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.yaml")
    s = YamlStore()
    await s.load()
    return s


def _library(**overrides) -> Library:
    defaults = {"paths": ["/media/movies"], "preset": "HEVC"}
    defaults.update(overrides)
    return Library(**defaults)


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
