from unittest.mock import AsyncMock

import aiosqlite
import pytest
import yaml
from httpx import AsyncClient, ASGITransport

import config
import core.db as db_mod
from app.server import app
from core.db import (
    SCHEMA,
    PROCESSED_SCHEMA,
    LIBRARY_FILES_SCHEMA,
    FILE_HASHES_SCHEMA,
    insert_job_history,
    upsert_library_file,
    get_library_files_mtimes,
)
from core.queue_manager import Job, JobStatus, QueueManager
from core.yaml_store import YamlStore, BUILTIN_PRESETS

ROUTERS = ("presets", "libraries", "queue", "settings")


@pytest.fixture
async def store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.yaml")
    s = YamlStore()
    await s.load()
    for name in ROUTERS:
        monkeypatch.setattr(f"app.routers.{name}.store", s)
    monkeypatch.setattr("core.queue_manager.store", s)
    return s


@pytest.fixture
def qm(monkeypatch):
    manager = QueueManager()
    manager._device_limits = {"cpu": 1}
    manager._device_active = {"cpu": 0}
    for name in ROUTERS:
        monkeypatch.setattr(f"app.routers.{name}.queue_manager", manager)
    monkeypatch.setattr("app.routers.libraries.watcher.restart", AsyncMock())
    monkeypatch.setattr("app.routers.libraries.periodic_scanner.restart", AsyncMock())
    return manager


@pytest.fixture
async def db_setup():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await conn.executescript(SCHEMA)
    await conn.executescript(PROCESSED_SCHEMA)
    await conn.executescript(LIBRARY_FILES_SCHEMA)
    await conn.executescript(FILE_HASHES_SCHEMA)
    await conn.commit()
    old_db = db_mod._db
    db_mod._db = conn
    yield conn
    db_mod._db = old_db
    await conn.close()


@pytest.fixture
async def client(store, qm, db_setup):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


def _on_disk(store):
    return yaml.safe_load(store._path.read_text())


PRESET = {"name": "Small", "ffmpeg_args": "-c:v libx265 -crf 28"}
LIBRARY = {"name": "movies", "paths": ["/media/movies"], "preset": "Small"}


async def _job(status="completed", job_id="j1", log="frame=1"):
    await insert_job_history(
        id=job_id,
        library_name="movies",
        file_path="/media/movies/a.mkv",
        status=status,
        old_size_bytes=1000,
        new_size_bytes=500,
        started_at="2026-01-01T00:00:00",
        finished_at="2026-01-01T00:01:00",
        duration_seconds=60.0,
        ffmpeg_log=log,
        error_message=None,
    )


async def test_health(client):
    resp = await client.get("/api/health")
    assert resp.json() == {"status": "ok"}


async def test_frontend_files_are_revalidated(client):
    for path in ("/", "/helpers.js"):
        resp = await client.get(path)
        assert resp.headers["cache-control"] == "no-cache"
        resp = await client.get(path, headers={"If-None-Match": resp.headers["etag"]})
        assert resp.status_code == 304
        assert resp.headers["cache-control"] == "no-cache"


