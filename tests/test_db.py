import aiosqlite

import core.db as db_mod
from core.db import (
    SCHEMA,
    PROCESSED_SCHEMA,
    mark_processed,
    is_processed,
    remove_processed,
)

import pytest


@pytest.fixture
async def db_setup():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await conn.executescript(SCHEMA)
    await conn.executescript(PROCESSED_SCHEMA)
    await conn.commit()
    old_db = db_mod._db
    db_mod._db = conn
    yield conn
    db_mod._db = old_db
    await conn.close()


class TestMarkAndIsProcessed:
    async def test_mark_and_check(self, db_setup):
        await mark_processed("/media/m.mkv", "lib1", 1000.0)
        assert await is_processed("/media/m.mkv", "lib1", 1000.0) is True

    async def test_mtime_differs(self, db_setup):
        await mark_processed("/media/m.mkv", "lib1", 1000.0)
        assert await is_processed("/media/m.mkv", "lib1", 2000.0) is False

    async def test_mtime_within_tolerance(self, db_setup):
        await mark_processed("/media/m.mkv", "lib1", 1000.0)
        # 0.0005 difference is within the 0.001 tolerance
        assert await is_processed("/media/m.mkv", "lib1", 1000.0005) is True

    async def test_path_not_in_db(self, db_setup):
        assert await is_processed("/media/unknown.mkv", "lib1", 1000.0) is False


class TestRemoveProcessed:
    async def test_removes_entry(self, db_setup):
        await mark_processed("/a.mkv", "lib1", 1.0)
        await remove_processed("/a.mkv", "lib1")
        assert not await is_processed("/a.mkv", "lib1", 1.0)
