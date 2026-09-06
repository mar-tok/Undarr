import asyncio
import os

import aiosqlite
import pytest

import core.db as db_mod
import core.duplicates as dup_mod
from core.db import (
    SCHEMA,
    PROCESSED_SCHEMA,
    LIBRARY_FILES_SCHEMA,
    FILE_HASHES_SCHEMA,
    upsert_library_file,
    get_cached_hashes,
)
from core.duplicates import scan_duplicates


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


async def _add(path, library, content: bytes):
    path.write_bytes(content)
    mtime = os.stat(path).st_mtime
    await upsert_library_file(str(path), library, "h264", 1080, len(content), mtime)
    return str(path)


# The partial hash reads the first 4096 bytes, so A and B collide there by construction
HEAD = b"h" * 4096
A = HEAD + b"a" * 100
B = HEAD + b"b" * 100


class TestScanDuplicates:
    async def test_empty_library(self, db_setup):
        result = await scan_duplicates(None)
        assert result == {
            "groups": [],
            "total_duplicate_size": 0,
            "total_groups": 0,
            "not_hashed": 0,
        }

    async def test_identical_files_group(self, db_setup, tmp_path):
        p1 = await _add(tmp_path / "a.mkv", "lib1", A)
        p2 = await _add(tmp_path / "b.mkv", "lib1", A)
        await _add(tmp_path / "c.mkv", "lib1", A + b"x")
        result = await scan_duplicates(["lib1"])
        assert result["total_groups"] == 1
        assert result["total_duplicate_size"] == len(A)
        assert sorted(f["file_path"] for f in result["groups"][0]["files"]) == [p1, p2]

    async def test_same_size_and_head_but_different_tail(self, db_setup, tmp_path):
        await _add(tmp_path / "a.mkv", "lib1", A)
        await _add(tmp_path / "b.mkv", "lib1", B)
        result = await scan_duplicates(["lib1"])
        assert result["groups"] == []

    async def test_groups_sorted_by_size_desc(self, db_setup, tmp_path):
        small = b"s" * 10
        await _add(tmp_path / "s1.mkv", "lib1", small)
        await _add(tmp_path / "s2.mkv", "lib1", small)
        await _add(tmp_path / "a1.mkv", "lib1", A)
        await _add(tmp_path / "a2.mkv", "lib1", A)
        result = await scan_duplicates(["lib1"])
        assert [g["file_size"] for g in result["groups"]] == [len(A), len(small)]

    async def test_scope_across_libraries(self, db_setup, tmp_path):
        await _add(tmp_path / "a.mkv", "lib1", A)
        await _add(tmp_path / "b.mkv", "lib2", A)
        assert (await scan_duplicates(["lib1"]))["groups"] == []
        result = await scan_duplicates(None)
        assert sorted(f["library_name"] for f in result["groups"][0]["files"]) == [
            "lib1",
            "lib2",
        ]

    async def test_hashes_are_cached_and_reused(self, db_setup, tmp_path, monkeypatch):
        p1 = await _add(tmp_path / "a.mkv", "lib1", A)
        await _add(tmp_path / "b.mkv", "lib1", A)
        await scan_duplicates(["lib1"])
        cached = await get_cached_hashes([(p1, "lib1")])
        assert cached[(p1, "lib1")]["full_hash"]

        calls = []
        monkeypatch.setattr(
            dup_mod, "_partial_hash", lambda path: calls.append(path) or "x"
        )
        monkeypatch.setattr(
            dup_mod, "_full_hash", lambda path: calls.append(path) or "x"
        )
        result = await scan_duplicates(["lib1"])
        assert calls == []
        assert result["total_groups"] == 1

    async def test_changed_mtime_rehashes(self, db_setup, tmp_path):
        p1 = await _add(tmp_path / "a.mkv", "lib1", A)
        await _add(tmp_path / "b.mkv", "lib1", A)
        await scan_duplicates(["lib1"])
        (tmp_path / "a.mkv").write_bytes(B)
        await upsert_library_file(p1, "lib1", "h264", 1080, len(B), 999.0)
        result = await scan_duplicates(["lib1"])
        assert result["groups"] == []

    async def test_unreadable_file_is_skipped(self, db_setup, tmp_path):
        await _add(tmp_path / "a.mkv", "lib1", A)
        await _add(tmp_path / "b.mkv", "lib1", A)
        await upsert_library_file(
            str(tmp_path / "gone.mkv"), "lib1", "h264", 1080, len(A), 1.0
        )
        result = await scan_duplicates(["lib1"])
        assert len(result["groups"][0]["files"]) == 2
        assert result["not_hashed"] == 0

    async def test_reports_progress(self, db_setup, tmp_path):
        await _add(tmp_path / "a.mkv", "lib1", A)
        await _add(tmp_path / "b.mkv", "lib1", A)
        seen = []

        async def progress(hashed, total):
            seen.append((hashed, total))

        await scan_duplicates(["lib1"], progress_fn=progress)
        assert seen == [(1, 2), (2, 2)]

    async def test_abort_reports_not_hashed(self, db_setup, tmp_path):
        small = b"s" * 10
        await _add(tmp_path / "s1.mkv", "lib1", small)
        await _add(tmp_path / "s2.mkv", "lib1", small)
        await _add(tmp_path / "a1.mkv", "lib1", A)
        await _add(tmp_path / "a2.mkv", "lib1", A)
        abort = asyncio.Event()

        async def progress(hashed, total):
            if hashed == 2:
                abort.set()

        result = await scan_duplicates(
            ["lib1"], progress_fn=progress, abort_event=abort
        )
        assert result["total_groups"] == 1
        assert result["not_hashed"] == 2