class TestPresets:
    async def test_list_starts_with_builtins(self, client):
        resp = await client.get("/api/presets")
        assert resp.status_code == 200
        assert {p["name"] for p in resp.json()} == set(BUILTIN_PRESETS)
        assert all(p["is_builtin"] for p in resp.json())

    async def test_create_persists(self, client, store):
        resp = await client.post("/api/presets", json=PRESET)
        assert resp.status_code == 201
        assert resp.json()["name"] == "Small"
        assert resp.json()["is_builtin"] is False
        assert (
            _on_disk(store)["presets"]["Small"]["ffmpeg_args"] == PRESET["ffmpeg_args"]
        )
        listed = {p["name"] for p in (await client.get("/api/presets")).json()}
        assert "Small" in listed

    async def test_create_rejects_taken_names(self, client):
        await client.post("/api/presets", json=PRESET)
        assert (await client.post("/api/presets", json=PRESET)).status_code == 409
        builtin = {**PRESET, "name": "HEVC Transparent"}
        assert (await client.post("/api/presets", json=builtin)).status_code == 409

    async def test_create_rejects_slash(self, client):
        resp = await client.post("/api/presets", json={**PRESET, "name": "a/b"})
        assert resp.status_code == 422
        assert "/" in resp.text

    async def test_update(self, client, store):
        await client.post("/api/presets", json=PRESET)
        resp = await client.put(
            "/api/presets/Small", json={"ffmpeg_args": "-c:v libx265 -crf 24"}
        )
        assert resp.status_code == 200
        assert resp.json()["ffmpeg_args"] == "-c:v libx265 -crf 24"
        assert (
            _on_disk(store)["presets"]["Small"]["ffmpeg_args"] == "-c:v libx265 -crf 24"
        )

    async def test_update_builtin_forbidden(self, client):
        resp = await client.put(
            "/api/presets/HEVC Transparent", json={"ffmpeg_args": "-c:v libx265"}
        )
        assert resp.status_code == 403

    async def test_update_missing(self, client):
        resp = await client.put(
            "/api/presets/Nope", json={"ffmpeg_args": "-c:v libx265"}
        )
        assert resp.status_code == 404

    async def test_rename(self, client, store):
        await client.post("/api/presets", json=PRESET)
        await client.post("/api/libraries", json=LIBRARY)
        body = {"name": "Smaller", "ffmpeg_args": PRESET["ffmpeg_args"]}
        resp = await client.put("/api/presets/Small", json=body)
        assert resp.status_code == 200
        assert resp.json()["name"] == "Smaller"
        assert set(_on_disk(store)["presets"]) == {"Smaller"}
        assert (await store.get_library("movies")).preset == "Smaller"

    async def test_rename_onto_existing(self, client):
        await client.post("/api/presets", json=PRESET)
        await client.post("/api/presets", json={**PRESET, "name": "Other"})
        body = {"name": "Other", "ffmpeg_args": PRESET["ffmpeg_args"]}
        assert (await client.put("/api/presets/Small", json=body)).status_code == 409
        body["name"] = "AV1 Transparent"
        assert (await client.put("/api/presets/Small", json=body)).status_code == 409

    async def test_delete(self, client, store):
        await client.post("/api/presets", json=PRESET)
        assert (await client.delete("/api/presets/Small")).status_code == 204
        assert "Small" not in _on_disk(store)["presets"]
        assert (await client.delete("/api/presets/Small")).status_code == 404

    async def test_delete_in_use(self, client):
        await client.post("/api/presets", json=PRESET)
        await client.post("/api/libraries", json=LIBRARY)
        resp = await client.delete("/api/presets/Small")
        assert resp.status_code == 409
        assert "movies" in resp.json()["detail"]

    async def test_delete_builtin_forbidden(self, client):
        assert (await client.delete("/api/presets/HEVC Transparent")).status_code == 403


