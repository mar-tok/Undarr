from __future__ import annotations

import aiosqlite

import config
from core.logger import log

_db: aiosqlite.Connection | None = None

SCHEMA = """\
CREATE TABLE IF NOT EXISTS job_history (
    id               TEXT PRIMARY KEY,
    library_name     TEXT NOT NULL,
    file_path        TEXT NOT NULL,
    status           TEXT NOT NULL,
    old_size_bytes   INTEGER NOT NULL,
    new_size_bytes   INTEGER,
    started_at       TEXT NOT NULL,
    finished_at      TEXT NOT NULL,
    duration_seconds REAL NOT NULL,
    ffmpeg_log       TEXT NOT NULL DEFAULT '',
    error_message    TEXT
);
"""


async def init_db() -> None:
    global _db
    db_path = config.DATA_DIR / "undarr.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _db = await aiosqlite.connect(str(db_path))
    _db.row_factory = aiosqlite.Row
    await _db.executescript(SCHEMA)
    await _db.commit()
    log.info("Database initialized at %s", db_path)


async def close_db() -> None:
    global _db
    if _db:
        await _db.close()
        _db = None


def get_db() -> aiosqlite.Connection:
    assert _db is not None, "Database not initialized"
    return _db


async def insert_job_history(
    *,
    id: str,
    library_name: str,
    file_path: str,
    status: str,
    old_size_bytes: int,
    new_size_bytes: int | None,
    started_at: str,
    finished_at: str,
    duration_seconds: float,
    ffmpeg_log: str,
    error_message: str | None,
) -> None:
    db = get_db()
    await db.execute(
        """INSERT INTO job_history
           (id, library_name, file_path, status, old_size_bytes, new_size_bytes,
            started_at, finished_at, duration_seconds, ffmpeg_log, error_message)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (id, library_name, file_path, status, old_size_bytes, new_size_bytes,
         started_at, finished_at, duration_seconds, ffmpeg_log, error_message),
    )
    await db.commit()