class TestLibraries:
    async def test_create_persists(self, client, store):
        await client.post("/api/presets", json=PRESET)
        resp = await client.post("/api/libraries", json=LIBRARY)
        assert resp.status_code == 201
        assert resp.json()["name"] == "movies"
        assert resp.json()["paused"] is False
        assert _on_disk(store)["libraries"]["movies"]["paths"] == ["/media/movies"]

    async def test_create_with_builtin_preset(self, client):
        body = {**LIBRARY, "preset": "HEVC Transparent"}
        assert (await client.post("/api/libraries", json=body)).status_code == 201

    async def test_create_unknown_preset(self, client):
        resp = await client.post("/api/libraries", json=LIBRARY)
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Preset 'Small' not found"

    async def test_create_duplicate(self, client):
        await client.post("/api/presets", json=PRESET)
        await client.post("/api/libraries", json=LIBRARY)
        assert (await client.post("/api/libraries", json=LIBRARY)).status_code == 409

    async def test_create_overlapping_path(self, client):
        await client.post("/api/presets", json=PRESET)
        await client.post("/api/libraries", json=LIBRARY)
        body = {**LIBRARY, "name": "kids", "paths": ["/media/movies/kids"]}
        resp = await client.post("/api/libraries", json=body)
        assert resp.status_code == 409
        assert resp.json()["detail"] == (
            "Path /media/movies/kids overlaps with library 'movies' (/media/movies)"
        )

    async def test_create_rejects_relative_path(self, client):
        resp = await client.post(
            "/api/libraries", json={**LIBRARY, "paths": ["movies"]}
        )
        assert resp.status_code == 422

    async def test_list(self, client):
        await client.post("/api/presets", json=PRESET)
        await client.post("/api/libraries", json=LIBRARY)
        resp = await client.get("/api/libraries")
        assert [l["name"] for l in resp.json()] == ["movies"]
        assert resp.json()[0]["preset"] == "Small"

    async def test_update_keeps_paused_flag(self, client, qm):
        await client.post("/api/presets", json=PRESET)
        await client.post("/api/libraries", json=LIBRARY)
        await client.post("/api/libraries/movies/pause", json={"paused": True})
        body = {**LIBRARY, "paths": ["/media/films"]}
        resp = await client.put("/api/libraries/movies", json=body)
        assert resp.status_code == 200
        assert resp.json()["paths"] == ["/media/films"]
        assert resp.json()["paused"] is True

    async def test_update_missing(self, client):
        resp = await client.put("/api/libraries/movies", json=LIBRARY)
        assert resp.status_code == 404

    async def test_rename_moves_file_records(self, client, store):
        await client.post("/api/presets", json=PRESET)
        await client.post("/api/libraries", json=LIBRARY)
        await upsert_library_file(
            "/media/movies/a.mkv", "movies", "h264", 1080, 1000, 1.0
        )
        body = {**LIBRARY, "name": "films"}
        resp = await client.put("/api/libraries/movies", json=body)
        assert resp.status_code == 200
        assert set(_on_disk(store)["libraries"]) == {"films"}
        assert await get_library_files_mtimes("films") == {"/media/movies/a.mkv": 1.0}

    async def test_pause(self, client, store, qm):
        await client.post("/api/presets", json=PRESET)
        await client.post("/api/libraries", json=LIBRARY)
        resp = await client.post("/api/libraries/movies/pause", json={"paused": True})
        assert resp.json() == {"paused": True}
        assert qm.paused_libraries == {"movies"}
        assert _on_disk(store)["libraries"]["movies"]["paused"] is True
        await client.post("/api/libraries/movies/pause", json={"paused": False})
        assert qm.paused_libraries == set()

    async def test_pause_missing(self, client):
        resp = await client.post("/api/libraries/movies/pause", json={"paused": True})
        assert resp.status_code == 404

    async def test_delete_clears_records_and_jobs(self, client, store, qm):
        await client.post("/api/presets", json=PRESET)
        await client.post("/api/libraries", json=LIBRARY)
        await client.post("/api/libraries/movies/pause", json={"paused": True})
        await upsert_library_file(
            "/media/movies/a.mkv", "movies", "h264", 1080, 1000, 1.0
        )
        qm._pending.append(
            Job(id="p1", file_path="/media/movies/a.mkv", library_name="movies")
        )
        assert (await client.delete("/api/libraries/movies")).status_code == 204
        assert _on_disk(store)["libraries"] == {}
        assert await get_library_files_mtimes("movies") == {}
        assert qm.pending_jobs == []
        assert qm.paused_libraries == set()
        assert (await client.delete("/api/libraries/movies")).status_code == 404


class TestQueue:
    async def test_get_queue_orders_active_pending_blocked(self, client, qm):
        qm._blocked.append(Job(id="b1", file_path="/m/c.mkv", library_name="movies"))
        qm._pending.append(Job(id="p1", file_path="/m/a.mkv", library_name="movies"))
        qm._active["a1"] = Job(id="a1", file_path="/m/b.mkv", library_name="movies")
        resp = await client.get("/api/queue")
        assert [j["id"] for j in resp.json()] == ["a1", "p1", "b1"]

    async def test_get_queue_empty(self, client):
        assert (await client.get("/api/queue")).json() == []

    async def test_pause_and_resume(self, client, qm):
        resp = await client.post("/api/queue/pause", json={"paused": True})
        assert resp.json() == {"paused": True}
        assert qm.paused is True
        resp = await client.post("/api/queue/pause", json={"paused": False})
        assert resp.json() == {"paused": False}
        assert qm.paused is False

    async def test_cancel(self, client, qm):
        job = Job(id="p1", file_path="/m/a.mkv", library_name="movies")
        qm._pending.append(job)
        assert (await client.delete("/api/queue/p1")).status_code == 204
        assert job.status == JobStatus.CANCELLED
        assert qm.pending_jobs == []
        assert (await client.delete("/api/queue/p1")).status_code == 404

    async def test_cancel_batch_counts_hits(self, client, qm):
        qm._pending.append(Job(id="p1", file_path="/m/a.mkv", library_name="movies"))
        resp = await client.post("/api/queue/cancel", json={"ids": ["p1", "nope"]})
        assert resp.json() == {"cancelled": 1}


class TestSettings:
    async def test_get_defaults(self, client):
        resp = await client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert data["cache_dir"] == "/tmp/undarr"
        assert data["process_priority"] == "normal"
        assert data["queue_order"] == "fifo"
        assert data["server_timezone"]

    async def test_patch_persists(self, client, store):
        resp = await client.patch("/api/settings", json={"process_priority": "low"})
        assert resp.status_code == 200
        assert resp.json()["process_priority"] == "low"
        assert _on_disk(store)["settings"]["process_priority"] == "low"

    @pytest.mark.parametrize(
        "body, detail",
        [
            ({"process_priority": "ultra"}, "process_priority must be one of"),
            ({"queue_order": "random"}, "queue_order must be one of"),
            ({"max_size_ratio": 1.5}, "max_size_ratio must be between"),
            ({"cache_dir": "  "}, "Cache folder cannot be empty"),
            ({"schedule": {"mon": [True] * 24}}, "Schedule must have exactly keys"),
            (
                {
                    "schedule": {
                        d: [True] * 12
                        for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
                    }
                },
                "list of 24 booleans",
            ),
        ],
    )
    async def test_patch_rejects(self, client, store, body, detail):
        before = _on_disk(store)
        resp = await client.patch("/api/settings", json=body)
        assert resp.status_code == 400
        assert detail in resp.json()["detail"]
        assert _on_disk(store) == before

    @pytest.mark.parametrize(
        "running, latest, shown",
        [
            ("0.1.0", "0.2.0", "0.2.0"),
            ("0.9.0", "0.10.0", "0.10.0"),
            ("0.1.0", "0.1.0", None),
            ("0.2.0", "0.1.0", None),
            ("0.1.0", "nightly", None),
            ("0.1.0", None, None),
        ],
    )
    async def test_version_shows_only_newer_release(
        self, client, monkeypatch, running, latest, shown
    ):
        monkeypatch.setattr("app.routers.settings.APP_VERSION", running)
        monkeypatch.setattr(
            "app.routers.settings._check_latest_version",
            AsyncMock(return_value=latest),
        )
        data = (await client.get("/api/version")).json()
        assert data["version"] == running
        assert data.get("latest") == shown


class TestHistory:
    async def test_get_history_filters_by_status(self, client):
        await _job("completed", "j1")
        await _job("failed", "j2")
        resp = await client.get("/api/history")
        assert {r["id"] for r in resp.json()} == {"j1", "j2"}
        resp = await client.get("/api/history", params={"status": "failed"})
        assert [r["id"] for r in resp.json()] == ["j2"]

    async def test_get_history_limit_bounds(self, client):
        assert (
            await client.get("/api/history", params={"limit": 0})
        ).status_code == 422
        assert (
            await client.get("/api/history", params={"limit": 501})
        ).status_code == 422

    async def test_job_log(self, client):
        await _job(log="frame=42")
        resp = await client.get("/api/history/j1/log")
        assert resp.json() == {"log": "frame=42"}
        assert (await client.get("/api/history/nope/log")).status_code == 404

    async def test_clear_history(self, client):
        await _job()
        assert (await client.delete("/api/history")).status_code == 204
        assert (await client.get("/api/history")).json() == []
